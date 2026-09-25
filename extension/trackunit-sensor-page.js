/* Reads only a CSV export created after the user starts this bounded operation.
   No requests, credentials, app state, chart internals or previous downloads. */
(function(root) {
  function sensorExportOperation(options) {
    'use strict';
    const MAX_BYTES=3000000, MAX_ROWS=20000, MAX_CHANNELS=96;
    function channelIdentity(header) {
      if(typeof header!=='string' || header.length>210)return null;
      let match=header.match(/^(.{1,180}?)\s*\(CAN (\d{1,10})\)$/);
      if(match)return {id:match[2],name:match[1].trim(),key:({'50278':'coolant_c','50281':'oil_pressure_kpa','50283':'engine_load_percent','50286':'engine_rpm'}[match[2]]||'can_'+match[2])};
      match=header.match(/^INPUT\s*([1-6])\s*\(INPUT([1-6])\)$/i);
      if(match && match[1]===match[2])return {id:'INPUT'+match[1],name:'INPUT'+match[1],key:'input_'+match[1]};
      return /^OUTPUT\s*1\s*\(OUTPUT1\)$/i.test(header)?{id:'OUTPUT1',name:'OUTPUT1',key:'output_1'}:null;
    }
    const normalizedName=name=>name.trim().replace(/\s+/g,' ').replace(/^input\s*([1-6])$/i,'INPUT$1').replace(/^output\s*1$/i,'OUTPUT1').toLowerCase();
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
         headers.slice(1).some(h=>!channelIdentity(h)) || new Set(headers.slice(1).map(h=>channelIdentity(h)?.id)).size!==headers.length-1)
        return {valid:false,reason:'header'};
      // Date/time and numeric values stay unmodified; timezone interpretation belongs to the local importer.
      const date=/^(?:\d{1,2}\/\d{1,2}\/\d{2,4},? \d{1,2}:\d{2}(?::\d{2})? (?:AM|PM) (?:EDT|EST|UTC|GMT)|\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2}))$/;
      let values=0;const textColumns=new Set();
      for(const sample of rows.slice(1)) {
        if(sample.length!==headers.length || !date.test(sample[0]))return {valid:false,reason:'sample'};
        for(let column=1;column<sample.length;column++) {
          const v=sample[column];
          if(v==='')continue;
          const numeric=/^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:e[+-]?\d+)?$/i.test(v);
          if(numeric){if(!Number.isFinite(Number(v)))return {valid:false,reason:'numeric'};}
          else {
            if(!/^[\p{L}\p{N}][\p{L}\p{N} _.:/+()*%#-]{0,239}$/u.test(v) || /^(?:nan|infinity|null|undefined)$/i.test(v))
              return {valid:false,reason:'numeric'};
            textColumns.add(column);
          }
          values++;
        }
      }
      return values?{valid:true,rows:rows.length-1,channels:headers.slice(1),text_channels:Array.from(textColumns).map(index=>headers[index])}:{valid:false,reason:'empty'};
    }
    if(options?.operation==='validate')return validateCSV(options.csv_text);
    if(options?.operation==='identity')return pageIdentity(options.page_url);
    if(options?.operation==='channel')return channelIdentity(options.header);
    // Each batch is selected through the public table controls and exported by Trackunit.
    // Virtualized rows must be discovered before changing any selection.
    async function collectAll() {
      const batchKey='__jilianSensorBatchV1',identity=pageIdentity(globalThis.location?.href);
      const requestId=options?.request_id,operationDeadline=Date.now()+Math.min(600000,Math.max(1000,options.timeout_ms||600000));
      const deadline=operationDeadline-15000; // Leave a bounded restoration budget inside the caller's watchdog.
      if(!/^[a-f0-9]{32}$/.test(requestId||'') || !identity || identity.asset_id!==options.asset_id)
        return {status:'error',reason:'wrong_page'};
      if(globalThis[batchKey] || globalThis.__jilianSensorExportObserverV1)return {status:'error',reason:'busy'};
      let cancelled=false,changed=false,inventory=[],scrollTop=0,table,scroller,scope,initialRange='',restore=false;
      const leaseMs=Number.isFinite(options.owner_lease_ms)?Math.max(5000,Math.min(30000,options.owner_lease_ms)):0;
      let leaseUntil=Date.now()+leaseMs;
      const exports=[],failed=[],readIndexes=new Set(),readChannels=new Set(),knownSelected=new Set();let totalBytes=0;
      const operation={request_id:requestId,cancel:()=>{cancelled=true;const observer=globalThis.__jilianSensorExportObserverV1;
        if(observer?.request_id===requestId)observer.cancel();},
        owned:()=>!cancelled && (!leaseMs || Date.now()<leaseUntil),
        renew:()=>{if(!operation.owned())return false;leaseUntil=Date.now()+leaseMs;return true;}};
      globalThis[batchKey]=operation;
      const error=reason=>{throw new Error(reason);};
      const sameContext=()=>{
        const now=pageIdentity(globalThis.location?.href);
        if(!now || now.page_url!==identity.page_url || now.asset_id!==identity.asset_id){changed=true;error('page_changed');}
        if(initialRange && rangeSignature()!==initialRange){changed=true;error('range_changed');}
        if(table) {
          let currentTable;
          try {currentTable=locateTable().table;}catch {changed=true;error('table_changed');}
          if(!table.isConnected || currentTable!==table){changed=true;error('table_changed');}
        }
      };
      const alive=()=>{
        sameContext();
        if(!operation.owned())cancelled=true;
        if(cancelled)error('cancelled');
        if(Date.now()>deadline)error('timeout');
      };
      const wait=async(ms=110)=>{await new Promise(resolve=>setTimeout(resolve,ms));alive();};
      function rangeSignature() {
        // Date range is user-visible text only. The complete URL is kept in memory, never forwarded.
        const labels=Array.from(document.querySelectorAll('button')).filter(el=>{
          const testId=el.getAttribute('data-testid')||'';
          const label=el.getAttribute('aria-label')||'',text=(el.textContent||'').trim();
          return /date.?range|date.?picker|time.?range/i.test(testId+' '+label) ||
            /\d{4}年\d{1,2}月\d{1,2}日\s*[-–—]\s*\d{4}年\d{1,2}月\d{1,2}日/.test(text) ||
            (text.length<160 && /\d/.test(text) && /\s[-–—]\s/.test(text) &&
              /(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)|\d{1,4}[/.]\d{1,2}[/.]\d{1,4}/i.test(text));
        }).map(el=>(el.textContent||'').trim());
        return globalThis.location.href+'|'+labels.join('|');
      }
      function locateTable() {
        const heading=Array.from(document.querySelectorAll('h3')).filter(el=>el.textContent.trim()==='Advanced Sensors');
        if(heading.length!==1)error('sensor_table_unavailable');
        let container=heading[0].parentElement;
        for(let depth=0;container && depth<7;depth++,container=container.parentElement) {
          const tables=container.querySelectorAll('table');
          if(tables.length===1) {
            const count=(container.textContent||'').match(/Showing\s+(\d+)\s+of\s+(\d+)/i);
            if(count)return {scope:container,table:tables[0],total:Number(count[2]),shown:Number(count[1])};
          }
        }
        error('sensor_table_unavailable');
      }
      function rows() {
        return Array.from(table.querySelectorAll('tbody tr')).map(row=>{
          const checkbox=row.querySelector('input[type="checkbox"][aria-label="rowSelector"]'),cells=row.querySelectorAll('td');
          if(!checkbox || cells.length<5)return null;
          const raw=row.getAttribute('data-index') ?? (row.getAttribute('data-testid')||'').match(/table-body-row-(\d+)$/)?.[1];
          const index=Number(raw),name=(cells[2].textContent||'').trim(),rawUnit=(cells[4].textContent||'').trim();
          if(raw===undefined || raw===null || !Number.isInteger(index) || index<0 || !name || name.length>180)return null;
          return {index,name,unit:['-','–','—'].includes(rawUnit)?'':rawUnit,checked:checkbox.checked,checkbox,row};
        }).filter(Boolean);
      }
      function remember(map) {
        for(const row of rows()) {
          const old=map.get(row.index);
          if(old && (old.name!==row.name || old.unit!==row.unit || old.checked!==row.checked))error('table_changed');
          map.set(row.index,{index:row.index,name:row.name,unit:row.unit,checked:row.checked});
        }
      }
      async function findRow(sensor,restoring=false) {
        const check=()=>{sameContext();if(restoring){if(Date.now()>operationDeadline)error('restore_timeout');}else alive();};
        check();
        let found=rows().find(row=>row.index===sensor.index);
        if(!found){
          check();
          scroller.scrollTop=Math.max(0,Math.min(scroller.scrollHeight-scroller.clientHeight,
            (sensor.index/(inventory.length||1))*scroller.scrollHeight));
          if(restoring)await new Promise(resolve=>setTimeout(resolve,110));else await wait();
          check();
          found=rows().find(row=>row.index===sensor.index);
        }
        check();
        if(!found || found.name!==sensor.name || found.unit!==sensor.unit)error('table_changed');
        return found;
      }
      async function select(sensor,checked,restoring=false) {
        if(restoring)sameContext();else alive();
        const found=await findRow(sensor,restoring);
        if(found.checkbox.checked)knownSelected.add(sensor.index);else knownSelected.delete(sensor.index);
        if(found.checkbox.checked===checked)return;
        if(found.checkbox.disabled || found.checkbox.getAttribute('aria-disabled')==='true')error('selection_unavailable');
        sameContext();
        found.checkbox.click();
        if(checked)knownSelected.add(sensor.index);else knownSelected.delete(sensor.index);
        sameContext();
        if(restoring)await new Promise(resolve=>setTimeout(resolve,90));else await wait(90);
        sameContext();
        if((await findRow(sensor,restoring)).checkbox.checked!==checked)error('selection_unavailable');
      }
      async function awaitExportControl(batchDeadline) {
        let idleSince=null;
        const visible=element=>{
          if(element.closest?.('[hidden],[inert]'))return false;
          const rect=element.getBoundingClientRect(),style=getComputedStyle(element);
          return rect.width>0 && rect.height>0 && style.display!=='none' && style.visibility!=='hidden';
        };
        while(Date.now()<batchDeadline) {
          alive();
          const loading=Array.from(document.querySelectorAll('[data-testid="insights-page-chart-loading"]')).some(visible);
          if(loading){idleSince=null;await wait(300);continue;}
          if(idleSince===null)idleSince=Date.now();
          const buttons=Array.from(document.querySelectorAll('button[data-testid="export-button"]'))
            .filter(button=>button.textContent.trim()==='Export' && visible(button));
          if(buttons.length>1)return 'export_unavailable';
          const idleFor=Date.now()-idleSince;
          if(buttons.length===1 && !buttons[0].disabled && buttons[0].getAttribute('aria-disabled')!=='true') {
            if(idleFor>=600)return null;
          } else if(idleFor>=2500)return buttons.length===1?'not_exportable':'export_unavailable';
          await wait(300);
        }
        return 'timeout';
      }
      function enrich(capture,batch) {
        const units={},channel_metadata={},sensors=[],matched_indexes=[];
        for(const header of capture.channels) {
          const channel=channelIdentity(header),matches=batch.filter(item=>normalizedName(item.name)===normalizedName(channel.name));
          if(!matches.length)error('wrong_channels');
          const sensor=matches.find(item=>!matched_indexes.includes(item.index));
          if(!sensor)error('wrong_channels');
          matched_indexes.push(sensor.index);
          const unit=matches.every(item=>item.unit===sensor.unit) && sensor.unit.length<=24?sensor.unit:'';
          const id=channel.id,key=channel.key,label=channel.name;
          const kind=/code|DTC|DM1|DM2|diagnostic|fault information|engine.*make|serial|identifier|故障码/i.test(label)?'code':
            /status|state|lamp|switch|gear information|^display\b|^input\s*[1-6]$|^output\s*1$|状态|指示灯/i.test(label) || capture.text_channels?.includes(header)?'state':
            /total|cumulative|累计/i.test(label)?'counter':'continuous';
          if(unit)units[key]=unit;
          channel_metadata[key]={label,unit,kind};sensors.push({name:label,unit,channel:id,
            ...(matches.length===1?{table_index:sensor.index}:{})});
        }
        return {csv_text:capture.csv_text,rows:capture.rows,channels:capture.channels,units,channel_metadata,sensors,
          page_url:identity.page_url,captured_at:capture.captured_at,matched_indexes};
      }
      let failure=null;
      try {
        const located=locateTable();({table,scope}=located);scroller=table.parentElement;scrollTop=scroller.scrollTop;
        if(!Number.isInteger(located.total) || located.total<1 || located.total>96 || located.shown!==located.total)
          error('sensor_table_filtered');
        initialRange=rangeSignature();const map=new Map();remember(map);
        for(let position=0;position<=scroller.scrollHeight && map.size<located.total;position+=Math.max(100,scroller.clientHeight*.65)) {
          alive();scroller.scrollTop=position;await wait();remember(map);
          if(scroller.scrollTop+scroller.clientHeight>=scroller.scrollHeight-2)break;
        }
        scroller.scrollTop=Math.max(0,scroller.scrollHeight-scroller.clientHeight);await wait();remember(map);
        inventory=Array.from(map.values()).sort((a,b)=>a.index-b.index);
        if(inventory.length!==located.total || inventory.some((sensor,index)=>sensor.index!==index))error('sensor_inventory_incomplete');
        inventory.filter(sensor=>sensor.checked).forEach(sensor=>knownSelected.add(sensor.index));
        restore=true;
        for(const sensor of inventory.filter(sensor=>sensor.checked))await select(sensor,false);
        for(let start=0;start<inventory.length;start+=4) {
          alive();const batch=inventory.slice(start,start+4),batchDeadline=Math.min(deadline,Date.now()+60000);
          for(const sensor of batch)await select(sensor,true);
          await wait(900);
          let captureResult;
          for(let attempt=0;attempt<2;attempt++) {
            const unavailable=await awaitExportControl(batchDeadline);
            if(unavailable){captureResult={status:'error',reason:unavailable};break;}
            captureResult=await sensorExportOperation({request_id:requestId,asset_id:identity.asset_id,
              owned_batch_request_id:requestId,
              auto_export:true,timeout_ms:Math.max(1,batchDeadline-Date.now()),
              expected_names:batch.map(sensor=>sensor.name),excluded_channels:Array.from(readChannels)});
            if(captureResult.reason!=='wrong_channels')break;
            await wait(900);
          }
          alive();
          if(captureResult.status==='captured') {
            const item=enrich(captureResult.capture,batch);totalBytes+=new TextEncoder().encode(item.csv_text).length;
            if(totalBytes>24000000)error('total_size');
            const {matched_indexes,...exportItem}=item;exports.push(exportItem);
            matched_indexes.forEach(index=>readIndexes.add(index));
            batch.filter(sensor=>!matched_indexes.includes(sensor.index)).forEach(sensor=>
              failed.push({name:sensor.name,table_index:sensor.index,reason:'column_not_exported'}));
            item.sensors.forEach(sensor=>readChannels.add(sensor.channel));
          } else {
            if(['cancelled','page_changed','range_changed'].includes(captureResult.reason))error(captureResult.reason);
            failed.push(...batch.map(sensor=>({name:sensor.name,table_index:sensor.index,reason:captureResult.reason||'read_failed'})));
          }
          for(const sensor of batch)await select(sensor,false);
        }
      } catch(e) {failure=e.message||'read_failed';}
      finally {
        if(restore && !changed) {
          try {
            sameContext();
            for(const sensor of inventory.filter(sensor=>knownSelected.has(sensor.index) && !sensor.checked))await select(sensor,false,true);
            for(const sensor of inventory.filter(sensor=>sensor.checked))await select(sensor,true,true);
            sameContext();
            restore=true;
          } catch(e) {restore=false;if(changed)failure=e.message||'context_changed';}
        } else restore=false;
        if(scroller?.isConnected && !changed)try{sameContext();scroller.scrollTop=scrollTop;}catch(e){if(changed)failure=e.message||'context_changed';}
        if(globalThis[batchKey]===operation)delete globalThis[batchKey];
      }
      const base={request_id:requestId,asset_id:identity.asset_id,page_url:identity.page_url};
      if(cancelled || changed || ['cancelled','page_changed','range_changed'].includes(failure))
        return {...base,status:'cancelled',reason:failure||'cancelled'};
      if(!exports.length)return {...base,status:'error',reason:failure||failed[0]?.reason||'read_failed'};
      for(const sensor of inventory)if(!readIndexes.has(sensor.index) && !failed.some(item=>item.table_index===sensor.index))
        failed.push({name:sensor.name,table_index:sensor.index,reason:failure||'not_read'});
      return {...base,status:'captured',capture:{schema_version:2,source:'trackunit_csv_export',...base,
        captured_at:new Date().toISOString(),exports,partial:failed.length>0,
        collection:{discovered_sensors:inventory.length,exported_sensors:readIndexes.size,failed_sensors:failed,
          complete:failed.length===0,selection_restored:restore,range_label:initialRange.split('|').slice(1).join('|')}}};
    }
    if(options?.operation==='batch')return collectAll();
    const page=pageIdentity(globalThis.location?.href);
    const requestId=options?.request_id;
    if(!/^[a-f0-9]{32}$/.test(requestId||'') || !page || page.asset_id!==options.asset_id)
      return Promise.resolve({status:'error',reason:'wrong_page'});
    const key='__jilianSensorExportObserverV1';
    if(globalThis[key])return Promise.resolve({status:'error',reason:'busy'});
    const ttl=Number.isFinite(options.timeout_ms)?Math.max(1,Math.min(options.timeout_ms,60000)):60000;
    return new Promise(resolve=>{
      const originalCreate=URL.createObjectURL, originalClick=HTMLAnchorElement.prototype.click;
      const originalDispatch=HTMLAnchorElement.prototype.dispatchEvent;
      const dispatchDescriptor=Object.getOwnPropertyDescriptor(HTMLAnchorElement.prototype,'dispatchEvent');
      const urls=new Map();let done=false,reading=false,timeout,interval,exportStep=null,menuDeadline=0;
      const current=()=>{
        const now=pageIdentity(globalThis.location?.href);
        return now && now.asset_id===page.asset_id && now.page_url===page.page_url;
      };
      const owned=()=>!options.owned_batch_request_id ||
        globalThis.__jilianSensorBatchV1?.request_id===options.owned_batch_request_id && globalThis.__jilianSensorBatchV1.owned();
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
        if(!owned()){finish({status:'cancelled',reason:'cancelled'});return;}
        const filename=anchor.getAttribute('download')||'';
        if(!/^[^\r\n]{1,180}\.csv$/i.test(filename))return;
        const blob=urls.get(anchor.href);if(!blob)return;
        reading=true;
        try {
          const text=await blob.text();
          if(done)return;
          if(!current()){finish({status:'cancelled',reason:'page_changed'});return;}
          if(!owned()){finish({status:'cancelled',reason:'cancelled'});return;}
          const checked=validateCSV(text);
          if(!checked.valid){finish({status:'error',reason:'invalid_csv'});return;}
          if(Array.isArray(options.expected_names)) {
            const names=checked.channels.map(header=>normalizedName(channelIdentity(header).name));
            const remaining=new Map();options.expected_names.map(normalizedName)
              .forEach(name=>remaining.set(name,(remaining.get(name)||0)+1));
            const unexpected=names.some(name=>{const count=remaining.get(name)||0;if(count<=0)return true;remaining.set(name,count-1);return false;});
            if(unexpected) {
              finish({status:'error',reason:'wrong_channels'});return;
            }
          }
          if(Array.isArray(options.excluded_channels) && checked.channels.some(header=>
            options.excluded_channels.includes(channelIdentity(header).id))) {
            finish({status:'error',reason:'wrong_channels'});return;
          }
          finish({status:'captured',capture:{schema_version:1,source:'trackunit_csv_export',
            asset_id:page.asset_id,page_url:page.page_url,captured_at:new Date().toISOString(),
            csv_text:text,rows:checked.rows,channels:checked.channels,text_channels:checked.text_channels}});
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
        if(done || !current() || !owned())return;
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
        interval=setInterval(()=>{if(!current())onLeave();else if(!owned())controller.cancel();else advanceExport();},200);
        if(options.auto_export===true){exportStep='button';advanceExport();}
      }catch{finish({status:'error',reason:'unsupported'});}
    });
  }
  function cancelExport(requestId) {
    const batch=globalThis.__jilianSensorBatchV1;
    if(batch?.request_id===requestId){batch.cancel();return true;}
    const observer=globalThis.__jilianSensorExportObserverV1;
    if(observer?.request_id!==requestId)return false;
    observer.cancel();return true;
  }
  function renewExport(requestId) {
    const batch=globalThis.__jilianSensorBatchV1;
    return Boolean(batch?.request_id===requestId && typeof batch.renew==='function' && batch.renew());
  }
  const api={observeExport:sensorExportOperation,cancelExport,renewExport,
    validateCSV:csv_text=>sensorExportOperation({operation:'validate',csv_text}),
    channelIdentity:header=>sensorExportOperation({operation:'channel',header}),
    pageIdentity:page_url=>sensorExportOperation({operation:'identity',page_url})};
  if(typeof module!=='undefined' && module.exports)module.exports=api;
  else root.TrackunitSensorPage=api;
})(globalThis);
