# Trackunit AI Analyzer

这是 Phase 1 的最小可运行项目，用来验证工程机械车联网数据的 AI 分析流程。

本阶段的目标是验证这一条链路：

```text
本地 mock Trackunit JSON 数据 -> 标准化数据结构 -> AI 分析 prompt -> 报告输入
```

## 本阶段包含什么

- FastAPI 后端服务
- 本地 mock JSON 数据
- Trackunit-like 设备、遥测、故障码数据标准化
- 英文 AI prompt 生成
- React + TypeScript + Vite 最小可视化 Dashboard
- Recharts 图表
- 单台设备健康分析 prompt
- Fleet weekly report prompt
- Pytest 自动测试

## 本阶段不包含什么

- 不接真实 Trackunit API
- 不调用真实 AI 大模型 API
- 不使用数据库
- 不做生产部署

## 项目结构

```text
trackunit-ai-analyzer/
  app/
    main.py
    models.py
    normalizer.py
    prompt_builder.py
    mock_data/
      machines.json
      telemetry_snapshots.json
      fault_codes.json
  tests/
    test_normalizer.py
    test_prompt_builder.py
  frontend/
    package.json
    index.html
    vite.config.ts
    tsconfig.json
    src/
      main.tsx
      App.tsx
      api.ts
      types.ts
      components/
        SummaryCards.tsx
        FleetTable.tsx
        UtilizationChart.tsx
        FaultChart.tsx
        MachineDetail.tsx
      styles.css
  requirements.txt
  README.md
```

## 文件说明

```text
app/main.py
FastAPI 入口文件，提供 API 接口。

app/models.py
定义设备、遥测、故障码、prompt 返回结果的数据模型。

app/normalizer.py
读取本地 mock JSON，并把 Trackunit-like 原始字段转换成统一字段。

app/prompt_builder.py
根据标准化后的设备、遥测、故障数据生成英文 AI 分析 prompt。
这里只生成 prompt，不调用真实 AI。

app/mock_data/machines.json
mock 设备主数据。

app/mock_data/telemetry_snapshots.json
mock 遥测快照数据。

app/mock_data/fault_codes.json
mock 故障码数据。

tests/test_normalizer.py
测试数据标准化逻辑。

tests/test_prompt_builder.py
测试 prompt 是否包含关键业务字段。

frontend/
React + TypeScript + Vite 前端，用于可视化 mock 车联网数据。
```

## 安装依赖

进入项目目录：

```powershell
cd "C:\Users\xcmgusa\OneDrive - XCMG North America Corporation\Documents\车联网AI平台\trackunit-ai-analyzer"
```

如果你的电脑已经配置了 Python，可以运行：

```powershell
python -m pip install -r requirements.txt
```

如果使用 Codex 自带的 Python 运行环境，可以运行：

```powershell
& "C:\Users\xcmgusa\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -m pip install -r requirements.txt
```

## 启动 FastAPI 服务

使用本机 Python：

```powershell
python -m uvicorn app.main:app --reload --port 8890
```

使用 Codex 自带 Python：

```powershell
& "C:\Users\xcmgusa\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -m uvicorn app.main:app --reload --port 8890
```

启动后打开：

```text
http://127.0.0.1:8890/docs
```

这里可以直接测试所有 API。

## 启动前端 Dashboard

需要同时启动后端和前端：

```text
后端端口: 8890
前端端口: 5173
```

先启动后端：

```powershell
python -m uvicorn app.main:app --reload --port 8890
```

然后打开另一个 PowerShell 窗口，启动前端：

```powershell
cd "C:\Users\xcmgusa\OneDrive - XCMG North America Corporation\Documents\车联网AI平台\trackunit-ai-analyzer\frontend"
npm install
npm run dev
```

访问地址：

```text
FastAPI Docs: http://127.0.0.1:8890/docs
Dashboard: http://127.0.0.1:5173
```

Dashboard 当前展示：

```text
1. Summary Cards
2. Fleet Table
3. Utilization Chart
4. Fault Chart
5. Machine Detail Panel
6. AI Prompt / Real LLM Report 显示
```

## 运行测试

使用本机 Python：

```powershell
python -m pytest
```

使用 Codex 自带 Python：

```powershell
& "C:\Users\xcmgusa\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -m pytest
```

当前测试覆盖：

```text
1. mock 设备数据是否正确标准化
2. telemetry 字段是否正确转换
3. fault code 字段是否正确转换
4. 单台设备 prompt 是否包含关键字段
5. fleet prompt 是否包含风险设备、低利用率设备、重复故障
```

## API 示例

健康检查：

```text
GET /health
```

## Trackunit API 调用策略

当前推荐使用“缓存优先”的方式，避免每次用户提问都实时扫描 Trackunit API。

```text
Trackunit API -> 手动/定时同步 -> 本地 cache -> AI 问答分析
```

原因：

```text
1. Trackunit REST API 有 rate limit，超过会返回 HTTP 429。
2. fleet snapshot 已包含油量、发动机状态、位置、运行小时等关键字段。
3. 车队级问题优先查 cache，单台设备深查再实时调用 API。
```

建议配置：

```env
DATA_SOURCE=trackunit_cache
TRACKUNIT_CACHE_FIRST=true
TRACKUNIT_CACHE_TTL_SECONDS=300
TRACKUNIT_REFRESH_STALE_CACHE_ON_ASK=false
TRACKUNIT_REALTIME_SINGLE_MACHINE=true
TRACKUNIT_LIVE_RETRIES=1
TRACKUNIT_AUTO_SYNC_ENABLED=false
TRACKUNIT_SYNC_INTERVAL_SECONDS=300
```

说明：

```text
TRACKUNIT_CACHE_FIRST=true
车队问题优先使用本地 cache，减少 Trackunit API 调用。

TRACKUNIT_CACHE_TTL_SECONDS=300
cache 在 300 秒内视为新鲜数据。

TRACKUNIT_REFRESH_STALE_CACHE_ON_ASK=false
cache 过期时，用户问答仍然先用 cache，不在提问时自动刷新 Trackunit API。
刷新数据请使用手动同步或后台自动同步。

TRACKUNIT_REALTIME_SINGLE_MACHINE=true
单台设备问题允许实时补查。

TRACKUNIT_AUTO_SYNC_ENABLED=false
默认不自动同步，避免开发时频繁触发 API 限流。
如需后台自动同步，改为 true。
```

手动同步 fleet snapshot：

```text
POST http://127.0.0.1:8890/sync/trackunit/fleet
```

查看 cache 状态：

```text
GET http://127.0.0.1:8890/cache/status
```

如果看到 `Trackunit API rate limit reached (429)`，说明 Trackunit 限流了。等待一段时间后再同步，或者提高同步间隔。

返回 mock 设备列表：

```text
GET /machines
```

返回单台设备：

```text
GET /machines/M-1002
```

返回单台设备遥测数据：

```text
GET /machines/M-1002/telemetry
```

返回单台设备故障码：

```text
GET /machines/M-1002/faults
```

生成单台设备 AI 分析 prompt：

```text
POST /analysis/machine/M-1002/prompt
```

生成 fleet weekly report prompt：

```text
POST /analysis/fleet/prompt
```

Dashboard 汇总：

```text
GET /dashboard/summary
```

生成单台设备真实 AI 报告：

```text
POST /analysis/machine/M-1002/ai-report
```

生成 fleet 真实 AI 报告：

```text
POST /analysis/fleet/ai-report
```

## Mock 数据设计

本阶段 mock 了 5 台设备：

```text
M-1001: excavator
M-1002: wheel loader
M-1003: roller
M-1004: boom lift
M-1005: telehandler
```

其中故意设计了几类异常情况：

```text
低利用率设备: M-1005
重复故障设备: M-1002
离线超过 72 小时设备: M-1003
缺失燃油数据设备: M-1004
```

这样做的目的是验证 AI prompt 能不能正确描述风险，而不是假设所有数据都完美。

## 下一阶段如何接入真实 Trackunit API

Phase 2 建议新增一个 Trackunit 数据同步模块，但保留现在的 `normalizer.py` 和 `prompt_builder.py` 结构。

建议步骤：

```text
1. 从环境变量读取 Trackunit client_id、client_secret、username、password；
2. 调用 Trackunit token endpoint 获取 access_token；
3. 调用 asset、location、AEMP fleet snapshot、faults、time-series endpoint；
4. 保存原始 API payload，方便排查；
5. 把真实 Trackunit payload 传给 normalizer；
6. 继续复用 prompt_builder 生成 AI 分析 prompt；
7. 后续再把标准化数据写入数据库。
```

这样 Phase 1 的报告逻辑不用推倒重来，只需要把数据来源从本地 mock JSON 换成真实 Trackunit API。

## Local AI with Ollama + Qwen2.5 7B

Phase 1.7 支持用本机 Ollama + Qwen2.5 7B 生成 AI 报告。

本阶段仍然使用 mock Trackunit data：

```text
不接真实 Trackunit API
不接数据库
默认使用本地 Ollama；Gemini 云模型为可选模式
```

### A. 确认模型是否已安装

如果你已经下载模型，可以用以下命令确认：

```powershell
ollama list
```

如果列表里看到：

```text
qwen2.5:7b
```

说明模型已经安装。

### B. 安装 Ollama

请去 Ollama 官网安装 Windows 版本：

```text
https://ollama.com
```

安装完成后，打开新的 PowerShell。

### C. 下载模型

默认模型：

```powershell
ollama pull qwen2.5:7b
```

可选 instruct 模型：

```powershell
ollama pull qwen2.5:7b-instruct
```

### D. 测试模型

```powershell
ollama run qwen2.5:7b
```

如果模型能正常回答问题，说明本地模型可用。

### E. 配置 .env

在项目根目录创建 `.env`：

```text
AI_PROVIDER=ollama_local
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_MODEL=qwen2.5:7b
```

如果你下载的是 instruct 模型，可以改成：

```text
OLLAMA_MODEL=qwen2.5:7b-instruct
```

系统不再提供假 AI fallback。若本地模型不可用，请切换 Gemini 或修复 Ollama 服务。

### F. 启动后端

```powershell
python -m uvicorn app.main:app --reload --port 8890
```

或使用 Codex 自带 Python：

```powershell
& "C:\Users\xcmgusa\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -m uvicorn app.main:app --reload --port 8890
```

### G. 启动前端

```powershell
cd frontend
npm install
npm run dev
```

如果 PowerShell 找到的是 Codex 自带 node，可以先运行：

```powershell
$env:PATH = "C:\Program Files\nodejs;" + $env:PATH
```

### H. 访问页面

```text
FastAPI Docs:
http://127.0.0.1:8890/docs

Dashboard:
http://127.0.0.1:5173
```

### I. 费用说明

```text
ollama_local 不产生云 API token 费用，但会使用本机 CPU/GPU 资源和电力。
gemini 会调用 Google Gemini API，可能消耗免费额度或产生费用。
```

## Optional Cloud AI with Gemini

项目现在支持在页面上切换：

```text
本地 Qwen: AI_PROVIDER=ollama_local
云模型 Gemini: ai_provider=gemini
```

Gemini API Key 只放在后端 `.env`，不要放进前端代码。

`.env` 示例：

```text
AI_PROVIDER=ollama_local
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_MODEL=qwen2.5:7b

GEMINI_API_KEY=你的新 Gemini API Key
GEMINI_MODEL=gemini-flash-latest
GEMINI_BASE_URL=https://generativelanguage.googleapis.com/v1beta
```

说明：

```text
页面上的“本地 Qwen / Gemini”按钮只控制本次请求使用哪个 provider。
前端不会看到 GEMINI_API_KEY。
如果 Gemini key 无效、没有网络或额度超限，后端会返回清晰错误。
```

### 常见错误

如果返回：

```text
Ollama is not running. Please start Ollama and retry.
```

说明 Ollama 服务没有启动。请启动 Ollama 后重试。

如果返回：

```text
Model qwen2.5:7b is not available. Please run: ollama pull qwen2.5:7b
```

说明模型还没下载，或 `.env` 里的 `OLLAMA_MODEL` 写错了。

## Phase 2: Trackunit API Cache + Natural Language Fleet Query

Phase 2 增加了真实 Trackunit API 接入层和自然语言车队查询功能。

当前仍然是 read-only：

```text
不做远程控制
不锁车
不解锁
不下发命令
```

### A. 当前支持两种数据源

```text
mock
trackunit_cache
```

配置在项目根目录 `.env`：

```text
DATA_SOURCE=mock
```

如果已经同步过真实 Trackunit 数据，可以改成：

```text
DATA_SOURCE=trackunit_cache
```

如果 `trackunit_cache` 不存在，系统会回退到 mock 数据。

### B. 使用 mock 数据测试自然语言问答

保持：

```text
DATA_SOURCE=mock
AI_PROVIDER=ollama_local
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_MODEL=qwen2.5:7b
```

启动后端和前端后，在 Dashboard 里使用 **AI Fleet Assistant**。

也可以直接调用 API：

```powershell
Invoke-RestMethod -Method Post `
  -Uri "http://127.0.0.1:8890/ask" `
  -ContentType "application/json" `
  -Body '{"question":"Which machines are offline for more than 72 hours?"}'
```

### C. 配置 Trackunit API credentials

所有 Trackunit credentials 只能放在 `.env`，不要写进代码：

```text
TRACKUNIT_BASE_URL=
TRACKUNIT_AUTH_URL=
TRACKUNIT_CLIENT_ID=
TRACKUNIT_CLIENT_SECRET=
TRACKUNIT_SCOPE=api
TRACKUNIT_USERNAME=
TRACKUNIT_PASSWORD=
TRACKUNIT_FLEET_SNAPSHOT_ENDPOINT=
TRACKUNIT_TIME_SERIES_ENDPOINT=
TRACKUNIT_SINGLE_ASSET_ENDPOINT=
TRACKUNIT_FAULTS_ENDPOINT=
```

Endpoint 暂时通过配置项提供，因为正式字段和 URL 需要根据 Trackunit 文档或实际账号权限确认。

### D. 手动同步 Trackunit 数据

同步 fleet snapshot：

```text
POST /sync/trackunit/fleet
```

同步 time series：

```text
POST /sync/trackunit/timeseries
Body: {"start_date":"2026-05-26T00:00:00Z","end_date":"2026-06-02T00:00:00Z"}
```

同步 faults：

```text
POST /sync/trackunit/faults
Body: {"start_date":"2026-05-26T00:00:00Z","end_date":"2026-06-02T00:00:00Z"}
```

查看同步日志：

```text
GET /sync/logs
```

同步后的标准化数据会保存到：

```text
data/cache/machines_cache.json
data/cache/telemetry_cache.json
data/cache/faults_cache.json
data/cache/sync_logs.json
```

### E. 使用 /ask 自然语言查询

请求：

```text
POST /ask
```

Body：

```json
{
  "question": "Which machines are offline for more than 72 hours?"
}
```

返回：

```text
question
intent
answer_markdown
used_data
data_source
provider
model
error
```

### F. 示例问题

```text
Which machines are offline for more than 72 hours?
Which machines have repeated faults?
Show me the top 10 low utilization machines this week.
What happened to machine M-1002?
Generate a management summary for the fleet.
Which machines need immediate service attention?
Summarize CAN faults by model.
Compare excavators and wheel loaders by utilization.
Which machines have missing fuel data?
Give me a weekly fleet health report.
```

### G. 数据安全说明

```text
Trackunit token 不会发送到前端。
Trackunit token 不写入日志。
client_secret、password 不写入代码。
前端只访问 FastAPI。
FastAPI 负责调用 Trackunit API 和 Ollama。
Qwen 本地运行，不产生云 API token 费用。
当前 read-only，不执行任何设备控制命令。
```

### H. 当前限制

```text
Trackunit endpoint 需要根据正式文档或账号权限配置。
真实 payload 字段 mapping 可能需要根据实际返回调整。
当前默认使用 JSON cache + SQLite，本地历史趋势已接入；PostgreSQL 通过数据库 adapter 预留。
自然语言 intent 先用规则识别，后续可升级为 LLM tool calling。
```

如果自然语言回答不准，先检查：

```text
1. query_engine.py 是否识别了正确 intent；
2. used_data 是否检索到了正确 records；
3. nl_query.py prompt 是否把数据清楚交给 Qwen。
```

## 数据库、自动同步、趋势和报表

### 1. 数据库

当前默认使用 SQLite：

```text
data/trackunit_ai.db
```

相关环境变量：

```text
SQLITE_DB_PATH=data/trackunit_ai.db
DATABASE_URL=sqlite:///data/trackunit_ai.db
```

当前核心表：

```text
machines
telemetry_snapshots
fault_codes
sync_logs
fleet_snapshot_history
```

PostgreSQL 目前是架构预留，后续可以把 `app/database.py` 替换为 PostgreSQL adapter。

### 2. 自动同步

自动同步默认关闭。开启方式是在 `.env` 中设置：

```text
TRACKUNIT_AUTO_SYNC_ENABLED=true
TRACKUNIT_SYNC_INTERVAL_SECONDS=300
TRACKUNIT_AUTO_SYNC_RUN_ON_START=false
```

状态接口：

```text
GET /sync/auto/status
```

### 3. 历史趋势分析

每次 fleet sync 成功后，会写入一条 `fleet_snapshot_history`，用于后续趋势分析。

接口：

```text
GET /analytics/trends?days=30
```

返回：

```text
points
latest
deltas
summary
```

### 4. PDF / Excel 报告导出

接口：

```text
GET /reports/fleet/excel
GET /reports/fleet/pdf
```

前端 Report Center 页面提供 Excel / PDF 下载按钮。

### 5. GitHub Actions

已增加 CI workflow：

```text
.github/workflows/ci.yml
```

CI 会运行：

```text
pytest
cd frontend && npm ci
cd frontend && npm run typecheck
cd frontend && npm run build
```

部署步骤目前是 placeholder。后续确定部署目标后，可以接 Azure App Service、Render、内部 Windows Server 或 Docker。

## 后端结构

当前后端已经拆成路由层、服务层、配置层和业务模块。

### 1. FastAPI 入口

```text
app/main.py
```

现在只负责：

```text
创建 FastAPI app
配置 CORS
注册 API routers
startup 时初始化 SQLite 和自动同步任务
shutdown 时停止自动同步任务
```

### 2. API 路由

```text
app/api/routes_health.py
app/api/routes_machines.py
app/api/routes_sync.py
app/api/routes_ai.py
app/api/routes_reports.py
app/api/routes_analytics.py
```

所有现有 API path 保持不变，例如：

```text
GET /health
GET /machines
GET /dashboard/summary
POST /ask
POST /sync/trackunit/fleet
GET /reports/fleet/pdf
```

### 3. 配置层

```text
app/core/config.py
```

集中读取非敏感环境变量，例如：

```text
DATA_SOURCE
TRACKUNIT_CACHE_TTL_SECONDS
TRACKUNIT_AUTO_SYNC_ENABLED
TRACKUNIT_SYNC_INTERVAL_SECONDS
SQLITE_DB_PATH
AI_PROVIDER
OLLAMA_BASE_URL
OLLAMA_MODEL
GEMINI_MODEL
GEMINI_BASE_URL
```

密钥、token、password、client secret 仍然只从 `.env` 读取，不会返回到前端，也不会写入 README 或日志。

### 4. 服务层

```text
app/services/machine_service.py
app/services/dashboard_service.py
```

服务层负责设备查询、遥测查询、故障查询、风险解释、Dashboard summary 等 helper 逻辑。路由层只负责 HTTP request / response。
