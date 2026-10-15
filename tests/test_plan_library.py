import copy
import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

from plan_library import PlanLibrary
from tracker import CURRICULUM, Tracker, TrackerError, validate_curriculum
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'packaging'))
from install_user import copy_legacy_data, migrate_legacy

SAMPLE = Path(__file__).resolve().parents[1] / 'examples' / 'sample_plan_v3.json'


class PlanLibraryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.library = PlanLibrary(self.temp.name)
        self.sample = json.loads(SAMPLE.read_text(encoding='utf-8'))
        self.sample['plan_id'] = 'alternate-one-week-v3'
        self.sample['plan_name'] = '另一个示例计划'

    def test_builtin_curriculum_and_sample(self):
        original = json.loads(CURRICULUM.read_text(encoding='utf-8'))
        self.assertEqual(validate_curriculum(original)['minutes'], 7 * 60)
        self.assertTrue(validate_curriculum(self.sample)['valid'])
        self.assertEqual(self.sample['weeks'], 1)
        self.assertEqual(self.library.bootstrap()['weeks'], 1)
        bad = copy.deepcopy(self.sample)
        bad['days'].pop()
        self.assertFalse(validate_curriculum(bad)['valid'])
        with self.assertRaises(TrackerError):
            self.library.preview_plan(bad)

    def test_import_preview_is_read_only_and_progress_isolated(self):
        self.library.update_progress('W01D01', status='in_progress', note='builtin')
        result = self.library.preview_plan(self.sample)
        self.assertEqual(len(result['added']), 7)
        self.assertFalse((Path(self.temp.name) / 'plans').exists())
        self.library.apply_plan(self.sample)
        self.assertEqual(len(self.library.list_days()), 7)
        self.assertEqual(self.library.get_day('W01D01')['progress']['note'], '')
        self.library.update_progress('W01D01', status='submitted', note='sample')
        self.library.select_plan(self.library.default_id)
        self.assertEqual(self.library.get_day('W01D01')['progress']['note'], 'builtin')
        self.library.select_plan(self.sample['plan_id'])
        self.assertEqual(self.library.get_day('W01D01')['progress']['note'], 'sample')
        self.assertEqual(PlanLibrary(self.temp.name).active_plan_id, self.sample['plan_id'])

    def test_reimport_same_id_keeps_progress_and_archives_removed_days(self):
        longer = copy.deepcopy(self.sample)
        second_week = copy.deepcopy(self.sample['days'])
        for day in second_week:
            day['week'] = 2
            day['id'] = day['id'].replace('W01', 'W02')
            for exercise in day['coding_exercises']:
                exercise['id'] = exercise['id'].replace('W01', 'W02')
            for criterion in day['acceptance_tests']:
                criterion['id'] = criterion['id'].replace('W01', 'W02')
        longer['weeks'] = 2
        longer['weekly_themes'] = self.sample['weekly_themes'] * 2
        longer['days'] = self.sample['days'] + second_week
        longer['leetcode_weekly']['2'] = self.sample['leetcode_weekly']['1']
        longer['total_planned_hours'] = 14
        self.assertTrue(validate_curriculum(longer)['valid'])
        self.library.apply_plan(longer)
        self.library.update_progress('W02D01', status='submitted', note='keep')
        self.assertEqual(len(self.library.preview_plan(self.sample)['removed']), 7)
        self.library.apply_plan(self.sample)
        self.assertEqual(len(self.library.list_days()), 7)
        with self.assertRaises(TrackerError):
            self.library.get_day('W02D01')
        self.library.apply_plan(longer)
        self.assertEqual(self.library.get_day('W02D01')['progress']['note'], 'keep')

    def test_timer_blocks_switch_and_wrong_plan_backup(self):
        default_backup = self.library.export()
        self.library.apply_plan(self.sample)
        with self.assertRaisesRegex(TrackerError, '另一计划'):
            self.library.restore_preview(default_backup)
        sample_backup = self.library.export()
        self.assertEqual(sample_backup['plan_id'], self.sample['plan_id'])
        self.library.start_session('W01D01')
        with self.assertRaisesRegex(TrackerError, '计时'):
            self.library.select_plan(self.library.default_id)
        with self.assertRaisesRegex(TrackerError, '计时'):
            self.library.restore(sample_backup)
        self.library.stop_session()
        self.library.select_plan(self.library.default_id)

    def test_legacy_backup_identified_by_curriculum_hashes(self):
        old_style = self.library.export()
        del old_style['plan_id']
        self.assertEqual(self.library.restore_preview(old_style)['tables']['curriculum_day']['backup'], 7)
        other = copy.deepcopy(self.sample)
        other['days'][0]['title'] = '另一份课程内容'
        self.library.apply_plan(other)
        with self.assertRaisesRegex(TrackerError, '不匹配'):
            self.library.restore_preview(old_style)

    def test_user_installer_migrates_legacy_plan_and_db(self):
        root = Path(self.temp.name)
        old_app = root / 'old_app'
        source = old_app / 'curriculum' / 'curriculum_v3.json'
        source.parent.mkdir(parents=True)
        source.write_text(json.dumps(self.sample, ensure_ascii=False), encoding='utf-8')
        legacy_data = root / 'legacy_data'
        legacy = Tracker(legacy_data, curriculum_path=source)
        legacy.update_progress('W01D01', status='submitted', note='saved')
        self.assertTrue(migrate_legacy(old_app, legacy_data))
        migrated = PlanLibrary(legacy_data)
        self.assertEqual(migrated.active_plan_id, self.sample['plan_id'])
        self.assertEqual(migrated.get_day('W01D01')['progress']['note'], 'saved')
        self.assertTrue((legacy_data / 'tracker.sqlite3').exists())

    def test_renamed_data_directory_preserves_old_copy(self):
        root = Path(self.temp.name)
        old = root / 'llm-study-tracker'
        new = root / 'studywaypoint'
        old.mkdir()
        (old / 'marker.txt').write_text('before')
        self.assertTrue(copy_legacy_data(old, new))
        self.assertEqual((new / 'marker.txt').read_text(), 'before')
        (new / 'marker.txt').write_text('after')
        self.assertEqual((old / 'marker.txt').read_text(), 'before')
        self.assertFalse(copy_legacy_data(old, new))

    def test_old_schema_migration(self):
        db_path = self.library.active.db_path
        with sqlite3.connect(db_path) as db:
            db.execute('ALTER TABLE curriculum_day RENAME TO curriculum_day_old')
            db.execute('CREATE TABLE curriculum_day (id TEXT PRIMARY KEY, week INTEGER NOT NULL, day INTEGER NOT NULL, payload TEXT NOT NULL, sha256 TEXT NOT NULL, version TEXT NOT NULL)')
            db.execute('INSERT INTO curriculum_day SELECT id,week,day,payload,sha256,version FROM curriculum_day_old')
            db.execute('DROP TABLE curriculum_day_old')
        migrated = Tracker(db_path.parent)
        self.assertEqual(len(migrated.list_days()), 7)
        with migrated.connect() as db:
            self.assertIn('is_active', {row['name'] for row in db.execute('PRAGMA table_info(curriculum_day)')})


if __name__ == '__main__':
    unittest.main()
