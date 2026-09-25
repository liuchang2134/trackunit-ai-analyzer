# 基于 Trackunit 平台的车联网 AI 备件和故障预测 Chrome 插件

**机联智检**是面向工程机械售后服务的网页工作区与 Chrome 侧栏插件。在客户已有的 Trackunit 设备页面旁，连接当前及历史故障、连续传感器数据和同 VIN 的 XGSS 图册，提供备件核查、参考估价及潜在故障配件建议。

**当前源码：20260925.4-button-check · Chrome 插件：0.9.31**

## 从这里开始

- 实时使用：按下方步骤运行源码，配置自己的接口，在获授权的 Trackunit 和 XGSS 设备范围内使用。
- 无账号审阅：可在 [Releases](https://github.com/liuchang2134/trackunit-ai-analyzer/releases) 查看已发布的完整项目复现包。发布包是各自发布时点的快照，版本和功能以对应发布说明为准；本次更新的是 `main` 分支源码。
- 更新与验收：[0.9.31 更新说明](docs/RELEASE_0.9.31.md)。

XC948U 是已验证的设备案例之一，不是产品的唯一适用机型。其他设备需具备可读取的 Trackunit 数据、正确 VIN 和获授权的适用图册。

## 主要功能

| 功能 | 交互与结果 |
| --- | --- |
| 关联当前设备 | 在 Trackunit 设备页打开插件，识别资产并校验设备与数据版本 |
| 当前及历史故障 | 切换故障范围，选择事件，保留故障描述、SPN/FMI/SA、来源及状态 |
| AI 配件推荐 | 按故障语义确定部件方向，读取同 VIN 的 XGSS 图册，返回料号、图示、依据及核查条件 |
| 配件参考估价 | 按币种保存用户提供的参考单价与来源，不把参考价当作官方报价 |
| 故障预测 | 从 Advanced Sensors 分批读取通道，或导入 Trackunit CSV，查看温度、压力、转速、负载等连续曲线 |
| 潜在故障配件 | 从每项风险线索直接查询相关图册，显示可能需要核查、准备的备件及图示 |
| 补图与恢复 | 保留已成功读取的资料，可补充图册图示、停止或继续查询，并恢复已保存分析 |

传感器通道数量取决于设备、账号权限与当前页面可导出的数据。曲线区域最多同时展示四项，可切换查看全部已读取通道。状态量、故障编码与连续传感器分开处理，不把停机零值直接判定为损坏。

风险分析当前提供连续工况的风险线索和核查方向，尚不提供经过实车标定的故障发生日期或剩余寿命。历史已解除故障用于复发备库参考，不作为当前故障。图册中存在料号，也不等于该部件已经损坏。

## 从源码启动

推荐 Python 3.12（支持 3.11–3.13）。首次安装依赖需要网络：

```bat
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt -r requirements-xgss.txt
copy .env.example .env
start_local.cmd --port 8890
```

打开 `http://127.0.0.1:8890/assistant-ui/`。在 Chrome 扩展程序页面打开开发者模式，加载仓库的 `extension` 目录；插件可连接本机 8890 或 8892。更新插件文件后，在扩展管理页面点击重新加载。当前网页与插件不需要 Node 构建。

AI 与 Trackunit 凭据在本机 `.env` 配置。XGSS 配置模板见 [xgss-config.example.json](docs/examples/xgss-config.example.json)，使用获准的身份、业务编号和公钥，在本机 `data/local/xgss-config.json` 保存配置。也可用 `XGSS_CONFIG_PATH` 指定本机配置路径。

仓库不提供企业账号、密钥、登录会话、客户车队缓存或整套内部图册。故障接口授权与网页可见事件分别处理；接口没有返回数据不等于设备没有故障。仅克隆源码不会取得企业数据访问权限。

## 实际操作顺序

1. 打开 Trackunit 设备页，点击插件“读取当前设备”。
2. 在 Events 页面读取可见故障，选择当前或历史故障，生成配件推荐并查看图纸。
3. 点击“故障预测”，在 Advanced Sensors 页面设置时间范围，读取当前曲线；也可导入该设备导出的 CSV。
4. 查看 AI 风险线索，点击“潜在故障配件”，核对料号、图中序号与准备条件。
5. 等待读取结束后再切换页面；需要中断时点击“停止读取”。

## 验证与打包

2026-09-25 本地验收通过 606 项 Node 测试和 632 项 Python 核心测试，并实际检查故障切换、图纸缩放、潜在配件查询与补图。设备关联及实时曲线读取已在重载后的 Chrome 插件中确认。验收范围和限制见更新说明。

源码不跟踪生成的 ZIP。运行涉及打包的 Node 测试前，先构建当前版本插件包：

```bat
.venv\Scripts\python.exe scripts\build_extension.py
node --test tests\*.test.cjs
```

构建器不会覆盖同版本已有 ZIP；若已有有效包，可直接运行测试。Python 测试使用 `pytest`，所需依赖见 `requirements.txt` 与 `requirements-xgss.txt`。

## 代码导航

- `app/assistant_ui`：原生 JavaScript 网页、故障与配件界面、参考估价、连续曲线。
- `extension`：Chrome Manifest V3 侧栏、页面故障读取、Advanced Sensors 分批采集。
- `app/xgss_direct_api.py`、`app/xgss_catalog_search.py`、`app/xgss_catalog_images.py`：XGSS 分类、零件和图示读取。
- `app/xgss_research_*`、`app/fault_part_grounding.py`：资料证据、AI 分析及故障因果约束。
- `app/sensor_series.py`、`app/sensor_risk.py`：连续序列与风险解释。
- `tests`：身份隔离、采集恢复、证据、AI 输出与交互测试。
- `scripts`：运行、打包、评测及历史发布工具。
- `frontend`：早期 React 界面源码，当前入口不依赖它。

第三方许可证保留在相应目录；XCMG、Trackunit 等名称与商标属于各自权利人。公开源码不表示获得平台官方背书。
