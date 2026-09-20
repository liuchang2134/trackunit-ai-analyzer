# 机联智检 v10：网页与 Chrome 插件

本包对应网页构建 `20260914.16-cooling-evidence` 和 Chrome 插件 **0.4.0**。使用 Gemini 云端分析，本机保存数据、资料和排查记录，无需安装本地大语言模型。它是可运行的软件原型；真实 Gemini 完整诊断、XGSS 生产连接和 Chrome 实装尚未完成验收，见 [本版状态](RELEASE_V10_NOTES.md)。

## 安装网页

1. 将 ZIP 解压到新的可写文件夹，进入 `jilian-assistant`，不要覆盖日常业务数据。
2. 准备 Python 3.11–3.13，推荐 3.12。在该目录打开 PowerShell，运行 `./setup_local.ps1`。首次安装依赖需要网络；脚本创建 `.venv`、空白 `.env` 和模拟案例，不包含付费服务。
3. 运行 `./start_local.ps1 -DemoOnly`，打开 http://127.0.0.1:8890/assistant-ui/ 。端口占用时可加 `-Port 8892` 并打开对应地址；不要停止其他项目的服务。
4. 需要 AI 分析时，在本机 `.env` 填写自己的 `GEMINI_API_KEY`，保留 `AI_PROVIDER=gemini` 和 `GEMINI_MODEL=gemini-flash-latest`，重新启动自己运行的服务。密钥配置成功不代表额度可用或诊断成功。

若 PowerShell 脚本受本机策略限制，可在解压目录逐条执行，无需修改系统策略：

```powershell
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt
```

仅当 `.env` 不存在时，将 `.env.example` 复制为 `.env`，然后执行：

```powershell
.venv/Scripts/python.exe scripts/prepare_parts_demo.py --install
.venv/Scripts/python.exe scripts/check_local_runtime.py --demo-only
.venv/Scripts/python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8890
```

## 主要操作

| 入口 | 可以完成的工作 |
| --- | --- |
| 待处理 | 找到需要核对的设备、继续排查任务、查看已归档任务 |
| 设备分析 | 按设备和数据版本查看趋势、故障记录、缺失数据及本地备件候选；导出绘图 CSV |
| 排查任务 | 创建任务、保存检查记录、更新进度、归档或重新打开、导出处理历史 |
| AI 排查 | 带入故障、已保存记录和资料出处，主动提交 Gemini；成功后保存报告、反馈续查及导出 |
| 本机草稿 | 在 AI 不可用时保存问题和现场观察；刷新后显式恢复，避免覆盖另一页面的新版本 |
| XGSS 图册／故障资料 | 配置完整后请求官方页面；有手册则进入手册，无故障码或无手册则进入整机图册 |
| 故障预警 | 回放模拟冷却预警、检查观测与误报对照、带入对应时点的设备排查 |
| 工况回放 | 查看柴油液压挖掘机模拟工况的分类与传感器数据 |

第一次展示可在“查找设备”搜索 `SIM-PARTS-REPLAY-001`，选择模拟备件案例，依次查看故障、资料、建立排查任务和保存观察。`DEMO-BOOST-SENSOR` 是演示候选，不能用于采购。仅“开始分析”会调用 Gemini；免费额度不足时仍可使用其余本机功能，但不会伪造 AI 报告。

扩大的冷却测试中，当前模型提前识别 **28/31** 次模拟事件，误报 **0.215 段/可评估小时**，未达到实验门槛。原先 8/8 的结果只作历史对照；不得据此宣称真实设备预测准确率。参见 [冷却预警](COOLING_WARNING.md)与[工况模型](WORK_STATE_MODEL.md)。

## 安装 Chrome 插件

在 Chrome 的 `chrome://extensions/` 启用开发者模式，点击“加载已解压的扩展程序”，选择本包 **`extension` 文件夹**。本机网页后端需保持运行。在插件连接设置选择 8890 或 8892，与实际网页一致。

打开 Trackunit 设备详情页，点击插件图标，再点击“读取当前设备”。网页匹配到相同设备与数据版本后才显示已关联；多个版本需明确选择，没有对应本地数据时需先同步或导入。切页后按提示重新读取。首次纯模拟安装不会匹配到真实 Trackunit 设备，这不代表可以拿其他设备代替。

完整步骤和支持页面见 [插件说明](../extension/README.md)。本包提供可加载的插件目录，**尚未完成真实 Chrome＋Trackunit 实装验收**。

## XGSS 与数据

XGSS 入口包含内嵌页面和新标签页两种方式。将接口方确认的配置填写到本机 `data/local/xgss-config.json`，模板见 [配置示例](examples/xgss-config.example.json)。安装可选 RSA 依赖使用 `.venv/Scripts/python.exe -m pip install -r requirements-xgss.txt`。模板没有账号和公钥，不能直接请求生产系统。

还需确认故障码字段名及加密位置、查询 type、获准身份及业务编号。返回地址并不提供 AI 可读取的手册正文、BOM、库存或价格。用户的手册／图册案例见 [路由案例](examples/xgss-page-routing-cases.json)，对接边界见 [XGSS 说明](XGSS_INTEGRATION.md)。

本包不带真实设备缓存、用户公钥、API 密钥或已有诊断记录。后续业务数据保存在 `data/local` 及配置的本机数据库；保留 `.env` 和数据备份，不要随参赛文件分发。此包不自动迁移开发目录中的业务数据。

## 完整性与独立自检

解压后可运行 `.venv/Scripts/python.exe scripts/verify_release_v10.py --folder .` 核对文件摘要，再运行 `.venv/Scripts/python.exe -m pip check`。摘要用于发现传输或意外修改，不是数字签名。

只有另一份全新解压、没有业务数据、`.env` 与空白示例一致的副本，才运行 `.venv/Scripts/python.exe scripts/release_smoke_v10.py`。自检写入模拟草稿、任务及无密钥失败记录，检查进程内应用启动／关闭；阻止外网连接，不验证真实 API 或 Chrome 安装。不要在日常业务目录反复自检。

本包包含冻结的两轮冷却实验、工况模型与必要观测；不要覆盖重训既有模型，新的实验应另建版本。开源许可与采用范围见 [开源说明](OPEN_SOURCE_REFERENCES.md)。
