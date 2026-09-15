function formatGeminiQuotaFailure(error) {
  if(!error || typeof error!=='object')return null;
  if(error.kind==='quota_unavailable')return 'Google 返回该模型的可用配额为 0，短暂等待不能确认恢复。请核查 Gemini 项目配额；仍可查看本机设备、故障资料和备件目录。本次未生成报告。';
  const limits=Array.isArray(error.limits)?error.limits:[];
  if(error.kind==='daily_quota') {
    const requests=limits.find(item=>item?.window==='day' && item?.measure==='requests' && Number.isSafeInteger(item?.limit) && item.limit>=0);
    return `Gemini 已达到当前项目与模型的每日额度${requests?`（每日请求上限 ${requests.limit} 次）`:''}。`
      +(requests?'每日请求额度按太平洋时间零点重置；':'请在 Gemini 项目中核查恢复时间；')
      +'短暂等待或反复点击不能恢复每日额度。仍可查看本机设备、故障资料和备件目录。本次未生成报告。';
  }
  if(error.kind==='minute_quota')return 'Gemini 已达到每分钟调用或输入额度。'
    +(Number.isSafeInteger(error.retry_after_seconds) && error.retry_after_seconds>=0?`Google 建议至少等待 ${error.retry_after_seconds} 秒后再手动尝试；`:'请降低请求频率后再手动尝试；')
    +'等待不保证下一次请求成功。本次未生成报告。';
  if(error.kind==='quota_unknown')return 'Gemini 返回额度限制，但未提供可确认的限额类别。请核查 API 项目额度，暂不要反复重试。本次未生成报告。';
  return null;
}
if(typeof module!=='undefined')module.exports={formatGeminiQuotaFailure};
