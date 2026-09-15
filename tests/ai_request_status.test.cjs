const test=require('node:test'),assert=require('node:assert/strict');
const {view,runtimeView,providerName}=require('../app/assistant_ui/ai-request-status.js');
const base={configured:true,record_state:'available',last_attempt:{finished_at:'2026-09-14T09:41:15Z',
  outcome:'failed',failure:{kind:'daily_quota',detail:'private response'},source:'application',configuration_match:true}};
test('daily status is historical and never promises quota recovery',()=>{
  const result=view(base);assert.match(result.title,/每日额度/);assert.match(result.detail,/不代表当前可用性/);
  assert.match(result.detail,/不表示额度已恢复/);assert.doesNotMatch(JSON.stringify(result),/private/);
});
test('prior verification is not attributed to current configuration',()=>{
  const result=view({...base,last_attempt:{...base.last_attempt,source:'prior_verification',configuration_match:false,older_than_24h:true}});
  assert.match(result.title,/此前联调/);assert.match(result.detail,/当前配置尚未核验/);assert.match(result.detail,/超过 24 小时/);
});
test('configured key, unknown or changed record never claims live availability',()=>{
  assert.match(view({configured:true,record_state:'other_configuration'}).title,/配置已变化/);
  assert.match(view({configured:true,record_state:'missing'}).detail,/不代表请求一定成功/);
  assert.match(view({configured:false}).title,/密钥未配置/);
  assert.match(view(null).title,/无法读取/);
});
test('saved and unsaved reports remain distinct; failures cannot invent completed output',()=>{
  const saved=view({...base,last_attempt:{...base.last_attempt,outcome:'report_saved',failure:null}});
  const unsaved=view({...base,recording_saved:false,last_attempt:{...base.last_attempt,outcome:'report_unsaved',failure:null}});
  assert.match(saved.title,/已生成并保存/);assert.match(saved.detail,/不代表当前可用性/);
  assert.match(unsaved.title,/保存失败/);assert.match(unsaved.detail,/未写入本机记录/);
  assert.doesNotMatch(view(base).title,/报告已生成/);
});
test('malformed timestamp and unknown error payload do not become visible instructions',()=>{
  assert.match(view({...base,last_attempt:{...base.last_attempt,finished_at:'bad'}}).title,/无可核验/);
  const result=view({...base,last_attempt:{...base.last_attempt,failure:{kind:'<script>private</script>'}}});
  assert.match(result.title,/未完成/);assert.doesNotMatch(JSON.stringify(result),/script|private/);
});
test('DeepSeek runtime labels identify cloud destination without claiming successful inference',()=>{
  const runtime={provider:'deepseek',model:'deepseek-flash',inference_location:'cloud',
    cloud_credentials_configured:true,investigation_timeout_seconds:120,transient_attempt_limit:3};
  const result=runtimeView(runtime);
  assert.match(result.label,/DeepSeek.*deepseek-flash/);assert.match(result.footer,/DeepSeek 云端推理/);
  assert.match(result.note,/发送至 DeepSeek/);assert.match(result.note,/120 秒/);
  assert.doesNotMatch(JSON.stringify(result),/Gemini|请求已成功|认证成功/);
  assert.match(runtimeView({...runtime,cloud_credentials_configured:false}).label,/DeepSeek 密钥未配置/);
  assert.match(runtimeView({...runtime,provider:'gemini',model:'gemini-flash-latest'}).note,/发送至 Gemini/);
  const local=runtimeView({provider:'ollama_local',model:'qwen',inference_location:'local'});
  assert.match(local.note,/运行于本机/);assert.doesNotMatch(local.note,/发送至|120/);
});
test('provider status separates balance, rate limits and missing credentials',()=>{
  assert.equal(view({provider:'deepseek',configured:false}).title,'DeepSeek 密钥未配置');
  assert.equal(view({provider:'gemini',configured:false}).title,'Gemini 密钥未配置');
  const balance=view({...base,provider:'deepseek',last_attempt:{...base.last_attempt,failure:{kind:'insufficient_balance',detail:'private'}}});
  assert.match(balance.title,/余额不足/);assert.match(balance.detail,/不会补充余额/);
  assert.doesNotMatch(JSON.stringify(balance),/Gemini|每日额度|private/);
  const rate=view({...base,provider:'deepseek',last_attempt:{...base.last_attempt,failure:{kind:'rate_limit'}}});
  assert.match(rate.title,/调用频率受限/);assert.match(rate.detail,/降低请求频率/);
  assert.equal(providerName('constructor'),'AI');
  assert.match(view({...base,last_attempt:{...base.last_attempt,failure:{kind:'constructor'}}}).title,/未完成/);
});
