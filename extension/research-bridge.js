/* Same-device bridge between the trusted workbench and rendered XGSS tabs.
   This path only collects local evidence; it does not invoke a cloud model. */
(() => {
  let active=null;
  const pending=new Map();
  const reply=(job,type,extra={})=>frame.contentWindow.postMessage({type,protocol:1,
    connection_id:job.connection,request_id:job.id,asset_id:job.asset,dataset_id:job.dataset,...extra},job.origin);
  function cancelled(job) {
    return active!==job || job.cancelled || state!=='connected' || mode!=='work' ||
      connectionId!==job.connection || assetId!==job.asset || !matchedSelection || matchedSelection.dataset_id!==job.dataset;
  }
  function stop(job) {
    job.cancelled=true;
    for(const [id,waiter] of pending) if(waiter.job===job) {clearTimeout(waiter.timer);pending.delete(id);waiter.reject(new Error('资料收集已停止。'));}
  }
  async function collect(job,data) {
    let tab;
    try {
      const url=new URL(data.url);
      if(!XGSSCatalog.isXGSS(url.href))throw new Error('资料地址不是 XGSS 官方页面。');
      if(cancelled(job))throw new Error('设备已切换。');
      tab=await chrome.tabs.create({url:url.href,active:false});
      // Bounded wait for page scripts to render, then inspect only the eligible frame.
      let target=null;
      for(let attempt=0;attempt<30;attempt++) {
        if(cancelled(job))throw new Error('资料收集已停止或设备已切换。');
        if(attempt%4===0)reply(job,'jilian:research-progress',{message:'正在等待同 VIN 图册的分类和资料加载…'});
        const current=await chrome.tabs.get(tab.id);
        const navigating=current.status==='loading' && current.pendingUrl ? current.pendingUrl : current.url;
        if(!XGSSCatalog.isXGSS(navigating))throw new Error('资料页已离开 XGSS，停止读取。');
        if(current.status==='complete') {
          await chrome.scripting.executeScript({target:{tabId:tab.id,allFrames:true},files:['xgss-catalog.js','xgss-research.js']});
          const snapshots=await chrome.scripting.executeScript({target:{tabId:tab.id,allFrames:true},
            func:terms=>XGSSResearch.inspect(terms),args:[data.terms]});
          const ready=snapshots.filter(s=>s.result?.status==='ready' && s.result.vin===data.vin);
          if(ready.length>1)throw new Error('资料页存在多个同 VIN 区域，请独立打开要读取的图册。');
          // VIN is rendered before the asynchronously loaded catalog tree/table.
          // Do not announce "no sources" merely because that header arrived first.
          if(ready.length===1 && (ready[0].result.capture || ready[0].result.targets?.length || ready[0].result.can_expand_root===true)){
            target={tabId:tab.id,frameIds:[ready[0].frameId]};break;
          }
        }
        await new Promise(resolve=>setTimeout(resolve,500));
      }
      if(!target)throw new Error('图册未在等待时间内显示同 VIN 的相关分类或资料，已保留标签页供查看。');
      const call=async(func,args)=>{
        if(cancelled(job))throw new Error('资料收集已停止。');
        const current=await chrome.tabs.get(tab.id);
        if(cancelled(job))throw new Error('资料收集已停止。');
        const navigating=current.status==='loading' && current.pendingUrl ? current.pendingUrl : current.url;
        if(!XGSSCatalog.isXGSS(navigating))throw new Error('资料页已离开 XGSS。');
        const results=await chrome.scripting.executeScript({target,func,args});
        if(cancelled(job))throw new Error('资料收集已停止。');
        return results[0]?.result;
      };
      const result=await XGSSResearchRunner.run({vin:data.vin,terms:data.terms},{
        cancelled:()=>cancelled(job),wait:ms=>new Promise(resolve=>setTimeout(resolve,ms)),
        inspect:terms=>call(terms=>XGSSResearch.inspect(terms),[terms]),
        select:(label,vin)=>call((label,vin)=>XGSSResearch.select(label,vin),[label,vin]),
        expandRoot:vin=>call(vin=>XGSSResearch.expandRoot(vin),[vin]),
        scrollTree:vin=>call(vin=>XGSSResearch.scrollTree(vin),[vin]),
        progress:message=>reply(job,'jilian:research-progress',{message}),
        save:async(capture,expected={})=>{
          reply(job,'jilian:research-progress',{message:'正在核对本页文字与图示…'});
          let illustrated;
          for(let attempt=0;attempt<3;attempt++){
            illustrated=await call(terms=>XGSSResearch.captureWithIllustration(terms),[data.terms]);
            if(illustrated?.status!=='loading'||illustrated.vin!==data.vin||attempt===2)break;
            reply(job,'jilian:research-progress',{message:'正在等待图示与本页资料同步…'});
            await new Promise(resolve=>setTimeout(resolve,350));
            if(cancelled(job))throw new Error('资料收集已停止。');
          }
          const changed=message=>Object.assign(new Error(message),{code:'capture_changed'});
          if(illustrated?.status==='loading'&&illustrated.vin===data.vin)
            throw changed('本页资料仍在更新，正在重新读取当前分类。');
          if(illustrated?.status!=='ready' || illustrated.vin!==data.vin || !illustrated.capture)
            throw new Error('资料已变化，请重新查找并提取当前分类。');
          if(expected.category_confirmed===true&&
            (illustrated.category_confirmed!==true||
             String(illustrated.category_label).trim().toLocaleLowerCase()!==String(expected.category_label).trim().toLocaleLowerCase()))
            throw new Error('图册分类已切换，请重新读取当前分类。');
          const {illustrations,...textCapture}=illustrated.capture;
          if(XGSSResearchRunner.captureSignature(textCapture)!==XGSSResearchRunner.captureSignature(capture))
            throw changed('图示与本次文字资料不一致，请重新读取当前分类。');
          if(cancelled(job))throw new Error('资料收集已停止。');
          if(illustrated.illustration_issue)reply(job,'jilian:research-progress',{message:illustrated.illustration_issue});
          return new Promise((resolve,reject)=>{
            const page_id=job.id+':'+(++job.page);
            const timer=setTimeout(()=>{pending.delete(page_id);reject(new Error('工作台未确认资料保存。'));},15000);
            pending.set(page_id,{job,resolve,reject,timer});
            reply(job,'jilian:research-page',{page_id,capture:illustrated.capture});
          });
        },
      });
      if(!cancelled(job))reply(job,'jilian:research-done',{result});
    } catch(error) {
      if(active===job)reply(job,'jilian:research-error',{message:error?.message?.slice(0,250)||'资料收集失败。'});
    } finally {stop(job);if(active===job)active=null;}
  }
  window.addEventListener('message',event=>{
    const data=event.data;
    if(event.source!==frame.contentWindow || event.origin!==localOrigin || data?.protocol!==1 || data.connection_id!==connectionId)return;
    if(data.type==='jilian:research-probe') {
      reply({connection:connectionId,id:data.request_id,asset:assetId,dataset:matchedSelection?.dataset_id,origin:localOrigin},'jilian:research-ready');return;
    }
    if(data.type==='jilian:research-ack') {
      const waiter=pending.get(data.page_id);
      if(!waiter || waiter.job.id!==data.request_id || cancelled(waiter.job))return;
      clearTimeout(waiter.timer);pending.delete(data.page_id);
      if(data.success)waiter.resolve();else waiter.reject(new Error('资料保存或设备核对未通过。'));
      return;
    }
    if(data.type==='jilian:research-cancel') {if(active?.id===data.request_id)stop(active);return;}
    if(data.type!=='jilian:research-start' || state!=='connected' || mode!=='work' || pageChanged || !matchedSelection ||
      data.asset_id!==assetId || data.dataset_id!==matchedSelection.dataset_id ||
      typeof data.request_id!=='string' || !/^[a-f0-9]{32}$/.test(data.request_id) || !/^[A-Z0-9]{8,32}$/.test(data.vin) ||
      !Array.isArray(data.terms) || !data.terms.length || data.terms.length>12 || data.terms.some(t=>typeof t!=='string'||t.length<2||t.length>40))return;
    if(active) {reply({connection:connectionId,id:data.request_id,asset:assetId,dataset:data.dataset_id,origin:localOrigin},'jilian:research-error',{message:'已有资料收集进行中，请先停止。'});return;}
    const job={id:data.request_id,asset:assetId,dataset:data.dataset_id,connection:connectionId,origin:localOrigin,page:0,cancelled:false};
    active=job;reply(job,'jilian:research-progress',{message:'正在打开同 VIN 图册并读取资料…'});collect(job,data);
  });
})();
