# XGSS 对接说明

## 当前验证结果

2026-09-15 03:40 UTC，使用用户提供的六个参数与原 RSA 公钥，向生产 `/api/thrid/crm/auth` 发起一次请求，无自动重试。结果为 HTTP 200、`success=true`、`message=成功。`，取得 `xgss.xcmg.com` 下有效 HTTPS 页面地址。访问该地址返回 HTTP 200 和 HTML。

该次请求证明加密与认证成功；随后04:34 UTC的浏览器验证进一步显示官方 VIN、图册目录、整机图及零件明细。故障码手册仍未验证。初始 HTML 本身不含 VIN，页面内容结论来自浏览器加载后的实际截图，不能只用 HTTP 200 代替。返回会话地址与页面网络正文没有写入持久日志。

本次请求只包含 `username`、整数 `type=1`、`systemCode=iov`、`terminal=t4`、`orderId`、`vin`。没有传 `lang`、`accountId` 或故障码。结果仅验证这组用户参数，不推断它们适用于所有账号及业务场景。

身份、业务编号及公钥路径已保存到本机 `data/local/xgss-config.json`。04:09 UTC 已验证应用 `request_page()` 追加 `lang` 后仍成功取得官方地址。六参数证据在本机 `data/local/xgss-probes/supplied-six-fields-result.json`，应用适配器证据在 `data/local/api-checks/20260915T040917Z-core-workflow.json`。

## 请求格式

- 生产地址：`https://xgss.xcmg.com/api/thrid/crm/auth`，保留 `thrid` 原拼写。
- 方法与类型：POST，`Content-Type: application/json`。
- 将业务参数组成 JSON，使用现有1024位 RSA 公钥按117字节分段进行 PKCS#1 v1.5 加密。
- 拼接密文后整体 Base64，外层只传 `{"data":"加密字符串"}`。
- 响应字段为 `success`、`message`、`data`；成功时 `data` 为官方页面地址。

来源为用户提供的2025-03-10接口文档、RSA.txt、后续参数及本次生产实测。无需重新索取公钥、username、orderId 或通用入口的 type。

## 手册与图册规则

下表来自用户提供的页面案例；本次无故障码请求没有重新验证全部分支。

| 输入与资料状态 | 预期页面 |
|---|---|
| VIN＋故障码且已维护手册 | 对应故障排查手册 |
| 仅 VIN | 整机零件图册 |
| VIN＋故障码但没有手册 | 整机零件图册 |
| 认证或网络失败 | 提示请求失败，不解释为没有手册 |

**剩余接口信息仅是故障码的准确字段名、数据类型和加密位置。** 当前故障码配置保持空值，故障查询不会静默改成通用图册查询。

## 应用使用与边界

设备入口与故障资料窗口由现有后端统一调用，提供内嵌和新标签页两种展示方式。真实设备的 VIN 与当前选中设备必须一致，模拟设备不会请求生产系统。当前参数中的 VIN 只用于这次获准查询，不会冒充 Trackunit 已识别的设备。

2026-09-15 04:32–04:34 UTC 的 Chrome 153 页面验证已显示相同 VIN、官方导航、图册目录、整机图及含物料编码、名称和数量的明细；在本机同源测试容器中使用与应用相同的 iframe sandbox，也能加载这些内容。截图已人工核对；统计中的表格 DOM 行数不能当作去重后的物料总数。点击“回转支承”后没有证据证明已切换到它的独立明细，因此仅验收实际看到的整机图册，不声称所有目录节点均已验证。

官方页面将此 VIN 归为“汽车起重机”，不能据此将它关联到 TV12U 滑移装载机协议。验证没有伪造或新增 Trackunit 设备记录，也没有证明正式网页所选设备与这个 VIN 的映射已打通。

页面仍有来自 `tsh-dec-d.xcmg.com` 的字体 DNS 加载失败；已加载内容与该异常分别记录，不归为认证失败。浏览器证据及截图位于本机 `data/local/xgss-render-check/`，会话地址、令牌和页面网络正文不落盘。故障码定位及对应手册仍未验证。

接口只提供页面入口，不提供手册正文、结构化零件表、VIN BOM、库存、价格或选件回传。取得地址不能当作 AI 已读取手册或备件适配已确认。

源码位置：`app/xgss_crypto.py`、`app/xgss_handoff.py`、`app/api/routes_xgss.py`、`app/assistant_ui/xgss-viewer.js`。通用配置模板见 [配置示例](examples/xgss-config.example.json)，页面案例见 [案例记录](examples/xgss-page-routing-cases.json)。用户配置及原公钥不加入公开交付包。
