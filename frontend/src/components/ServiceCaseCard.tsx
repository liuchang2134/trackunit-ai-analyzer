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
};

export default function ServiceCaseCard({ item }: Props) {
  const tone = item.priority === "Critical" || item.priority === "High" ? "danger" : item.priority === "Medium" ? "warning" : "neutral";
  return (
    <article className="service-card">
      <div className="issue-card-header">
        <div>
          <strong>{item.machineLabel}</strong>
          <span>{item.reason}</span>
        </div>
        <StatusBadge label={item.priority} tone={tone} />
      </div>
      <p>{item.action}</p>
      <div className="service-meta">
        <StatusBadge label={item.status} tone={item.status === "Completed" ? "good" : "info"} />
        <span>{item.relatedParts.join(", ")}</span>
      </div>
    </article>
  );
}
