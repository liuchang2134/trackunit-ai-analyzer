# Trackunit 与 XGSS API 解析

依据：Trackunit 官方文档、已保存的 Asset Event OpenAPI、用户提供的 2025-03-10 XGSS 接口说明及 RSA.txt、后续生产地址和页面截图说明，以及本项目既有测试记录。初次记录仅解析资料；2026-09-15 03:40 UTC 已补充 XGSS 六参数生产认证成功证据，当前状态见 [XGSS 对接说明](XGSS_INTEGRATION.md)。

## 两套接口的分工

| 系统 | 提供什么 | 本项目如何使用 |
| --- | --- | --- |
| Trackunit | 设备身份、遥测历史、故障事件等结构化数据 | 趋势分析、故障证据、AI 排查输入 |
| XGSS | 根据设备与故障上下文返回官方资料页面地址 | 内嵌手册或整机图册，供用户查阅核对 |
| 本项目 | 设备关联、数据整理、AI 分析、检查反馈与历史记录 | 将两套系统的能力组织到同一工作流 |

“协议能够解析”“账号能访问”“完整功能已接通”分别需要不同证据。已有资料足以确定主流程，并不是所有细节都未知。

## Trackunit

### 认证

`POST https://auth.trackunit.com/token/v2`，表单编码 `application/x-www-form-urlencoded`。

字段为 `grant_type=client_credentials`、`client_id`、`client_secret` 和空格分隔的 `scope`。本项目沿用接口方建议的四项读取范围：

```text
api.iso15143.snapshot api.iso15143.timeseries asset.view account.event.view
```

成功后使用返回的 `access_token` 发起 `Authorization: Bearer ...` 请求。有效期以 `expires_in` 为准；官方示例 1200 秒即 20 分钟。到期重新申请 token，不需要用户每 20 分钟重新登录，也不是分析任务需要运行 20 分钟。此流程没有 refresh token。[官方认证说明](https://developers.trackunit.com/reference/access-token-v2)

### 设备与工时

`assetId` 是平台设备 UUID，VIN/PIN 是制造商设备标识，二者需要通过已核实的设备元数据关联。累计工时历史使用单设备 AEMP GET 接口，时间区间最长 14 天。[累计工时接口](https://developers.trackunit.com/docs/api-reference/aemp-iso-api/get-cumulative-operating-hours-time-series/)

本项目既有实测中，同一 token 获取累计工时返回 HTTP 200、36 条记录。该结果只证明当时该设备的该接口可用，不证明所有遥测字段或故障接口均可访问。本机历史验收记录，不随源码分发：`docs/evaluation/2026-09-14-trackunit-fault-access.json`。

### 故障事件

```text
POST https://iris.trackunit.com/public/api/eventlog/v3/asset-event/log
```

JSON 过滤使用 `fromTime`、`toTime`、`assetIds` 和 `type: ["MACHINE_FAULT"]`；分页在查询参数 `page`、`size` 中。不能把这个接口套进通用 GET 模板。

返回 `content` 事件列表及分页信息。解析重点为 `assetId`、`id`、`status`、时间字段，以及 `assetEventDomainDetails` 下的 `faultCode`、`description`、`j1939`；后者可含 `spn`、`fmi`、`sa`。字段缺失时保留未知，不补造故障码。[官方事件定义](https://developers.trackunit.com/openapi/asset-event-api.json)

官方限制为每个 API 用户每 30 分钟最多 2 次请求，应缓存结果，避免页面刷新触发反复请求。[接口概览](https://developers.trackunit.com/docs/api-reference/asset-event-api/asset-event-api/)

此前已用上述 POST 结构实际查询，返回 401；同一 token 的工时查询成功。现有证据尚不能确定是 token 兼容性、账号授权或服务端配置原因。401 不能当作“没有故障”，也不能据此认定已返回可用故障样本。

## XGSS

### 地址与请求

生产地址由用户转发的接口方说明确认：

```text
POST https://xgss.xcmg.com/api/thrid/crm/auth
Content-Type: application/json
```

`thrid` 为原接口拼写，应原样保留。原说明书规定的外层请求为：

```json
{"data": "<RSA 加密后整体 Base64 编码的字符串>"}
```

加密前的业务字段：

| 字段 | 现有定义 | 解析结论 |
| --- | --- | --- |
| `username` | 登录用户名 | 用户已提供，本次认证成功 |
| `terminal` | `t4` | 固定值 |
| `lang` | 语言，默认英文 | 本项目按中文或英文选择 |
| `type` | 文档的类型描述存在歧义 | 用户提供整数1，本次无故障码认证成功；其他业务类型不推断 |
| `vin` | 整机 VIN | 使用已核实 VIN/PIN，不能传平台 UUID |
| `orderId` | 订单／工单／唯一用户编号 | 用户已提供，本次认证成功 |
| `accountId` | 唯一用户编号 | 本次成功请求未传；其他场景不推断 |
| `systemCode` | `iov` | 固定值 |
| 故障码参数 | 后续补充：增加故障码可定位手册 | 原文未写字段名、字段类型或加密位置，不能认定叫 `faultCode` |

RSA.txt 给出了公钥和 Java 分段思路。本项目已解析 1024 位 RSA 公钥，按 117 字节明文块加密为 128 字节密文块，拼接后整体 Base64；本地实现采用 PKCS#1 v1.5。加密适配已通过本地测试和本次生产认证请求。公钥无需重新提供，发布包不包含用户公钥。

### 返回与页面规则

原文响应字段为 `success`、`message`、`data`；成功时 `data` 是页面地址。

| 输入或资料情况 | 返回页面 |
| --- | --- |
| VIN＋故障码，存在已维护手册 | 对应故障排查手册，例如截图中的 E4030／J1939 总线故障 |
| VIN，无故障码 | 对应整机图册 |
| VIN＋故障码，但没有对应手册 | 对应整机图册 |

以上页面规则来自用户明确补充，已足够用于设计交互。两张截图是不同设备，不合并成同一 VIN 的连续测试证据。HTTP 或认证失败应单独报错，不能解释成图册回退。

页面展示使用返回 URL 内嵌；若官方嵌入策略限制，提供新标签页。只有 URL 时无法可靠判断是否命中手册，不把任意成功地址标成“找到故障手册”。

## 两套系统怎样衔接

```text
Trackunit 设备与故障记录
    ↓ 关联同一设备的 VIN/PIN，保留故障原码
本项目整理遥测、故障与人工检查证据 → Gemini 辅助分析
    ↓ 用户打开官方资料
XGSS 认证请求（设备标识＋已确认的故障码参数）
    ↓ 官方返回页面
内嵌手册或图册 → 人工核对 → 保存检查结果、继续排查
```

不能把 Trackunit UUID 当成 VIN；不能凭 SPN/FMI 或故障描述推造 E4030 一类厂商代码。仅在编码含义及设备适用性已明确时直接带入，否则保留原码并提示核对，或由用户主动进入通用图册。

当前 XGSS 契约不含手册正文、结构化零件表、VIN BOM、适配规则、库存或价格查询。官方网页可嵌入，不等于 AI 已获得网页正文。实现自动手册检索或正式备件匹配，还需要相应内容接口、授权资料导入或官方选件回传机制。

## 最少还需补充什么

1. XGSS 通用六参数示例已验证成功；剩余需要故障码的准确字段名、类型及加密位置。无需再次提供已验证的身份、业务编号或公钥。
2. Trackunit 对现有 v2 token 调用 Asset Event 返回 401 的解释，以及适用的账号授权条件；成功响应用于验证实际字段映射。

现有 XGSS 适配和页面入口见 `app/xgss_handoff.py`、`app/api/routes_xgss.py`、`app/assistant_ui/xgss-viewer.js`。它们已经准备好接收上述配置；“需要补充参数”不等于接口的整体结构无法解析。
