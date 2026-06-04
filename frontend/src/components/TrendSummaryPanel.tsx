import type { FleetTrends } from "../types";
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

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
        <span className="pill">{trends?.point_count ?? 0} {language === "zh" ? "个快照" : "points"}</span>
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
            <div><span>{language === "zh" ? "故障记录" : "Fault Records"}</span><strong>{latest.fault_records}</strong></div>
          </div>
          <div className="trend-chart">
            <ResponsiveContainer width="100%" height={220}>
              <LineChart data={trends.points.map((point) => ({
                ...point,
                label: new Date(point.captured_at).toLocaleDateString(),
              }))}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="label" />
                <YAxis allowDecimals={false} />
                <Tooltip />
                <Line type="monotone" dataKey="offline_machines" name={language === "zh" ? "离线" : "Offline"} stroke="#b42318" strokeWidth={2} dot={false} />
                <Line type="monotone" dataKey="low_fuel_machines" name={language === "zh" ? "低油量" : "Low fuel"} stroke="#a15c07" strokeWidth={2} dot={false} />
                <Line type="monotone" dataKey="low_utilization_machines" name={language === "zh" ? "低利用率" : "Low utilization"} stroke="#155eef" strokeWidth={2} dot={false} />
                <Line type="monotone" dataKey="fault_records" name={language === "zh" ? "故障" : "Faults"} stroke="#475467" strokeWidth={2} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
          <div className="trend-notes">
            {buildNotes(trends, language).map((item) => <p key={item}>{item}</p>)}
          </div>
        </>
      )}
    </section>
  );
}

function buildNotes(trends: FleetTrends, language: "zh" | "en"): string[] {
  const latest = trends.latest;
  if (!latest) return [];
  if (language === "en") return trends.summary;
  const notes = [
    `最新快照：共 ${latest.total_machines} 台设备，离线 ${latest.offline_machines} 台，低油量 ${latest.low_fuel_machines} 台，低利用率 ${latest.low_utilization_machines} 台。`,
  ];
  const offlineDelta = trends.deltas.offline_machines;
  if (typeof offlineDelta === "number") {
    notes.push(`离线设备较上一快照${offlineDelta > 0 ? "增加" : offlineDelta < 0 ? "减少" : "持平"} ${Math.abs(offlineDelta)} 台。`);
  }
  const faultDelta = trends.deltas.fault_records;
  if (typeof faultDelta === "number") {
    notes.push(`故障记录较上一快照${faultDelta > 0 ? "增加" : faultDelta < 0 ? "减少" : "持平"} ${Math.abs(faultDelta)} 条。`);
  }
  return notes;
}
