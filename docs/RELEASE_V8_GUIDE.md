# 机联智检 v8：安装与演示

这是 **Gemini API + 本机网页/后端/资料** 的软件原型包，不要求安装 Ollama 或下载本地大语言模型。包内默认模拟数据，自动 Trackunit 同步关闭。故障预测只完成模拟冷却热事件实验，真实接口和现场效果仍待验收，详见 [本版状态](RELEASE_V8_NOTES.md)。

## Windows 首次使用

1. 解压 ZIP，进入 `jilian-assistant` 文件夹。选择新的可写目录，不要覆盖此前项目或 `.env`。
2. 准备 Python 3.11–3.13，推荐使用本版实际验证的 3.12。首次安装依赖需要网络；Python 运行时不在 ZIP 内。
3. 在此文件夹打开 PowerShell，运行 `./setup_local.ps1`。如果有多个 Python，可指定 `./setup_local.ps1 -PythonExecutable 'C:/你的Python目录/python.exe'`。脚本创建本文件夹的 `.venv`、安装固定版本依赖、首次复制空白配置并初始化模拟案例；已有 `.env` 保留。
4. 先查看模拟数据时运行 `./start_local.ps1 -DemoOnly`，打开 [本机网页](http://127.0.0.1:8890/assistant-ui/)。这个选项只跳过云端密钥就绪要求，不改变 AI 服务商、不生成替代报告。
5. 需要 AI 排查时，在本地 `.env` 填写自己的 `GEMINI_API_KEY`。保留 `AI_PROVIDER=gemini`、模型 `gemini-flash-latest` 与官方 HTTPS 地址。停止自己启动的服务终端后重新运行 `./start_local.ps1`。密钥只交给 Google 官方端点，不放进网页、扩展或参赛附件。

`start_local.ps1` 会核对当前版本及运行策略，避免将旧服务当作新版。默认端口 8890；端口被占用时可指定 `-Port 8892`。不要停止来源不明或仍在使用的进程。运行期间保留终端，Ctrl+C 结束自己启动的服务。

没有 Gemini 密钥或额度时，趋势图、原始资料查询、CSV 导出、工况回放和冷却预警仍可使用；开始 AI 分析会明确失败，不保存成功报告。配置检查只证明密钥字段存在，不能证明鉴权、额度或完整分析成功。云端调用可能收费，本包没有订阅、购买、模型切换或自动充值操作。

## 脚本无法执行时

遵循电脑现有脚本策略，不需要修改系统安全设置。在项目目录逐条运行下面的等价命令：

```powershell
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt
```

仅在没有 `.env` 时，把 `.env.example` 复制为 `.env`；保留已有配置。然后：

```powershell
.venv/Scripts/python.exe scripts/prepare_parts_demo.py --install
.venv/Scripts/python.exe scripts/check_local_runtime.py --demo-only
.venv/Scripts/python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8890
```

服务只监听本机回环地址，不是可直接公开部署的多用户服务。`data/local` 保存导入、备件目录和诊断记录；不要将它连同 `.env` 一起发给其他人。

## 五分钟演示路线

1. **设备分析**：选择“演示：增压信号告警与备件排查”。查看工时、怠速、两条人工注入告警；“查看资料”显示 `DEMO-BOOST-SENSOR`、资料出处和待核对事项。这是本地资料查询，零件号禁止用于采购。
2. **趋势导出**：选择趋势指标和末尾一小时，展开数据表并下载 CSV；设备、版本、来源、单位和空值随文件保留。
3. **故障预警**：点击“预警示例”，移动时点观察温度、十分钟变化和随机森林得分；查看独立测试与误报对照。提前量更长伴随更多误报，不能只展示命中率。
4. **带入排查**：点击“带入设备排查”，核对新选中的模拟设备及截止时点。只有再点击“开始分析”才向 Gemini 发送所选证据；未配置密钥时到此展示数据交接，不把预警当成 AI 诊断报告。
5. **工况回放**：加载独立测试片段，播放挖掘、回转、卸料、怠速、行走与停机识别。未知状态保留，模型得分不是正确率。

检查反馈和续查需要已有成功诊断记录。历史本地模型曾验证该流程，当前 Gemini 完整成功流程尚未验收，不能在本包声称已经通过。

## 平台和 XGSS

本包不带 Trackunit 或 XGSS 凭据、真实车队缓存、私有备件库或用户公钥。规范化 CSV/JSON 可以在网页独立导入，后端按来源和数据版本隔离。

`extension` 为 0.3.0 Chrome/Edge 侧栏源文件，可连接 8890/8892 并读取受支持设备详情 URL 的 UUID。实际安装及平台侧栏联调仍未验收；安装应由设备使用者按浏览器规则完成。说明见 [扩展](EXTENSION.md)。XGSS 只有本地 RSA 适配与已确认接口范围，缺少授权身份和故障参数契约，见 [XGSS](XGSS_INTEGRATION.md)。跳转接口不能代替正式备件搜索 API。

## 包内模型与数据

- `data/cooling_warning_v1`：完整 120 个虚拟设备实验，含观测、评价专用真值、数值模型、摘要及指标。运行时只读取观测和模型；`evaluator_only` 只供评价，不作为 AI 输入。
- `data/work_state_v1`：数值模型、评价和训练/验证/测试传感器观测；七段测试回放可直接用。重新训练所需的原始标签可由 `generate_diagnostic_dataset.py` 生成。
- `scripts`：数据生成、训练、准备、配置检查、包完整性核验和本地自检；训练时另装 `requirements-training.txt`，正常使用无需 sklearn。
- `app/assistant_ui/vendor/echarts`：已包含所用图表库及其 LICENSE、NOTICE 和来源版本记录。

热模型系数全部是模拟假设，不是某款实机的标定数据。模型数据卡：[冷却预警](COOLING_WARNING.md)、[工况识别](WORK_STATE_MODEL.md)。Python 第三方依赖由 pip 根据固定版本安装，其许可证随各自软件分发。项目业务代码、比赛署名及知识产权归属仍由参赛主体确认。

## 完整性与自检

在解压文件夹运行：

```powershell
.venv/Scripts/python.exe scripts/verify_release_v8.py --folder .
.venv/Scripts/python.exe -m pip check
```

`MANIFEST.json` 给出逐文件 SHA-256，可检查传输和意外修改；它不是作者数字签名。包内源码不应被安装脚本改写，正常数据写到运行目录。

在**全新解压且 `.env` 保持空白示例配置**的副本中，还可运行：

```powershell
.venv/Scripts/python.exe scripts/release_smoke.py
```

该自检会启动及关闭进程内 FastAPI 应用，检查模拟设备/资料/CSV/两类回放/预警交接，以及无密钥请求不生成报告。它会添加明确的模拟本地数据，禁止非本机网络连接，不启动监听服务。已配置真实密钥或有自己的数据时，应在另一个全新解压副本做此自检。

同一台电脑的全新虚拟环境、另一台实体电脑、实际云端分析、浏览器侧栏安装是不同验收项。软件包核验不等于全部业务完成。此包不包含已过时的本地大模型视频或答辩稿；最新竞赛材料应与 [v8 状态](RELEASE_V8_NOTES.md)核对后另行提交。
