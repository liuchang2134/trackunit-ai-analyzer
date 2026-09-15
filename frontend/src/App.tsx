import { useEffect, useMemo, useState } from "react";
import {
  fetchCacheStatus,
  fetchAutoSyncStatus,
  fetchDatabaseStatus,
  fetchFleetTrends,
  fetchFaults,
  fetchMachines,
  fetchSummary,
  fetchSyncLogs,
  fetchTelemetry,
  fleetExcelReportUrl,
  fleetPdfReportUrl,
  generateFleetAiReport,
  generateMachineAiReport,
  generateMachinePrompt,
  syncTrackunitFleet
} from "./api";
import AiAssistantPanel from "./components/AiAssistantPanel";
import CacheStatusPanel from "./components/CacheStatusPanel";
import FaultChart from "./components/FaultChart";
import HealthIssueCard from "./components/HealthIssueCard";
import KpiCard from "./components/KpiCard";
import Layout from "./components/Layout";
import MachineDetail from "./components/MachineDetail";
import MachineTable from "./components/MachineTable";
import MarkdownRenderer from "./components/MarkdownRenderer";
import PartsDemandCard, { type PartsDemand } from "./components/PartsDemandCard";
import ServiceCaseCard, { type ServiceCase } from "./components/ServiceCaseCard";
import StatusBadge from "./components/StatusBadge";
import SyncLogsPanel from "./components/SyncLogsPanel";
import TrendSummaryPanel from "./components/TrendSummaryPanel";
import UtilizationChart from "./components/UtilizationChart";
import { isLowFuel, isLowUtilization, isOffline, recommendedAction, riskLevel, riskReasons, riskScore, riskTone } from "./utils/display";
import type {
  AiProvider,
  AiReportResponse,
  AutoSyncStatus,
  CacheStatus,
  DashboardSummary,
  DatabaseStatus,
  FaultCode,
  FleetTrends,
  Machine,
  SyncLog,
  TelemetrySnapshot,
  ViewKey
} from "./types";

export default function App() {
  const [activeView, setActiveView] = useState<ViewKey>("dashboard");
  const [language, setLanguage] = useState<"zh" | "en">("zh");
  const [aiProvider, setAiProvider] = useState<AiProvider>("deepseek");
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [cacheStatus, setCacheStatus] = useState<CacheStatus | null>(null);
  const [databaseStatus, setDatabaseStatus] = useState<DatabaseStatus | null>(null);
  const [autoSyncStatus, setAutoSyncStatus] = useState<AutoSyncStatus | null>(null);
  const [fleetTrends, setFleetTrends] = useState<FleetTrends | null>(null);
  const [syncLogs, setSyncLogs] = useState<SyncLog[]>([]);
  const [machines, setMachines] = useState<Machine[]>([]);
  const [selectedMachineId, setSelectedMachineId] = useState<string | null>(null);
  const [telemetry, setTelemetry] = useState<TelemetrySnapshot[]>([]);
  const [faults, setFaults] = useState<FaultCode[]>([]);
  const [promptText, setPromptText] = useState("");
  const [aiReport, setAiReport] = useState<AiReportResponse | null>(null);
  const [fleetAiReport, setFleetAiReport] = useState<AiReportResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const [syncMessage, setSyncMessage] = useState("");
  const [loadingAction, setLoadingAction] = useState<string | null>(null);
  const [error, setError] = useState("");

  const selectedMachine = useMemo(
    () => machines.find((machine) => machine.machine_id === selectedMachineId) || null,
    [machines, selectedMachineId]
  );

  const fleetMetrics = useMemo(() => buildFleetMetrics(machines, summary, cacheStatus, language), [cacheStatus, language, machines, summary]);
  const healthIssues = useMemo(() => buildHealthIssues(machines, language), [language, machines]);
  const serviceCases = useMemo(() => buildServiceCases(machines, language), [language, machines]);
  const partsDemand = useMemo(() => buildPartsDemand(serviceCases, language), [language, serviceCases]);

  useEffect(() => {
    void loadDashboardData();
  }, []);

  useEffect(() => {
    async function loadMachineDetail() {
      if (!selectedMachineId) return;
      try {
        const [telemetryData, faultData] = await Promise.all([fetchTelemetry(selectedMachineId), fetchFaults(selectedMachineId)]);
        setTelemetry(telemetryData);
        setFaults(faultData);
        setPromptText("");
        setAiReport(null);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to load machine detail.");
      }
    }
    void loadMachineDetail();
  }, [selectedMachineId]);

  async function loadDashboardData() {
    try {
      setLoading(true);
      const [summaryData, machineData, cacheData, logsData, trendsData, dbData, autoSyncData] = await Promise.all([
        fetchSummary(),
        fetchMachines(),
        fetchCacheStatus(),
        fetchSyncLogs(),
        fetchFleetTrends(),
        fetchDatabaseStatus(),
        fetchAutoSyncStatus()
      ]);
      setSummary(summaryData);
      setMachines(machineData);
      setCacheStatus(cacheData);
      setSyncLogs(logsData);
      setFleetTrends(trendsData);
      setDatabaseStatus(dbData);
      setAutoSyncStatus(autoSyncData);
      setSelectedMachineId((current) => current || machineData[0]?.machine_id || null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load dashboard data.");
    } finally {
      setLoading(false);
    }
  }

  async function refreshCacheAndLogs() {
    const [cacheData, logsData, summaryData, machineData, trendsData, dbData, autoSyncData] = await Promise.all([
      fetchCacheStatus(),
      fetchSyncLogs(),
      fetchSummary(),
      fetchMachines(),
      fetchFleetTrends(),
      fetchDatabaseStatus(),
      fetchAutoSyncStatus()
    ]);
    setCacheStatus(cacheData);
    setSyncLogs(logsData);
    setSummary(summaryData);
    setMachines(machineData);
    setFleetTrends(trendsData);
    setDatabaseStatus(dbData);
    setAutoSyncStatus(autoSyncData);
  }

  async function handleSyncFleet() {
    setSyncing(true);
    setSyncMessage("");
    try {
      const response = await syncTrackunitFleet();
      if (response.status === "success") {
        setSyncMessage(`${language === "zh" ? "同步成功" : "Sync succeeded"}: ${response.records} records`);
      } else {
        const message = response.error?.includes("429")
          ? (language === "zh" ? "Trackunit API 限流 429，请等待后再同步。" : "Trackunit API rate limit 429. Please wait and retry.")
          : response.error || "Sync failed";
        setSyncMessage(message);
      }
      await refreshCacheAndLogs();
    } catch (err) {
      const message = err instanceof Error ? err.message : "Sync failed";
      setSyncMessage(message.includes("429") ? "Trackunit API 限流 429，请等待后再同步。" : message);
    } finally {
      setSyncing(false);
    }
  }

  async function handleGeneratePrompt() {
    if (!selectedMachineId) return;
    setLoadingAction("prompt");
    setAiReport(null);
    try {
      setPromptText((await generateMachinePrompt(selectedMachineId)).prompt);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to generate prompt.");
    } finally {
      setLoadingAction(null);
    }
  }

  async function handleGenerateAiReport() {
    if (!selectedMachineId) return;
    setLoadingAction("ai-report");
    setPromptText("");
    try {
      setAiReport(await generateMachineAiReport(selectedMachineId, aiProvider));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to generate AI report.");
    } finally {
      setLoadingAction(null);
    }
  }

  async function handleGenerateFleetAiReport() {
    setLoadingAction("fleet-ai-report");
    setFleetAiReport(null);
    try {
      setFleetAiReport(await generateFleetAiReport(aiProvider));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to generate fleet AI report.");
    } finally {
      setLoadingAction(null);
    }
  }

  return (
    <Layout
      activeView={activeView}
      language={language}
      aiProvider={aiProvider}
      cacheStatus={cacheStatus}
      onChangeView={setActiveView}
      onToggleLanguage={() => setLanguage(language === "zh" ? "en" : "zh")}
      onChangeProvider={setAiProvider}
    >
      {error && <div className="error-banner">{error}</div>}
      {loading ? (
        <section className="loading-panel">{language === "zh" ? "正在加载车联网数据..." : "Loading telematics data..."}</section>
      ) : (
        renderView()
      )}
    </Layout>
  );

  function renderView() {
    if (activeView === "fleet") return (
      <div className="view-stack">
        <MachineTable machines={machines} selectedMachineId={selectedMachineId} language={language} onSelectMachine={(machine) => setSelectedMachineId(machine.machine_id)} />
        <MachineDetail
          machine={selectedMachine}
          telemetry={telemetry}
          faults={faults}
          promptText={promptText}
          aiReport={aiReport}
          loadingAction={loadingAction}
          language={language}
          onGeneratePrompt={handleGeneratePrompt}
          onGenerateAiReport={handleGenerateAiReport}
        />
      </div>
    );
    if (activeView === "machine-health") return <MachineHealthView issues={healthIssues} language={language} />;
    if (activeView === "service-parts") return <ServicePartsView cases={serviceCases} parts={partsDemand} language={language} />;
    if (activeView === "ai-assistant") return <AiAssistantPanel language={language} aiProvider={aiProvider} machines={machines} />;
    if (activeView === "sync-cache") return (
      <div className="view-stack">
        <CacheStatusPanel cacheStatus={cacheStatus} language={language} />
        <SystemStoragePanel language={language} databaseStatus={databaseStatus} autoSyncStatus={autoSyncStatus} />
        <SyncLogsPanel logs={syncLogs} language={language} syncing={syncing} syncMessage={syncMessage} onSync={handleSyncFleet} />
      </div>
    );
    if (activeView === "reports") return <ReportsView language={language} loadingAction={loadingAction} report={fleetAiReport} trends={fleetTrends} onGenerate={handleGenerateFleetAiReport} />;
    if (activeView === "settings") return <SettingsView language={language} />;
    return (
      <DashboardView
        language={language}
        metrics={fleetMetrics}
        machines={machines}
        issues={healthIssues}
        cacheStatus={cacheStatus}
        trends={fleetTrends}
        onOpenView={setActiveView}
      />
    );
  }
}

function DashboardView({
  language,
  metrics,
  machines,
  issues,
  cacheStatus,
  trends,
  onOpenView
}: {
  language: "zh" | "en";
  metrics: ReturnType<typeof buildFleetMetrics>;
  machines: Machine[];
  issues: HealthIssue[];
  cacheStatus: CacheStatus | null;
  trends: FleetTrends | null;
  onOpenView: (view: ViewKey) => void;
}) {
  const topRiskMachines = [...machines]
    .sort((a, b) => riskScore(b) - riskScore(a))
    .filter((machine) => riskScore(machine) > 0)
    .slice(0, 10);

  return (
    <div className="view-stack">
      <section className="kpi-grid">
        {metrics.map((metric) => <KpiCard key={metric.label} {...metric} />)}
      </section>
      <div className="dashboard-grid">
        <section className="panel">
          <div className="panel-header">
            <div>
              <h2>{language === "zh" ? "高风险设备 Top 10" : "Top 10 High-Risk Machines"}</h2>
              <span>{language === "zh" ? "按风险评分排序，优先处理前几台设备" : "Sorted by risk score for operational priority"}</span>
            </div>
            <button className="secondary-button" onClick={() => onOpenView("machine-health")}>{language === "zh" ? "查看健康中心" : "Open health center"}</button>
          </div>
          <TopRiskTable machines={topRiskMachines} language={language} />
        </section>
        <CacheStatusPanel cacheStatus={cacheStatus} language={language} />
      </div>
      <div className="chart-grid">
        <UtilizationChart machines={machines.slice(0, 40)} language={language} />
        <FaultChart machines={machines.slice(0, 40)} language={language} />
      </div>
      <TrendSummaryPanel trends={trends} language={language} />
      <section className="panel">
        <div className="panel-header">
          <h2>{language === "zh" ? "近期预警 / 服务优先级" : "Recent Alerts / Service Priority"}</h2>
          <span>{language === "zh" ? "基于离线、故障、低油量、低利用率规则" : "Based on offline, fault, fuel, and utilization rules"}</span>
        </div>
        <div className="issue-list">
          {issues.slice(0, 8).map((issue) => <HealthIssueCard key={`${issue.machine.machine_id}-${issue.issueType}-recent`} {...issue} language={language} />)}
          {issues.length === 0 && <div className="empty-panel">{language === "zh" ? "当前缓存未发现健康风险。" : "No health issues detected from current cache."}</div>}
        </div>
      </section>
    </div>
  );
}

function TopRiskTable({ machines, language }: { machines: Machine[]; language: "zh" | "en" }) {
  if (machines.length === 0) {
    return <div className="empty-panel">{language === "zh" ? "当前没有触发风险规则的设备。" : "No machines triggered risk rules."}</div>;
  }
  return (
    <div className="table-wrap">
      <table className="data-table risk-table">
        <thead>
          <tr>
            <th>{language === "zh" ? "排名" : "Rank"}</th>
            <th>{language === "zh" ? "设备" : "Machine"}</th>
            <th>{language === "zh" ? "型号" : "Model"}</th>
            <th>{language === "zh" ? "风险" : "Risk"}</th>
            <th>{language === "zh" ? "原因" : "Reason"}</th>
            <th>{language === "zh" ? "建议动作" : "Action"}</th>
          </tr>
        </thead>
        <tbody>
          {machines.map((machine, index) => (
            <tr key={machine.machine_id}>
              <td>{index + 1}</td>
              <td>{machine.serial_number || machine.machine_id}</td>
              <td>{machine.model}</td>
              <td><StatusBadge label={`${riskLevel(machine, language)} ${riskScore(machine)}`} tone={riskTone(machine)} /></td>
              <td>{riskReasons(machine, language).join("; ")}</td>
              <td>{recommendedAction(machine, language)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function MachineHealthView({ issues, language }: { issues: HealthIssue[]; language: "zh" | "en" }) {
  return (
    <section className="panel">
      <div className="panel-header">
        <div>
          <h2>{language === "zh" ? "设备健康中心" : "Machine Health Center"}</h2>
          <span>{language === "zh" ? "故障、离线、低利用率、低油量设备" : "Fault, offline, low utilization, and low fuel machines"}</span>
        </div>
      </div>
      <div className="issue-list">
        {issues.map((issue) => <HealthIssueCard key={`${issue.machine.machine_id}-${issue.issueType}`} {...issue} language={language} />)}
        {issues.length === 0 && <div className="empty-panel">{language === "zh" ? "当前缓存未发现健康风险。" : "No health issues detected from current cache."}</div>}
      </div>
    </section>
  );
}

function ServicePartsView({ cases, parts, language }: { cases: ServiceCase[]; parts: PartsDemand[]; language: "zh" | "en" }) {
  return (
    <div className="view-stack">
      <section className="panel">
        <div className="panel-header">
          <div>
            <h2>{language === "zh" ? "服务跟进建议" : "Service Cases"}</h2>
            <span>{language === "zh" ? "车联网信号转化为服务动作" : "Telematics signal -> service action"}</span>
          </div>
        </div>
        <div className="issue-list">
          {cases.map((item) => <ServiceCaseCard key={item.id} item={item} language={language} />)}
          {cases.length === 0 && <div className="empty-panel">{language === "zh" ? "当前缓存没有服务跟进建议。" : "No service cases from current cache."}</div>}
        </div>
      </section>
      <section className="panel">
        <div className="panel-header">
          <div>
            <h2>{language === "zh" ? "备件需求线索" : "Parts Demand"}</h2>
            <span>{language === "zh" ? "当前缺少真实故障码到备件映射表" : "Requires fault-code-to-parts mapping table"}</span>
          </div>
        </div>
        <div className="placeholder-callout">
          {language === "zh"
            ? "备件推荐需要故障码到备件号映射表。当前不会根据缓存数据生成真实 XCMG 备件号。"
            : "Parts recommendation requires fault-code-to-parts mapping table. No real XCMG part numbers are generated from current cache."}
        </div>
        <div className="issue-list">
          {parts.map((item) => <PartsDemandCard key={item.id} item={item} language={language} />)}
        </div>
      </section>
    </div>
  );
}

function ReportsView({ language, loadingAction, report, trends, onGenerate }: { language: "zh" | "en"; loadingAction: string | null; report: AiReportResponse | null; trends: FleetTrends | null; onGenerate: () => void }) {
  const reportCards = [
    {
      title: language === "zh" ? "运营日报" : "Daily Operations Report",
      desc: language === "zh" ? "用于每日运营例会，关注离线、高风险、低油量和故障设备。" : "For daily operations meetings, focusing on offline, high-risk, low-fuel, and fault machines.",
    },
    {
      title: language === "zh" ? "周报 / 月报" : "Weekly / Monthly Report",
      desc: language === "zh" ? "用于管理层汇报，包含趋势、风险和服务优先级。" : "For management reporting with trends, risks, and service priorities.",
    },
    {
      title: language === "zh" ? "单台设备健康报告" : "Single Machine Health Report",
      desc: language === "zh" ? "请在设备列表选择设备后生成单车 AI 健康总结。" : "Select a machine in Fleet to generate a machine-level AI health report.",
    },
  ];
  return (
    <div className="view-stack">
      <section className="panel">
        <div className="panel-header">
          <div>
            <h2>{language === "zh" ? "报告中心" : "Report Center"}</h2>
            <span>{language === "zh" ? "运营日报、周报/月报、单车健康报告" : "Daily, weekly/monthly, and machine health reports"}</span>
          </div>
        </div>
        <div className="report-card-grid">
          {reportCards.map((item, index) => (
            <article className="report-card" key={item.title}>
              <h3>{item.title}</h3>
              <p>{item.desc}</p>
              <dl>
                <dt>{language === "zh" ? "数据源" : "Data source"}</dt>
                <dd>trackunit_cache / Trackunit API</dd>
                <dt>{language === "zh" ? "缺失字段" : "Missing fields"}</dt>
                <dd>{language === "zh" ? "生成后显示在 AI 分析信息中" : "Shown in AI analysis info after generation"}</dd>
              </dl>
              <div className="button-row">
                {index < 2 && (
                  <button disabled={Boolean(loadingAction)} onClick={onGenerate}>
                    {loadingAction === "fleet-ai-report" ? (language === "zh" ? "生成中..." : "Generating...") : (language === "zh" ? "生成 AI 报告" : "Generate AI Report")}
                  </button>
                )}
                <a className="secondary-button link-button" href={fleetExcelReportUrl()} target="_blank" rel="noreferrer">Excel</a>
                <a className="secondary-button link-button" href={fleetPdfReportUrl()} target="_blank" rel="noreferrer">PDF</a>
              </div>
            </article>
          ))}
        </div>
        {report && (
          <div className="output-box">
            <p><strong>Provider:</strong> {report.provider}</p>
            <p><strong>{language === "zh" ? "模型" : "Model"}:</strong> {report.model}</p>
            {report.error ? <div className="inline-error">{report.error}</div> : <MarkdownRenderer content={report.ai_report_markdown} />}
          </div>
        )}
      </section>
      <TrendSummaryPanel trends={trends} language={language} />
    </div>
  );
}

function SystemStoragePanel({ language, databaseStatus, autoSyncStatus }: { language: "zh" | "en"; databaseStatus: DatabaseStatus | null; autoSyncStatus: AutoSyncStatus | null }) {
  return (
    <section className="panel">
      <div className="panel-header">
        <div>
          <h2>{language === "zh" ? "数据库 / 自动同步" : "Database / Auto Sync"}</h2>
          <span>{language === "zh" ? "SQLite 本地库，PostgreSQL 架构预留" : "Local SQLite with PostgreSQL-ready adapter"}</span>
        </div>
        <StatusBadge
          label={autoSyncStatus?.enabled ? (language === "zh" ? "自动同步开" : "auto sync on") : (language === "zh" ? "自动同步关" : "auto sync off")}
          tone={autoSyncStatus?.enabled ? "good" : "neutral"}
        />
      </div>
      <div className="settings-list">
        <div><strong>{language === "zh" ? "数据库" : "Database"}</strong><span>{databaseStatus?.provider ?? "-"} · {databaseStatus?.exists ? (language === "zh" ? "已就绪" : "ready") : (language === "zh" ? "未创建" : "not created")}</span></div>
        <div><strong>{language === "zh" ? "设备表记录" : "Machines"}</strong><span>{databaseStatus?.tables?.machines ?? 0}</span></div>
        <div><strong>{language === "zh" ? "遥测记录" : "Telemetry"}</strong><span>{databaseStatus?.tables?.telemetry_snapshots ?? 0}</span></div>
        <div><strong>{language === "zh" ? "车队历史快照" : "Fleet History"}</strong><span>{databaseStatus?.tables?.fleet_snapshot_history ?? 0}</span></div>
        <div><strong>{language === "zh" ? "同步间隔" : "Sync Interval"}</strong><span>{autoSyncStatus?.interval_seconds ?? "-"}s</span></div>
        <div><strong>{language === "zh" ? "下次运行" : "Next Run"}</strong><span>{autoSyncStatus?.next_run_at ?? (language === "zh" ? "未启用" : "disabled")}</span></div>
      </div>
    </section>
  );
}

function SettingsView({ language }: { language: "zh" | "en" }) {
  return (
    <section className="panel">
      <div className="panel-header">
        <h2>{language === "zh" ? "系统设置" : "Settings"}</h2>
      </div>
      <div className="settings-list">
        <div><strong>TRACKUNIT_CACHE_FIRST</strong><span>true</span></div>
        <div><strong>TRACKUNIT_REFRESH_STALE_CACHE_ON_ASK</strong><span>false</span></div>
        <div><strong>TRACKUNIT_AUTO_SYNC_ENABLED</strong><span>{language === "zh" ? "默认关闭" : "false by default"}</span></div>
        <div><strong>{language === "zh" ? "安全" : "Security"}</strong><span>{language === "zh" ? "前端不暴露 Trackunit key、token 或 secret。" : "No Trackunit key, token, or secret is exposed in frontend."}</span></div>
      </div>
    </section>
  );
}

type HealthIssue = {
  machine: Machine;
  issueType: string;
  severity: "Critical" | "Warning" | "Info";
  evidence: string;
  action: string;
  missingFields?: string[];
};

function buildFleetMetrics(machines: Machine[], summary: DashboardSummary | null, cacheStatus: CacheStatus | null, language: "zh" | "en") {
  const activeFaults = machines.reduce((count, machine) => count + (machine.fault_count ?? 0), 0);
  const lowFuel = machines.filter((machine) => isLowFuel(machine)).length;
  const highRisk = machines.filter((machine) => riskScore(machine) >= 70).length || summary?.high_risk_machines || 0;
  const labels = language === "zh"
    ? {
        total: "设备总数",
        online: "在线设备",
        offline: "离线设备",
        highRisk: "高风险设备",
        lowFuel: "低油量设备",
        lowUtil: "低利用率设备",
        faults: "故障设备",
        source: "Trackunit 缓存",
        lastComm: "基于最后通信时间",
        over72: "超过 72 小时",
        riskScore: "按风险评分",
        fuel: "油量 <= 10%",
        rule: "规则识别",
        faultRecords: "故障记录",
        good: "正常",
        warning: "关注",
        danger: "风险",
        info: "信息",
      }
    : {
        total: "Total Machines",
        online: "Online Machines",
        offline: "Offline Machines",
        highRisk: "High Risk Machines",
        lowFuel: "Low Fuel Machines",
        lowUtil: "Low Utilization",
        faults: "Fault Machines",
        source: "Trackunit cache",
        lastComm: "from last communication",
        over72: "over 72 hours",
        riskScore: "by risk score",
        fuel: "fuel <= 10%",
        rule: "rule based",
        faultRecords: "fault records",
        good: "good",
        warning: "warning",
        danger: "risk",
        info: "info",
      };
  return [
    { label: labels.total, value: summary?.total_machines ?? machines.length, helper: labels.source, tone: "info" as const, toneLabel: labels.info },
    { label: labels.online, value: summary?.online_machines ?? "-", helper: labels.lastComm, tone: "good" as const, toneLabel: labels.good },
    { label: labels.offline, value: summary?.offline_machines ?? "-", helper: labels.over72, tone: (summary?.offline_machines ?? 0) > 0 ? "danger" as const : "good" as const, toneLabel: (summary?.offline_machines ?? 0) > 0 ? labels.danger : labels.good },
    { label: labels.highRisk, value: highRisk, helper: labels.riskScore, tone: highRisk > 0 ? "danger" as const : "good" as const, toneLabel: highRisk > 0 ? labels.danger : labels.good },
    { label: labels.lowFuel, value: lowFuel, helper: labels.fuel, tone: lowFuel > 0 ? "warning" as const : "good" as const, toneLabel: lowFuel > 0 ? labels.warning : labels.good },
    { label: labels.lowUtil, value: summary?.low_utilization_machines ?? "-", helper: labels.rule, tone: "warning" as const, toneLabel: labels.warning },
    { label: labels.faults, value: activeFaults, helper: labels.faultRecords, tone: activeFaults > 0 ? "danger" as const : "good" as const, toneLabel: activeFaults > 0 ? labels.danger : labels.good },
  ];
}

function buildHealthIssues(machines: Machine[], language: "zh" | "en"): HealthIssue[] {
  const issues: HealthIssue[] = [];
  for (const machine of machines) {
    if (isOffline(machine)) {
      issues.push({
        machine,
        issueType: language === "zh" ? "设备离线" : "Offline machine",
        severity: "Critical",
        evidence: `${language === "zh" ? "最后通信" : "last_seen_at"}=${machine.last_seen_at}`,
        action: recommendedAction(machine, language)
      });
    }
    if ((machine.fault_count ?? 0) >= 2) {
      issues.push({
        machine,
        issueType: language === "zh" ? "重复故障" : "Repeated faults",
        severity: "Critical",
        evidence: `${language === "zh" ? "故障数量" : "fault_count"}=${machine.fault_count}`,
        action: recommendedAction(machine, language)
      });
    } else if ((machine.fault_count ?? 0) > 0) {
      issues.push({
        machine,
        issueType: language === "zh" ? "存在故障" : "Fault reported",
        severity: "Warning",
        evidence: `${language === "zh" ? "故障数量" : "fault_count"}=${machine.fault_count}`,
        action: recommendedAction(machine, language)
      });
    }
    if (isLowFuel(machine)) {
      issues.push({
        machine,
        issueType: language === "zh" ? "低油量" : "Low fuel",
        severity: "Warning",
        evidence: `${language === "zh" ? "剩余油量" : "fuel_remaining_percent"}=${machine.fuel_remaining_percent}`,
        action: recommendedAction(machine, language)
      });
    }
    if (machine.risk_level === "Low Utilization") {
      issues.push({
        machine,
        issueType: language === "zh" ? "低利用率" : "Low utilization",
        severity: "Info",
        evidence: `${language === "zh" ? "运行小时" : "operating_hours"}=${machine.operating_hours ?? (language === "zh" ? "缺失" : "missing")}`,
        action: recommendedAction(machine, language),
        missingFields: machine.operating_hours === null || machine.operating_hours === undefined ? [language === "zh" ? "运行小时" : "operating_hours"] : []
      });
    }
  }
  return issues.slice(0, 80);
}

function buildServiceCases(machines: Machine[], language: "zh" | "en"): ServiceCase[] {
  return buildHealthIssues(machines, language).slice(0, 24).map((issue, index) => ({
    id: `${issue.machine.machine_id}-${issue.issueType}-${index}`,
    machineLabel: `${issue.machine.serial_number || issue.machine.machine_id} / ${issue.machine.model}`,
    reason: issue.issueType,
    priority: issue.severity === "Critical" ? "High" : issue.severity === "Warning" ? "Medium" : "Low",
    action: issue.action,
    status: "Open",
    relatedParts: issue.issueType.includes("Fault") || issue.issueType.includes("fault")
      ? [language === "zh" ? "需要映射表" : "Mapping required"]
      : [language === "zh" ? "当前缓存无法推断备件" : "No parts inferred from current cache"]
  }));
}

function buildPartsDemand(cases: ServiceCase[], language: "zh" | "en"): PartsDemand[] {
  return cases
    .filter((item) => item.relatedParts.includes("Mapping required") || item.relatedParts.includes("需要映射表"))
    .slice(0, 12)
    .map((item) => ({
      id: `parts-${item.id}`,
      partNumber: language === "zh" ? "需要映射表" : "Mapping required",
      partName: language === "zh" ? "需要故障码到备件号映射表" : "Fault-code-to-parts mapping required",
      machineLabel: item.machineLabel,
      quantity: language === "zh" ? "待确认" : "TBD",
      priority: item.priority === "High" ? "High" : "Medium",
      reason: item.reason,
      source: "Missing data"
    }));
}
