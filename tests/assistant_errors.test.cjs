const {test}=require('node:test');
const assert=require('node:assert/strict');
const {formatGeminiQuotaFailure:format}=require('../app/assistant_ui/assistant-errors.js');

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
