import type { CacheStatus } from "../types";
import DataSourceBadge from "./DataSourceBadge";
import StatusBadge from "./StatusBadge";

type Props = {
  cacheStatus: CacheStatus | null;
  language: "zh" | "en";
};

export default function CacheStatusPanel({ cacheStatus, language }: Props) {
  const t = language === "zh"
    ? {
        title: "Cache / 数据新鲜度",
        exists: "Cache 存在",
        updated: "更新时间",
        age: "缓存年龄",
        ttl: "TTL",
        policy: "当前策略",
        noData: "没有 cache 状态"
      }
    : {
        title: "Cache / Data Freshness",
        exists: "Cache exists",
        updated: "Updated",
        age: "Cache age",
        ttl: "TTL",
        policy: "Policy",
        noData: "No cache status"
      };

  if (!cacheStatus) {
    return <section className="panel empty-panel">{t.noData}</section>;
  }

  return (
    <section className="panel">
      <div className="panel-header">
        <div>
          <h2>{t.title}</h2>
          <span>{t.policy}: cache-first, no refresh on ask</span>
        </div>
        <DataSourceBadge source={cacheStatus.data_source} fresh={cacheStatus.fresh} />
      </div>
      <div className="status-grid">
        <div><span>{t.exists}</span><strong>{cacheStatus.exists ? "true" : "false"}</strong></div>
        <div><span>{t.updated}</span><strong>{formatDate(cacheStatus.updated_at)}</strong></div>
        <div><span>{t.age}</span><strong>{formatAge(cacheStatus.age_seconds)}</strong></div>
        <div><span>{t.ttl}</span><strong>{cacheStatus.ttl_seconds}s</strong></div>
        <div><span>Fresh</span><StatusBadge label={cacheStatus.fresh ? "fresh" : "stale"} tone={cacheStatus.fresh ? "good" : "warning"} /></div>
      </div>
    </section>
  );
}

function formatDate(value: string | null): string {
  if (!value) return "Not available";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

function formatAge(value: number | null): string {
  if (value === null) return "Not available";
  if (value < 60) return `${Math.round(value)}s`;
  if (value < 3600) return `${Math.round(value / 60)}m`;
  return `${Math.round(value / 3600)}h`;
}
