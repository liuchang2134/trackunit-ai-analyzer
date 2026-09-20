# 文档索引

这个目录此前同时存放九个版本的参赛材料、七套演示稿与十一份发布说明，**没有任何一处说明哪一份是当前的**。本页是那个缺失的入口。

## 先看这几份

| 想了解 | 看这里 |
|---|---|
| **两页读懂项目、AI 做了什么、怎么自己复核** | [参赛说明.md](参赛说明.md) |
| **照着走一遍演示（约 8 分钟）** | [演示路径.md](演示路径.md)；演示前先跑 `scripts/demo_preflight.py` 预检 |
| 项目现在到什么程度、哪些没验收 | [PROJECT_ACCEPTANCE_STATUS.md](PROJECT_ACCEPTANCE_STATUS.md) |
| 怎么启动、怎么跑测试、怎么复核 AI 依据 | [../README.md](../README.md) |
| 核心排查流程的目标与验收标准 | [CORE_WORKFLOW_PLAN.md](CORE_WORKFLOW_PLAN.md) |
| 参考过哪些开源项目、借鉴了什么 | [OPEN_SOURCE_REFERENCES.md](OPEN_SOURCE_REFERENCES.md) |

## 当前参赛材料

| 文件 | 说明 |
|---|---|
| `机联智检_参赛Proposal_v9.md / .docx / .pdf` | 参赛提案。撰写时的模型提供方为 Gemini，**其后默认已改为 DeepSeek**，因此文中模型相关表述与当前源码不一致时，以 `PROJECT_ACCEPTANCE_STATUS.md` 为准。 |
| `机联智检_答辩演示稿_v9.pptx / .pdf` | 答辩演示稿 |
| `机联智检_答辩讲稿_v9.md` | 答辩讲稿 |
| `机联智检_五分钟演示脚本_v9.md` | 五分钟演示脚本 |
| `机联智检_v9_原型演示_中文字幕.mp4 / .srt / .md` | 原型演示录屏与字幕 |
| `机联智检_检查反馈演示_v1.mp4`、`机联智检_模拟功能演示_v1.mp4` | 功能演示录屏 |

**这三份 Markdown 正文已于 2026-09-15 就地更正**，与当前实现一致：模型提供方为 DeepSeek（原写 Gemini）、测试规模 793 项 Python / 170 项 Node（原写 342 / 22）、插件 0.9.1（原写 0.3.0）、分析与图册标注等原本列为"待验收"的项目已改为已验证。Proposal 开头有逐条修订对照表。

仍需注意：**同名 `.docx` 与 `.pdf` 是更正前的导出件，未同步重新生成**；答辩演示稿 `.pptx` 内的文字也仍是更正前的内容。以 Markdown 与 `PROJECT_ACCEPTANCE_STATUS.md` 为准。

## 功能说明

| 文件 | 覆盖范围 |
|---|---|
| [EXTENSION.md](EXTENSION.md) | Chrome 侧栏插件的安装、权限与交接 |
| [LOCAL_ASSISTANT.md](LOCAL_ASSISTANT.md) | AI 排查的运行方式与配置 |
| [AI_REQUEST_STATUS.md](AI_REQUEST_STATUS.md) | AI 请求状态与错误分类 |
| [XGSS_INTEGRATION.md](XGSS_INTEGRATION.md) | XGSS 官方资料入口与图册条目读取 |
| [TRACKUNIT_XGSS_API_ANALYSIS.md](TRACKUNIT_XGSS_API_ANALYSIS.md) | 两套外部接口的联调分析 |
| [TRACKUNIT_HISTORY_SYNC.md](TRACKUNIT_HISTORY_SYNC.md)、[TRACKUNIT_NORMALIZATION.md](TRACKUNIT_NORMALIZATION.md) | Trackunit 历史数据同步与归一化 |
| [PARTS_DEMO.md](PARTS_DEMO.md) | 本地备件目录的演示与来源要求 |
| [INSPECTION_FEEDBACK.md](INSPECTION_FEEDBACK.md) | 检查反馈与续查 |
| [LOCAL_INVESTIGATION_DRAFTS.md](LOCAL_INVESTIGATION_DRAFTS.md) | 本机草稿与恢复 |
| [MAINTENANCE_WORKLIST.md](MAINTENANCE_WORKLIST.md) | 排查任务工作台 |
| 侧栏验证（真实 Chrome） | `node scripts/extension_probe.mjs`：渲染侧栏、验证设备识别与连接握手（8 项检查）；仍有三项需人工确认（见输出 `still_manual`） |
| 图册标注验证（真实 DOM） | `node scripts/xgss_marking_probe.mjs`：在 `https://xgss.xcmg.com` 的本地夹具上验证 AI 检索词只标注该标的行（9 项检查） |
| 侧栏 AI 面板验证 | `node scripts/sidebar_guidance_probe.mjs --report .tmp/g.json`：面板连通、状态落定、无建议时给指引；并记录"工作区只接受扩展来源"这条边界（6 项检查） |
| [TV12U_FAULT_REFERENCE.md](TV12U_FAULT_REFERENCE.md) | 演示用故障码定义 |
| [SYNTHETIC_DATA_GUIDE.md](SYNTHETIC_DATA_GUIDE.md) | 合成数据的生成与边界 |
| [WORK_STATE_MODEL.md](WORK_STATE_MODEL.md)、[COOLING_WARNING.md](COOLING_WARNING.md) | 工况识别与冷却预警两个实验模块 |

## 历史构建的发布说明（位置保留）

`RELEASE_GUIDE.md`、`RELEASE_V8/V9/V10_GUIDE.md`、`RELEASE_V8/V9/V10_NOTES.md` 描述的是历史构建。它们**留在原位是因为构建与校验脚本按固定路径读取**（`scripts/build_release*.py`、`scripts/verify_release*.py`、`tests/test_release_v*.py`），移动会让那些脚本找不到文件。

**它们不代表当前构建。** 当前构建、版本与验收状态一律看 [PROJECT_ACCEPTANCE_STATUS.md](PROJECT_ACCEPTANCE_STATUS.md)。

## 实测记录

`evaluation/` 存放验收证据，其中：

- `ai-grounding-*.md / .json` —— 由 `scripts/evaluate_ai_grounding.py` 生成，**可重复运行**，报告引用可核验性与代码哈希；
- `extension-*-package.json` —— 插件打包校验；
- `2026-09-15-*` —— 本轮界面、设备关联、流式 AI、回放与证据包的验收记录。

其余按日期命名的文件是各阶段的历史记录，保留用于追溯，不代表当前状态。

## 归档

`archive/` 存放被取代的材料：更早的提案与答辩稿、历史构建的发布说明、一次性构建脚本。它们描述的是当时的实现，**不要据此判断当前行为**。

归档由 `scripts/archive_superseded_docs.py` 完成，可用 `--undo` 撤销。
