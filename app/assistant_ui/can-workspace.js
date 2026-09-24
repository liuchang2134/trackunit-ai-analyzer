/* Embed CAN exploration in the existing device-following workbench.
 * Device context stays on loopback; the synthetic AI route never consumes it.
 */
(() => {
  const frame = document.getElementById('can-workspace');
  let loaded = false, visible = false, ticket = 0, lastKey = null, cached = null;
  function post(context) {
    if (loaded) frame.contentWindow.postMessage({type:'jilian:can-host-context', context}, location.origin);
  }
  window.syncCanWorkspace = async () => {
    if (!visible || !loaded) return;
    const assetId = PlatformContext.asset(location.hash);
    const machine = selected();
    // A previously selected local machine must never be announced as the new tab.
    const matched = machine && (!assetId || machine.machine_id === assetId) && !['mock','imported_synthetic'].includes(machine.source) && machine.provenance !== 'synthetic';
    const hint = assetId ? getPlatformEquipmentHint(assetId).value : null;
    const key = `${assetId || ''}:${matched ? machine.selection_id : ''}:${hint || ''}`;
    if (key === lastKey && cached) { post(cached); return; }
    lastKey = key;
    const mine = ++ticket;
    cached = {asset_id:assetId, hint, state:matched?'loading':'unmatched',
      model:matched?machine.model:null, serial:matched?machine.serial_number:null,
      source:matched?machine.source:null, source_document:matched?machine.source_document:null, sample:null};
    post(cached);
    if (!matched) return;
    const params = new URLSearchParams({machine_id:machine.machine_id});
    if(machine.dataset_id)params.set('dataset_id',machine.dataset_id);
    try {
      const response = await api('/assistant/device-overview?'+params);
      if(mine!==ticket || response.machine_id!==machine.machine_id || response.dataset_id!==(machine.dataset_id||null))return;
      const last = response.series.at(-1);
      cached = {...cached,state:'matched',sample:last?{recorded_at:last.recorded_at,
        operating_hours:last.operating_hours,idle_hours:last.idle_hours,fuel_remaining_percent:last.fuel_remaining_percent}:null};
    } catch { if(mine!==ticket)return; cached = {...cached,state:'unavailable'}; }
    post(cached);
  };
  window.enterCanWorkspace = show => {
    visible = show;
    if (!show) { if(loaded)frame.contentWindow.postMessage({type:'jilian:can-hidden'},location.origin); return; }
    if (!frame.getAttribute('src'))frame.src='can-replay.html?embedded=1';
    else window.syncCanWorkspace();
  };
  window.addEventListener('message', event => {
    if(event.origin!==location.origin||event.source!==frame.contentWindow)return;
    if(event.data?.type==='jilian:can-ready'){loaded=true;window.syncCanWorkspace();}
    if(event.data?.type==='jilian:can-open-work')setView('work',{reason:'user'});
  });
})();
