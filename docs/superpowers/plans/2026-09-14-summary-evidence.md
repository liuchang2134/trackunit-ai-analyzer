# 摘要证据压缩 Implementation Plan

**Goal:** 让最终摘要从已有工具事实和明确限制生成，减少重复原始遥测与早期工具对话干扰。

**Architecture:** 新增独立 summary_evidence 模块，只投影已返回的证据，不计算新指标。所有必需工具执行后，使用原系统规则、用户问题、投影证据和已有纠正消息生成最终决策；原始完整证据仍保存到报告。模型仍可选择尚未使用的额外工具。

**Tech Stack:** Python、现有 Pydantic 决策协议、Ollama；无新增依赖。

**Constraints:** 本地运行；不改写检查原文；不丢失人工反馈；不更改工具计算或备件过滤；不将结构通过称为语义正确。本次在当前工作区直接实施，保持其他未提交工作。

**执行结论：** 已实现并测试，实际双语评测出现备件匹配自相矛盾及检查建议缺失，按第 5 步撤回运行路径改动。实验与结果见 docs/evaluation/2026-09-14-summary-context-experiment.md，未作为当前产品能力交付。

1. 新增 app/summary_evidence.py 的 summary_evidence(evidence: dict) -> dict，保留来源、时点、窗口计算、未匹配原因、候选限制和人工反馈。快照去除重复遥测，仅保留最新有效时点的一条样本；保留总记录数及非健康认证说明。
2. 新增 tests/test_summary_evidence.py，检验按时间选择样本、原输入不变、缺失指标/目录原因/反馈保留、完整证据仍留在报告。先运行确认模块缺失，再实现。
3. app/local_assistant.py 在 required <= used 时组装压缩消息；保留系统纠正消息和原 schema 控制。final control 要求模拟来源、确定的目录原因及所请求的趋势结果。
4. 运行 pytest tests/test_summary_evidence.py tests/test_local_assistant.py tests/test_decision_schema.py -q。通过后实际运行中英文各五个固定案例，逐例复核来源、时间关系、健康和适配措辞，记录改善及残余失败。
5. 有效改动完成后重启已确认的本地后端，检查 /health；更新人工评测记录。若实际结果退化，应撤回本次摘要消息改动，不覆盖原始评测证据。
