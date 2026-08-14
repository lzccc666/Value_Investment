import { RefreshCw } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { StatusPill } from "../components/StatusPill";
import { getHealth, type HealthResponse } from "../services/api";
import { CompanySearchView } from "./CompanySearchView";
import { CompanyWorkspaceView } from "./CompanyWorkspaceView";
import { DashboardView } from "./DashboardView";
import { navigationItems } from "./dashboardData";

type WorkbenchView = "dashboard" | "company-search" | "company-workspace";

type ApiState =
  | { status: "checking"; label: "API 检查中" }
  | { status: "online"; label: string }
  | { status: "offline"; label: "API 未连接" };

const navigationViewMap: Record<string, WorkbenchView | null> = {
  Dashboard: "dashboard",
  "Company Search": "company-search",
  "Company Workspace": "company-workspace",
  Financials: null,
  Announcements: null,
  "Analyst Views": null,
  "Valuation Lab": null,
  Portfolio: null,
  Memo: null,
  Settings: null
};

const pageMeta: Record<WorkbenchView, { eyebrow: string; title: string }> = {
  dashboard: {
    eyebrow: "本地开发环境",
    title: "价值投资研究工作台"
  },
  "company-search": {
    eyebrow: "Company Search",
    title: "公司搜索与列表"
  },
  "company-workspace": {
    eyebrow: "Company Workspace",
    title: "公司档案"
  }
};

function formatApiState(health: HealthResponse | null, failed: boolean): ApiState {
  if (health) {
    return { status: "online", label: `${health.service} ${health.version}` };
  }

  if (failed) {
    return { status: "offline", label: "API 未连接" };
  }

  return { status: "checking", label: "API 检查中" };
}

export function App() {
  const [activeView, setActiveView] = useState<WorkbenchView>("dashboard");
  const [selectedCompanyId, setSelectedCompanyId] = useState<number | null>(null);
  const [refreshToken, setRefreshToken] = useState(0);
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let isMounted = true;

    getHealth()
      .then((result) => {
        if (isMounted) {
          setHealth(result);
          setFailed(false);
        }
      })
      .catch(() => {
        if (isMounted) {
          setFailed(true);
        }
      });

    return () => {
      isMounted = false;
    };
  }, [refreshToken]);

  const apiState = formatApiState(health, failed);
  const currentPage = pageMeta[activeView];

  function openCompany(companyId: number) {
    setSelectedCompanyId(companyId);
    setActiveView("company-workspace");
  }

  const handleCompanyUnavailable = useCallback(() => {
    setSelectedCompanyId(null);
    setActiveView("company-search");
  }, []);

  return (
    <div className="app-shell">
      <aside className="sidebar" aria-label="主导航">
        <div className="brand-block">
          <div className="brand-mark">VI</div>
          <div>
            <span>Value Investment</span>
            <strong>研究工作台</strong>
          </div>
        </div>

        <nav className="nav-list">
          {navigationItems.map((item) => {
            const Icon = item.icon;
            const targetView = navigationViewMap[item.label];
            const isActive = targetView === activeView;

            return (
              <button
                key={item.label}
                className={isActive ? "nav-item nav-item--active" : "nav-item"}
                type="button"
                title={targetView ? item.label : "模块待接入"}
                disabled={!targetView}
                aria-current={isActive ? "page" : undefined}
                onClick={() => {
                  if (targetView) {
                    setActiveView(targetView);
                  }
                }}
              >
                <Icon aria-hidden="true" size={18} strokeWidth={2} />
                <span>{item.label}</span>
              </button>
            );
          })}
        </nav>
      </aside>

      <main className="workspace">
        <header className="topbar">
          <div>
            <span className="eyebrow">{currentPage.eyebrow}</span>
            <h1>{currentPage.title}</h1>
          </div>
          <div className="topbar-actions">
            <StatusPill status={apiState.status} label={apiState.label} />
            <button
              className="icon-button"
              type="button"
              title="刷新当前页面"
              onClick={() => setRefreshToken((value) => value + 1)}
            >
              <RefreshCw aria-hidden="true" size={18} />
            </button>
          </div>
        </header>

        {activeView === "dashboard" ? <DashboardView /> : null}
        {activeView === "company-search" ? (
          <CompanySearchView
            selectedCompanyId={selectedCompanyId}
            onSelectCompany={openCompany}
            refreshToken={refreshToken}
          />
        ) : null}
        {activeView === "company-workspace" ? (
          <CompanyWorkspaceView
            companyId={selectedCompanyId}
            onBackToSearch={() => setActiveView("company-search")}
            onCompanyUnavailable={handleCompanyUnavailable}
            refreshToken={refreshToken}
          />
        ) : null}
      </main>
    </div>
  );
}
