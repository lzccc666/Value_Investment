import { ArrowRight, Building2, Search } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { getCompanies, type Company, type CompanyListResponse } from "../services/api";

type CompanySearchViewProps = {
  selectedCompanyId: number | null;
  onSelectCompany: (companyId: number) => void;
  refreshToken: number;
};

type CompaniesState =
  | { status: "loading"; data: null; error: null }
  | { status: "ready"; data: CompanyListResponse; error: null }
  | { status: "error"; data: null; error: string };

const defaultCompaniesState: CompaniesState = {
  status: "loading",
  data: null,
  error: null
};

export function CompanySearchView({
  selectedCompanyId,
  onSelectCompany,
  refreshToken
}: CompanySearchViewProps) {
  const [query, setQuery] = useState("");
  const [companiesState, setCompaniesState] = useState<CompaniesState>(defaultCompaniesState);
  const normalizedQuery = query.trim();

  useEffect(() => {
    const controller = new AbortController();
    setCompaniesState(defaultCompaniesState);

    getCompanies({ q: normalizedQuery || undefined, limit: 20, offset: 0, signal: controller.signal })
      .then((data) => {
        setCompaniesState({ status: "ready", data, error: null });
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) {
          return;
        }

        setCompaniesState({
          status: "error",
          data: null,
          error: error instanceof Error ? error.message : "公司列表加载失败"
        });
      });

    return () => {
      controller.abort();
    };
  }, [normalizedQuery, refreshToken]);

  const summary = useMemo(() => {
    if (companiesState.status !== "ready") {
      return "正在读取公司池";
    }

    if (normalizedQuery) {
      return `匹配 ${companiesState.data.total} 家公司`;
    }

    return `公司池共 ${companiesState.data.total} 家`;
  }, [companiesState, normalizedQuery]);

  const companies = companiesState.status === "ready" ? companiesState.data.items : [];

  return (
    <section className="company-search-view" aria-labelledby="company-search-heading">
      <div className="section-header">
        <div>
          <span className="eyebrow">Company Search</span>
          <h2 id="company-search-heading">公司搜索</h2>
        </div>
        <span className="result-count">{summary}</span>
      </div>

      <div className="search-toolbar">
        <label className="search-box">
          <Search aria-hidden="true" size={18} />
          <span className="sr-only">搜索公司</span>
          <input
            type="search"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="输入代码、名称、交易所或行业"
          />
        </label>
      </div>

      {companiesState.status === "loading" ? (
        <StateNotice title="正在加载" description="公司列表正在同步。" />
      ) : null}

      {companiesState.status === "error" ? (
        <StateNotice title="加载失败" description={companiesState.error} tone="error" />
      ) : null}

      {companiesState.status === "ready" && companies.length === 0 ? (
        <StateNotice title="没有匹配结果" description="当前关键词没有匹配公司。" />
      ) : null}

      {companies.length > 0 ? (
        <div className="company-list" role="list" aria-label="公司列表">
          {companies.map((company) => (
            <CompanyRow
              key={`${company.exchange}-${company.ticker}`}
              company={company}
              selected={company.id === selectedCompanyId}
              onSelectCompany={onSelectCompany}
            />
          ))}
        </div>
      ) : null}
    </section>
  );
}

type CompanyRowProps = {
  company: Company;
  selected: boolean;
  onSelectCompany: (companyId: number) => void;
};

function CompanyRow({ company, selected, onSelectCompany }: CompanyRowProps) {
  return (
    <article className={selected ? "company-row company-row--selected" : "company-row"} role="listitem">
      <div className="company-row__mark">
        <Building2 aria-hidden="true" size={20} />
      </div>
      <div className="company-row__main">
        <div className="company-row__title">
          <h3>{company.name}</h3>
          <span>{company.ticker}</span>
        </div>
        <p>{company.description ?? "暂无公司简介"}</p>
        <div className="company-meta">
          <span>{company.exchange}</span>
          <span>{company.industry ?? "未分类行业"}</span>
          <span>{company.status}</span>
          {company.listed_date ? <span>上市 {company.listed_date}</span> : null}
        </div>
      </div>
      <div className="company-tags" aria-label={`${company.name} 标签`}>
        {company.tags.map((tag) => (
          <span key={tag}>{tag}</span>
        ))}
      </div>
      <button
        className="company-detail-button"
        type="button"
        onClick={() => onSelectCompany(company.id)}
        title="进入公司档案"
      >
        <span>档案</span>
        <ArrowRight aria-hidden="true" size={16} />
      </button>
    </article>
  );
}

type StateNoticeProps = {
  title: string;
  description: string;
  tone?: "default" | "error";
};

function StateNotice({ title, description, tone = "default" }: StateNoticeProps) {
  return (
    <div className={tone === "error" ? "state-notice state-notice--error" : "state-notice"}>
      <strong>{title}</strong>
      <span>{description}</span>
    </div>
  );
}
