import type { SyncLog } from "../types";
import StatusBadge from "./StatusBadge";

type Props = {
  logs: SyncLog[];
  language: "zh" | "en";
  syncing: boolean;
  syncMessage: string;
  onSync: () => void;
};

export default function SyncLogsPanel({ logs, language, syncing, syncMessage, onSync }: Props) {
  const t = language === "zh"
    ? { title: "同步日志", sync: "手动同步 Fleet Snapshot", syncing: "同步中...", empty: "暂无同步日志", records: "记录数" }
    : { title: "Sync Logs", sync: "Sync Fleet Snapshot", syncing: "Syncing...", empty: "No sync logs", records: "Records" };

  return (
    <section className="panel">
      <div className="panel-header">
        <div>
          <h2>{t.title}</h2>
          <span>{language === "zh" ? "同步按钮不会自动重复请求" : "Manual sync does not repeat automatically"}</span>
        </div>
        <button disabled={syncing} onClick={onSync}>{syncing ? t.syncing : t.sync}</button>
      </div>
      {syncMessage && <div className={messageClass(syncMessage)}>{syncMessage}</div>}
      <div className="table-wrap">
        <table className="data-table">
          <thead>
            <tr>
              <th>Type</th>
              <th>Status</th>
              <th>{t.records}</th>
              <th>Finished</th>
              <th>Error</th>
            </tr>
          </thead>
          <tbody>
            {logs.length === 0 ? (
              <tr><td colSpan={5}>{t.empty}</td></tr>
            ) : logs.slice(-12).reverse().map((log, index) => (
              <tr key={`${log.finished_at || log.created_at || "log"}-${index}`}>
                <td>{log.sync_type}</td>
                <td><StatusBadge label={log.status} tone={log.status === "success" ? "good" : "danger"} /></td>
                <td>{log.records ?? "-"}</td>
                <td>{log.finished_at || log.created_at || "-"}</td>
                <td>{log.error || "-"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function messageClass(message: string): string {
  const lower = message.toLowerCase();
  if (lower.includes("429") || lower.includes("rate limit")) return "warning-banner";
  if (lower.includes("success") || lower.includes("成功")) return "success-banner";
  return "inline-error";
}
