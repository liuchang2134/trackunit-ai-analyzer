const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const adjacent = path.join(__dirname,'sensor-parts-workspace.js');
const source = fs.readFileSync(fs.existsSync(adjacent) ? adjacent : path.join(__dirname,'../app/assistant_ui/sensor-parts-workspace.js'),'utf8');
const dataset = 'a'.repeat(64), series = 'b'.repeat(64), capture = 'c'.repeat(64), imageId = 'd'.repeat(64), id = 'e'.repeat(32);
const machine = {machine_id:'asset',dataset_id:dataset,serial_number:'XUGTEST000000001'};
const tick = () => new Promise(resolve => setImmediate(resolve));
const hypothesis = (index = 0, extra = {}) => ({failure_mode:index ? '传动温度风险' : '散热能力待检查',
  reason:index ? '传动油温与工况变化' : '水温与负载变化',inspection:index ? '核对变速箱油温' : '核对散热器清洁度',
  search_terms:index ? ['变速箱'] : ['散热器'],evidence_ids:[`series-evidence-${index}`],priority:'watch',...extra});

function element(tag) {
  return {tag,children:[],attributes:{},style:{},hidden:false,isConnected:true,textContent:'',
    append(...children) { this.children.push(...children); },
    replaceChildren(...children) { this.children = children; this.textContent = ''; },
    setAttribute(name,value) { this.attributes[name] = value; }};
}
const all = item => [item,...(item.children || []).flatMap(all)];
const text = item => all(item).map(item => item.textContent).join(' ');
function stream(value, error = false, kind = 'test_failure') {
  const data = ': heartbeat\r\n\r\ndata: '+JSON.stringify(error ? {type:'error',kind,message:value} : {type:'result',record:value})+'\r\n\r\n';
  const bytes = new TextEncoder().encode(data); let offset = 0;
  return {ok:true,body:{getReader:() => ({read:async() => offset >= bytes.length ? {done:true} :
    {done:false,value:bytes.slice(offset,offset = Math.min(bytes.length,offset+17))},releaseLock() {}})}};
}
function harness() {
  const requests = [], window = {}, state = {current:true};
  vm.runInNewContext(source,{window,document:{createElement:element},AbortController,DOMException,TextDecoder,Map,Set,
    fetch:(url,options) => new Promise(resolve => requests.push({url,options,
      json:value => resolve({ok:true,json:async() => value}),result:value => resolve(stream(value)),fail:(value,kind) => resolve(stream(value,true,kind)),
      httpFail:value => resolve({ok:false,json:async() => ({detail:value})})}))});
  const target = element('div');
  const options = extra => ({target,machine,seriesId:series,hypothesisIndex:0,analysisKey:'analysis-v4',
    hypothesis:hypothesis(extra?.hypothesisIndex || 0),isCurrent:() => state.current,...extra});
  return {api:window.SensorPotentialParts,requests,target,state,options};
}
const seed = (index = 0, extra = {}) => ({...machine,vin:machine.serial_number,series_id:series,hypothesis_index:index,
  hypothesis:hypothesis(index),symptom_source:'user_question',symptom:`连续趋势风险方向 ${index}，未确认故障`,search_terms:index ? ['变速箱'] : ['散热器'],...extra});
const planned = (index = 0, extra = {}) => ({research_id:index ? 'f'.repeat(32) : id,machine_id:machine.machine_id,dataset_id:dataset,
  vin:machine.serial_number,symptom:seed(index).symptom,symptom_source:'user_question',analysis_mode:'fault',revision:0,pages:[],
  plan:{summary:'检查风险方向',directions:[{component:index ? '变速箱' : '散热器',reason:'趋势待核实',search_terms:seed(index).search_terms}]},
  evidence:{parts:[],manuals:[]},fault_context:{manual_fault:null,engineering_fault:null,manuals:[]},...extra});
const part = extra => ({source_id:`xpart:${capture}:0`,capture_id:capture,name:'散热器',part_number:'800123456',figure_ref:'4',
  assembly_path:['冷却系统'],reason:'本项水温趋势需核对散热能力',replacement_condition:'检查芯体堵塞及泄漏，确认不可清理修复后准备',...extra});
const collected = (index = 0, extra = {}) => ({...planned(index),revision:1,
  pages:[{capture_id:capture,content:{vin:machine.serial_number,assembly_path:['冷却系统']},illustrations:[{image_id:imageId,title:'冷却系统'}]}],
  evidence:{parts:[part()],manuals:[]},direct_collection:{status:'completed',revision:1,unmatched_terms:[],unresolved:[]},...extra});
const analyzed = (index = 0, extra = {}) => ({...collected(index),analysis_revision:1,
  advice:{summary:'先核查对应风险方向',parts:[],inspection_targets:[part()],analysis_scope:'current'},...extra});
async function reachAnalyze(h, index = 0, extra = {}) {
  const run = h.api.open(h.options({hypothesisIndex:index,...extra}));
  h.requests.at(-1).json(seed(index)); await tick();
  h.requests.at(-1).result(planned(index)); await tick();
  h.requests.at(-1).result(collected(index)); await tick();
  return {run};
}

test('potential parts: one click chains verified handoff, plan, direct collection and analysis without activation', async() => {
  const h = harness(), {run} = await reachAnalyze(h);
  assert.deepEqual(h.requests.map(item => item.url),[
    `/assistant/sensor-series/${series}/parts-handoff`,'/assistant/xgss/research/plan',
    `/assistant/xgss/research/${id}/collect-direct`,`/assistant/xgss/research/${id}/analyze`]);
  assert.deepEqual(JSON.parse(h.requests[0].options.body),{machine_id:'asset',dataset_id:dataset,hypothesis_index:0});
  assert.deepEqual(JSON.parse(h.requests[1].options.body),{machine_id:'asset',dataset_id:dataset,vin:machine.serial_number,
    analysis_mode:'fault',symptom:seed().symptom,symptom_source:'user_question'});
  assert.deepEqual(JSON.parse(h.requests[2].options.body),{expected_revision:0,terms:['散热器'],sensor_context:{series_id:series,hypothesis_index:0}});
  h.requests[3].result(analyzed()); await run;
  assert.match(text(h.target),/已找到 1 项潜在故障配件/); assert.match(text(h.target),/待核查候选/);
  assert.match(text(h.target),/800123456/); assert.match(text(h.target),/芯体堵塞及泄漏/);
  const links = all(h.target).filter(item => item.tag === 'a');
  assert.equal(links.length,2); assert.ok(links.every(item => item.href === `/assistant/xgss/research/${id}/images/${imageId}`));
  assert.match(links[1].textContent,/图中序号 4/);
  assert.ok(h.requests.every(item => !/activate|active|latest|email/.test(item.url)));
});

test('potential parts: duplicate clicks share work and completed results are reused', async() => {
  const h = harness(), first = h.api.open(h.options()), second = h.api.open(h.options());
  assert.equal(first,second); assert.equal(h.requests.length,1);
  h.requests[0].json(seed()); await tick(); h.requests[1].result(planned()); await tick();
  h.requests[2].result(collected()); await tick(); h.requests[3].result(analyzed()); await first;
  const replacement = element('div'); await h.api.open(h.options({target:replacement}));
  assert.equal(h.requests.length,4); assert.match(text(replacement),/800123456/);
});

test('potential parts: failed analysis retries only analysis and retains collected revision', async() => {
  const h = harness(), {run} = await reachAnalyze(h);
  h.requests[3].fail('暂时无法分析'); await run;
  assert.match(text(h.target),/配件分析暂未完成/);
  const retry = all(h.target).find(item => item.tag === 'button' && item.textContent === '重试').onclick();
  assert.equal(h.requests.length,5); assert.match(h.requests[4].url,/\/analyze$/);
  h.requests[4].result(analyzed()); await retry;
  assert.match(text(h.target),/已找到 1 项/); assert.equal(h.requests.filter(item => /\/plan$/.test(item.url)).length,1);
});

test('potential parts: failed direct read reuses seed and plan, with the same expected revision', async() => {
  const h = harness(), run = h.api.open(h.options());
  h.requests[0].json(seed()); await tick(); h.requests[1].result(planned()); await tick();
  h.requests[2].fail('图册暂不可读'); await run;
  const again = h.api.open(h.options()); assert.equal(h.requests.length,4);
  assert.match(h.requests[3].url,/\/collect-direct$/); assert.equal(JSON.parse(h.requests[3].options.body).expected_revision,0);
  h.requests[3].result(collected()); await tick(); h.requests[4].result(analyzed()); await again;
  assert.match(text(h.target),/已找到 1 项/);
});

test('potential parts: collection combines AI catalog terms with seed terms and excludes invalid search strings', async() => {
  const h = harness(), run = h.api.open(h.options()); h.requests[0].json(seed()); await tick();
  const record = planned(); record.plan.directions[0].search_terms = ['冷却系统','散热器','冷却系统','https://invalid.test/','A'];
  h.requests[1].result(record); await tick();
  assert.deepEqual(JSON.parse(h.requests[2].options.body).terms,['冷却系统','散热器']);
  h.api.cancelAll(); h.requests[2].result(collected(0,{plan:record.plan})); await run;
});

test('potential parts: invalid server context clears the old handoff and rechecks the displayed hypothesis before retry', async() => {
  const h = harness(), run = h.api.open(h.options()); h.requests[0].json(seed()); await tick();
  h.requests[1].result(planned()); await tick(); h.requests[2].fail('风险依据已改变','direct_sensor_context_invalid'); await run;
  assert.match(text(h.target),/风险分析依据已变化/);
  const again = h.api.open(h.options()); assert.equal(h.requests.length,4); assert.match(h.requests[3].url,/\/parts-handoff$/);
  h.requests[3].json(seed(0,{symptom:'已重新核验的风险方向'})); await tick();
  assert.match(h.requests[4].url,/\/plan$/); assert.equal(JSON.parse(h.requests[4].options.body).symptom,'已重新核验的风险方向');
  h.api.cancelAll(); h.requests[4].result(planned(0,{symptom:'已重新核验的风险方向'})); await again;
});

test('potential parts: stale reason or reordered hypotheses cannot start a plan for the displayed old risk', async() => {
  for (const changed of [hypothesis(0,{reason:'服务器已更新风险原因'}),hypothesis(1),
    hypothesis(0,{evidence_ids:['new-evidence']}),hypothesis(0,{inspection:'新检查顺序'}),undefined]) {
    const h = harness(), run = h.api.open(h.options());
    h.requests[0].json(seed(0,{hypothesis:changed})); await run;
    assert.equal(h.requests.length,1); assert.match(text(h.target),/风险分析已更新，请重新打开故障预测后选择对应方向/);
    assert.equal(all(h.target).filter(item => item.tag === 'button').length,0);
  }
});

test('potential parts: server-context retry cannot attach an updated or reordered risk to the old displayed card', async() => {
  for (const changed of [hypothesis(0,{reason:'更新后的原因'}),hypothesis(1)]) {
    const h = harness(), run = h.api.open(h.options()); h.requests[0].json(seed()); await tick();
    h.requests[1].result(planned()); await tick(); h.requests[2].fail('依据更新','direct_sensor_context_invalid'); await run;
    const again = h.api.open(h.options()); h.requests[3].json(seed(0,{hypothesis:changed})); await again;
    assert.equal(h.requests.length,4); assert.match(text(h.target),/风险分析已更新，请重新打开故障预测后选择对应方向/);
    assert.equal(h.requests.filter(item => /\/plan$/.test(item.url)).length,1,'the prior plan is never reused or replaced under a stale risk card');
  }
});

test('potential parts: key ordering is immaterial while the visible hypothesis snapshot cannot be mutated', async() => {
  const h = harness(), shown = hypothesis(), run = h.api.open(h.options({hypothesis:shown}));
  shown.reason = '调用方后来修改'; shown.search_terms.push('新方向');
  const reordered = Object.fromEntries(Object.entries(hypothesis()).reverse());
  h.requests[0].json(seed(0,{hypothesis:reordered})); await tick();
  assert.equal(h.requests.length,2); assert.match(h.requests[1].url,/\/plan$/);
  h.api.cancelAll(); h.requests[1].result(planned()); await run;
});

test('potential parts: changed displayed hypothesis does not reuse cached results under an unchanged analysis key', async() => {
  const h = harness(), {run} = await reachAnalyze(h); h.requests[3].result(analyzed()); await run;
  const again = h.api.open(h.options({hypothesis:hypothesis(0,{reason:'新显示的风险原因'})}));
  assert.equal(h.requests.length,5); assert.match(h.requests[4].url,/\/parts-handoff$/); assert.doesNotMatch(text(h.target),/800123456/);
  h.api.cancelAll(); h.requests[4].json(seed()); await again;
});

test('potential parts: revision-conflict retry reads only its own saved research and then rechecks sensor collection', async() => {
  const h = harness(), run = h.api.open(h.options()); h.requests[0].json(seed()); await tick();
  h.requests[1].result(planned()); await tick(); h.requests[2].fail('资料已更新','direct_revision_changed'); await run;
  const again = h.api.open(h.options());
  assert.equal(h.requests[3].url,`/assistant/xgss/research/${id}`); assert.equal(h.requests[3].options.method,'GET');
  h.requests[3].json(collected()); await tick();
  assert.match(h.requests[4].url,/\/collect-direct$/); assert.equal(JSON.parse(h.requests[4].options.body).expected_revision,1);
  assert.deepEqual(JSON.parse(h.requests[4].options.body).sensor_context,{series_id:series,hypothesis_index:0});
  h.requests[4].result(collected()); await tick(); h.requests[5].result(analyzed()); await again;
  assert.match(text(h.target),/800123456/); assert.equal(h.requests.filter(item => /\/plan$/.test(item.url)).length,1);
});

test('potential parts: images are bound to exact capture and validated local image IDs', async() => {
  const h = harness(), {run} = await reachAnalyze(h), otherCapture = '8'.repeat(64);
  const source = part({source_id:`xpart:${otherCapture}:0`,capture_id:otherCapture,name:'风扇',part_number:'800999111'});
  const data = analyzed();
  data.pages.push({capture_id:otherCapture,content:{vin:machine.serial_number},illustrations:[{image_id:'https://untrusted.invalid/image.png'}]});
  data.evidence.parts.push(source); data.advice.inspection_targets.push(source);
  data.advice.inspection_targets.push(part({capture_id:'9'.repeat(64),name:'无来源零件',part_number:'FAKE'}));
  h.requests[3].result(data); await run;
  const images = all(h.target).filter(item => item.tag === 'img');
  assert.equal(images.length,1); assert.match(images[0].src,new RegExp(`${id}/images/${imageId}$`));
  assert.match(text(h.target),/风扇/); assert.match(text(h.target),/对应分类尚未取得图示/); assert.doesNotMatch(text(h.target),/FAKE/);
  assert.match(text(h.target),/部分候选的图册来源无法核对/);
});

test('potential parts: two directions keep requests, research and output isolated', async() => {
  const h = harness(), target1 = element('div');
  const run0 = h.api.open(h.options()), run1 = h.api.open(h.options({target:target1,hypothesisIndex:1}));
  h.requests[0].json(seed(0)); h.requests[1].json(seed(1)); await tick();
  h.requests[2].result(planned(0)); h.requests[3].result(planned(1)); await tick();
  assert.equal(JSON.parse(h.requests[4].options.body).sensor_context.hypothesis_index,0);
  assert.equal(JSON.parse(h.requests[5].options.body).sensor_context.hypothesis_index,1);
  h.requests[4].result(collected(0)); h.requests[5].result(collected(1)); await tick();
  h.requests[6].result(analyzed(0));
  const data = analyzed(1); data.advice.summary = '变速箱独立方向'; h.requests[7].result(data);
  await Promise.all([run0,run1]); assert.doesNotMatch(text(h.target),/变速箱独立方向/); assert.match(text(target1),/变速箱独立方向/);
});

test('potential parts: cancelAll aborts requests and ignores their late completion', async() => {
  const h = harness(), run = h.api.open(h.options());
  h.requests[0].json(seed()); await tick();
  h.state.current = false; h.api.cancelAll(); assert.equal(h.requests[1].options.signal.aborted,true);
  h.requests[1].result(planned()); await run;
  assert.equal(h.requests.length,2); assert.doesNotMatch(text(h.target),/已找到|800123456/);
  h.state.current = true; const again = h.api.open(h.options());
  assert.equal(h.requests.length,3); assert.match(h.requests[2].url,/\/plan$/,'verified handoff survives cancellation');
  h.api.cancelAll(); h.requests[2].result(planned()); await again;
});

test('potential parts: isCurrent rejects late analysis after device or report changes', async() => {
  const h = harness(), {run} = await reachAnalyze(h);
  h.state.current = false; h.requests[3].result(analyzed()); await run;
  assert.doesNotMatch(text(h.target),/已找到|800123456/);
});

test('potential parts: analysis version changes never reuse prior risk candidates', async() => {
  const h = harness(), {run} = await reachAnalyze(h); h.requests[3].result(analyzed()); await run;
  const again = h.api.open(h.options({analysisKey:'analysis-v5'})); assert.equal(h.requests.length,5);
  assert.match(h.requests[4].url,/\/parts-handoff$/); assert.doesNotMatch(text(h.target),/800123456/);
  h.api.cancelAll(); h.requests[4].json(seed()); await again;
});

test('potential parts: mismatched handoff identity or direction never reaches plan', async() => {
  for (const changed of [{vin:'OTHER000000001'},{machine_id:'other'},{dataset_id:'9'.repeat(64)},{series_id:'9'.repeat(64)},
    {hypothesis_index:1},{symptom_source:'operator_report'}]) {
    const h = harness(), run = h.api.open(h.options()); h.requests[0].json(seed(0,changed)); await run;
    assert.equal(h.requests.length,1); assert.match(text(h.target),/不一致/);
  }
});

test('potential parts: fault-bound or changed-source plan never reaches collection', async() => {
  for (const changed of [{symptom_source:'operator_report'},{symptom:'其他风险'},{fault_event_id:'f'.repeat(64)},
    {manual_fault:{code:'E4030'}},{analysis_mode:'maintenance'}]) {
    const h = harness(), run = h.api.open(h.options()); h.requests[0].json(seed()); await tick();
    h.requests[1].result(planned(0,changed)); await run;
    assert.equal(h.requests.length,2); assert.match(text(h.target),/返回资料与本次风险问题不一致/);
  }
});

test('potential parts: changed research identity, source plan or revision never reaches analysis', async() => {
  for (const changed of [{research_id:'1'.repeat(32)},{vin:'OTHER000000001'},{revision:-1},
    {plan:{summary:'其他方向',directions:[]}}]) {
    const h = harness(), run = h.api.open(h.options()); h.requests[0].json(seed()); await tick();
    h.requests[1].result(planned()); await tick(); h.requests[2].result(collected(0,changed)); await run;
    assert.equal(h.requests.length,3); assert.match(text(h.target),/不一致/);
  }
});

test('potential parts: directory-only results have an explicit empty state and do not analyze', async() => {
  for (const parts of [[],[part({name:'XC948U 装载机'})],[part({name:'越野轮胎起重机'})]]) {
    const h = harness(), run = h.api.open(h.options()); h.requests[0].json(seed()); await tick();
    h.requests[1].result(planned()); await tick();
    h.requests[2].result(collected(0,{evidence:{parts,manuals:[]},direct_collection:{status:'partial',revision:1,unmatched_terms:['散热器'],unresolved:[]}}));
    await run; assert.equal(h.requests.length,3); assert.match(text(h.target),/暂未取得本项风险可核对的部件资料/);
    assert.match(text(h.target),/尚未完成：散热器/); assert.ok(all(h.target).some(item => item.textContent === '继续读取图册'));
  }
});

test('potential parts: stale analysis revision stays hidden and can retry from saved sources', async() => {
  const h = harness(), {run} = await reachAnalyze(h); h.requests[3].result(analyzed(0,{analysis_revision:0})); await run;
  assert.doesNotMatch(text(h.target),/800123456/); assert.match(text(h.target),/资料版本不一致/);
  const again = h.api.open(h.options()); assert.match(h.requests[4].url,/\/analyze$/);
  h.requests[4].result(analyzed()); await again; assert.match(text(h.target),/800123456/);
});

test('potential parts: duplicates share one card while their separate preparation conditions are retained', async() => {
  const h = harness(), {run} = await reachAnalyze(h), data = analyzed();
  data.advice.parts = [part({reason:'补充理由',replacement_condition:'同时核对接插件与管路'})];
  h.requests[3].result(data); await run;
  assert.equal(all(h.target).filter(item => item.className === 'sensor-parts-card').length,1);
  assert.match(text(h.target),/芯体堵塞及泄漏/); assert.match(text(h.target),/同时核对接插件与管路/);
});

test('potential parts: no grounded candidates is explicit and a broken picture retains candidate text', async() => {
  const h = harness(), {run} = await reachAnalyze(h); h.requests[3].result(analyzed()); await run;
  all(h.target).find(item => item.tag === 'img').onerror(); assert.match(text(h.target),/图示加载失败/); assert.match(text(h.target),/800123456/);
  const other = harness(), next = await reachAnalyze(other);
  other.requests[3].result(analyzed(0,{advice:{summary:'证据不足',parts:[],inspection_targets:[],analysis_scope:'current'}})); await next.run;
  assert.match(text(other.target),/暂未匹配到可核对料号的潜在配件/); assert.equal(all(other.target).filter(item => item.className === 'sensor-parts-card').length,0);
});

test('repair: twelve planned terms cannot remove the selected risk seed terms', async() => {
  const h = harness(), run = h.api.open(h.options()); h.requests[0].json(seed()); await tick();
  const record = planned(); record.plan.directions = Array.from({length:3},(_,i) => ({search_terms:Array.from({length:4},(_,j) => `方向${i*4+j}`)}));
  h.requests[1].result(record); await tick();
  const body = JSON.parse(h.requests[2].options.body);
  assert.equal(body.terms.length,12); assert.ok(body.terms.includes('散热器')); assert.equal(body.force_refresh,undefined);
  h.api.cancelAll(); h.requests[2].result(collected(0,{plan:record.plan})); await run;
});

test('repair: no-match narrows to risk seed once, then gives an accurate empty result and explicit fresh retry', async() => {
  const h = harness(), run = h.api.open(h.options()); h.requests[0].json(seed()); await tick();
  const record = planned(); record.plan.directions[0].search_terms = ['冷却系统','风扇','散热器'];
  h.requests[1].result(record); await tick();
  assert.deepEqual(JSON.parse(h.requests[2].options.body).terms,['冷却系统','风扇','散热器']);
  h.requests[2].fail('尚未匹配，可使用网页继续查找','direct_no_match'); await tick();
  assert.equal(h.requests.length,4); assert.deepEqual(JSON.parse(h.requests[3].options.body).terms,['散热器']);
  assert.equal(JSON.parse(h.requests[3].options.body).force_refresh,undefined);
  h.requests[3].fail('仍未匹配','direct_no_match'); await run;
  assert.equal(h.requests.length,4); assert.match(text(h.target),/尚未在该设备图册中匹配到本项风险的配件分类/);
  assert.match(text(h.target),/已保留本项风险与检索方向，尚未读取到图册资料/);
  assert.doesNotMatch(text(h.target),/已成功读取|网页继续查找/);
  const retry = all(h.target).find(item => item.textContent === '重新查找图册').onclick();
  assert.equal(h.requests.length,5); assert.equal(JSON.parse(h.requests[4].options.body).force_refresh,true);
  assert.doesNotMatch(text(h.target),/尚未在该设备图册中匹配/,'old error clears before retry');
  h.requests[4].result(collected(0,{plan:record.plan})); await tick();
  h.requests[5].result(analyzed(0,{plan:record.plan})); await retry;
  assert.match(text(h.target),/已找到 1 项/); assert.doesNotMatch(text(h.target),/仍未匹配|尚未读取到图册资料/);
  assert.equal(h.requests.filter(item => /\/plan$/.test(item.url)).length,1);
});

test('repair: no-match does not reissue an identical set of terms in a different order', async() => {
  const h = harness(), run = h.api.open(h.options()); h.requests[0].json(seed()); await tick();
  h.requests[1].result(planned()); await tick(); h.requests[2].fail('无匹配','direct_no_match'); await run;
  assert.equal(h.requests.length,3); assert.ok(all(h.target).some(item => item.textContent === '重新查找图册'));
});

test('repair: partial candidates stay visible while explicit refresh gets new diagrams and replaces the old result', async() => {
  const h = harness(), {run} = await reachAnalyze(h), first = analyzed();
  first.pages[0].illustrations = []; first.direct_collection.status = 'partial'; first.direct_collection.unresolved = ['图纸提取失败'];
  h.requests[3].result(first); await run;
  assert.match(text(h.target),/800123456/); assert.match(text(h.target),/尚未取得图示/); assert.equal(all(h.target).filter(item => item.tag === 'img').length,0);
  const refreshing = all(h.target).find(item => item.textContent === '补充图册与图示').onclick();
  assert.match(text(h.target),/800123456/,'prior candidates stay visible while re-reading');
  assert.match(h.requests[4].url,/\/collect-direct$/); assert.equal(JSON.parse(h.requests[4].options.body).force_refresh,true);
  assert.equal(JSON.parse(h.requests[4].options.body).expected_revision,1);
  const fresh = collected(0,{revision:2,direct_collection:{status:'completed',revision:2,unmatched_terms:[],unresolved:[]}});
  fresh.pages[0].illustrations = [{image_id:'7'.repeat(64),title:'补充的同分类图示'}];
  h.requests[4].result(fresh); await tick(); assert.match(h.requests[5].url,/\/analyze$/);
  const newResult = {...fresh,analysis_revision:2,advice:{...first.advice,inspection_targets:[part({reason:'图示补充后的核查理由'})]}};
  h.requests[5].result(newResult); await refreshing;
  const images = all(h.target).filter(item => item.tag === 'img'); assert.equal(images.length,1);
  assert.equal(images[0].src,`/assistant/xgss/research/${id}/images/${'7'.repeat(64)}`);
  assert.match(text(h.target),/图示补充后的核查理由/); assert.doesNotMatch(text(h.target),/尚未取得图示|图纸提取失败/);
  assert.equal(all(h.target).filter(item => item.className === 'sensor-parts-card').length,1);
  assert.ok(h.requests.every(item => !/activate|\/active|\/latest/.test(item.url)));
});

test('repair: failed image extraction retains existing candidate cards and accurately distinguishes an empty first attempt', async() => {
  const h = harness(), {run} = await reachAnalyze(h), first = analyzed(); first.pages[0].illustrations = [];
  h.requests[3].result(first); await run;
  const refresh = all(h.target).find(item => item.textContent === '补充图册与图示').onclick();
  h.requests[4].fail('图纸提取失败','direct_image'); await refresh;
  assert.match(text(h.target),/800123456/); assert.match(text(h.target),/已读取的图册资料仍保留/); assert.match(text(h.target),/下方仍为上次候选結果|下方仍为上次候选结果/);
  const other = harness(), empty = other.api.open(other.options()); other.requests[0].json(seed()); await tick();
  other.requests[1].result(planned()); await tick(); other.requests[2].fail('图纸提取失败','direct_image'); await empty;
  assert.match(text(other.target),/尚未读取到图册资料/); assert.doesNotMatch(text(other.target),/已成功读取|已读取的图册资料仍保留/);
});

test('repair: image load failure retains part identity and retry actually reloads that same local image', async() => {
  const h = harness(), {run} = await reachAnalyze(h); h.requests[3].result(analyzed()); await run;
  const image = all(h.target).find(item => item.tag === 'img'); image.onerror();
  assert.match(text(h.target),/图示加载失败；配件料号与来源仍保留/); assert.match(text(h.target),/800123456/);
  const retry = all(h.target).find(item => item.textContent === '重试图示'); assert.equal(retry.hidden,false); retry.onclick();
  assert.equal(retry.disabled,true); assert.equal(image.src,`/assistant/xgss/research/${id}/images/${imageId}?retry=1`);
  assert.equal(h.requests.length,4,'an image retry does not re-run model or catalog requests');
  image.onload(); assert.equal(retry.hidden,true); assert.doesNotMatch(text(h.target),/图示加载失败|正在重新加载/);
});

test('repair: sensor context changing during collection revalidates handoff before any retry', async() => {
  const h = harness(), run = h.api.open(h.options()); h.requests[0].json(seed()); await tick(); h.requests[1].result(planned()); await tick();
  h.requests[2].fail('保存前风险分析变更','direct_sensor_context_changed'); await run;
  assert.match(text(h.target),/风险分析依据已变化/); const retry = h.api.open(h.options());
  assert.match(h.requests[3].url,/\/parts-handoff$/);
  h.requests[3].json(seed(0,{hypothesis:hypothesis(0,{reason:'新分析原因'})})); await retry;
  assert.equal(h.requests.length,4); assert.match(text(h.target),/风险分析已更新/);
});
