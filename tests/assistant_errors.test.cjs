const {test}=require('node:test');
const assert=require('node:assert/strict');
const {formatGeminiQuotaFailure:format,formatDeepSeekFailure}=require('../app/assistant_ui/assistant-errors.js');

test('daily request limit explains recovery without short retry instruction',()=>{
 const text=format({kind:'daily_quota',limits:[{window:'day',measure:'requests',limit:20}],retry_after_seconds:44});
 assert.match(text,/每日请求上限 20 次/);assert.match(text,/太平洋时间零点/);
 assert.match(text,/本机设备、故障资料和备件目录/);assert.doesNotMatch(text,/44/);
});
test('daily token limit is not displayed as a request count',()=>{
 const text=format({kind:'daily_quota',limits:[{window:'day',measure:'tokens',limit:10000}]});
 assert.doesNotMatch(text,/请求上限|10000|零点/);assert.match(text,/核查恢复时间/);
});
test('minute quota and zero quota need different actions',()=>{
 const minute=format({kind:'minute_quota',retry_after_seconds:5});
 assert.match(minute,/至少等待 5 秒/);assert.match(minute,/不保证/);
 const zero=format({kind:'quota_unavailable',retry_after_seconds:5});
 assert.match(zero,/配额为 0/);assert.doesNotMatch(zero,/等待 5 秒/);
});
test('unstructured limits stay unknown and arbitrary data is not echoed',()=>{
 assert.equal(format(null),null);assert.equal(format({kind:'private'}),null);
 assert.match(format({kind:'quota_unknown'}),/未提供可确认/);
 assert.doesNotMatch(format({kind:'daily_quota',limits:[{window:'day',measure:'requests',limit:'private'}]}),/private/);
});
test('DeepSeek balance and rate limit errors suggest distinct actions without Gemini quota claims',()=>{
 const balance=formatDeepSeekFailure({kind:'insufficient_balance',message:'secret upstream body'});
 assert.match(balance,/DeepSeek API 账户余额不足/);assert.match(balance,/不会补充余额/);
 assert.doesNotMatch(balance,/Gemini|每日|secret/);
 const rate=formatDeepSeekFailure({kind:'rate_limit',retry_after_seconds:5});
 assert.match(rate,/降低请求频率/);assert.match(rate,/不保证/);assert.doesNotMatch(rate,/每日|零点|余额不足/);
});
test('DeepSeek error copy is bounded and never displays raw upstream data',()=>{
 for(const kind of ['configuration_missing','configuration_invalid','authentication','service_unavailable','timeout','network','invalid_response','analysis_incomplete','secret','constructor']){
   const result=formatDeepSeekFailure({kind,message:'secret upstream body'});
   assert.equal(typeof result,'string');assert.match(result,/DeepSeek/);assert.doesNotMatch(result,/secret|Gemini|function/);
 }
 assert.match(formatDeepSeekFailure(null),/未完成/);
});
