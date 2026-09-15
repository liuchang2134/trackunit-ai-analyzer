/* Pure selection acknowledgement; no VIN, telemetry, report or credentials leave the frame. */
const PlatformContext=(()=>{
  const uuid=/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
  function asset(hash){const value=hash.startsWith('#trackunit-asset=')?hash.slice('#trackunit-asset='.length):'';return uuid.test(value)?value:null;}
  function candidates(machines,source,id){
    return id?machines.filter(m=>m.machine_id===id&&(m.dataset_id?m.provenance==='user_supplied':source==='trackunit_cache')):[];
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
  return {asset,candidates,snapshot};
})();
if(typeof module!=='undefined')module.exports=PlatformContext;
