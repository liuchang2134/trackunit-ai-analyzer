const PORTS=new Set(['8890','8892']);
const frame=document.getElementById('assistant');
const portSelector=document.getElementById('service-port');
try{const saved=localStorage.getItem('jilian-service-port');if(PORTS.has(saved))portSelector.value=saved;}catch{}
let deadline,contextDeadline,assetId=null,localOrigin,connectionId,sequence=0,dataReady=false,runtime=null;
let pageChanged=false,pageGeneration=0,currentTabId=null,currentWindowId=null;
function contextText(message){document.getElementById('context').textContent=(pageChanged?'浏览器页面已变化，下方保留上次设备；请重新读取。 ':'')+message;}
function markPageChanged(){pageGeneration++;if(assetId){pageChanged=true;contextText('上次读取的设备 ID：'+assetId);}}
chrome.tabs.onActivated?.addListener(info=>{if(currentWindowId===null||info.windowId===currentWindowId)markPageChanged();});
chrome.tabs.onUpdated?.addListener((id,change)=>{if(id===currentTabId&&(change.url||change.status==='loading'))markPageChanged();});
function assistantUrl(){return localOrigin+'/assistant-ui/?panel='+connectionId+(assetId?'#trackunit-asset='+assetId:'');}
function updateFrame(){frame.src=assistantUrl();document.getElementById('standalone').href=assistantUrl();}
function requestContext(){
  if(assetId)frame.contentWindow.postMessage({type:'jilian:context-request',protocol:1,connection_id:connectionId,asset_id:assetId},localOrigin);
}
function awaitContext(){
  clearTimeout(contextDeadline);
  if(!assetId)return;
  contextText('已读取平台设备 ID：'+assetId+'；正在等待下方助手确认数据匹配。');
  contextDeadline=setTimeout(()=>{contextText('尚未收到设备匹配确认。请核对下方设备，旧版网页可能不支持此确认。');},8000);
  requestContext();
}
function connect(){
  clearTimeout(deadline);
  const port=PORTS.has(portSelector.value)?portSelector.value:'8890';
  portSelector.value=port;localOrigin='http://127.0.0.1:'+port;
  connectionId=String(Date.now())+'-'+(++sequence);dataReady=false;runtime=null;
  document.getElementById('connection').textContent='正在连接本地服务…';
  document.getElementById('runtime').textContent='等待后端配置；连接成功不代表模型请求已成功。';
  document.getElementById('help').textContent='请在项目目录的 CMD 运行 start_local.cmd --port '+port+'，然后点击重新连接。旧版本服务需在其终端关闭后重新启动。';
  document.getElementById('help').hidden=true;
  updateFrame();
  awaitContext();
  deadline=setTimeout(()=>{
    document.getElementById('connection').textContent=dataReady?'界面已响应，但后端配置未通过核验。':'本地界面未响应，或服务版本过旧。';
    document.getElementById('help').hidden=false;
  },8000);
}
window.addEventListener('message',event=>{
  if(event.origin!==localOrigin || event.source!==frame.contentWindow)return;
  const data=event.data;
  if(data?.protocol!==1 || data.connection_id!==connectionId)return;
  if(data.type==='jilian:context'){
    const label=trackunitContextLabel(data,assetId);if(label===null)return;
    clearTimeout(contextDeadline);contextText(label+' 设备 ID：'+assetId);return;
  }
  if(data.type==='jilian:ready'){dataReady=true;requestContext();}
  else if(data.type==='jilian:runtime' && typeof data.provider==='string' && typeof data.model==='string' && typeof data.backend_build==='string'){
    runtime=data;
  }else return;
  if(dataReady && runtime){
    clearTimeout(deadline);
    const currentCloud=runtime.provider==='gemini' && runtime.inference_location==='cloud'
      && runtime.investigation_timeout_seconds===120 && runtime.transient_attempt_limit===3;
    document.getElementById('connection').textContent=currentCloud?'本地界面与 Gemini 配置已连接。':'界面已连接；当前后端未采用新版 Gemini 配置。';
    document.getElementById('runtime').textContent=runtime.provider+' / '+runtime.model+' · '+runtime.backend_build+'。模型是否可用需以实际分析结果为准。';
    document.getElementById('help').hidden=currentCloud;
  }
});
document.getElementById('retry').onclick=connect;
document.getElementById('service-form').onsubmit=event=>{
  event.preventDefault();
  if(!PORTS.has(portSelector.value))return;
  try{localStorage.setItem('jilian-service-port',portSelector.value);}catch{}
  connect();
};
document.getElementById('identify').onclick=async()=>{
  const button=document.getElementById('identify');button.disabled=true;
  const generation=pageGeneration;
  try{
    const [tab]=await chrome.tabs.query({active:true,currentWindow:true});
    if(generation!==pageGeneration)throw new Error('读取期间浏览器页面已变化，请重新读取当前设备。');
    const found=trackunitAssetId(tab?.url);
    if(!found)throw new Error('请打开 Trackunit 设备详情页并再次点击插件图标；列表页或其他网站无法识别。');
    assetId=found;currentTabId=tab.id;currentWindowId=tab.windowId;pageChanged=false;
    updateFrame();
    awaitContext();
  }catch(error){contextText((error.message || '无法读取当前设备。')+(assetId?' 下方仍保留上次设备，尚未切换。':''));}
  finally{button.disabled=false;}
};
connect();
