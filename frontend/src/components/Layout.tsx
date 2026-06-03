import type { AiProvider, CacheStatus, ViewKey } from "../types";
import type { ReactNode } from "react";
import Header from "./Header";
import Sidebar from "./Sidebar";

type Props = {
  activeView: ViewKey;
  language: "zh" | "en";
  aiProvider: AiProvider;
  cacheStatus: CacheStatus | null;
  children: ReactNode;
  onChangeView: (view: ViewKey) => void;
  onToggleLanguage: () => void;
  onChangeProvider: (provider: AiProvider) => void;
};

export default function Layout({
  activeView,
  language,
  aiProvider,
  cacheStatus,
  children,
  onChangeView,
  onToggleLanguage,
  onChangeProvider
}: Props) {
  return (
    <div className="enterprise-shell">
      <Sidebar activeView={activeView} language={language} onChangeView={onChangeView} />
      <div className="workspace">
        <Header
          activeView={activeView}
          language={language}
          aiProvider={aiProvider}
          cacheStatus={cacheStatus}
          onToggleLanguage={onToggleLanguage}
          onChangeProvider={onChangeProvider}
        />
        <main className="workspace-main">{children}</main>
      </div>
    </div>
  );
}
