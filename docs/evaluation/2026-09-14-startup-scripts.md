# 后端停止启动与重复启动验证

目标为 start_local.ps1 → check_local_runtime.py → run_backend.ps1 链路。三个文件均与 v3 ZIP 内逐字节一致。本次在开发目录运行，使用已安装依赖和保持运行的 Ollama，不属于新电脑或模型冷启动。

先核对当前 uvicorn 日志 PID 与 Python 可执行文件，停止该后端进程。从 Windows PowerShell 5.1 执行 start_local.ps1 时，系统策略在脚本执行前拒绝加载。没有修改 ExecutionPolicy 或使用 Bypass；随后恢复服务。

现有 PowerShell 7 的执行策略为 RemoteSigned。再次停止已核验后端，从该 PowerShell 的 -NoProfile -File 参数执行原启动脚本，启动检查显示 ready=true，uvicorn 记录 Application startup complete，/health 返回 ok。后端由停止状态启动成功。

在后端运行期间再执行同一脚本，退出码 0，显示 Assistant already running，原 uvicorn PID 保持运行，没有进入重复启动分支。该脚本启动的服务继续保留供用户使用。

已在 RELEASE_GUIDE.md 加入终端逐条安装/运行命令，以及 PowerShell 5.1 策略拦截和 PowerShell 7 已验证范围。不能从本机策略推断所有 Windows 电脑的默认设置；也不能将这次后端启动称为整机离线或 Ollama 冷启动成功。v3 已交付 ZIP 中尚未包含这条新增说明，最终打包需同步。
