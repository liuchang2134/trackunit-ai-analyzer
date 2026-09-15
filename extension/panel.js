/* Exact Trackunit hosts expose only the active URL. Connection probes use loopback frames, never fetch. */
const PORTS = ['8892', '8890'];
const HANDSHAKE_TIMEOUT = 6500;
const FOLLOW_DELAY = 150;
const get = id => document.getElementById(id);
const frame = get('assistant'), portSelector = get('service-port');
let preferredPort = '8892';
try { const saved = localStorage.getItem('jilian-service-port'); if (PORTS.includes(saved)) preferredPort = saved; } catch {}
portSelector.value = preferredPort;
let deadline, contextDeadline, assetId = null, localOrigin, connectionId, sequence = 0;
let dataReady = false, runtime = null, state = 'connecting', mode = 'work', remaining = [], failures = [];
let pageChanged = false, pageGeneration = 0, currentTabId = null, currentWindowId = null;
let followEnabled = true, followTimer, lookupTicket = 0, lastContextLabel = '';
let matchedSelection = null, catalogRequest = null, catalogDeadline;

function resetCatalogRequest(message) {
  clearTimeout(catalogDeadline); catalogRequest = null;
  if (get('capture-catalog')) get('capture-catalog').disabled = false;
  if (message && get('catalog-status')) get('catalog-status').textContent = message;
}
function catalogError(message) { const error = new Error(message); error.catalogMessage = message; return error; }

function contextText(message) {
  get('context').dataset.stale = String(pageChanged);
  get('context').textContent = (pageChanged ? '当前页面尚未关联，下面保留上次设备。 ' : '') +
    (!followEnabled && mode !== 'demo' ? '自动跟随已暂停。 ' : '') + message;
}
function markPageChanged() {
  pageGeneration++; lookupTicket++;
  clearTimeout(contextDeadline);
  if (assetId) { pageChanged = true; contextText('正在核对页面。上次设备 ID：' + assetId); }
}
function scheduleRead() {
  clearTimeout(followTimer);
  if (!followEnabled || mode === 'demo') return;
  followTimer = setTimeout(() => { followTimer = null; readCurrent(false); }, FOLLOW_DELAY);
}
function setFollow(enabled) {
  followEnabled = enabled;
  clearTimeout(followTimer); lookupTicket++;
  get('follow').setAttribute('aria-pressed', String(enabled));
  get('follow').textContent = enabled ? '自动跟随：开' : '自动跟随：关';
}
chrome.tabs.onActivated?.addListener(info => {
  if (currentWindowId !== null && info.windowId !== currentWindowId) return;
  if (Number.isInteger(info.tabId)) currentTabId = info.tabId;
  markPageChanged(); scheduleRead();
});
chrome.tabs.onUpdated?.addListener((id, change) => {
  if (id !== currentTabId || !(change.url || change.status === 'loading' || change.status === 'complete')) return;
  markPageChanged();
  if (change.url || change.status === 'complete') scheduleRead();
});

function assistantUrl(withPanel = true) {
  const query = new URLSearchParams();
  if (withPanel) query.set('panel', connectionId);
  if (mode === 'demo') query.set('demo', '1');
  return localOrigin + '/assistant-ui/' + (query.size ? '?' + query : '') + (assetId ? '#trackunit-asset=' + assetId : '');
}
function setState(next) {
  state = next;
  get('workspace').dataset.state = next;
  get('connection').dataset.state = next;
  get('connection-cover').hidden = next === 'connected';
  frame.setAttribute('aria-hidden', String(next !== 'connected'));
  get('standalone').setAttribute('aria-disabled', String(next !== 'connected'));
  if (next === 'connected') get('standalone').href = assistantUrl(false);
  else get('standalone').removeAttribute('href');
}
function requestContext() {
  if (assetId && !pageChanged && state === 'connected') frame.contentWindow.postMessage({
    type: 'jilian:context-request', protocol: 1, connection_id: connectionId, asset_id: assetId
  }, localOrigin);
}
function awaitContext() {
  clearTimeout(contextDeadline);
  if (!assetId || pageChanged) return;
  const expectedId = assetId, expectedConnection = connectionId;
  contextText('已读取设备 ID，正在等待助手确认数据与版本。');
  contextDeadline = setTimeout(() => {
    if (assetId === expectedId && connectionId === expectedConnection)
      contextText('尚未收到设备匹配确认，请核对工作区中的设备和数据版本。');
  }, 8000);
  requestContext();
}
function failConnection() {
  clearTimeout(deadline); clearTimeout(contextDeadline);
  connectionId = 'inactive-' + (++sequence);
  setState('failed');
  frame.removeAttribute('src');
  get('connection').textContent = '未连接';
  get('cover-title').textContent = '本机助手尚未连接';
  get('cover-detail').textContent = '已检查端口 ' + failures.map(item => item.port).join('、') + '，未完成连接。请启动本机服务后重试。';
  get('connection-detail').textContent = failures.map(item => item.port + '：' + item.reason).join('；');
  get('runtime').textContent = '尚未读取后端配置。';
  get('help').hidden = false;
  get('start-command').textContent = 'start_local.cmd --port ' + preferredPort;
  get('cover-retry').hidden = false;
  if (assetId) contextText('保留上次读取的设备 ID；重新连接后再确认匹配。');
}
function attemptNext() {
  clearTimeout(deadline); clearTimeout(contextDeadline);
  matchedSelection = null; resetCatalogRequest();
  if (!remaining.length) { failConnection(); return; }
  const port = remaining.shift();
  localOrigin = 'http://127.0.0.1:' + port;
  connectionId = String(Date.now()) + '-' + (++sequence);
  dataReady = false; runtime = null;
  setState('connecting');
  get('connection').textContent = '连接中 · ' + port;
  get('cover-title').textContent = '正在连接本机助手';
  get('cover-detail').textContent = failures.length ? '正在尝试备用端口 ' + port + '…' : '正在检查本机端口 ' + port + '…';
  get('connection-detail').textContent = failures.length ? failures.map(item => item.port + '：' + item.reason).join('；') : '通过网页握手确认连接，不调用 AI 或设备接口。';
  get('runtime').textContent = '等待后端配置…';
  get('help').hidden = true; get('cover-retry').hidden = true;
  frame.title = mode === 'demo' ? '机联智检模拟案例' : '机联智检设备工作区';
  frame.src = assistantUrl();
  const attemptId = connectionId;
  deadline = setTimeout(() => {
    if (connectionId !== attemptId || state !== 'connecting') return;
    failures.push({port, reason: dataReady ? '工作区已响应，配置未确认' : runtime ? '已读取配置，工作区尚未就绪' : '未收到助手回应'});
    attemptNext();
  }, HANDSHAKE_TIMEOUT);
}
function connect(firstPort = preferredPort) {
  const first = PORTS.includes(firstPort) ? firstPort : '8892';
  remaining = [first, ...PORTS.filter(port => port !== first)]; failures = [];
  attemptNext();
}
function finishHandshake() {
  if (!dataReady || !runtime || state !== 'connecting') return;
  clearTimeout(deadline);
  setState('connected');
  const port = new URL(localOrigin).port;
  get('connection').textContent = '已连接 · ' + port;
  get('connection-detail').textContent = failures.length
    ? '优先端口未响应，已自动连接 ' + port + '。保存的端口偏好保持不变。'
    : '本机界面与后端配置已确认。';
  get('runtime').textContent = runtime.provider + ' / ' + runtime.model + ' · ' + runtime.backend_build + '。模型可用性以实际分析结果为准。';
  if (assetId) awaitContext();
  else contextText(mode === 'demo' ? '模拟案例 · 自动跟随已暂停；预设讲解不调用外部接口。' : '打开 Trackunit 设备详情页后自动读取；也可先查看演示案例。');
}
window.addEventListener('message', event => {
  if (state === 'failed' || event.origin !== localOrigin || event.source !== frame.contentWindow) return;
  const data = event.data;
  if (data?.protocol !== 1 || data.connection_id !== connectionId) return;
  if (data.type === 'jilian:context') {
    if (state !== 'connected' || pageChanged || mode !== 'work') return;
    const label = trackunitContextLabel(data, assetId); if (label === null) return;
    matchedSelection = data.state === 'matched' ? {machine_id:data.machine_id,dataset_id:data.dataset_id} : null;
    clearTimeout(contextDeadline); lastContextLabel = label; contextText(label + ' 设备 ID：' + assetId); return;
  }
  if (data.type === 'jilian:xgss-catalog-result') {
    if (!catalogRequest || data.request_id !== catalogRequest.request_id || catalogRequest.asset_id !== assetId ||
        !matchedSelection || catalogRequest.dataset_id !== matchedSelection.dataset_id) return;
    const message = typeof data.message === 'string' ? data.message.slice(0,400) : data.success ? '已读取，查看下方备件候选。' : '图册读取未完成。';
    resetCatalogRequest(message); return;
  }
  if (data.type === 'jilian:ready') dataReady = true;
  else if (data.type === 'jilian:runtime' && ['provider', 'model', 'backend_build'].every(key => typeof data[key] === 'string' && data[key].length > 0 && data[key].length <= 160)) runtime = data;
  else return;
  finishHandshake();
});
get('retry').onclick = () => connect();
get('cover-retry').onclick = () => connect();
get('standalone').onclick = event => { if (state !== 'connected') event.preventDefault(); };
get('service-form').onsubmit = event => {
  event.preventDefault();
  if (!PORTS.includes(portSelector.value)) return;
  preferredPort = portSelector.value;
  try { localStorage.setItem('jilian-service-port', preferredPort); } catch {}
  get('connection-options').open = false;
  connect();
};
get('open-demo').onclick = () => {
  if (mode === 'demo' && state === 'connected') return;
  if (mode === 'work' && state === 'connected' && !window.confirm('打开演示案例会重新载入工作区，未保存的输入可能丢失。请先保存本机草稿。继续打开演示吗？')) return;
  setFollow(false); mode = 'demo'; assetId = null; pageChanged = false; lastContextLabel = '';
  matchedSelection = null; resetCatalogRequest();
  contextText('正在打开模拟案例…');
  connect(localOrigin ? new URL(localOrigin).port : preferredPort);
};
async function readCurrent(manual = false) {
  if (!manual && (!followEnabled || mode === 'demo')) return;
  clearTimeout(followTimer);
  const button = get('identify');
  if (manual) { button.disabled = true; setFollow(true); }
  const generation = pageGeneration, ticket = ++lookupTicket;
  try {
    const [tab] = await chrome.tabs.query({active: true, currentWindow: true});
    if (ticket !== lookupTicket || generation !== pageGeneration) return;
    if (Number.isInteger(tab?.id)) currentTabId = tab.id;
    if (Number.isInteger(tab?.windowId)) currentWindowId = tab.windowId;
    if (tab?.status === 'loading' || tab?.pendingUrl) {
      if (assetId) pageChanged = true;
      contextText('页面正在加载，完成后自动核对设备。' + (assetId ? ' 上次设备 ID：' + assetId : ''));
      if (mode === 'demo') setFollow(false);
      return;
    }
    if (typeof XGSSCatalog !== 'undefined' && XGSSCatalog.isXGSS(tab?.url)) {
      pageChanged = false;
      contextText(assetId ? '正在查看 XGSS，保留当前设备调查。读取图册时将核对 VIN。设备 ID：' + assetId : '请先在 Trackunit 选择设备，再读取对应 VIN 的 XGSS 图册。');
      return;
    }
    const found = trackunitAssetId(tab?.url);
    if (!found) throw new Error('当前页面无法识别设备，请打开 Trackunit 设备详情页。');
    const sameDocument = mode === 'work' && state !== 'failed';
    const sameAsset = mode === 'work' && assetId === found, wasChanged = pageChanged;
    assetId = found; pageChanged = false; mode = 'work';
    if (sameAsset && sameDocument) {
      // Sub-tabs, reloads and repeated events must not reset the work form or acknowledgement timer.
      if (wasChanged || manual) {
        contextText((lastContextLabel || '已读取设备 ID，等待助手确认数据与版本。') + ' 设备 ID：' + assetId);
        requestContext();
      }
      return;
    }
    lastContextLabel = '';
    matchedSelection = null; resetCatalogRequest('设备已切换，请读取对应 VIN 的 XGSS 图册。');
    if (sameDocument) {
      // A hash-only change preserves drafts/in-flight analysis. Device acknowledgement is renewed.
      frame.src = assistantUrl();
      if (state === 'connected') { get('standalone').href = assistantUrl(false); awaitContext(); }
      else contextText('已读取设备 ID，正在等待本机工作区连接。');
    } else if (state === 'failed' && !manual) {
      contextText('已读取设备 ID；本机服务尚未连接，请点击重新连接。设备 ID：' + assetId);
    } else {
      // Every full navigation gets a new connection id and a complete readiness handshake.
      contextText('已读取设备 ID，正在连接对应工作区。');
      connect(localOrigin ? new URL(localOrigin).port : preferredPort);
    }
  } catch (error) {
    if (ticket !== lookupTicket || generation !== pageGeneration) return;
    clearTimeout(contextDeadline);
    if (assetId) pageChanged = true;
    if (mode === 'demo') setFollow(false);
    const message = error?.message === '当前页面无法识别设备，请打开 Trackunit 设备详情页。'
      ? error.message : '无法读取当前页面，请检查插件的 Trackunit 站点访问权限后重试。';
    contextText(message + (assetId ? ' 上次设备 ID：' + assetId : ''));
  } finally { if (manual) button.disabled = false; }
}
get('identify').onclick = () => readCurrent(true);
if (get('capture-catalog')) get('capture-catalog').onclick = async () => {
  const note = get('catalog-status'), button = get('capture-catalog');
  if (state !== 'connected' || mode !== 'work' || !assetId || !matchedSelection) {
    note.textContent = '请先在 Trackunit 打开设备，并等待助手确认实测数据。'; return;
  }
  const selection = {...matchedSelection}, expectedAsset = assetId, expectedConnection = connectionId;
  button.disabled = true; note.textContent = '正在读取当前可见图册…';
  try {
    const [tab] = await chrome.tabs.query({active:true,currentWindow:true});
    if (!Number.isInteger(tab?.id) || tab.status === 'loading' || !XGSSCatalog.isXGSS(tab.url))
      throw catalogError('请打开 XGSS 页面，选中分类并显示零件明细后再读取。');
    await chrome.scripting.executeScript({target:{tabId:tab.id,allFrames:true},files:['xgss-catalog.js']});
    const frames = await chrome.scripting.executeScript({target:{tabId:tab.id,allFrames:true},func:() => XGSSCatalog.capture()});
    if (assetId !== expectedAsset || connectionId !== expectedConnection || !matchedSelection || matchedSelection.dataset_id !== selection.dataset_id)
      throw catalogError('设备或数据版本已切换，本次图册未导入，请重新读取。');
    const captures = frames.map(item => item.result).filter(Boolean);
    const valid = captures.filter(item => item.capture_status === 'visible_rows');
    if (valid.length > 1) throw catalogError('页面存在多个图册区域，无法确认唯一来源。请独立打开所需图册再读取。');
    if (!valid.length) {
      const statuses = captures.map(item => item.capture_status);
      throw catalogError(statuses.includes('ambiguous_vin') ? '页面出现多个 VIN，未导入。请打开单台设备图册。' : statuses.includes('vin_missing') ? '页面未显示可识别的 VIN/PIN，未导入。请先显示设备信息。' : '未读取到有效零件行。请选中分类、打开零件明细，并让名称和物料编码同时显示。');
    }
    const request_id = 'catalog-' + Date.now() + '-' + (++sequence);
    catalogRequest = {request_id,asset_id:expectedAsset,dataset_id:selection.dataset_id};
    frame.contentWindow.postMessage({type:'jilian:xgss-catalog-capture',protocol:1,connection_id:connectionId,
      ...catalogRequest,capture:valid[0]},localOrigin);
    note.textContent = '已读取 ' + valid[0].items.length + ' 行，正在核对设备并保存到本机…';
    catalogDeadline = setTimeout(() => resetCatalogRequest('助手未确认图册导入。请检查工作区是否已更新，并重新读取。'),15000);
  } catch (error) {
    resetCatalogRequest(error?.catalogMessage || '无法读取此图册，请核对扩展的 XGSS 站点访问权限并重新加载页面。');
  }
};
get('follow').onclick = () => {
  if (!followEnabled && mode === 'demo') return readCurrent(true);
  setFollow(!followEnabled);
  if (followEnabled) scheduleRead();
  else contextText(assetId ? '保留设备 ID：' + assetId : '点击“读取当前设备”可恢复自动跟随。');
};
connect();
scheduleRead();
