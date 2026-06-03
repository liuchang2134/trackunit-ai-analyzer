import type { Machine } from "../types";
import StatusBadge from "./StatusBadge";

type Props = {
  machine: Machine;
  issueType: string;
  severity: "Critical" | "Warning" | "Info";
  evidence: string;
  action: string;
  missingFields?: string[];
};

export default function HealthIssueCard({ machine, issueType, severity, evidence, action, missingFields = [] }: Props) {
  const tone = severity === "Critical" ? "danger" : severity === "Warning" ? "warning" : "info";
  return (
    <article className="issue-card">
      <div className="issue-card-header">
        <div>
          <strong>{machine.serial_number || machine.machine_id}</strong>
          <span>{machine.model}</span>
        </div>
        <StatusBadge label={severity} tone={tone} />
      </div>
      <dl>
        <dt>Issue</dt>
        <dd>{issueType}</dd>
        <dt>Evidence</dt>
        <dd>{evidence}</dd>
        <dt>Recommended action</dt>
        <dd>{action}</dd>
        {missingFields.length > 0 && (
          <>
            <dt>Missing fields</dt>
            <dd>{missingFields.join(", ")}</dd>
          </>
        )}
      </dl>
    </article>
  );
}
