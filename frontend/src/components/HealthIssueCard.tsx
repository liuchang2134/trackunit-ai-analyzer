import type { Machine } from "../types";
import StatusBadge from "./StatusBadge";

type Props = {
  machine: Machine;
  issueType: string;
  severity: "Critical" | "Warning" | "Info";
  evidence: string;
  action: string;
  missingFields?: string[];
  language?: "zh" | "en";
};

export default function HealthIssueCard({ machine, issueType, severity, evidence, action, missingFields = [], language = "en" }: Props) {
  const tone = severity === "Critical" ? "danger" : severity === "Warning" ? "warning" : "info";
  const severityLabel = language === "zh"
    ? severity === "Critical" ? "高" : severity === "Warning" ? "中" : "关注"
    : severity;
  return (
    <article className="issue-card">
      <div className="issue-card-header">
        <div>
          <strong>{machine.serial_number || machine.machine_id}</strong>
          <span>{machine.model}</span>
        </div>
        <StatusBadge label={severityLabel} tone={tone} />
      </div>
      <dl>
        <dt>{language === "zh" ? "问题" : "Issue"}</dt>
        <dd>{issueType}</dd>
        <dt>{language === "zh" ? "依据" : "Evidence"}</dt>
        <dd>{evidence}</dd>
        <dt>{language === "zh" ? "建议动作" : "Recommended action"}</dt>
        <dd>{action}</dd>
        {missingFields.length > 0 && (
          <>
            <dt>{language === "zh" ? "缺失字段" : "Missing fields"}</dt>
            <dd>{missingFields.join(", ")}</dd>
          </>
        )}
      </dl>
    </article>
  );
}
