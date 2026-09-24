# 机联智检 · AI 设备服务助手

面向工程机械的 **网页工作区 + Chrome 侧栏插件**，在客户已有的 Trackunit 设备页面旁，将故障信息、连续传感器数据与同 VIN 的 XGSS 图册连接起来，辅助维修检查与备件准备。

**参赛版本：20260924.4-fault-causality · 插件 0.9.25**

## 评委先从这里开始

打开本仓库的 [Releases](https://github.com/liuchang2134/trackunit-ai-analyzer/releases)，下载“完整项目复现包”。其中包含当前源码、插件、Windows x64 本地运行环境、XC948U 案例与图册图片，以及运行说明。

- 立即审阅：解压后打开 `review/index.html`，无需账号、安装或联网。
- 原生网页复现：Windows 10/11 x64 双击 `START_REVIEW.cmd`，浏览器打开本机 8896 端口。
- 实时系统：按下方说明配置自己的接口，在获授权的 Trackunit/XGSS 页面使用插件。

评审包展示已保存的真实资料和实际 AI 输出，查看时不会重新请求模型、刷新企业接口或发送邮件。生产源码保持独立，实时系统仍使用评委自己的账号和授权。

## 主要能力

| 功能 | 输入与输出 |
|---|---|
| 关联当前设备 | Trackunit 页面 UUID、设备快照及 VIN 校验，跟随当前设备 |
| 故障分析 | 保留 SPN/FMI/SA、事件来源与时间，AI 提出系统与部件核查方向 |
| XGSS 资料连接 | 检索同 VIN 图册，提取零件、料号、序号、图纸与资料依据 |
| 备件与维修建议 | 将优先核查对象与有依据的条件性备件分开，显示适配和更换条件 |
| 邮件准备 | 根据合格备件候选生成预览，配置 SMTP 后由用户明确发送 |
| 工时保养 | 无已读取故障时，结合工时及适用资料筛选保养、易损件方向 |
| 连续传感器风险分析 | 对温度、压力、转速、负载等序列识别间隔和运行状态，由 AI 解释风险征兆 |

## XC948U 案例

当前审阅案例是 **SPN 444 / FMI 1 / SA 163**，关联同 VIN 后车架电气图册。AI 输出 3 项优先核查对象；由于没有部件实测损坏证据，**条件性备件为 0**。图册里的料号存在，不能单独证明该零件应当更换。历史已解除的通信事件也不视为当前故障。

连续传感器案例含 1,348 个时间点、4 个通道，保留缺测与工况识别。当前输出是风险征兆与检查方向，尚不提供经过实车标定的故障日期或剩余寿命。

Trackunit 故障接口仍受账号权限影响，网页可见事件与故障 API 验证结果分别标注。系统未完成规模化生产验收，也不把数据缺失解释为设备正常。

## 从源码启动

推荐 Python 3.12（支持 3.11–3.13）。首次安装依赖需要网络：

```bat
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt -r requirements-xgss.txt
copy .env.example .env
start_local.cmd --port 8890
```

打开 `http://127.0.0.1:8890/assistant-ui/`。在 Chrome 扩展程序页面打开开发者模式，加载本仓库 `extension` 目录，侧栏连接 8890 或 8892。当前网页和插件不需要 Node 构建。

AI 密钥仅配置在后端 `.env`；Trackunit 和 XGSS 使用自有授权。仓库不包含提交者的密钥、企业登录会话、全量客户车队缓存或整套内部手册。只运行源码不会自动拥有企业数据；无账号审阅请使用 Releases 中的复现包。

## 代码导航

- `app/assistant_ui`：当前原生 JavaScript 网页。
- `extension`：Chrome Manifest V3 侧栏、页面读取与资料回传。
- `app/xgss_research_*`、`app/fault_part_grounding.py`：证据整理、AI 分析与故障因果约束。
- `app/sensor_series.py`、`app/sensor_risk.py`：连续序列与风险解释。
- `app/research_email.py`：候选备件通知与预览校验。
- `tests`：针对身份、证据、AI 输出与交互的测试。
- `scripts`：运行、训练、评测及历史发布工具；参赛入口以本 README 和本次 Release 为准。
- `frontend`：早期 React 界面源码，当前参赛入口不依赖它。

第三方代码的许可证保留在相应目录；XCMG、Trackunit 等名称与商标属于各自权利人。项目是独立参赛原型，公开代码不表示获得平台官方背书。
