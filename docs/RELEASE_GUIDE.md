# 机联智检本地原型安装与演示

这是 v6 参赛软件原型包。默认运行模拟数据，不需要 Trackunit 凭据。新增内容与材料版本关系见 docs/RELEASE_V6_NOTES.md。真实设备效果、完整离线冷启动和实际侧栏安装仍待验证。

## Windows 首次安装

1. 解压到可写目录，建议路径简短并保留 jilian-local 文件夹。
2. 准备 Python 3.11 或更高版本并加入 PATH；从 Ollama 官方来源安装 Ollama。
3. 在 PowerShell 中进入目录，运行 `./setup_local.ps1`。首次安装依赖需要网络，不覆盖已有 .env。脚本准备明确标识的模拟告警和演示备件目录。
4. 运行 `ollama pull qwen3.5:9b` 下载模型，再运行 `./start_local.ps1`。模型权重未打入安装包，需按其许可证获取。本项目使用 Ollama 0.34.0 验证；开发机模型文件约 6.59 GB，8192 上下文的已观察显存占用约 4.80–5.51 GB，部分计算使用系统内存。这些是本机观测，不是最低配置保证；资源不足时可能明显变慢。
5. 打开 http://127.0.0.1:8890/assistant-ui/ 。运行期间保留服务终端，Ctrl+C 停止后端；Ollama 为独立进程。

如果 PowerShell 策略限制脚本，请遵循本机管理要求；也可依次手动创建 venv、安装 requirements.txt、复制 .env.example、运行 prepare_parts_demo.py --install 及 uvicorn app.main:app --host 127.0.0.1 --port 8890。

本机 Windows PowerShell 5.1 实测会在脚本执行前拦截；已有 PowerShell 7 在其现有 RemoteSigned 策略下通过了启动与重复启动检查。不需要为此修改系统策略。若脚本不能运行，在项目目录的终端逐条执行以下命令（首次安装依赖需要网络）：

```powershell
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt
```

仅当目录中没有 .env 时，将 .env.example 复制为 .env，保留已有配置。Ollama 与模型准备好后执行：

```powershell
.venv/Scripts/python.exe scripts/prepare_parts_demo.py --install
.venv/Scripts/python.exe scripts/check_local_runtime.py
.venv/Scripts/python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8890
```

启动检查显示 ready=false 时，先按提示补齐依赖或模型。手动 uvicorn 命令不会复用已有进程；若 8890 已运行本助手，直接打开网页即可，无需再启动一份。

从旧包升级时，setup_local.ps1 保留已有 .env；请核对 OLLAMA_MODEL 是否仍为旧值。要使用本版默认模型，将该项设为 qwen3.5:9b 并重启本项目后端。模型切换不会重写历史报告；历史模型名称按当时实际执行值保留。

XGSS 在本版提供接口对接说明和可选 RSA 加密适配，尚未接通在线手册跳转。仅运行模拟演示无需安装额外依赖；开发对接时可执行 `.venv/Scripts/python.exe -m pip install -r requirements-xgss.txt`。包内不含 XGSS 公钥、账号或登录会话，缺少的故障码参数契约见 docs/XGSS_INTEGRATION.md。

## 三分钟演示

- 设备分析：选择“演示：增压信号告警与备件排查”，任务选故障与备件查询，输入“读取故障并匹配备件，说明匹配依据和仍需核实的事项”。确认来源是模拟、零件号以 DEMO- 开头、事件首末间隔 25 分钟。
- 检查反馈：在诊断记录下保存“模拟反馈：尚无实机检查结果，不能确认传感器损坏”，带反馈继续分析，核对新报告保留不确定性。
- 工况回放：选择独立测试片段，加载并播放，查看输入信号、分类和未知状态。模型内部得分不是正确率，展示的是模拟工况。

工况数值模型和七段测试传感器文件已包含，可直接回放；训练集和完整仿真真值未随包分发。需要重跑训练时先运行 scripts/generate_diagnostic_dataset.py，再安装 requirements-training.txt 并运行 scripts/train_work_state.py。测试标签仅用于评价，不能输入推理。

## 插件与真实数据

v3 新增 scripts/sync_trackunit_history.py、docs/TRACKUNIT_HISTORY_SYNC.md 和 docs/SYNTHETIC_DATA_GUIDE.md。真实接入需自己提供授权配置和单设备快照；模拟数据说明列出字段、单位、生成步骤与仿真假设。旧 import_existing_trackunit_exports.py 是开发迁移脚本，依赖固定文件且写入车队缓存，未作为通用入口分发；规范化 JSON/CSV 仍通过网页独立导入。

extension 文件夹是 Chrome/Edge 侧栏扩展，安装方法和权限见 docs/EXTENSION.md。安装会新增侧栏及点击后读取当前页网址的权限，需要设备使用者同意。当前发布验证不包含实际安装联调。

真实 API 配置和现场目录请在自有授权环境中完成。本包不含账户凭据、真实设备标识或位置响应、私有目录及历史记录，不主动同步平台。当前默认模拟数据；故障事件接口权限并未验证为可用。

## 包内内容与复核

app 为本地服务与网页；scripts 为演示、训练和评价脚本；data/work_state_v1 为模拟分类模型与测试观测；docs 为说明和 proposal。MANIFEST.json 记录逐文件 SHA256，可用于发现传输损坏，不是作者签名。第三方依赖和模型按各自许可证单独安装，本包不包含其运行时或权重。项目业务代码权属仍由参赛主体确认。

验收必须区分：现有开发环境运行、解压包隔离运行、新电脑首次安装和完全断网运行。不能将其中一项通过当成全部通过。本包包含 v4 可编辑答辩 PPTX、PDF、逐页讲稿、实际浏览器模拟报告和 44 秒模拟功能视频。视频早于最新事实分区界面，且未覆盖侧栏与完整反馈操作，详见 docs/DEMO_VIDEO.md。

2026-09-14 已对前版包补充同机全新 Python 3.12 虚拟环境安装验证：直接运行 setup_local.ps1 成功，依赖检查、本地 AI 备件查询、报告保存及独立 HTTP 服务均通过。该验证复用已有 Python 和 Ollama/模型，不等同于新电脑安装或断网验收，详见 docs/evaluation/2026-09-14-clean-venv-install.md，其中哈希限定该次验证对象。

本版新增不可计算指标的原因、备件检索阶段说明及针对已知肯定健康结论的输出校验。近期语义复核也一并保留：模型仍可能误述模拟时间关系或重复检查建议，结构检查通过不代表诊断结论全部正确。请结合原始证据复核。

模型加载补测：在本机通过 Ollama 官方接口卸载 qwen3:8b、确认运行模型列表为空后，网页首次查询成功重新加载模型，完成备件分析并保存记录。Ollama 服务始终运行，权重已提前下载；此项不等于服务冷启动、新电脑或断网验收，详见 evaluation/2026-09-14-model-reload.md。
