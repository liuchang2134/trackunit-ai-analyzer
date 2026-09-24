/* Public status copy is built from bounded categories, never raw upstream text. */
const AIRequestStatus = (()=>{
  const failureNames={daily_quota:'每日额度限制',minute_quota:'每分钟额度限制',quota_unavailable:'配额不可用',
    quota_unknown:'额度受限，类别未确认',configuration_missing:'密钥未配置',configuration_invalid:'请求配置或格式不匹配',
    authentication:'认证失败',service_unavailable:'服务暂不可用',network:'网络连接失败',timeout:'请求超时',
    insufficient_balance:'API 账户余额不足',rate_limit:'调用频率受限',
    invalid_response:'返回结果未通过校验',analysis_incomplete:'未得到完整报告'};
  function providerName(provider){
    const names={deepseek:'DeepSeek',gemini:'Gemini',ollama_local:'本地模型'};
    return Object.hasOwn(names,provider)?names[provider]:'AI';
  }
  function runtimeView(runtime){
    const cloud=runtime.inference_location==='cloud',name=providerName(runtime.provider);
    const model=typeof runtime.model==='string'?runtime.model:'模型未确认';
    const bounded=runtime.investigation_timeout_seconds===120 && runtime.transient_attempt_limit===3;
    return {
      label:cloud && runtime.cloud_credentials_configured===false
        ?`${name} 密钥未配置 · 设备资料可查`
        :`${cloud?name+' 云端推理':'本机推理'} · ${model}`,
      footer:`${cloud?name+' 云端推理':'本机推理'} · 只读辅助分析 · 报告保存在本机`,
      note:cloud?`分析时会将所选设备的证据和输入内容发送至 ${name}，报告保存在本机。`
        +(bounded?'单次排查最长等待 120 秒。':'')
        :'分析与模型推理运行于本机。'
    };
  }
  function view(data){
    const local='已载入的运行数据、故障资料和备件目录仍可查看。';
    if(!data)return {title:'请求状态暂时无法读取',tone:'warning',time:null,detail:'没有进行 AI 调用。'+local};
    if(data.configured===false)return {title:providerName(data.provider)+' 密钥未配置',tone:'warning',time:null,
      detail:'完整 AI 排查需要后端配置有效密钥。'+local};
    if(data.record_state==='unsupported_configuration')return {title:'AI 配置无法识别',tone:'warning',time:null,detail:local};
    const last=data.last_attempt;
    if(!last || !Number.isFinite(Date.parse(last.finished_at)))return {
      title:data.record_state==='other_configuration'?'配置已变化，尚无对应排查记录':'尚无可核验的完整排查记录',
      tone:'neutral',time:null,detail:'当前配置尚未完成分析验证。'};
    const prior=last.source==='prior_verification' || last.configuration_match!==true;
    const prefix=prior?'此前配置的记录：':'最近一次排查：';
    let title, tone='neutral';
    if(last.outcome==='report_saved')title=prefix+'报告已生成并保存';
    else if(last.outcome==='report_unsaved'){title=prefix+'报告已生成，保存失败';tone='warning';}
    else if(last.outcome==='failed'){title=prefix+(Object.hasOwn(failureNames,last.failure?.kind)?failureNames[last.failure.kind]:'未完成');tone='warning';}
    else return {title:'排查记录无法识别',tone:'warning',time:null,detail:local};
    let detail=prior?'对应当时配置；当前配置尚未核验。':'这是上次完整排查的结果，不代表当前可用性。';
    if(last.older_than_24h)detail+='记录已超过 24 小时。';
    if(['daily_quota','quota_unavailable'].includes(last.failure?.kind))detail+='请在服务商账户查看可用额度。';
    if(last.failure?.kind==='insufficient_balance')detail+='请核查 API 账户余额。';
    if(last.failure?.kind==='rate_limit')detail+='请降低请求频率后再手动尝试。';
    if(data.recording_saved===false)detail+='本次状态未写入本机记录，刷新后可能缺失。';
    if(last.outcome!=='report_saved')detail+=local;
    return {title,tone,time:last.finished_at,detail};
  }
  return {view,providerName,runtimeView};
})();
if(typeof module!=='undefined')module.exports=AIRequestStatus;
