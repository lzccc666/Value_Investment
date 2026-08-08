import { ArrowLeft, BarChart3, BookOpenText, Building2, FileText } from "lucide-react";
import { useEffect, useState } from "react";

import { getCompany, type Company } from "../services/api";

type CompanyWorkspaceViewProps = {
  companyId: number | null;
  onBackToSearch: () => void;
  refreshToken: number;
};

type CompanyDetailState =
  | { status: "idle"; company: null; error: null }
  | { status: "loading"; company: null; error: null }
  | { status: "ready"; company: Company; error: null }
  | { status: "error"; company: null; error: string };

export function CompanyWorkspaceView({
  companyId,
  onBackToSearch,
  refreshToken
}: CompanyWorkspaceViewProps) {
  const [detailState, setDetailState] = useState<CompanyDetailState>({
    status: "idle",
    company: null,
    error: null
  });

  useEffect(() => {
    if (companyId === null) {
      setDetailState({ status: "idle", company: null, error: null });
      return;
    }

    const controller = new AbortController();
    setDetailState({ status: "loading", company: null, error: null });

    getCompany(companyId, controller.signal)
      .then((company) => {
        setDetailState({ status: "ready", company, error: null });
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) {
          return;
        }

        setDetailState({
          status: "error",
          company: null,
          error: error instanceof Error ? error.message : "公司档案加载失败"
        });
      });

    return () => {
      controller.abort();
    };
  }, [companyId, refreshToken]);

  if (companyId === null || detailState.status === "idle") {
    return (
      <section className="empty-workspace" aria-labelledby="empty-company-workspace-heading">
        <Building2 aria-hidden="true" size={32} />
        <h2 id="empty-company-workspace-heading">公司档案</h2>
        <p>先在公司搜索页选择一家企业，再进入单家公司研究工作台。</p>
        <button className="primary-action" type="button" onClick={onBackToSearch}>
          打开公司搜索
        </button>
      </section>
    );
  }

  if (detailState.status === "loading") {
    return <WorkspaceNotice title="正在加载公司档案" description="公司基础资料正在同步。" />;
  }

  if (detailState.status === "error") {
    return (
      <WorkspaceNotice
        title="公司档案加载失败"
        description={detailState.error}
        actionLabel="返回搜索"
        onAction={onBackToSearch}
        tone="error"
      />
    );
  }

  const { company } = detailState;

  return (
    <section className="company-workspace-view" aria-labelledby="company-workspace-heading">
      <button className="back-button" type="button" onClick={onBackToSearch}>
        <ArrowLeft aria-hidden="true" size={16} />
        <span>返回搜索</span>
      </button>

      <div className="company-profile-hero">
        <div className="company-identity">
          <div className="company-identity__mark">
            <Building2 aria-hidden="true" size={24} />
          </div>
          <div>
            <span className="eyebrow">Company Workspace</span>
            <h2 id="company-workspace-heading">{company.name}</h2>
            <div className="company-meta company-meta--hero">
              <span>{company.exchange}</span>
              <span>{company.ticker}</span>
              <span>{company.industry ?? "未分类行业"}</span>
              <span>{company.status}</span>
            </div>
          </div>
        </div>

        <div className="company-tag-panel" aria-label="公司标签">
          {company.tags.length > 0 ? (
            company.tags.map((tag) => <span key={tag}>{tag}</span>)
          ) : (
            <span>暂无标签</span>
          )}
        </div>
      </div>

      <section className="profile-summary" aria-label="公司简介">
        <h3>基础档案</h3>
        <p>{company.description ?? "暂无公司简介，后续可从公告、年报或手动录入补充。"}</p>
        <dl className="profile-facts">
          <div>
            <dt>上市日期</dt>
            <dd>{company.listed_date ?? "待补充"}</dd>
          </div>
          <div>
            <dt>研究状态</dt>
            <dd>{company.status}</dd>
          </div>
          <div>
            <dt>档案更新时间</dt>
            <dd>{formatDateTime(company.updated_at)}</dd>
          </div>
        </dl>
      </section>

      <div className="workspace-module-grid" aria-label="公司研究入口">
        <WorkspaceModule
          icon={BarChart3}
          title="财务指标"
          description="接入 005 后展示报表、ROE、现金流质量和趋势图。"
        />
        <WorkspaceModule
          icon={FileText}
          title="公告与证据"
          description="接入 006 后聚合公告摘要、风险提示和事实出处。"
        />
        <WorkspaceModule
          icon={BookOpenText}
          title="投资假设"
          description="沉淀买入逻辑、反证条件、观察指标和复盘记录。"
        />
      </div>
    </section>
  );
}

type WorkspaceModuleProps = {
  icon: typeof BarChart3;
  title: string;
  description: string;
};

function WorkspaceModule({ icon: Icon, title, description }: WorkspaceModuleProps) {
  return (
    <section className="workspace-module">
      <Icon aria-hidden="true" size={22} />
      <h3>{title}</h3>
      <p>{description}</p>
    </section>
  );
}

type WorkspaceNoticeProps = {
  title: string;
  description: string;
  actionLabel?: string;
  onAction?: () => void;
  tone?: "default" | "error";
};

function WorkspaceNotice({
  title,
  description,
  actionLabel,
  onAction,
  tone = "default"
}: WorkspaceNoticeProps) {
  return (
    <section className={tone === "error" ? "empty-workspace empty-workspace--error" : "empty-workspace"}>
      <h2>{title}</h2>
      <p>{description}</p>
      {actionLabel && onAction ? (
        <button className="primary-action" type="button" onClick={onAction}>
          {actionLabel}
        </button>
      ) : null}
    </section>
  );
}

function formatDateTime(value: string): string {
  return new Intl.DateTimeFormat("zh-CN", {
    dateStyle: "medium",
    timeStyle: "short"
  }).format(new Date(value));
}
