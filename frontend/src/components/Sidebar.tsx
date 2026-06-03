import type { ViewKey } from "../types";

type NavItem = {
  key: ViewKey;
  zh: string;
  en: string;
};

const navItems: NavItem[] = [
  { key: "dashboard", zh: "Dashboard", en: "Dashboard" },
  { key: "fleet", zh: "Fleet", en: "Fleet" },
  { key: "machine-health", zh: "Machine Health", en: "Machine Health" },
  { key: "service-parts", zh: "Service & Parts", en: "Service & Parts" },
  { key: "ai-assistant", zh: "AI Assistant", en: "AI Assistant" },
  { key: "sync-cache", zh: "Sync & Cache", en: "Sync & Cache" },
  { key: "reports", zh: "Reports", en: "Reports" },
  { key: "settings", zh: "Settings", en: "Settings" }
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
