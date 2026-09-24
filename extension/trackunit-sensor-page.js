/* Reads only a CSV export created after the user starts this bounded operation.
   No requests, credentials, app state, chart internals or previous downloads. */
(function(root) {
  function sensorExportOperation(options) {
    'use strict';
    const MAX_BYTES=4*1024*1024, MAX_ROWS=50000, MAX_CHANNELS=64;
    function pageIdentity(value) {
      try {
        const url=new URL(value);
        if(url.protocol!=='https:' || url.username || url.password || url.port ||
           !['new.manager.trackunit.com','manager.trackunit.com'].includes(url.hostname))return null;
        const match=url.pathname.match(/^\/assets\/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\/insights(?:\/[^?#]*)?\/?$/i);
        return match?{asset_id:match[1].toLowerCase(),page_url:url.origin+url.pathname}:null;
      }catch{return null;}
    }
    function validateCSV(text) {
      if(typeof text!=='string' || !text.length || text.length>MAX_BYTES || new TextEncoder().encode(text).length>MAX_BYTES)
        return {valid:false,reason:'size'};
      const rows=[],row=[];let value='',quoted=false;
      text=text.replace(/^\uFEFF/,'');
      for(let i=0;i<text.length;i++) {
        const ch=text[i];
        if(ch==='"') {
          if(quoted && text[i+1]==='"'){value+='"';i++;}
          else if(!quoted && value.length){return {valid:false,reason:'csv'};}
          else quoted=!quoted;
        }else if(!quoted && (ch===',' || ch==='\n' || ch==='\r')) {
          row.push(value.trim());value='';
          if(row.length>MAX_CHANNELS+1)return {valid:false,reason:'columns'};
          if(ch!==',') {
            if(ch==='\r' && text[i+1]==='\n')i++;
            if(row.some(Boolean))rows.push(row.splice(0));else row.length=0;
            if(rows.length>MAX_ROWS+1)return {valid:false,reason:'rows'};
          }
        }else value+=ch;
        if(value.length>512)return {valid:false,reason:'cell'};
      }
      if(quoted)return {valid:false,reason:'csv'};
      if(value.length || row.length){row.push(value.trim());if(row.some(Boolean))rows.push(row);}
      if(rows.length<3 || rows.length>MAX_ROWS+1)return {valid:false,reason:'rows'};
      const headers=rows[0];
      if(headers.length<2 || headers.length>MAX_CHANNELS+1 || headers[0]!=='Date and time' ||
         headers.slice(1).some(h=>!/^.{1,180}\(CAN \d{1,10}\)$/.test(h)) || new Set(headers).size!==headers.length)
        return {valid:false,reason:'header'};
      // Date/time and numeric values stay unmodified; timezone interpretation belongs to the local importer.
      const date=/^(?:\d{1,2}\/\d{1,2}\/\d{2,4},? \d{1,2}:\d{2}(?::\d{2})? (?:AM|PM) (?:EDT|EST|UTC|GMT)|\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2}))$/;
      let values=0;
      for(const sample of rows.slice(1)) {
        if(sample.length!==headers.length || !date.test(sample[0]))return {valid:false,reason:'sample'};
        for(const v of sample.slice(1)) {
          if(v==='')continue;
          if(!/^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:e[+-]?\d+)?$/i.test(v) || !Number.isFinite(Number(v)))
            return {valid:false,reason:'numeric'};
          values++;
        }
      }
      return values?{valid:true,rows:rows.length-1,channels:headers.slice(1)}:{valid:false,reason:'empty'};
    }
    if(options?.operation==='validate')return validateCSV(options.csv_text);
    if(options?.operation==='identity')return pageIdentity(options.page_url);
    const page=pageIdentity(globalThis.location?.href);
    const requestId=options?.request_id;
    if(!/^[a-f0-9]{32}$/.test(requestId||'') || !page || page.asset_id!==options.asset_id)
      return Promise.resolve({status:'error',reason:'wrong_page'});
    const key='__jilianSensorExportObserverV1';
    if(globalThis[key])return Promise.resolve({status:'error',reason:'busy'});
    const ttl=Number.isFinite(options.timeout_ms)?Math.max(1000,Math.min(options.timeout_ms,60000)):60000;
    return new Promise(resolve=>{
      const originalCreate=URL.createObjectURL, originalClick=HTMLAnchorElement.prototype.click;
      const originalDispatch=HTMLAnchorElement.prototype.dispatchEvent;
      const dispatchDescriptor=Object.getOwnPropertyDescriptor(HTMLAnchorElement.prototype,'dispatchEvent');
      const urls=new Map();let done=false,reading=false,timeout,interval,exportStep=null,menuDeadline=0;
      const current=()=>{
        const now=pageIdentity(globalThis.location?.href);
        return now && now.asset_id===page.asset_id && now.page_url===page.page_url;
      };
      const finish=result=>{
        if(done)return;done=true;clearTimeout(timeout);clearInterval(interval);
        if(URL.createObjectURL===create)URL.createObjectURL=originalCreate;
        if(HTMLAnchorElement.prototype.click===click)HTMLAnchorElement.prototype.click=originalClick;
        if(HTMLAnchorElement.prototype.dispatchEvent===dispatch) {
          if(dispatchDescriptor)Object.defineProperty(HTMLAnchorElement.prototype,'dispatchEvent',dispatchDescriptor);
          else delete HTMLAnchorElement.prototype.dispatchEvent;
        }
        document.removeEventListener('click',onClick,true);globalThis.removeEventListener?.('pagehide',onLeave);
        urls.clear();if(globalThis[key]===controller)delete globalThis[key];
        resolve({...result,request_id:requestId,asset_id:page.asset_id,page_url:page.page_url});
      };
      const onLeave=()=>finish({status:'cancelled',reason:'page_changed'});
      const controller={request_id:requestId,cancel:()=>finish({status:'cancelled',reason:'cancelled'})};
      function create(blob) {
        const url=Reflect.apply(originalCreate,this,arguments);
        const mime=typeof blob?.type==='string'?blob.type.split(';')[0].trim().toLowerCase():null;
        if(!done && current() && blob instanceof Blob && blob.size>0 && blob.size<=MAX_BYTES &&
           ['', 'text/csv','application/csv','text/plain','application/vnd.ms-excel','application/octet-stream'].includes(mime) && urls.size<8)
          urls.set(url,blob);
        return url;
      }
      async function consider(anchor) {
        if(done || reading || !current() || !(anchor instanceof HTMLAnchorElement))return;
        const filename=anchor.getAttribute('download')||'';
        if(!/^[^\r\n]{1,180}\.csv$/i.test(filename))return;
        const blob=urls.get(anchor.href);if(!blob)return;
        reading=true;
        try {
          const text=await blob.text();
          if(done)return;
          if(!current()){finish({status:'cancelled',reason:'page_changed'});return;}
          const checked=validateCSV(text);
          if(!checked.valid){finish({status:'error',reason:'invalid_csv'});return;}
          finish({status:'captured',capture:{schema_version:1,source:'trackunit_csv_export',
            asset_id:page.asset_id,page_url:page.page_url,captured_at:new Date().toISOString(),
            csv_text:text,rows:checked.rows,channels:checked.channels}});
        }catch{finish({status:'error',reason:'read_failed'});}
      }
      function click() {void consider(this);return Reflect.apply(originalClick,this,arguments);}
      function dispatch(event) {
        if(event?.type==='click')void consider(this);
        return Reflect.apply(originalDispatch,this,arguments);
      }
      function onClick(event) {const anchor=event.target?.closest?.('a[download]');if(anchor)void consider(anchor);}
      function visible(element) {
        if(!element || element.closest?.('[hidden],[inert]'))return false;
        const rect=element.getBoundingClientRect(),style=getComputedStyle(element);
        return rect.width>0 && rect.height>0 && style.display!=='none' && style.visibility!=='hidden';
      }
      function advanceExport() {
        if(done || !current())return;
        if(exportStep==='button') {
          const buttons=Array.from(document.querySelectorAll('button[data-testid="export-button"]'))
            .filter(b=>visible(b) && !b.disabled && b.getAttribute('aria-disabled')!=='true' && b.textContent.trim()==='Export');
          if(buttons.length!==1){finish({status:'error',reason:'export_unavailable'});return;}
          exportStep='menu';menuDeadline=Date.now()+5000;buttons[0].click();
        }
        if(exportStep==='menu') {
          const items=Array.from(document.querySelectorAll('[role="menuitem"]'))
            .filter(item=>visible(item) && item.getAttribute('aria-disabled')!=='true' && item.textContent.trim()==='CSV');
          if(items.length===1){exportStep='waiting';items[0].click();}
          else if(items.length>1 || Date.now()>menuDeadline)finish({status:'error',reason:'export_unavailable'});
        }
      }
      globalThis[key]=controller;
      try {
        URL.createObjectURL=create;HTMLAnchorElement.prototype.click=click;
        if(typeof originalDispatch==='function')HTMLAnchorElement.prototype.dispatchEvent=dispatch;
        document.addEventListener('click',onClick,true);globalThis.addEventListener?.('pagehide',onLeave);
        timeout=setTimeout(()=>finish({status:'error',reason:'timeout'}),ttl);
        interval=setInterval(()=>{if(!current())onLeave();else advanceExport();},200);
        if(options.auto_export===true){exportStep='button';advanceExport();}
      }catch{finish({status:'error',reason:'unsupported'});}
    });
  }
  function cancelExport(requestId) {
    const observer=globalThis.__jilianSensorExportObserverV1;
    if(observer?.request_id!==requestId)return false;
    observer.cancel();return true;
  }
  const api={observeExport:sensorExportOperation,cancelExport,
    validateCSV:csv_text=>sensorExportOperation({operation:'validate',csv_text}),
    pageIdentity:page_url=>sensorExportOperation({operation:'identity',page_url})};
  if(typeof module!=='undefined' && module.exports)module.exports=api;
  else root.TrackunitSensorPage=api;
})(globalThis);
