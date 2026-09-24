/* A same-device bridge for the explicitly requested Advanced Sensors CSV export. */
(function(root) {
  function create({chrome,frame,current,window:host=window,page=TrackunitSensorPage}) {
    let active=null;
    const reply=(job,type,extra={})=>frame.contentWindow.postMessage({type,protocol:1,
      connection_id:job.connection_id,request_id:job.request_id,asset_id:job.asset_id,
      dataset_id:job.dataset_id,...extra},job.origin);
    const same=job=>{
      const now=current();
      return active===job && !job.cancelled && now.state==='connected' && now.mode==='work' && !now.pageChanged &&
        ['connection_id','asset_id','dataset_id','generation','currentTabId','origin'].every(k=>now[k]===job[k]);
    };
    async function clean(job) {
      clearInterval(job.monitor);
      if(job.started)try{await chrome.scripting.executeScript({target:{tabId:job.currentTabId},world:'MAIN',
        func:page.cancelExport,args:[job.request_id]});}catch{}
    }
    async function stop(job,reason='cancelled') {
      if(job.cancelled)return;job.cancelled=true;job.reason=reason;
      await clean(job);
    }
    async function collect(job) {
      try {
        const [tab]=await chrome.tabs.query({active:true,currentWindow:true});
        if(!same(job))return;
        const found=page.pageIdentity(tab?.url);
        if(tab?.id!==job.currentTabId || tab.status==='loading' || found?.asset_id!==job.asset_id)
          throw new Error('wrong_page');
        job.page_url=found.page_url;
        reply(job,'jilian:sensor-series-progress',{message:'正在读取当前所选传感器和时间范围的连续记录…'});
        job.started=true;
        job.monitor=setInterval(()=>{if(!same(job))void stop(job,'context_changed');},150);
        const results=await chrome.scripting.executeScript({target:{tabId:job.currentTabId},world:'MAIN',
          func:page.observeExport,args:[{request_id:job.request_id,asset_id:job.asset_id,timeout_ms:60000,auto_export:true}]});
        if(!same(job))return;
        const result=results?.length===1 && results[0]?.result;
        if(!result || result.request_id!==job.request_id || result.asset_id!==job.asset_id || result.page_url!==job.page_url)
          throw new Error('invalid_result');
        if(result.status!=='captured')throw new Error(result.reason||'read_failed');
        const capture=result.capture,checked=page.validateCSV(capture?.csv_text);
        if(capture?.source!=='trackunit_csv_export' || capture.schema_version!==1 || capture.asset_id!==job.asset_id ||
           capture.page_url!==job.page_url || !checked.valid)throw new Error('invalid_csv');
        const currentTab=await chrome.tabs.get(job.currentTabId);
        if(!same(job) || currentTab.status==='loading' || page.pageIdentity(currentTab.url)?.page_url!==job.page_url)return;
        if(typeof capture.captured_at!=='string' || !Number.isFinite(Date.parse(capture.captured_at)))throw new Error('invalid_result');
        reply(job,'jilian:sensor-series-result',{capture:{schema_version:1,source:'trackunit_csv_export',
          asset_id:job.asset_id,page_url:job.page_url,captured_at:capture.captured_at,csv_text:capture.csv_text,
          rows:checked.rows,channels:checked.channels}});
      }catch(error) {
        if(same(job)) {
          const reasons={wrong_page:'请先打开当前设备的 Insights → Advanced Sensors，选好传感器和时间范围。',
            timeout:'尚未收到 CSV 导出，请重新读取，并在图表菜单选择 Export CSV。',
            invalid_csv:'导出的文件不是可用的连续传感器 CSV，请检查所选通道和时间范围。',
            export_unavailable:'请在 Advanced Sensors 选择传感器和时间范围，等图表加载后重新读取。',
            busy:'本页已有传感器读取进行中，请稍后重试。'};
          reply(job,'jilian:sensor-series-error',{reason:error?.message||'read_failed',
            message:reasons[error?.message]||'本次连续传感器读取未完成，请重试。'});
        }
      }finally{await clean(job);if(active===job)active=null;}
    }
    function onMessage(event) {
      const data=event.data,scope=current();
      if(event.source!==frame.contentWindow || event.origin!==scope.origin || data?.protocol!==1 ||
         data.connection_id!==scope.connection_id)return;
      const ready=scope.state==='connected' && scope.mode==='work' && !scope.pageChanged && scope.matched &&
        typeof scope.asset_id==='string' && Number.isInteger(scope.currentTabId);
      if(data.type==='jilian:sensor-series-probe') {
        reply({...scope,request_id:data.request_id},'jilian:sensor-series-ready',{available:ready});return;
      }
      if(data.type==='jilian:sensor-series-cancel') {
        if(active?.request_id===data.request_id && data.asset_id===active.asset_id && data.dataset_id===active.dataset_id)
          void stop(active);
        return;
      }
      if(data.type!=='jilian:sensor-series-start' || !ready || data.asset_id!==scope.asset_id ||
         data.dataset_id!==scope.dataset_id || !/^[a-f0-9]{32}$/.test(data.request_id||''))return;
      const job={...scope,request_id:data.request_id,cancelled:false,started:false};
      if(active){reply(job,'jilian:sensor-series-error',{reason:'busy',message:'已有连续传感器读取进行中。'});return;}
      active=job;void collect(job);
    }
    host.addEventListener('message',onMessage);
    return {dispose:async()=>{host.removeEventListener('message',onMessage);if(active)await stop(active);},
      cancel:()=>active?stop(active):Promise.resolve()};
  }
  const api={create};
  if(typeof module!=='undefined' && module.exports)module.exports=api;
  else {
    root.SensorSeriesBridge=api;
    if(typeof panelRequestScope==='function')api.create({chrome,frame,current:()=>({
      ...panelRequestScope(),state,pageChanged,currentTabId})});
  }
})(globalThis);
