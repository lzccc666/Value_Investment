import { ArrowRight, Check, Search } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { MetricTile } from "../components/MetricTile";
import { getCompanies, type Company, type CompanyListResponse } from "../services/api";
import type { CompanyWorkspaceSection } from "./CompanyWorkspaceView";
import { researchModules, type Metric } from "./dashboardData";

type DashboardViewProps = {
  selectedCompany: Company | null;
  refreshToken: number;
  onOpenSearch: () => void;
  onOpenCompany: (company: Company) => void;
  onOpenSection: (section: CompanyWorkspaceSection) => void;
};

type CompanyPoolState =
  | { status: "loading"; data: null }
  | { status: "ready"; data: CompanyListResponse }
  | { status: "error"; data: null };

export function DashboardView({
  selectedCompany,
  refreshToken,
  onOpenSearch,
  onOpenCompany,
  onOpenSection
}: DashboardViewProps) {
  const [companyPool, setCompanyPool] = useState<CompanyPoolState>({
    status: "loading",
    data: null
  });

  useEffect(() => {
    const controller = new AbortController();
    setCompanyPool({ status: "loading", data: null });

    getCompanies({ limit: 6, offset: 0, signal: controller.signal })
      .then((data) => setCompanyPool({ status: "ready", data }))
      .catch((error: unknown) => {
        if (!(error instanceof DOMException && error.name === "AbortError")) {
          setCompanyPool({ status: "error", data: null });
        }
      });

    return () => controller.abort();
  }, [refreshToken]);

  const metrics = useMemo<Metric[]>(
    () => [
      {
        label: "研究公司",
        value:
          companyPool.status === "ready"
            ? String(companyPool.data.total)
            : companyPool.status === "error"
              ? "--"
              : "...",
        trend: companyPool.status === "error" ? "公司池读取失败" : "本地公司池",
        tone: "green"
      },
      {
        label: "当前研究对象",
        value: selectedCompany ? `${selectedCompany.name} ${selectedCompany.ticker}` : "未选择",
        trend: selectedCompany ? "已选择" : "先选择一家公司",
        tone: "blue",
        valueStyle: selectedCompany ? "compact" : "standard"
      },
      {
        label: "研究主链路",
        value: "8 / 8",
        trend: "004-011 已接通",
        tone: "amber"
      }
    ],
    [companyPool, selectedCompany]
  );

  const recentCompanies = companyPool.status === "ready" ? companyPool.data.items : [];

  return (
    <div className="dashboard-view">
      <section className="metric-grid" aria-label="研究概览">
        {metrics.map((metric) => (
          <MetricTile key={metric.label} metric={metric} />
        ))}
      </section>

      <section className="dashboard-section research-flow" aria-labelledby="research-flow-heading">
        <div className="dashboard-section__heading">
          <div>
            <span className="eyebrow">Research Flow</span>
            <h2 id="research-flow-heading">研究主链路</h2>
          </div>
          <span className="module-status module-status--online">
            <Check aria-hidden="true" size={14} />
            8 / 8 已接通
          </span>
        </div>

        <div className="research-flow__list">
          {researchModules.map((module, index) => {
            const Icon = module.icon;
            const disabled = !selectedCompany;

            return (
              <button
                className="research-flow__item"
                type="button"
                key={module.code}
                disabled={disabled}
                title={disabled ? "请先选择研究公司" : `进入${module.name}`}
                onClick={() => onOpenSection(module.section)}
              >
                <span className="research-flow__index">{String(index + 1).padStart(2, "0")}</span>
                <span className="research-flow__icon">
                  <Icon aria-hidden="true" size={19} />
                </span>
                <span className="research-flow__content">
                  <strong>{module.name}</strong>
                  <small>{module.description}</small>
                </span>
                <span className="research-flow__code">{module.code}</span>
                <ArrowRight aria-hidden="true" size={17} />
              </button>
            );
          })}
        </div>

        {!selectedCompany ? (
          <button className="dashboard-primary-action" type="button" onClick={onOpenSearch}>
            <Search aria-hidden="true" size={17} />
            选择研究公司
          </button>
        ) : null}
      </section>

      <section className="dashboard-section" aria-labelledby="recent-companies-heading">
        <div className="dashboard-section__heading">
          <div>
            <span className="eyebrow">Company Pool</span>
            <h2 id="recent-companies-heading">最近公司</h2>
          </div>
          <button className="text-action" type="button" onClick={onOpenSearch}>
            查看全部
            <ArrowRight aria-hidden="true" size={15} />
          </button>
        </div>

        {companyPool.status === "loading" ? (
          <div className="dashboard-empty">正在读取公司池</div>
        ) : null}
        {companyPool.status === "error" ? (
          <div className="dashboard-empty dashboard-empty--error">公司池读取失败</div>
        ) : null}
        {companyPool.status === "ready" && recentCompanies.length === 0 ? (
          <div className="dashboard-empty">公司池为空</div>
        ) : null}
        {recentCompanies.length > 0 ? (
          <div className="recent-company-list">
            {recentCompanies.map((company) => (
              <button
                className={
                  selectedCompany?.id === company.id
                    ? "recent-company-row recent-company-row--selected"
                    : "recent-company-row"
                }
                type="button"
                key={company.id}
                aria-label={`打开${company.name}公司档案`}
                onClick={() => onOpenCompany(company)}
              >
                <span className="recent-company-row__identity">
                  <strong>{company.name}</strong>
                  <small>{company.ticker}</small>
                </span>
                <span>{company.industry ?? "行业待补"}</span>
                <ArrowRight aria-hidden="true" size={16} />
              </button>
            ))}
          </div>
        ) : null}
      </section>
    </div>
  );
}
