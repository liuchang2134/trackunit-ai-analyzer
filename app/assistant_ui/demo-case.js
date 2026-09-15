/* Scripted case is an independent, read-only presentation, never a live AI report. */
(() => {
  const byId=id=>document.getElementById(id);
  const node=(tag,value,className)=>{const item=document.createElement(tag);item.textContent=value;if(className)item.className=className;return item;};
  let scenario=null,index=0,chart=null,loading=null;
  const revealed=new Set();
  const evidenceFor=ids=>scenario.evidence.filter(item=>ids.includes(item.id));
  const items=values=>{const list=document.createElement('ul');for(const value of values)list.append(node('li',value));return list;};
  function drawChart(){
    if(!scenario||byId('demo-view').hidden||!window.echarts)return;
    chart=chart||echarts.init(byId('demo-chart'));
    chart.setOption({animation:false,color:['#0055d9','#db963b'],grid:{left:42,right:16,top:34,bottom:36},
      tooltip:{trigger:'axis'},legend:{data:['左行走指令（%）','左行走响应（%）'],textStyle:{fontSize:11}},
      xAxis:{type:'value',name:'分钟',nameLocation:'middle',nameGap:24,min:0},
      yAxis:{type:'value',min:0,max:100,axisLabel:{formatter:'{value}%'}},
      series:[['左行走指令（%）','left_travel_command_percent'],['左行走响应（%）','left_travel_response_percent']].map(([name,key])=>({name,type:'line',showSymbol:false,smooth:false,data:scenario.telemetry.points.map(p=>[p.minute,p[key]])}))});
    chart.resize();
  }
  function renderStage(focus=false){
    const stage=scenario.stages[index],body=byId('demo-stage');body.replaceChildren();
    byId('demo-step-count').textContent=`${index+1} / ${scenario.stages.length}`;
    byId('demo-prev').disabled=index===0;
    byId('demo-next').textContent=index===scenario.stages.length-1?'从头演示':'下一步';
    byId('demo-steps').querySelectorAll('button').forEach((button,i)=>{if(i===index)button.setAttribute('aria-current','step');else button.removeAttribute('aria-current');});
    body.append(node('p',stage.label,'demo-reference-label'),node('h3',stage.title),node('p',stage.summary,'demo-summary'),items(stage.details));
    if(stage.id==='analysis')body.prepend(node('span','预设 AI 分析示例 · 未调用 Gemini','demo-tag'));
    if(stage.id==='checks')for(const check of scenario.checks){
      const card=node('article','','demo-check'),button=node('button',revealed.has(check.id)?'收起模拟结果':'查看模拟检查结果','quiet');button.type='button';
      const result=node('p',check.simulated_result,'demo-check-result');result.hidden=!revealed.has(check.id);
      button.setAttribute('aria-expanded',String(!result.hidden));
      button.onclick=()=>{if(revealed.has(check.id))revealed.delete(check.id);else revealed.add(check.id);result.hidden=!revealed.has(check.id);button.textContent=result.hidden?'查看模拟检查结果':'收起模拟结果';button.setAttribute('aria-expanded',String(!result.hidden));};
      card.append(node('h4',check.title),node('p',check.action),button,result);body.append(card);
    }
    if(stage.id==='conclusion'){
      body.append(node('h3','备件建议 · 按检查结果分流'));
      for(const part of scenario.parts){const item=node('article','','demo-part');item.append(node('strong',part.name),node('p',part.reason),node('p',part.status),node('small','准确料号 / 库存：未提供，需按真实 VIN 在官方资料中核对。'));body.append(item);}
      body.append(node('p',scenario.conclusion.summary,'demo-summary'),items(scenario.conclusion.limitations));
    }
    const evidence=byId('demo-evidence');evidence.replaceChildren();
    for(const item of evidenceFor(stage.evidence_ids)){const row=node('li','');row.append(node('strong',item.label),node('p',item.text),node('small',item.source_note));evidence.append(row);}
    if(focus){body.focus({preventScroll:true});body.scrollIntoView({block:'nearest'});}
  }
  function render(){
    byId('demo-title').textContent=scenario.title;byId('demo-disclaimer').textContent=scenario.disclaimer;
    byId('demo-content').querySelector('.demo-hero .demo-tag').textContent=scenario.source.label;
    byId('demo-device-id').textContent=scenario.machine.machine_id;
    byId('demo-steps').replaceChildren();
    scenario.stages.forEach((stage,i)=>{const item=document.createElement('li'),button=document.createElement('button');button.type='button';button.append(node('span',String(i+1),'demo-step-number'),node('span',stage.label.replace(/^\d+\s*·\s*/,'')));button.onclick=()=>{index=i;renderStage(true);};item.append(button);byId('demo-steps').append(item);});
    byId('demo-chart-note').textContent=scenario.telemetry.label;
    byId('demo-assumptions').replaceChildren(items(scenario.telemetry.assumptions));
    const table=document.createElement('table');table.className='demo-table';
    const head=document.createElement('tr');for(const label of ['分钟','阶段','转速 rpm','电压 V','油温 °C','指令 %','响应 %','故障码'])head.append(node('th',label));
    const thead=document.createElement('thead');thead.append(head);table.append(thead);const tbody=document.createElement('tbody');
    for(const p of scenario.telemetry.points){const row=document.createElement('tr');for(const value of [p.minute,p.phase,p.engine_rpm,p.system_voltage_v,p.hydraulic_oil_temperature_c,p.left_travel_command_percent,p.left_travel_response_percent,p.fault_code||'—'])row.append(node('td',String(value)));tbody.append(row);}table.append(tbody);
    byId('demo-data-table').replaceChildren(table);renderStage();byId('demo-content').hidden=false;byId('demo-status').hidden=true;
    requestAnimationFrame(drawChart);
  }
  window.enterDemoCase=()=>{
    if(scenario){requestAnimationFrame(drawChart);return Promise.resolve();}
    if(loading)return loading;
    byId('demo-status').hidden=false;byId('demo-status').textContent='正在载入预设演示案例…';
    loading=api('/assistant/demo-case').then(data=>{scenario=data;render();}).catch(()=>{
      byId('demo-status').replaceChildren(node('p','演示案例暂时无法载入。请确认后端已更新后重试。'));
      const retry=node('button','重新载入','quiet');retry.type='button';retry.onclick=()=>window.enterDemoCase();byId('demo-status').append(retry);
    }).finally(()=>{loading=null;});return loading;
  };
  byId('demo-prev').onclick=()=>{if(index>0){index--;renderStage(true);}};
  byId('demo-next').onclick=()=>{index=(index+1)%scenario.stages.length;renderStage(true);};
  byId('demo-reset').onclick=()=>{index=0;revealed.clear();renderStage(true);};
  window.addEventListener('resize',()=>{if(chart&&!byId('demo-view').hidden)chart.resize();});
  if(new URLSearchParams(location.search).get('demo')==='1')setView('demo');
})();
