# Trackunit 快照时间与零值处理

2026-09-14 修复：
- 数字零和布尔 false 不再触发缺失值回退；适用于工时、怠速、燃油、坐标以及 SPN/FMI。
- 支持 Metadata/metadata 的 AssetId/assetId 和 MachineId/machineId。设备与遥测使用相同身份解析；保留平台 ID 与设备编号的区别。
- 各 AEMP 字段按自身 datetime 拆分成独立记录；只有同一 UTC 时刻的字段才合并，不插值，不借用 GPS 时间。缺少有效时区时间的值保留为未知时间，下游趋势不能用于区间计算。
- 字段明确为 null 时不从别名补造数值。createdAt/updatedAt 不当作设备上报时间；last_seen_at 使用显式 lastSeenAt 与支持的遥测字段中最新的有效观测时间。
- 不把显示名称当作整机序列号；位置字符串和位置对象分别处理。

依据：Trackunit 官方 AEMP OpenAPI https://developers.trackunit.com/openapi/aemp-iso-api.json 定义 Location、CumulativeOperatingHours、FuelRemaining、EngineStatus 等字段各自的 datetime。

入库及直接读取路径均使用 normalize_trackunit_telemetry_series。旧单记录函数仅返回最新时点作为兼容视图，不会将较旧字段搬到最新时间。旧缓存与旧数据库行不自动改写；后续同步使用新逻辑。当前 /assistant 的已导入历史数据使用独立 AEMP 时序规范化，不受此次快照拆分影响。

离线复核已授权的原始快照第一页：100 台设备展开为 193 条不同观测时间的记录，50 台包含多个时点，100 台均有平台 ID 且设备/遥测对应一致，13 个数值零得到保留。只记录统计结果，真实原始资料留在 data/local 中。此检查验证转换行为，不证明原始上报完整或准确，也不代表重新查询了平台。
