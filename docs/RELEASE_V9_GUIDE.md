# 机联智检 v9：安装与使用

本包为 `20260914.11-ai-request-status` 软件原型：**Gemini 云端推理 + 本机网页、后端、资料与报告**。包含设备查找、故障资料到排查的交接和最近 AI 请求状态。无需安装 Ollama。模拟预警和目录可以独立演示，真实 Gemini 成功流程、XGSS、正式备件与现场效果仍未验收，见 [本版状态](RELEASE_V9_NOTES.md)。

## Windows 安装

1. 将 ZIP 解压到新的可写目录，进入 `jilian-assistant`。不要覆盖已有项目、配置或业务数据。
2. 准备 Python 3.11–3.13，推荐 3.12。ZIP 不含 Python；首次安装依赖需要网络。
3. 在此文件夹打开 PowerShell，运行 `./setup_local.ps1`。多个 Python 时可指定 `./setup_local.ps1 -PythonExecutable 'C:/你的Python目录/python.exe'`。脚本创建本目录 `.venv`、安装固定版本依赖、首次复制空白 `.env` 并准备模拟案例；已有配置会保留。
4. 运行 `./start_local.ps1 -DemoOnly`，打开 [本机网页](http://127.0.0.1:8890/assistant-ui/)。首次应看到模拟数据和“Gemini 密钥未配置”。这个选项只允许先看本地功能，不替换 AI 输出。
5. 需要云端分析时，在本机 `.env` 填写自己的 `GEMINI_API_KEY`，保留 `AI_PROVIDER=gemini`、`gemini-flash-latest` 及官方 HTTPS 端点。结束自己启动的服务后重新运行 `./start_local.ps1`。有效凭据、可用额度和完整分析是不同检查项。

端口 8890 被占用时可指定 `./start_local.ps1 -DemoOnly -Port 8892`，打开对应端口。启动脚本会核对构建版本和运行策略；不应停止其他来源的服务。保留自己启动的终端，Ctrl+C 结束该服务。

若电脑策略阻止 PowerShell 脚本，无需修改安全设置，可在解压目录逐条运行：

```powershell
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt
```

仅在没有 `.env` 时复制 `.env.example` 为 `.env`，然后：

```powershell
.venv/Scripts/python.exe scripts/prepare_parts_demo.py --install
.venv/Scripts/python.exe scripts/check_local_runtime.py --demo-only
.venv/Scripts/python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8890
```

服务只监听本机回环地址。`data/local` 保存导入文件、目录、AI 状态及诊断记录；不要将业务数据和 `.env` 随参赛附件分发。

## 从设备到排查

1. **查找设备。** 在“设备分析”点击“查找设备”，搜索 `SIM-PARTS-REPLAY-001`，选择“演示：增压信号告警与备件排查”。结果分别列出数据版本；搜索本身不切换设备。首次安装有五台模拟车队设备和一个导入模拟案例。
2. **查看依据。** 核对“模拟”来源和数据版本，查看工时、怠速、故障记录。两条告警是同一故障码的不同记录，不代表两次独立故障。可切换曲线时段并下载带设备、来源、单位和空值的 CSV。
3. **查询资料。** 从故障行打开“查看资料”，看到 `DEMO-BOOST-SENSOR`、适用限制和资料出处。记录原文可以展开，关闭后焦点返回原按钮。演示零件号不能用于采购。
4. **进入 AI 排查。** 点击“带此故障码进入 AI 排查”，故障码自动填入问题，任务和设备版本保持对应。表单上方显示最近完整请求状态；“更新状态”只读本机记录，不调用模型、不承诺额度恢复。
5. **主动提交。** 只有“开始分析”会将当前证据、问题和检查反馈通过后端发送给 Gemini。失败会明确提示并恢复控件；没有成功报告就不会产生成功历史。整次排查时限 120 秒，仅临时服务错误有限重试。

完成报告后可查看出处、导出、保存检查反馈并继续排查。原报告保持不变，人工反馈保留未验证来源。此链路已有模拟 Gemini HTTP 响应的应用测试，**真实 Gemini 完整成功流程仍待验收**。

## 展示模拟预警与工况

“故障预警”提供冷却热事件示例、温度和观测表、过去十分钟变化及误报对照。移动到指定时点后，“带入设备排查”生成对应模拟设备和截止时间的数据版本，仍需另行提交 AI。

模型对八个模拟测试热事件识别八个，中位提前量 15 分钟，但误报 0.268/有效小时，高于温度对照的 0.141/有效小时，也超过验证预算。不能只展示命中数或把它称为实机故障预测。100°C 持续 180 秒是实验定义，不是制造商限值。详见 [冷却预警说明](COOLING_WARNING.md)。

“工况回放”提供七段独立模拟测试片段，覆盖挖掘、回转、卸料、怠速、行走、停机和未知输出。模型分数不是正确率，详见 [工况模型说明](WORK_STATE_MODEL.md)。两种数值模型均在本机计算，无需本地大语言模型。

## 平台、目录和资料

扩展源文件在 `extension`，版本 0.3.0，支持 Chrome/Edge 侧栏连接 8890/8892 及受支持设备 URL。实际安装和平台联调尚未验收，见 [扩展说明](EXTENSION.md)。网页本身可以独立运行。

包内没有 Trackunit/XGSS 凭据、实测缓存、私人目录或用户公钥。可导入规范化 CSV/JSON；正式接口需各自的已确认权限和契约。XGSS 当前只有本地 RSA 适配，缺获准身份和故障参数，不能打开已验证的生产手册；认证跳转接口不能当作 BOM、库存或价格 API。见 [XGSS 说明](XGSS_INTEGRATION.md)。

## 完整性和独立自检

在解压目录运行：

```powershell
.venv/Scripts/python.exe scripts/verify_release_v9.py --folder .
.venv/Scripts/python.exe -m pip check
```

逐文件 SHA256 检查传输和意外修改，不是作者数字签名。仅在**另一份全新解压、未放入业务数据且 `.env` 保持空白示例配置**的副本运行：

```powershell
.venv/Scripts/python.exe scripts/release_smoke_v9.py
```

自检会在该副本添加模拟数据和一次无密钥失败状态。它检查应用进程内启动/关闭、设备索引、状态持久化、目录、CSV、两类回放和预警交接；禁止非本机网络，不启动监听服务。不要在自己的日常数据副本反复运行。

包内含完整冷却模拟实验、工况模型及必要观测资源，训练另需 `requirements-training.txt`。ECharts 的 LICENSE、NOTICE 和来源已保留，见 [开源参考](OPEN_SOURCE_REFERENCES.md)。没有附带旧本地模型视频。v9 软件包与 v9 参赛文档分别编号，软件以本页顶部的构建号为准。
