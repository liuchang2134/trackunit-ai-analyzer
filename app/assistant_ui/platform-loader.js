/* Load an unseen asset once, with one bounded follow-up for a newly supplied lookup hint. */
(function(global){
  class PlatformLoadState {
    constructor(){this.assetId=null;this.epoch=0;this.entries=new Map();}
    select(assetId){if(this.assetId!==assetId){this.assetId=assetId;++this.epoch;}return this.entry();}
    entry(){return this.entries.get(this.assetId)||null;}
    begin(retry=false,hint=null,followup=false){
      if(!this.assetId||this.entry()?.pending||(!retry&&this.entry()))return null;
      const previous=this.entry(),ticket={assetId:this.assetId,epoch:this.epoch,request:(previous?.request||0)+1,hint};
      this.entries.set(this.assetId,{pending:true,request:ticket.request,result:null,refreshed:false,
        usedHint:hint,hintFollowupUsed:Boolean(previous?.hintFollowupUsed||followup)});return ticket;
    }
    finish(ticket,result){
      const entry=this.entries.get(ticket.assetId);if(!entry||entry.request!==ticket.request)return false;
      entry.pending=false;entry.result=result;
      entry.retryAt=Date.now()+Math.max(0,Number(result.retry_after_seconds)||0)*1000;
      return this.assetId===ticket.assetId&&this.epoch===ticket.epoch;
    }
    accepts(ticket){return this.assetId===ticket.assetId&&this.epoch===ticket.epoch;}
  }
  if(typeof module!=='undefined'&&module.exports)module.exports={PlatformLoadState};
  global.PlatformLoadState=PlatformLoadState;
  if(typeof document==='undefined')return;
  const state=new PlatformLoadState(),byId=id=>document.getElementById(id);
  const hintRequests=new Set();
  let refreshPending=false;
  const busy=()=>byId('run').disabled||byId('form').getAttribute('aria-busy')==='true';
  const currentAsset=()=>PlatformContext.asset(location.hash);
  const hintContext=()=>global.parent&&global.parent!==global
    ?(typeof getPlatformEquipmentHint==='function'?getPlatformEquipmentHint(currentAsset()):{confirmed:false,value:null})
    :{confirmed:true,value:null};
  const permitted=()=>Boolean(currentAsset()&&!busy()&&activeView!=='demo'&&platformIndexState==='ready'&&hintContext().confirmed);
  const noLocalData=()=>PlatformContext.candidates(machines,defaultSource,currentAsset()).length===0;
  function panel(){
    let root=byId('platform-load');if(root)return root;
    root=document.createElement('div');root.id='platform-load';
    const status=document.createElement('p');status.id='platform-load-status';status.className='muted';status.setAttribute('role','status');status.setAttribute('aria-live','polite');
    const identity=document.createElement('p');identity.id='platform-load-identity';identity.className='muted';
    const retry=document.createElement('button');retry.id='platform-load-retry';retry.className='quiet';retry.type='button';retry.textContent='重试读取当前设备';retry.onclick=()=>load(true);
    root.append(status,identity,retry);document.querySelector('.device').append(root);return root;
  }
  function render(){
    const root=panel(),entry=state.entry();root.hidden=!currentAsset()||activeView==='demo'||!noLocalData();
    if(root.hidden)return;
    const result=entry?.result;
    byId('platform-load-status').textContent=entry?.pending?'正在读取 Trackunit 设备数据…':result?.message?result.message+(result.retry_after_seconds?' 请稍后重试。':''):
      (busy()?'当前分析结束后切换设备。':!hintContext().confirmed?'正在识别当前设备…':platformIndexState==='ready'?'正在连接 Trackunit…':'正在载入设备资料…');
    byId('platform-load-identity').textContent=result?.machine
      ? `${result.machine.model||'机型待确认'} · ${result.machine.serial_number||'VIN 待确认'}${result.status==='metadata_only'?' · 暂无运行样本':''} · 故障记录未读取`:'';
    byId('platform-load-retry').hidden=!result;
    byId('platform-load-retry').disabled=!permitted()||entry?.pending||refreshPending;
  }
  async function refreshLoaded(entry){
    if(refreshPending||entry.refreshed||!permitted()||!noLocalData())return;
    entry.refreshed=true;refreshPending=true;
    try{await refresh();}finally{refreshPending=false;global.platformLoaderChanged();}
  }
  async function load(retry=false,followup=false){
    state.select(currentAsset());if(!permitted()||!noLocalData())return;
    if(retry&&state.entry()?.retryAt>Date.now()){
      byId('platform-load-status').textContent=`请在 ${Math.ceil((state.entry().retryAt-Date.now())/1000)} 秒后重试。`;return;
    }
    const ticket=state.begin(retry||followup,hintContext().value,followup);if(!ticket)return;render();
    try{
      const result=await api('/assistant/platform-asset/'+ticket.assetId+'/load',{method:'POST',
        ...(ticket.hint?{headers:{'Content-Type':'application/json'},body:JSON.stringify({equipment_id_hint:ticket.hint})}:{})});
      if(result.asset_id!==ticket.assetId)throw new Error('返回设备与当前请求不一致，未加载。');
      const accepted=state.finish(ticket,result);
      if(accepted&&permitted()&&result.state==='loaded'&&/^[a-f0-9]{64}$/.test(result.dataset_id||''))await refreshLoaded(state.entry());
    }catch(error){state.finish(ticket,{state:'unavailable',status:'request_failed',message:'设备读取未完成：'+error.message});}
    finally{if(currentAsset()===ticket.assetId)global.platformLoaderChanged();}
  }
  global.platformLoaderChanged=()=>{
    state.select(currentAsset());render();
    if(currentAsset()&&noLocalData()&&!busy()&&activeView!=='demo'&&platformIndexState==='ready'&&!hintContext().confirmed&&
      !hintRequests.has(currentAsset())&&typeof notifyAssistantPanel==='function'){
      hintRequests.add(currentAsset());notifyAssistantPanel('jilian:asset-hint-request',{asset_id:currentAsset()});
    }
    if(!permitted()||!noLocalData())return;
    const entry=state.entry();
    if(!entry){load();return;}
    if(!entry.pending&&entry.result?.state==='loaded'&&/^[a-f0-9]{64}$/.test(entry.result.dataset_id||'')){refreshLoaded(entry);return;}
    const hint=hintContext().value;
    if(!entry.pending&&hint&&hint!==entry.usedHint&&!entry.hintFollowupUsed)load(false,true);
  };
  global.addEventListener('hashchange',()=>global.platformLoaderChanged());
  global.platformLoaderChanged();
})(globalThis);
