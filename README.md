# 机联智检

辅助已有车联网平台处理设备故障的工具：网页工作区 + Chrome 侧栏插件。AI 分析默认使用 DeepSeek API，关闭深度思考；设备资料、草稿和检查记录保存在本机。Gemini 和本地 Ollama 仍可手动配置。

## 当前先验收 XE55U 的一条工作流程

当前网页构建：`20260915.8-xe55u-components`；Chrome 插件源码：`0.6.0`。当前工作预览在 [8890 设备排查](http://127.0.0.1:8890/assistant-ui/)。本机旧 8892 服务尚未更新，不能用它判断此次新增功能。

选定产品为 **XE55U 柴油液压挖掘机**，首个测试故障为 **E4030 J1939 总线通信故障**。当前设备已有导入的 Trackunit 历史工时；E4030 单独标记为测试输入，不写入或伪装成真实 Trackunit 故障事件。

1. 选择 XE55U，在「运行数据与故障记录」点击「测试 E4030」。
2. 核对来源和配置；未知时保留「待核对」，点击「开始分析」。
3. DeepSeek 结合设备上下文和手册摘录，生成可疑部件、依据页码、图册检索词与待检查项。
4. 记录检查反馈后继续分析，查看反馈对判断的影响；保存和导出报告。
5. 在对应 VIN 的 XGSS 图册中打开零件明细，用新版 Chrome 插件「读取当前 XGSS 图册」读取可见条目，再「结合图册继续分析」。料号只取实际读取的图册条目，关联与排序由 AI 完成。

手册知识当前仅为已核查的 **XE55U.00III / EWMEN55U-A02 / PDF 第 286–287 页**摘录，保存在本机私有目录；不是整本 PDF 已导入，也未完成四向铲版本的知识导入。实际 Chrome 已在 8890 完成测试：首次真实 DeepSeek 分析显示用时 13 秒，返回 4 类可疑部件、2 页依据；保存明确标注的模拟检查反馈后，续查显示用时 6 秒，逐项说明反馈没有排除故障。历史重开、Markdown 实际下载和 390 像素窄屏报告也已验证。这些时间是单次软件流程观测，不代表诊断准确率或固定响应时间。

**尚未完成真实料号闭环：**当前 XE55U 的 VIN 尾号 02003 请求 XGSS 时，HTTP 200 的业务内容返回 `success=false`，提示 VIN 不存在，未读到该机器的真实零件条目。扩展读取能力已有自动化测试，但 Chrome 中 `0.6.0` 的实际重载及读取验收尚未完成。完整状态见 [当前验收状态](docs/PROJECT_ACCEPTANCE_STATUS.md)。

## 另有离线模拟案例

启动后打开 [完整演示案例](http://127.0.0.1:8890/assistant-ui/?demo=1)，或在网页选择「演示案例」。

案例：**滑移装载机左侧行走异常，仪表出现 H10101**。

1. 观察模拟现场现象和行走指令／响应趋势。
2. 查阅 H10101 的协议定义及来源。
3. 展示预设的 AI 分析示例，列出待检查的控制支路。
4. 展开模拟检查结果，查看线束问题和复测记录。
5. 按检查依据给出备件类型建议，导出演示讲解。

这是用户要求编写的展示案例。除注明出处的代码定义外，设备、工况数值、检查和结论均为虚构。演示不调用 Trackunit、DeepSeek、Gemini 或 XGSS，不消耗 API 配额，不写入真实设备或诊断历史；不是实机效果证明。14分钟是压缩演示时间，不是实际维修工时。数据在 `data/demo_case.json`。

## 启动

Windows，使用 Python 3.12，在项目根目录的 CMD 运行。首次克隆：

```bat
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt -r requirements-xgss.txt
copy .env.example .env
start_local.cmd --port 8890
```

已有环境直接运行 `start_local.cmd --port 8890`。本机检查用 `start_local.cmd --port 8890 --check-only`；不会停止或重启已有进程。演示无需填写密钥；真实 AI 分析需要在 `.env` 配置 `DEEPSEEK_API_KEY`。默认 `AI_PROVIDER=deepseek`、`DEEPSEEK_MODEL=deepseek-flash`，只连接 DeepSeek 官方地址。修改配置后重启后端；网页和插件共用后端密钥，无需分别填写。

网页入口：[设备排查](http://127.0.0.1:8890/assistant-ui/)。Chrome 插件直接加载项目中的 `extension` 文件夹，连接设置选择8890，详见 [插件说明](extension/README.md)。不需要单独编译当前网页和插件。

## 功能与当前边界

| 功能 | 状态 |
|---|---|
| 完整模拟案例 | 五阶段讲解、趋势、证据、检查反馈和导出，可离线演示 |
| 设备数据与故障资料 | 搜索、数据版本选择、趋势及 CSV 导出 |
| 排查任务与草稿 | 创建任务、记录检查、归档、草稿恢复及冲突检查 |
| TV12U 查码 | 本机可读取72条私有参考资料；完整原表和提取文件不随 Git 分发。演示所需 H10101 定义独立提供 |
| DeepSeek / XE55U 部件推断 | E4030 独立测试输入、配置分隔、手册摘录检索、可疑部件与检查依据、反馈续查；有一次真实 API 成功记录 |
| Gemini / Ollama | 保留手动配置；不会在 DeepSeek 失败时自动切换 |
| Trackunit | 已验证工时接口；故障事件访问仍返回401 |
| XGSS | 新增对应设备的可见图册条目读取、来源保存和 AI 候选关联；当前 XE55U 的 VIN 被业务接口拒绝，尚无该机真实料号闭环 |
| Chrome 侧栏 | 0.6.0 源码保留 Trackunit 自动跟随并新增 XGSS 可见条目读取；新版本实际安装及跨页面操作待验收 |
| 工况与冷却预警实验 | 附带模拟回放所需模型和测试片段，未完成实机效果验证 |

此次插件源码升级到 `0.6.0`；已安装旧版时，需要在 Chrome 扩展页重新加载项目的 `extension` 文件夹，并将连接端口设为 8890。仅重新连接网页不能更新扩展脚本。保存未提交草稿后再操作。设备自动跟随仍只选择同一 UUID 的已有实测资料，不自动调用 AI 或同步 Trackunit；XGSS 条目由用户点击读取，覆盖范围仅限当前可见页面。

## 开发与验证

当前完整测试：Python **632 项通过**、Node **119 项通过**；当前版本 ZIP 已构建。网页已验证测试故障、真实 AI 请求、模拟反馈续查、历史重开和报告下载；XGSS 真实料号及新版扩展实装仍未验收。见[本轮脱敏验收证据](docs/evaluation/xe55u-first-case-2026-09-15.json)。

```bat
.venv\Scripts\python.exe -m pytest tests -q
node --test tests/*.test.cjs
```

历史封存包验收、完整训练数据复算以及本机私有参考资料检查，在对应资料未分发时会明确跳过；其余业务规则测试照常运行。CI 同时检查旧 `frontend` 的类型和构建，当前产品界面位于 `app/assistant_ui/`。

- [案例说明](docs/DEMO_CASE.md)
- [当前验收状态](docs/PROJECT_ACCEPTANCE_STATUS.md)
- [Trackunit 与 XGSS 接口](docs/TRACKUNIT_XGSS_API_ANALYSIS.md) · [XGSS 对接](docs/XGSS_INTEGRATION.md)
- [TV12U 参考资料](docs/TV12U_FAULT_REFERENCE.md) · [任务记录](docs/MAINTENANCE_WORKLIST.md) · [草稿](docs/LOCAL_INVESTIGATION_DRAFTS.md)
- [开源组件与许可证](docs/OPEN_SOURCE_REFERENCES.md)

Git 不包含 `.env`、`data/local/`、真实缓存、内部原始文件、私人截图、旧参赛材料或本机软件包。旧 v10 包保留于本机历史目录，不包含当前案例；当前功能以本仓库源码为准。
