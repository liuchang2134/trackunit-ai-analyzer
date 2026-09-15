/* Local discovery helpers; no provider calls and no health-score inference. */
const DeviceFinder = (() => {
  const normalize = value => String(value ?? '').normalize('NFKC').toLocaleLowerCase().trim();
  const isReal = item => ['trackunit_cache','imported_user_supplied'].includes(item.source);
  const needsAttention = item => ['unresolved','conflicting'].includes(item.fault_summary?.state);
  const priority = item => item.fault_summary?.conflicting_codes ? 5 :
    ({critical:4,high:3,medium:2,low:1}[item.fault_summary?.highest_severity] || 0);
  const time = item => Date.parse(item.fault_summary?.latest_record_at) || 0;
  const sourceLabel = item => item.source==='imported_synthetic'?'模拟片段':
    item.source==='mock'?'示例设备':item.source==='imported_user_supplied'?'导入实测 · 未验证':'车联网缓存';
  function faultLabel(summary) {
    if(!summary || summary.state==='unavailable')return '故障资料不可读';
    if(summary.state==='no_records')return '未载入故障记录';
    if(summary.state==='resolved_records')return '仅有已解决记录';
    const severity={critical:'严重',high:'高',medium:'中',low:'低'}[summary.highest_severity];
    const parts=[];
    if(summary.conflicting_codes)parts.push(`${summary.conflicting_codes} 个故障码状态待核对`);
    if(summary.unresolved_codes)parts.push(`${summary.unresolved_codes} 个故障码未解决${severity?' · 最高级别 '+severity:''}`);
    return parts.join('；');
  }
  function filter(devices, {query='',source='all',attention=false,sort='priority',platformId=null}={}) {
    const words=normalize(query).split(/\s+/).filter(Boolean);
    return devices.filter(item=>{
      if(platformId!==null && (!/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/.test(platformId) ||
          !isReal(item) || item.machine_id!==platformId))return false;
      if(source==='real'&&!isReal(item) || source==='simulation'&&isReal(item))return false;
      if(attention&&!needsAttention(item))return false;
      const text=normalize([item.model,item.machine_id,item.serial_number,item.equipment_id,item.machine_type,
        item.dataset_name,item.dataset_id].join(' '));
      return words.every(word=>text.includes(word));
    }).sort((a,b)=>{
      const name=normalize(a.model+' '+a.serial_number).localeCompare(normalize(b.model+' '+b.serial_number),'zh-CN');
      const order=sort==='name'?name:sort==='recent'?time(b)-time(a):priority(b)-priority(a)||time(b)-time(a);
      return order || name || a.selection_id.localeCompare(b.selection_id);
    });
  }
  return {filter,faultLabel,sourceLabel,needsAttention};
})();
if(typeof module!=='undefined')module.exports=DeviceFinder;

if(typeof document!=='undefined') {
  let finderPage=0;
  const pageSize=20;
  const platformId=()=>location.hash.startsWith('#trackunit-asset=')?location.hash.slice('#trackunit-asset='.length):null;
  function renderFinder() {
    const all=DeviceFinder.filter(machines,{platformId:platformId()});
    const result=DeviceFinder.filter(machines,{query:$('finder-search').value,source:$('finder-source').value,
      attention:$('finder-attention').checked,sort:$('finder-sort').value,platformId:platformId()});
    finderPage=Math.min(finderPage,Math.max(0,Math.ceil(result.length/pageSize)-1));
    const start=finderPage*pageSize,rows=result.slice(start,start+pageSize);
    $('finder-count').textContent=`找到 ${result.length} / ${all.length} 个数据版本${result.length>pageSize?` · 显示 ${start+1}—${start+rows.length}`:''}`;
    $('finder-scope').textContent=platformId()!==null?'仅显示当前平台设备的实测数据版本。':'范围：本机已载入的设备与数据版本。';
    $('finder-warnings').textContent=deviceIndexWarnings.join(' ');
    $('finder-warnings').hidden=!deviceIndexWarnings.length;
    $('finder-empty').hidden=!!result.length;
    $('finder-empty').textContent=all.length?'没有匹配结果。可清除筛选后重新查找。':
      platformId()!==null?'当前平台设备没有可用的本地实测版本。请先同步或导入对应设备；不会选择其他设备替代。':'还没有可用设备。请先同步或导入数据。';
    const body=$('finder-results');body.replaceChildren();
    for(const item of rows) {
      const row=document.createElement('li');row.className='finder-result';
      row.dataset.current=String(item.selection_id===$('machine').value);
      const identity=document.createElement('div'),title=document.createElement('strong'),serial=document.createElement('span');
      title.textContent=item.model || '未知机型';serial.textContent=item.serial_number || item.machine_id;
      identity.append(title,serial);
      const source=document.createElement('span');source.className='finder-source-label';source.textContent=DeviceFinder.sourceLabel(item);identity.append(source);
      const version=document.createElement('p');version.className='muted';
      version.textContent=item.dataset_id?`${item.dataset_name} · 版本 ${item.dataset_id.slice(0,8)} · ${item.sample_count} 条采样`:'当前缓存版本';identity.append(version);
      const evidence=document.createElement('div'),state=document.createElement('span'),date=document.createElement('p');
      state.className='finder-fault-label';state.dataset.attention=String(DeviceFinder.needsAttention(item));
      state.textContent=DeviceFinder.faultLabel(item.fault_summary);
      date.className='muted';date.textContent=item.fault_summary?.latest_record_at?'末条故障记录：'+displayDate(item.fault_summary.latest_record_at):'没有可显示的故障记录时间';
      evidence.append(state,date);
      const choose=document.createElement('button');choose.type='button';choose.className='quiet';
      choose.textContent=item.selection_id===$('machine').value?'当前版本':'查看设备';
      choose.setAttribute('aria-label',`${choose.textContent}：${item.model} ${item.serial_number}${item.dataset_id?' 版本 '+item.dataset_id.slice(0,8):' 当前缓存'}`);
      choose.onclick=()=>{
        if($('machine').disabled || !DeviceFinder.filter(machines,{platformId:platformId()}).some(m=>m.selection_id===item.selection_id))return;
        if(![...$('machine').options].some(option=>option.value===item.selection_id))return;
        const changed=$('machine').value!==item.selection_id;
        $('machine').value=item.selection_id;
        if(changed)selectMachine();
        $('device-finder').close('selected');setView('work');$('machine').focus();
      };
      row.append(identity,evidence,choose);body.append(row);
    }
    $('finder-pagination').hidden=result.length<=pageSize;
    $('finder-prev').disabled=finderPage===0;
    $('finder-next').disabled=start+pageSize>=result.length;
    $('finder-page').textContent=`第 ${finderPage+1} / ${Math.max(1,Math.ceil(result.length/pageSize))} 页`;
  }
  window.updateDeviceFinder=()=>{
    const item=selected(),summary=item?.fault_summary;
    $('device-fault-summary').textContent=item?DeviceFinder.faultLabel(summary)+' · 仅据已载入记录':'';
    $('finder-open').disabled=$('machine').disabled;
    $('device-faults-jump').hidden=!summary?.valid_records;
    $('device-faults-jump').disabled=typeof overview==='undefined'||!overview||overview.machine_id!==item?.machine_id||
      (overview.dataset_id||null)!==(item?.dataset_id||null);
    if($('device-finder').open)renderFinder();
  };
  $('finder-open').onclick=()=>{
    if($('machine').disabled)return;
    finderPage=0;renderFinder();$('device-finder').returnValue='';$('device-finder').showModal();$('finder-search').focus();
  };
  $('finder-close').onclick=()=>$('device-finder').close();
  $('device-finder').addEventListener('close',()=>($('device-finder').returnValue==='selected'?$('machine'):$('finder-open')).focus());
  const filterChanged=()=>{finderPage=0;renderFinder();};
  $('finder-search').oninput=filterChanged;
  for(const id of ['finder-source','finder-sort','finder-attention'])$(id).onchange=filterChanged;
  $('finder-clear').onclick=()=>{
    $('finder-search').value='';$('finder-source').value='all';$('finder-attention').checked=false;
    $('finder-sort').value='priority';filterChanged();$('finder-search').focus();
  };
  for(const [id,delta] of [['finder-prev',-1],['finder-next',1]])$(id).onclick=()=>{
    finderPage+=delta;renderFinder();$('finder-count').focus();
  };
  $('device-faults-jump').onclick=()=>{
    setView('work');$('overview-fault-title').scrollIntoView({block:'start'});$('overview-fault-title').focus();
  };
  updateDeviceFinder();
}
