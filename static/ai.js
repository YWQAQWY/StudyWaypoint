const aiSavedPrefs=(()=>{try{return {...JSON.parse(localStorage.getItem('studywaypoint.ui.v1')||'{}'),...(window.__initialUiPrefs||{})}}catch(_){return typeof window==='undefined'?{}:window.__initialUiPrefs||{}}})();
const aiState = {data:null, draft:null, planDraft:null, preview:null, busy:false, partialText:'', polling:null, activityPolling:null,
  sidebarOpen:aiSavedPrefs.aiSidebarOpen===undefined ?
    (typeof window==='undefined'||window.innerWidth>1140) : aiSavedPrefs.aiSidebarOpen!==false,
  splitWidth:Math.min(620,Math.max(320,Number(aiSavedPrefs.aiSplitWidth)||450)),
  chatInput:'',chatScrollTop:0,draftScrollTop:0,
  closedStages:new Set(aiSavedPrefs.closedStages||[]),allowUpdateExisting:false,
  form:{plan_name:'', plan_id:'', weeks:'8', daily_hours:'4,4,4,4,4,4,4'}};

const planStatusLabel={IDLE:'未开始',COLLECTING_REQUIREMENTS:'收集需求',DRAFTING:'正在更新草稿',
  REFINING:'等待反馈',READY_FOR_CONFIRMATION:'可确认',GENERATING_JSON:'正在生成 JSON',
  VALIDATING:'正在校验',IMPORTING:'正在导入',COMPLETED:'已导入',ERROR:'需处理错误',CANCELLED:'已取消'};
const planMoveAnimations=new WeakMap();

function animatePlanMove(node,delta,duration) {
  planMoveAnimations.get(node)?.cancel();
  if(Math.abs(delta)<=2||!node.animate) return;
  const animation=node.animate([{transform:`translateY(${delta}px)`},{transform:'translateY(0)'}],
    {duration,easing:'cubic-bezier(.2,.72,.2,1)'});
  planMoveAnimations.set(node,animation);
  animation.onfinish=()=>{if(planMoveAnimations.get(node)===animation) planMoveAnimations.delete(node);};
}

function aiStageMarkup(stage,index,changed) {
  const taskCount=stage.tasks?.length||0;
  const status=changed.has(stage.id)?'<span class="pill teal">已调整</span>':'';
  return `<details data-plan-stage="${esc(stage.id)}" ${aiState.closedStages.has(stage.id)?'':'open'} class="plan-stage ${changed.has(stage.id)?'changed':''}"><summary><b>${index+1}. ${esc(stage.title||'待确认')}</b><small>${taskCount} 项任务 · ${stage.estimated_hours?`约 ${esc(stage.estimated_hours)} 小时`:'时间待确认'}</small>${status}</summary>
    <div class="plan-stage-content"><div class="plan-stage-summary">${stage.summary?`<p class="muted">${esc(stage.summary)}</p>`:''}</div>
    <div class="plan-task-list">${(stage.tasks||[]).map(task=>`<div class="plan-task ${changed.has(task.id)?'changed':''}" data-plan-task="${esc(task.id)}"><b>${esc(task.title||'待确认')}</b><small>${task.estimated_minutes?`约 ${esc(task.estimated_minutes)} 分钟`:'时间待确认'}${changed.has(task.id)?' · 已调整':''}</small>${task.description?`<p>${esc(task.description)}</p>`:''}${task.resources?.length?`<small>关联资源 ${task.resources.length} 项</small>`:''}</div>`).join('')||'<p class="muted">任务待确认</p>'}</div></div></details>`;
}

function aiDraftPanel() {
  const draft=aiState.planDraft;
  if(!draft||draft.status==='IDLE') return `<section class="card plan-draft-sidebar"><div class="plan-panel-head"><h2>实时计划预览</h2></div><div class="plan-draft-scroll"><p class="muted">发送学习目标后，这里会显示可持续修改的结构化草稿。</p></div></section>`;
  const changed=new Set(draft.last_changed_ids||[]);
  const active=['GENERATING_JSON','VALIDATING','IMPORTING'].includes(draft.status);
  const stages=(draft.stages||[]).map((stage,index)=>aiStageMarkup(stage,index,changed)).join('');
  const issues=(draft.unresolved_questions||[]).map(q=>`<li>${esc(q.text)}${q.blocking?' · 需确认':''}</li>`).join('');
  const resources=(draft.resources||[]).slice(-8).map(r=>`<li><a href="${esc(r.url)}" target="_blank" rel="noopener noreferrer">${esc(r.title||r.url)}</a><small>${esc(r.verification_status||'unknown')} · ${esc(r.provider||'unknown')}</small></li>`).join('');
  const effectiveId=draft.plan_id||`plan-${draft.draft_id.slice(0,12)}`;
  const existingPlan=(state.bootstrap?.plans||[]).some(plan=>plan.plan_id===effectiveId);
  const blockers=[];
  if(!draft.learning_goal) blockers.push('学习目标待确认');
  if(!draft.title) blockers.push('计划名称待确认');
  if(!draft.weeks) blockers.push('学习周期待确认');
  if(!draft.daily_hours) blockers.push('学习时间待确认');
  if(!draft.stages?.length||draft.stages.some(stage=>!stage.tasks?.length)) blockers.push('学习阶段或任务尚不完整');
  if((draft.unresolved_questions||[]).some(q=>q.blocking)) blockers.push('仍有关键问题待确认');
  if(existingPlan&&!aiState.allowUpdateExisting) blockers.push('现有计划 ID 需要明确授权更新');
  if(aiState.busy||active) blockers.push('正在更新计划');
  const canConfirm=!blockers.length&&draft.status!=='COMPLETED';
  const progressLabel={GENERATING_JSON:'正在生成学习计划…',VALIDATING:'正在校验计划…',IMPORTING:'正在导入学习计划…'}[draft.status];
  return `<section class="card plan-draft-sidebar" data-draft-id="${esc(draft.draft_id)}" aria-live="polite">
    <div class="plan-panel-head" data-draft-part="head"><div class="section-title"><h2>实时计划预览</h2><span class="pill ${draft.status==='COMPLETED'?'teal':draft.status==='ERROR'?'red':'gold'}">${esc(planStatusLabel[draft.status]||draft.status)}</span></div><p class="muted">修订 ${esc(draft.revision)} · ${esc(draft.updated_at||'')}</p></div>
    <div class="plan-draft-scroll"><div data-draft-part="summary"><h3>${esc(draft.title||'名称待确认')}</h3><p>${esc(draft.learning_goal||'学习目标待确认')}</p><p class="muted">计划 ID：${esc(effectiveId)}</p>
    <div class="plan-facts"><span>${draft.weeks?`${esc(draft.weeks)} 周`:'周期待确认'}</span><span>${draft.weekly_hours?`每周 ${esc(draft.weekly_hours)} 小时`:'时间待确认'}</span></div>
    ${draft.daily_hours?`<p class="muted">每日时长：${draft.daily_hours.map(esc).join('、')} 小时</p>`:''}
    ${draft.language||draft.platform?`<p class="muted">资源偏好：${esc([draft.language,draft.platform].filter(Boolean).join(' · '))}</p>`:''}</div>
    <h3>学习阶段</h3><div class="plan-stage-list">${stages||'<p class="muted">模型正在整理阶段；可继续提供信息。</p>'}</div>
    <div data-draft-part="resources">${resources?`<h3>已发现资源</h3><ul class="plan-resource-list">${resources}</ul>`:''}</div>
    <div data-draft-part="issues">${issues?`<div class="soft warning"><b>待确认事项</b><ul class="small-list">${issues}</ul></div>`:''}
    ${draft.validation_warnings?.length?`<p class="muted">建议：${esc(draft.validation_warnings.join('；'))}</p>`:''}
    ${draft.error?`<p class="error-text" role="alert">${esc(draft.error)}</p>`:''}</div></div>
    <div class="plan-confirm-bar" data-draft-part="confirm">
      ${existingPlan&&draft.status!=='COMPLETED'?`<label class="ai-checkbox"><input id="ai-update-existing" type="checkbox" ${aiState.allowUpdateExisting?'checked':''}>此 ID 已存在，我确认更新该计划并保留其进度</label>`:''}
      ${draft.status==='COMPLETED'?`<p class="plan-success">✓ 学习计划已成功导入：${esc(draft.import_result?.active_plan_id||'')}</p><button class="button primary" data-action="ai-open-imported">查看学习计划</button>`:
        `<div class="form-row"><button class="button primary" data-action="ai-confirm-import" ${canConfirm?'':'disabled'}>${progressLabel?`<span class="import-spinner" aria-hidden="true"></span>${progressLabel}`:draft.confirmation_id&&draft.status==='ERROR'?'重试确认并导入':'确认计划并导入'}</button>${active?'<button class="button" data-action="ai-cancel">取消</button>':''}</div>`}
      ${blockers.length&&!active&&draft.status!=='COMPLETED'?`<p class="muted">${esc(blockers.join('；'))}</p>`:''}
      <p class="muted">确认将冻结当前修订，通过既有 v3 校验后自动导入。</p>
    </div></section>`;
}

function saveAiLayout() {
  if(typeof uiPrefs==='undefined') return;
  uiPrefs.aiSidebarOpen=aiState.sidebarOpen;
  uiPrefs.aiSplitWidth=aiState.splitWidth;
  uiPrefs.closedStages=[...aiState.closedStages];
  saveUiPrefs();
}

function syncTaskList(current,desired,reduce) {
  if(!current||!desired||current.innerHTML===desired.innerHTML) return;
  const old=[...current.querySelectorAll(':scope > [data-plan-task]')];
  const positions=new Map(old.map(node=>[node.dataset.planTask,node.getBoundingClientRect()]));
  const wanted=[...desired.querySelectorAll(':scope > [data-plan-task]')];
  const ids=new Set(wanted.map(node=>node.dataset.planTask));
  for(const node of old) if(!ids.has(node.dataset.planTask)) {
    planMoveAnimations.get(node)?.cancel();node.remove();
  }
  if(!wanted.length) {current.innerHTML=desired.innerHTML;return;}
  current.querySelector(':scope > p')?.remove();
  for(let index=0;index<wanted.length;index++) {
    const target=wanted[index],id=target.dataset.planTask;
    let node=[...current.children].find(item=>item.dataset.planTask===id);
    if(!node) {
      node=target.cloneNode(true);
      if(!reduce) node.classList.add('entering');
    } else {
      if(node.innerHTML!==target.innerHTML) node.innerHTML=target.innerHTML;
      node.className=target.className;
    }
    if(current.children[index]!==node) current.insertBefore(node,current.children[index]||null);
  }
  if(!reduce) for(const node of current.querySelectorAll(':scope > [data-plan-task]')) {
    const before=positions.get(node.dataset.planTask);
    if(!before) continue;
    const delta=before.top-node.getBoundingClientRect().top;
    animatePlanMove(node,delta,260);
  }
}

function syncStageList(current,desired) {
  if(!current||!desired||current.innerHTML===desired.innerHTML) return;
  const reduce=window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
  const existing=[...current.querySelectorAll(':scope > [data-plan-stage]')];
  const oldRects=new Map(existing.map(node=>[node.dataset.planStage,node.getBoundingClientRect()]));
  const wanted=[...desired.querySelectorAll(':scope > [data-plan-stage]')];
  const wantedIds=new Set(wanted.map(node=>node.dataset.planStage));
  for(const node of existing) if(!wantedIds.has(node.dataset.planStage)) {
    planMoveAnimations.get(node)?.cancel();node.remove();
  }
  if(!wanted.length) {current.innerHTML=desired.innerHTML;return;}
  current.querySelector(':scope > p')?.remove();
  for(let index=0;index<wanted.length;index++) {
    const target=wanted[index],id=target.dataset.planStage;
    let node=[...current.children].find(item=>item.dataset.planStage===id);
    if(!node) {
      node=target.cloneNode(true);
      if(!reduce) node.classList.add('entering');
    } else {
      const header=node.querySelector('summary'),wantedHeader=target.querySelector('summary');
      if(header.innerHTML!==wantedHeader.innerHTML) header.innerHTML=wantedHeader.innerHTML;
      const summary=node.querySelector('.plan-stage-summary'),wantedSummary=target.querySelector('.plan-stage-summary');
      if(summary.innerHTML!==wantedSummary.innerHTML) summary.innerHTML=wantedSummary.innerHTML;
      syncTaskList(node.querySelector('.plan-task-list'),target.querySelector('.plan-task-list'),reduce);
      node.className=target.className;
      node.open=!aiState.closedStages.has(id);
    }
    const at=current.children[index];
    if(at!==node) current.insertBefore(node,at||null);
  }
  if(!reduce) for(const node of current.querySelectorAll(':scope > [data-plan-stage]')) {
    const before=oldRects.get(node.dataset.planStage);
    if(!before) continue;
    const delta=before.top-node.getBoundingClientRect().top;
    animatePlanMove(node,delta,300);
  }
}

function syncDraftPanel(current,desired) {
  if(!current||!desired||current.dataset.draftId!==desired.dataset.draftId) {
    current?.replaceWith(desired.cloneNode(true));return;
  }
  const scroll=current.querySelector('.plan-draft-scroll'),position=scroll.scrollTop;
  for(const name of ['head','summary','resources','issues','confirm']) {
    const before=current.querySelector(`[data-draft-part="${name}"]`);
    const after=desired.querySelector(`[data-draft-part="${name}"]`);
    if(before&&after&&before.innerHTML!==after.innerHTML) before.innerHTML=after.innerHTML;
  }
  syncStageList(current.querySelector('.plan-stage-list'),desired.querySelector('.plan-stage-list'));
  scroll.scrollTop=position;
}

function aiRememberScroll() {
  aiState.chatScrollTop=document.querySelector('.ai-messages')?.scrollTop||0;
  aiState.draftScrollTop=document.querySelector('.plan-draft-scroll')?.scrollTop||0;
}

function aiRestoreScroll() {
  const chat=document.querySelector('.ai-messages'),draft=document.querySelector('.plan-draft-scroll');
  if(chat) chat.scrollTop=aiState.chatScrollTop;
  if(draft) draft.scrollTop=aiState.draftScrollTop;
}

function aiRender() {
  if(state.view==='settings') {render();return;}
  if(state.view!=='ai') return;
  const layout=document.querySelector('.ai-layout');
  if(!layout) {render();return;}
  const template=document.createElement('template');
  template.innerHTML=aiView();
  const desired=template.content.querySelector('.ai-layout');
  if(!desired) {render();return;}
  layout.classList.toggle('sidebar-closed',!aiState.sidebarOpen);
  layout.style.setProperty('--plan-width',`${aiState.splitWidth}px`);
  const toggle=document.querySelector('.ai-sidebar-toggle');
  if(toggle) {toggle.textContent=aiState.sidebarOpen?'收起计划侧栏':'显示计划侧栏';toggle.setAttribute('aria-expanded',String(aiState.sidebarOpen));}
  const messages=layout.querySelector('.ai-messages'),wantedMessages=desired.querySelector('.ai-messages');
  if(messages&&wantedMessages&&messages.innerHTML!==wantedMessages.innerHTML) {
    const nearBottom=messages.scrollHeight-messages.scrollTop-messages.clientHeight<70;
    messages.innerHTML=wantedMessages.innerHTML;
    if(nearBottom) messages.scrollTop=messages.scrollHeight;
  }
  const form=layout.querySelector('#ai-chat-form'),wantedForm=desired.querySelector('#ai-chat-form');
  if(form&&wantedForm) for(const button of form.querySelectorAll('button')) {
    const match=wantedForm.querySelector(button.type==='submit'?'button[type="submit"]':`button[data-action="${button.dataset.action}"]`);
    if(match) button.disabled=match.disabled;
  }
  const clear=layout.querySelector('[data-action="ai-clear"]');
  if(clear) clear.disabled=aiState.busy;
  const meta=layout.querySelector('.ai-search-meta'),wantedMeta=desired.querySelector('.ai-search-meta');
  if(meta&&wantedMeta&&meta.innerHTML!==wantedMeta.innerHTML) meta.innerHTML=wantedMeta.innerHTML;
  const legacy=layout.querySelector('.ai-legacy'),wantedLegacy=desired.querySelector('.ai-legacy');
  if(legacy&&wantedLegacy&&legacy.innerHTML!==wantedLegacy.innerHTML) legacy.innerHTML=wantedLegacy.innerHTML;
  syncDraftPanel(layout.querySelector('.plan-draft-sidebar'),desired.querySelector('.plan-draft-sidebar'));
}

function aiConfigPanel() {
  const config=aiState.data?.config;
  if(!config) return `<section class="card empty">AI 配置加载中…</section>`;
  const enabled=config.enabled, disabled=aiState.busy?'disabled':'';
  return `<section class="card"><div class="section-title"><h2>API 配置</h2><span class="pill ${enabled?'teal':'gold'}">${enabled?'对话已启用':'等待配置'}</span></div>
    <p class="muted">使用 OpenAI 兼容的 Chat Completions 格式。基础地址可配置，默认示例为 DeepSeek；应用会向基础地址追加 <code>/chat/completions</code>。密钥只保存在本机数据目录。</p>
    <form id="ai-config-form"><div class="field"><label>API 基础地址（HTTPS）</label><input name="base_url" type="url" value="${esc(config.base_url)}" required placeholder="https://api.deepseek.com"></div><div class="two-col"><div class="field"><label>模型 API Key ${enabled?'（已配置，留空则保留）':''}</label><input name="api_key" type="password" autocomplete="off" placeholder="sk-…"></div><div class="field"><label>模型名称</label><input name="model" value="${esc(config.model)}" required placeholder="deepseek-v4-pro"></div></div><div class="field"><label>推理强度（服务商不支持时选“服务商默认”）</label><select name="reasoning_effort">${[['high','高'],['max','最高'],['low','低'],['default','服务商默认']].map(([value,label])=>`<option value="${value}" ${config.reasoning_effort===value?'selected':''}>${label}</option>`).join('')}</select></div>
    <div class="soft"><b>默认搜索 · SearXNG</b><p class="muted">不启用第三方搜索时，所有新搜索只访问下方配置的 SearXNG 实例。${config.searxng_tested_at?`上次连接通过：${esc(config.searxng_tested_at)}`:config.searxng_url?'已填写地址，尚未通过连接测试。':'尚未配置实例地址。'}</p></div>
    <div class="field"><label>SearXNG 实例地址</label><input name="searxng_url" type="url" value="${esc(config.searxng_url||'')}" placeholder="http://127.0.0.1:8888"></div>
    <p class="muted">填写站点根地址并启用 JSON 搜索接口；本机可使用 HTTP，远程实例须用 HTTPS。应用不会自动安装 SearXNG。<a href="https://docs.searxng.org/admin/installation-docker" target="_blank" rel="noopener noreferrer">SearXNG 安装说明</a></p>
    <label class="ai-checkbox"><input id="ai-third-party-toggle" name="third_party_enabled" type="checkbox" ${config.third_party_enabled?'checked':''}>启用第三方搜索（优先使用 Brave，失败回退 SearXNG）</label>
    <div id="ai-brave-settings" ${config.third_party_enabled?'':'hidden'}><div class="field"><label>第三方服务</label><select name="third_party_provider"><option value="brave">Brave Search API</option></select></div>
    <div class="field"><label>Brave Search API Key ${config.brave_key_configured?'（已填写，留空则保留）':''}</label><input name="search_api_key" type="password" autocomplete="off" placeholder="启用第三方搜索时填写"></div>
    <p class="muted">${config.brave_tested_at?`Brave 上次连接通过：${esc(config.brave_tested_at)}`:config.brave_key_configured?'Brave Key 已填写，尚未通过连接测试。':'Brave Key 未填写；启用后仍会使用 SearXNG。'}</p></div>
    <div class="form-row"><label class="ai-checkbox"><input name="clear_api_key" type="checkbox">删除模型 API Key</label><label class="ai-checkbox"><input name="clear_search_api_key" type="checkbox">删除 Brave Key</label><label class="ai-checkbox"><input name="clear_searxng_url" type="checkbox">删除 SearXNG 地址</label></div>
    <div class="form-row"><button class="button primary" type="submit" ${disabled}>保存配置</button><button class="button" type="button" data-action="ai-test-searxng" ${disabled||!config.searxng_url?'disabled':''}>测试 SearXNG</button><button class="button" type="button" data-action="ai-test-brave" ${disabled||!config.third_party_enabled||!config.brave_key_configured?'disabled':''}>测试 Brave</button></div></form>
    <p class="muted">密钥保存在 <code>${esc(config.key_storage)}</code>，文件权限为仅当前用户可读写。调用 API 可能产生服务商费用；对话内容会发送给模型服务商，检索词会发送给所选检索来源。</p></section>`;
}

function aiView() {
  const data=aiState.data;
  if(!data) return `<div class="card empty">正在读取 AI 规划配置…</div>`;
  const config=data.config, enabled=config.enabled;
  const messages=data.history.messages||[], sources=data.history.sources||[];
  const job=data.job;
  const disabled=aiState.busy?'disabled':'';
  const configPanel=aiConfigPanel();
  if(!enabled) return `${hero('AI 规划','先配置模型 API','保存 OpenAI 兼容 API 的地址、模型名称与 Key 后，即可讨论学习目标并生成计划。')}${configPanel}`;
  const conversation=`<section class="card ai-conversation"><div class="section-title"><h2>讨论学习目标</h2><button class="mini" data-action="ai-clear" ${disabled}>清空对话与草稿</button></div>
    <p class="muted">建议先说明现有基础、学习目标、每周可投入时间、偏好的资料与最终验收标准；可继续追问和修改方案。</p>
    <div class="ai-messages" aria-live="polite">${messages.length?messages.map(m=>`<div class="ai-message ${m.role==='user'?'user':'assistant'}"><b>${m.role==='user'?'你':m.research?'AI · 检索分析':'AI'}</b><div>${esc(m.content)}</div></div>`).join(''):'<div class="empty">先描述你想学什么，以及希望在多久内达到什么程度。</div>'}${aiState.partialText?`<div class="ai-message assistant streaming"><b>AI · 正在回复</b><div>${esc(aiState.partialText)}</div></div>`:''}</div>
    <div class="ai-search-meta">${!config.search_enabled?'<p class="muted">联网检索尚未配置；普通 AI 对话仍可使用。请在设置中配置 SearXNG 或 Brave。</p>':''}
    ${data.activity?`<p class="ai-job" role="status">${esc(data.activity)}</p>`:''}${data.history.last_search_status?`<p class="muted">最近检索：${esc(data.history.last_search_status)}</p>`:''}
    ${sources.length?`<details class="ai-sources"><summary>本轮检索来源（${sources.length}）</summary><ol>${sources.map(s=>`<li><a href="${esc(s.url)}" target="_blank" rel="noopener noreferrer">${esc(s.title||s.url)}</a><small>${esc(s.description)}</small></li>`).join('')}</ol></details>`:''}</div>
    <form id="ai-chat-form"><div class="field"><label>发送消息 · Ctrl/⌘ + Enter</label><textarea name="message" rows="3" maxlength="12000" required placeholder="例如：我会 Python 基础，想用 8 周学习 LLM 应用开发，每天约 4 小时…">${esc(aiState.chatInput)}</textarea></div><div class="form-row"><button class="button primary" type="submit" ${disabled}>发送给模型</button><button class="button dark" type="button" data-action="ai-research" ${disabled||!config.search_enabled?'disabled':''}>联网检索系统课程</button><button class="button" type="button" data-action="ai-cancel" ${aiState.busy?'':'disabled'}>取消当前请求</button></div></form></section>`;
  const f=aiState.form;
  const autoJob=job?.id&&job.id===aiState.planDraft?.confirmation_id;
  const generating=job?.status==='running';
  const jobText=autoJob?'':generating?`正在生成第 ${job.current_week+1} / ${job.weeks} 周，计划会在后台逐周完成。`
    :job?.status==='failed'||job?.status==='cancelled'?`生成${job.status==='cancelled'?'已取消':'失败'}：${esc(job.error)}`
    :job?.status==='complete'?'计划草稿已完成，请核对后导入。':'';
  const draft=autoJob?null:data.draft;
  const preview=aiState.preview;
  const draftPanel=draft?`<div class="soft ai-draft"><h3>待确认的 v3 计划：${esc(draft.plan_name)}</h3>
    <p>${esc(draft.plan_id)} · ${draft.weeks} 周 / ${draft.days} 天 / ${draft.hours} 小时</p>
    <p>${preview?`相对现有计划：新增 ${preview.added.length} 天，变更 ${preview.changed.length} 天，未变 ${preview.unchanged} 天，移除 ${preview.removed.length} 天。`:'正在预览导入差异…'}</p>
    <p class="muted">请先下载并检查每日任务、资料网址、时间分配和验收标准。AI 生成的链接可能失效或不准确。</p>
    <div class="form-row"><button class="button" data-action="ai-download" ${aiState.draft?'':'disabled'}>下载 JSON 检查</button><button class="button primary" data-action="ai-apply" ${preview&&!generating&&!aiState.busy?'':'disabled'}>确认导入并启用</button></div></div>`:'';
  const generate=`<details class="card ai-legacy" ${generating||draft?'open':''}><summary>旧版手动生成草稿（可选）</summary><p class="muted">交互式规划请使用侧栏的“确认计划并导入”。这里保留原有手动生成方式：填好最终参数后生成草稿，再预览并导入。</p>
    <form id="ai-generate-form"><div class="two-col"><div class="field"><label>计划名称</label><input name="plan_name" value="${esc(f.plan_name)}" maxlength="120" required placeholder="例如：8 周 LLM 应用开发"></div><div class="field"><label>计划 ID（稳定英文标识）</label><input name="plan_id" value="${esc(f.plan_id)}" pattern="[A-Za-z0-9][A-Za-z0-9._-]{2,79}" required placeholder="llm-app-8-weeks"></div></div>
    <div class="two-col"><div class="field"><label>周数（1–52）</label><input name="weeks" type="number" min="1" max="52" value="${esc(f.weeks)}" required></div><div class="field"><label>一周七天的小时数（逗号分隔）</label><input name="daily_hours" value="${esc(f.daily_hours)}" required placeholder="4,4,4,4,4,4,4"></div></div>
    <label class="ai-checkbox"><input name="confirmed" type="checkbox" required>我已确认学习目标、时间和课程范围，并会在导入前核对资源链接</label>
    <div class="form-row"><button class="button dark" type="submit" ${disabled||generating?'disabled':''}>生成 v3 JSON 草稿</button><button class="button" type="button" data-action="ai-cancel" ${generating?'':'disabled'}>取消生成</button></div></form>
    ${jobText?`<p class="ai-job ${job?.status==='failed'?'error-text':''}" role="status">${jobText}</p>`:''}${draftPanel}</details>`;
  return `${hero('AI 规划','从目标讨论到可导入课程','对话中的草稿会实时显示在侧栏；确认后自动校验并导入。')}
    <button class="mini ai-sidebar-toggle" data-action="ai-toggle-sidebar" aria-expanded="${aiState.sidebarOpen}">${aiState.sidebarOpen?'收起':'显示'}计划侧栏</button>
    <div class="ai-layout ${aiState.sidebarOpen?'':'sidebar-closed'}" style="--plan-width:${aiState.splitWidth}px"><div class="ai-main">${conversation}${generate}</div><div class="ai-resizer" role="separator" aria-label="调整对话区和计划预览宽度" aria-orientation="vertical" aria-valuenow="${aiState.splitWidth}" tabindex="0"></div><aside class="ai-side">${aiDraftPanel()}</aside></div>`;
}

async function aiRefresh() {
  const [data,planDraft]=await Promise.all([api('/api/ai/state'),api('/api/ai/plan-draft')]);
  aiState.data=data;
  const justImported=planDraft.status==='COMPLETED'&&aiState.planDraft?.status!=='COMPLETED';
  if(planDraft.revision>0&&aiState.planDraft?.status==='IDLE') {
    aiState.sidebarOpen=true;
    saveAiLayout();
  }
  aiState.planDraft=planDraft;
  if(justImported) await refresh();
  if(data.draft?.id!==aiState.draft?.id) {
    aiState.draft=data.draft ? await api('/api/ai/draft') : null;
    aiState.preview=aiState.draft ? await api('/api/plans/import/preview','POST',aiState.draft.plan) : null;
  }
  if(state.view==='ai') aiRender();
  else if(state.view==='settings') render();
  if(aiState.polling) clearTimeout(aiState.polling);
  if(data.job?.status==='running') aiState.polling=setTimeout(()=>aiRefresh().catch(e=>flash(e.message,true)),2500);
}

async function aiRun(task, success) {
  if(aiState.busy) return;
  aiState.busy=true; aiState.partialText=''; if(state.view==='ai') aiRender();
  aiState.activityPolling=setInterval(async()=>{
    try { const latest=await api('/api/ai/activity');
      const draft=await api('/api/ai/plan-draft');
      let changed=aiState.planDraft?.revision!==draft.revision||aiState.planDraft?.status!==draft.status;
      aiState.planDraft=draft;
      if(aiState.data && latest.status!==aiState.data.activity) {aiState.data.activity=latest.status;changed=true;}
      if((latest.partial_text||'')!==aiState.partialText) {aiState.partialText=latest.partial_text||'';changed=true;}
      if(changed&&state.view==='ai') aiRender();
    } catch (_) { /* The active request reports its own error. */ }
  },1000);
  try { await task(); await aiRefresh(); if(success) flash(success); }
  catch(e) { flash(e.message,true); }
  finally { clearInterval(aiState.activityPolling);aiState.activityPolling=null;aiState.busy=false;aiState.partialText='';if(state.view==='ai'||state.view==='settings') aiRender(); }
}

document.addEventListener('toggle',event=>{
  const id=event.target?.dataset?.planStage;
  if(!id) return;
  if(event.target.open) aiState.closedStages.delete(id);
  else aiState.closedStages.add(id);
  saveAiLayout();
},true);

document.addEventListener('click',event=>{
  const summary=event.target.closest?.('.plan-stage summary');
  if(!summary) return;
  event.preventDefault();
  const stage=summary.parentElement;
  stage.open=!stage.open;
  if(stage.open) aiState.closedStages.delete(stage.dataset.planStage);
  else aiState.closedStages.add(stage.dataset.planStage);
  saveAiLayout();
});

document.addEventListener('input',event=>{
  if(event.target?.matches?.('#ai-chat-form textarea')) aiState.chatInput=event.target.value;
});

document.addEventListener('pointerdown',event=>{
  const handle=event.target.closest?.('.ai-resizer');
  if(!handle||window.innerWidth<=980||!aiState.sidebarOpen) return;
  const layout=handle.closest('.ai-layout');
  if(!layout) return;
  event.preventDefault();
  layout.classList.add('resizing');
  handle.setPointerCapture?.(event.pointerId);
  const move=e=>{
    const bounds=layout.getBoundingClientRect();
    aiState.splitWidth=Math.round(Math.min(620,Math.max(320,bounds.right-e.clientX)));
    aiState.splitWidth=Math.min(aiState.splitWidth,Math.max(320,bounds.width-348));
    layout.style.setProperty('--plan-width',`${aiState.splitWidth}px`);
    handle.setAttribute('aria-valuenow',String(aiState.splitWidth));
  };
  const stop=()=>{layout.classList.remove('resizing');window.removeEventListener('pointermove',move);window.removeEventListener('pointerup',stop);window.removeEventListener('pointercancel',stop);saveAiLayout();};
  window.addEventListener('pointermove',move);
  window.addEventListener('pointerup',stop);
  window.addEventListener('pointercancel',stop);
});

document.addEventListener('keydown',event=>{
  if(!event.target?.matches?.('.ai-resizer')||!['ArrowLeft','ArrowRight'].includes(event.key)) return;
  event.preventDefault();
  const layout=event.target.closest('.ai-layout');
  const maximum=Math.min(620,Math.max(320,layout.getBoundingClientRect().width-348));
  aiState.splitWidth=Math.min(maximum,Math.max(320,aiState.splitWidth+(event.key==='ArrowLeft'?20:-20)));
  layout.style.setProperty('--plan-width',`${aiState.splitWidth}px`);
  event.target.setAttribute('aria-valuenow',String(aiState.splitWidth));
  saveAiLayout();
});

document.addEventListener('change', event=>{
  if(event.target?.id==='ai-update-existing') aiState.allowUpdateExisting=event.target.checked;
  if(event.target?.id==='ai-third-party-toggle') {
    const area=document.getElementById('ai-brave-settings');
    if(area) area.hidden=!event.target.checked;
  }
});

async function aiSubmit(form) {
  const values=Object.fromEntries(new FormData(form).entries());
  if(form.id==='ai-config-form') return aiRun(async()=>{
    await api('/api/ai/config','POST',{...values,third_party_enabled:!!form.querySelector('[name="third_party_enabled"]')?.checked,clear_api_key:!!values.clear_api_key,
      clear_search_api_key:!!values.clear_search_api_key,clear_searxng_url:!!values.clear_searxng_url});
  },'API 配置已保存');
  if(form.id==='ai-chat-form') {
    aiState.chatInput='';
    form.querySelector('textarea').value='';
    return aiRun(()=>api('/api/ai/chat','POST',{message:values.message}),'已收到回答');
  }
  if(form.id==='ai-generate-form') {
    aiState.form={plan_name:values.plan_name,plan_id:values.plan_id,weeks:values.weeks,daily_hours:values.daily_hours};
    const hours=values.daily_hours.split(/[,，]/).map(x=>Number(x.trim()));
    if(hours.length!==7 || hours.some(x=>!Number.isFinite(x))) return flash('请填写七个用逗号分隔的小时数',true);
    return aiRun(()=>api('/api/ai/generate','POST',{plan_name:values.plan_name,plan_id:values.plan_id,
      weeks:Number(values.weeks),daily_hours:hours,confirmed:!!values.confirmed}),'已开始后台生成');
  }
}

async function aiAction(action) {
  if(action==='ai-toggle-sidebar') {aiState.sidebarOpen=!aiState.sidebarOpen;saveAiLayout();aiRender();return;}
  if(action==='ai-confirm-import') {
    const draft=aiState.planDraft;
    if(!draft?.draft_id) return;
    const key=draft.confirmation_id||`confirm-${draft.draft_id}-${draft.revision}`;
    return aiRun(()=>api('/api/ai/plan-draft/confirm','POST',{draft_id:draft.draft_id,
      revision:draft.revision,confirmation_id:key,update_existing:aiState.allowUpdateExisting}),'已确认计划，正在生成并自动导入');
  }
  if(action==='ai-open-imported') {state.view='calendar';await refresh();return;}
  if(action==='ai-test-searxng') return aiRun(()=>api('/api/ai/search/test','POST',{provider:'searxng'}),'SearXNG 连接测试通过');
  if(action==='ai-test-brave') return aiRun(()=>api('/api/ai/search/test','POST',{provider:'brave'}),'Brave 连接测试通过');
  if(action==='ai-cancel') { await api('/api/ai/cancel','POST',{}); return flash('已请求取消当前 AI 操作'); }
  if(action==='ai-research') return aiRun(()=>api('/api/ai/research','POST',{}),'联网研究已完成');
  if(action==='ai-clear') {
    if(!window.confirm('清空本机的 AI 对话记录与待导入草稿？API 配置会保留。')) return;
    return aiRun(async()=>{await api('/api/ai/clear','POST',{});aiState.draft=null;aiState.planDraft=null;aiState.preview=null;},'对话已清空');
  }
  if(action==='ai-download' && aiState.draft) {
    downloadJson(aiState.draft.plan,`${aiState.draft.plan.plan_id}.json`);return;
  }
  if(action==='ai-apply' && aiState.draft && aiState.preview) return aiRun(async()=>{
    await api('/api/ai/draft/apply','POST',{id:aiState.draft.id});
    state.view='calendar';await refresh();
  },'计划已导入并启用');
}
