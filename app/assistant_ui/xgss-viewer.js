/* XGSS owns the manual/catalog page. Never store its authenticated URL. */
(() => {
  const text=(tag,value)=>{const e=document.createElement(tag);e.textContent=value;return e;};
  window.createXGSSControls=(machine,faultCode=null)=>{
    const root=document.createElement('aside');root.className='integration-limit';
    root.append(text('strong','XGSS 官方资料'));
    const note=text('p','有对应手册时打开故障排查页；未提供故障码或未维护手册时，进入该整机的零件图册。');root.append(note);
    const status=text('p','正在检查本机接入配置…');status.setAttribute('role','status');root.append(status);
    const actions=document.createElement('div');actions.className='fault-context-actions';
    const buttons=[];
    for(const [label,code] of [...(faultCode?[['查询此故障的官方资料',faultCode]]:[]),['打开整机图册',null]]){
      const button=text('button',label);button.type='button';button.disabled=true;
      button.onclick=()=>openViewer(machine,code,button);buttons.push([button,code]);actions.append(button);
    }
    root.append(actions);
    const simulated=['mock','imported_synthetic'].includes(machine.source);
    api('/assistant/xgss/status').then(data=>{
      status.textContent=simulated?'当前是模拟设备，可演示本地排查，不向 XGSS 生产环境请求资料。':data.reason;
      for(const [button,code] of buttons)button.disabled=simulated||!(code?data.fault_ready:data.catalog_ready);
    }).catch(()=>{status.textContent='无法读取 XGSS 配置，请稍后重试。';});
    return root;
  };
  function openViewer(machine,code,opener){
    const dialog=document.createElement('dialog');dialog.className='xgss-dialog';
    const heading=text('h2',code?'XGSS 故障资料 · '+code:'XGSS 整机图册');
    heading.id='xgss-dialog-title';dialog.setAttribute('aria-labelledby',heading.id);
    const header=document.createElement('div');header.className='row';const close=text('button','关闭');close.type='button';close.onclick=()=>dialog.close();header.append(heading,close);
    const identity=text('p',`${machine.model} · VIN/PIN：${machine.serial_number}`);
    const form=document.createElement('form');const label=document.createElement('label');
    const confirmed=document.createElement('input');confirmed.type='checkbox';confirmed.required=true;
    label.append(confirmed,document.createTextNode(' 我已核对以上 VIN/PIN 与当前整机一致'));
    const submit=text('button','连接 XGSS 并打开');submit.type='submit';submit.disabled=true;form.append(label,submit);
    const status=text('p','将向 XGSS 发送该整机 VIN/PIN'+(code?'及故障码 '+code:'')+'，取得官方页面入口。');status.setAttribute('role','status');
    const external=text('a','在新标签页打开 XGSS');external.target='_blank';external.rel='noopener noreferrer';external.hidden=true;
    const frame=document.createElement('iframe');frame.title='XGSS 官方手册与零件图册';frame.referrerPolicy='no-referrer';frame.hidden=true;
    frame.setAttribute('sandbox','allow-scripts allow-same-origin allow-forms allow-popups allow-downloads');
    const help=text('p','若内嵌页面空白或要求登录，可使用“在新标签页打开 XGSS”。进入图册不代表已找到对应故障手册。');help.hidden=true;
    dialog.append(header,identity,form,status,external,help,frame);document.body.append(dialog);
    let closed=false;
    api('/assistant/xgss/status').then(data=>{
      if(closed)return;
      const simulated=['mock','imported_synthetic'].includes(machine.source);
      submit.disabled=simulated||!(code?data.fault_ready:data.catalog_ready);
      if(submit.disabled)status.textContent=simulated?'模拟设备不向 XGSS 生产环境请求资料。':data.reason;
    }).catch(()=>{if(!closed)status.textContent='无法读取 XGSS 配置，请关闭后重试。';});
    dialog.addEventListener('close',()=>{closed=true;frame.removeAttribute('src');external.removeAttribute('href');dialog.remove();if(opener.isConnected)opener.focus();},{once:true});
    form.onsubmit=async event=>{
      event.preventDefault();if(!confirmed.checked||submit.disabled)return;
      submit.disabled=true;status.textContent='正在请求 XGSS 页面地址…';
      try{
        const result=await api('/assistant/xgss/open',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({
          machine_id:machine.machine_id,dataset_id:machine.dataset_id||null,vin:machine.serial_number.trim().toUpperCase(),
          vin_confirmed:true,fault_code:code,language:$('language').value})});
        if(closed)return;
        // Defense in depth; the backend applies the authoritative URL contract.
        const url=new URL(result.url);
        if(url.protocol!=='https:'||url.hostname!=='xgss.xcmg.com'||url.username||url.password||(url.port&&url.port!=='443'))throw new Error('返回地址不属于已配置的 XGSS 官方环境。');
        status.textContent=result.message;form.hidden=true;
        external.href=result.url;external.hidden=false;help.hidden=false;frame.src=result.url;frame.hidden=false;
      }catch(error){if(!closed){status.textContent=error.message;submit.disabled=false;}}
    };
    dialog.showModal();confirmed.focus();
  }
  $('xgss-device-open').onclick=()=>{
    const machine=selected();if(!machine)return;
    openViewer({...machine,source:machine.dataset_id?'imported_'+machine.provenance:defaultSource},null,$('xgss-device-open'));
  };
})();
