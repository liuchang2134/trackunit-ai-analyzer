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
};

export default function PartsDemandCard({ item }: Props) {
  return (
    <article className="parts-card">
      <div className="issue-card-header">
        <div>
          <strong>{item.partNumber}</strong>
          <span>{item.partName}</span>
        </div>
        <StatusBadge label={item.priority} tone={item.priority === "High" ? "danger" : item.priority === "Medium" ? "warning" : "neutral"} />
      </div>
      <dl>
        <dt>Machine</dt>
        <dd>{item.machineLabel}</dd>
        <dt>Quantity</dt>
        <dd>{item.quantity}</dd>
        <dt>Reason</dt>
        <dd>{item.reason}</dd>
        <dt>Source</dt>
        <dd>{item.source}</dd>
      </dl>
    </article>
  );
}
