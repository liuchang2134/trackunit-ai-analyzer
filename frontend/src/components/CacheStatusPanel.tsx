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
        title: "缓存 / 数据新鲜度",
        exists: "缓存存在",
        updated: "更新时间",
        age: "缓存年龄",
        ttl: "有效期",
        policy: "当前策略",
        noData: "没有缓存状态",
        policyValue: "优先使用缓存，提问时不自动刷新",
        fresh: "新鲜度",
        yes: "是",
        no: "否",
        freshValue: "有效",
        staleValue: "过期",
        notAvailable: "数据缺失"
      }
    : {
        title: "Cache / Data Freshness",
        exists: "Cache exists",
        updated: "Updated",
        age: "Cache age",
        ttl: "TTL",
        policy: "Policy",
        noData: "No cache status",
        policyValue: "cache-first, no refresh on ask",
        fresh: "Freshness",
        yes: "true",
        no: "false",
        freshValue: "fresh",
        staleValue: "stale",
        notAvailable: "Not available"
      };

  if (!cacheStatus) {
    return <section className="panel empty-panel">{t.noData}</section>;
  }

  return (
    <section className="panel">
      <div className="panel-header">
        <div>
          <h2>{t.title}</h2>
          <span>{t.policy}: {t.policyValue}</span>
        </div>
        <DataSourceBadge source={cacheStatus.data_source} fresh={cacheStatus.fresh} language={language} />
      </div>
      <div className="status-grid">
        <div><span>{t.exists}</span><strong>{cacheStatus.exists ? t.yes : t.no}</strong></div>
        <div><span>{t.updated}</span><strong>{formatDate(cacheStatus.updated_at, t.notAvailable)}</strong></div>
        <div><span>{t.age}</span><strong>{formatAge(cacheStatus.age_seconds, t.notAvailable)}</strong></div>
        <div><span>{t.ttl}</span><strong>{cacheStatus.ttl_seconds}s</strong></div>
        <div><span>{t.fresh}</span><StatusBadge label={cacheStatus.fresh ? t.freshValue : t.staleValue} tone={cacheStatus.fresh ? "good" : "warning"} /></div>
      </div>
    </section>
  );
}

function formatDate(value: string | null, fallback: string): string {
  if (!value) return fallback;
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

function formatAge(value: number | null, fallback: string): string {
  if (value === null) return fallback;
  if (value < 60) return `${Math.round(value)}s`;
  if (value < 3600) return `${Math.round(value / 60)}m`;
  return `${Math.round(value / 3600)}h`;
}
