# 开源参考与采用记录

以下按日期记录当时的调研、采用与验收情况；旧构建、模型配置和封存包说明不代表当前交付状态。当前进度以源码中的 `docs/PROJECT_ACCEPTANCE_STATUS.md` 为准。提到的 `docs/evaluation/` 文件为本机历史验收记录，不随源码分发。

## 2026-09-15：核心查码与人工记录

阅读 [ACL Findings 2025 的引用可信性研究](https://aclanthology.org/2025.findings-acl.919/)、[LangGraph 官方仓库](https://github.com/langchain-ai/langgraph)和 [FastAPI APIRouter 文档](https://fastapi.tiangolo.com/tutorial/bigger-applications/)。结合本项目采用三点：原表精确查码与 AI 解释分开、人工检查记录不依赖模型成功、继续使用单个应用。已实现 TV12U 原文来源与内容校验、强制引用、人工代码适用确认、保留逐项检查的最近反馈，并将实验入口收拢。仅借鉴方法，未复现论文训练、复制项目代码或新增框架依赖；72条定义直接查表，无需向量库。

## 2026-09-14：待处理工作台与本机排查任务

再次阅读 [Atlas CMMS 官方仓库](https://github.com/Grashjs/cmms) 的 Work Orders & Maintenance 及工作流说明，参考任务、记录、进度与历史的组织方式。该仓库标示 AGPL-3.0；本次仅参考流程，自行使用 SQLite、FastAPI 与现有原生 JavaScript 实现，没有复制源码、安装平台或新增依赖。任务归档与原始设备故障状态分开处理，保留设备版本和记录原文。实现及实测说明见开发目录的 MAINTENANCE_WORKLIST.md；尚未加入封存 v9 包。


## 2026-09-14：设备搜索、来源筛选与记录排序

阅读 [Traccar Web MainToolbar.jsx](https://github.com/traccar/traccar-web/blob/master/src/main/MainToolbar.jsx) 的关键字搜索、状态筛选和排序控制，以及 [DeviceList.jsx](https://github.com/traccar/traccar-web/blob/master/src/main/DeviceList.jsx) 的设备行组织。采用“先找设备/版本，再进入详情”的交互方式，使用现有原生 JavaScript/CSS 与 dialog 自行实现，没有复制其 React/MUI 源码或安装依赖。本项目只按所载入故障记录的末次状态和级别筛选，不复用在线状态推断健康。本机历史验收记录，不随源码分发：`docs/evaluation/2026-09-14-device-finder.md`。

## 2026-09-14：故障资料与备件详情

再次检查 [Atlas CMMS 官方仓库](https://github.com/Grashjs/cmms) 的工单历史、设备和库存流程，并查看 [Tabler Card 官方文档](https://docs.tabler.io/ui/components/card) 的标题、内容与操作组织方式。本模块沿用“记录—相关资料—下一步操作”的组织思路，将故障原文、适用备件、出处和 AI 排查入口放在一个可关闭的详情区域。未复制源码、未安装这两个项目；Atlas 仓库标示 AGPL-3.0，当前使用仅为流程参考，Tabler 仍沿用既有自写样式。

具体实现为本机只读查询接口与原生 DOM 详情区域。目录文字按原文显示，独立标出来源、页码、版本、演示属性和序列号限制；XGSS 无已确认接口时不生成跳转按钮或虚构手册。AI 诊断仍通过单独操作请求 Gemini。该直接查询不被记为 AI 推理成功或实际备件适配认证。

## 2026-09-14：设备时序图已采用 Apache ECharts

采用 Apache ECharts **6.0.0**，来源为 [官方仓库](https://github.com/apache/echarts) 与 npm 官方注册表的固定版本包。下载包核对 SHA-512 integrity 后，只取发布版 JavaScript、LICENSE 和 NOTICE，保存在 `app/assistant_ui/vendor/echarts/`，来源和完整性记录见同目录 SOURCE.json。许可证 Apache-2.0；页面本地加载，不依赖运行时 CDN，没有新增收费服务。

参考官方 [坐标轴](https://echarts.apache.org/handbook/en/concepts/axis/)、[事件与动作](https://echarts.apache.org/handbook/en/concepts/event/) 和 [无障碍](https://echarts.apache.org/handbook/en/best-practices/aria/) 文档。实际实现工时/怠速/燃油折线、时间窗口、缩放滑块、故障时间标记、可读的图表描述与数据表。采用折线而非平滑插值，缺失值不连接，避免把未观测区间画成连续测量。数据质量筛查与数值统计在后端独立完成。

已验证：真实导入 36 个时点及缺失怠速状态；模拟 105 个时点切为末尾一小时 61 点时，完整载入时段的统计不变；1280×820 和窄窗口布局。CSV 下载按钮已有实现但本轮未验收下载文件；未做完整屏幕阅读器测试。详见 evaluation/ux-20260914/审查与修正.md。

用户要求：开发过程中持续查看 GitHub 开源项目，寻找可参考的优化方案。每个主要模块实施前，检查相关成熟项目；记录来源、具体借鉴点、许可证、依赖与本地部署成本，以及采用或不采用的理由。实际引用代码时核实对应版本并保留许可证及署名。

## 2026-09-14：设备分析 UI

| 项目 | 检查来源 | 借鉴点 | 当前采用情况 |
| --- | --- | --- | --- |
| Tabler | https://github.com/tabler/tabler ，MIT | 紧凑后台导航、统一表格和指标层级 | 自行实现导航栏、设备详情和指标布局；未复制源码或安装包 |
| ThingsBoard | https://github.com/thingsboard/thingsboard 及官方 dashboard 文档 | 设备、时间窗口、告警与数据可视化组织 | 作为业务流程参考；未引入平台依赖 |
| NetBox | https://github.com/netbox-community/netbox ，Apache-2.0 | 设备资料、关系及来源组织 | 后续设备与备件详情参考；未引入源码 |

## 后续研究队列
- 故障与时序异常：成熟时间序列库的窗口处理、缺失值和回测设计。
- 本地备件检索：带来源引用的本地文档检索、精确型号过滤与混合检索。
- 模型评测：固定用例、原始响应保存、失败分类和可重复对比。
- 插件：侧栏设备上下文与离线资源打包。

以上队列尚未完成项目筛选；不视为已采用或实现。

## 2026-09-14：Qwen3.5 本地候选模型

核查官方 https://ollama.com/library/qwen3.5:9b ，标注 Apache-2.0、Q4_K_M、约 6.6 GB。已通过本地 Ollama 官方拉取接口下载，实际大小 6594474711 字节，摘要 6488c96fa5faab64bb65cbd30d4289e20e6130ef535a93ef9a49f42eda893ea7。使用相同助手协议、8192 上下文、关闭思考模式，对同一人工模拟反馈做中英文初测；结果见 evaluation/2026-09-14-qwen35-feedback.json。初测时仅作为候选；后续同代码案例和本地后端验证见 evaluation/2026-09-14-summary-source-scope.md，v6 默认配置已更新为 qwen3.5:9b。不能将模型页面基准成绩当作本项目诊断效果。

## 持续筛选原则

按模块开发时查阅官方 GitHub 仓库及文档，优先评估能解决当前问题的流程和组件。筛选依据包括本地部署、现有电脑资源、额外现金成本、许可证、维护情况和可验证效果。参考记录明确区分已阅读、拟采用与已实现；引用代码或新增依赖前锁定版本并保留必要署名。研究与当前交付并行推进，不为更换框架而重写已经验证的功能。

## 2026-09-14：持续参考与车队界面候选

用户再次确认：实现过程中持续寻找 GitHub 开源项目参考优化。后续每个主要模块的改动说明应指出参考项目、实际采用内容和验证结果。

本次复查 Tabler、ThingsBoard 官方仓库，并阅读 https://github.com/traccar/traccar-web 的 README。Traccar Web 是基于 React、Material UI 和 MapLibre 的 GPS 跟踪前端，仓库标注 Apache-2.0，包含地图、报告与设备管理。拟进一步查看其设备选择、详情导航与报告筛选交互，用于本项目的设备上下文切换。当前仅完成仓库级筛选，尚未检查具体组件源码、复制代码或安装依赖。

界面优化方向：紧凑导航、清晰表格、统一状态色；以设备、故障证据、备件和检查记录组织工作区，AI 分析作为设备工作流内的操作。具体布局仍需实际页面对照和交互验证后落地。

## 2026-09-14：维修文档检索候选补充

- RAGFlow：https://github.com/infiniflow/ragflow 。本次阅读官方 README 的文档分块、可追溯引用、混合召回与重排、自托管要求；仓库标注 Apache-2.0。拟参考原文片段查看与引用定位，让维修建议能追溯到手册章节或页码。README 当前列出至少 16 GB RAM、50 GB 磁盘及 Docker 等要求，结合本机同时运行大模型的资源需求，暂不引入完整平台。未安装、未复制源码，尚未实现该文档检索功能。
- Haystack：https://github.com/deepset-ai/haystack 。本次阅读官方 README 的模块化检索、过滤、路由与生成流程。拟参考将机型及序列号适用范围过滤与文本相关性排序分开处理，避免语义相近但不适用的备件进入推荐。未安装、未复制源码；具体组件、版本、许可证与关闭默认遥测的配置仍需在实际选用前核实。
- 两者均是待验证的设计参考。当前精确型号与目录来源校验继续保留，不能把参考项目的功能或效果写成机联智检已交付能力。

## 2026-09-14：浏览器侧栏和设备上下文

查看 https://github.com/GoogleChrome/chrome-extensions-samples （Apache-2.0）、https://developer.chrome.com/docs/extensions/reference/api/sidePanel 和 scripting 文档中 activeTab 权限说明。采用 MV3 侧栏加点击后临时访问当前标签页的设计，不需要 scripting 或全站读取权限。只从核验过的资产详情 URL 提取 UUID，明确选择本地历史版本。代码自行实现，未复制示例；运行与安装验证范围见 EXTENSION.md。

## 2026-09-14：检查反馈闭环

参考 https://github.com/Grashjs/cmms （Atlas CMMS，仓库标注 AGPL-3.0）的工单、历史和维修记录流程。采用“诊断记录附加检查结果，再继续调查”的交互思路；原报告保留，人工反馈标记未经验证，不直接变成已确认故障或维修结论。自行实现本地 JSON 存储与界面，未复制源码、未安装依赖，不增加云服务开支。若日后复用代码，再核实对应版本和许可证要求。

## 2026-09-14：评测可诊断性

查看 Promptfoo 官方的 assertions 文档与 Ollama provider 文档：
- https://github.com/promptfoo/promptfoo/blob/main/site/docs/configuration/expected-outputs/index.md
- https://www.promptfoo.dev/docs/providers/ollama/

借鉴“固定案例与显式断言分离”的评测组织方法，在现有 Python 评测脚本中增加单案例选择、每一步允许动作、模型决策和纠正反馈记录。未复制源码、未安装 Promptfoo，也未调用外部模型。若后续采用其代码或依赖，需再核实具体版本许可证及运行成本。

## 2026-09-14：本地模型能力对照

官方源码与模型来源：https://github.com/QwenLM/Qwen3 ，https://ollama.com/library/qwen3:8b 。官方8b页面列明Apache-2.0、Q4_K_M、约5.2GB。选择它与现有4b做相同协议的对照，避免同时更换推理框架造成混杂。仅通过本地Ollama拉取官方权重，评测输入是人工模拟数据。当前处于评测阶段，未据模型宣传性能认定适用于工程诊断。

## 2026-09-14：工况分类

参考 https://github.com/aeon-toolkit/aeon 的时序分类工作流，以及 https://scikit-learn.org/stable/modules/cross_validation.html 对组间独立验证的说明。实现采用scikit-learn1.7.2随机森林固定基线，未引入aeon依赖；保留整段episode划分，禁止标签、场景和未来数据进入特征。scikit-learn为可选训练依赖，模型导出数值JSON供本地纯Python推理。结果与限制见WORK_STATE_MODEL.md。

## 2026-09-14：冷却热事件预警

再次查看 [aeon](https://github.com/aeon-toolkit/aeon) 的时序算法及基准评价组织方式，以及 [scikit-learn 随机森林官方接口](https://scikit-learn.org/stable/modules/generated/sklearn.ensemble.RandomForestClassifier.html)。继续用既有 sklearn 1.7.2 训练环境和自行编写的数值 JSON 推理，不安装 aeon，不复制其代码。评价按 [Carrasco 等论文](https://arxiv.org/abs/2105.12818) 所讨论的事件前窗口和提前发现思路设计，同时保留温度阈值对照及误报计数；未声称复现完整论文方法。热平衡为自编的简化模拟，所有参数是实验假设；具体来源、采用范围和结果见 [冷却预警说明](COOLING_WARNING.md)。
