/* Pure selection acknowledgement; no VIN, telemetry, report or credentials leave the frame. */
const PlatformContext=(()=>{
  const uuid=/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
  function asset(hash){const value=hash.startsWith('#trackunit-asset=')?hash.slice('#trackunit-asset='.length):'';return uuid.test(value)?value:null;}
  function initialDemo(search,hash){return !hash.startsWith('#trackunit-asset=')&&new URLSearchParams(search).get('demo')==='1';}
  function equipmentHint(value){
    if(value==null||value==='')return null;
    if(typeof value!=='string'||value.length>100||!/^[A-Za-z0-9._ -]+$/.test(value))return undefined;
    return value.trim()||null;
  }
  function candidates(machines,source,id){
    return typeof id==='string'&&uuid.test(id)?machines.filter(m=>m.machine_id===id&&(m.dataset_id?m.provenance==='user_supplied':source==='trackunit_cache')):[];
  }
  function sampleTime(machine,nowMs){
    // An explicit null means no usable telemetry. Only older indexes fall back to last_seen_at.
    const value=Object.hasOwn(machine,'latest_telemetry_at')?machine.latest_telemetry_at:machine.last_seen_at;
    if(typeof value!=='string')return -Infinity;
    const parts=/^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.\d+)?(?:Z|[+-](\d{2}):(\d{2}))$/.exec(value);
    if(!parts)return -Infinity;
    const [year,month,day,hour,minute,second]=parts.slice(1,7).map(Number),offsetHour=Number(parts[7]||0),offsetMinute=Number(parts[8]||0);
    const days=[31,year%4===0&&(year%100!==0||year%400===0)?29:28,31,30,31,30,31,31,30,31,30,31];
    if(month<1||month>12||day<1||day>days[month-1]||hour>23||minute>59||second>59||offsetHour>23||offsetMinute>59)return -Infinity;
    const result=Date.parse(value);
    return Number.isFinite(result)&&result<=nowMs?result:-Infinity;
  }
  /**
   * Choose one real-data version for the exact platform UUID without changing the input.
   * previousSelection is a selection_id string; any still-valid explicit choice is retained.
   * Returns {selected: original machine or null, reason, tied: equally dated candidate count}.
   * Timestamp ties use known sample counts, then ordinal selection_id order. A default is
   * a navigation choice, not a claim that this version has the fullest or best evidence.
   */
  function selectDefault(machines,source,assetId,previousSelection,nowMs=Date.now()){
    const matches=candidates(machines,source,assetId);
    if(!matches.length)return {selected:null,reason:'no_match',tied:0};
    const dated=matches.map(machine=>({machine,time:sampleTime(machine,nowMs),
      count:typeof machine.sample_count==='number'&&Number.isFinite(machine.sample_count)&&machine.sample_count>=0?machine.sample_count:-1}));
    const previous=dated.find(item=>item.machine.selection_id===previousSelection);
    if(previous)return {selected:previous.machine,reason:'retained',tied:dated.filter(item=>item.time===previous.time).length};
    dated.sort((a,b)=>a.time!==b.time?(a.time>b.time?-1:1):a.count!==b.count?(a.count>b.count?-1:1):
      a.machine.selection_id<b.machine.selection_id?-1:a.machine.selection_id>b.machine.selection_id?1:0);
    const chosen=dated[0],tied=dated.filter(item=>item.time===chosen.time).length;
    return {selected:chosen.machine,reason:chosen.time===-Infinity?'undated_default':tied>1?'equal_latest_sample':'latest_sample',tied};
  }
  function snapshot({hash,machines,source,selectionId,indexState,pending}){
    const id=asset(hash);if(!id)return null;
    const base={asset_id:id};
    if(pending)return {...base,state:'pending'};
    if(indexState!=='ready')return {...base,state:indexState==='error'?'unavailable':'loading'};
    const matches=candidates(machines,source,id);
    if(!matches.length)return {...base,state:'missing'};
    const selected=matches.find(m=>m.selection_id===selectionId);
    if(!selected)return {...base,state:'choose_version',available_versions:matches.length};
    return {...base,state:'matched',machine_id:selected.machine_id,selection_id:selected.selection_id,
      dataset_id:selected.dataset_id||null,source:selected.dataset_id?'imported_user_supplied':'trackunit_cache'};
  }
  return {asset,candidates,selectDefault,snapshot,initialDemo,equipmentHint};
})();
if(typeof module!=='undefined')module.exports=PlatformContext;
