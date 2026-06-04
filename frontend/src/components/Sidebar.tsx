import type { ViewKey } from "../types";

type NavItem = {
  key: ViewKey;
  zh: string;
  en: string;
};

const navItems: NavItem[] = [
  { key: "dashboard", zh: "车队总览", en: "Dashboard" },
  { key: "fleet", zh: "设备列表", en: "Fleet" },
  { key: "machine-health", zh: "设备健康", en: "Machine Health" },
  { key: "service-parts", zh: "服务与备件", en: "Service & Parts" },
  { key: "ai-assistant", zh: "AI 助手", en: "AI Assistant" },
  { key: "sync-cache", zh: "同步与缓存", en: "Sync & Cache" },
  { key: "reports", zh: "报告中心", en: "Reports" },
  { key: "settings", zh: "系统设置", en: "Settings" }
];

type Props = {
  activeView: ViewKey;
  language: "zh" | "en";
  onChangeView: (view: ViewKey) => void;
};

export default function Sidebar({ activeView, language, onChangeView }: Props) {
  return (
    <aside className="sidebar">
      <div className="brand-block">
        <div className="brand-mark">X</div>
        <div>
          <strong>XCMG NA</strong>
          <span>Telematics AI</span>
        </div>
      </div>
      <nav className="sidebar-nav">
        {navItems.map((item) => (
          <button
            key={item.key}
            className={activeView === item.key ? "nav-active" : ""}
            onClick={() => onChangeView(item.key)}
          >
            {language === "zh" ? item.zh : item.en}
          </button>
        ))}
      </nav>
    </aside>
  );
}
