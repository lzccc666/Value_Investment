import { AlertTriangle, CheckCircle2, Power, RefreshCw } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { StatusPill } from "../components/StatusPill";
import {
  getHealth,
  requestLocalShutdown,
  type Company,
  type HealthResponse
} from "../services/api";
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
import { InvestmentToolsView } from "./InvestmentToolsView";
import { ParameterConfigView } from "./ParameterConfigView";
import { navigationItems, type NavItemId } from "./dashboardData";

type WorkbenchView =
  | "dashboard"
  | "company-search"
  | "company-workspace"
  | "investment-tools"
  | "parameter-config"
  | "data-management";

type ApiState =
  | { status: "checking"; label: "API 检查中" }
  | { status: "online"; label: string }
  | { status: "offline"; label: "API 未连接" };

type ShutdownState = "idle" | "requesting" | "accepted" | "stopped" | "timeout";

const SHUTDOWN_POLL_INTERVAL_MS = 300;
const SHUTDOWN_MAX_WAIT_MS = 12_000;

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
  "investment-tools": { view: "investment-tools" },
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
  },
  "investment-tools": {
    eyebrow: "Independent Tools · 015",
    title: "投资小工具"
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
  const [shutdownDialogOpen, setShutdownDialogOpen] = useState(false);
  const [shutdownState, setShutdownState] = useState<ShutdownState>("idle");
  const [shutdownError, setShutdownError] = useState<string | null>(null);

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

  useEffect(() => {
    if (shutdownState !== "accepted") {
      return;
    }

    let cancelled = false;
    let pollTimer: number | undefined;
    const deadline = Date.now() + SHUTDOWN_MAX_WAIT_MS;

    async function pollUntilStopped() {
      try {
        await getHealth();
        if (cancelled) return;
        if (Date.now() >= deadline) {
          setShutdownState("timeout");
          return;
        }
        pollTimer = window.setTimeout(pollUntilStopped, SHUTDOWN_POLL_INTERVAL_MS);
      } catch {
        if (!cancelled) {
          setShutdownState("stopped");
        }
      }
    }

    pollTimer = window.setTimeout(pollUntilStopped, SHUTDOWN_POLL_INTERVAL_MS);
    return () => {
      cancelled = true;
      if (pollTimer !== undefined) {
        window.clearTimeout(pollTimer);
      }
    };
  }, [shutdownState]);

  useEffect(() => {
    if (shutdownState !== "stopped") {
      return;
    }
    const closeTimer = window.setTimeout(() => window.close(), 400);
    return () => window.clearTimeout(closeTimer);
  }, [shutdownState]);

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

  async function shutDownLocalServices() {
    setShutdownState("requesting");
    setShutdownError(null);
    try {
      await requestLocalShutdown();
      setShutdownDialogOpen(false);
      setShutdownState("accepted");
    } catch (error) {
      setShutdownState("idle");
      setShutdownError(error instanceof Error ? error.message : "关闭请求失败，请使用停止脚本。");
    }
  }

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

        {health?.local_control_enabled ? (
          <div className="sidebar-local-control">
            <span>本地服务</span>
            <button
              className="sidebar-power-button"
              type="button"
              title="关闭前后端服务"
              aria-label="关闭前后端服务"
              onClick={() => {
                setShutdownError(null);
                setShutdownDialogOpen(true);
              }}
            >
              <Power aria-hidden="true" size={18} />
            </button>
          </div>
        ) : null}
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
        {activeView === "investment-tools" ? (
          <InvestmentToolsView refreshToken={refreshToken} />
        ) : null}
        {activeView === "parameter-config" ? (
          <ParameterConfigView refreshToken={refreshToken} />
        ) : null}
      </main>

      {shutdownDialogOpen ? (
        <div className="shutdown-dialog-backdrop" role="presentation">
          <section
            className="shutdown-dialog"
            role="dialog"
            aria-modal="true"
            aria-labelledby="shutdown-dialog-title"
          >
            <div className="shutdown-dialog__heading">
              <Power aria-hidden="true" size={21} />
              <div>
                <h2 id="shutdown-dialog-title">关闭本地服务</h2>
                <p>将停止前端和后端，当前页面随后不可访问。</p>
              </div>
            </div>
            <p className="shutdown-dialog__notice">未保存的浏览器输入会丢失。</p>
            {shutdownError ? (
              <p className="shutdown-dialog__error" role="alert">
                {shutdownError}
              </p>
            ) : null}
            <div className="shutdown-dialog__actions">
              <button
                type="button"
                onClick={() => setShutdownDialogOpen(false)}
                disabled={shutdownState === "requesting"}
              >
                取消
              </button>
              <button
                className="shutdown-dialog__confirm"
                type="button"
                onClick={shutDownLocalServices}
                disabled={shutdownState === "requesting"}
              >
                <Power aria-hidden="true" size={16} />
                {shutdownState === "requesting" ? "正在提交" : "关闭服务"}
              </button>
            </div>
          </section>
        </div>
      ) : null}

      {shutdownState === "accepted" ? (
        <div className="shutdown-progress shutdown-progress--waiting" role="status" aria-live="assertive">
          <Power aria-hidden="true" size={30} />
          <h2>正在关闭前后端</h2>
          <p>正在等待本地服务退出。</p>
        </div>
      ) : null}

      {shutdownState === "stopped" ? (
        <div className="shutdown-progress shutdown-progress--stopped" role="status" aria-live="assertive">
          <CheckCircle2 aria-hidden="true" size={30} />
          <h2>前后端已关闭</h2>
          <p>正在尝试关闭此页面；浏览器若保留标签页，可点击下方按钮。</p>
          <button type="button" onClick={() => window.close()}>关闭页面</button>
        </div>
      ) : null}

      {shutdownState === "timeout" ? (
        <div className="shutdown-progress shutdown-progress--timeout" role="alert">
          <AlertTriangle aria-hidden="true" size={30} />
          <h2>关闭未完成</h2>
          <p>本地服务仍可访问，请重新尝试或运行 scripts/stop-app.ps1。</p>
          <button type="button" onClick={() => setShutdownState("idle")}>返回工作台</button>
        </div>
      ) : null}
    </div>
  );
}
