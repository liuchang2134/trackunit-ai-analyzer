import type { FleetTrends } from "../types";

type Props = {
  trends: FleetTrends | null;
  language: "zh" | "en";
};

export default function TrendSummaryPanel({ trends, language }: Props) {
  const latest = trends?.latest;
  return (
    <section className="panel">
      <div className="panel-header">
        <div>
          <h2>{language === "zh" ? "历史趋势分析" : "Historical Trend Analysis"}</h2>
          <span>{language === "zh" ? "来自 SQLite fleet_snapshot_history" : "From SQLite fleet_snapshot_history"}</span>
        </div>
        <span className="pill">{trends?.point_count ?? 0} points</span>
      </div>
      {!latest ? (
        <div className="empty-panel">
          {language === "zh" ? "还没有历史快照。运行一次 Trackunit 同步后会生成趋势点。" : "No history yet. Run Trackunit sync to create trend points."}
        </div>
      ) : (
        <>
          <div className="mini-kpi-grid">
            <div><span>{language === "zh" ? "设备总数" : "Total"}</span><strong>{latest.total_machines}</strong></div>
            <div><span>{language === "zh" ? "离线" : "Offline"}</span><strong>{latest.offline_machines}</strong></div>
            <div><span>{language === "zh" ? "低油量" : "Low Fuel"}</span><strong>{latest.low_fuel_machines}</strong></div>
            <div><span>{language === "zh" ? "低利用率" : "Low Utilization"}</span><strong>{latest.low_utilization_machines}</strong></div>
          </div>
          <div className="trend-notes">
            {trends.summary.map((item) => <p key={item}>{item}</p>)}
          </div>
        </>
      )}
    </section>
  );
}
