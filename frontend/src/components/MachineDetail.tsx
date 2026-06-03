import type { AiReportResponse, FaultCode, Machine, TelemetrySnapshot } from "../types";

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

function value(value: unknown) {
  if (value === null || value === undefined || value === "") {
    return "Data not available";
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
        basic: "基础信息",
        serial: "序列号",
        model: "型号",
        type: "类型",
        customer: "客户",
        location: "位置",
        lastSeen: "最后在线",
        telemetry: "最近遥测",
        hours: "运行小时",
        idle: "怠速小时",
        fuel: "剩余燃油",
        engine: "发动机状态",
        latitude: "纬度",
        longitude: "经度",
        risk: "风险说明",
        faults: "故障列表",
        noFaults: "当前 cache 中没有故障记录。",
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
        basic: "Basic Information",
        serial: "Serial",
        model: "Model",
        type: "Type",
        customer: "Customer",
        location: "Location",
        lastSeen: "Last seen",
        telemetry: "Latest Telemetry",
        hours: "Operating hours",
        idle: "Idle hours",
        fuel: "Fuel remaining",
        engine: "Engine status",
        latitude: "Latitude",
        longitude: "Longitude",
        risk: "Risk Explanation",
        faults: "Fault List",
        noFaults: "No fault records in current cache.",
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
        <h2>{t.title}</h2>
        <span>{machine.machine_id}</span>
      </div>

      <div className="detail-grid">
        <div>
          <h3>{t.basic}</h3>
          <p><strong>{t.serial}:</strong> {machine.serial_number}</p>
          <p><strong>{t.modelLabel}:</strong> {machine.model}</p>
          <p><strong>{t.type}:</strong> {machine.machine_type}</p>
          <p><strong>{t.customer}:</strong> {machine.customer}</p>
          <p><strong>{t.location}:</strong> {machine.location}</p>
          <p><strong>{t.lastSeen}:</strong> {machine.last_seen_at}</p>
        </div>

        <div>
          <h3>{t.telemetry}</h3>
          <p><strong>{t.hours}:</strong> {value(latest?.operating_hours)}</p>
          <p><strong>{t.idle}:</strong> {value(latest?.idle_hours)}</p>
          <p><strong>{t.fuel}:</strong> {value(latest?.fuel_remaining_percent)}</p>
          <p><strong>{t.engine}:</strong> {value(latest?.engine_status)}</p>
          <p><strong>{t.latitude}:</strong> {value(latest?.latitude)}</p>
          <p><strong>{t.longitude}:</strong> {value(latest?.longitude)}</p>
        </div>
      </div>

      <h3>{t.risk}</h3>
      <ul className="risk-list">
        {(machine.risk_explanation || ["No risk explanation available."]).map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>

      <h3>{t.faults}</h3>
      {faults.length === 0 ? (
        <p className="muted">{t.noFaults}</p>
      ) : (
        <div className="fault-list">
          {faults.map((fault) => (
            <div className="fault-item" key={`${fault.fault_code}-${fault.occurred_at}`}>
              <strong>{fault.fault_code}</strong>
              <span>SPN {value(fault.spn)} / FMI {value(fault.fmi)}</span>
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
            <pre>{aiReport.ai_report_markdown}</pre>
          )}
        </div>
      )}
    </section>
  );
}
