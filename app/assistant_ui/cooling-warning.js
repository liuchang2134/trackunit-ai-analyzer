/* Independent synthetic early warning. Requests never run Gemini automatically. */
(() => {
  const el=id=>document.getElementById(id);
  const labels={warning:'提前预警',watch:'观察中 · 尚未连续触发',below_threshold:'未触发预警',unknown:'暂时无法判断',stopped:'停机 · 不作预测',current_high:'当前已达到实验温度阈值'};
  const reasons={insufficient_history:'需要连续 10 分钟运行数据；停机或采样中断后重新积累。',invalid_sensor:'必需传感器缺失或超出实验输入范围。',unordered_time:'记录时间未按顺序递增。',constant_temperature_sensor:'温度读数持续不变，请核对传感器。'};
  const num=(value,digits=2)=>value==null?'—':Number(value).toFixed(digits);
  let loaded=false,sequence=0,current=null,chart=null,contextSequence=0;
  let evaluationCache=null;
  function evaluationData(){
    if(!evaluationCache)evaluationCache=api('/assistant/cooling/evaluation').catch(error=>{evaluationCache=null;throw error;});
    return evaluationCache;
  }
  async function updateValidationNote(){
    try{
      const e=await evaluationData(),extended=e.extended;
      el('cooling-validity').textContent=extended?.status==='available'
        ? `扩大模拟测试：当前模型提前识别 ${extended.reports.original.overall.detected_events}/${extended.reports.original.overall.events} 次事件，95°C 规则识别 ${extended.reports.temperature_95c.overall.detected_events}/${extended.reports.temperature_95c.overall.events} 次。误报仍超出预设要求；未触发预警不能排除异常。`
        : (extended?.reason||'尚无扩展评估结果。')+' 当前仅能查看早期模拟测试，不能据此认定实机有效。';
    }catch(error){el('cooling-validity').textContent='评估结果暂时无法读取，预警可靠性未能核对。';}
  }
  function invalidate() {sequence++;current=null;el('cooling-handoff').disabled=true;el('cooling-result').hidden=true;}
  function busy(value) {for(const id of ['cooling-load','cooling-episode','cooling-minute','cooling-position','cooling-prev','cooling-next','cooling-example-warning','cooling-example-low'])el(id).disabled=value;}
  function atMinute(value) {const minute=Math.max(1,Math.min(480,Number(value)||1));el('cooling-minute').value=minute;el('cooling-position').value=minute;return minute;}
  function draw(data) {
    const p=data.prediction,last=data.history.at(-1).observation;
    el('cooling-result').hidden=false;
    el('cooling-state').textContent=labels[p.status]||p.status;
    el('cooling-result').dataset.state=p.status;
    el('cooling-at').textContent=`${data.machine_id} · 截止 ${displayDate(data.cutoff)}（本机时间）`;
    el('cooling-temperature').textContent=num(last.coolant_c)+' °C';
    el('cooling-delta').textContent=p.coolant_delta10==null?'数据不足':`${p.coolant_delta10>0?'+':''}${num(p.coolant_delta10)} °C`;
    el('cooling-score').textContent=p.score==null?'未预测':num(p.score,3);
    el('cooling-explanation').textContent=p.status==='unknown'?(reasons[p.reason]||'数据尚不足以支持预警。'):
      p.status==='current_high'?'当前观测已达到 100°C 实验阈值，属于现有温度异常提示，不计作提前预测。':
      p.status==='stopped'?'当前转速对应停机状态；不估计运行中的热事件风险。':
      `预测未来 ${data.horizon_minutes} 分钟的模拟高温事件。得分阈值 ${data.alarm_threshold.toFixed(2)}，连续两次达标才预警。未触发不代表设备无故障。`;
    el('cooling-source').textContent=`本地随机森林 · 模型 ${data.model_sha256.slice(0,8)} · 仅使用截止时点及过去数据。得分不是概率。`;
    el('cooling-chart-note').textContent=`展示截止时点之前最多 60 分钟的温度观测；蓝线为冷却液温度，虚线 100°C 是本实验事件阈值。当前 ${num(last.coolant_c)}°C，环境 ${num(last.ambient_c)}°C。`;
    const root=el('cooling-table');root.replaceChildren();
    const table=document.createElement('table'),head=table.createTHead().insertRow();
    for(const title of ['本机时间','冷却液 °C','转速 rpm','压力 bar','流量 L/min','预警状态']){const th=document.createElement('th');th.scope='col';th.textContent=title;head.append(th);}
    const body=table.createTBody();
    for(const h of data.history){const o=h.observation,row=body.insertRow();for(const v of [displayDate(o.recorded_at),num(o.coolant_c),num(o.engine_rpm,0),num(o.hydraulic_pressure_bar,1),num(o.hydraulic_flow_lpm,1),labels[h.prediction.status]])row.insertCell().textContent=v;}
    root.append(table);
    if(window.echarts){
      chart=chart||echarts.init(el('cooling-chart'));
      chart.setOption({animation:false,grid:{left:48,right:18,top:24,bottom:42},tooltip:{trigger:'axis',renderMode:'richText'},
        xAxis:{type:'time',axisLabel:{formatter:value=>new Date(value).toLocaleTimeString('zh-CN',{hour:'2-digit',minute:'2-digit',hour12:false})}},
        yAxis:{type:'value',name:'°C',min:Math.floor(Math.min(70,...data.history.map(h=>h.observation.coolant_c??70))/10)*10,
          max:Math.max(110,Math.ceil((last.coolant_c||100)/10)*10)},
        series:[{name:'冷却液温度',type:'line',showSymbol:false,lineStyle:{color:'#2463bc',width:2},
          data:data.history.map(h=>[h.observation.recorded_at,h.observation.coolant_c]),
          markLine:{symbol:'none',label:{show:false},lineStyle:{color:'#af7427',type:'dashed'},data:[{yAxis:100}]}}]},true);
      chart.resize();
    }
    el('cooling-handoff').disabled=false;
  }
  async function load() {
    invalidate(); const mine=sequence;
    const episode=el('cooling-episode').value,cursor=atMinute(el('cooling-minute').value)-1;
    if(!episode)return;
    busy(true);el('cooling-status').textContent='正在读取当前及过去观测，并运行本地预警模型…';
    try{
      const data=await api('/assistant/cooling/replay?'+new URLSearchParams({episode_id:episode,cursor}));
      if(mine!==sequence)return;
      current=data;draw(data);el('cooling-status').textContent=`已更新至第 ${cursor+1} 分钟；没有使用未来事件标签。`;
    }catch(error){if(mine===sequence)el('cooling-status').textContent=error.message;}
    finally{if(mine===sequence)busy(false);}
  }
  window.enterCoolingView=async()=>{
    updateValidationNote();
    if(!loaded){
      el('cooling-status').textContent='正在读取独立测试片段…';busy(true);
      try{const episodes=await api('/assistant/cooling/episodes');
        el('cooling-episode').replaceChildren(...episodes.map((e,i)=>{const option=document.createElement('option');option.value=e.episode_id;option.textContent=`片段 ${String(i+1).padStart(2,'0')} · ${e.episode_id} · 8小时`;return option;}));loaded=true;
      }catch(error){el('cooling-status').textContent=error.message;return;}finally{busy(false);}
      if(!el('cooling-view').hidden)await load();
    }else if(current){requestAnimationFrame(()=>chart?.resize());}
    else await load();
  };
  window.leaveCoolingView=()=>{sequence++;busy(false);};
  el('cooling-load').onclick=load;
  el('cooling-minute').oninput=()=>{invalidate();atMinute(el('cooling-minute').value);el('cooling-status').textContent='回放时点已改变，点击“更新预警”查看结果。';};
  el('cooling-position').oninput=()=>{invalidate();atMinute(el('cooling-position').value);el('cooling-status').textContent='松开滑块或用键盘选择后，点击“更新预警”。';};
  el('cooling-episode').onchange=()=>{invalidate();el('cooling-status').textContent='已更换片段，点击“更新预警”。';};
  el('cooling-prev').onclick=()=>{atMinute(Number(el('cooling-minute').value)-5);load();};
  el('cooling-next').onclick=()=>{atMinute(Number(el('cooling-minute').value)+5);load();};
  for(const [id,episode] of [['cooling-example-warning','CW-1b1941610c93'],['cooling-example-low','CW-255282c9c890']])el(id).onclick=()=>{
    el('cooling-episode').value=episode;atMinute(136);load();
  };
  el('cooling-handoff').onclick=async()=>{
    if(!current)return;
    if(!el('elapsed').hidden){el('cooling-status').textContent='请等待当前设备的 AI 分析结束后再切换。';return;}
    const mine=sequence,data=current;busy(true);el('cooling-handoff').disabled=true;
    el('cooling-status').textContent='正在保存此模拟设备与回放时点，准备排查证据…';
    try{
      const prepared=await api('/assistant/cooling/prepare',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({episode_id:data.episode_id,cursor:data.cursor})});
      if(mine!==sequence)return;
      await refresh();if(mine!==sequence)return;
      el('machine').value='dataset:'+prepared.dataset_id;selectMachine();
      el('task').value='overview';el('question').value=prepared.question;updateTask();
      if(typeof refreshLocalDraftControls==='function')refreshLocalDraftControls();
      el('question-details').open=true;setView('work');el('question').focus();
      el('status').textContent='已带入对应模拟设备、温度观测和预警证据。点击“开始分析”才会请求 Gemini。';
    }catch(error){if(mine===sequence)el('cooling-status').textContent=error.message;}
    finally{busy(false);if(mine===sequence)el('cooling-handoff').disabled=!current;}
  };
  el('cooling-evaluation').ontoggle=async()=>{
    if(!el('cooling-evaluation').open||el('cooling-evaluation-body').children.length)return;
    const root=el('cooling-evaluation-body');
    try{
      const e=await evaluationData();root.replaceChildren();
      const extended=e.extended;
      function comparison(title,models){
        const h=document.createElement('h3');h.textContent=title;root.append(h);
        const table=document.createElement('table'),head=table.createTHead().insertRow();
        for(const title of ['指标','当前随机森林','95°C 温度规则']){const th=document.createElement('th');th.scope='col';th.textContent=title;head.append(th);}
        const body=table.createTBody();
        for(const [title,fn] of [['提前识别事件',m=>`${m.detected_events} / ${m.events}`],['检出事件提前量中位数',m=>`${m.median_lead_minutes??'—'} 分钟`],['误报段数',m=>m.false_alert_episodes],['每可评估小时误报段数',m=>num(m.false_alert_episodes_per_eligible_hour,3)],['误报累计分钟',m=>m.false_alert_minutes]]){
          const row=body.insertRow();row.insertCell().textContent=title;models.forEach(m=>row.insertCell().textContent=fn(m));
        }
        root.append(table);
      }
      if(extended?.status==='available'){
        comparison('扩大测试 · 96 个新模拟片段',[extended.reports.original.overall,extended.reports.temperature_95c.overall]);
        const note=document.createElement('p');note.className='muted';
        note.textContent=`可评估观测 ${num(extended.reports.original.overall.eligible_hours,2)} 小时；误报门槛为每可评估小时 0.1 段，当前仍未达标。提前量仅统计检出的事件，不包括漏报。情景经过人为平衡，不代表真实故障发生率。`;
        root.append(note);
        comparison('原参数范围 · 48 个新片段',[extended.reports.original.groups.nominal,extended.reports.temperature_95c.groups.nominal]);
        comparison('改变热参数、控制和传感器误差 · 48 个片段',[extended.reports.original.groups.shifted,extended.reports.temperature_95c.groups.shifted]);
        const candidate=document.createElement('p');candidate.className='muted';
        candidate.textContent=`报警参数候选未采用：同一测试中识别 ${extended.reports.candidate.overall.detected_events}/${extended.reports.candidate.overall.events} 次事件、每可评估小时误报 ${num(extended.reports.candidate.overall.false_alert_episodes_per_eligible_hour,3)} 段，仍未通过预设门槛。回放继续使用原模型。`;
        root.append(candidate);
      }else{const missing=document.createElement('p');missing.textContent=extended?.reason||'扩展评估尚不可用。';root.append(missing);}
      const historical=document.createElement('details'),label=document.createElement('summary');label.textContent='查看最初 24 个测试片段的历史结果';historical.append(label);
      const table=document.createElement('table'),head=table.createTHead().insertRow();
      for(const title of ['独立模拟测试','随机森林','95°C 温度对照']){const th=document.createElement('th');th.scope='col';th.textContent=title;head.append(th);}
      const models=[e.test.random_forest,e.test.temperature_95c],body=table.createTBody();
      for(const [title,fn] of [['提前识别事件',m=>`${m.detected_events} / ${m.events}`],['提前量中位数',m=>`${m.median_lead_minutes??'—'} 分钟`],['误报片段',m=>m.false_alert_episodes],['每有效小时误报片段',m=>num(m.false_alert_episodes_per_eligible_hour,3)],['预警采样点精确率',m=>num(m.window_precision,3)]]){
        const row=body.insertRow();row.insertCell().textContent=title;models.forEach(m=>row.insertCell().textContent=fn(m));
      }
      const note=document.createElement('p');note.className='muted';
      note.textContent=`训练/验证/测试：${e.split_counts.train}/${e.split_counts.validation}/${e.split_counts.test} 个独立模拟设备片段。有效测试观测 ${num(models[0].eligible_hours,2)} 小时；故意混合不同情景，不代表真实故障发生率。模型提前量更长，但此次误报更多；尚未达到实机告警要求。示例为事后选取的交互演示，评估包含全部测试片段。`;
      historical.append(table,note);root.append(historical);
    }catch(error){root.textContent=error.message;}
  };
  window.refreshCoolingContext=async()=>{
    const mine=++contextSequence,m=selected(),root=el('selected-cooling');root.hidden=true;root.replaceChildren();
    if(!m?.cooling_reference)return;
    try{
      const c=await api('/assistant/cooling/context?'+new URLSearchParams({dataset_id:m.dataset_id}));
      if(mine!==contextSequence||!c)return;
      const h=document.createElement('h2');h.textContent='已关联的模拟冷却预警';
      const p=document.createElement('p');p.textContent=`${labels[c.prediction.status]} · 得分 ${num(c.prediction.score,3)} · 截止 ${displayDate(c.cutoff)}。`;
      const note=document.createElement('p');note.className='muted';note.textContent='温度观测与预警证据随本数据版本保留；AI 可解释证据，不能据此确认具体零件故障。';root.append(h,p,note);root.hidden=false;
    }catch(error){if(mine===contextSequence){root.textContent=error.message;root.hidden=false;}}
  };
  window.addEventListener('resize',()=>chart?.resize());
})();
