import { useEffect, useMemo, useState } from "react";
import { askFleetAssistant } from "../api";
import type { AiProvider, AskResponse } from "../types";
import DataSourceBadge from "./DataSourceBadge";

const chips = {
  zh: [
    "总结当前车队健康状况",
    "哪些设备离线？",
    "哪些设备油量低？",
    "哪些设备利用率低？",
    "哪些设备有故障？",
    "哪些设备有重复故障？",
    "哪些设备需要优先维修？",
    "未来哪些设备可能需要备件？"
  ],
  en: [
    "Summarize current fleet health",
    "Which machines are offline?",
    "Which machines have low fuel?",
    "Which machines have faults?",
    "Which machines have repeated faults?",
    "Which machines need urgent service?",
    "Which machines may need parts soon?"
  ]
};

type Props = {
  language: "zh" | "en";
  aiProvider: AiProvider;
};

type RecordRow = {
  machine_id?: string;
  serial_number?: string;
  model?: string;
  fuel_remaining_percent?: number | null;
  operating_hours?: number | null;
  last_seen_at?: string;
  fault_count?: number;
};

export default function AiAssistantPanel({ language, aiProvider }: Props) {
  const [question, setQuestion] = useState(chips[language][0]);
  const [result, setResult] = useState<AskResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    setQuestion(chips[language][0]);
    setResult(null);
    setError("");
  }, [language]);

  const records = useMemo(() => extractRows(result?.used_data), [result]);

  async function ask() {
    if (!question.trim()) {
      setError(language === "zh" ? "请输入问题。" : "Please enter a question.");
      return;
    }
    setLoading(true);
    setError("");
    setResult(null);
    try {
      setResult(await askFleetAssistant(question, "auto", aiProvider));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to ask fleet assistant.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="panel assistant-panel">
      <div className="panel-header">
        <div>
          <h2>{language === "zh" ? "AI 车队助手" : "AI Fleet Assistant"}</h2>
          <span>{language === "zh" ? "意图理解 + 规则查询 + AI 润色" : "Intent planning + rule query + AI wording"}</span>
        </div>
      </div>
      <div className="assistant-body">
        <div className="example-row">
          {chips[language].map((item) => (
            <button className="secondary-button" key={item} onClick={() => setQuestion(item)}>{item}</button>
          ))}
        </div>
        <div className="ask-row">
          <textarea value={question} rows={3} onChange={(event) => setQuestion(event.target.value)} />
          <button disabled={loading} onClick={ask}>
            {loading ? (language === "zh" ? "分析中..." : "Analyzing...") : (language === "zh" ? "提问" : "Ask")}
          </button>
        </div>
        {error && <div className="inline-error">{error}</div>}
        {result && (
          <div className="assistant-result">
            <div className="result-meta">
              <span>{language === "zh" ? "意图" : "Intent"}: {result.intent}</span>
              <span>Provider: {result.provider}</span>
              <span>{language === "zh" ? "模型" : "Model"}: {result.model}</span>
              <DataSourceBadge source={result.data_summary?.source || result.data_source} fresh={result.data_summary?.cache_fresh} />
              <span>{language === "zh" ? "分析模式" : "Analysis mode"}: {result.analysis_mode || "-"}</span>
              <span>{language === "zh" ? "扫描设备" : "Machines scanned"}: {result.data_summary?.machines_scanned ?? "-"}</span>
              <span>{language === "zh" ? "使用记录" : "Records used"}: {result.data_summary?.records_used ?? "-"}</span>
              <span>{language === "zh" ? "风险分析" : "Risk analysis"}: enabled</span>
              <span>{language === "zh" ? "质量校验" : "Quality"}: {result.quality_validation?.valid === false ? "failed" : "passed"}</span>
            </div>
            {result.fallback_used && (
              <div className="warning-banner">
                {language === "zh"
                  ? "Trackunit API 调用失败，当前结果基于本地 cache，可能不是实时状态。"
                  : "Trackunit API failed. Current result is based on local cache and may not be real-time."}
              </div>
            )}
            {result.api_error && <div className="inline-error">{result.api_error}</div>}
            {result.missing_fields && result.missing_fields.length > 0 && (
              <div className="missing-fields">
                <strong>{language === "zh" ? "缺失字段" : "Missing fields"}:</strong> {result.missing_fields.join(", ")}
              </div>
            )}
            <pre className="answer-box">{result.answer || result.answer_markdown}</pre>
            {records.length > 0 && <ResultRecordsTable rows={records} language={language} />}
            {result.risk_ranking && result.risk_ranking.length > 0 && (
              <details open>
                <summary>{language === "zh" ? "风险排序" : "Risk Ranking"}</summary>
                <RiskRankingTable rows={result.risk_ranking.slice(0, 10)} language={language} />
              </details>
            )}
            {result.service_recommendations && result.service_recommendations.length > 0 && (
              <details open>
                <summary>{language === "zh" ? "服务建议" : "Service Recommendations"}</summary>
                <ServiceRecommendationList rows={result.service_recommendations.slice(0, 8)} />
              </details>
            )}
            <details>
              <summary>{language === "zh" ? "查询计划" : "Query plan"}</summary>
              <pre>{JSON.stringify(result.query_plan || result.intent_plan, null, 2)}</pre>
            </details>
            <details>
              <summary>{language === "zh" ? "使用的数据" : "Used data"}</summary>
              <pre>{JSON.stringify(result.used_data, null, 2)}</pre>
            </details>
          </div>
        )}
      </div>
    </section>
  );
}

function RiskRankingTable({ rows, language }: { rows: Array<Record<string, unknown>>; language: "zh" | "en" }) {
  return (
    <div className="table-wrap compact-result-table">
      <table className="data-table">
        <thead>
          <tr>
            <th>{language === "zh" ? "设备" : "Machine"}</th>
            <th>{language === "zh" ? "型号" : "Model"}</th>
            <th>{language === "zh" ? "风险分" : "Risk Score"}</th>
            <th>{language === "zh" ? "等级" : "Level"}</th>
            <th>{language === "zh" ? "原因" : "Reason"}</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => (
            <tr key={`${String(row.machine_id || "risk")}-${index}`}>
              <td>{String(row.serial_number || row.machine_id || "-")}</td>
              <td>{String(row.model || "-")}</td>
              <td>{String(row.risk_score ?? "-")}</td>
              <td>{String(row.risk_level || "-")}</td>
              <td>{Array.isArray(row.risk_reason) ? row.risk_reason.join("; ") : String(row.risk_reason || "-")}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ServiceRecommendationList({ rows }: { rows: Array<Record<string, unknown>> }) {
  return (
    <div className="issue-list">
      {rows.map((row, index) => (
        <article className="service-card" key={`${String(row.machine_id || "svc")}-${index}`}>
          <div className="issue-card-header">
            <div>
              <strong>{String(row.serial_number || row.machine_id || "-")} / {String(row.model || "-")}</strong>
              <span>{String(row.priority || "-")}</span>
            </div>
          </div>
          <p>{String(row.recommended_action || "-")}</p>
          <p className="muted">{String(row.parts_recommendation || "-")}</p>
        </article>
      ))}
    </div>
  );
}

function ResultRecordsTable({ rows, language }: { rows: RecordRow[]; language: "zh" | "en" }) {
  return (
    <div className="table-wrap compact-result-table">
      <table className="data-table">
        <thead>
          <tr>
            <th>{language === "zh" ? "设备" : "Machine"}</th>
            <th>{language === "zh" ? "序列号" : "Serial"}</th>
            <th>{language === "zh" ? "型号" : "Model"}</th>
            <th>{language === "zh" ? "油量" : "Fuel"}</th>
            <th>{language === "zh" ? "小时" : "Hours"}</th>
            <th>{language === "zh" ? "故障" : "Faults"}</th>
            <th>{language === "zh" ? "最近通信" : "Last seen"}</th>
          </tr>
        </thead>
        <tbody>
          {rows.slice(0, 20).map((row, index) => (
            <tr key={`${row.machine_id || row.serial_number || "row"}-${index}`}>
              <td>{row.machine_id || "-"}</td>
              <td>{row.serial_number || "-"}</td>
              <td>{row.model || "-"}</td>
              <td>{row.fuel_remaining_percent === null || row.fuel_remaining_percent === undefined ? "Missing" : `${row.fuel_remaining_percent}%`}</td>
              <td>{row.operating_hours ?? "-"}</td>
              <td>{row.fault_count ?? 0}</td>
              <td>{row.last_seen_at || "-"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function extractRows(value: unknown): RecordRow[] {
  if (!isObject(value)) return [];
  const records = value.records;
  if (!Array.isArray(records)) return [];
  return records.filter(isObject).map((item) => ({
    machine_id: asString(item.machine_id),
    serial_number: asString(item.serial_number),
    model: asString(item.model),
    fuel_remaining_percent: asNumberOrNull(item.fuel_remaining_percent),
    operating_hours: asNumberOrNull(item.operating_hours),
    last_seen_at: asString(item.last_seen_at),
    fault_count: asNumber(item.fault_count)
  }));
}

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function asString(value: unknown): string | undefined {
  return typeof value === "string" ? value : undefined;
}

function asNumber(value: unknown): number | undefined {
  return typeof value === "number" ? value : undefined;
}

function asNumberOrNull(value: unknown): number | null | undefined {
  if (value === null) return null;
  return typeof value === "number" ? value : undefined;
}
