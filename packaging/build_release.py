"""Build the Debian package, source archive and checksums for a GitHub release."""

from __future__ import annotations

import hashlib
import os
import sys
import zipfile
from pathlib import Path

from build_deb import ROOT, VERSION, build

OUTPUT = Path(os.getenv('STUDYWAYPOINT_OUTPUT_DIR', ROOT.parent))
FILES = [
    '.gitignore', 'AGENTS.md', 'README.md', 'USER_GUIDE.md', 'CHANGELOG.md', 'log.md',
    f'RELEASE_NOTES_{VERSION}.md', 'desktop.py', 'server.py', 'tracker.py',
    'plan_library.py', 'ai_planner.py', 'run.sh', 'run-desktop.sh',
]
FOLDERS = ['assets', 'examples', 'packaging', 'static', 'tests']


def source_files():
    result = [ROOT / name for name in FILES]
    for folder in FOLDERS:
        result.extend(path for path in (ROOT / folder).rglob('*') if path.is_file()
                      and '__pycache__' not in path.parts and path.suffix != '.pyc')
    result.extend((ROOT / 'docs').glob('release_*.md'))
    return sorted(result)


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    deb = build(OUTPUT / f'studywaypoint_{VERSION}_all.deb')
    archive = OUTPUT / f'StudyWaypoint-{VERSION}-source.zip'
    with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as output:
        for path in source_files():
            relative = path.relative_to(ROOT)
            info = zipfile.ZipInfo(f'StudyWaypoint-{VERSION}/{relative}', date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = (0o755 if path.name in ('run.sh', 'run-desktop.sh') else 0o644) << 16
            output.writestr(info, path.read_bytes(), compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
    checksums = OUTPUT / 'SHA256SUMS'
    with checksums.open('w', encoding='utf-8') as output:
        for path in (deb, archive):
            output.write(f'{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}\n')
    for path in (deb, archive, checksums):
        print(path)


if __name__ == '__main__':
    main()
