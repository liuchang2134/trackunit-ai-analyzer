import StatusBadge from "./StatusBadge";

export type ServiceCase = {
  id: string;
  machineLabel: string;
  reason: string;
  priority: "Critical" | "High" | "Medium" | "Low";
  action: string;
  status: "Open" | "In progress" | "Completed";
  relatedParts: string[];
};

type Props = {
  item: ServiceCase;
  language?: "zh" | "en";
};

export default function ServiceCaseCard({ item, language = "en" }: Props) {
  const tone = item.priority === "Critical" || item.priority === "High" ? "danger" : item.priority === "Medium" ? "warning" : "neutral";
  return (
    <article className="service-card">
      <div className="issue-card-header">
        <div>
          <strong>{item.machineLabel}</strong>
          <span>{item.reason}</span>
        </div>
        <StatusBadge label={priorityLabel(item.priority, language)} tone={tone} />
      </div>
      <p>{item.action}</p>
      <div className="service-meta">
        <StatusBadge label={statusLabel(item.status, language)} tone={item.status === "Completed" ? "good" : "info"} />
        <span>{item.relatedParts.join(", ")}</span>
      </div>
    </article>
  );
}

function priorityLabel(value: ServiceCase["priority"], language: "zh" | "en"): string {
  if (language === "en") return value;
  return value === "Critical" || value === "High" ? "高优先级" : value === "Medium" ? "中优先级" : "低优先级";
}

function statusLabel(value: ServiceCase["status"], language: "zh" | "en"): string {
  if (language === "en") return value;
  return value === "Completed" ? "已完成" : value === "In progress" ? "处理中" : "待处理";
}
