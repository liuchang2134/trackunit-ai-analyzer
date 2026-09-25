/* A same-device bridge for the explicitly requested Advanced Sensors CSV export. */
(function(root) {
  function create({chrome,frame,current,window:host=window,page=TrackunitSensorPage}) {
    let active=null,disposed=false;
    function validateCapture(capture,job) {
      if(capture?.source!=='trackunit_csv_export' || ![1,2].includes(capture.schema_version) ||
         capture.asset_id!==job.asset_id || capture.page_url!==job.page_url ||
         typeof capture.captured_at!=='string' || !Number.isFinite(Date.parse(capture.captured_at)))throw new Error('invalid_result');
      const base={schema_version:capture.schema_version,source:'trackunit_csv_export',asset_id:job.asset_id,
        page_url:job.page_url,captured_at:capture.captured_at};
      if(capture.schema_version===1) {
        const checked=page.validateCSV(capture.csv_text);if(!checked.valid)throw new Error('invalid_csv');
        return {...base,csv_text:capture.csv_text,rows:checked.rows,channels:checked.channels};
      }
      if(!Array.isArray(capture.exports) || !capture.exports.length || capture.exports.length>32)throw new Error('invalid_result');
      let bytes=0;const ids=new Set();
      const exports=capture.exports.map(item=>{
        const checked=page.validateCSV(item?.csv_text);if(!checked.valid)throw new Error('invalid_csv');
        const size=new TextEncoder().encode(item.csv_text).length;bytes+=size;
        if(size>3000000 || checked.rows>20000 || bytes>24000000)throw new Error('total_size');
        const units={},channel_metadata={},sensors=[];
        for(const header of checked.channels) {
          const channel=page.channelIdentity(header),id=channel.id,key=channel.key,label=channel.name;
          if(ids.has(id))throw new Error('duplicate_channel');ids.add(id);
          const meta=item.channel_metadata?.[key],unit=meta?.unit||item.units?.[key]||'';
          if(typeof unit!=='string' || unit.length>24 || /[\r\n\u0000-\u001f]/.test(unit) ||
             meta?.label && meta.label!==label || meta?.kind && !['continuous','state','code','counter'].includes(meta.kind))
            throw new Error('invalid_result');
          if(unit)units[key]=unit;
          channel_metadata[key]={label,unit,kind:meta?.kind==='code'?'code':checked.text_channels?.includes(header)?'state':meta?.kind||'continuous'};
          sensors.push({name:label,unit,channel:id});
        }
        return {csv_text:item.csv_text,rows:checked.rows,channels:checked.channels,units,channel_metadata,sensors};
      });
      if(ids.size>96)throw new Error('total_size');
      const coverage=capture.collection;
      if(!coverage || !Number.isInteger(coverage.discovered_sensors) || coverage.discovered_sensors<ids.size ||
         coverage.discovered_sensors>96 || coverage.exported_sensors!==ids.size || !Array.isArray(coverage.failed_sensors) ||
         coverage.failed_sensors.length!==coverage.discovered_sensors-ids.size)throw new Error('invalid_result');
      const failed_sensors=coverage.failed_sensors.map(item=>{
        if(typeof item?.name!=='string' || !item.name || item.name.length>180 ||
           typeof item.reason!=='string' || !/^[a-z_]{1,40}$/.test(item.reason))throw new Error('invalid_result');
        return {name:item.name,reason:item.reason};
      });
      return {...base,exports,partial:failed_sensors.length>0,collection:{discovered_sensors:coverage.discovered_sensors,
        exported_sensors:ids.size,failed_sensors,complete:failed_sensors.length===0,
        selection_restored:coverage.selection_restored===true,
        range_label:typeof coverage.range_label==='string'?coverage.range_label.slice(0,512):''}};
    }
    const reply=(job,type,extra={})=>frame.contentWindow.postMessage({type,protocol:1,
      connection_id:job.connection_id,request_id:job.request_id,asset_id:job.asset_id,
      dataset_id:job.dataset_id,...extra},job.origin);
    const same=job=>{
      const now=current();
      return !disposed && active===job && !job.cancelled && now.state==='connected' && now.mode==='work' && !now.pageChanged &&
        ['connection_id','asset_id','dataset_id','generation','currentTabId','origin'].every(k=>now[k]===job[k]);
    };
    async function clean(job) {
      clearInterval(job.monitor);clearInterval(job.leaseTimer);
      if(job.cleaned)return;job.cleaned=true;
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
        reply(job,'jilian:sensor-series-progress',{message:'正在分批读取 Advanced Sensors 全部传感器，保持当前时间范围…'});
        job.started=true;
        job.monitor=setInterval(()=>{if(!same(job))void stop(job,'context_changed');},150);
        // pagehide cancellation is best effort when the panel is destroyed.
        // A page-owned lease also stops/restores the injected batch if its
        // owner disappears before Chrome can deliver that cancellation.
        job.leaseTimer=setInterval(()=>{
          if(!same(job) || job.renewing)return;
          job.renewing=true;
          chrome.scripting.executeScript({target:{tabId:job.currentTabId},world:'MAIN',
            func:page.renewExport,args:[job.request_id]}).catch(()=>{}).finally(()=>{job.renewing=false;});
        },5000);
        const results=await chrome.scripting.executeScript({target:{tabId:job.currentTabId},world:'MAIN',
          func:page.observeExport,args:[{operation:'batch',request_id:job.request_id,asset_id:job.asset_id,timeout_ms:600000,
            owner_lease_ms:30000,auto_export:true}]});
        if(!same(job))return;
        const result=results?.length===1 && results[0]?.result;
        if(!result || result.request_id!==job.request_id || result.asset_id!==job.asset_id || result.page_url!==job.page_url)
          throw new Error('invalid_result');
        if(result.status!=='captured')throw new Error(result.reason||'read_failed');
        const capture=validateCapture(result.capture,job);
        const currentTab=await chrome.tabs.get(job.currentTabId);
        if(!same(job) || currentTab.status==='loading' || page.pageIdentity(currentTab.url)?.page_url!==job.page_url)return;
        reply(job,'jilian:sensor-series-result',{capture});
      }catch(error) {
        if(same(job)) {
          const reasons={wrong_page:'请先打开当前设备的 Insights → Advanced Sensors，选好传感器和时间范围。',
            timeout:'尚未收到 CSV 导出，请重新读取，并在图表菜单选择 Export CSV。',
            invalid_csv:'导出的文件不是可用的连续传感器 CSV，请检查所选通道和时间范围。',
            export_unavailable:'请在 Advanced Sensors 选择传感器和时间范围，等图表加载后重新读取。',
            sensor_table_unavailable:'未找到 Advanced Sensors 完整传感器表，请打开该页面后重试。',
            sensor_table_filtered:'请清除 Advanced Sensors 表格筛选，再读取全部传感器。',
            sensor_inventory_incomplete:'传感器表格尚未完整加载，本次没有修改传感器选择，请稍后重试。',
            range_changed:'读取期间时间范围发生变化，已停止本次读取，请按新的范围重试。',
            selection_unavailable:'传感器选择尚未就绪，请等页面加载后重试。',
            busy:'本页已有传感器读取进行中，请稍后重试。'};
          reply(job,'jilian:sensor-series-error',{reason:error?.message||'read_failed',
            message:reasons[error?.message]||'本次连续传感器读取未完成，请重试。'});
        }
      }finally{await clean(job);if(active===job)active=null;}
    }
    function onMessage(event) {
      if(disposed)return;
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
    async function dispose() {
      if(disposed)return;disposed=true;
      host.removeEventListener('message',onMessage);host.removeEventListener('pagehide',onLeave);
      if(active)await stop(active,'panel_closed');
    }
    const onLeave=()=>{void dispose();};
    host.addEventListener('message',onMessage);
    host.addEventListener('pagehide',onLeave);
    return {dispose,
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
