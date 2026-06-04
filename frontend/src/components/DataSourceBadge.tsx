import StatusBadge from "./StatusBadge";

type Props = {
  source?: string;
  fresh?: boolean;
  language?: "zh" | "en";
};

export default function DataSourceBadge({ source = "unknown", fresh, language = "en" }: Props) {
  const sourceLabel = language === "zh"
    ? source === "trackunit_cache" ? "Trackunit 缓存" : source === "trackunit_api" ? "Trackunit API" : source === "mock" ? "模拟数据" : source === "unknown" ? "未知" : source
    : source;
  const freshness = fresh ? (language === "zh" ? "有效" : "fresh") : (language === "zh" ? "过期" : "stale");
  const label = fresh === undefined ? sourceLabel : `${sourceLabel} · ${freshness}`;
  return <StatusBadge label={label} tone={source === "trackunit_api" ? "good" : fresh ? "info" : "warning"} />;
}
