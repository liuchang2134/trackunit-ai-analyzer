import StatusBadge from "./StatusBadge";

type Props = {
  source?: string;
  fresh?: boolean;
};

export default function DataSourceBadge({ source = "unknown", fresh }: Props) {
  const label = fresh === undefined ? source : `${source} · ${fresh ? "fresh" : "stale"}`;
  return <StatusBadge label={label} tone={source === "trackunit_api" ? "good" : fresh ? "info" : "warning"} />;
}
