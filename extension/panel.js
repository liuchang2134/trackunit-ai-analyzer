/* Read the active Trackunit identity and, on its Events tab, visible fault cards. */
const PORTS = ['8890', '8892'];
const HANDSHAKE_TIMEOUT = 6500;
const FOLLOW_DELAY = 150;
const MINIMUM_BACKEND = [20260915, 9];
const get = id => document.getElementById(id);
const frame = get('assistant'), portSelector = get('service-port');
let preferredPort = '8890';
try { const saved = localStorage.getItem('jilian-service-port'); if (PORTS.includes(saved)) preferredPort = saved; } catch {}
let dataMode = 'live';
// Retire an older saved demo choice so reopening the extension follows Trackunit.
try { localStorage.removeItem('jilian-data-mode'); } catch {}
portSelector.value = preferredPort;
let deadline, contextDeadline, assetId = null, localOrigin, connectionId, sequence = 0;
let dataReady = false, runtime = null, state = 'connecting', mode = 'work', remaining = [], failures = [];
let pageChanged = false, pageGeneration = 0, currentTabId = null, currentWindowId = null;
let followEnabled = true, followTimer, lookupTicket = 0, lastContextLabel = '';
let matchedSelection = null, catalogRequest = null;
let activeResearchId = null;
let contextGeneration = 0, catalogGeneration = 0;
let showWorkOnReady = false;
let equipmentIdHint = null;
let resumeFollowAfterModeSwitch = false;
let faultPageTimer = null, faultPageRead = null, faultPageLastKey = '', faultPageLastAt = 0;

function supportsDeviceFollowing(build) {
  const match = /^(\d{8})\.(\d+)-/.exec(build || '');
  return Boolean(match && (Number(match[1]) > MINIMUM_BACKEND[0] ||
    Number(match[1]) === MINIMUM_BACKEND[0] && Number(match[2]) >= MINIMUM_BACKEND[1]));
}

function panelRequestScope() {
  return {asset_id:assetId,dataset_id:matchedSelection?.dataset_id ?? null,
    machine_id:matchedSelection?.machine_id ?? null,matched:Boolean(matchedSelection),
    connection_id:connectionId,origin:localOrigin,mode,dataMode,generation:contextGeneration};
}
function matchesPanelScope(scope) {
  if (!scope || state !== 'connected' || mode !== 'work' || !assetId || !matchedSelection) return false;
  const current = panelRequestScope();
  return Object.keys(current).every(key => current[key] === scope[key]);
}
function resetCatalogRequest(message, request = catalogRequest) {
  if (request !== catalogRequest) return false;
  clearTimeout(request?.timer); catalogRequest = null;
  if (get('capture-catalog')) get('capture-catalog').disabled = false;
  if (message && get('catalog-status')) get('catalog-status').textContent = message;
  return true;
}
function currentCatalogRequest(request) {
  return catalogRequest === request && request.generation === catalogGeneration && matchesPanelScope(request.scope);
}
function invalidatePanelRequests(message) {
  contextGeneration++; catalogGeneration++; markTicket++;
  clearTimeout(faultPageTimer);faultPageTimer=null;faultPageRead=null;faultPageLastKey='';faultPageLastAt=0;
  activeResearchId = null;
  if (state === 'connected') get('standalone').href = assistantUrl(false);
  resetCatalogRequest(message);
  if (get('catalog-open')) get('catalog-open').disabled = false;
  clearAIGuidance();
}
function catalogError(message) { const error = new Error(message); error.catalogMessage = message; return error; }

function contextText(message) {
  get('context').dataset.stale = String(pageChanged);
  get('context').textContent = (pageChanged ? '当前页面尚未关联。 ' : '') +
    (!followEnabled && mode !== 'demo' ? '自动跟随已暂停。 ' : '') + message;
  if (get('device-detail')) get('device-detail').textContent = assetId ? 'Trackunit 设备 ID：' + assetId : '尚未识别设备。';
  get('identify').hidden = false;
}
function markPageChanged() {
  pageGeneration++; lookupTicket++;
  clearTimeout(contextDeadline);
  if (assetId) { pageChanged = true; contextText('正在核对当前设备。'); }
}
function scheduleRead() {
  clearTimeout(followTimer);
  if (!followEnabled || mode === 'demo' || dataMode === 'demo') return;
  followTimer = setTimeout(() => { followTimer = null; readCurrent(false); }, FOLLOW_DELAY);
}
function isCurrentFaultPage(tab) {
  if (!Number.isInteger(tab?.id) || tab.id !== currentTabId || tab.status === 'loading' ||
      trackunitAssetId(tab.url) !== assetId || !/\/events\/?$/.test(new URL(tab.url).pathname)) return false;
  return true;
}
function reportFaultPageError(scope, reason = 'read_failed') {
  if (!matchesPanelScope(scope)) return;
  frame.contentWindow.postMessage({type:'jilian:trackunit-page-faults-error',protocol:1,
    connection_id:scope.connection_id,asset_id:scope.asset_id,dataset_id:scope.dataset_id,reason},scope.origin);
}
async function captureFaultPage(tab, attempt = 0) {
  if (!isCurrentFaultPage(tab) || state !== 'connected' || mode !== 'work' || pageChanged || !matchedSelection) return;
  const scope = panelRequestScope(), read = {scope,tabId:tab.id};
  faultPageRead = read;
  try {
    await chrome.scripting.executeScript({target:{tabId:tab.id},files:['trackunit-fault-page.js']});
    if (faultPageRead !== read || !matchesPanelScope(scope) || !isCurrentFaultPage(tab)) return;
    const [item] = await chrome.scripting.executeScript({target:{tabId:tab.id},func:() => TrackunitFaultPage.capture()});
    if (faultPageRead !== read || !matchesPanelScope(scope) || !isCurrentFaultPage(tab)) return;
    const capture = item?.result;
    if (capture?.schema_version !== 1 || capture.asset_id !== scope.asset_id ||
        !['visible_fault_cards','no_visible_fault_cards'].includes(capture.capture_status)) {
      reportFaultPageError(scope); return;
    }
    if (capture.capture_status === 'no_visible_fault_cards' && attempt < 2) {
      faultPageTimer = setTimeout(() => captureFaultPage(tab, attempt + 1), 1300); return;
    }
    faultPageLastKey = tab.id + '|' + tab.url + '|' + (scope.dataset_id || '');faultPageLastAt = Date.now();
    frame.contentWindow.postMessage({type:'jilian:trackunit-page-faults',protocol:1,
      connection_id:scope.connection_id,asset_id:scope.asset_id,dataset_id:scope.dataset_id,capture},scope.origin);
  } catch {
    // A page-read failure is distinct from an empty Events page and from the API state.
    if (faultPageRead === read && matchesPanelScope(scope) && isCurrentFaultPage(tab))
      reportFaultPageError(scope);
  }
  finally { if (faultPageRead === read) faultPageRead = null; }
}
function scheduleFaultPage(tab) {
  if (!isCurrentFaultPage(tab) || state !== 'connected' || !matchedSelection || pageChanged) return;
  const key = tab.id + '|' + tab.url + '|' + (matchedSelection.dataset_id || '');
  if (faultPageRead || key === faultPageLastKey && Date.now() - faultPageLastAt < 60000) return;
  clearTimeout(faultPageTimer);
  faultPageTimer = setTimeout(() => {faultPageTimer=null;void captureFaultPage(tab);}, 900);
}
function scheduleCurrentFaultPage() {
  chrome.tabs.query({active:true,currentWindow:true}).then(([tab]) => scheduleFaultPage(tab)).catch(() => {});
}
function setFollow(enabled) {
  followEnabled = enabled;
  clearTimeout(followTimer); lookupTicket++;
  get('follow').setAttribute('aria-pressed', String(enabled));
  get('follow').textContent = enabled ? '自动跟随 · 开' : '自动跟随 · 关';
}
chrome.tabs.onActivated?.addListener(info => {
  if (currentWindowId !== null && info.windowId !== currentWindowId) return;
  if (Number.isInteger(info.tabId)) currentTabId = info.tabId;
  if (mode === 'demo' || dataMode === 'demo') return;
  markPageChanged(); scheduleRead();
});
chrome.tabs.onUpdated?.addListener((id, change) => {
  if (id !== currentTabId || !(change.url || change.title || change.status === 'loading' || change.status === 'complete')) return;
  if (mode === 'demo' || dataMode === 'demo') return;
  markPageChanged();
  if (change.url || change.title || change.status === 'complete') scheduleRead();
});

function assistantUrl(withPanel = true) {
  const query = new URLSearchParams();
  if (withPanel) query.set('panel', connectionId);
  else if (mode === 'work' && activeResearchId) {
    query.set('research', activeResearchId);
    if (/^[a-f0-9]{64}$/.test(matchedSelection?.dataset_id || '')) query.set('dataset', matchedSelection.dataset_id);
  }
  if (mode === 'demo') query.set('demo', '1');
  query.set('mode',dataMode);
  return localOrigin + '/assistant-ui/' + (query.size ? '?' + query : '') + (assetId && mode === 'work' && dataMode === 'live' ? '#trackunit-asset=' + assetId : '');
}
function setState(next) {
  state = next;
  if (next !== 'connected') activeResearchId = null;
  get('workspace').dataset.state = next;
  get('connection').dataset.state = next;
  get('connection-cover').hidden = next === 'connected';
  frame.setAttribute('aria-hidden', String(next !== 'connected'));
  get('standalone').setAttribute('aria-disabled', String(next !== 'connected'));
  if (next === 'connected') get('standalone').href = assistantUrl(false);
  else get('standalone').removeAttribute('href');
}
function requestContext(showWork = false) {
  if (dataMode === 'live' && assetId && !pageChanged && state === 'connected') frame.contentWindow.postMessage({
    type: 'jilian:context-request', protocol: 1, connection_id: connectionId, asset_id: assetId,
    equipment_id_hint: equipmentIdHint,
    ...(showWork ? {show_work:true} : {})
  }, localOrigin);
}
function awaitContext() {
  clearTimeout(contextDeadline);
  if (!assetId || pageChanged) return;
  const expectedId = assetId, expectedConnection = connectionId;
  contextText('正在读取设备，等待数据确认。');
  contextDeadline = setTimeout(() => {
    if (assetId === expectedId && connectionId === expectedConnection)
      contextText('尚未收到设备匹配确认，请在下方重试。');
  }, 8000);
  requestContext(showWorkOnReady); showWorkOnReady = false;
}
function failConnection() {
  clearTimeout(deadline); clearTimeout(contextDeadline);
  connectionId = 'inactive-' + (++sequence);
  setState('failed');
  frame.removeAttribute('src');
  get('connection').textContent = '未连接';
  get('cover-title').textContent = '设备助手尚未连接';
  get('cover-detail').textContent = '未找到兼容的工作区，请启动设备助手后重新连接。';
  get('connection-detail').textContent = failures.map(item => item.port + '：' + item.reason).join('；');
  get('runtime').textContent = 'AI 服务配置尚未读取。';
  get('help').hidden = false;
  get('start-command').textContent = 'start_local.cmd --port ' + preferredPort;
  get('cover-retry').hidden = false;
  if (assetId) contextText('连接已断开，设备关联尚未确认。');
}
function attemptNext() {
  clearTimeout(deadline); clearTimeout(contextDeadline);
  matchedSelection = null; invalidatePanelRequests();
  if (!remaining.length) { failConnection(); return; }
  const port = remaining.shift();
  localOrigin = 'http://127.0.0.1:' + port;
  connectionId = String(Date.now()) + '-' + (++sequence);
  dataReady = false; runtime = null;
  setState('connecting');
  get('connection').textContent = '连接中';
  get('cover-title').textContent = '正在连接设备助手';
  get('cover-detail').textContent = failures.length ? '正在尝试备用连接，请稍候…' : '请稍候，工作区即将就绪。';
  get('connection-detail').textContent = failures.length ? failures.map(item => item.port + '：' + item.reason).join('；') : '正在连接本机服务…';
  get('runtime').textContent = '正在读取 AI 服务配置…';
  get('help').hidden = true; get('cover-retry').hidden = true;
  frame.title = dataMode === 'demo' ? '机联智检演示工作区' : '机联智检设备工作区';
  frame.src = assistantUrl();
  const attemptId = connectionId;
  deadline = setTimeout(() => {
    if (connectionId !== attemptId || state !== 'connecting') return;
    failures.push({port, reason: dataReady ? '工作区已响应，配置未确认' : runtime ? '已读取配置，工作区尚未就绪' : '未收到助手回应'});
    attemptNext();
  }, HANDSHAKE_TIMEOUT);
}
function connect(firstPort = preferredPort) {
  const first = PORTS.includes(firstPort) ? firstPort : '8890';
  remaining = [first, ...PORTS.filter(port => port !== first)]; failures = [];
  attemptNext();
}
function finishHandshake() {
  if (!dataReady || !runtime || state !== 'connecting') return;
  clearTimeout(deadline);
  setState('connected');
  const port = new URL(localOrigin).port;
  get('connection').textContent = '已连接';
  get('connection-detail').textContent = failures.length
    ? '优先端口未响应，已自动连接 ' + port + '。保存的端口偏好保持不变。'
    : '已连接本机服务，端口 ' + port + '。';
  get('runtime').textContent = runtime.provider + ' / ' + runtime.model + ' · ' + runtime.backend_build + '。模型可用性以实际分析结果为准。';
  if (assetId) awaitContext();
  else {
    contextText(mode === 'demo' ? '模拟案例 · 自动跟随已暂停。' : dataMode === 'demo' ?
      '演示数据 · 自动跟随已暂停，不关联当前设备。' : '打开 Trackunit 设备页，自动关联当前机器。');
    if (resumeFollowAfterModeSwitch && dataMode === 'live' && mode === 'work') scheduleRead();
    resumeFollowAfterModeSwitch = false;
  }
}
window.addEventListener('message', event => {
  if (state === 'failed' || event.origin !== localOrigin || event.source !== frame.contentWindow) return;
  const data = event.data;
  if (data?.protocol !== 1 || data.connection_id !== connectionId) return;
  if (data.type === 'jilian:data-mode-switch') {
    if (state === 'connected' && data.mode === 'live') setDataMode('live');
    return;
  }
  if (data.type === 'jilian:trackunit-page-faults-request') {
    const scope=panelRequestScope();
    if (!matchesPanelScope(scope) || matchedSelection.machine_id!==assetId ||
        data.asset_id!==scope.asset_id || data.dataset_id!==scope.dataset_id) return;
    chrome.tabs.query({active:true,currentWindow:true}).then(([tab])=>{
      if (!matchesPanelScope(scope)) return;
      if (!isCurrentFaultPage(tab)) {reportFaultPageError(scope,'wrong_page');return;}
      if (pageChanged) {reportFaultPageError(scope,'identity_pending');return;}
      if (!faultPageRead) void captureFaultPage(tab);
    }).catch(()=>reportFaultPageError(scope));
    return;
  }
  if (data.type === 'jilian:research-active') {
    if (state !== 'connected' || mode !== 'work' || pageChanged || !assetId || !matchedSelection ||
      data.asset_id !== assetId || matchedSelection.machine_id !== assetId ||
      data.dataset_id !== matchedSelection.dataset_id ||
      !(data.research_id === null || typeof data.research_id === 'string' && /^[a-f0-9]{32}$/.test(data.research_id))) return;
    activeResearchId = data.research_id;
    get('standalone').href = assistantUrl(false);
    return;
  }
  if (data.type === 'jilian:asset-hint-request') {
    if (mode === 'work' && state === 'connected' && data.asset_id === assetId) requestContext();
    return;
  }
  if (data.type === 'jilian:view') {
    if (!['demo','work'].includes(data.view) || !['user','platform','initial'].includes(data.reason) || data.asset_id !== assetId) return;
    const wasDemo = mode === 'demo';
    mode = data.view;
    if (mode === 'demo') {
      setFollow(false); clearTimeout(contextDeadline); pageChanged = false;
      invalidatePanelRequests('演示模式不读取真实图册。');
      contextText('模拟案例 · 自动跟随已暂停。');
    } else if (data.reason === 'user' && wasDemo) {
      readCurrent(true);
    }
    if (state === 'connected') get('standalone').href = assistantUrl(false);
    return;
  }
  if (data.type === 'jilian:context') {
    if (state !== 'connected' || pageChanged || mode !== 'work') return;
    const label = trackunitContextLabel(data, assetId); if (label === null) return;
    const nextSelection = data.state === 'matched' ? {machine_id:data.machine_id,dataset_id:data.dataset_id} : null;
    const selectionChanged = Boolean(matchedSelection) !== Boolean(nextSelection) ||
      matchedSelection?.machine_id !== nextSelection?.machine_id || matchedSelection?.dataset_id !== nextSelection?.dataset_id;
    matchedSelection = nextSelection;
    if (selectionChanged) invalidatePanelRequests();
    const displayLabel = {matched:'已关联当前设备。', loading:'正在读取当前设备数据…',
      pending:'正在完成上一项操作，尚未切换设备。', unavailable:'设备读取失败，请在下方重试。',
      missing:'当前设备暂无可用数据，请在下方读取。', choose_version:'数据版本尚未选定，请在下方选择。'}[data.state] || label;
    clearTimeout(contextDeadline); lastContextLabel = displayLabel; contextText(displayLabel);
    if (nextSelection) scheduleCurrentFaultPage(); return;
  }
  if (data.type === 'jilian:xgss-catalog-result') {
    const request = catalogRequest;
    if (!request || data.request_id !== request.request_id || !currentCatalogRequest(request)) return;
    const message = typeof data.message === 'string' ? data.message.slice(0,400) : data.success ? '已读取，查看下方备件候选。' : '图册读取未完成。';
    resetCatalogRequest(message, request); return;
  }
  if (data.type === 'jilian:ready') dataReady = true;
  else if (data.type === 'jilian:ai-guidance') {
    const waiting = data.request_id && guidanceWaiters.get(data.request_id);
    if (waiting) {
      guidanceWaiters.delete(data.request_id); clearTimeout(waiting.timer);
      waiting.resolve(waiting.ticket === guidanceTicket && matchesPanelScope(waiting.scope) ? data : null);
    }
  }
  else if (data.type === 'jilian:runtime' && ['provider', 'model', 'backend_build'].every(key => typeof data[key] === 'string' && data[key].length > 0 && data[key].length <= 160)) {
    if (!supportsDeviceFollowing(data.backend_build)) {
      if (state !== 'connecting') return;
      failures.push({port:new URL(localOrigin).port,reason:'服务版本较旧，不支持当前设备关联；请更新后重启'});
      attemptNext(); return;
    }
    runtime = data;
  }
  else return;
  finishHandshake();
});
get('retry').onclick = () => connect();
get('cover-retry').onclick = () => connect();
get('standalone').onclick = event => { if (state !== 'connected') event.preventDefault(); };
function updateDataModeButtons(){
  get('mode-demo')?.setAttribute('aria-pressed',String(dataMode==='demo'));
  get('mode-live')?.setAttribute('aria-pressed',String(dataMode==='live'));
}
function setDataMode(next){
  if (!['demo','live'].includes(next) || next===dataMode && state==='connected') return;
  dataMode=next;
  try { localStorage.setItem('jilian-data-mode',next); } catch {}
  resumeFollowAfterModeSwitch=next==='live';
  mode='work';assetId=null;equipmentIdHint=null;pageChanged=false;lastContextLabel='';matchedSelection=null;
  invalidatePanelRequests();setFollow(next==='live');updateDataModeButtons();
  get('connection-options').open=false;
  contextText(next==='demo'?'正在打开演示数据…':'正在切换到 Trackunit 设备数据…');
  connect(localOrigin ? new URL(localOrigin).port : preferredPort);
}
if(get('mode-demo'))get('mode-demo').onclick=()=>setDataMode('demo');
if(get('mode-live'))get('mode-live').onclick=()=>setDataMode('live');
updateDataModeButtons();
// Legacy replay remains testable, but the competition panel has no entry for it.
if (get('open-demo')) get('open-demo').onclick = () => {
  if (mode === 'demo' && state === 'connected') return;
  if (mode === 'work' && state === 'connected' && !window.confirm('打开历史分析回放会重新载入工作区，未保存的输入将丢失。是否继续？')) return;
  setFollow(false); mode = 'demo'; assetId = null; equipmentIdHint = null; pageChanged = false; lastContextLabel = '';
  matchedSelection = null; invalidatePanelRequests();
  contextText('正在打开模拟案例…');
  connect(localOrigin ? new URL(localOrigin).port : preferredPort);
};
get('service-form').onsubmit = event => {
  event.preventDefault();
  if (!PORTS.includes(portSelector.value)) return;
  preferredPort = portSelector.value;
  try { localStorage.setItem('jilian-service-port', preferredPort); } catch {}
  get('connection-options').open = false;
  connect();
};
async function readCurrent(manual = false) {
  if (dataMode === 'demo') { if(manual)setDataMode('live'); return; }
  if (!manual && (!followEnabled || mode === 'demo')) return;
  clearTimeout(followTimer);
  const button = get('identify');
  if (manual) {
    button.disabled = true; setFollow(true); mode = 'work'; showWorkOnReady = true;
    contextText('正在读取当前设备…');
  }
  const generation = pageGeneration, ticket = ++lookupTicket;
  try {
    const [tab] = await chrome.tabs.query({active: true, currentWindow: true});
    if (ticket !== lookupTicket || generation !== pageGeneration) return;
    if (Number.isInteger(tab?.id)) currentTabId = tab.id;
    if (Number.isInteger(tab?.windowId)) currentWindowId = tab.windowId;
    if (tab?.status === 'loading' || tab?.pendingUrl) {
      if (assetId) pageChanged = true;
      contextText('页面正在加载，完成后自动核对设备。');
      if (mode === 'demo') setFollow(false);
      return;
    }
    if (typeof XGSSCatalog !== 'undefined' && XGSSCatalog.isXGSS(tab?.url)) {
      pageChanged = false;
      contextText(assetId ? '正在查看 XGSS，保留当前设备调查。' : '请先在 Trackunit 选择设备，再读取对应图册。');
      return;
    }
    const found = trackunitAssetId(tab?.url);
    if (!found) throw new Error('当前页面无法识别设备，请打开 Trackunit 设备详情页。');
    const nextHint = trackunitEquipmentHint(tab?.title), hintChanged = equipmentIdHint !== nextHint;
    const frameIsDemo = frame.src && new URL(frame.src).searchParams.get('demo') === '1';
    const sameDocument = mode === 'work' && state !== 'failed' && !frameIsDemo;
    const sameAsset = mode === 'work' && assetId === found, wasChanged = pageChanged;
    assetId = found; equipmentIdHint = nextHint; pageChanged = false; mode = 'work';
    if (sameAsset && sameDocument) {
      // Sub-tabs, reloads and repeated events must not reset the work form or acknowledgement timer.
      if (wasChanged || manual || hintChanged) {
        contextText(lastContextLabel || '正在读取设备，等待数据确认。');
        requestContext(manual || showWorkOnReady); showWorkOnReady = false;
      }
      scheduleFaultPage(tab);
      return;
    }
    lastContextLabel = '';
    matchedSelection = null; invalidatePanelRequests('设备已切换，请读取对应 VIN 的 XGSS 图册。');
    if (sameDocument) {
      // A hash-only change preserves drafts/in-flight analysis. Device acknowledgement is renewed.
      frame.src = assistantUrl();
      if (state === 'connected') { get('standalone').href = assistantUrl(false); awaitContext(); }
      else contextText('已识别设备，正在等待工作区连接。');
    } else if (state === 'failed' && !manual) {
      contextText('设备已识别，本机服务尚未连接，请重新连接。');
    } else {
      // Every full navigation gets a new connection id and a complete readiness handshake.
      contextText('已识别设备，正在连接工作区。');
      connect(localOrigin ? new URL(localOrigin).port : preferredPort);
    }
  } catch (error) {
    if (ticket !== lookupTicket || generation !== pageGeneration) return;
    clearTimeout(contextDeadline);
    if (assetId) pageChanged = true;
    if (mode === 'demo') setFollow(false);
    const message = error?.message === '当前页面无法识别设备，请打开 Trackunit 设备详情页。'
      ? error.message : '无法读取当前页面，请检查插件的 Trackunit 站点访问权限后重试。';
    contextText(message);
  } finally { if (manual) button.disabled = false; }
}
get('identify').onclick = () => readCurrent(true);

/* ---- AI guidance for the parts catalog -------------------------------------
   The panel cannot judge what a parts page means. It asks the workbench for the
   AI's current hypotheses (suspicious components and the manual search terms
   behind them), shows them here, and uses them to mark the matching rows on the
   XGSS page. That is the AI's role made visible: what to look for, where to look,
   and — once rows come back — which candidate the evidence supports. */
let aiGuidance = {terms:[],components:[],fault_code:null,has_report:false};
let aiGuidanceScope = null;
const guidanceWaiters = new Map();
let guidanceTicket = 0, markTicket = 0;

function settleGuidanceWaiters() {
  for (const waiting of guidanceWaiters.values()) { clearTimeout(waiting.timer); waiting.resolve(null); }
  guidanceWaiters.clear();
}
function clearAIGuidance() {
  guidanceTicket++; settleGuidanceWaiters();
  aiGuidance = {terms:[],components:[],fault_code:null,has_report:false};
  aiGuidanceScope = null; renderAIGuidance();
}

function renderAIGuidance() {
  const status = get('ai-guidance-status'), terms = get('ai-guidance-terms'), list = get('ai-guidance-components');
  if (!status || !terms || !list) return;
  terms.replaceChildren(); list.replaceChildren();
  terms.hidden = true; list.hidden = true;
  if (state !== 'connected') { status.textContent = '连接工作区后读取 AI 建议。'; return; }
  if (mode !== 'work' || !assetId || !matchedSelection) { status.textContent = '请先读取设备，并等待助手确认实测数据。'; return; }
  if (!matchesPanelScope(aiGuidanceScope) || !aiGuidance.has_report) {
    status.textContent = '尚无 AI 检索词，请先在设备工作区完成分析。';
    return;
  }
  status.textContent = aiGuidance.fault_code
    ? `AI 依据 ${aiGuidance.fault_code} 给出 ${aiGuidance.components.length} 个可疑部件、${aiGuidance.terms.length} 个图册检索词：`
    : `AI 给出 ${aiGuidance.components.length} 个可疑部件、${aiGuidance.terms.length} 个图册检索词：`;
  if (aiGuidance.terms.length) {
    for (const term of aiGuidance.terms) { const li = document.createElement('li'); li.textContent = term; terms.append(li); }
    terms.hidden = false;
  }
  for (const row of aiGuidance.components) {
    const li = document.createElement('li');
    const strong = document.createElement('strong'); strong.textContent = row.name; li.append(strong);
    if (row.reason) { const p = document.createElement('span'); p.textContent = row.reason; li.append(p); }
    list.append(li);
  }
  list.hidden = !aiGuidance.components.length;
}

async function requestAIGuidance() {
  if (!matchesPanelScope(panelRequestScope()) || !frame.contentWindow) { clearAIGuidance(); return aiGuidance; }
  const scope = panelRequestScope(), ticket = ++guidanceTicket;
  settleGuidanceWaiters();
  const request_id = 'guidance-' + Date.now() + '-' + (++sequence);
  const answer = new Promise(resolve => {
    const waiting = {resolve,scope,ticket};
    waiting.timer = setTimeout(() => {
      if (guidanceWaiters.get(request_id) !== waiting) return;
      guidanceWaiters.delete(request_id); resolve(null);
    }, 4000);
    guidanceWaiters.set(request_id, waiting);
  });
  frame.contentWindow.postMessage({type:'jilian:ai-guidance-request',protocol:1,
    connection_id:scope.connection_id,request_id},scope.origin);
  const result = await answer;
  if (ticket !== guidanceTicket || !matchesPanelScope(scope)) return null;
  if (result) aiGuidance = {terms:result.terms||[],components:result.components||[],
    fault_code:result.fault_code||null,has_report:Boolean(result.has_report)};
  else aiGuidance = {terms:[],components:[],fault_code:null,has_report:false};
  aiGuidanceScope = scope;
  renderAIGuidance();
  return aiGuidance;
}

/** Mark the AI's search terms on an open XGSS tab. Returns what was marked. */
async function markCatalogTargets(tab, guidance = aiGuidance, current = () => matchesPanelScope(aiGuidanceScope)) {
  if (!guidance.terms.length || !current()) return null;
  await chrome.scripting.executeScript({target:{tabId:tab.id,allFrames:true},files:['xgss-catalog.js']});
  if (!current()) return null;
  const frames = await chrome.scripting.executeScript({target:{tabId:tab.id,allFrames:true},
    func:terms => (typeof XGSSCatalog === 'undefined' ? null : XGSSCatalog.mark(terms)),
    args:[guidance.terms]});
  if (!current()) return null;
  const results = frames.map(item => item.result).filter(Boolean);
  return results.reduce((best,item) => (!best || item.marked_rows > best.marked_rows ? item : best), null);
}

async function markOpenCatalogTab() {
  const note = get('catalog-status'), button = get('catalog-open');
  if (!matchesPanelScope(panelRequestScope())) {
    note.textContent = '请先读取设备，并等待助手确认实测数据。'; return;
  }
  const scope = panelRequestScope(), ticket = ++markTicket;
  const current = () => ticket === markTicket && matchesPanelScope(scope);
  button.disabled = true;
  try {
    // The selected fault or AI plan can change without changing the device.
    // Refresh this small local-frame payload before using any cached terms.
    if (!await requestAIGuidance()) return;
    if (!current()) return;
    const guidance = aiGuidance;
    if (!guidance.terms.length) {
      note.textContent = '当前方向尚无 AI 检索词，请先在设备工作区完成分析。'; return;
    }
    const [tab] = await chrome.tabs.query({active:true,currentWindow:true});
    if (!current()) return;
    if (!Number.isInteger(tab?.id) || !XGSSCatalog.isXGSS(tab.url)) {
      // The panel cannot cross the XGSS sign-in itself; the workbench owns that
      // handshake. Say exactly where to start instead of opening a bare web page.
      note.textContent = guidance.has_report
        ? '请切换到已登录的 XGSS 图册页，打开当前设备对应 VIN 的图册，再在插件“设置 → 图册维护”中点“标出 AI 检索条目”。'
        : '尚无 AI 建议。请先在工作区完成一次 AI 分析，再打开图册标注目标。';
      return;
    }
    const marked = await markCatalogTargets(tab, guidance, current);
    if (!current()) return;
    if (!marked) throw catalogError('暂无 AI 检索词可标出，请先完成一次 AI 分析。');
    note.textContent = marked.marked_rows
      ? `已在页面上标出 ${marked.marked_rows} 行（AI 检索词：${marked.terms.join('、')}）。`
        + (marked.unmatched.length ? ` 本页未出现：${marked.unmatched.join('、')}，可能在其他分类下。` : '')
      : `本页未出现 AI 检索词${marked.unmatched.length ? '：' + marked.unmatched.join('、') : ''}；请展开可疑部件所在分类。`;
  } catch (error) {
    if (current()) note.textContent = error?.catalogMessage || '无法在图册页面标出目标，请核对扩展的 XGSS 站点访问权限。';
  } finally { if (ticket === markTicket) button.disabled = false; }
}

if (get('catalog-open')) get('catalog-open').onclick = markOpenCatalogTab;
/* Sheets are fixed to the panel's own viewport, so their offset has to follow the
   action bar instead of being hard-coded. */
function syncSheetOffset() {
  const bar = document.querySelector('.actionbar') || document.querySelector('.panel-controls');
  if (!bar) return;
  document.documentElement.style.setProperty('--sheet-top', Math.round(bar.getBoundingClientRect().bottom) + 'px');
}
syncSheetOffset();
window.addEventListener('resize', syncSheetOffset);
/* A sheet covers the rest of the bar while it is open, so any other bar action
   closes it first — otherwise the button the user wants next is underneath it. */
function closeSheets(except) {
  for (const id of ['catalog-options', 'connection-options']) {
    const sheet = get(id);
    if (sheet && sheet !== except && !sheet.contains?.(except)) sheet.open = false;
  }
}
for (const el of document.querySelectorAll('.actionbar>button, .actionbar>a')) {
  el.addEventListener('click', () => closeSheets());
}
/* A positioned sheet escapes the closed-details hiding rule, so each sheet is
   also kept `hidden` while collapsed: a closed panel must not render at all. */
for (const id of ['catalog-options', 'connection-options']) {
  const sheet = get(id);
  if (!sheet) continue;
  const panel = sheet.querySelector('.settings-panel');
  const sync = () => { if (panel) panel.hidden = !sheet.open; };
  // The sheet itself is the source of truth for whether it is open; depending on
  // event.target would also tie this handler to how the event was dispatched.
  sheet.addEventListener('toggle', () => {
    if (sheet.open) closeSheets(sheet);
    sync();
    syncSheetOffset();
    // Returning the guidance promise lets a caller await the refresh that
    // opening this sheet triggers.
    if (sheet.open && id === 'catalog-options') return requestAIGuidance();
    return undefined;
  });
  sync();
}

if (get('capture-catalog')) get('capture-catalog').onclick = async () => {
  const note = get('catalog-status'), button = get('capture-catalog');
  if (state !== 'connected' || mode !== 'work' || !assetId || !matchedSelection) {
    note.textContent = '请先在 Trackunit 打开设备，并等待助手确认实测数据。'; return;
  }
  if (catalogRequest) return;
  const scope = panelRequestScope();
  const request = {request_id:'catalog-' + Date.now() + '-' + (++sequence),
    asset_id:scope.asset_id,dataset_id:scope.dataset_id,scope,generation:++catalogGeneration};
  catalogRequest = request;
  button.disabled = true; note.textContent = '正在读取当前可见图册…';
  try {
    const [tab] = await chrome.tabs.query({active:true,currentWindow:true});
    if (!currentCatalogRequest(request)) return;
    if (!Number.isInteger(tab?.id) || tab.status === 'loading' || !XGSSCatalog.isXGSS(tab.url))
      throw catalogError('请打开 XGSS 页面，选中分类并显示零件明细后再读取。');
    await chrome.scripting.executeScript({target:{tabId:tab.id,allFrames:true},files:['xgss-catalog.js']});
    if (!currentCatalogRequest(request)) return;
    // Mark the AI's search terms first, so the highlight matches the rows that
    // are about to be read and the user sees what the AI asked for.
    if (matchesPanelScope(aiGuidanceScope) && aiGuidance.terms.length)
      await markCatalogTargets(tab, aiGuidance, () => currentCatalogRequest(request));
    if (!currentCatalogRequest(request)) return;
    const frames = await chrome.scripting.executeScript({target:{tabId:tab.id,allFrames:true},func:() => XGSSCatalog.capture()});
    if (!currentCatalogRequest(request)) return;
    const captures = frames.map(item => item.result).filter(Boolean);
    const valid = captures.filter(item => item.capture_status === 'visible_rows');
    if (valid.length > 1) throw catalogError('页面存在多个图册区域，无法确认唯一来源。请独立打开所需图册再读取。');
    if (!valid.length) {
      const statuses = captures.map(item => item.capture_status);
      throw catalogError(statuses.includes('ambiguous_vin') ? '页面出现多个 VIN，未导入。请打开单台设备图册。' : statuses.includes('vin_missing') ? '页面未显示可识别的 VIN/PIN，未导入。请先显示设备信息。' : '未读取到有效零件行。请选中分类、打开零件明细，并让名称和物料编码同时显示。');
    }
    frame.contentWindow.postMessage({type:'jilian:xgss-catalog-capture',protocol:1,connection_id:scope.connection_id,
      request_id:request.request_id,asset_id:request.asset_id,dataset_id:request.dataset_id,capture:valid[0]},scope.origin);
    note.textContent = '已读取 ' + valid[0].items.length + ' 行，正在核对设备并保存到本机…';
    request.timer = setTimeout(() => {
      if (currentCatalogRequest(request)) resetCatalogRequest('助手未确认图册导入。请检查工作区是否已更新，并重新读取。', request);
    },15000);
  } catch (error) {
    if (currentCatalogRequest(request))
      resetCatalogRequest(error?.catalogMessage || '无法读取此图册，请核对扩展的 XGSS 站点访问权限并重新加载页面。', request);
  }
};
get('follow').onclick = () => {
  if (dataMode === 'demo') return setDataMode('live');
  if (!followEnabled || mode === 'demo') return readCurrent(true);
  setFollow(false);
  contextText(assetId ? '保留当前设备。' : '点击“读取当前设备”可恢复自动跟随。');
};
connect();
scheduleRead();
