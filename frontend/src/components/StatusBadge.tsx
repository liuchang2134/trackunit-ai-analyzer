type StatusTone = "good" | "warning" | "danger" | "neutral" | "info";

type Props = {
  label: string;
  tone?: StatusTone;
};

export default function StatusBadge({ label, tone = "neutral" }: Props) {
  return <span className={`status-badge status-${tone}`}>{label}</span>;
}
