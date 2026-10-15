const app = document.getElementById('app');
const notice = document.getElementById('message');
const state = { bootstrap:null, days:[], day:null, view:'today', week:1, active:null, restoreData:null, importData:null };
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const pct = n => `${Math.max(0, Math.min(100, n))}%`;
const minutes = n => `${Math.round(n)} 分钟`;
const dateText = (dayId) => {
  const start = state.bootstrap?.settings.start_date;
  if (!start) return '';
  const match = /W(\d+)D(\d+)/.exec(dayId);
  const base = new Date(`${start}T12:00:00Z`);
  base.setUTCDate(base.getUTCDate() + (Number(match[1])-1)*7 + Number(match[2])-1);
  return base.toISOString().slice(0,10);
};
async function api(path, method='GET', body) {
  const response = await fetch(path, {method, headers: body ? {'Content-Type':'application/json'} : {}, body: body ? JSON.stringify(body) : undefined});
  const data = await response.json();
  if (!response.ok) throw new Error(data.error?.message || `HTTP ${response.status}`);
  return data;
}
function flash(message, error=false) {
  notice.textContent = message; notice.className = error ? 'error' : '';
  clearTimeout(flash.timer); flash.timer = setTimeout(() => { notice.textContent=''; notice.className=''; }, 4200);
}
async function refresh() {
  const previousPlan=state.bootstrap?.active_plan_id;
  [state.bootstrap,state.days] = await Promise.all([api('/api/bootstrap'),api('/api/days')]);
  if(previousPlan && previousPlan!==state.bootstrap.active_plan_id) { state.day=null; state.week=1; }
  state.week=Math.max(1,Math.min(state.week,state.bootstrap.weeks));
  state.active = (await api('/api/sessions/active')).session;
  if (state.view==='today' && state.bootstrap.today_id) state.day=await api(`/api/days/${state.bootstrap.today_id}`);
  else if (state.day && state.days.some(d=>d.id===state.day.id)) state.day = await api(`/api/days/${state.day.id}`);
  else if(state.view==='day') {state.day=null;state.view='calendar';}
  render();
}
function setView(view) { state.view=view; render(); window.scrollTo({top:0,behavior:'smooth'}); }
async function openDay(id) { state.day=await api(`/api/days/${id}`); state.week=state.day.week; state.view='day'; render(); window.scrollTo({top:0,behavior:'smooth'}); }
function nav() { ['today','calendar','settings'].forEach(x => document.getElementById(`nav-${x}`).classList.toggle('active',state.view===x)); }
function render() {
  nav();
  if (state.view==='settings') app.innerHTML=settingsView();
  else if (state.view==='calendar') app.innerHTML=calendarView();
  else if (state.view==='day' && state.day) app.innerHTML=dayView(state.day);
  else app.innerHTML=todayView();
  updateTimer();
}
function hero(kicker,title,description,actions='') { return `<div class="hero"><div><div class="eyebrow">${esc(kicker)}</div><h1>${esc(title)}</h1><p class="lead">${esc(description)}</p></div><div class="actions">${actions}</div></div>`; }
function todayView() {
  const today=state.bootstrap.today_id;
  const count=state.days.length;
  if (!state.bootstrap.settings.start_date) return `<div class="setup card">${hero('开始你的学习计划','设定学习起点','设置开始日期后，首页会按你所在的时区自动找到对应的 Week / Day。')}<form id="setup-form"><div class="two-col"><div class="field"><label for="setup-start">开始日期</label><input id="setup-start" type="date" required></div><div class="field"><label for="setup-zone">时区</label><input id="setup-zone" value="Asia/Shanghai" required></div></div><button class="button primary" type="submit">保存并开始</button> <button class="button" type="button" data-view="calendar">先查看全部 ${count} 天</button></form></div>`;
  if (!today) return `${hero('今日学习','当前日期不在计划内','可浏览完整课程，或在设置中调整起始日期。',`<button class="button primary" data-view="calendar">查看全部 ${count} 天</button>`)}${calendarSummary()}`;
  if (state.day?.id===today) return dayView(state.day);
  const summary=state.days.find(d=>d.id===today);
  return `${hero('今日学习 · '+dateText(today),'今天学什么',`第 ${summary.week} 周 · 第 ${summary.day} 天 · ${summary.title}`,`<button class="button primary" data-day="${today}">打开今日任务</button><button class="button" data-view="calendar">查看全部 ${count} 天</button>`)}${calendarSummary()}`;
}
function calendarSummary() {
  const done=state.days.filter(d=>d.mastered).length;
  const started=state.days.filter(d=>d.status!=='not_started').length;
  const count=state.days.length, weeks=state.bootstrap.weeks;
  return `<div class="grid"><div class="card metric"><span>${esc(state.bootstrap.plan_name)}</span><strong>${count} 天</strong><span>${weeks} 周 · 共 ${state.bootstrap.total_planned_hours} 小时</span></div><div class="card metric"><span>已开始的学习日</span><strong>${started} / ${count}</strong><div class="progress"><i style="width:${pct(started/count*100)}"></i></div></div><div class="card metric"><span>全部验收通过的学习日</span><strong>${done} / ${count}</strong><span>以逐项验收结果计算</span></div></div><div class="card" style="margin-top:16px"><div class="section-title"><h2>${weeks} 周路线</h2><button class="mini" data-view="calendar">进入日历 →</button></div><div class="week-nav">${state.bootstrap.weekly_themes.map((name,i)=>`<button class="week-btn" data-week="${i+1}"><b>Week ${i+1}</b><span>${esc(name)}</span></button>`).join('')}</div></div>`;
}
function calendarView() {
  const w=state.week, list=state.days.filter(d=>d.week===w), theme=state.bootstrap.weekly_themes[w-1];
  const hours=list.reduce((sum,d)=>sum+d.planned_minutes,0)/60;
  return `${hero('课程总览',esc(state.bootstrap.plan_name),`按周浏览全部 ${state.days.length} 天任务；个人进度保存在此计划独立的数据库中。`)}<div class="calendar-layout"><aside class="week-nav" aria-label="选择周次">${state.bootstrap.weekly_themes.map((name,i)=>`<button class="week-btn ${w===i+1?'active':''}" data-week="${i+1}"><b>Week ${i+1}</b><span>${esc(name)}</span></button>`).join('')}</aside><section class="card"><div class="section-title"><div><div class="eyebrow">WEEK ${w} / ${state.bootstrap.weeks}</div><h2>${esc(theme)}</h2></div><span class="pill teal">${hours} 小时</span></div><p class="week-caption">每天都有课程阅读、动手练习、交付物和验收。点击日期查看完整内容。</p><div class="days-grid">${list.map(d=>`<button class="day-tile" data-day="${d.id}"><span class="day-num">DAY ${d.day}${dateText(d.id)?' · '+dateText(d.id):''}</span><strong>${esc(d.title)}</strong><small>${d.planned_minutes/60} 小时 · ${statusLabel(d.status)}</small></button>`).join('')}</div><div class="divider"></div><h3>本周 LeetCode</h3><div class="stack">${(state.bootstrap.leetcode_weekly[String(w)]||[]).map(q=>`<a href="${esc(q.url)}" target="_blank" rel="noopener noreferrer">${esc(q.title)} ↗</a>`).join('')}</div></section></div>`;
}
const statusMap={not_started:'未开始',in_progress:'进行中',submitted:'已提交',passed:'通过',failed:'未通过',deferred:'延期',skipped:'跳过'};
function statusLabel(status) { return statusMap[status] || '未开始'; }
function dayView(d) {
  const budget=d.effective_budget;
  const spent=d.actual_seconds/60;
  const evidence=d.evidence_items;
  const acceptancePassed=d.acceptance_tests.every(a=>d.acceptance_progress[a.id]?.status==='passed');
  const note=acceptancePassed ? '必需验收已逐项通过。' : '仍有验收未通过；阅读和打卡不会自动判定掌握。';
  return `${hero(`WEEK ${d.week} · DAY ${d.day}${dateText(d.id)?' · '+dateText(d.id):''}`,d.title,d.course_section,`<button class="button" data-view="calendar">← 返回日历</button>`)}
    <div class="grid" style="margin-bottom:16px"><div class="card metric"><span>今日计划</span><strong>${minutes(d.effective_planned_minutes)}</strong><span>理论 ${budget.theory_minutes} · 实践 ${budget.practice_minutes} · 验收 ${budget.verification_minutes}</span></div><div class="card metric"><span>实际学习</span><strong>${minutes(spent)}</strong><span>剩余 ${minutes(Math.max(0,d.effective_planned_minutes-spent))}</span></div><div class="card metric"><span>计划完成 / 验收通过</span><strong>${d.completion_rate}% / ${d.acceptance_rate}%</strong><span>${note}</span></div></div>
    <div class="detail-layout"><div class="detail-main">
      <section class="card"><div class="section-title"><h2>01 · 课程阅读</h2><span class="pill">${budget.theory_minutes} 分钟预算</span></div>${d.course_readings.map((r,i)=>`<div class="item"><input class="check" type="checkbox" aria-label="标记阅读 ${esc(r.title)}" data-toggle="reading" data-id="${d.id}:R${i}" ${d.reading_progress[`${d.id}:R${i}`]?'checked':''}><div class="item-body resource-link"><a href="${esc(r.url)}" target="_blank" rel="noopener noreferrer">${esc(r.title)}</a><small>${esc(r.url)}</small><div class="item-meta">${r.mandatory?'必修':'选读'} · 预计 ${r.estimated_minutes} 分钟 · ${esc(r.type)}</div></div></div>`).join('')}</section>
      <section class="card"><div class="section-title"><h2>02 · 动手练习</h2><span class="pill">${budget.practice_minutes} 分钟预算</span></div><p class="muted top-note">请亲自完成代码与实验。勾选表示步骤已做，不代表验收通过。</p>${d.coding_exercises.map(e=>`<div class="item"><input class="check" type="checkbox" aria-label="标记练习 ${esc(e.title)}" data-toggle="exercise" data-id="${esc(e.id)}" ${d.exercise_progress[e.id]?'checked':''}><div class="item-body"><div class="item-title">${esc(e.title)}</div><div>${esc(e.instructions)}</div><div class="item-meta">${e.requires_manual_implementation?'需独立实现 · ':''}预期产物：${e.expected_artifacts.map(esc).join('、')}</div><div class="item-meta">验证：${esc(e.verification)}</div></div></div>`).join('')}</section>
      <section class="card"><div class="section-title"><h2>03 · 交付物与验收</h2><span class="pill gold">${budget.verification_minutes} 分钟预算</span></div><div class="soft"><b>交付物</b><ul class="small-list">${d.deliverables.map(x=>`<li><span class="code">${esc(x)}</span></li>`).join('')}</ul></div><div class="divider"></div>${d.acceptance_tests.map(a=>acceptanceView(a,d)).join('')}</section>
      ${d.leetcode?.length?`<section class="card"><div class="section-title"><h2>本日 LeetCode</h2><span class="pill">已含在今日预算</span></div>${d.leetcode.map(q=>`<div class="item"><div class="item-body"><a href="${esc(q.url)}" target="_blank" rel="noopener noreferrer">${esc(q.title)} ↗</a><div class="item-meta">建议用 Python 完成并记录复杂度、复盘与提交证据</div></div></div>`).join('')}</section>`:''}
      <section class="card" id="reflection"><div class="section-title"><h2>04 · 今日复盘</h2><span class="pill ${d.reflection?'teal':'gold'}">${d.reflection?'已填写':'未复盘'}</span></div><p class="muted">实际学习 ${minutes(spent)}。可跳过复盘，未填写状态会保留。</p><form id="reflection-form"><div class="two-col"><div class="field"><label>完成产物 / 成果</label><textarea name="achievements">${esc(d.reflection?.achievements||'')}</textarea></div><div class="field"><label>测试结果</label><textarea name="tests">${esc(d.reflection?.tests||'')}</textarea></div><div class="field"><label>卡点与失败原因</label><textarea name="blockers">${esc(d.reflection?.blockers||'')}</textarea></div><div class="field"><label>明日优先事项</label><textarea name="tomorrow">${esc(d.reflection?.tomorrow||'')}</textarea></div></div><button class="button primary" type="submit">保存复盘</button></form></section>
    </div><aside class="detail-side">
      <section class="card"><h2>学习计时</h2><div id="timer" class="timer">00:00:00</div><p class="muted" id="timer-state">未开始</p><div class="form-row"><button class="button primary" data-action="start-timer" ${state.active&&state.active.day_id!==d.id?'disabled':''}>开始 / 继续</button><button class="button" data-action="stop-timer" ${!state.active||state.active.day_id!==d.id?'disabled':''}>暂停 / 结束</button></div><div class="divider"></div><form id="manual-form"><div class="field"><label>补录分钟</label><input name="minutes" type="number" min="1" max="1440" required></div><div class="field"><label>备注</label><input name="note" placeholder="例如：线下阅读"></div><button class="mini" type="submit">补录学习时间</button></form><p class="muted">计时器重启后可继续；一次只计一个学习日，避免重复计算。</p></section>
      <section class="card"><h2>任务与笔记</h2><form id="progress-form"><div class="field"><label>今日状态</label><select name="status">${Object.entries(statusMap).map(([k,v])=>`<option value="${k}" ${d.progress.status===k?'selected':''}>${v}</option>`).join('')}</select></div><div class="field"><label>学习笔记 / 卡点</label><textarea name="note">${esc(d.progress.note)}</textarea></div><button class="mini" type="submit">保存状态与笔记</button></form><p class="muted">状态和逐项验收分开保存。</p></section>
      <section class="card"><h2>添加证据</h2><form id="evidence-form"><div class="field"><label>关联验收</label><select name="criterion_id"><option value="">通用证据</option>${d.acceptance_tests.map(a=>`<option value="${a.id}">${esc(a.assertion)}</option>`).join('')}</select></div><div class="field"><label>证据类型</label><select name="type"><option value="text">文字说明</option><option value="url">URL</option><option value="source_file">文件路径</option><option value="git_commit">Git commit</option><option value="test_log">测试日志</option><option value="screenshot">截图路径</option><option value="notes">笔记</option><option value="benchmark_result">基准结果</option></select></div><div class="field"><label>内容或路径</label><textarea name="content" required placeholder="粘贴提交 hash、测试结果、URL 或相对路径"></textarea></div><button class="button dark" type="submit">保存证据</button></form><div class="evidence-list">${evidence.length?evidence.map(e=>`<div class="evidence-row">#${e.id} · ${esc(e.type)}${e.criterion_id?' · '+esc(e.criterion_id):''}<br>${esc(e.content)}</div>`).join(''):'<span class="muted">暂无证据</span>'}</div></section>
      <section class="card"><h2>调整今日预算</h2><form id="budget-form"><div class="three-col"><div class="field"><label>理论</label><input name="theory_minutes" type="number" min="0" max="1440" value="${budget.theory_minutes}" required></div><div class="field"><label>实践</label><input name="practice_minutes" type="number" min="0" max="1440" value="${budget.practice_minutes}" required></div><div class="field"><label>验收</label><input name="verification_minutes" type="number" min="0" max="1440" value="${budget.verification_minutes}" required></div></div><button class="mini" type="submit">保存分钟预算</button></form><p class="muted">三项相加为今日总预算，调整会记录历史。</p></section>
    </aside></div>`;
}
function acceptanceView(a,d) {
  const progress=d.acceptance_progress[a.id] || {status:'not_started',evidence_id:null,note:''};
  const eligible=d.evidence_items.filter(e=>e.criterion_id===a.id || e.criterion_id===null);
  return `<div class="item"><div class="item-body"><div class="item-title">${esc(a.assertion)} <span class="pill ${progress.status==='passed'?'teal':progress.status==='failed'?'red':'gold'}">${statusLabel(progress.status)}</span></div><div class="item-meta">${a.evidence_required?'需证据':'可无证据'} · ${esc(a.pass_rule)}</div><form class="acceptance-form" data-criterion="${a.id}"><div class="two-col"><div class="field"><label>验收状态</label><select name="status">${['not_started','in_progress','submitted','passed','failed'].map(s=>`<option value="${s}" ${progress.status===s?'selected':''}>${statusLabel(s)}</option>`).join('')}</select></div><div class="field"><label>关联证据</label><select name="evidence_id"><option value="">请选择证据</option>${eligible.map(e=>`<option value="${e.id}" ${progress.evidence_id===e.id?'selected':''}>#${e.id} ${esc(e.type)} · ${esc(e.content.slice(0,32))}</option>`).join('')}</select></div></div><div class="field"><label>审核备注</label><input name="note" value="${esc(progress.note)}" placeholder="记录测试结论或解释"></div><button class="mini" type="submit">保存验收</button></form></div></div>`;
}
function settingsView() {
  const settings=state.bootstrap.settings;
  const planRows=state.bootstrap.plans.map(p=>`<div class="item"><div class="item-body"><b>${esc(p.plan_name)}</b> ${p.active?'<span class="pill teal">当前计划</span>':''}<div class="item-meta">${esc(p.plan_id)} · ${p.weeks} 周 / ${p.days} 天 / ${p.total_planned_hours} 小时 · v${esc(p.curriculum_version)}</div></div>${p.active?'':`<button class="mini" data-plan="${esc(p.plan_id)}">切换</button>`}</div>`).join('');
  return `${hero('个人设置','学习计划与数据','每个计划有独立的学习记录。更改起始日期只影响“今日”对应的课程日。')}<div class="grid"><section class="card"><h2>日期与时区</h2><form id="settings-form"><div class="field"><label>学习起始日</label><input name="start_date" type="date" value="${esc(settings.start_date)}" required></div><div class="field"><label>时区</label><input name="timezone" value="${esc(settings.timezone)}" required></div><button class="button primary" type="submit">保存设置</button></form></section><section class="card"><h2>计划库</h2><p>选择同格式的 v3 JSON 文件；先校验并预览差异，再导入。相同 plan_id 更新原计划并保留进度，新 plan_id 建立独立进度。</p>${planRows}<div class="field"><label>导入计划 JSON</label><input id="plan-file" type="file" accept="application/json,.json"></div><div id="plan-result" class="muted"></div><div class="form-row"><button class="button primary" data-action="apply-plan" ${state.importData?'':'disabled'}>确认导入</button><button class="button" data-action="sample-plan">下载示例计划</button></div></section><section class="card"><h2>备份与恢复</h2><p>备份包含当前计划的课程快照与全部学习历史。恢复只影响当前计划。</p><button class="button dark" data-action="export">下载当前计划备份</button><div class="field"><label>选择备份 JSON</label><input id="restore-file" type="file" accept="application/json,.json"></div><div id="restore-result" class="muted"></div><button class="button" data-action="apply-restore" disabled>确认恢复</button></section></div><div class="soft warning" style="margin-top:16px">课程链接需要联网。证据中的路径只作为文字保存；应用不会执行实验代码。</div>`;
}
function formValues(form) { return Object.fromEntries(new FormData(form).entries()); }
function downloadJson(data, filename) { const blob=new Blob([JSON.stringify(data,null,2)+'\n'],{type:'application/json'});const url=URL.createObjectURL(blob);const a=document.createElement('a');a.href=url;a.download=filename;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000); }
async function mutate(action, success) { try { await action(); if(success) flash(success); await refresh(); } catch(e) { flash(e.message,true); render(); } }
document.addEventListener('click', async event => {
  const node=event.target.closest('[data-view],[data-day],[data-week],[data-plan],[data-action]'); if(!node) return;
  if(node.dataset.view) {
    if (node.dataset.view==='today') { state.view='today'; await refresh(); window.scrollTo({top:0,behavior:'smooth'}); }
    else setView(node.dataset.view);
    return;
  }
  if(node.dataset.day) { try { await openDay(node.dataset.day); } catch(e) { flash(e.message,true); } return; }
  if(node.dataset.week) { state.week=Number(node.dataset.week); setView('calendar'); return; }
  if(node.dataset.plan) return mutate(()=>api('/api/plans/select','POST',{plan_id:node.dataset.plan}),'已切换计划');
  const action=node.dataset.action, day=state.day;
  if(action==='start-timer') return mutate(async()=>{ state.active=await api('/api/sessions/start','POST',{day_id:day.id}); },'计时已开始');
  if(action==='stop-timer') return mutate(async()=>{ await api('/api/sessions/stop','POST'); state.active=null; },'计时已结束');
  if(action==='apply-plan' && state.importData) return mutate(async()=>{await api('/api/plans/import/apply','POST',state.importData);state.importData=null;},'计划已导入并切换');
  if(action==='sample-plan') {try {downloadJson(await api('/api/plans/template'),'sample_plan_v3.json');flash('示例计划已下载');}catch(e){flash(e.message,true)}return;}
  if(action==='export') { try { downloadJson(await api('/api/export'),`studywaypoint-${state.bootstrap.active_plan_id}-${new Date().toISOString().slice(0,10)}.json`);flash('备份已下载'); } catch(e){flash(e.message,true)} return; }
  if(action==='apply-restore' && state.restoreData) return mutate(()=>api('/api/restore/apply','POST',state.restoreData),'备份已恢复');
});
document.addEventListener('change', async event => {
  const node=event.target;
  if(node.dataset.toggle && state.day) { const kind=node.dataset.toggle==='reading'?'readings':'exercises'; return mutate(()=>api(`/api/days/${state.day.id}/${kind}/${encodeURIComponent(node.dataset.id)}/toggle`,'POST'),'打卡已更新'); }
  if(node.id==='plan-file') {state.importData=null;document.querySelector('[data-action="apply-plan"]').disabled=true;if(!node.files?.[0])return;try{const data=JSON.parse(await node.files[0].text());const p=await api('/api/plans/import/preview','POST',data);state.importData=data;document.getElementById('plan-result').textContent=`${p.plan_name} · ${p.weeks} 周 / ${p.days} 天 / ${p.minutes/60} 小时。新增 ${p.added.length} 天，变更 ${p.changed.length} 天，未变 ${p.unchanged} 天，移除 ${p.removed.length} 天。导入后将切换到此计划。`;document.querySelector('[data-action="apply-plan"]').disabled=false;}catch(e){document.getElementById('plan-result').textContent=e.message;flash(e.message,true)}return;}
  if(node.id==='restore-file') { try { state.restoreData=JSON.parse(await node.files[0].text()); const p=await api('/api/restore/preview','POST',state.restoreData);const changes=Object.entries(p.tables).filter(([,v])=>v.backup||v.current).map(([k,v])=>`${k}: ${v.current} → ${v.backup}`).join('；');document.getElementById('restore-result').textContent=changes;document.querySelector('[data-action="apply-restore"]').disabled=false; } catch(e){state.restoreData=null;flash(e.message,true)} }
});
document.addEventListener('submit', async event => {
  const form=event.target; if(!form.id && !form.classList.contains('acceptance-form')) return; event.preventDefault();
  const d=state.day, v=formValues(form);
  if(form.id==='setup-form') return mutate(()=>api('/api/settings','PATCH',{start_date:document.getElementById('setup-start').value,timezone:document.getElementById('setup-zone').value}),'起始日期已保存');
  if(form.id==='settings-form') return mutate(()=>api('/api/settings','PATCH',v),'设置已保存');
  if(form.id==='progress-form') return mutate(()=>api(`/api/days/${d.id}/progress`,'PATCH',v),'任务状态已保存');
  if(form.id==='budget-form') return mutate(()=>api(`/api/days/${d.id}/budget`,'PATCH',Object.fromEntries(Object.entries(v).map(([k,x])=>[k,Number(x)]))),'预算已保存');
  if(form.id==='evidence-form') return mutate(()=>api(`/api/days/${d.id}/evidence`,'POST',{...v,criterion_id:v.criterion_id||null}),'证据已保存');
  if(form.id==='manual-form') return mutate(()=>api('/api/sessions/manual','POST',{day_id:d.id,minutes:Number(v.minutes),note:v.note}),'学习时间已补录');
  if(form.id==='reflection-form') return mutate(()=>api(`/api/days/${d.id}/reflection`,'PUT',v),'复盘已保存');
  if(form.classList.contains('acceptance-form')) return mutate(()=>api(`/api/days/${d.id}/acceptance/${form.dataset.criterion}/review`,'POST',{status:v.status,evidence_id:v.evidence_id?Number(v.evidence_id):null,note:v.note}),'验收已保存');
});
function updateTimer() {
  const display=document.getElementById('timer'), label=document.getElementById('timer-state');
  if(!display) return;
  if(!state.active || state.active.day_id!==state.day?.id) {display.textContent='00:00:00';label.textContent=state.active?'其他课程日正在计时':'未开始';return;}
  const seconds=Math.max(0,Math.floor((Date.now()-new Date(state.active.started_at).getTime())/1000));
  const h=String(Math.floor(seconds/3600)).padStart(2,'0'),m=String(Math.floor(seconds%3600/60)).padStart(2,'0'),s=String(seconds%60).padStart(2,'0');
  display.textContent=`${h}:${m}:${s}`;label.textContent='正在计时 · 关闭页面后仍会持续记录';
}
setInterval(updateTimer,1000);
refresh().catch(e => {app.innerHTML=`<div class="card empty">启动失败：${esc(e.message)}</div>`;});
