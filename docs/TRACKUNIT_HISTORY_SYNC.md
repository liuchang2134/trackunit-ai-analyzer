# Trackunit 历史同步

使用本地 `.env` 中现有 v2 凭据；命令行无需填写密钥。输入是带 `EquipmentHeader` 和 `metadata` 的单设备 AEMP 快照，必须包含 PIN/VIN/终端序列号、机型和 `metadata.assetId`。

安装包默认模拟模式，不附带账户配置和已登记真实设备。在本地 .env 增加 TRACKUNIT_CLIENT_ID、TRACKUNIT_CLIENT_SECRET，填写自己已授权的凭据。默认认证地址为 https://auth.trackunit.com/token/v2，client_credentials，默认 scope 为 api.iso15143.snapshot api.iso15143.timeseries asset.view account.event.view；实际权限以账户授权为准。显式同步不要求启用后台自动同步。

先运行 `.venv/Scripts/python.exe scripts/sync_trackunit_history.py --help` 检查入口，不会发起接口查询。下面 selected.json 是用户保存的单设备响应，包内没有这个私有文件，需改成实际路径；日期需改成过去且不超过 14 天的范围。

在项目根目录运行（日期为示例，按需要修改，均含时区）：

```powershell
.venv/Scripts/python.exe scripts/sync_trackunit_history.py --snapshot-file data/local/trackunit-probe/selected.json --start 2026-09-07T00:00:00Z --end 2026-09-14T00:00:00Z
```

此命令只读取指定设备的累计工时和累计怠速工时，查询窗口最多14天，不得包含未来时间。AEMP 的 OEM 标识与 asset ID 分开使用；前者用于 URL，后者用于本地设备关联。

结果保存为独立实测数据集，并更新“数据与备件库”的上次核验状态。刷新设备列表可选新数据集。相同规范化内容采用内容哈希去重，不覆盖已有车队缓存。

每次尝试前记录本地时间，同一设备15分钟内再次执行会被拒绝；失败请求同样计入等待时间。脚本不自动重试，不调用故障事件接口。故障状态因此显示“未核验”，不能据此判断无故障。该命令也不能修复权限不足或供应商侧限流。

空响应与读取失败分别保留为空数据和错误。一个工时通道失败时，另一个通道仍可导入；两者均无数据时不创建空数据集。不会插值、填零或把不同时间的计数器强行对齐。原始错误正文不会打印。

进程异常终止可能留下 `data/local/sync-state/*.lock`；确认没有同步进程运行后再清理对应锁，保留 `.last-attempt` 文件以遵守请求间隔。

仓库开发环境验证命令（发布包不含 tests 目录）：

```powershell
.tmp/venv/Scripts/python.exe -m pytest tests/test_history_sync.py tests/test_aemp_history.py -q
```

2026年9月14日正式命令已完成真实端到端验证：读取36条工时记录，怠速返回空数据，创建独立数据集并更新核验状态；运行中的数据集API可读取结果。界面已提供同步入口；重复请求的实际浏览器拦截已验证。完整故障事件适配仍未交付。

## 网页入口
2026-09-14 网页成功同步分支已实际验证：最近 7 天查询返回 36 条工时，怠速为空，自动选中实测数据集；故障事件保持未核验。详见 evaluation/2026-09-14-ui-history-sync-success.md。

在“数据与备件库”选择已登记的真实设备和最近1、7或14天，点击“同步历史数据”。成功后选择新数据集；无可用数据时查看接口结果。设备登记文件放在本机 data/local/history-sources，以64位十六进制名称保存单设备快照；该目录不提交Git。目前已登记一台经授权核验的设备，尚无网页设备登记功能。浏览器不能传入任意文件路径或API地址。CLI与网页复用同一后台同步逻辑和请求间隔记录。
