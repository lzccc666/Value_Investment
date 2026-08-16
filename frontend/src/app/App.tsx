import { RefreshCw } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { StatusPill } from "../components/StatusPill";
import { getHealth, type Company, type HealthResponse } from "../services/api";
import {
  CompanySearchView,
  type CompanySearchLocation
} from "./CompanySearchView";
import {
  CompanyWorkspaceView,
  type CompanyWorkspaceSection
} from "./CompanyWorkspaceView";
import { DashboardView } from "./DashboardView";
import { DataManagementView } from "./DataManagementView";
import { ParameterConfigView } from "./ParameterConfigView";
import { navigationItems, type NavItemId } from "./dashboardData";

type WorkbenchView = "dashboard" | "company-search" | "company-workspace" | "parameter-config" | "data-management";

type ApiState =
  | { status: "checking"; label: "API 检查中" }
  | { status: "online"; label: string }
  | { status: "offline"; label: "API 未连接" };

const navigationViewMap: Record<
  NavItemId,
  { view: WorkbenchView; section?: CompanyWorkspaceSection }
> = {
  dashboard: { view: "dashboard" },
  "company-search": { view: "company-search" },
  "company-workspace": { view: "company-workspace", section: "overview" },
  financials: { view: "company-workspace", section: "financials" },
  announcements: { view: "company-workspace", section: "announcements" },
  evidence: { view: "company-workspace", section: "evidence" },
  "analyst-views": { view: "company-workspace", section: "analyst-views" },
  "valuation-lab": { view: "company-workspace", section: "valuation-lab" },
  memo: { view: "company-workspace", section: "memo" },
  "price-decision": { view: "company-workspace", section: "price-decision" },
  "parameter-config": { view: "parameter-config" },
  "data-management": { view: "data-management" }
};

const pageMeta: Record<WorkbenchView, { eyebrow: string; title: string }> = {
  dashboard: {
    eyebrow: "Research System · 004-011",
    title: "价值投资研究工作台"
  },
  "company-search": {
    eyebrow: "Company Search",
    title: "公司搜索与列表"
  },
  "company-workspace": {
    eyebrow: "Company Workspace",
    title: "公司档案"
  },
  "parameter-config": {
    eyebrow: "全局参数 · 004-011",
    title: "参数配置中心"
  },
  "data-management": {
    eyebrow: "Operations · 012",
    title: "数据管理"
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
  const [activeCompanySection, setActiveCompanySection] =
    useState<CompanyWorkspaceSection>("overview");
  const [selectedCompany, setSelectedCompany] = useState<Company | null>(null);
  const [companySearchLocation, setCompanySearchLocation] = useState<CompanySearchLocation>({
    query: "",
    offset: 0
  });
  const [companySearchScrollTop, setCompanySearchScrollTop] = useState(0);
  const [companySearchRestoreToken, setCompanySearchRestoreToken] = useState(0);
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

  function openCompany(company: Company) {
    setSelectedCompany(company);
    setActiveCompanySection("overview");
    setActiveView("company-workspace");
  }

  function openCompanyFromSearch(company: Company) {
    setCompanySearchScrollTop(window.scrollY);
    openCompany(company);
  }

  function returnToCompanySearch() {
    if (activeView !== "company-search") {
      setCompanySearchRestoreToken((value) => value + 1);
    }
    setActiveView("company-search");
  }

  function openCompanySection(section: CompanyWorkspaceSection) {
    if (!selectedCompany) {
      returnToCompanySearch();
      return;
    }

    setActiveCompanySection(section);
    setActiveView("company-workspace");
  }

  const handleCompanyUnavailable = useCallback(() => {
    setSelectedCompany(null);
    setCompanySearchRestoreToken((value) => value + 1);
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
            const target = navigationViewMap[item.id];
            const isActive =
              target?.view === activeView &&
              (target.view !== "company-workspace" ||
                target.section === activeCompanySection ||
                (!target.section && activeView === "company-workspace"));

            return (
              <button
                key={item.id}
                className={isActive ? "nav-item nav-item--active" : "nav-item"}
                type="button"
                title={item.label}
                aria-current={isActive ? "page" : undefined}
                onClick={() => {
                  if (target) {
                    if (target.section) {
                      setActiveCompanySection(target.section);
                    }
                    if (target.view === "company-search") {
                      returnToCompanySearch();
                    } else {
                      setActiveView(target.view);
                    }
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

        {activeView === "dashboard" ? (
          <DashboardView
            selectedCompany={selectedCompany}
            refreshToken={refreshToken}
            onOpenSearch={returnToCompanySearch}
            onOpenCompany={openCompany}
            onOpenSection={openCompanySection}
          />
        ) : null}
        {activeView === "company-search" ? (
          <CompanySearchView
            selectedCompanyId={selectedCompany?.id ?? null}
            onSelectCompany={openCompanyFromSearch}
            refreshToken={refreshToken}
            location={companySearchLocation}
            onLocationChange={setCompanySearchLocation}
            restoreScrollTop={companySearchScrollTop}
            restoreToken={companySearchRestoreToken}
          />
        ) : null}
        {activeView === "company-workspace" ? (
          <CompanyWorkspaceView
            companyId={selectedCompany?.id ?? null}
            activeSection={activeCompanySection}
            onSectionChange={setActiveCompanySection}
            onBackToSearch={returnToCompanySearch}
            onCompanyUnavailable={handleCompanyUnavailable}
            refreshToken={refreshToken}
          />
        ) : null}
        {activeView === "data-management" ? (
          <DataManagementView refreshToken={refreshToken} />
        ) : null}
        {activeView === "parameter-config" ? (
          <ParameterConfigView refreshToken={refreshToken} />
        ) : null}
      </main>
    </div>
  );
}
