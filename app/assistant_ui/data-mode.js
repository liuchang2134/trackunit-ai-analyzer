/* The competition workbench always uses Trackunit-backed data. */
(function(global){
  const allowed = new Set(['live']);
  const mode = 'live';
  const params = new URLSearchParams(global.location?.search || '');
  if((params.get('mode')==='demo'||params.get('demo')==='1')&&global.history?.replaceState){
    const current=new URL(global.location.href);
    current.searchParams.delete('demo');current.searchParams.set('mode','live');
    global.history.replaceState(null,'',current.href);
  }
  function targetUrl(target){
    if(!allowed.has(target))throw new Error('Unsupported data mode');
    const url = new URL(global.location.href);
    url.searchParams.set('mode',target);
    for(const key of ['demo','research','dataset'])url.searchParams.delete(key);
    url.hash='';
    return url.href;
  }
  function display(target){
    if(!allowed.has(target))return;
    global.document.documentElement.dataset.dataMode=target;
    global.document.querySelectorAll('[data-data-mode]').forEach(button=>{
      button.setAttribute('aria-pressed',String(button.dataset.dataMode===target));
    });
  }
  function switchTo(target){
    if(!allowed.has(target))return;
    if(target===mode)return;
    if(global.parent && global.parent!==global){
      const origin=global.location.ancestorOrigins?.[0];
      const connectionId=new URLSearchParams(global.location.search).get('panel');
      if(/^chrome-extension:\/\/[a-p]{32}$/.test(origin||'') && connectionId){
        global.parent.postMessage({type:'jilian:data-mode-switch',protocol:1,
          connection_id:connectionId,mode:target},origin);
        return;
      }
    }
    global.location.assign(targetUrl(target));
  }
  if(mode && typeof global.fetch==='function'){
    const original=global.fetch.bind(global);
    global.fetch=(input,init)=>{
      const raw=typeof input==='string'?input:input?.url;
      let url;
      try{url=new URL(raw,global.location.href);}catch{return original(input,init);}
      if(url.origin!==global.location.origin||!url.pathname.startsWith('/assistant/'))return original(input,init);
      const headers=new Headers(typeof Request!=='undefined'&&input instanceof Request?input.headers:undefined);
      new Headers(init?.headers).forEach((value,key)=>headers.set(key,value));
      headers.set('X-Jilian-Data-Mode',mode);
      return original(input,{...init,headers});
    };
  }
  global.JilianDataMode={mode,targetUrl,display,switchTo};
  if(typeof module!=='undefined')module.exports={targetUrlFor:(url,target)=>{
    if(!allowed.has(target))throw new Error('Unsupported data mode');
    const next=new URL(url);next.searchParams.set('mode',target);
    for(const key of ['demo','research','dataset'])next.searchParams.delete(key);
    next.hash='';return next.href;
  }};
  if(global.document?.addEventListener)global.document.addEventListener('DOMContentLoaded',()=>{
    global.document.querySelectorAll('[data-data-mode]').forEach(button=>{
      button.addEventListener('click',()=>switchTo(button.dataset.dataMode));
    });
    display(mode);
  });
})(typeof window!=='undefined'?window:globalThis);
