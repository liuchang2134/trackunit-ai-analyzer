/* A separate, clearly synthetic risk example; never associate it with a Trackunit asset. */
(() => {
  const byId=id=>document.getElementById(id);
  const live=byId('risk-live'),demo=byId('risk-demo');
  if(!live||!demo)return;
  const mode=window.JilianDataMode?.mode;
  let loading=null,loaded=false;
  const formatTime=value=>new Date(value).toLocaleString('zh-CN',{month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit'});
  async function json(url){
    const response=await fetch(url);
    if(!response.ok)throw new Error('模拟模型资料暂时无法读取。');
    return response.json();
  }
  window.renderRiskDemo=async()=>{
    if(mode!=='demo'){live.hidden=false;demo.hidden=true;return;}
    live.hidden=true;demo.hidden=false;
    if(loaded)return;
    if(loading)return loading;
    byId('risk-demo-status').textContent='正在运行模拟工况预警模型…';
    loading=(async()=>{
      try{
        const data=await json('/assistant/cooling/replay?episode_id=CW-1b1941610c93&cursor=135');
        if(data.source!=='synthetic_only'||!data.machine_id?.startsWith('SIM-')||
          data.real_trackunit_supported!==false||!Number.isFinite(Date.parse(data.cutoff))||
          !data.prediction||!Array.isArray(data.history)||!data.history.length)
          throw new Error('模拟资料身份未通过校验，未展示风险结果。');
        const prediction=data.prediction,observation=data.history.at(-1).observation;
        const horizon=Number(data.horizon_minutes),cutoff=Date.parse(data.cutoff);
        if(!Number.isFinite(horizon)||horizon<1||horizon>60)throw new Error('模拟预测窗口无法核验。');
        const labels={warning:'冷却系统持续高温 · 提前预警',watch:'冷却系统持续高温 · 观察中',
          below_threshold:'冷却系统持续高温 · 未触发预警',unknown:'冷却系统持续高温 · 数据不足',
          stopped:'冷却系统持续高温 · 停机不预测',current_high:'当前温度异常 · 非提前预警'};
        byId('risk-demo-title').textContent=labels[prediction.status]||'模拟冷却风险 · 状态待核对';
        byId('risk-demo-machine').textContent=`SIM-EXC-90kW · 独立模拟设备 ${data.machine_id} · 观测截止 ${formatTime(data.cutoff)}`;
        byId('risk-demo-window').textContent=`${formatTime(data.cutoff)}—${formatTime(cutoff+horizon*60000)}`;
        byId('risk-demo-score').textContent=Number.isFinite(prediction.score)?
          `${prediction.score.toFixed(3)}（阈值 ${Number(data.alarm_threshold).toFixed(2)}）`:'尚无有效得分';
        byId('risk-demo-delta').textContent=Number.isFinite(prediction.coolant_delta10)?
          `${prediction.coolant_delta10>=0?'+':''}${prediction.coolant_delta10.toFixed(2)} °C`:'数据不足';
        const temp=Number.isFinite(observation.coolant_c)?`${observation.coolant_c.toFixed(1)} °C`:'未采集',
          load=Number.isFinite(prediction.hydraulic_kw_mean10)?`${prediction.hydraulic_kw_mean10.toFixed(1)} kW`:'未采集';
        byId('risk-demo-evidence').textContent=`截至模拟观测时点的依据：冷却液 ${temp}；过去 10 分钟温升如上；液压功率代理均值 ${load}。模型仅使用过去观测。`;
        byId('risk-demo-limit').textContent=`${data.limitation||'模拟实验，未经实机验证。'} 预警不指认某个零件损坏。`;
        byId('risk-demo-result').hidden=false;
        byId('risk-demo-status').textContent='已运行本地时序模型；以下结果属于模拟设备。';
        loaded=true;
        try{
          const evaluation=await json('/assistant/cooling/evaluation'),metrics=evaluation.extended?.reports?.original?.overall;
          byId('risk-demo-evaluation').textContent=evaluation.extended?.status==='available'&&metrics?
            `独立模拟测试：提前发现 ${metrics.detected_events}/${metrics.events} 次热事件；每可评估小时误报 ${Number(metrics.false_alert_episodes_per_eligible_hour).toFixed(3)} 段，高于预设 0.1 门槛。`:
            '独立评估暂不可用；本例只能演示模型输出，不能评估告警可靠性。';
        }catch{byId('risk-demo-evaluation').textContent='独立评估暂不可用；不能据此判断告警可靠性。';}
      }catch(error){byId('risk-demo-result').hidden=true;byId('risk-demo-status').textContent=error.message;}
    })().finally(()=>{loading=null;});
    return loading;
  };
})();
