const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const {formatDeepSeekFailure,formatGeminiQuotaFailure}=require('../app/assistant_ui/assistant-errors.js');
const source=fs.readFileSync(path.join(__dirname,'../app/assistant_ui/app.js'),'utf8');
const apiFunction=source.slice(source.indexOf('async function api('),source.indexOf('\nfunction setView('));
function setup(data,provider='deepseek'){
  const statuses=[];
  const context={fetch:async()=>({ok:false,status:503,json:async()=>data}),aiProvider:provider,
    formatDeepSeekFailure,formatGeminiQuotaFailure,applyAIRequestStatus:value=>statuses.push(value)};
  vm.runInNewContext(apiFunction,context);
  return {request:context.api,statuses};
}
test('investigation uses structured DeepSeek failure and records status without exposing upstream text',async()=>{
  const data={detail:'private upstream text',provider_error:{kind:'insufficient_balance'},ai_status:{provider:'deepseek'}};
  const app=setup(data);
  await assert.rejects(app.request('/assistant/investigate'),error=>{
    assert.match(error.message,/DeepSeek API 账户余额不足/);assert.doesNotMatch(error.message,/private|Gemini/);
    assert.equal(error.status,503);return true;
  });
  assert.deepEqual(app.statuses,[data.ai_status]);
});
test('existing Gemini quota responses remain Gemini-specific after provider switch',async()=>{
  const app=setup({detail:'Gemini API quota exceeded',provider_error:{kind:'daily_quota'},ai_status:{provider:'gemini'}});
  await assert.rejects(app.request('/assistant/investigate'),/Gemini 已达到当前项目与模型的每日额度/);
});
test('manual input errors are retained rather than mislabeled as DeepSeek failures',async()=>{
  const app=setup({detail:'请先确认故障码适用范围。'});
  await assert.rejects(app.request('/assistant/investigate'),/请先确认故障码适用范围/);
  assert.equal(app.statuses.length,0);
});
