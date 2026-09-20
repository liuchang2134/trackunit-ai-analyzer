# 模型缺失与本地连接边界检查

对象为 v3 包已验证解压目录 `.tmp/release-smoke-4e184237bb63456b897d5d0b6735fafd/jilian-local`。未修改开发服务配置或系统网络设置。

先将该独立目录的模型配置临时设为不存在的模型名称，运行包内 check_local_runtime.py。结果：Python 和依赖正常、Ollama 可达、model_available=false、ready=false，退出码 1。随后原样恢复配置文件。没有删除模型或停止用户 Ollama。

再在单独 Python 测试进程内拦截 socket.connect、connect_ex 和 getaddrinfo，仅允许环回地址。对文档保留地址的外部连接尝试在调用原操作系统连接前被拒绝，用于确认测试拦截生效，随后清零该探针记录。这不是系统防火墙或操作系统级隔离。

拦截生效期间执行发布包烟雾验证：健康、五台模拟设备、一套模拟数据、七段工况回放及实际 qwen3:8b 备件分析均通过。模型完成三次工具查询，返回一个演示候选并保存报告。观察到五次允许的环回连接，未观察到被拦截的应用外部连接。运行结果保存在 `.tmp/local-boundary-result.json`，测试脚本为 `.tmp/check-local-boundary.py`。

范围限制：只覆盖该 Python 进程使用被拦截接口的连接；没有隔离其他进程、浏览器、Ollama、原生库网络调用或操作系统。推理使用已下载模型和现有 Ollama 服务，没有冷启动。只能说明本次模拟工作流的应用连接依赖为本机，不能声称整个产品已通过物理断网或操作系统级离线验收。
