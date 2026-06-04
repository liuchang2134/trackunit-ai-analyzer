import type { AiReportResponse, FaultCode, Machine, TelemetrySnapshot } from "../types";
import MarkdownRenderer from "./MarkdownRenderer";
import StatusBadge from "./StatusBadge";
import { formatMissing, recommendedAction, riskLevel, riskReasons, riskScore, riskTone } from "../utils/display";

type Props = {
  machine: Machine | null;
  telemetry: TelemetrySnapshot[];
  faults: FaultCode[];
  promptText: string;
  aiReport: AiReportResponse | null;
  loadingAction: string | null;
  language: "zh" | "en";
  onGeneratePrompt: () => void;
  onGenerateAiReport: () => void;
};

function value(value: unknown, language: "zh" | "en") {
  if (value === null || value === undefined || value === "") {
    return language === "zh" ? "数据缺失" : "Data not available";
  }
  return String(value);
}

export default function MachineDetail({
  machine,
  telemetry,
  faults,
  promptText,
  aiReport,
  loadingAction,
  language,
  onGeneratePrompt,
  onGenerateAiReport
}: Props) {
  const t = language === "zh"
    ? {
        title: "设备详情",
        select: "请从车队列表中选择一台设备。",
        profile: "单车健康档案",
        basic: "基础信息",
        currentStatus: "当前状态",
        serial: "序列号",
        model: "型号",
        type: "类型",
        customer: "客户",
        location: "位置",
        recentLocation: "最近位置",
        lastSeen: "最后在线",
        telemetry: "最近遥测",
        hours: "运行小时",
        idle: "怠速小时",
        fuel: "剩余燃油",
        engine: "发动机状态",
        latitude: "纬度",
        longitude: "经度",
        risk: "风险说明",
        riskScore: "风险评分",
        faults: "故障列表",
        noFaults: "当前 cache 中没有故障记录。",
        healthSummary: "AI 健康总结",
        maintenance: "建议维修动作",
        serviceCase: "服务工单建议",
        genPrompt: "生成 AI Prompt",
        genAi: "生成 AI 报告",
        generating: "生成中...",
        aiPrompt: "AI Prompt",
        aiReport: "AI 报告",
        provider: "Provider",
        modelLabel: "模型",
        generatedAt: "生成时间",
        unavailable: "数据不可用"
      }
    : {
        title: "Machine Detail",
        select: "Select a machine from the fleet table.",
        profile: "Machine Health Profile",
        basic: "Basic Information",
        currentStatus: "Current Status",
        serial: "Serial",
        model: "Model",
        type: "Type",
        customer: "Customer",
        location: "Location",
        recentLocation: "Latest Location",
        lastSeen: "Last seen",
        telemetry: "Latest Telemetry",
        hours: "Operating hours",
        idle: "Idle hours",
        fuel: "Fuel remaining",
        engine: "Engine status",
        latitude: "Latitude",
        longitude: "Longitude",
        risk: "Risk Explanation",
        riskScore: "Risk Score",
        faults: "Fault List",
        noFaults: "No fault records in current cache.",
        healthSummary: "AI Health Summary",
        maintenance: "Recommended Maintenance Action",
        serviceCase: "Service Work Order Recommendation",
        genPrompt: "Generate AI Prompt",
        genAi: "Generate AI Report",
        generating: "Generating...",
        aiPrompt: "AI Prompt",
        aiReport: "AI Report",
        provider: "Provider",
        modelLabel: "Model",
        generatedAt: "Generated at",
        unavailable: "Data not available"
      };
  if (!machine) {
    return (
      <section className="panel detail-panel">
        <h2>{t.title}</h2>
        <p className="muted">{t.select}</p>
      </section>
    );
  }

  const latest = telemetry[telemetry.length - 1];

  return (
    <section className="panel detail-panel">
      <div className="panel-header">
        <div>
          <h2>{t.profile}</h2>
          <span>{machine.machine_id}</span>
        </div>
        <StatusBadge label={`${riskLevel(machine, language)} ${riskScore(machine)}`} tone={riskTone(machine)} />
      </div>

      <div className="detail-grid">
        <div>
          <h3>{t.basic}</h3>
          <p><strong>{t.serial}:</strong> {formatMissing(machine.serial_number, language)}</p>
          <p><strong>{t.modelLabel}:</strong> {formatMissing(machine.model, language)}</p>
          <p><strong>{t.type}:</strong> {formatMissing(machine.machine_type, language)}</p>
          <p><strong>{t.customer}:</strong> {formatMissing(machine.customer, language)}</p>
          <p><strong>{t.lastSeen}:</strong> {formatMissing(machine.last_seen_at, language)}</p>
        </div>

        <div>
          <h3>{t.currentStatus}</h3>
          <p><strong>{t.engine}:</strong> {value(latest?.engine_status, language)}</p>
          <p><strong>{t.fuel}:</strong> {value(latest?.fuel_remaining_percent, language)}</p>
          <p><strong>{t.riskScore}:</strong> {riskScore(machine)}</p>
          <p><strong>{t.faults}:</strong> {faults.length}</p>
        </div>

        <div>
          <h3>{t.recentLocation}</h3>
          <p><strong>{t.location}:</strong> {formatMissing(machine.location, language)}</p>
          <p><strong>{t.latitude}:</strong> {value(latest?.latitude ?? machine.latitude, language)}</p>
          <p><strong>{t.longitude}:</strong> {value(latest?.longitude ?? machine.longitude, language)}</p>
        </div>

        <div>
          <h3>{t.telemetry}</h3>
          <p><strong>{t.hours}:</strong> {value(latest?.operating_hours, language)}</p>
          <p><strong>{t.idle}:</strong> {value(latest?.idle_hours, language)}</p>
          <p><strong>{t.fuel}:</strong> {value(latest?.fuel_remaining_percent, language)}</p>
        </div>
      </div>

      <h3>{t.risk}</h3>
      <ul className="risk-list">
        {riskReasons(machine, language).map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>

      <h3>{t.maintenance}</h3>
      <p className="placeholder-callout">{recommendedAction(machine, language)}</p>

      <h3>{t.serviceCase}</h3>
      <p className="placeholder-callout">
        {language === "zh"
          ? "建议创建服务跟进记录，关联设备状态、故障记录、最近通信时间和客户信息。当前系统尚未接入真实工单系统。"
          : "Create a service follow-up linked to status, faults, last communication, and customer. Real work order integration is not connected yet."}
      </p>

      <h3>{t.faults}</h3>
      {faults.length === 0 ? (
        <p className="muted">{t.noFaults}</p>
      ) : (
        <div className="fault-list">
          {faults.map((fault) => (
            <div className="fault-item" key={`${fault.fault_code}-${fault.occurred_at}`}>
              <strong>{fault.fault_code}</strong>
              <span>SPN {value(fault.spn, language)} / FMI {value(fault.fmi, language)}</span>
              <span>{fault.severity} | {fault.status}</span>
              <span>{fault.description}</span>
            </div>
          ))}
        </div>
      )}

      <div className="actions">
        <button disabled={Boolean(loadingAction)} onClick={onGeneratePrompt}>
          {loadingAction === "prompt" ? t.generating : t.genPrompt}
        </button>
        <button disabled={Boolean(loadingAction)} onClick={onGenerateAiReport}>
          {loadingAction === "ai-report" ? t.generating : t.genAi}
        </button>
      </div>

      {promptText && (
        <div className="output-box">
          <h3>{t.aiPrompt}</h3>
          <pre>{promptText}</pre>
        </div>
      )}

      {aiReport && (
        <div className="output-box">
          <h3>{t.aiReport}</h3>
          <p><strong>{t.provider}:</strong> {aiReport.provider}</p>
          <p><strong>{t.modelLabel}:</strong> {aiReport.model}</p>
          <p><strong>{t.generatedAt}:</strong> {aiReport.generated_at}</p>
          {aiReport.error ? (
            <div className="inline-error">{aiReport.error}</div>
          ) : (
            <MarkdownRenderer content={aiReport.ai_report_markdown} />
          )}
        </div>
      )}
    </section>
  );
}
