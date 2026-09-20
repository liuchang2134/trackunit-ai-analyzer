# 模型未加载状态下的网页查询验证

范围：当前电脑和已有安装环境，Ollama 服务持续运行，qwen3:8b 权重已在磁盘。验证卸载模型后，网页请求能重新加载模型并完成工作流；不是操作系统重启、Ollama 服务冷启动或断网测试。

使用 Ollama 官方 /api/generate 的 keep_alive=0 卸载 qwen3:8b，返回 done=true、done_reason=unload；随后 /api/ps 返回 models=[]。官方参数说明：https://docs.ollama.com/api/generate 。没有删除磁盘权重或改动系统网络设置。

从已有网页选择模拟备件演示，实际点击“开始分析”。界面显示首次加载等待提示并暂时禁用提交。随后 /api/ps 显示 qwen3:8b 重新加载，context_length=8192，size_vram=6186378198；此为一次本机观察，不是硬件最低配置或性能基准。

最终网页显示分析完成、三次工具查询、已保存本地记录，提交按钮恢复可用。报告包含 DEMO-BOOST-SENSOR 待检查候选、原文检查步骤及四条数据事实，来源 imported_synthetic。记录 34d055644d64526b9cae820a5066cfde1bc62eede734758b08803196bfec2ef2 经 read_investigation 验证内容哈希和字段。此次未测量可复现延迟，也未额外发起一次热启动对照。

原计划停止并重启 Ollama 进程的 shell 调用，在执行前被自动审批策略拒绝，返回仅为 blocked by policy。未绕过该拒绝；改用更小范围的官方模型卸载接口完成上述验证。Ollama 原服务保持运行，所以不能将本记录写成服务完整冷启动成功。
