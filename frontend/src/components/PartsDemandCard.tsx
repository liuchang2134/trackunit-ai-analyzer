import StatusBadge from "./StatusBadge";

export type PartsDemand = {
  id: string;
  partNumber: string;
  partName: string;
  machineLabel: string;
  quantity: string;
  priority: "High" | "Medium" | "Low";
  reason: string;
  source: "AI inferred" | "Rule based" | "Missing data";
};

type Props = {
  item: PartsDemand;
  language?: "zh" | "en";
};

export default function PartsDemandCard({ item, language = "en" }: Props) {
  return (
    <article className="parts-card">
      <div className="issue-card-header">
        <div>
          <strong>{item.partNumber}</strong>
          <span>{item.partName}</span>
        </div>
        <StatusBadge label={priorityLabel(item.priority, language)} tone={item.priority === "High" ? "danger" : item.priority === "Medium" ? "warning" : "neutral"} />
      </div>
      <dl>
        <dt>{language === "zh" ? "设备" : "Machine"}</dt>
        <dd>{item.machineLabel}</dd>
        <dt>{language === "zh" ? "数量" : "Quantity"}</dt>
        <dd>{item.quantity}</dd>
        <dt>{language === "zh" ? "原因" : "Reason"}</dt>
        <dd>{item.reason}</dd>
        <dt>{language === "zh" ? "来源" : "Source"}</dt>
        <dd>{sourceLabel(item.source, language)}</dd>
      </dl>
    </article>
  );
}

function priorityLabel(value: PartsDemand["priority"], language: "zh" | "en"): string {
  if (language === "en") return value;
  return value === "High" ? "高" : value === "Medium" ? "中" : "低";
}

function sourceLabel(value: PartsDemand["source"], language: "zh" | "en"): string {
  if (language === "en") return value;
  return value === "Missing data" ? "数据缺失" : value === "Rule based" ? "规则生成" : "AI 推断";
}
