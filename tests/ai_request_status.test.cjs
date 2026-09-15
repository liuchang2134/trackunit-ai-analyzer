const test=require('node:test'),assert=require('node:assert/strict');
const {view}=require('../app/assistant_ui/ai-request-status.js');
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
