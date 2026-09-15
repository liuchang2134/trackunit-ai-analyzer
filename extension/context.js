/* Pure URL validation; never forwards query parameters, fragments or page text. */
function trackunitAssetId(value) {
  try {
    const url=new URL(value);
    if(url.protocol!=='https:' || url.username || url.password || url.port ||
       !['new.manager.trackunit.com','manager.trackunit.com'].includes(url.hostname))return null;
    const match=url.pathname.match(/^\/assets\/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})(?:\/|$)/i);
    return match ? match[1].toLowerCase() : null;
  }catch{return null;}
}
function trackunitContextLabel(data,expectedId){
  if(!expectedId||data.asset_id!==expectedId)return null;
  const labels={pending:'正在完成上一项操作，尚未切换到此设备。',loading:'正在读取该设备的本地数据…',
    unavailable:'设备数据读取失败，尚未确认关联。请在下方刷新设备。',missing:'该平台设备没有对应的本地实测数据，请先同步或导入。',
    choose_version:'该设备的数据版本尚未选定，请在下方选择。'};
  if(Object.prototype.hasOwnProperty.call(labels,data.state))return labels[data.state];
  if(data.state!=='matched'||data.machine_id!==expectedId)return null;
  if(data.source==='trackunit_cache'&&data.dataset_id===null&&data.selection_id==='fleet:'+expectedId)
    return '已关联此平台设备 · 本地真实缓存。请在下方核对机型与采样时间。';
  if(data.source==='imported_user_supplied'&&/^[a-f0-9]{64}$/.test(data.dataset_id||'')&&data.selection_id==='dataset:'+data.dataset_id)
    return '已关联此平台设备 · 导入实测版本 '+data.dataset_id.slice(0,8)+'（未验证）。';
  return null;
}
if(typeof module!=='undefined')module.exports={trackunitAssetId,trackunitContextLabel};
