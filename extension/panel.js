/* Probe only the two permitted loopback frames; no host permissions or network fetch. */
const PORTS = ['8892', '8890'];
const HANDSHAKE_TIMEOUT = 6500;
const get = id => document.getElementById(id);
const frame = get('assistant'), portSelector = get('service-port');
let preferredPort = '8892';
try { const saved = localStorage.getItem('jilian-service-port'); if (PORTS.includes(saved)) preferredPort = saved; } catch {}
portSelector.value = preferredPort;
let deadline, contextDeadline, assetId = null, localOrigin, connectionId, sequence = 0;
let dataReady = false, runtime = null, state = 'connecting', mode = 'work', remaining = [], failures = [];
let pageChanged = false, pageGeneration = 0, currentTabId = null, currentWindowId = null;

function contextText(message) {
  get('context').textContent = (pageChanged ? '页面已变化，仍保留上次设备；请重新读取。 ' : '') + message;
}
function markPageChanged() {
  pageGeneration++;
  if (assetId) { pageChanged = true; contextText('设备 ID：' + assetId); }
}
chrome.tabs.onActivated?.addListener(info => { if (currentWindowId === null || info.windowId === currentWindowId) markPageChanged(); });
chrome.tabs.onUpdated?.addListener((id, change) => { if (id === currentTabId && (change.url || change.status === 'loading')) markPageChanged(); });

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
  if (assetId && state === 'connected') frame.contentWindow.postMessage({
    type: 'jilian:context-request', protocol: 1, connection_id: connectionId, asset_id: assetId
  }, localOrigin);
}
function awaitContext() {
  clearTimeout(contextDeadline);
  if (!assetId) return;
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
  else contextText(mode === 'demo' ? '模拟案例 · 预设讲解，不调用外部接口。' : '可先查看演示案例，或从 Trackunit 详情页读取设备。');
}
window.addEventListener('message', event => {
  if (state === 'failed' || event.origin !== localOrigin || event.source !== frame.contentWindow) return;
  const data = event.data;
  if (data?.protocol !== 1 || data.connection_id !== connectionId) return;
  if (data.type === 'jilian:context') {
    if (state !== 'connected') return;
    const label = trackunitContextLabel(data, assetId); if (label === null) return;
    clearTimeout(contextDeadline); contextText(label + ' 设备 ID：' + assetId); return;
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
  mode = 'demo'; assetId = null; pageChanged = false;
  contextText('正在打开模拟案例…');
  connect(localOrigin ? new URL(localOrigin).port : preferredPort);
};
get('identify').onclick = async () => {
  const button = get('identify'); button.disabled = true;
  const generation = pageGeneration;
  try {
    const [tab] = await chrome.tabs.query({active: true, currentWindow: true});
    if (generation !== pageGeneration) throw new Error('读取期间页面已变化，请重新读取当前设备。');
    const found = trackunitAssetId(tab?.url);
    if (!found) throw new Error('请打开 Trackunit 设备详情页并点击插件图标；当前页面无法识别设备。');
    const sameDocument = mode === 'work' && state === 'connected';
    assetId = found; currentTabId = tab.id; currentWindowId = tab.windowId; pageChanged = false; mode = 'work';
    if (sameDocument) {
      // A hash-only change preserves drafts/in-flight analysis. Device acknowledgement is renewed.
      frame.src = assistantUrl(); get('standalone').href = assistantUrl(false); awaitContext();
    } else {
      // Every full navigation gets a new connection id and a complete readiness handshake.
      contextText('已读取设备 ID，正在连接对应工作区。');
      connect(localOrigin ? new URL(localOrigin).port : preferredPort);
    }
  } catch (error) { contextText((error.message || '无法读取当前设备。') + (assetId ? ' 仍保留上次设备，尚未切换。' : '')); }
  finally { button.disabled = false; }
};
connect();
