# v6 使用说明勘误

适用归档：jilian-local-prototype-20260914-v6.zip，SHA-256 758517923e9a6e09ff8b3087c2114aca2eb1fdbd2523c25a65e7b533b61eb9f1。归档未修改，本文件在交付核对后补充。

包内 docs/LOCAL_ASSISTANT.md 残留了早期说明，以以下更正为准：

1. 侧栏 0.2.0 的权限为 sidePanel 和 activeTab，并非只有 sidePanel。点击图标后可读取受支持平台网址的设备 ID，再匹配本地数据；切换设备后需重新读取。实际安装与侧栏联调仍待完成。包内 EXTENSION.md 和 manifest.json 的描述正确。
2. 历史同步命令及网页入口已验证，不是待开发功能。最近一次网页核验中工时返回 36 条、怠速为空、故障事件未核验；此前故障接口 401 是另一项记录，不能混作同一次结果。
3. 模拟工况模型、独立测试集回放、检查反馈及历史报告查看已有实现与验证。实机标定、真实侧栏和完整离线/新电脑验收仍待完成。
4. 已有 .env 时不要运行无条件 Copy-Item 覆盖配置。首次安装优先按 START_HERE.md 运行 setup_local.ps1；该脚本保留已有 .env。升级模型按 START_HERE.md 单独核对 OLLAMA_MODEL。

工作区 docs/LOCAL_ASSISTANT.md 已修正。上述勘误不改变包内程序行为，不补造缺失的现场验证，也不改变 XGSS 尚未接通的状态。
