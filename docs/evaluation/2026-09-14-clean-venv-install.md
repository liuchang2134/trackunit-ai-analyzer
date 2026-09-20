# 独立虚拟环境安装验证

验证对象为 `dist/jilian-local-prototype-20260914.zip`，SHA256 为 `c7bb7452181dc6806a3135761be6f38116b71323e2becafb10ad77075fbb4efa`。先校验包内文件与清单，再解压到全新 `.tmp/install-check-46703918a95f48849c685530003fa073/jilian-local`。

## 安装

使用 Python 3.12.14，将其目录加入当前测试进程 PATH 后，直接运行包内 `setup_local.ps1`，退出码为 0。脚本创建新的 `.venv`，`include-system-site-packages = false`，从 requirements.txt 安装依赖，创建默认模拟配置并准备演示目录。未复制开发环境 site-packages。pip 使用了本机下载缓存，因此不能声称全量重新下载或无网络安装。

新环境 `pip check` 报告无依赖冲突。`scripts/check_local_runtime.py` 报告 Python 受支持、无缺失依赖、本地 Ollama 可达且 qwen3:8b 可用。

## 功能

使用新环境 Python 运行此前发布包烟雾验证中的同一组断言：五台模拟设备、一套人工演示数据、一项演示备件目录、七段工况测试片段及回放 HTTP 200。实际本地 qwen3:8b 完成三次工具查询，返回一个 DEMO 备件候选并保存诊断报告。日志为解压目录中的 `install-smoke.log`，逐步决策保存在 `smoke-model-decisions.json`。

随后在独立子进程启动 uvicorn，使用本机端口 18891，验证 `/health`、`/assistant-ui/`、`/assistant/datasets`、`/assistant/work-state/episodes`。页面返回 200，数据来源为 mock、一个模拟数据集及七段测试片段。结果保存在 `install-http-result.json`，子进程通过其进程句柄结束。原 8890 开发服务保持运行。

## 验证边界

本次证明同一台电脑上的新虚拟环境可按脚本安装、通过 HTTP 提供页面并使用本地 AI 完成演示查询。复用了已安装 Python、系统组件、pip 缓存和本机 Ollama/模型。没有在全新电脑、全新 Windows 用户或物理断网条件下验证。`start_local.ps1` 的完整 8890 冷启动分支、实际侧栏安装及真实设备效果仍需另行验证。
