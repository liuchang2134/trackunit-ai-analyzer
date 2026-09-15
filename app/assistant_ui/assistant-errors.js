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
function formatDeepSeekFailure(error) {
  const messages={
    configuration_missing:'尚未配置 DeepSeek 密钥。请更新后端密钥配置后重启本机服务；模拟数据、趋势图和预警演示仍可使用。',
    configuration_invalid:'DeepSeek 请求配置或格式不匹配。请检查后端的模型与接口设置；本次未生成报告。',
    authentication:'DeepSeek 密钥认证失败。请核查后端配置的有效密钥；本次未生成报告。',
    insufficient_balance:'DeepSeek API 账户余额不足。请核查 API 账户余额；等待或反复重试不会补充余额。本次未生成报告。',
    rate_limit:'DeepSeek 调用频率受限。请降低请求频率后再手动尝试；等待不保证下一次请求成功。本次未生成报告。',
    service_unavailable:'DeepSeek 服务暂时不可用。请稍后重试；本次未生成报告。',
    timeout:'DeepSeek 请求超时，本次未生成报告。问题和设备数据已保留，可稍后重试。',
    network:'DeepSeek 网络连接失败。请检查网络后重试；本次未生成报告。',
    invalid_response:'DeepSeek 返回的结果未通过证据与格式校验，本次未生成报告。请缩小排查范围后重试。',
    analysis_incomplete:'DeepSeek 未给出符合证据要求的完整报告。请缩小排查范围后重试。'
  };
  return Object.hasOwn(messages,error?.kind)?messages[error.kind]:'DeepSeek 排查未完成。问题和设备数据已保留；仍可查看本机设备、故障资料和备件目录。';
}
if(typeof module!=='undefined')module.exports={formatGeminiQuotaFailure,formatDeepSeekFailure};
