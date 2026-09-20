let overview = null, overviewTicket = 0, deviceChart = null, chartRows = [];
const chartFields = {
  operating_hours:{name:'累计工时',unit:'h',color:'#2463bc'},
  idle_hours:{name:'累计怠速',unit:'h',color:'#946522'},
  fuel_remaining_percent:{name:'剩余燃油',unit:'%',color:'#32806b'}
};
function overviewNumber(value,unit='') {
  return value==null?'数据不足':Number(value).toLocaleString('zh-CN',{maximumFractionDigits:2})+unit;
}
async function refreshDeviceOverview() {
  const ticket=++overviewTicket, machine=selected(); overview=null;
  if(typeof updateDeviceFinder==='function')updateDeviceFinder();
  $('overview-export').hidden=true;
  $('overview-export').removeAttribute('href');
  resetFaultContext();
  $('overview-content').hidden=true;
  deviceChart?.clear();
  if(!machine){$('overview-status').textContent='选择设备后查看运行概况。';return;}
  $('overview-status').textContent='正在读取运行记录…';
  const params=new URLSearchParams({machine_id:machine.machine_id});
  if(machine.dataset_id)params.set('dataset_id',machine.dataset_id);
  try {
    const data=await api('/assistant/device-overview?'+params);
    if(ticket!==overviewTicket)return;
    overview=data;
    const isDemo=['mock','imported_synthetic'].includes(data.source);
    $('overview-status').textContent=`${isDemo?'模拟数据':machineSourceLabel(machine)} · ${data.valid_timestamp_samples} 条采样记录`;
    $('overview-metrics').replaceChildren();
    for(const [label,value] of [
      ['区间工时',overviewNumber(data.trend.operating_hours_delta,' h')],
      ['怠速占比',data.trend.idle_share==null?'数据不足':overviewNumber(data.trend.idle_share*100,'%')],
      ['故障记录',String(data.faults.valid_loaded_records)+' 条']
    ]) {
      const cell=document.createElement('div'),dt=document.createElement('dt'),dd=document.createElement('dd');
      dt.textContent=label;dd.textContent=value;cell.append(dt,dd);$('overview-metrics').append(cell);
    }
    $('overview-content').hidden=false;
    if(!report)$('empty-result').hidden=true;
    renderOverviewFindings();renderOverviewFaults();renderDeviceChart();
    if(typeof updateDeviceFinder==='function')updateDeviceFinder();
  } catch(e) {
    if(ticket!==overviewTicket)return;
    $('overview-status').textContent='设备数据未能载入：'+e.message;
  }
}
function renderOverviewFindings() {
  const root=$('overview-findings');root.replaceChildren();
  const names={stale_telemetry:'采样已过期，不能代表当前设备状态。',
    reporting_gap:'上报间隔较长，请核实作业安排、终端供电与通信。',
    invalid_counter_interval:'部分工时增量不一致，已从统计中排除。',
    invalid_idle_interval:'部分怠速增量不一致，怠速统计存在缺口。',
    high_idle_share:'怠速占比较高，可检查作业安排；40% 是本项目筛查假设，不是厂家故障阈值。',
    repeated_unresolved_events:'存在重复的未解决故障记录，需核实是否为同一持续故障。'};
  const codes=[...new Set(overview.trend.findings.map(item=>item.code))];
  if(codes.length){const list=document.createElement('ul');list.className='evidence-notes';
    for(const code of codes){const li=document.createElement('li');li.textContent=names[code]||'存在需要核查的数据记录。';list.append(li);}root.append(list);}
}
function renderOverviewFaults() {
  const root=$('overview-faults');root.replaceChildren();
  if(!overview.faults.events.length){root.textContent='暂无已载入的故障记录，设备健康状态待确认。';return;}
  const table=document.createElement('table'),head=table.createTHead().insertRow();
  for(const label of ['时间 / 故障码','记录内容','下一步']){const th=document.createElement('th');th.scope='col';th.textContent=label;head.append(th);}
  const body=table.createTBody(),statuses={open:'未解决',resolved:'已解决（历史记录）',acknowledged:'已确认记录'};
  for(const fault of [...overview.faults.events].reverse()){
    const row=body.insertRow();row.insertCell().textContent=displayDate(fault.occurred_at)+'\n'+fault.fault_code;
    row.insertCell().textContent=(statuses[fault.status]||fault.status)+'\n'+fault.description;
    const actions=row.insertCell();actions.className='fault-row-actions';
    const view=document.createElement('button');view.type='button';view.className='quiet';view.textContent='查看资料';
    view.setAttribute('aria-controls','fault-context');view.setAttribute('aria-expanded','false');
    view.onclick=()=>showFaultContext(fault.fault_code,view);
    const button=document.createElement('button');button.className='quiet';button.type='button';button.textContent='AI 排查';
    button.onclick=()=>focusFaultInvestigation(fault.fault_code);
    button.disabled=$('run').disabled;actions.append(view,button);
  }
  root.append(table);
}
function renderDeviceChart() {
  if(!overview)return;
  const field=$('overview-field').value,meta=chartFields[field],all=overview.series;
  const end=all.length?Date.parse(all[all.length-1].recorded_at):0;
  const start=$('overview-window').value==='all'?-Infinity:end-Number($('overview-window').value)*3600000;
  chartRows=all.filter(row=>Date.parse(row.recorded_at)>=start);
  const exportParams=new URLSearchParams({machine_id:overview.machine_id,metric:field,
    window:$('overview-window').value,expected_revision:overview.plot_revision});
  if(overview.dataset_id)exportParams.set('dataset_id',overview.dataset_id);
  $('overview-export').href='/assistant/device-overview.csv?'+exportParams;
  $('overview-export').hidden=!chartRows.length;
  $('overview-export').textContent='导出当前数据';
  $('chart-note').textContent=`${chartRows.length} 条采样${overview.sampled_for_display?' · 抽样显示':''} · 拖动滑块查看时段`;
  $('device-chart').hidden=!chartRows.some(row=>row[field]!=null);
  if($('device-chart').hidden)$('chart-note').textContent='此时段暂无该指标，切换指标或时间范围查看。';
  if(window.echarts && !$('device-chart').hidden){
    deviceChart ||= echarts.init($('device-chart'));
    const events=overview.faults.events.filter(f=>Date.parse(f.occurred_at)>=start && Date.parse(f.occurred_at)<=end);
    deviceChart.setOption({animation:false,aria:{enabled:true,label:{description:
        `${meta.name}趋势图，单位${meta.unit}，显示${chartRows.length}个采样时点。时间从${displayDate(chartRows[0]?.recorded_at)}到${displayDate(chartRows.at(-1)?.recorded_at)}。缺失值留空，详细测量值见下方数据表。`}},
      grid:{left:48,right:18,top:28,bottom:74,backgroundColor:'transparent'},
      textStyle:{color:chartTheme.inkSecondary},
      tooltip:chartTooltip({trigger:'axis',renderMode:'richText',valueFormatter:value=>value==null?'缺失':overviewNumber(value,' '+meta.unit)}),
      xAxis:{type:'time',axisLabel:Object.assign(chartAxisText(),{hideOverlap:true}),
        axisLine:{lineStyle:{color:chartTheme.axisLine}},splitLine:{show:false}},
      yAxis:{type:'value',scale:true,name:meta.unit,nameGap:10,
        nameTextStyle:{color:chartTheme.muted,fontSize:11},
        axisLabel:chartAxisText(),axisLine:{show:true,lineStyle:{color:chartTheme.axisLine}},
        splitLine:{lineStyle:{color:chartTheme.splitLine}}},
      dataZoom:[{type:'inside',filterMode:'none'},chartSlider()],
      series:[{name:meta.name,type:'line',smooth:false,connectNulls:false,showSymbol:chartRows.length<80,
        symbolSize:4,lineStyle:{width:2,color:meta.color},itemStyle:{color:meta.color},
        areaStyle:{color:meta.color,opacity:.10},
        data:chartRows.map(row=>[row.recorded_at,row[field]]),
        markLine:{silent:true,symbol:['none','none'],label:{show:false},lineStyle:{type:'dashed',color:chartTheme.warn,width:1},
          data:events.map(f=>({name:f.fault_code,xAxis:f.occurred_at}))}}]
    },true);
    deviceChart.resize();
  } else if(!window.echarts){$('chart-note').textContent='图表暂不可用，可展开数据详情查看。';}
  const table=document.createElement('table'),head=table.createTHead().insertRow();
  for(const label of ['采样时间（本机时区）',meta.name+'（'+meta.unit+'）']){const th=document.createElement('th');th.scope='col';th.textContent=label;head.append(th);}
  const body=table.createTBody();
  for(const row of chartRows){const tr=body.insertRow();tr.insertCell().textContent=displayDate(row.recorded_at);tr.insertCell().textContent=row[field]==null?'缺失':String(row[field]);}
  const scope=document.createElement('p');scope.className='muted';
  scope.textContent=`统计时段：${displayDate(overview.trend.window_start)} — ${displayDate(overview.trend.window_end)}。计入 ${overview.trend.valid_intervals} 个有效区间，排除 ${overview.trend.excluded_intervals} 个区间；不随图表缩放改变。缺失值留空，统计可能不覆盖完整工况。`;
  $('overview-table').replaceChildren(scope,table);
  $('overview-table').tabIndex=0;
  $('overview-table').setAttribute('role','region');
  $('overview-table').setAttribute('aria-label','绘图数据表，可用方向键滚动');
}
function resizeDeviceOverview(){deviceChart?.resize();}
$('overview-field').onchange=renderDeviceChart;
$('overview-window').onchange=renderDeviceChart;
$('overview-analyze').onclick=()=>{$('task').focus({preventScroll:true});document.querySelector('.query').scrollIntoView({block:'start'});};
new ResizeObserver(resizeDeviceOverview).observe($('device-chart'));
if(selected())refreshDeviceOverview();
