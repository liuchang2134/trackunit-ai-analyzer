# 机联智检

辅助已有车联网平台处理设备故障的工具：网页工作区 + Chrome 侧栏插件。真实分析使用 Gemini API；设备资料、草稿和检查记录保存在本机。

## 直接展示一个案例

当前构建：`20260915.3-demo-case`。

启动后打开 [完整演示案例](http://127.0.0.1:8892/assistant-ui/?demo=1)，或在网页选择「演示案例」。

案例：**滑移装载机左侧行走异常，仪表出现 H10101**。

1. 观察模拟现场现象和行走指令／响应趋势。
2. 查阅 H10101 的协议定义及来源。
3. 展示预设的 AI 分析示例，列出待检查的控制支路。
4. 展开模拟检查结果，查看线束问题和复测记录。
5. 按检查依据给出备件类型建议，导出演示讲解。

这是用户要求编写的展示案例。除注明出处的代码定义外，设备、工况数值、检查和结论均为虚构。演示不调用 Trackunit、Gemini 或 XGSS，不消耗 API 配额，不写入真实设备或诊断历史；不是实机效果证明。14分钟是压缩演示时间，不是实际维修工时。数据在 `data/demo_case.json`。

## 启动

Windows，使用 Python 3.12，在项目根目录的 CMD 运行。首次克隆：

```bat
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt -r requirements-xgss.txt
copy .env.example .env
start_local.cmd --port 8892
```

已有环境直接运行 `start_local.cmd --port 8892`。本机检查用 `start_local.cmd --port 8892 --check-only`；不会停止或重启已有进程。演示无需填写密钥；真实 AI 分析需要在 `.env` 配置 Gemini。

网页入口：[设备排查](http://127.0.0.1:8892/assistant-ui/)。Chrome 插件直接加载项目中的 `extension` 文件夹，连接设置选择8892，详见 [插件说明](extension/README.md)。不需要单独编译当前网页和插件。

## 功能与当前边界

| 功能 | 状态 |
|---|---|
| 完整模拟案例 | 五阶段讲解、趋势、证据、检查反馈和导出，可离线演示 |
| 设备数据与故障资料 | 搜索、数据版本选择、趋势及 CSV 导出 |
| 排查任务与草稿 | 创建任务、记录检查、归档、草稿恢复及冲突检查 |
| TV12U 查码 | 本机可读取72条私有参考资料；完整原表和提取文件不随 Git 分发。演示所需 H10101 定义独立提供 |
| Gemini | 接入已实现，最近完整请求受每日额度限制；完整真实链路仍待验收 |
| Trackunit | 已验证工时接口；故障事件访问仍返回401 |
| XGSS | 获准 VIN 的官方整机图和物料明细已在浏览器显示；故障参数和真实设备交接仍待联调 |
| Chrome 侧栏 | 源码及消息逻辑测试已有；真实安装、Trackunit 登录与设备关联仍待验收 |
| 工况与冷却预警实验 | 附带模拟回放所需模型和测试片段，未完成实机效果验证 |

## 开发与验证

```bat
.venv\Scripts\python.exe -m pytest tests -q
node --test tests/*.test.cjs
```

历史封存包验收、完整训练数据复算以及本机私有参考资料检查，在对应资料未分发时会明确跳过；其余业务规则测试照常运行。CI 同时检查旧 `frontend` 的类型和构建，当前产品界面位于 `app/assistant_ui/`。

- [案例说明](docs/DEMO_CASE.md)
- [当前验收状态](docs/PROJECT_ACCEPTANCE_STATUS.md)
- [Trackunit 与 XGSS 接口](docs/TRACKUNIT_XGSS_API_ANALYSIS.md) · [XGSS 对接](docs/XGSS_INTEGRATION.md)
- [TV12U 参考资料](docs/TV12U_FAULT_REFERENCE.md) · [任务记录](docs/MAINTENANCE_WORKLIST.md) · [草稿](docs/LOCAL_INVESTIGATION_DRAFTS.md)
- [开源组件与许可证](docs/OPEN_SOURCE_REFERENCES.md)

Git 不包含 `.env`、`data/local/`、真实缓存、内部原始文件、私人截图、旧参赛材料或本机软件包。旧 v10 包保留于本机历史目录，不包含当前案例；当前功能以本仓库源码为准。
