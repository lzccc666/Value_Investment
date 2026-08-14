import { ArrowRight, Building2, Plus, Search } from "lucide-react";
import { type FormEvent, useEffect, useMemo, useState } from "react";
import { ChevronLeft, ChevronRight } from "lucide-react";

import {
  createCompany,
  getCompanies,
  type Company,
  type CompanyListResponse,
  type NewCompanyPayload
} from "../services/api";

type CompanySearchViewProps = {
  selectedCompanyId: number | null;
  onSelectCompany: (companyId: number) => void;
  refreshToken: number;
};

type CompaniesState =
  | { status: "loading"; data: null; error: null }
  | { status: "ready"; data: CompanyListResponse; error: null }
  | { status: "error"; data: null; error: string };

type NewCompanyForm = {
  ticker: string;
  exchange: string;
  name: string;
  industry: string;
  description: string;
  listedDate: string;
  status: string;
  tags: string;
};

type CreateState =
  | { status: "idle"; message: null }
  | { status: "saving"; message: null }
  | { status: "error"; message: string };

const COMPANY_LIST_PAGE_SIZE = 20;

const defaultCompaniesState: CompaniesState = {
  status: "loading",
  data: null,
  error: null
};

const defaultNewCompanyForm: NewCompanyForm = {
  ticker: "",
  exchange: "",
  name: "",
  industry: "",
  description: "",
  listedDate: "",
  status: "未研究",
  tags: ""
};

export function CompanySearchView({
  selectedCompanyId,
  onSelectCompany,
  refreshToken
}: CompanySearchViewProps) {
  const [query, setQuery] = useState("");
  const [companiesState, setCompaniesState] = useState<CompaniesState>(defaultCompaniesState);
  const [newCompanyForm, setNewCompanyForm] = useState<NewCompanyForm>(defaultNewCompanyForm);
  const [createState, setCreateState] = useState<CreateState>({ status: "idle", message: null });
  const [localRefreshToken, setLocalRefreshToken] = useState(0);
  const [offset, setOffset] = useState(0);
  const normalizedQuery = query.trim();

  useEffect(() => {
    const controller = new AbortController();
    setCompaniesState(defaultCompaniesState);

    getCompanies({
      q: normalizedQuery || undefined,
      limit: COMPANY_LIST_PAGE_SIZE,
      offset,
      signal: controller.signal
    })
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
  }, [normalizedQuery, offset, refreshToken, localRefreshToken]);

  const summary = useMemo(() => {
    if (companiesState.status !== "ready") {
      return "正在读取公司池";
    }

    const pageStart = companiesState.data.total === 0 ? 0 : companiesState.data.offset + 1;
    const pageEnd = companiesState.data.offset + companiesState.data.items.length;

    if (normalizedQuery) {
      return `匹配 ${companiesState.data.total} 家公司，第 ${pageStart}-${pageEnd} 家`;
    }

    return `公司池共 ${companiesState.data.total} 家，第 ${pageStart}-${pageEnd} 家`;
  }, [companiesState, normalizedQuery]);

  const companies = companiesState.status === "ready" ? companiesState.data.items : [];
  const pagination = companiesState.status === "ready" ? companiesState.data : null;
  const hasPreviousPage = pagination !== null && pagination.offset > 0;
  const hasNextPage =
    pagination !== null && pagination.offset + pagination.items.length < pagination.total;

  function updateNewCompanyField(field: keyof NewCompanyForm, value: string) {
    setNewCompanyForm((current) => ({ ...current, [field]: value }));
  }

  function handleSearchChange(value: string) {
    setQuery(value);
    setOffset(0);
  }

  function handlePreviousPage() {
    setOffset((currentOffset) => Math.max(0, currentOffset - COMPANY_LIST_PAGE_SIZE));
  }

  function handleNextPage() {
    setOffset((currentOffset) => currentOffset + COMPANY_LIST_PAGE_SIZE);
  }

  async function handleCreateCompany(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setCreateState({ status: "saving", message: null });

    try {
      const company = await createCompany(toNewCompanyPayload(newCompanyForm));
      setCreateState({ status: "idle", message: null });
      setNewCompanyForm(defaultNewCompanyForm);
      setLocalRefreshToken((value) => value + 1);
      onSelectCompany(company.id);
    } catch (error) {
      setCreateState({
        status: "error",
        message: error instanceof Error ? error.message : "新增公司失败"
      });
    }
  }

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
            onChange={(event) => handleSearchChange(event.target.value)}
            placeholder="输入代码、名称、交易所、行业或标签"
          />
        </label>
      </div>

      {!selectedCompanyId ? (
        <NewCompanyPanel
          form={newCompanyForm}
          createState={createState}
          onChange={updateNewCompanyField}
          onSubmit={handleCreateCompany}
        />
      ) : null}

      {companiesState.status === "loading" ? (
        <StateNotice title="正在加载" description="公司列表正在同步。" />
      ) : null}

      {companiesState.status === "error" ? (
        <StateNotice title="加载失败" description={companiesState.error} tone="error" />
      ) : null}

      {companiesState.status === "ready" && companies.length === 0 ? (
        <StateNotice title="没有匹配结果" description="当前关键词没有匹配公司，可以直接在上方新增。" />
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

      {pagination !== null && pagination.total > COMPANY_LIST_PAGE_SIZE ? (
        <nav className="company-pagination" aria-label="公司列表分页">
          <button
            className="pagination-button"
            type="button"
            onClick={handlePreviousPage}
            disabled={!hasPreviousPage || companiesState.status === "loading"}
          >
            <ChevronLeft aria-hidden="true" size={16} />
            <span>上一页</span>
          </button>
          <span className="pagination-status">
            {pagination.offset + 1}-{pagination.offset + companies.length} / {pagination.total}
          </span>
          <button
            className="pagination-button"
            type="button"
            onClick={handleNextPage}
            disabled={!hasNextPage || companiesState.status === "loading"}
          >
            <span>下一页</span>
            <ChevronRight aria-hidden="true" size={16} />
          </button>
        </nav>
      ) : null}
    </section>
  );
}

type NewCompanyPanelProps = {
  form: NewCompanyForm;
  createState: CreateState;
  onChange: (field: keyof NewCompanyForm, value: string) => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
};

function NewCompanyPanel({ form, createState, onChange, onSubmit }: NewCompanyPanelProps) {
  const isSaving = createState.status === "saving";

  return (
    <section className="new-company-panel" aria-labelledby="new-company-heading">
      <div className="new-company-heading">
        <div>
          <Plus aria-hidden="true" size={20} />
          <h3 id="new-company-heading">新增公司</h3>
        </div>
        <span>本地主数据</span>
      </div>

      <form className="new-company-form" onSubmit={onSubmit}>
        <FormField
          id="new-company-ticker"
          label="证券代码"
          value={form.ticker}
          onChange={(value) => onChange("ticker", value)}
          required
          placeholder="600519.SH"
          description="必填。建议使用带市场后缀的唯一代码，如 600519.SH、00700.HK、AAPL.US。"
        />
        <FormField
          id="new-company-exchange"
          label="交易所"
          value={form.exchange}
          onChange={(value) => onChange("exchange", value)}
          required
          placeholder="SSE"
          description="必填。例如 SSE、SZSE、HKEX、NASDAQ、NYSE。用于和证券代码一起去重。"
        />
        <FormField
          id="new-company-name"
          label="公司名称"
          value={form.name}
          onChange={(value) => onChange("name", value)}
          required
          placeholder="贵州茅台"
          description="必填。公司正式名称或你习惯使用的研究名称。"
        />
        <FormField
          id="new-company-industry"
          label="所属行业"
          value={form.industry}
          onChange={(value) => onChange("industry", value)}
          placeholder="白酒"
          description="可选。用于后续筛选、对比和研究分组。"
        />
        <FormField
          id="new-company-listed-date"
          label="上市日期"
          type="date"
          value={form.listedDate}
          onChange={(value) => onChange("listedDate", value)}
          description="可选。格式为 YYYY-MM-DD；留空时系统会在公司档案页尝试自动补齐。"
        />
        <FormField
          id="new-company-status"
          label="研究状态"
          value={form.status}
          onChange={(value) => onChange("status", value)}
          placeholder="未研究"
          description="可选。建议使用 未研究、观察中、重点跟踪、持仓、已放弃。"
        />
        <FormField
          id="new-company-tags"
          label="标签"
          value={form.tags}
          onChange={(value) => onChange("tags", value)}
          placeholder="A股, 白酒, 消费"
          description="可选。用逗号、顿号或分号分隔，标签会参与搜索。"
        />
        <div className="form-field form-field--wide">
          <label htmlFor="new-company-description">公司简介</label>
          <textarea
            id="new-company-description"
            aria-describedby="new-company-description-help"
            value={form.description}
            onChange={(event) => onChange("description", event.target.value)}
            placeholder="写一句业务范围或研究备注"
            rows={3}
          />
          <small id="new-company-description-help">可选。用于进入公司档案时快速理解研究对象。</small>
        </div>

        {createState.status === "error" ? (
          <div className="form-error" role="alert">
            {createState.message}
          </div>
        ) : null}

        <div className="new-company-actions">
          <button className="primary-action" type="submit" disabled={isSaving}>
            <Plus aria-hidden="true" size={16} />
            <span>{isSaving ? "保存中" : "保存并进入档案"}</span>
          </button>
        </div>
      </form>
    </section>
  );
}

type FormFieldProps = {
  id: string;
  label: string;
  value: string;
  onChange: (value: string) => void;
  description: string;
  placeholder?: string;
  required?: boolean;
  type?: "text" | "date";
};

function FormField({
  id,
  label,
  value,
  onChange,
  description,
  placeholder,
  required = false,
  type = "text"
}: FormFieldProps) {
  return (
    <div className="form-field">
      <label htmlFor={id}>
        {label}
        {required ? <em>必填</em> : null}
      </label>
      <input
        id={id}
        aria-describedby={`${id}-help`}
        type={type}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder={placeholder}
        required={required}
      />
      <small id={`${id}-help`}>{description}</small>
    </div>
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

function toNewCompanyPayload(form: NewCompanyForm): NewCompanyPayload {
  return {
    ticker: form.ticker,
    exchange: form.exchange,
    name: form.name,
    industry: blankToNull(form.industry),
    description: blankToNull(form.description),
    listed_date: blankToNull(form.listedDate),
    status: form.status.trim() || "未研究",
    tags: parseTags(form.tags)
  };
}

function parseTags(value: string): string[] {
  return value
    .split(/[,，;；、]/)
    .map((tag) => tag.trim())
    .filter((tag, index, tags) => tag.length > 0 && tags.indexOf(tag) === index);
}

function blankToNull(value: string): string | null {
  const normalized = value.trim();
  return normalized || null;
}
