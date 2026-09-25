# 公开数据集候选：故障类型与提前预警

核验日期：2026-09-22。仅核对官方仓库/原论文与元数据，尚未下载、训练或验证本项目模型。公开数据用于独立算法基线，不冒充当前 Trackunit 设备的工况，不与 XGSS VIN 伪造配对。

| 候选 | 官方数据内容 | 可验证目标 | 不能据此宣称 |
|---|---|---|---|
| UCI Condition monitoring of hydraulic systems | 液压试验台；2,205 个 60 秒循环；压力、流量、温度、振动等；冷却器、阀、泵内泄漏、蓄能器的状态/等级 | 多种部件异常的识别与故障方向分类 | 循环序号不是实际设备退化寿命；没有对应失效倒计时，不能推出“还有几小时损坏” |
| SCANIA Component X，当前 v3 | 真实重卡匿名发动机部件；运行读数、车辆配置、维修记录；含 time-to-event 与验证/测试标签 | 基于运行历史的故障风险时间窗口、删失数据下的生存分析基线 | 部件与特征匿名，不能对应徐工具体零件；相对 time units 不得写成运行小时；不能直接作为 XC948U 模型 |
| MetroPT-3 | 实际运行列车空压机的压力、温度、电流、阀状态；原始 CSV 未逐行标注，另给公司故障/维修时间报告 | 连续时序异常与故障前预警；需要据维修报告构造并核对评价窗口 | 不是工程机械整机故障数据；少量事件不足以宣称全机型准确率 |
| RWTH Off-Highway Twins | 真实轮式装载机 8 次试验；工作液压压力/位移、轮速、驾驶室加速度、相机及 LiDAR | 工况识别和正常行为基线，需先检查采样与工况标注粒度 | 官方说明未列故障发生、维修或 RUL 标签，不能直接用于故障倒计时训练 |

上述四套官方数据页均标 CC BY 4.0；使用时保留作者、来源与修改说明。原始文件无需进入产品界面，也不需要为每套数据增加一个演示导航。

## 官方来源

- UCI hydraulic：[数据页](https://archive.ics.uci.edu/dataset/447/condition+monitoring+of+hydraulic+systems)。官方压缩下载约 73.1 MB。
- SCANIA：[v3 数据页](https://researchdata.se/en/catalogue/dataset/2024-34)，当前共 11 文件、约 1.54 GiB；版本 2 已补充测试标签。应使用当前版本，不沿用旧竞赛 PDF 中“测试标签未发布”的历史状态。
- SCANIA [竞赛说明](https://api.researchdata.se/dataset/2024-34/3/file/documentation?filePath=2024_IDA_challenge_v2.pdf)：故障前 48–24、24–12、12–6、6–0 **time units** 分组，非小时。
- SCANIA [原论文](https://api.researchdata.se/dataset/2024-34/3/file/documentation?filePath=Scania_Component_X.pdf)：部件匿名；采样不均匀；数据包括未观察到维修事件的设备；维修/采样频率有隐私扰动。
- MetroPT-3：[UCI 数据页](https://archive.ics.uci.edu/dataset/791/metropt3%2Bdataset)，约 208.3 MB。页面分别写原采集 1 Hz 与提供数据 0.1 Hz；使用前以文件时间戳核验间隔，不凭页面一句话假定固定采样率。故障报告日期也须与原论文/附录对照。
- NASA [C-MAPSS](https://data.nasa.gov/dataset/cmapss-jet-engine-simulated-data) 可做退化/RUL算法对照，但对象为模拟航空发动机，当前不优先，避免进一步偏离工程机械场景。
- RWTH [官方数据页](https://publications.rwth-aachen.de/record/843595)，[当前访问说明](https://publications.rwth-aachen.de/record/843595/files/Datenzugang_DataAccess_843595_20250828.pdf)。8 个包约 85 GB，通过 S3 提供，未下载；本项目不需要为了工况时序先下载全部点云/视频。

## 应用判断

优先级建议：若优先“什么部件异常”，先做 hydraulic 故障分类；若优先“何时可能失效”，先做 SCANIA 时间窗口基线。它们是两个独立验证目标，不能把两套模型拼在一起就宣称已预测徐工整机某个料号的失效时间。

部署到本项目仍需：对应设备实际可读的信号、相同物理含义与单位、历史故障/维修标签，以及独立验证。故障码→XGSS→备件邮件这条流程不依赖上述模型训练，可单独推进。
