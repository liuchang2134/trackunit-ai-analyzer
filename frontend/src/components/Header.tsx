import type { AiProvider, CacheStatus, ViewKey } from "../types";
import DataSourceBadge from "./DataSourceBadge";

type Props = {
  activeView: ViewKey;
  language: "zh" | "en";
  aiProvider: AiProvider;
  cacheStatus: CacheStatus | null;
  onToggleLanguage: () => void;
  onChangeProvider: (provider: AiProvider) => void;
};

const titles: Record<ViewKey, { zh: string; en: string }> = {
  dashboard: { zh: "车队运营总览", en: "Fleet Operations Dashboard" },
  fleet: { zh: "设备车队", en: "Fleet" },
  "machine-health": { zh: "设备健康中心", en: "Machine Health" },
  "service-parts": { zh: "服务与备件", en: "Service & Parts" },
  "ai-assistant": { zh: "AI 车队助手", en: "AI Fleet Assistant" },
  "sync-cache": { zh: "同步与缓存", en: "Sync & Cache" },
  reports: { zh: "报告中心", en: "Reports" },
  settings: { zh: "系统设置", en: "Settings" }
};

export default function Header({
  activeView,
  language,
  aiProvider,
  cacheStatus,
  onToggleLanguage,
  onChangeProvider
}: Props) {
  return (
    <header className="top-header">
      <div>
        <h1>{titles[activeView][language]}</h1>
        <p>
          {language === "zh"
            ? "Trackunit cache-first 数据分析 · AI 辅助服务运营决策"
            : "Trackunit cache-first analytics · AI-assisted service operations"}
        </p>
      </div>
      <div className="header-actions">
        <DataSourceBadge source={cacheStatus?.data_source} fresh={cacheStatus?.fresh} language={language} />
        <div className="provider-toggle" role="group" aria-label="AI provider">
          <button
            className={aiProvider === "deepseek" ? "toggle-active" : "secondary-button"}
            onClick={() => onChangeProvider("deepseek")}
          >
            DeepSeek
          </button>
          <button
            className={aiProvider === "ollama_local" ? "toggle-active" : "secondary-button"}
            onClick={() => onChangeProvider("ollama_local")}
          >
            {language === "zh" ? "本地 Qwen" : "Local Qwen"}
          </button>
          <button
            className={aiProvider === "gemini" ? "toggle-active" : "secondary-button"}
            onClick={() => onChangeProvider("gemini")}
          >
            Gemini
          </button>
        </div>
        <button className="secondary-button" onClick={onToggleLanguage}>
          {language === "zh" ? "English" : "中文"}
        </button>
      </div>
    </header>
  );
}
