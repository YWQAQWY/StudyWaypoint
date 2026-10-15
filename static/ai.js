const aiState = {data:null, draft:null, preview:null, busy:false, polling:null,
  form:{plan_name:'', plan_id:'', weeks:'8', daily_hours:'4,4,4,4,4,4,4'}};

function aiView() {
  const data=aiState.data;
  if(!data) return `<div class="card empty">正在读取 AI 规划配置…</div>`;
  const config=data.config, enabled=config.enabled;
  const messages=data.history.messages||[], sources=data.history.sources||[];
  const job=data.job;
  const disabled=aiState.busy?'disabled':'';
  const configPanel=`<section class="card"><div class="section-title"><h2>API 配置</h2><span class="pill ${enabled?'teal':'gold'}">${enabled?'对话已启用':'等待配置'}</span></div>
    <p class="muted">使用 OpenAI 兼容的 Chat Completions 格式。基础地址可配置，默认示例为 DeepSeek；应用会向基础地址追加 <code>/chat/completions</code>。密钥只保存在本机数据目录。</p>
    <form id="ai-config-form"><div class="field"><label>API 基础地址（HTTPS）</label><input name="base_url" type="url" value="${esc(config.base_url)}" required placeholder="https://api.deepseek.com"></div><div class="two-col"><div class="field"><label>模型 API Key ${enabled?'（已配置，留空则保留）':''}</label><input name="api_key" type="password" autocomplete="off" placeholder="sk-…"></div><div class="field"><label>模型名称</label><input name="model" value="${esc(config.model)}" required placeholder="deepseek-v4-pro"></div></div><div class="field"><label>推理强度（服务商不支持时选“服务商默认”）</label><select name="reasoning_effort">${[['high','高'],['max','最高'],['low','低'],['default','服务商默认']].map(([value,label])=>`<option value="${value}" ${config.reasoning_effort===value?'selected':''}>${label}</option>`).join('')}</select></div>
    <div class="field"><label>联网检索来源</label><select name="search_provider"><option value="brave" ${config.search_provider==='brave'?'selected':''}>Brave Search（需要搜索 API Key）</option><option value="searxng" ${config.search_provider==='searxng'?'selected':''}>SearXNG（无需 Brave Key，需可用实例）</option></select></div>
    <div class="field"><label>Brave Search API Key ${config.brave_key_configured?'（已配置，留空则保留）':''}</label><input name="search_api_key" type="password" autocomplete="off" placeholder="选择 Brave 时填写"></div>
    <div class="field"><label>SearXNG 实例地址</label><input name="searxng_url" type="url" value="${esc(config.searxng_url||'')}" placeholder="http://127.0.0.1:8888"></div>
    <p class="muted">选择 SearXNG 时，填写站点根地址并启用 JSON 搜索接口，例如 <code>http://127.0.0.1:8888</code>；本机可使用 HTTP，远程实例必须使用 HTTPS。<a href="https://docs.searxng.org/admin/installation-docker" target="_blank" rel="noopener noreferrer">SearXNG 安装说明</a>。选择的来源会用于下次检索。</p>
    <div class="form-row"><label class="ai-checkbox"><input name="clear_api_key" type="checkbox">删除模型 API Key</label><label class="ai-checkbox"><input name="clear_search_api_key" type="checkbox">删除 Brave Key</label><label class="ai-checkbox"><input name="clear_searxng_url" type="checkbox">删除 SearXNG 地址</label></div>
    <button class="button primary" type="submit" ${disabled}>保存配置</button></form>
    <p class="muted">密钥保存在 <code>${esc(config.key_storage)}</code>，文件权限为仅当前用户可读写。调用 API 可能产生服务商费用；对话内容会发送给模型服务商，检索词会发送给所选检索来源。</p></section>`;
  if(!enabled) return `${hero('AI 规划','先配置模型 API','保存 OpenAI 兼容 API 的地址、模型名称与 Key 后，即可讨论学习目标并生成计划。')}${configPanel}`;
  const conversation=`<section class="card ai-conversation"><div class="section-title"><h2>讨论学习目标</h2><button class="mini" data-action="ai-clear" ${disabled}>清空对话与草稿</button></div>
    <p class="muted">建议先说明现有基础、学习目标、每周可投入时间、偏好的资料与最终验收标准；可继续追问和修改方案。</p>
    <div class="ai-messages" aria-live="polite">${messages.length?messages.map(m=>`<div class="ai-message ${m.role==='user'?'user':'assistant'}"><b>${m.role==='user'?'你':m.research?'AI · 检索分析':'AI'}</b><div>${esc(m.content)}</div></div>`).join(''):'<div class="empty">先描述你想学什么，以及希望在多久内达到什么程度。</div>'}</div>
    <form id="ai-chat-form"><div class="field"><label>发送消息</label><textarea name="message" rows="4" maxlength="12000" required placeholder="例如：我会 Python 基础，想用 8 周学习 LLM 应用开发，每天约 4 小时…"></textarea></div><div class="form-row"><button class="button primary" type="submit" ${disabled}>发送给模型</button><button class="button dark" type="button" data-action="ai-research" ${disabled||!config.search_enabled?'disabled':''}>联网检索并提出路线</button></div></form>
    ${!config.search_enabled?'<p class="muted">要启用联网检索，请在上方配置所选来源：Brave Key 或 SearXNG 实例地址。</p>':''}
    ${sources.length?`<details class="ai-sources"><summary>本轮检索来源（${sources.length}）</summary><ol>${sources.map(s=>`<li><a href="${esc(s.url)}" target="_blank" rel="noopener noreferrer">${esc(s.title||s.url)}</a><small>${esc(s.description)}</small></li>`).join('')}</ol></details>`:''}</section>`;
  const f=aiState.form;
  const generating=job?.status==='running';
  const jobText=generating?`正在生成第 ${job.current_week+1} / ${job.weeks} 周，计划会在后台逐周完成。`
    :job?.status==='failed'?`生成失败：${esc(job.error)}`
    :job?.status==='complete'?'计划草稿已完成，请核对后导入。':'';
  const draft=data.draft;
  const preview=aiState.preview;
  const draftPanel=draft?`<div class="soft ai-draft"><h3>待确认的 v3 计划：${esc(draft.plan_name)}</h3>
    <p>${esc(draft.plan_id)} · ${draft.weeks} 周 / ${draft.days} 天 / ${draft.hours} 小时</p>
    <p>${preview?`相对现有计划：新增 ${preview.added.length} 天，变更 ${preview.changed.length} 天，未变 ${preview.unchanged} 天，移除 ${preview.removed.length} 天。`:'正在预览导入差异…'}</p>
    <p class="muted">请先下载并检查每日任务、资料网址、时间分配和验收标准。AI 生成的链接可能失效或不准确。</p>
    <div class="form-row"><button class="button" data-action="ai-download" ${aiState.draft?'':'disabled'}>下载 JSON 检查</button><button class="button primary" data-action="ai-apply" ${preview&&!generating&&!aiState.busy?'':'disabled'}>确认导入并启用</button></div></div>`:'';
  const generate=`<section class="card"><h2>敲定并生成计划</h2><p class="muted">与 AI 讨论、必要时检索后，填写最终参数。每日小时数按每周第 1–7 天重复；生成的草稿会经过现有 v3 校验，并在你确认后才导入。</p>
    <form id="ai-generate-form"><div class="two-col"><div class="field"><label>计划名称</label><input name="plan_name" value="${esc(f.plan_name)}" maxlength="120" required placeholder="例如：8 周 LLM 应用开发"></div><div class="field"><label>计划 ID（稳定英文标识）</label><input name="plan_id" value="${esc(f.plan_id)}" pattern="[A-Za-z0-9][A-Za-z0-9._-]{2,79}" required placeholder="llm-app-8-weeks"></div></div>
    <div class="two-col"><div class="field"><label>周数（1–52）</label><input name="weeks" type="number" min="1" max="52" value="${esc(f.weeks)}" required></div><div class="field"><label>一周七天的小时数（逗号分隔）</label><input name="daily_hours" value="${esc(f.daily_hours)}" required placeholder="4,4,4,4,4,4,4"></div></div>
    <button class="button dark" type="submit" ${disabled||generating?'disabled':''}>生成 v3 JSON 草稿</button></form>
    ${jobText?`<p class="ai-job ${job?.status==='failed'?'error-text':''}" role="status">${jobText}</p>`:''}${draftPanel}</section>`;
  return `${hero('AI 规划','从目标讨论到可导入课程','兼容模型负责推理与对话；可选择 Brave Search 或 SearXNG 检索网页资料。')}
    <div class="ai-layout"><div class="ai-main">${conversation}${generate}</div><aside>${configPanel}</aside></div>`;
}

async function aiRefresh() {
  const data=await api('/api/ai/state');
  aiState.data=data;
  if(data.draft?.id!==aiState.draft?.id) {
    aiState.draft=data.draft ? await api('/api/ai/draft') : null;
    aiState.preview=aiState.draft ? await api('/api/plans/import/preview','POST',aiState.draft.plan) : null;
  }
  if(state.view==='ai') render();
  if(aiState.polling) clearTimeout(aiState.polling);
  if(data.job?.status==='running') aiState.polling=setTimeout(()=>aiRefresh().catch(e=>flash(e.message,true)),2500);
}

async function aiRun(task, success) {
  if(aiState.busy) return;
  aiState.busy=true; if(state.view==='ai') render();
  try { await task(); await aiRefresh(); if(success) flash(success); }
  catch(e) { flash(e.message,true); }
  finally { aiState.busy=false; if(state.view==='ai') render(); }
}

async function aiSubmit(form) {
  const values=Object.fromEntries(new FormData(form).entries());
  if(form.id==='ai-config-form') return aiRun(async()=>{
    await api('/api/ai/config','POST',{...values,clear_api_key:!!values.clear_api_key,
      clear_search_api_key:!!values.clear_search_api_key,clear_searxng_url:!!values.clear_searxng_url});
  },'API 配置已保存');
  if(form.id==='ai-chat-form') return aiRun(()=>api('/api/ai/chat','POST',{message:values.message}),'已收到回答');
  if(form.id==='ai-generate-form') {
    aiState.form={plan_name:values.plan_name,plan_id:values.plan_id,weeks:values.weeks,daily_hours:values.daily_hours};
    const hours=values.daily_hours.split(/[,，]/).map(x=>Number(x.trim()));
    if(hours.length!==7 || hours.some(x=>!Number.isFinite(x))) return flash('请填写七个用逗号分隔的小时数',true);
    return aiRun(()=>api('/api/ai/generate','POST',{plan_name:values.plan_name,plan_id:values.plan_id,
      weeks:Number(values.weeks),daily_hours:hours}),'已开始后台生成');
  }
}

async function aiAction(action) {
  if(action==='ai-research') return aiRun(()=>api('/api/ai/research','POST',{}),'联网研究已完成');
  if(action==='ai-clear') {
    if(!window.confirm('清空本机的 AI 对话记录与待导入草稿？API 配置会保留。')) return;
    return aiRun(async()=>{await api('/api/ai/clear','POST',{});aiState.draft=null;aiState.preview=null;},'对话已清空');
  }
  if(action==='ai-download' && aiState.draft) {
    downloadJson(aiState.draft.plan,`${aiState.draft.plan.plan_id}.json`);return;
  }
  if(action==='ai-apply' && aiState.draft && aiState.preview) return aiRun(async()=>{
    await api('/api/ai/draft/apply','POST',{id:aiState.draft.id});
    state.view='calendar';await refresh();
  },'计划已导入并启用');
}
