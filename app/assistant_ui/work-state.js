(() => {
  const names={dig:'挖掘',swing:'回转',dump:'卸料',idle:'怠速',travel:'行走',off:'停机',unknown:'未知'};
  const colors={dig:'#4d8fe8',swing:'#a884d8',dump:'#e0a33f',idle:'#8fa2b3',travel:'#4ecb8d',off:'#7d8b99',unknown:'#5d6b7a'};
  let replay=null,timer=null;
  const stop=()=>{clearInterval(timer);timer=null;$('state-play').textContent='播放 · 20×';};
  window.stopWorkStatePlayback=stop;
  function table(target,headers,rows){
    const node=document.createElement('table'),head=node.createTHead().insertRow();
    headers.forEach(label=>{const th=document.createElement('th');th.scope='col';th.textContent=label;head.append(th);});
    const body=node.createTBody();rows.forEach(values=>{const row=body.insertRow();values.forEach(value=>{row.insertCell().textContent=String(value);});});
    $(target).replaceChildren(node);
  }
  function frame(){
    if(!replay)return;
    const index=Number($('state-position').value),sample=replay.samples[index];
    $('state-name').textContent=names[sample.state]||'未知';
    $('state-name').style.color=colors[sample.state]||colors.unknown;
    $('state-time').textContent=`${displayDate(sample.recorded_at)}（本机时间） · 采样 ${index+1}/${replay.samples.length}`;
    $('state-score').textContent=sample.score==null?'输入不足，未识别。':`模型内部得分 ${sample.score.toFixed(3)}${sample.state==='unknown'?` · 候选为${names[sample.candidate_state]||'未知'}，得分不足，保留未知。`:' · 仅限此模拟片段。'} 得分不是正确率，高分也可能误判。`;
    table('state-sensors',['传感器输入','数值'],[
      ['发动机转速',sample.sensors.engine_rpm+' rpm'],['液压压力',sample.sensors.hydraulic_pressure_bar+' bar'],
      ['液压流量',sample.sensors.hydraulic_flow_lpm+' L/min'],['地面速度',sample.sensors.speed_kmh+' km/h']]);
    [...$('state-track').children].forEach((el,i)=>el.classList.toggle('current',i===index));
  }
  async function load(){
    stop();replay=null;$('state-player').hidden=true;
    const startMinutes=Number($('state-start').value);
    if(!Number.isInteger(startMinutes)||startMinutes<0||startMinutes>479){$('state-status').textContent='起点须为0至479之间的整数分钟。';return;}
    if(!$('state-episode').value){$('state-status').textContent='没有可用的模拟片段。';return;}
    $('state-load').disabled=true;$('state-episode').disabled=true;$('state-start').disabled=true;
    $('state-status').textContent='本地分类器正在处理模拟传感器记录…';
    try{
      const query=new URLSearchParams({episode_id:$('state-episode').value,start:String(startMinutes*12),count:'360'});
      replay=await api('/assistant/work-state/replay?'+query);
      $('state-position').max=String(replay.samples.length-1);$('state-position').value='0';
      const counts={};
      $('state-track').replaceChildren(...replay.samples.map((sample,index)=>{
        counts[sample.state]=(counts[sample.state]||0)+1;
        const node=document.createElement('span');node.style.background=colors[sample.state]||colors.unknown;
        node.title=`${displayDate(sample.recorded_at)} · ${names[sample.state]||'未知'}`;
        node.onclick=()=>{stop();$('state-position').value=String(index);frame();};return node;
      }));
      table('state-distribution',['识别工况','采样点','占比'],Object.entries(names).map(([key,name])=>[
        name,counts[key]||0,((counts[key]||0)/replay.samples.length*100).toFixed(1)+'%']));
      $('state-player').hidden=false;
      $('state-status').textContent=`已加载 ${replay.samples.length} 点，每点间隔5秒；下方展示模型识别结果，不含隐藏工况标签。`;
      frame();
    }catch(error){$('state-status').textContent=error.message;}
    finally{$('state-load').disabled=false;$('state-episode').disabled=false;$('state-start').disabled=false;}
  }
  $('state-load').onclick=load;
  const invalidate=()=>{stop();replay=null;$('state-player').hidden=true;$('state-status').textContent='片段或起点已变更，请重新加载。';};
  $('state-episode').onchange=invalidate;
  $('state-start').onchange=invalidate;
  $('state-position').oninput=()=>{stop();frame();};
  $('state-play').onclick=()=>{
    if(timer){stop();return;}if(!replay)return;
    if(Number($('state-position').value)>=replay.samples.length-1)$('state-position').value='0';
    $('state-play').textContent='暂停';
    timer=setInterval(()=>{const next=Number($('state-position').value)+1;if(next>=replay.samples.length){stop();return;}$('state-position').value=String(next);frame();},250);
  };
  document.addEventListener('visibilitychange',()=>{if(document.hidden)stop();});
  api('/assistant/work-state/episodes').then(episodes=>{
    $('state-episode').replaceChildren(...episodes.map((item,index)=>{const option=document.createElement('option');option.value=item.episode_id;option.textContent=`测试片段 ${index+1} · ${item.episode_id}`;return option;}));
    if(!episodes.length)$('state-status').textContent='尚未生成模拟传感器片段，请运行工况训练脚本。';
  }).catch(error=>{$('state-status').textContent=error.message;});
})();
