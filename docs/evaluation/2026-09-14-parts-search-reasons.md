# 备件检索原因验证

本地检索新增可选 diagnostics 输出，现有候选列表接口保持兼容。检索一次读取目录，按来源、机型、序列号适用范围、故障码或部件查询逐级筛选；报告每级剩余条目数、第一个无结果阶段、返回数量和是否超过 20 条展示上限。不返回被排除的备件编号或目录正文。

原因码：catalog_empty、no_eligible_catalog、model_not_in_catalog、serial_not_applicable、fault_or_component_not_matched，成功为 matched。它们只说明当前本地目录，不能推断其他目录不存在备件。

本地 AI 工具结果包含 search_diagnostics；网页空候选区域按原因码直接显示中文说明，旧报告继续使用原通用提示。网页脚本通过 Node 语法检查，尚未完成本次分支的实际浏览器操作验证。

新增自动测试逐一覆盖五种无匹配情况、成功匹配、阶段数量以及不暴露被排除零件号。全套测试 168 passed、6 个已有弃用警告。

真实本地 qwen3:8b 两例运行保存在 local-assistant-20260914T055617Z.json。错误型号工具明确返回 matching_model=0 和 model_not_in_catalog；空目录工具明确返回 catalog_entries=0 和 catalog_empty。两例结构检查通过，但自然语言摘要仍有缺陷：前者将确定的目录过滤事实写成“可能”，并误称回放和记录时间一致；后者没有明确说目录为空，而且再次将运行状态写成正常。不能把新增工具解释能力表述为 AI 全部语义问题已解决，后续需加入针对性输出校验。原始失败语义输出保留，不用于宣称诊断准确率。
