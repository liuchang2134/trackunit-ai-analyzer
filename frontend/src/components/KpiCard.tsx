import StatusBadge from "./StatusBadge";

type Props = {
  label: string;
  value: string | number;
  helper?: string;
  tone?: "good" | "warning" | "danger" | "neutral" | "info";
};

export default function KpiCard({ label, value, helper, tone = "neutral" }: Props) {
  return (
    <div className="kpi-card">
      <div className="kpi-top">
        <span>{label}</span>
        <StatusBadge label={tone} tone={tone} />
      </div>
      <div className="kpi-value">{value}</div>
      {helper && <div className="kpi-helper">{helper}</div>}
    </div>
  );
}
