import { useEffect, useMemo, useState } from "react";
import {
  fetchCacheStatus,
  fetchFaults,
  fetchMachines,
  fetchSummary,
  fetchSyncLogs,
  fetchTelemetry,
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
import PartsDemandCard, { type PartsDemand } from "./components/PartsDemandCard";
import ServiceCaseCard, { type ServiceCase } from "./components/ServiceCaseCard";
import StatusBadge from "./components/StatusBadge";
import SyncLogsPanel from "./components/SyncLogsPanel";
import UtilizationChart from "./components/UtilizationChart";
import type {
  AiProvider,
  AiReportResponse,
  CacheStatus,
  DashboardSummary,
  FaultCode,
  Machine,
  SyncLog,
  TelemetrySnapshot,
  ViewKey
} from "./types";

export default function App() {
  const [activeView, setActiveView] = useState<ViewKey>("dashboard");
  const [language, setLanguage] = useState<"zh" | "en">("zh");
  const [aiProvider, setAiProvider] = useState<AiProvider>("ollama_local");
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [cacheStatus, setCacheStatus] = useState<CacheStatus | null>(null);
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

  const fleetMetrics = useMemo(() => buildFleetMetrics(machines, summary, cacheStatus), [cacheStatus, machines, summary]);
  const healthIssues = useMemo(() => buildHealthIssues(machines), [machines]);
  const serviceCases = useMemo(() => buildServiceCases(machines), [machines]);
  const partsDemand = useMemo(() => buildPartsDemand(serviceCases), [serviceCases]);

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
      const [summaryData, machineData, cacheData, logsData] = await Promise.all([
        fetchSummary(),
        fetchMachines(),
        fetchCacheStatus(),
        fetchSyncLogs()
      ]);
      setSummary(summaryData);
      setMachines(machineData);
      setCacheStatus(cacheData);
      setSyncLogs(logsData);
      setSelectedMachineId((current) => current || machineData[0]?.machine_id || null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load dashboard data.");
    } finally {
      setLoading(false);
    }
  }

  async function refreshCacheAndLogs() {
    const [cacheData, logsData, summaryData, machineData] = await Promise.all([
      fetchCacheStatus(),
      fetchSyncLogs(),
      fetchSummary(),
      fetchMachines()
    ]);
    setCacheStatus(cacheData);
    setSyncLogs(logsData);
    setSummary(summaryData);
    setMachines(machineData);
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
    if (activeView === "ai-assistant") return <AiAssistantPanel language={language} aiProvider={aiProvider} />;
    if (activeView === "sync-cache") return (
      <div className="view-stack">
        <CacheStatusPanel cacheStatus={cacheStatus} language={language} />
        <SyncLogsPanel logs={syncLogs} language={language} syncing={syncing} syncMessage={syncMessage} onSync={handleSyncFleet} />
      </div>
    );
    if (activeView === "reports") return <ReportsView language={language} loadingAction={loadingAction} report={fleetAiReport} onGenerate={handleGenerateFleetAiReport} />;
    if (activeView === "settings") return <SettingsView language={language} />;
    return (
      <DashboardView
        language={language}
        metrics={fleetMetrics}
        machines={machines}
        issues={healthIssues}
        cacheStatus={cacheStatus}
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
  onOpenView
}: {
  language: "zh" | "en";
  metrics: ReturnType<typeof buildFleetMetrics>;
  machines: Machine[];
  issues: HealthIssue[];
  cacheStatus: CacheStatus | null;
  onOpenView: (view: ViewKey) => void;
}) {
  return (
    <div className="view-stack">
      <section className="kpi-grid">
        {metrics.map((metric) => <KpiCard key={metric.label} {...metric} />)}
      </section>
      <div className="dashboard-grid">
        <section className="panel">
          <div className="panel-header">
            <div>
              <h2>{language === "zh" ? "Fleet Health Overview" : "Fleet Health Overview"}</h2>
              <span>{language === "zh" ? "由 cache 规则分析生成" : "Generated from cache rule analysis"}</span>
            </div>
            <button className="secondary-button" onClick={() => onOpenView("machine-health")}>{language === "zh" ? "查看健康中心" : "Open health center"}</button>
          </div>
          <div className="health-summary">
            {issues.slice(0, 4).map((issue) => (
              <HealthIssueCard key={`${issue.machine.machine_id}-${issue.issueType}`} {...issue} />
            ))}
            {issues.length === 0 && <div className="empty-panel">No critical issues from current cache.</div>}
          </div>
        </section>
        <CacheStatusPanel cacheStatus={cacheStatus} language={language} />
      </div>
      <div className="chart-grid">
        <UtilizationChart machines={machines.slice(0, 40)} language={language} />
        <FaultChart machines={machines.slice(0, 40)} language={language} />
      </div>
      <section className="panel">
        <div className="panel-header">
          <h2>{language === "zh" ? "Recent Alerts / Service Priority" : "Recent Alerts / Service Priority"}</h2>
          <span>{language === "zh" ? "基于离线、故障、低油量、低利用率规则" : "Based on offline, fault, fuel, and utilization rules"}</span>
        </div>
        <div className="issue-list">
          {issues.slice(0, 8).map((issue) => <HealthIssueCard key={`${issue.machine.machine_id}-${issue.issueType}-recent`} {...issue} />)}
        </div>
      </section>
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
        {issues.map((issue) => <HealthIssueCard key={`${issue.machine.machine_id}-${issue.issueType}`} {...issue} />)}
        {issues.length === 0 && <div className="empty-panel">No health issues detected from current cache.</div>}
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
            <h2>{language === "zh" ? "Service Cases" : "Service Cases"}</h2>
            <span>{language === "zh" ? "Telematics signal → service action" : "Telematics signal -> service action"}</span>
          </div>
        </div>
        <div className="issue-list">
          {cases.map((item) => <ServiceCaseCard key={item.id} item={item} />)}
          {cases.length === 0 && <div className="empty-panel">No service cases from current cache.</div>}
        </div>
      </section>
      <section className="panel">
        <div className="panel-header">
          <div>
            <h2>{language === "zh" ? "Parts Demand" : "Parts Demand"}</h2>
            <span>{language === "zh" ? "当前缺少真实故障码到备件映射表" : "Requires fault-code-to-parts mapping table"}</span>
          </div>
        </div>
        <div className="placeholder-callout">
          Parts recommendation requires fault-code-to-parts mapping table. No real XCMG part numbers are generated from current cache.
        </div>
        <div className="issue-list">
          {parts.map((item) => <PartsDemandCard key={item.id} item={item} />)}
        </div>
      </section>
    </div>
  );
}

function ReportsView({ language, loadingAction, report, onGenerate }: { language: "zh" | "en"; loadingAction: string | null; report: AiReportResponse | null; onGenerate: () => void }) {
  return (
    <section className="panel">
      <div className="panel-header">
        <div>
          <h2>{language === "zh" ? "报告中心" : "Report Center"}</h2>
          <span>{language === "zh" ? "当前支持车队 AI 报告" : "Fleet AI report is available in this phase"}</span>
        </div>
        <button disabled={Boolean(loadingAction)} onClick={onGenerate}>
          {loadingAction === "fleet-ai-report" ? (language === "zh" ? "生成中..." : "Generating...") : (language === "zh" ? "生成车队 AI 报告" : "Generate Fleet AI Report")}
        </button>
      </div>
      {report && (
        <div className="output-box">
          <p><strong>Provider:</strong> {report.provider}</p>
          <p><strong>{language === "zh" ? "模型" : "Model"}:</strong> {report.model}</p>
          {report.error ? <div className="inline-error">{report.error}</div> : <pre>{report.ai_report_markdown}</pre>}
        </div>
      )}
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
        <div><strong>TRACKUNIT_AUTO_SYNC_ENABLED</strong><span>false by default</span></div>
        <div><strong>Security</strong><span>No Trackunit key, token, or secret is exposed in frontend.</span></div>
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

function buildFleetMetrics(machines: Machine[], summary: DashboardSummary | null, cacheStatus: CacheStatus | null) {
  const activeFaults = machines.reduce((count, machine) => count + (machine.fault_count ?? 0), 0);
  const lowFuel = machines.filter((machine) => isLowFuel(machine)).length;
  return [
    { label: "Total Machines", value: summary?.total_machines ?? machines.length, helper: "trackunit_cache", tone: "info" as const },
    { label: "Online Machines", value: summary?.online_machines ?? "-", helper: "from last communication", tone: "good" as const },
    { label: "Offline Machines", value: summary?.offline_machines ?? "-", helper: "over 72 hours", tone: (summary?.offline_machines ?? 0) > 0 ? "danger" as const : "good" as const },
    { label: "Active Faults", value: activeFaults, helper: "fault records in cache", tone: activeFaults > 0 ? "danger" as const : "good" as const },
    { label: "Low Fuel Machines", value: lowFuel, helper: "fuel <= 10%", tone: lowFuel > 0 ? "warning" as const : "good" as const },
    { label: "Low Utilization", value: summary?.low_utilization_machines ?? "-", helper: "rule based", tone: "warning" as const },
    { label: "Repeated Faults", value: summary?.repeated_fault_machines ?? "-", helper: "fault count >= 2", tone: (summary?.repeated_fault_machines ?? 0) > 0 ? "danger" as const : "good" as const },
    { label: "Cache Age", value: formatAge(cacheStatus?.age_seconds ?? null), helper: cacheStatus?.fresh ? "fresh" : "stale", tone: cacheStatus?.fresh ? "good" as const : "warning" as const },
    { label: "Data Source", value: cacheStatus?.data_source ?? "unknown", helper: "cache-first", tone: "info" as const }
  ];
}

function buildHealthIssues(machines: Machine[]): HealthIssue[] {
  const issues: HealthIssue[] = [];
  for (const machine of machines) {
    if (isOffline(machine)) {
      issues.push({
        machine,
        issueType: "Offline machine",
        severity: "Critical",
        evidence: `last_seen_at=${machine.last_seen_at}`,
        action: "Check telematics power, terminal connectivity, and site status."
      });
    }
    if ((machine.fault_count ?? 0) >= 2) {
      issues.push({
        machine,
        issueType: "Repeated faults",
        severity: "Critical",
        evidence: `fault_count=${machine.fault_count}`,
        action: "Create service follow-up and review active fault history."
      });
    } else if ((machine.fault_count ?? 0) > 0) {
      issues.push({
        machine,
        issueType: "Fault reported",
        severity: "Warning",
        evidence: `fault_count=${machine.fault_count}`,
        action: "Review fault severity and contact service if open."
      });
    }
    if (isLowFuel(machine)) {
      issues.push({
        machine,
        issueType: "Low fuel",
        severity: "Warning",
        evidence: `fuel_remaining_percent=${machine.fuel_remaining_percent}`,
        action: "Confirm refuel plan with customer/site team."
      });
    }
    if (machine.risk_level === "Low Utilization") {
      issues.push({
        machine,
        issueType: "Low utilization",
        severity: "Info",
        evidence: `operating_hours=${machine.operating_hours ?? "missing"}`,
        action: "Review rental status, customer usage, and deployment plan.",
        missingFields: machine.operating_hours === null || machine.operating_hours === undefined ? ["operating_hours"] : []
      });
    }
  }
  return issues.slice(0, 80);
}

function buildServiceCases(machines: Machine[]): ServiceCase[] {
  return buildHealthIssues(machines).slice(0, 24).map((issue, index) => ({
    id: `${issue.machine.machine_id}-${issue.issueType}-${index}`,
    machineLabel: `${issue.machine.serial_number || issue.machine.machine_id} / ${issue.machine.model}`,
    reason: issue.issueType,
    priority: issue.severity === "Critical" ? "High" : issue.severity === "Warning" ? "Medium" : "Low",
    action: issue.action,
    status: "Open",
    relatedParts: issue.issueType.includes("Fault") || issue.issueType.includes("fault")
      ? ["Mapping required"]
      : ["No parts inferred from current cache"]
  }));
}

function buildPartsDemand(cases: ServiceCase[]): PartsDemand[] {
  return cases
    .filter((item) => item.relatedParts.includes("Mapping required"))
    .slice(0, 12)
    .map((item) => ({
      id: `parts-${item.id}`,
      partNumber: "Mapping required",
      partName: "Fault-code-to-parts mapping required",
      machineLabel: item.machineLabel,
      quantity: "TBD",
      priority: item.priority === "High" ? "High" : "Medium",
      reason: item.reason,
      source: "Missing data"
    }));
}

function isLowFuel(machine: Machine): boolean {
  return machine.fuel_remaining_percent !== null && machine.fuel_remaining_percent !== undefined && machine.fuel_remaining_percent <= 10;
}

function isOffline(machine: Machine): boolean {
  const timestamp = Date.parse(machine.last_seen_at);
  if (Number.isNaN(timestamp)) return false;
  return Date.now() - timestamp > 72 * 60 * 60 * 1000;
}

function formatAge(value: number | null): string {
  if (value === null) return "Not available";
  if (value < 60) return `${Math.round(value)}s`;
  if (value < 3600) return `${Math.round(value / 60)}m`;
  return `${Math.round(value / 3600)}h`;
}
