import {
  Archive,
  ArrowLeft,
  BarChart3,
  BrainCircuit,
  Building2,
  Calculator,
  ChevronDown,
  ChevronRight,
  FileText,
  PlayCircle,
  RefreshCw,
  Save,
  Scale,
  Search,
  ShieldCheck,
  SlidersHorizontal,
  Square,
  Trash2
} from "lucide-react";
import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type Dispatch,
  type FormEvent,
  type SetStateAction
} from "react";

import {
  getCompany,
  getAnalystProfiles,
  getLatestCompanyAnalysisRuns,
  getCompanyAnnouncements,
  getCompanyEvidence,
  getCompanyFinancialEvidencePack,
  getCompanyFinancials,
  getEvidenceModelConfig,
  getAnnouncementDisplayStatus,
  deleteCompanyAnnouncement,
  deleteCompanyFinancialStatement,
  deleteEvidence,
  deleteCompanyAnalysisRun,
  deleteInvestmentMemo,
  deletePriceDecisionRun,
  archiveInvestmentMemo,
  createPriceDecisionRun,
  createValuationDraft,
  generateInvestmentMemo,
  refreshCompanyProfile,
  getInvestmentMemos,
  getLatestInvestmentMemo,
  getLatestValuationRun,
  getValuationRuns,
  getLatestPriceDecisionRun,
  getPriceDecisionRuns,
  importTextEvidence,
  runEvidenceModelSmokeTest,
  recalculateValuationRun,
  runCompanyAnalysis,
  runCompanyAnalysisBatch,
  searchCompanyEvidence,
  summarizeCompanyAnnouncement,
  summarizeCompanyAnnouncements,
  summarizeCompanyAnnouncementsDeep,
  syncCompanyAnnouncements,
  syncCompanyFinancials,
  updateAnalysisRunRuleStatus,
  type AnalysisBatchRunResponse,
  type AnalysisRun,
  type AnalysisRunListResponse,
  type AnalystRuleStatus,
  type AnalystProfileListResponse,
  type Announcement,
  type AnnouncementListResponse,
  type Company,
  type EvidenceSearchResponse,
  type EvidenceSourceType,
  type EvidenceListResponse,
  type FinancialEvidencePack,
  type FinancialStatement,
  type FinancialStatementListResponse,
  type InvestmentMemo,
  type InvestmentMemoLatestResponse,
  type InvestmentMemoListResponse,
  type ModelConfigStatus,
  type PriceDecisionListResponse,
  type PriceDecisionRun,
  type PriceDecisionLatestResponse,
  type ValuationRun,
  type ValuationRunLatestResponse,
  type ValuationRunListResponse
} from "../services/api";
import { matrixParameterLabel } from "./parameterConfigLabels";

type CompanyWorkspaceViewProps = {
  companyId: number | null;
  activeSection: CompanyWorkspaceSection;
  onSectionChange: (section: CompanyWorkspaceSection) => void;
  onBackToSearch: () => void;
  onCompanyUnavailable: () => void;
  refreshToken: number;
};

export type CompanyWorkspaceSection =
  | "overview"
  | "financials"
  | "announcements"
  | "evidence"
  | "analyst-views"
  | "valuation-lab"
  | "price-decision"
  | "memo";

type CompanyWorkspaceData = {
  company: Company;
  financials: FinancialStatementListResponse;
  financialEvidencePack: FinancialEvidencePack;
  announcements: AnnouncementListResponse;
  evidence: EvidenceListResponse;
  modelConfig: ModelConfigStatus;
  analystProfiles: AnalystProfileListResponse;
  analysisRuns: AnalysisRunListResponse;
  failedAnalysisRuns: AnalysisRunListResponse;
  latestMemo: InvestmentMemoLatestResponse;
  memoHistory: InvestmentMemoListResponse;
  latestValuationRun: ValuationRunLatestResponse;
  valuationHistory: ValuationRunListResponse;
  latestPriceDecision: PriceDecisionLatestResponse;
  priceDecisionHistory: PriceDecisionListResponse;
};

type CompanyDetailState =
  | { status: "idle"; data: null; error: null }
  | { status: "loading"; data: null; error: null }
  | { status: "ready"; data: CompanyWorkspaceData; error: null }
  | { status: "error"; data: null; error: string };

type ModelSmokeTestState = {
  status: "idle" | "testing" | "success" | "error";
  message: string | null;
};

type EvidenceDeleteState = {
  status: "idle" | "deleting" | "success" | "error";
  evidenceId: number | null;
  message: string | null;
};

type FinancialDeleteState = {
  status: "idle" | "deleting" | "success" | "error";
  statementId: number | null;
  message: string | null;
};

type AnalysisRunDeleteState = {
  status: "idle" | "deleting" | "success" | "error";
  runId: number | null;
  message: string | null;
};

type AnalysisRuleStatusUpdateState = {
  status: "idle" | "saving" | "success" | "error";
  runId: number | null;
  ruleId: string | null;
  message: string | null;
};

type MemoGenerateState = {
  status: "idle" | "generating" | "success" | "error";
  message: string | null;
};

type MemoDeleteState = {
  status: "idle" | "deleting" | "success" | "error";
  memoId: number | null;
  message: string | null;
};

type MemoArchiveState = {
  status: "idle" | "archiving" | "success" | "error";
  memoId: number | null;
  message: string | null;
};

type ValuationActionState = {
  status: "idle" | "saving" | "success" | "error";
  message: string | null;
};

type PriceDecisionActionState = {
  status: "idle" | "saving" | "success" | "error";
  message: string | null;
};

type PriceDecisionDeleteState = {
  status: "idle" | "deleting" | "success" | "error";
  runId: number | null;
  message: string | null;
};

type ProfileRefreshState =
  | { status: "idle"; message: null }
  | { status: "refreshing"; message: string }
  | { status: "success"; message: string }
  | { status: "error"; message: string };

const statementTypeLabels: Record<string, string> = {
  income_statement: "利润表",
  balance_sheet: "资产负债表",
  cash_flow_statement: "现金流量表",
  main_financial_indicators: "主要财务指标",
  shareholder_return: "股东回报",
  capital_structure: "资本结构"
};

const financialStatementTypeDisplayOrder = [
  "main_financial_indicators",
  "income_statement",
  "cash_flow_statement",
  "balance_sheet"
];

const fieldLabels: Record<string, string> = {
  report_date: "报告日期",
  report_type: "报告类型",
  notice_date: "披露日期",
  revenue: "收入",
  operating_cost: "营业成本",
  gross_profit: "毛利",
  gross_margin: "毛利率",
  taxes_and_surcharges: "税金及附加",
  selling_expense: "销售费用",
  admin_expense: "管理费用",
  r_and_d_expense: "研发费用",
  finance_expense: "财务费用",
  other_income: "其他收益",
  investment_income: "投资收益",
  fair_value_change_income: "公允价值变动收益",
  credit_impairment_loss: "信用减值损失",
  asset_impairment_loss: "资产减值损失",
  operating_profit: "营业利润",
  non_operating_income: "营业外收入",
  non_operating_expense: "营业外支出",
  total_profit: "利润总额",
  income_tax_expense: "所得税费用",
  net_profit: "净利润",
  parent_net_profit: "归母净利润",
  minority_interest: "少数股东损益",
  deducted_net_profit: "扣非净利润",
  eps: "每股收益",
  bps: "每股净资产",
  roe: "净资产收益率",
  net_margin: "净利率",
  asset_liability_ratio: "资产负债率",
  revenue_yoy: "收入同比",
  net_profit_yoy: "净利润同比",
  operating_cash_flow: "经营现金流",
  purchase_fixed_assets_cash_paid: "购建长期资产支付现金",
  capital_expenditure: "资本开支",
  free_cash_flow: "自由现金流",
  depreciation_and_amortization: "折旧摊销",
  working_capital_change: "营运资本变动",
  dividend: "分红总额",
  net_cash_from_investing: "投资活动现金流净额",
  net_cash_from_financing: "筹资活动现金流净额",
  operating_cash_flow_per_share: "每股经营现金流",
  operating_cash_flow_to_revenue: "经营现金流/收入",
  cash_and_equivalents: "货币资金",
  short_term_interest_bearing_debt: "短期有息负债",
  long_term_interest_bearing_debt: "长期有息负债",
  interest_bearing_debt: "有息负债合计",
  net_cash: "净现金",
  total_assets: "总资产",
  total_liabilities: "总负债",
  shareholders_equity: "归母股东权益",
  total_equity: "股东权益合计",
  goodwill: "商誉",
  receivables: "应收款项",
  inventory: "存货",
  shares_outstanding: "总股本",
  treasury_shares: "库存股",
  buyback_amount: "回购金额",
  buyback_amount_proxy: "回购代理口径",
  dividend_payable: "应付股利",
  dividend_payout_ratio: "分红率",
  buyback_ratio: "回购率",
  share_dilution_rate: "股本稀释率",
  operating_cash_flow_to_net_profit: "经营现金流/净利润",
  free_cash_flow_to_net_profit: "自由现金流/净利润",
  free_cash_flow_margin: "自由现金流率",
  cash_to_interest_bearing_debt: "现金/有息负债",
  interest_bearing_debt_to_equity: "有息负债/股东权益",
  capital_expenditure_to_revenue: "资本开支/收入",
  total_shareholder_return: "股东回报总额",
  total_assets_turnover: "总资产周转率",
  inventory_turnover_days: "存货周转天数",
  raw_secucode: "数据源代码",
  raw_security_name: "数据源名称"
};

const sourceLabels: Record<string, string> = {
  eastmoney_f10_main_finance: "东方财富 F10 主要财务指标",
  eastmoney_f10_income_statement: "东方财富 F10 利润表",
  eastmoney_f10_cash_flow: "东方财富 F10 现金流量表",
  eastmoney_f10_balance_sheet: "东方财富 F10 资产负债表",
  fake_financial_source: "测试财务数据"
};

const financialFieldDisplayOrder = [
  "report_date",
  "report_type",
  "notice_date",
  "revenue",
  "revenue_yoy",
  "operating_cost",
  "gross_profit",
  "gross_margin",
  "taxes_and_surcharges",
  "selling_expense",
  "admin_expense",
  "r_and_d_expense",
  "finance_expense",
  "other_income",
  "investment_income",
  "fair_value_change_income",
  "credit_impairment_loss",
  "asset_impairment_loss",
  "operating_profit",
  "non_operating_income",
  "non_operating_expense",
  "total_profit",
  "income_tax_expense",
  "net_profit",
  "net_profit_yoy",
  "parent_net_profit",
  "minority_interest",
  "deducted_net_profit",
  "eps",
  "bps",
  "roe",
  "net_margin",
  "asset_liability_ratio",
  "operating_cash_flow",
  "capital_expenditure",
  "free_cash_flow",
  "depreciation_and_amortization",
  "working_capital_change",
  "operating_cash_flow_per_share",
  "operating_cash_flow_to_revenue",
  "cash_and_equivalents",
  "short_term_interest_bearing_debt",
  "long_term_interest_bearing_debt",
  "interest_bearing_debt",
  "net_cash",
  "total_assets",
  "total_liabilities",
  "shareholders_equity",
  "goodwill",
  "receivables",
  "inventory",
  "dividend",
  "dividend_payout_ratio",
  "buyback_amount",
  "buyback_amount_proxy",
  "shares_outstanding",
  "share_dilution_rate",
  "total_assets_turnover",
  "inventory_turnover_days",
  "raw_secucode",
  "raw_security_name"
];

const ANNOUNCEMENT_LOOKBACK_YEARS = 1;
const ANNOUNCEMENT_LIST_LIMIT = 50;
const ANNOUNCEMENT_SUMMARY_BATCH_LIMIT = ANNOUNCEMENT_LIST_LIMIT;
const FINANCIAL_STATEMENT_SYNC_LIMIT = 60;
const DISPLAY_TIME_ZONE = "Asia/Shanghai";
const EMPTY_FINANCIAL_EVIDENCE_PACK: FinancialEvidencePack = {
  latest_period: null,
  periods: [],
  financial_facts: {},
  financial_metrics: {},
  cash_flow_coverage: {},
  financial_trends: {},
  financial_flags: [],
  financial_data_gaps: [],
  financial_data_gap_messages: [],
  cash_flow_quality: {},
  balance_sheet_adjustment: {},
  capital_allocation: {},
  valuation_readiness: {},
  quality_matrix: {},
  analyst_summary: {},
  data_quality: {}
};
const EMPTY_MODEL_CONFIG: ModelConfigStatus = {
  provider: "unknown",
  base_url: null,
  model_name: null,
  wire_api: null,
  api_key_configured: false
};
const EMPTY_ANALYST_PROFILES: AnalystProfileListResponse = {
  items: []
};

const workspaceSections: Array<{
  id: CompanyWorkspaceSection;
  label: string;
  description: string;
}> = [
  { id: "overview", label: "Overview", description: "研究准备度" },
  { id: "financials", label: "Financials", description: "财务底稿" },
  { id: "announcements", label: "Announcements", description: "公告摘要" },
  { id: "evidence", label: "Evidence", description: "外部证据" },
  { id: "analyst-views", label: "Analyst Views", description: "多视角分析" },
  { id: "memo", label: "Memo", description: "备忘录准备" },
  { id: "valuation-lab", label: "Valuation Lab", description: "无锚定估值" },
  { id: "price-decision", label: "Price Decision", description: "价格对照与投资决策" }
];

export function CompanyWorkspaceView({
  companyId,
  activeSection,
  onSectionChange,
  onBackToSearch,
  onCompanyUnavailable,
  refreshToken
}: CompanyWorkspaceViewProps) {
  const [detailState, setDetailState] = useState<CompanyDetailState>({
    status: "idle",
    data: null,
    error: null
  });
  const [financialSyncState, setFinancialSyncState] = useState<FinancialSyncState>({
    status: "idle",
    message: null
  });
  const [financialDeleteState, setFinancialDeleteState] = useState<FinancialDeleteState>({
    status: "idle",
    statementId: null,
    message: null
  });
  const [announcementSyncState, setAnnouncementSyncState] = useState<AnnouncementSyncState>({
    status: "idle",
    message: null
  });
  const [announcementDeleteState, setAnnouncementDeleteState] = useState<AnnouncementDeleteState>({
    status: "idle",
    announcementId: null,
    message: null
  });
  const [announcementSummaryState, setAnnouncementSummaryState] =
    useState<AnnouncementSummaryState>({
      status: "idle",
      message: null
    });
  const [evidenceSearchState, setEvidenceSearchState] = useState<EvidenceSearchState>({
    status: "idle",
    message: null
  });
  const [evidenceImportTextState, setEvidenceImportTextState] =
    useState<EvidenceImportTextState>({
      status: "idle",
      message: null
    });
  const [modelSmokeTestState, setModelSmokeTestState] = useState<ModelSmokeTestState>({
    status: "idle",
    message: null
  });
  const [evidenceDeleteState, setEvidenceDeleteState] = useState<EvidenceDeleteState>({
    status: "idle",
    evidenceId: null,
    message: null
  });
  const [analystRunState, setAnalystRunState] = useState<AnalystRunState>({
    status: "idle",
    profileId: null,
    message: null
  });
  const [analysisRunDeleteState, setAnalysisRunDeleteState] = useState<AnalysisRunDeleteState>({
    status: "idle",
    runId: null,
    message: null
  });
  const [analysisRuleStatusUpdateState, setAnalysisRuleStatusUpdateState] =
    useState<AnalysisRuleStatusUpdateState>({
      status: "idle",
      runId: null,
      ruleId: null,
      message: null
    });
  const [memoGenerateState, setMemoGenerateState] = useState<MemoGenerateState>({
    status: "idle",
    message: null
  });
  const [memoDeleteState, setMemoDeleteState] = useState<MemoDeleteState>({
    status: "idle",
    memoId: null,
    message: null
  });
  const [memoArchiveState, setMemoArchiveState] = useState<MemoArchiveState>({
    status: "idle",
    memoId: null,
    message: null
  });
  const [valuationActionState, setValuationActionState] = useState<ValuationActionState>({
    status: "idle",
    message: null
  });
  const [priceDecisionActionState, setPriceDecisionActionState] =
    useState<PriceDecisionActionState>({ status: "idle", message: null });
  const [priceDecisionDeleteState, setPriceDecisionDeleteState] =
    useState<PriceDecisionDeleteState>({ status: "idle", runId: null, message: null });
  const [profileRefreshState, setProfileRefreshState] = useState<ProfileRefreshState>({
    status: "idle",
    message: null
  });
  const analystRunAbortControllerRef = useRef<AbortController | null>(null);

  useEffect(() => {
    if (companyId === null) {
      setDetailState({ status: "idle", data: null, error: null });
      return;
    }

    const controller = new AbortController();
    setDetailState({ status: "loading", data: null, error: null });
    setFinancialSyncState({ status: "idle", message: null });
    setFinancialDeleteState({ status: "idle", statementId: null, message: null });
    setAnnouncementSyncState({ status: "idle", message: null });
    setAnnouncementDeleteState({ status: "idle", announcementId: null, message: null });
    setAnnouncementSummaryState({ status: "idle", message: null });
    setEvidenceSearchState({ status: "idle", message: null });
    setEvidenceImportTextState({ status: "idle", message: null });
    setModelSmokeTestState({ status: "idle", message: null });
    setEvidenceDeleteState({ status: "idle", evidenceId: null, message: null });
    setAnalystRunState({ status: "idle", profileId: null, message: null });
    setAnalysisRunDeleteState({ status: "idle", runId: null, message: null });
    setAnalysisRuleStatusUpdateState({
      status: "idle",
      runId: null,
      ruleId: null,
      message: null
    });
    setMemoGenerateState({ status: "idle", message: null });
    setMemoDeleteState({ status: "idle", memoId: null, message: null });
    setMemoArchiveState({ status: "idle", memoId: null, message: null });
    setValuationActionState({ status: "idle", message: null });
    setPriceDecisionActionState({ status: "idle", message: null });
    setPriceDecisionDeleteState({ status: "idle", runId: null, message: null });
    setProfileRefreshState({ status: "idle", message: null });
    analystRunAbortControllerRef.current?.abort();
    analystRunAbortControllerRef.current = null;

    Promise.all([
      getCompany(companyId, controller.signal),
      withOptionalWorkspaceData(
        getCompanyFinancials(companyId, {
          period_offset: 0,
          signal: controller.signal
        }),
        {
          items: [],
          total: 0,
          limit: 0,
          offset: 0
        }
      ),
      withOptionalWorkspaceData(
        getCompanyFinancialEvidencePack(companyId, controller.signal),
        EMPTY_FINANCIAL_EVIDENCE_PACK
      ),
      withOptionalWorkspaceData(
        getCompanyAnnouncements(companyId, {
          limit: ANNOUNCEMENT_LIST_LIMIT,
          offset: 0,
          signal: controller.signal
        }),
        {
          items: [],
          total: 0,
          limit: ANNOUNCEMENT_LIST_LIMIT,
          offset: 0
        }
      ),
      withOptionalWorkspaceData(
        getCompanyEvidence(companyId, { limit: 10, offset: 0, signal: controller.signal }),
        {
          items: [],
          total: 0,
          limit: 10,
          offset: 0
        }
      ),
      withOptionalWorkspaceData(getEvidenceModelConfig(controller.signal), EMPTY_MODEL_CONFIG),
      withOptionalWorkspaceData(getAnalystProfiles(controller.signal), EMPTY_ANALYST_PROFILES),
      withOptionalWorkspaceData(
        getLatestCompanyAnalysisRuns(companyId, {
          run_type: "analyst_view",
          status: "success",
          signal: controller.signal
        }),
        {
          company_id: companyId,
          run_type: "analyst_view",
          analyst_profile: null,
          status: "success",
          items: []
        }
      ),
      withOptionalWorkspaceData(
        getLatestCompanyAnalysisRuns(companyId, {
          run_type: "analyst_view",
          status: "failed",
          signal: controller.signal
        }),
        {
          company_id: companyId,
          run_type: "analyst_view",
          analyst_profile: null,
          status: "failed",
          items: []
        }
      ),
      withOptionalWorkspaceData(getLatestInvestmentMemo(companyId, controller.signal), {
        company_id: companyId,
        item: null
      }),
      withOptionalWorkspaceData(
        getInvestmentMemos(companyId, {
          limit: 20,
          offset: 0,
          signal: controller.signal
        }),
        {
          items: [],
          total: 0,
          limit: 20,
          offset: 0
        }
      ),
      withOptionalWorkspaceData(getLatestValuationRun(companyId, controller.signal), {
        company_id: companyId,
        item: null
      }),
      withOptionalWorkspaceData(
        getValuationRuns(companyId, { limit: 20, offset: 0, signal: controller.signal }),
        { items: [], total: 0, limit: 20, offset: 0 }
      ),
      withOptionalWorkspaceData(getLatestPriceDecisionRun(companyId, controller.signal), {
        company_id: companyId,
        item: null
      }),
      withOptionalWorkspaceData(
        getPriceDecisionRuns(companyId, { offset: 0, signal: controller.signal }),
        { items: [], total: 0, limit: 0, offset: 0 }
      )
    ])
      .then(
        ([
          company,
          financials,
          financialEvidencePack,
          announcements,
          evidence,
          modelConfig,
          analystProfiles,
          analysisRuns,
          failedAnalysisRuns,
          latestMemo,
          memoHistory,
          latestValuationRun,
          valuationHistory,
          latestPriceDecision,
          priceDecisionHistory
        ]) => {
        if (controller.signal.aborted) {
          return;
        }

        setDetailState({
          status: "ready",
          data: {
            company,
            financials,
            financialEvidencePack,
            announcements,
            evidence,
            modelConfig,
            analystProfiles,
            analysisRuns: toAnalysisRunListResponse(analysisRuns),
            failedAnalysisRuns: toAnalysisRunListResponse(failedAnalysisRuns),
            latestMemo,
            memoHistory,
            latestValuationRun,
            valuationHistory,
            latestPriceDecision,
            priceDecisionHistory
          },
          error: null
        });
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) {
          return;
        }

        const message = error instanceof Error ? error.message : "公司档案加载失败";
        if (message === "Company not found") {
          onCompanyUnavailable();
          return;
        }

        setDetailState({
          status: "error",
          data: null,
          error: message
        });
      });

    return () => {
      controller.abort();
    };
  }, [companyId, onCompanyUnavailable, refreshToken]);

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

  const {
    company,
    financials,
    financialEvidencePack,
    announcements,
    evidence,
    modelConfig,
    analystProfiles,
    analysisRuns,
    failedAnalysisRuns,
    latestMemo,
    memoHistory,
    latestValuationRun,
    valuationHistory,
    latestPriceDecision,
    priceDecisionHistory
  } = detailState.data;
  const readiness = buildResearchReadiness({
    financials,
    financialEvidencePack,
    announcements,
    evidence,
    analystProfiles,
    analysisRuns,
    failedAnalysisRuns
  });
  const memoPreparation = buildMemoPreparation(analystProfiles, analysisRuns, failedAnalysisRuns);

  async function handleRefreshCompanyProfile() {
    setProfileRefreshState({ status: "refreshing", message: "正在更新基本信息" });

    try {
      const refreshedCompany = await refreshCompanyProfile(company.id);
      setDetailState((currentState) => {
        if (currentState.status !== "ready") {
          return currentState;
        }

        return {
          status: "ready",
          data: {
            ...currentState.data,
            company: refreshedCompany
          },
          error: null
        };
      });
      setProfileRefreshState({ status: "success", message: "基本信息已更新" });
    } catch (error: unknown) {
      setProfileRefreshState({
        status: "error",
        message: error instanceof Error ? error.message : "基本信息更新失败"
      });
    }
  }

  async function handleSyncFinancials() {
    setFinancialSyncState({ status: "syncing", message: "正在搜索财务数据" });

    try {
      const syncResult = await syncCompanyFinancials(company.id, {
        limit: FINANCIAL_STATEMENT_SYNC_LIMIT
      });
      const refreshedFinancials = await getCompanyFinancials(company.id, {
        period_offset: 0
      });
      const refreshedFinancialEvidencePack = await getCompanyFinancialEvidencePack(company.id);

      setDetailState((currentState) => {
        if (currentState.status !== "ready") {
          return currentState;
        }

        return {
          status: "ready",
          data: {
            ...currentState.data,
            financials: refreshedFinancials,
            financialEvidencePack: refreshedFinancialEvidencePack
          },
          error: null
        };
      });
      setFinancialSyncState({
        status: "success",
        message: `已搜索 ${syncResult.fetched} 条，新增 ${syncResult.created} 条，更新 ${syncResult.updated} 条`
      });
    } catch (error: unknown) {
      setFinancialSyncState({
        status: "error",
        message: error instanceof Error ? error.message : "财务数据搜索失败"
      });
    }
  }

  async function handleDeleteFinancialStatement(statementId: number) {
    setFinancialDeleteState({
      status: "deleting",
      statementId,
      message: "正在删除财务数据"
    });

    try {
      await deleteCompanyFinancialStatement(company.id, statementId);
      const refreshedFinancialEvidencePack = await getCompanyFinancialEvidencePack(company.id);
      setDetailState((currentState) => {
        if (currentState.status !== "ready") {
          return currentState;
        }

        const nextItems = currentState.data.financials.items.filter(
          (item) => item.id !== statementId
        );

        return {
          status: "ready",
          data: {
            ...currentState.data,
            financials: {
              ...currentState.data.financials,
              items: nextItems,
              total: Math.max(0, currentState.data.financials.total - 1)
            },
            financialEvidencePack: refreshedFinancialEvidencePack
          },
          error: null
        };
      });
      setFinancialDeleteState({
        status: "success",
        statementId: null,
        message: "已删除财务数据"
      });
    } catch (error: unknown) {
      setFinancialDeleteState({
        status: "error",
        statementId,
        message: error instanceof Error ? error.message : "财务数据删除失败"
      });
    }
  }

  async function handleSearchEvidence() {
    setEvidenceSearchState({ status: "searching", message: "正在搜索外部信息" });

    try {
      const searchResult = await searchCompanyEvidence(company.id, {
        keywords: [company.name, company.industry ?? ""].filter(Boolean)
      });
      const refreshedEvidence = await getCompanyEvidence(company.id, {
        limit: 10,
        offset: 0
      });

      setDetailState((currentState) => {
        if (currentState.status !== "ready") {
          return currentState;
        }

        return {
          status: "ready",
          data: {
            ...currentState.data,
            evidence: refreshedEvidence
          },
          error: null
        };
      });
      setEvidenceSearchState({
        status: "success",
        message: formatEvidenceSearchMessage(searchResult)
      });
    } catch (error: unknown) {
      setEvidenceSearchState({
        status: "error",
        message: error instanceof Error ? error.message : "外部信息搜索失败"
      });
    }
  }

  async function handleImportTextEvidence(form: EvidenceImportTextForm) {
    const content = form.content.trim();
    if (!content) {
      setEvidenceImportTextState({
        status: "error",
        message: "请输入要导入的正文内容"
      });
      return;
    }

    setEvidenceImportTextState({ status: "importing", message: "正在结构化导入文本" });

    try {
      const importResult = await importTextEvidence(company.id, {
        title: optionalText(form.title),
        content,
        source: optionalText(form.source),
        source_url: optionalText(form.source_url),
        published_at: form.published_at ? `${form.published_at}T00:00:00+08:00` : undefined,
        source_type: form.source_type,
        notes: optionalText(form.notes)
      });
      const refreshedEvidence = await getCompanyEvidence(company.id, {
        limit: 10,
        offset: 0
      });

      setDetailState((currentState) => {
        if (currentState.status !== "ready") {
          return currentState;
        }

        return {
          status: "ready",
          data: {
            ...currentState.data,
            evidence: refreshedEvidence
          },
          error: null
        };
      });
      setEvidenceImportTextState({
        status: "success",
        message: formatEvidenceImportTextMessage(importResult)
      });
    } catch (error: unknown) {
      setEvidenceImportTextState({
        status: "error",
        message: error instanceof Error ? error.message : "导入文本失败"
      });
    }
  }

  async function handleSmokeTestModel() {
    setModelSmokeTestState({
      status: "testing",
      message: "正在自检模型连通性"
    });

    try {
      const smokeResult = await runEvidenceModelSmokeTest();
      const refreshedModelConfig = await getEvidenceModelConfig();

      setDetailState((currentState) => {
        if (currentState.status !== "ready") {
          return currentState;
        }

        return {
          status: "ready",
          data: {
            ...currentState.data,
            modelConfig: refreshedModelConfig
          },
          error: null
        };
      });
      setModelSmokeTestState({
        status: "success",
        message: smokeResult.message || "模型自检通过"
      });
    } catch (error: unknown) {
      setModelSmokeTestState({
        status: "error",
        message: error instanceof Error ? error.message : "模型自检失败"
      });
    }
  }

  async function handleDeleteEvidence(evidenceId: number) {
    setEvidenceDeleteState({
      status: "deleting",
      evidenceId,
      message: "正在删除外部信息"
    });

    try {
      await deleteEvidence(evidenceId);
      const refreshedEvidence = await getCompanyEvidence(company.id, {
        limit: 10,
        offset: 0
      });

      setDetailState((currentState) => {
        if (currentState.status !== "ready") {
          return currentState;
        }

        return {
          status: "ready",
          data: {
            ...currentState.data,
            evidence: refreshedEvidence
          },
          error: null
        };
      });
      setEvidenceDeleteState({
        status: "success",
        evidenceId: null,
        message: "已删除外部信息"
      });
    } catch (error: unknown) {
      setEvidenceDeleteState({
        status: "error",
        evidenceId,
        message: error instanceof Error ? error.message : "外部信息删除失败"
      });
    }
  }

  async function handleSyncAnnouncements() {
    setAnnouncementSyncState({ status: "syncing", message: "正在搜索公告" });

    try {
      const syncResult = await syncCompanyAnnouncements(company.id, {
        years: ANNOUNCEMENT_LOOKBACK_YEARS
      });
      const refreshedAnnouncements = await getCompanyAnnouncements(company.id, {
        limit: ANNOUNCEMENT_LIST_LIMIT,
        offset: 0
      });

      setDetailState((currentState) => {
        if (currentState.status !== "ready") {
          return currentState;
        }

        return {
          status: "ready",
          data: {
            ...currentState.data,
            announcements: refreshedAnnouncements
          },
          error: null
        };
      });
      setAnnouncementSyncState({
        status: "success",
        message: `已搜索 ${syncResult.fetched} 条，新增 ${syncResult.created} 条，更新 ${syncResult.updated} 条，跳过 ${syncResult.skipped} 条，清理 ${syncResult.pruned ?? 0} 条`
      });
    } catch (error: unknown) {
      setAnnouncementSyncState({
        status: "error",
        message: getUnknownErrorMessage(error, "公告搜索失败")
      });
    }
  }

  async function handleDeleteAnnouncement(announcementId: number) {
    setAnnouncementDeleteState({
      status: "deleting",
      announcementId,
      message: "正在删除公告"
    });

    try {
      await deleteCompanyAnnouncement(company.id, announcementId);
      setDetailState((currentState) => {
        if (currentState.status !== "ready") {
          return currentState;
        }

        const nextItems = currentState.data.announcements.items.filter(
          (item) => item.id !== announcementId
        );

        return {
          status: "ready",
          data: {
            ...currentState.data,
            announcements: {
              ...currentState.data.announcements,
              items: nextItems,
              total: Math.max(0, currentState.data.announcements.total - 1)
            }
          },
          error: null
        };
      });
      setAnnouncementDeleteState({
        status: "success",
        announcementId: null,
        message: "已删除公告"
      });
    } catch (error: unknown) {
      setAnnouncementDeleteState({
        status: "error",
        announcementId,
        message: getUnknownErrorMessage(error, "公告删除失败")
      });
    }
  }

  async function handleSummarizeAnnouncement(announcementId: number) {
    setAnnouncementSummaryState({
      status: "summarizing",
      announcementId,
      mode: "single",
      message: "正在生成单条深度摘要"
    });

    try {
      const summaryResult = await summarizeCompanyAnnouncement(company.id, announcementId);
      updateAnnouncementsFromSummaryItems(setDetailState, [
        {
          announcement_id: summaryResult.announcement_id,
          announcement: summaryResult.announcement
        }
      ]);
      setAnnouncementSummaryState({
        status: "success",
        announcementId: null,
        mode: "single",
        message: "已生成单条深度摘要"
      });
    } catch (error: unknown) {
      setAnnouncementSummaryState({
        status: "error",
        announcementId,
        mode: "single",
        message: getUnknownErrorMessage(error, "单条深度摘要失败")
      });
    }
  }

  async function handleSummarizeAllAnnouncements() {
    const quickSummaryCount = announcements.items.filter(
      (announcement) => !isDeepSummarizedAnnouncement(announcement)
    ).length;
    setAnnouncementSummaryState({
      status: "summarizing",
      announcementId: null,
      mode: "quick",
      message: `正在生成公告快速摘要：准备处理 ${quickSummaryCount} 条`
    });

    try {
      const summaryResult = await summarizeCompanyAnnouncements(company.id, {
        limit: ANNOUNCEMENT_SUMMARY_BATCH_LIMIT,
        only_missing: false,
        include_failed: true
      });
      const totalSucceeded = summaryResult.succeeded;
      const totalFailed = summaryResult.failed;
      const firstFailure = summaryResult.items.find((item) => item.status === "failed");
      const firstFailureReason = firstFailure?.error ? compactErrorMessage(firstFailure.error) : "";

      updateAnnouncementsFromSummaryItems(setDetailState, summaryResult.items);

      const refreshedAnnouncements = await getCompanyAnnouncements(company.id, {
        limit: ANNOUNCEMENT_LIST_LIMIT,
        offset: 0
      });
      setDetailState((currentState) => {
        if (currentState.status !== "ready") {
          return currentState;
        }

        return {
          status: "ready",
          data: {
            ...currentState.data,
            announcements: refreshedAnnouncements
          },
          error: null
        };
      });

      const failureReason = firstFailureReason ? `：${firstFailureReason}` : "";
      if (totalSucceeded === 0 && totalFailed > 0) {
        setAnnouncementSummaryState({
          status: "error",
          announcementId: null,
          mode: "quick",
          message: `公告快速摘要全部失败，失败 ${totalFailed} 条${failureReason}`
        });
        return;
      }

      setAnnouncementSummaryState({
        status: totalFailed > 0 ? "partial_success" : "success",
        announcementId: null,
        mode: "quick",
        message:
          totalFailed > 0
            ? `已生成 ${totalSucceeded} 条公告快速摘要，失败 ${totalFailed} 条${failureReason}`
            : `已生成 ${totalSucceeded} 条公告快速摘要`
      });
    } catch (error: unknown) {
      setAnnouncementSummaryState({
        status: "error",
        announcementId: null,
        mode: "quick",
        message: getUnknownErrorMessage(error, "公告快速摘要失败")
      });
    }
  }

  async function handleSummarizeAllAnnouncementsDeep() {
    const deepSummaryCount = announcements.items.filter(
      (announcement) => !isDeepSummarizedAnnouncement(announcement)
    ).length;
    setAnnouncementSummaryState({
      status: "summarizing",
      announcementId: null,
      mode: "deep",
      message: `正在生成公告深度摘要：准备处理 ${deepSummaryCount} 条`
    });

    try {
      const summaryResult = await summarizeCompanyAnnouncementsDeep(company.id, {
        limit: ANNOUNCEMENT_SUMMARY_BATCH_LIMIT
      });
      const totalSucceeded = summaryResult.succeeded;
      const totalFailed = summaryResult.failed;
      const firstFailure = summaryResult.items.find((item) => item.status === "failed");
      const firstFailureReason = firstFailure?.error ? compactErrorMessage(firstFailure.error) : "";

      updateAnnouncementsFromSummaryItems(setDetailState, summaryResult.items);

      const refreshedAnnouncements = await getCompanyAnnouncements(company.id, {
        limit: ANNOUNCEMENT_LIST_LIMIT,
        offset: 0
      });
      setDetailState((currentState) => {
        if (currentState.status !== "ready") {
          return currentState;
        }

        return {
          status: "ready",
          data: {
            ...currentState.data,
            announcements: refreshedAnnouncements
          },
          error: null
        };
      });

      const failureReason = firstFailureReason ? `：${firstFailureReason}` : "";
      if (totalSucceeded === 0 && totalFailed > 0) {
        setAnnouncementSummaryState({
          status: "error",
          announcementId: null,
          mode: "deep",
          message: `公告深度摘要全部失败，失败 ${totalFailed} 条${failureReason}`
        });
        return;
      }

      setAnnouncementSummaryState({
        status: totalFailed > 0 ? "partial_success" : "success",
        announcementId: null,
        mode: "deep",
        message:
          totalFailed > 0
            ? `已生成 ${totalSucceeded} 条公告深度摘要，失败 ${totalFailed} 条${failureReason}`
            : `已生成 ${totalSucceeded} 条公告深度摘要`
      });
    } catch (error: unknown) {
      setAnnouncementSummaryState({
        status: "error",
        announcementId: null,
        mode: "deep",
        message: getUnknownErrorMessage(error, "公告深度摘要失败")
      });
    }
  }

  async function handleRunAnalystAnalysis(profileId: string) {
    analystRunAbortControllerRef.current?.abort();
    const controller = new AbortController();
    analystRunAbortControllerRef.current = controller;
    setAnalystRunState({
      status: "running",
      profileId,
      message: "正在生成分析师视角"
    });

    try {
      const runResult = await runCompanyAnalysis(company.id, {
        analyst_profile: profileId,
        signal: controller.signal
      });
      const [refreshedRuns, refreshedFailedRuns] = await loadLatestAnalystRuns(company.id);

      setDetailState((currentState) => {
        if (currentState.status !== "ready") {
          return currentState;
        }

        return {
          status: "ready",
          data: {
            ...currentState.data,
            analysisRuns: toAnalysisRunListResponse(refreshedRuns),
            failedAnalysisRuns: toAnalysisRunListResponse(refreshedFailedRuns)
          },
          error: null
        };
      });
      setAnalystRunState({
        status: "success",
        profileId,
        message: `已生成分析师视角，运行记录 #${runResult.id}`
      });
    } catch (error: unknown) {
      if (controller.signal.aborted) {
        setAnalystRunState({
          status: "idle",
          profileId: null,
          message: "已停止本次生成请求"
        });
        void refreshLatestAnalystRuns(company.id, setDetailState);
        return;
      }
      setAnalystRunState({
        status: "error",
        profileId,
        message: error instanceof Error ? error.message : "分析师视角生成失败"
      });
      void refreshFailedAnalystRuns(company.id, setDetailState);
    } finally {
      if (analystRunAbortControllerRef.current === controller) {
        analystRunAbortControllerRef.current = null;
      }
    }
  }

  async function handleRunAllAnalystAnalysis() {
    const successfulProfileIds = new Set(
      analysisRuns.items
        .map((run) => run.analyst_profile)
        .filter((profileId): profileId is string => Boolean(profileId))
    );
    const missingProfileIds = analystProfiles.items
      .map((profile) => profile.id)
      .filter((profileId) => !successfulProfileIds.has(profileId));

    if (missingProfileIds.length === 0) {
      setAnalystRunState({
        status: "success",
        profileId: null,
        message: "8 位分析师均已有成功 run，无需生成"
      });
      return;
    }

    analystRunAbortControllerRef.current?.abort();
    const controller = new AbortController();
    analystRunAbortControllerRef.current = controller;
    setAnalystRunState({
      status: "running_all",
      profileId: null,
      message: `正在生成 ${missingProfileIds.length} 位缺失分析师视角`
    });

    try {
      const batchResult = await runCompanyAnalysisBatch(company.id, {
        analyst_profiles: missingProfileIds,
        signal: controller.signal
      });
      const [refreshedRuns, refreshedFailedRuns] = await loadLatestAnalystRuns(company.id);

      setDetailState((currentState) => {
        if (currentState.status !== "ready") {
          return currentState;
        }

        return {
          status: "ready",
          data: {
            ...currentState.data,
            analysisRuns: toAnalysisRunListResponse(refreshedRuns),
            failedAnalysisRuns: toAnalysisRunListResponse(refreshedFailedRuns)
          },
          error: null
        };
      });
      setAnalystRunState({
        status: batchResult.failed > 0 ? "partial_success" : "success",
        profileId: null,
        message: formatBatchRunMessage(batchResult, analystProfiles)
      });
    } catch (error: unknown) {
      if (controller.signal.aborted) {
        setAnalystRunState({
          status: "idle",
          profileId: null,
          message: "已停止本次批量生成请求"
        });
        void refreshLatestAnalystRuns(company.id, setDetailState);
        return;
      }
      setAnalystRunState({
        status: "error",
        profileId: null,
        message: error instanceof Error ? error.message : "全部分析师视角生成失败"
      });
    } finally {
      if (analystRunAbortControllerRef.current === controller) {
        analystRunAbortControllerRef.current = null;
      }
    }
  }

  function handleStopAnalystAnalysis() {
    analystRunAbortControllerRef.current?.abort();
    analystRunAbortControllerRef.current = null;
    setAnalystRunState({
      status: "idle",
      profileId: null,
      message: "已停止本次生成请求"
    });
  }

  async function handleDeleteAnalysisRun(runId: number) {
    setAnalysisRunDeleteState({
      status: "deleting",
      runId,
      message: "正在删除分析记录"
    });

    try {
      await deleteCompanyAnalysisRun(company.id, runId);
      const [refreshedRuns, refreshedFailedRuns] = await loadLatestAnalystRuns(company.id);

      setDetailState((currentState) => {
        if (currentState.status !== "ready") {
          return currentState;
        }

        return {
          status: "ready",
          data: {
            ...currentState.data,
            analysisRuns: toAnalysisRunListResponse(refreshedRuns),
            failedAnalysisRuns: toAnalysisRunListResponse(refreshedFailedRuns)
          },
          error: null
        };
      });
      setAnalysisRunDeleteState({
        status: "success",
        runId: null,
        message: "已删除分析记录"
      });
    } catch (error: unknown) {
      setAnalysisRunDeleteState({
        status: "error",
        runId,
        message: error instanceof Error ? error.message : "分析记录删除失败"
      });
    }
  }

  async function handleUpdateAnalysisRuleStatus(
    runId: number,
    ruleId: string,
    status: AnalystRuleStatus
  ) {
    setAnalysisRuleStatusUpdateState({
      status: "saving",
      runId,
      ruleId,
      message: "正在保存规则结论"
    });

    try {
      const updatedRun = await updateAnalysisRunRuleStatus(company.id, runId, ruleId, status);
      setDetailState((currentState) => {
        if (currentState.status !== "ready") {
          return currentState;
        }

        return {
          status: "ready",
          data: {
            ...currentState.data,
            analysisRuns: {
              ...currentState.data.analysisRuns,
              items: currentState.data.analysisRuns.items.map((run) =>
                run.id === updatedRun.id ? updatedRun : run
              )
            }
          },
          error: null
        };
      });
      setAnalysisRuleStatusUpdateState({
        status: "success",
        runId: null,
        ruleId: null,
        message: "已保存规则结论"
      });
    } catch (error: unknown) {
      setAnalysisRuleStatusUpdateState({
        status: "error",
        runId,
        ruleId,
        message: getUnknownErrorMessage(error, "规则结论保存失败")
      });
    }
  }

  async function handleGenerateMemo() {
    setMemoGenerateState({
      status: "generating",
      message: "正在生成综合投资备忘录"
    });

    try {
      const result = await generateInvestmentMemo(company.id);
      const [refreshedLatestMemo, refreshedMemoHistory] = await loadInvestmentMemos(company.id);

      setDetailState((currentState) => {
        if (currentState.status !== "ready") {
          return currentState;
        }

        return {
          status: "ready",
          data: {
            ...currentState.data,
            latestMemo: refreshedLatestMemo,
            memoHistory: refreshedMemoHistory
          },
          error: null
        };
      });
      setMemoGenerateState({
        status: "success",
        message: `已生成综合投资备忘录 v${result.memo.version_no}`
      });
    } catch (error: unknown) {
      setMemoGenerateState({
        status: "error",
        message: getMemoGenerateErrorMessage(error)
      });
    }
  }

  async function handleDeleteMemo(memoId: number) {
    setMemoDeleteState({
      status: "deleting",
      memoId,
      message: "正在删除综合投资备忘录"
    });

    try {
      await deleteInvestmentMemo(memoId);
      const [refreshedLatestMemo, refreshedMemoHistory] = await loadInvestmentMemos(company.id);

      setDetailState((currentState) => {
        if (currentState.status !== "ready") {
          return currentState;
        }

        return {
          status: "ready",
          data: {
            ...currentState.data,
            latestMemo: refreshedLatestMemo,
            memoHistory: refreshedMemoHistory
          },
          error: null
        };
      });
      setMemoDeleteState({
        status: "success",
        memoId: null,
        message: "已删除综合投资备忘录"
      });
    } catch (error: unknown) {
      setMemoDeleteState({
        status: "error",
        memoId,
        message: getUnknownErrorMessage(error, "综合投资备忘录删除失败")
      });
    }
  }

  async function handleArchiveMemo(memoId: number) {
    setMemoArchiveState({
      status: "archiving",
      memoId,
      message: "正在归档综合投资备忘录"
    });

    try {
      await archiveInvestmentMemo(memoId);
      const [refreshedLatestMemo, refreshedMemoHistory] = await loadInvestmentMemos(company.id);

      setDetailState((currentState) => {
        if (currentState.status !== "ready") {
          return currentState;
        }

        return {
          status: "ready",
          data: {
            ...currentState.data,
            latestMemo: refreshedLatestMemo,
            memoHistory: refreshedMemoHistory
          },
          error: null
        };
      });
      setMemoArchiveState({
        status: "success",
        memoId: null,
        message: "已归档综合投资备忘录"
      });
    } catch (error: unknown) {
      setMemoArchiveState({
        status: "error",
        memoId,
        message: getUnknownErrorMessage(error, "综合投资备忘录归档失败")
      });
    }
  }

  async function handleCreateValuationDraft(assumptions?: Record<string, unknown>) {
    setValuationActionState({
      status: "saving",
      message: "正在生成无锚定估值草稿"
    });

    try {
      const result = await createValuationDraft(company.id, { assumptions });
      setDetailState((currentState) => {
        if (currentState.status !== "ready") {
          return currentState;
        }

        return {
          status: "ready",
          data: {
            ...currentState.data,
            latestValuationRun: {
              company_id: company.id,
              item: result.item
            }
          },
          error: null
        };
      });
      setValuationActionState({
        status: "success",
        message: `已生成无锚定估值草稿 #${result.item.id}`
      });
    } catch (error: unknown) {
      setValuationActionState({
        status: "error",
        message: getUnknownErrorMessage(error, "无锚定估值草稿生成失败")
      });
    }
  }

  async function handleRecalculateValuation(
    runId: number,
    assumptions: Record<string, unknown>
  ) {
    setValuationActionState({
      status: "saving",
      message: "正在确认参数并计算"
    });

    try {
      const result = await recalculateValuationRun(runId, { assumptions });
      setDetailState((currentState) => {
        if (currentState.status !== "ready") {
          return currentState;
        }

        return {
          status: "ready",
          data: {
            ...currentState.data,
            latestValuationRun: {
              company_id: company.id,
              item: result.item
            }
          },
          error: null
        };
      });
      setValuationActionState({
        status: "success",
        message: `已确认参数并生成估值草稿 #${result.item.id}`
      });
    } catch (error: unknown) {
      setValuationActionState({
        status: "error",
        message: getUnknownErrorMessage(error, "重新计算无锚定估值失败")
      });
    }
  }

  async function handleCreatePriceDecision(
    valuationRunId: number,
    safetyMarginOverride: number | null
  ) {
    setPriceDecisionActionState({
      status: "saving",
      message: latestPriceDecision.item ? "正在重新计算价格决策" : "正在生成价格决策"
    });

    try {
      const result = await createPriceDecisionRun(company.id, {
        valuation_run_id: valuationRunId,
        safety_margin_override: safetyMarginOverride
      });
      const [refreshedLatest, refreshedHistory] = await loadPriceDecisions(company.id);
      setDetailState((currentState) => {
        if (currentState.status !== "ready") {
          return currentState;
        }
        return {
          status: "ready",
          data: {
            ...currentState.data,
            latestPriceDecision: refreshedLatest,
            priceDecisionHistory: refreshedHistory
          },
          error: null
        };
      });
      setPriceDecisionActionState({
        status: "success",
        message: `已生成价格决策 v${result.item.version_no}`
      });
    } catch (error: unknown) {
      setPriceDecisionActionState({
        status: "error",
        message: getUnknownErrorMessage(error, "价格决策生成失败")
      });
    }
  }

  async function handleDeletePriceDecision(runId: number) {
    setPriceDecisionDeleteState({
      status: "deleting",
      runId,
      message: "正在删除价格决策版本"
    });
    try {
      await deletePriceDecisionRun(runId);
      const [refreshedLatest, refreshedHistory] = await loadPriceDecisions(company.id);
      setDetailState((currentState) => {
        if (currentState.status !== "ready") {
          return currentState;
        }
        return {
          status: "ready",
          data: {
            ...currentState.data,
            latestPriceDecision: refreshedLatest,
            priceDecisionHistory: refreshedHistory
          },
          error: null
        };
      });
      setPriceDecisionDeleteState({
        status: "success",
        runId: null,
        message: "已删除价格决策版本"
      });
    } catch (error: unknown) {
      setPriceDecisionDeleteState({
        status: "error",
        runId,
        message: getUnknownErrorMessage(error, "价格决策删除失败")
      });
    }
  }

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
        <div className="profile-summary__heading">
          <h3>基础档案</h3>
          <button
            className="panel-action"
            type="button"
            title="更新公司基本信息"
            disabled={profileRefreshState.status === "refreshing"}
            onClick={handleRefreshCompanyProfile}
          >
            <RefreshCw aria-hidden="true" size={15} />
            <span>{profileRefreshState.status === "refreshing" ? "更新中" : "更新"}</span>
          </button>
        </div>
        <p>{company.description ?? "暂无公司简介。"}</p>
        {profileRefreshState.message ? (
          <div
            className={
              profileRefreshState.status === "error"
                ? "sync-message sync-message--error"
                : "sync-message"
            }
          >
            {profileRefreshState.message}
          </div>
        ) : null}
        <dl className="profile-facts">
          <div>
            <dt>上市日期</dt>
            <dd>{company.listed_date ?? "待补充"}</dd>
          </div>
          <div>
            <dt>档案更新时间</dt>
            <dd>{formatDateTime(company.updated_at)}</dd>
          </div>
          <div>
            <dt>行情更新时间</dt>
            <dd>
              {company.market_data_updated_at
                ? formatDateTime(company.market_data_updated_at)
                : "待更新"}
            </dd>
          </div>
        </dl>
        <h4>基本信息</h4>
        <dl className="market-facts">
          <MetricFact label="市值" value={formatMoney(company.market_cap)} />
          <MetricFact label="价格" value={formatPrice(company.current_price)} />
          <MetricFact label="TTM市盈率" value={formatRatio(company.pe_ttm)} />
          <MetricFact label="动态市盈率" value={formatRatio(company.pe_dynamic)} />
          <MetricFact label="静态市盈率" value={formatRatio(company.pe_static)} />
          <MetricFact label="市净率" value={formatRatio(company.pb_ratio)} />
          <MetricFact label="市销率" value={formatRatio(company.ps_ratio)} />
          <MetricFact label="TTM股息率" value={formatPercent(company.dividend_yield_ttm)} />
        </dl>
      </section>

      <WorkspaceSectionTabs activeSection={activeSection} onSectionChange={onSectionChange} />

      {activeSection === "overview" ? (
        <OverviewPanel readiness={readiness} onOpenSection={onSectionChange} />
      ) : null}

      {activeSection === "financials" ? (
        <FinancialsPanel
          financials={financials}
          financialEvidencePack={financialEvidencePack}
          syncState={financialSyncState}
          deleteState={financialDeleteState}
          onSyncFinancials={handleSyncFinancials}
          onDeleteFinancialStatement={handleDeleteFinancialStatement}
        />
      ) : null}

      {activeSection === "announcements" ? (
        <AnnouncementsPanel
          announcements={announcements}
          syncState={announcementSyncState}
          deleteState={announcementDeleteState}
          summaryState={announcementSummaryState}
          onSyncAnnouncements={handleSyncAnnouncements}
          onDeleteAnnouncement={handleDeleteAnnouncement}
          onSummarizeAnnouncement={handleSummarizeAllAnnouncements}
          onSummarizeDeepAnnouncements={handleSummarizeAllAnnouncementsDeep}
          onSummarizeSingleAnnouncement={handleSummarizeAnnouncement}
        />
      ) : null}

      {activeSection === "evidence" ? (
        <EvidencePanel
          evidence={evidence}
          modelConfig={modelConfig}
          searchState={evidenceSearchState}
          importTextState={evidenceImportTextState}
          modelSmokeTestState={modelSmokeTestState}
          deleteState={evidenceDeleteState}
          onSearchEvidence={handleSearchEvidence}
          onImportTextEvidence={handleImportTextEvidence}
          onSmokeTestModel={handleSmokeTestModel}
          onDeleteEvidence={handleDeleteEvidence}
        />
      ) : null}

      {activeSection === "analyst-views" ? (
        <AnalystPanel
          profiles={analystProfiles}
          runs={analysisRuns}
          failedRuns={failedAnalysisRuns}
          runState={analystRunState}
          deleteState={analysisRunDeleteState}
          statusUpdateState={analysisRuleStatusUpdateState}
          onRunProfile={handleRunAnalystAnalysis}
          onRunAllProfiles={handleRunAllAnalystAnalysis}
          onStopRun={handleStopAnalystAnalysis}
          onDeleteRun={handleDeleteAnalysisRun}
          onUpdateRuleStatus={handleUpdateAnalysisRuleStatus}
        />
      ) : null}

      {activeSection === "valuation-lab" ? (
        <ValuationLabPanel
          analystProfiles={analystProfiles}
          latestMemo={latestMemo.item}
          latestValuationRun={latestValuationRun.item}
          financialEvidencePack={financialEvidencePack}
          actionState={valuationActionState}
          onCreateDraft={handleCreateValuationDraft}
          onRecalculate={handleRecalculateValuation}
        />
      ) : null}

      {activeSection === "price-decision" ? (
        <PriceDecisionPanel
          company={company}
          latestValuationRun={latestValuationRun.item}
          valuationHistory={valuationHistory}
          latestRun={latestPriceDecision.item}
          history={priceDecisionHistory}
          actionState={priceDecisionActionState}
          deleteState={priceDecisionDeleteState}
          onGenerate={handleCreatePriceDecision}
          onDelete={handleDeletePriceDecision}
          onOpenValuation={() => onSectionChange("valuation-lab")}
          onRefreshCompany={handleRefreshCompanyProfile}
        />
      ) : null}

      {activeSection === "memo" ? (
        <MemoPreparationPanel
          memoPreparation={memoPreparation}
          latestMemo={latestMemo.item}
          memoHistory={memoHistory}
          generateState={memoGenerateState}
          deleteState={memoDeleteState}
          archiveState={memoArchiveState}
          onGenerateMemo={handleGenerateMemo}
          onDeleteMemo={handleDeleteMemo}
          onArchiveMemo={handleArchiveMemo}
        />
      ) : null}
    </section>
  );
}

type FinancialsPanelProps = {
  financials: FinancialStatementListResponse;
  financialEvidencePack: FinancialEvidencePack;
  syncState: FinancialSyncState;
  deleteState: FinancialDeleteState;
  onSyncFinancials: () => void;
  onDeleteFinancialStatement: (statementId: number) => void;
};

type FinancialSyncState =
  | { status: "idle"; message: null }
  | { status: "syncing"; message: string }
  | { status: "success"; message: string }
  | { status: "error"; message: string };

type EvidenceSearchState =
  | { status: "idle"; message: null }
  | { status: "searching"; message: string }
  | { status: "success"; message: string }
  | { status: "error"; message: string };

type EvidenceImportTextState =
  | { status: "idle"; message: null }
  | { status: "importing"; message: string }
  | { status: "success"; message: string }
  | { status: "error"; message: string };

type EvidenceImportTextForm = {
  title: string;
  content: string;
  source: string;
  source_url: string;
  published_at: string;
  source_type: EvidenceSourceType;
  notes: string;
};

type AnnouncementSyncState =
  | { status: "idle"; message: null }
  | { status: "syncing"; message: string }
  | { status: "success"; message: string }
  | { status: "error"; message: string };

type AnnouncementDeleteState =
  | { status: "idle"; announcementId: null; message: null }
  | { status: "deleting"; announcementId: number; message: string }
  | { status: "success"; announcementId: null; message: string }
  | { status: "error"; announcementId: number; message: string };

type AnnouncementSummaryState =
  | { status: "idle"; message: null }
  | {
      status: "summarizing";
      announcementId: number | null;
      mode: "quick" | "deep" | "single";
      message: string;
    }
  | { status: "success"; announcementId: null; mode?: "quick" | "deep" | "single"; message: string }
  | {
      status: "partial_success";
      announcementId: null;
      mode?: "quick" | "deep" | "single";
      message: string;
    }
  | {
      status: "error";
      announcementId: number | null;
      mode?: "quick" | "deep" | "single";
      message: string;
    };

type AnalystRunState =
  | { status: "idle"; profileId: null; message: string | null }
  | { status: "running"; profileId: string; message: string }
  | { status: "running_all"; profileId: null; message: string }
  | { status: "success"; profileId: string | null; message: string }
  | { status: "partial_success"; profileId: null; message: string }
  | { status: "error"; profileId: string | null; message: string };

type ResearchReadiness = {
  financialRecords: number;
  latestFinancialPeriod: string;
  financialGapCount: number;
  announcementTotal: number;
  announcementUnprocessed: number;
  announcementQuickSummarized: number;
  announcementDeepSummarized: number;
  evidenceTotal: number;
  modelAnalyzedEvidence: number;
  searchLeadEvidence: number;
  analystSuccessCount: number;
  analystFailureCount: number;
  missingProfileCount: number;
  memoReady: boolean;
  memoStatus: string;
};

type MemoPreparation = {
  successfulProfiles: string[];
  missingProfiles: string[];
  failedProfiles: string[];
  risks: string[];
  counterEvidence: string[];
  dataGaps: string[];
  valuationAssumptions: string[];
};

type WorkspaceSectionTabsProps = {
  activeSection: CompanyWorkspaceSection;
  onSectionChange: (section: CompanyWorkspaceSection) => void;
};

type MetricFactProps = {
  label: string;
  value: string;
};

function WorkspaceSectionTabs({ activeSection, onSectionChange }: WorkspaceSectionTabsProps) {
  return (
    <nav className="workspace-section-tabs" aria-label="公司工作台模块">
      {workspaceSections.map((section) => (
        <button
          key={section.id}
          className={
            activeSection === section.id
              ? "workspace-section-tab workspace-section-tab--active"
              : "workspace-section-tab"
          }
          type="button"
          aria-current={activeSection === section.id ? "page" : undefined}
          onClick={() => onSectionChange(section.id)}
        >
          <strong>{section.label}</strong>
          <span>{section.description}</span>
        </button>
      ))}
    </nav>
  );
}

function OverviewPanel({
  readiness,
  onOpenSection
}: {
  readiness: ResearchReadiness;
  onOpenSection: (section: CompanyWorkspaceSection) => void;
}) {
  return (
    <section className="data-panel overview-panel" aria-labelledby="overview-heading">
      <div className="data-panel__heading">
        <div>
          <ShieldCheck aria-hidden="true" size={20} />
          <h3 id="overview-heading">研究准备度</h3>
        </div>
        <div className="data-panel__actions">
          <span>{readiness.memoStatus}</span>
        </div>
      </div>

      <div className="readiness-grid">
        <button
          className="readiness-card"
          type="button"
          onClick={() => onOpenSection("financials")}
        >
          <span>财务底稿</span>
          <strong>{readiness.financialRecords} 条</strong>
          <small>
            最新 {readiness.latestFinancialPeriod}，缺口 {readiness.financialGapCount} 项
          </small>
        </button>
        <button
          className="readiness-card"
          type="button"
          onClick={() => onOpenSection("announcements")}
        >
          <span>公告摘要</span>
          <strong>{readiness.announcementTotal} 条</strong>
          <small>
            未摘要 {readiness.announcementUnprocessed}，快速{" "}
            {readiness.announcementQuickSummarized}，深度{" "}
            {readiness.announcementDeepSummarized}
          </small>
        </button>
        <button className="readiness-card" type="button" onClick={() => onOpenSection("evidence")}>
          <span>外部证据</span>
          <strong>{readiness.evidenceTotal} 条</strong>
          <small>
            模型分析 {readiness.modelAnalyzedEvidence}，待复核线索{" "}
            {readiness.searchLeadEvidence}
          </small>
        </button>
        <button
          className="readiness-card"
          type="button"
          onClick={() => onOpenSection("analyst-views")}
        >
          <span>分析师视角</span>
          <strong>{readiness.analystSuccessCount} 个成功</strong>
          <small>
            最近失败 {readiness.analystFailureCount}，缺失{" "}
            {readiness.missingProfileCount}
          </small>
        </button>
      </div>

      <div className={readiness.memoReady ? "memo-status memo-status--ready" : "memo-status"}>
        <div>
          <strong>Memo 准备状态</strong>
          <p>{readiness.memoStatus}</p>
        </div>
        <button className="panel-action" type="button" onClick={() => onOpenSection("memo")}>
          <FileText aria-hidden="true" size={15} />
          <span>查看 Memo 准备区</span>
        </button>
      </div>
    </section>
  );
}

type MemoPreparationPanelProps = {
  memoPreparation: MemoPreparation;
  latestMemo: InvestmentMemo | null;
  memoHistory: InvestmentMemoListResponse;
  generateState: MemoGenerateState;
  deleteState: MemoDeleteState;
  archiveState: MemoArchiveState;
  onGenerateMemo: () => void;
  onDeleteMemo: (memoId: number) => void;
  onArchiveMemo: (memoId: number) => void;
};

type ValuationLabPanelProps = {
  analystProfiles: AnalystProfileListResponse;
  latestMemo: InvestmentMemo | null;
  latestValuationRun: ValuationRun | null;
  financialEvidencePack: FinancialEvidencePack;
  actionState: ValuationActionState;
  onCreateDraft: (assumptions?: Record<string, unknown>) => void;
  onRecalculate: (runId: number, assumptions: Record<string, unknown>) => void;
};

type ValuationScenarioName = "conservative" | "base" | "optimistic";

const valuationScenarioNames: ValuationScenarioName[] = [
  "conservative",
  "base",
  "optimistic"
];

const valuationScenarioLabels: Record<ValuationScenarioName, string> = {
  conservative: "保守",
  base: "中性",
  optimistic: "乐观"
};

const valuationAssumptionFields = [
  { key: "cash_flow_growth_rate", label: "自由现金流增长" },
  { key: "owner_earnings_growth_rate", label: "所有者盈余增长" },
  { key: "discount_rate", label: "折现率" },
  { key: "terminal_growth_rate", label: "永续增长率" }
] as const;

const valuationModelWeightFields = [
  { key: "owner_earnings", label: "所有者盈余" },
  { key: "dcf", label: "DCF" },
  { key: "residual_income", label: "剩余收益" },
  { key: "dividend_discount", label: "分红折现" },
  { key: "asset_value", label: "资产价值" }
] as const;

const defaultValuationModelWeights = {
  owner_earnings: 35,
  dcf: 35,
  residual_income: 15,
  dividend_discount: 10,
  asset_value: 5
} as const;

type ValuationScenarioDraft = Record<
  ValuationScenarioName,
  Record<(typeof valuationAssumptionFields)[number]["key"], number | null>
>;

type ValuationModelWeightsDraft = Record<
  (typeof valuationModelWeightFields)[number]["key"],
  number | null
>;

function ValuationLabPanel({
  analystProfiles,
  latestMemo,
  latestValuationRun,
  financialEvidencePack,
  actionState,
  onCreateDraft,
  onRecalculate
}: ValuationLabPanelProps) {
  const [scenarioDraft, setScenarioDraft] = useState<ValuationScenarioDraft>(() =>
    buildEditableValuationScenarios(latestValuationRun)
  );
  const [modelWeightsDraft, setModelWeightsDraft] = useState<ValuationModelWeightsDraft>(() =>
    buildEditableValuationModelWeights(latestValuationRun)
  );

  useEffect(() => {
    setScenarioDraft(buildEditableValuationScenarios(latestValuationRun));
    setModelWeightsDraft(buildEditableValuationModelWeights(latestValuationRun));
  }, [latestValuationRun]);

  const isSaving = actionState.status === "saving";
  const valuationInputs = latestValuationRun?.valuation_inputs ?? {};
  const results = latestValuationRun?.results ?? {};
  const inputGaps = latestValuationRun
    ? readRecordArray(results.valuation_input_gaps)
    : readRecordArray(financialEvidencePack.financial_data_gaps).filter((gap) =>
        normalizeStringList(gap.needed_by).includes("valuation_lab")
      );
  const methodResults = readRecordArray(results.method_results);
  const combinedRange = readPlainRecord(results.intrinsic_value_range);
  const totalEquityValue = readPlainRecord(combinedRange.total_equity_value);
  const perShareValue = readPlainRecord(combinedRange.per_share_value);
  const modelWeighting = readRecordArray(results.model_weighting);
  const dispersionWarning = readPlainRecord(results.dispersion_warning);
  const resultStatus = String(results.status ?? "");
  const normalizationAudit = readPlainRecord(valuationInputs.normalization_audit);
  const growthBasis = readPlainRecord(
    latestValuationRun?.model_suggested_assumptions.growth_basis
  );
  const matrixSnapshot = readPlainRecord(
    latestValuationRun?.model_suggested_assumptions.analyst_parameter_matrix_snapshot
  );
  const analystWeights = readRecordArray(matrixSnapshot.analyst_weights);
  const ruleImpacts = readRecordArray(matrixSnapshot.rule_impacts);
  const safetyMarginContributions = readRecordArray(results.dynamic_safety_margin_contributions);
  const dynamicSafetyMargin = readNumber(results.dynamic_safety_margin);
  const analystProfileOrder = new Map(
    analystProfiles.items.map((profile, index) => [profile.id, index])
  );
  const currentRuleIds = new Map(
    analystProfiles.items.map((profile) => [
      profile.id,
      new Set(profile.rules.map((rule) => rule.id))
    ])
  );
  const currentRuleImpacts = ruleImpacts.filter((rule) =>
    currentRuleIds
      .get(String(rule.profile_id ?? ""))
      ?.has(String(rule.rule_id ?? ""))
  );
  const currentSafetyMarginContributions = safetyMarginContributions.filter((item) =>
    currentRuleIds
      .get(String(item.profile_id ?? ""))
      ?.has(String(item.rule_id ?? ""))
  );
  const analystOrder = (item: Record<string, unknown>) =>
    analystProfileOrder.get(String(item.profile_id ?? "")) ?? Number.MAX_SAFE_INTEGER;
  const orderedAnalystWeights = analystWeights
    .filter(
      (analyst) =>
        analystProfileOrder.has(String(analyst.profile_id ?? "")) &&
        currentRuleImpacts.some(
          (rule) =>
            rule.profile_id === analyst.profile_id && rule.source_run_id === analyst.source_run_id
        )
    )
    .sort((left, right) => analystOrder(left) - analystOrder(right));
  const hasLegacyAnalystMatrix =
    analystWeights.length !== orderedAnalystWeights.length ||
    ruleImpacts.length !== currentRuleImpacts.length;
  const dimensionContributions = readPlainRecord(matrixSnapshot.dimension_contributions);
  const confidenceReasons = normalizeStringList(latestValuationRun?.confidence_summary.reasons);
  const isCalculated =
    resultStatus === "calculated_after_user_confirmation" || methodResults.length > 0;
  const modelWeightTotal = sumValuationModelWeights(modelWeightsDraft);
  const modelWeightValidation = validateValuationModelWeights(modelWeightsDraft);

  function updateScenarioDraft(
    scenarioName: ValuationScenarioName,
    fieldName: (typeof valuationAssumptionFields)[number]["key"],
    value: string
  ) {
    setScenarioDraft((currentDraft) => ({
      ...currentDraft,
      [scenarioName]: {
        ...currentDraft[scenarioName],
        [fieldName]: parseAssumptionInput(value)
      }
    }));
  }

  function updateModelWeightDraft(
    fieldName: (typeof valuationModelWeightFields)[number]["key"],
    value: string
  ) {
    setModelWeightsDraft((currentDraft) => ({
      ...currentDraft,
      [fieldName]: parseAssumptionInput(value)
    }));
  }

  return (
    <section className="data-panel valuation-lab-panel" aria-labelledby="valuation-lab-heading">
      <div className="data-panel__heading">
        <div>
          <Calculator aria-hidden="true" size={20} />
          <h3 id="valuation-lab-heading">无锚定估值实验室</h3>
        </div>
        <div className="data-panel__actions">
          <span>price_blind=true</span>
          <button
            className="panel-action"
            type="button"
            disabled={!latestMemo || isSaving}
            onClick={() => onCreateDraft()}
          >
            <PlayCircle aria-hidden="true" size={15} />
            <span>{isSaving && !latestValuationRun ? "生成中" : "生成草稿"}</span>
          </button>
        </div>
      </div>

      {actionState.message ? (
        <div
          aria-live="polite"
          className={
            actionState.status === "error" ? "sync-message sync-message--error" : "sync-message"
          }
        >
          {actionState.message}
        </div>
      ) : null}

      <div className="valuation-lab-grid">
        <article className="valuation-card">
          <div className="valuation-card__heading">
            <FileText aria-hidden="true" size={17} />
            <strong>Memo 来源</strong>
          </div>
          {latestMemo ? (
            <>
              <dl className="valuation-input-grid">
                <MetricFact label="Memo" value={`v${latestMemo.version_no}`} />
                <MetricFact label="参数配置" value={formatConfigVersion(latestMemo.config_version)} />
                <MetricFact label="生成时间" value={formatDateTime(latestMemo.created_at)} />
                <MetricFact label="来源视角" value={`${latestMemo.source_analyst_run_ids.length} 个`} />
                <MetricFact label="状态" value={latestMemo.status} />
              </dl>
              {renderMemoListSection("估值假设队列", readValuationQueue(latestMemo))}
            </>
          ) : (
            <div className="inline-empty">需要先生成最新综合备忘录。</div>
          )}
        </article>

        <article className="valuation-card">
          <div className="valuation-card__heading">
            <ShieldCheck aria-hidden="true" size={17} />
            <strong>输入完整度</strong>
          </div>
          <dl className="valuation-input-grid">
            <MetricFact label="最新期间" value={financialEvidencePack.latest_period ?? "待更新"} />
            <MetricFact
              label="估值草稿"
              value={latestValuationRun ? `#${latestValuationRun.id}` : "待生成"}
            />
            <MetricFact
              label="状态"
              value={formatValuationRunStatus(latestValuationRun?.status)}
            />
            <MetricFact
              label="置信度"
              value={
                latestValuationRun?.confidence === null || latestValuationRun?.confidence === undefined
                  ? "待计算"
                  : formatPercent(latestValuationRun.confidence)
              }
            />
          </dl>
          <ValuationGapList gaps={inputGaps} />
        </article>
      </div>

      {latestValuationRun ? (
        <>
          <article className="valuation-card">
            <div className="valuation-card__heading">
              <BrainCircuit aria-hidden="true" size={17} />
              <strong>估值输入</strong>
            </div>
            <dl className="valuation-input-grid valuation-input-grid--wide">
              <MetricFact
                label="收入基准"
                value={formatFinancialSummaryMoney(valuationInputs.base_revenue)}
              />
              <MetricFact
                label="净利润基准"
                value={formatFinancialSummaryMoney(valuationInputs.base_net_profit)}
              />
              <MetricFact
                label="自由现金流基准"
                value={formatFinancialSummaryMoney(valuationInputs.base_free_cash_flow)}
              />
              <MetricFact
                label="资本开支"
                value={formatFinancialSummaryMoney(valuationInputs.capital_expenditure)}
              />
              <MetricFact
                label="货币资金"
                value={formatFinancialSummaryMoney(valuationInputs.cash_and_equivalents)}
              />
              <MetricFact
                label="有息负债"
                value={formatFinancialSummaryMoney(valuationInputs.interest_bearing_debt)}
              />
              <MetricFact
                label="股份数"
                value={formatShareCount(valuationInputs.shares_outstanding)}
              />
              <MetricFact label="数据期间" value={String(valuationInputs.latest_period ?? "待更新")} />
              </dl>
            </article>

          <ValuationNormalizationAudit
            audit={normalizationAudit}
            growthBasis={growthBasis}
            valuationInputs={valuationInputs}
          />

          <article className="valuation-card">
            <div className="valuation-card__heading">
              <SlidersHorizontal aria-hidden="true" size={17} />
              <strong>场景参数</strong>
            </div>
            <div className="valuation-assumption-grid">
              {valuationScenarioNames.map((scenarioName) => (
                <div className="valuation-scenario-card" key={scenarioName}>
                  <strong>{valuationScenarioLabels[scenarioName]}</strong>
                  {valuationAssumptionFields.map((field) => (
                    <label key={field.key}>
                      <span>{field.label}</span>
                      <input
                        type="number"
                        step="0.1"
                        value={formatAssumptionInputValue(scenarioDraft[scenarioName][field.key])}
                        onChange={(event) =>
                          updateScenarioDraft(scenarioName, field.key, event.currentTarget.value)
                        }
                      />
                    </label>
                  ))}
                </div>
              ))}
            </div>
            <div className="valuation-model-weight-section">
              <div className="valuation-model-weight-heading">
                <strong>模型配比</strong>
                <span className={modelWeightValidation ? "valuation-weight-total--error" : ""}>
                  合计 {formatDraftPercent(modelWeightTotal)}
                </span>
              </div>
              <div className="valuation-model-weight-grid">
                {valuationModelWeightFields.map((field) => (
                  <label key={field.key}>
                    <span>{field.label}</span>
                    <span className="valuation-model-weight-input">
                      <input
                        aria-label={`${field.label}权重`}
                        aria-invalid={modelWeightValidation ? "true" : "false"}
                        type="number"
                        min="0"
                        max="100"
                        step="1"
                        value={formatAssumptionInputValue(modelWeightsDraft[field.key])}
                        onChange={(event) =>
                          updateModelWeightDraft(field.key, event.currentTarget.value)
                        }
                      />
                      <span>%</span>
                    </span>
                  </label>
                ))}
              </div>
              {modelWeightValidation ? (
                <div className="valuation-weight-error" role="alert">
                  {modelWeightValidation}
                </div>
              ) : null}
            </div>
            <div className="valuation-action-row">
              <button
                className="panel-action"
                type="button"
                aria-busy={isSaving}
                disabled={isSaving || Boolean(modelWeightValidation)}
                onClick={() =>
                  onRecalculate(
                    latestValuationRun.id,
                    buildValuationAssumptionPayload(scenarioDraft, modelWeightsDraft)
                  )
                }
                title="确认当前参数并计算估值"
              >
                <Save aria-hidden="true" size={15} />
                <span>{isSaving ? "计算中" : "确认参数并计算"}</span>
              </button>
            </div>
          </article>

          <article className="valuation-card">
            <div className="valuation-card__heading">
              <BrainCircuit aria-hidden="true" size={17} />
              <strong>008 规则到参数审计</strong>
            </div>
            <dl className="valuation-input-grid">
              <MetricFact
                label="动态安全边际"
                value={dynamicSafetyMargin === null ? "待计算" : formatPercent(dynamicSafetyMargin)}
              />
                <MetricFact
                  label="规则贡献"
                  value={`${currentSafetyMarginContributions.length} / 32`}
                />
                <MetricFact label="分析师覆盖" value={`${orderedAnalystWeights.length} / 8`} />
              </dl>
              {hasLegacyAnalystMatrix ? (
                <div className="sync-message">
                  此历史估值包含已退出的分析师或旧规则合同；原始快照继续保留，活动审计区只展示当前 8 人 32 规则合同中的兼容条目。
                </div>
              ) : null}
              {orderedAnalystWeights.length > 0 ? (
                <div className="valuation-method-list">
                  {orderedAnalystWeights.map((analyst) => {
                    const analystRules = currentRuleImpacts.filter(
                      (rule) => rule.source_run_id === analyst.source_run_id
                    );
                  return (
                    <div key={String(analyst.source_run_id)}>
                      <strong>
                        {String(analyst.profile_name ?? analyst.profile_id)} · 权重 {formatPercent(readNumber(analyst.weight))}
                      </strong>
                      <ul className="compact-fact-list">
                        {analystRules.map((rule) => (
                          <li key={`${String(rule.source_run_id)}-${String(rule.rule_id)}`}>
                            {String(rule.rule_label ?? rule.rule_id)}：{formatRuleStatus(rule.status)}；
                            维度贡献 {formatRuleDimensionContributions(rule, dimensionContributions)}；
                              安全边际贡献 {formatPercent(readSafetyMarginContribution(rule, currentSafetyMarginContributions))}
                          </li>
                        ))}
                      </ul>
                    </div>
                  );
                })}
              </div>
            ) : (
              <div className="inline-empty">当前没有可用的最新成功分析师规则矩阵。</div>
            )}
          </article>

          {isCalculated ? (
          <div className="valuation-lab-grid">
            <article className="valuation-card">
              <div className="valuation-card__heading">
                <BarChart3 aria-hidden="true" size={17} />
                <strong>综合区间</strong>
              </div>
              <dl className="valuation-range-grid">
                {valuationScenarioNames.map((scenarioName) => (
                  <MetricFact
                    key={scenarioName}
                    label={valuationScenarioLabels[scenarioName]}
                    value={formatValuationRangeItem(
                      readNumber(totalEquityValue[scenarioName]),
                      readNumber(perShareValue[scenarioName])
                    )}
                  />
                ))}
              </dl>
              {modelWeighting.length > 0 ? (
                <ul className="compact-fact-list">
                  {modelWeighting.map((item) => (
                    <li key={String(item.method)}>
                      {formatMethodName(item.method)} 权重 {formatPercent(readNumber(item.weight))}
                    </li>
                  ))}
                </ul>
              ) : null}
              {dispersionWarning.message ? (
                <p className="valuation-warning">{String(dispersionWarning.message)}</p>
              ) : null}
            </article>

            <article className="valuation-card">
              <div className="valuation-card__heading">
                <Square aria-hidden="true" size={17} />
                <strong>单模型交叉验证</strong>
              </div>
              <div className="valuation-method-list">
                {methodResults.map((methodResult) => (
                  <ValuationMethodResult key={String(methodResult.method)} methodResult={methodResult} />
                ))}
              </div>
            </article>
          </div>
          ) : (
            <div className="inline-empty">模型建议参数正在等待用户确认，尚未生成内在价值结果。</div>
          )}

          {confidenceReasons.length > 0 ? (
            <article className="valuation-card">
              <div className="valuation-card__heading">
                <ShieldCheck aria-hidden="true" size={17} />
                <strong>置信度说明</strong>
              </div>
              <ul className="compact-fact-list">
                {confidenceReasons.map((reason) => (
                  <li key={reason}>{reason}</li>
                ))}
              </ul>
            </article>
          ) : null}
        </>
      ) : (
        <div className="inline-empty">
          暂无无锚定估值草稿。生成草稿后可编辑折现率、永续增长率和增长假设。
        </div>
      )}
    </section>
  );
}

type PriceDecisionPanelProps = {
  company: Company;
  latestValuationRun: ValuationRun | null;
  valuationHistory: ValuationRunListResponse;
  latestRun: PriceDecisionRun | null;
  history: PriceDecisionListResponse;
  actionState: PriceDecisionActionState;
  deleteState: PriceDecisionDeleteState;
  onGenerate: (valuationRunId: number, safetyMarginOverride: number | null) => void;
  onDelete: (runId: number) => void;
  onOpenValuation: () => void;
  onRefreshCompany: () => void;
};

function PriceDecisionPanel({
  company,
  latestValuationRun,
  valuationHistory,
  latestRun,
  history,
  actionState,
  deleteState,
  onGenerate,
  onDelete,
  onOpenValuation,
  onRefreshCompany
}: PriceDecisionPanelProps) {
  const [useOverride, setUseOverride] = useState(
    latestRun?.safety_margin_override !== null && latestRun?.safety_margin_override !== undefined
  );
  const [overridePercent, setOverridePercent] = useState(() =>
    latestRun?.safety_margin_override === null || latestRun?.safety_margin_override === undefined
      ? ""
      : String(latestRun.safety_margin_override * 100)
  );
  const [selectedHistoryId, setSelectedHistoryId] = useState<number | null>(null);

  useEffect(() => {
    const override = latestRun?.safety_margin_override;
    setUseOverride(override !== null && override !== undefined);
    setOverridePercent(override === null || override === undefined ? "" : String(override * 100));
  }, [latestRun]);

  const calculatedValuation = [latestValuationRun, ...valuationHistory.items].find(
    (run, index, runs) =>
      run !== null &&
      runs.findIndex((candidate) => candidate?.id === run.id) === index &&
      run.results.status === "calculated_after_user_confirmation"
  ) ?? null;
  const selectedHistoryRun = history.items.find((run) => run.id === selectedHistoryId) ?? null;
  const parsedOverride = overridePercent.trim() === "" ? Number.NaN : Number(overridePercent);
  const overrideError =
    useOverride && (!Number.isFinite(parsedOverride) || parsedOverride < 10 || parsedOverride > 50)
      ? "覆盖安全边际必须位于 10%-50%。"
      : null;
  const missingValuation = calculatedValuation === null;
  const missingPrice = company.current_price === null || company.current_price <= 0;
  const missingPriceTime = company.market_data_updated_at === null;
  const isSaving = actionState.status === "saving";

  return (
    <section className="data-panel price-decision-panel" aria-labelledby="price-decision-heading">
      <div className="data-panel__heading">
        <div>
          <Scale aria-hidden="true" size={20} />
          <h3 id="price-decision-heading">价格对照与投资决策</h3>
        </div>
        <div className="data-panel__actions">
          <span>011_v1</span>
          <button
            className="panel-action"
            type="button"
            disabled={missingValuation || missingPrice || missingPriceTime || isSaving || Boolean(overrideError)}
            onClick={() => {
              if (calculatedValuation) {
                onGenerate(
                  calculatedValuation.id,
                  useOverride ? parsedOverride / 100 : null
                );
              }
            }}
          >
            <RefreshCw aria-hidden="true" size={15} />
            <span>{isSaving ? "计算中" : latestRun ? "重新计算" : "生成价格决策"}</span>
          </button>
        </div>
      </div>

      {actionState.message ? (
        <div
          aria-live="polite"
          className={
            actionState.status === "error" ? "sync-message sync-message--error" : "sync-message"
          }
        >
          {actionState.message}
        </div>
      ) : null}
      {deleteState.message ? (
        <div
          aria-live="polite"
          className={
            deleteState.status === "error" ? "sync-message sync-message--error" : "sync-message"
          }
        >
          {deleteState.message}
        </div>
      ) : null}

      {missingValuation ? (
        <div className="price-decision-guidance" role="status">
          <strong>缺少已完成计算的 010 估值</strong>
          <p>先在无锚定估值中确认参数并计算，估值记录保持 draft 不影响价格决策。</p>
          <button className="panel-action" type="button" onClick={onOpenValuation}>
            <Calculator aria-hidden="true" size={15} />
            <span>前往无锚定估值</span>
          </button>
        </div>
      ) : null}
      {missingPrice || missingPriceTime ? (
        <div className="price-decision-guidance" role="status">
          <strong>{missingPrice ? "缺少当前价格" : "缺少价格更新时间"}</strong>
          <p>先更新公司基本信息和行情数据，再生成价格决策。</p>
          <button className="panel-action" type="button" onClick={onRefreshCompany}>
            <RefreshCw aria-hidden="true" size={15} />
            <span>更新公司行情</span>
          </button>
        </div>
      ) : null}

      <div className="price-decision-context">
        <article className="valuation-card">
          <div className="valuation-card__heading">
            <Calculator aria-hidden="true" size={17} />
            <strong>本次绑定</strong>
          </div>
          <dl className="valuation-input-grid">
            <MetricFact
              label="估值版本"
              value={calculatedValuation ? `#${calculatedValuation.id}` : "待完成"}
            />
            <MetricFact
              label="参数配置"
              value={formatConfigVersion(calculatedValuation?.config_version)}
            />
            <MetricFact
              label="估值结果"
              value={
                calculatedValuation?.results.status === "calculated_after_user_confirmation"
                  ? "已确认并计算"
                  : "待完成"
              }
            />
            <MetricFact label="当前价格" value={formatPrice(company.current_price)} />
            <MetricFact
              label="价格时间"
              value={company.market_data_updated_at ? formatDateTime(company.market_data_updated_at) : "待更新"}
            />
          </dl>
        </article>

        <article className="valuation-card">
          <div className="valuation-card__heading">
            <SlidersHorizontal aria-hidden="true" size={17} />
            <strong>动态安全边际</strong>
          </div>
          <dl className="valuation-input-grid">
            <MetricFact
              label="系统建议值"
              value={latestRun ? formatPercent(latestRun.suggested_safety_margin) : "生成后显示"}
            />
            <MetricFact
              label="用户覆盖值"
              value={
                latestRun?.safety_margin_override === null || latestRun?.safety_margin_override === undefined
                  ? "未覆盖"
                  : formatPercent(latestRun.safety_margin_override)
              }
            />
            <MetricFact
              label="最终安全边际"
              value={latestRun ? formatPercent(latestRun.effective_safety_margin) : "待计算"}
            />
          </dl>
          <label className="price-decision-override-toggle">
            <input
              type="checkbox"
              checked={useOverride}
              onChange={(event) => setUseOverride(event.currentTarget.checked)}
            />
            <span>手动覆盖安全边际</span>
          </label>
          {useOverride ? (
            <label className="price-decision-override-input">
              <span>覆盖安全边际（%）</span>
              <span>
                <input
                  aria-label="覆盖安全边际（%）"
                  aria-invalid={Boolean(overrideError)}
                  type="number"
                  min="10"
                  max="50"
                  step="0.1"
                  value={overridePercent}
                  onChange={(event) => setOverridePercent(event.currentTarget.value)}
                />
                <span>%</span>
              </span>
            </label>
          ) : null}
          {overrideError ? <p className="valuation-weight-error" role="alert">{overrideError}</p> : null}
        </article>
      </div>

      {latestRun ? <PriceDecisionResult run={latestRun} /> : (
        <div className="inline-empty">
          尚未生成价格决策。系统只给出建议买入上限和价格状态，不推断持仓或仓位。
        </div>
      )}

      <article className="price-decision-history" aria-label="价格决策历史记录">
        <div className="memo-latest__heading">
          <strong>历史版本</strong>
          <span>{history.total} 条</span>
        </div>
        {history.items.length > 0 ? (
          <ul>
            {history.items.map((run) => (
              <li key={run.id}>
                <div>
                  <strong>v{run.version_no} · {run.price_status}</strong>
                  <span>估值 #{run.valuation_run_id} · {formatDateTime(run.created_at)}</span>
                </div>
                <button
                  className="panel-action panel-action--icon"
                  type="button"
                  title={`查看价格决策 v${run.version_no}`}
                  aria-label={`查看价格决策 v${run.version_no}`}
                  onClick={() => setSelectedHistoryId((current) => current === run.id ? null : run.id)}
                >
                  {selectedHistoryId === run.id ? <ChevronDown aria-hidden="true" size={15} /> : <ChevronRight aria-hidden="true" size={15} />}
                  <span>{selectedHistoryId === run.id ? "收起" : "查看"}</span>
                </button>
                <button
                  className="panel-action panel-action--danger panel-action--icon"
                  type="button"
                  title={`删除价格决策 v${run.version_no}`}
                  aria-label={`删除价格决策 v${run.version_no}`}
                  disabled={deleteState.status === "deleting"}
                  onClick={() => onDelete(run.id)}
                >
                  <Trash2 aria-hidden="true" size={15} />
                  <span>{deleteState.status === "deleting" && deleteState.runId === run.id ? "删除中" : "删除"}</span>
                </button>
              </li>
            ))}
          </ul>
        ) : (
          <div className="inline-empty inline-empty--compact">暂无历史版本。</div>
        )}
        {selectedHistoryRun ? <PriceDecisionResult run={selectedHistoryRun} compact /> : null}
      </article>
    </section>
  );
}

function PriceDecisionResult({ run, compact = false }: { run: PriceDecisionRun; compact?: boolean }) {
  const memoSnapshot = readPlainRecord(run.input_snapshot.memo);
  return (
    <article className={compact ? "price-decision-result price-decision-result--compact" : "price-decision-result"}>
      <div className="price-decision-result__heading">
        <div>
          <strong>{run.price_status}</strong>
          <span>估值 #{run.valuation_run_id} · Memo v{String(memoSnapshot.version_no ?? run.memo_id)} · {formatConfigVersion(run.config_version)}</span>
        </div>
        <span className={`price-decision-status price-decision-status--${priceDecisionStatusTone(run.price_status)}`}>
          {run.price_status}
        </span>
      </div>
      <dl className="price-decision-key-metrics">
        <MetricFact label="当前价格" value={formatPrice(run.current_price)} />
        <MetricFact label="建议买入上限" value={formatPrice(run.suggested_buy_price)} />
        <MetricFact label="当前安全边际" value={formatSignedPercent(run.current_margin)} />
        <MetricFact label="最终安全边际" value={formatPercent(run.effective_safety_margin)} />
      </dl>
      <div className="price-decision-scenarios">
        {valuationScenarioNames.map((scenario) => (
          <div key={scenario}>
            <strong>{valuationScenarioLabels[scenario]}</strong>
            <span>内在价值 {formatPrice(run.intrinsic_values_per_share[scenario])}</span>
            <span>买入价 {formatPrice(run.scenario_buy_prices[scenario])}</span>
          </div>
        ))}
      </div>
      <dl className="valuation-input-grid">
        <MetricFact label="价格时间" value={formatDateTime(run.market_data_updated_at)} />
        <MetricFact label="生成时间" value={formatDateTime(run.created_at)} />
      </dl>
    </article>
  );
}

function priceDecisionStatusTone(status: string): "target" | "below" | "range" | "above" {
  if (status === "达到目标安全边际") return "target";
  if (status === "低于内在价值但安全边际不足") return "below";
  if (status === "处于估值区间上半部") return "range";
  return "above";
}

function formatSignedPercent(value: number): string {
  return `${value >= 0 ? "+" : ""}${(value * 100).toFixed(2)}%`;
}

function formatSignedNumber(value: number): string {
  return `${value >= 0 ? "+" : ""}${value.toFixed(2)}`;
}

function formatConfigVersion(version: number | null | undefined): string {
  return version === null || version === undefined ? "内置参数" : `参数 v${version}`;
}

function MemoPreparationPanel({
  memoPreparation,
  latestMemo,
  memoHistory,
  generateState,
  deleteState,
  archiveState,
  onGenerateMemo,
  onDeleteMemo,
  onArchiveMemo
}: MemoPreparationPanelProps) {
  const isGenerating = generateState.status === "generating";
  const isDeleting = deleteState.status === "deleting";
  const isArchiving = archiveState.status === "archiving";
  const [selectedHistoryMemoId, setSelectedHistoryMemoId] = useState<number | null>(null);
  const selectedHistoryMemo =
    memoHistory.items.find((memo) => memo.id === selectedHistoryMemoId) ?? null;

  return (
    <section className="data-panel memo-prep-panel" aria-labelledby="memo-prep-heading">
      <div className="data-panel__heading">
        <div>
          <FileText aria-hidden="true" size={20} />
          <h3 id="memo-prep-heading">综合备忘录准备区</h3>
        </div>
        <div className="data-panel__actions">
          <span>{memoPreparation.successfulProfiles.length} 个可用视角</span>
          <button
            className="panel-action"
            type="button"
            title="生成综合投资备忘录"
            disabled={isGenerating}
            onClick={onGenerateMemo}
          >
            <PlayCircle aria-hidden="true" size={15} />
            <span>{isGenerating ? "生成中" : "生成备忘录"}</span>
          </button>
        </div>
      </div>

      {generateState.message ? (
        <div
          className={
            generateState.status === "error"
              ? "sync-message sync-message--error"
              : "sync-message"
          }
        >
          {generateState.message}
        </div>
      ) : null}

      {deleteState.message ? (
        <div
          className={
            deleteState.status === "error" ? "sync-message sync-message--error" : "sync-message"
          }
        >
          {deleteState.message}
        </div>
      ) : null}

      {archiveState.message ? (
        <div
          className={
            archiveState.status === "error" ? "sync-message sync-message--error" : "sync-message"
          }
        >
          {archiveState.message}
        </div>
      ) : null}

      <div className="memo-latest">
        <div className="memo-latest__heading">
          <strong>最新综合备忘录</strong>
          {latestMemo ? (
            <span>
              v{latestMemo.version_no} · {formatConfigVersion(latestMemo.config_version)} · {formatDateTime(latestMemo.created_at)}
            </span>
          ) : null}
        </div>
        {latestMemo ? (
          <article>
            <h4>{latestMemo.title}</h4>
            <p>{readMemoExecutiveSummary(latestMemo)}</p>
            {renderMemoListSection("核心判断", latestMemo.sections.core_thesis)}
            {renderMemoListSection("关键风险", latestMemo.sections.key_risks)}
            {renderMemoListSection("估值输入队列", readValuationQueue(latestMemo))}
          </article>
        ) : (
          <div className="inline-empty">暂无综合投资备忘录</div>
        )}
      </div>

      <div className="memo-history" aria-label="综合投资备忘录历史记录">
        <div className="memo-latest__heading">
          <strong>历史分析记录</strong>
          <span>{memoHistory.total} 条</span>
        </div>
        {memoHistory.items.length > 0 ? (
          <ul>
            {memoHistory.items.map((memo) => {
              const isDeletingMemo = isDeleting && deleteState.memoId === memo.id;
              const isArchivingMemo = isArchiving && archiveState.memoId === memo.id;
              return (
                <li key={memo.id}>
                  <div>
                    <strong>
                      v{memo.version_no} {memo.is_latest ? "最新" : ""}
                    </strong>
                    <span>{formatDateTime(memo.created_at)}</span>
                    <p>{memo.title}</p>
                  </div>
                  <button
                    className="icon-action"
                    type="button"
                    title={`查看备忘录 v${memo.version_no}`}
                    aria-label={`查看备忘录 v${memo.version_no}`}
                    onClick={() =>
                      setSelectedHistoryMemoId((currentId) =>
                        currentId === memo.id ? null : memo.id
                      )
                    }
                  >
                    <FileText aria-hidden="true" size={15} />
                    <span>{selectedHistoryMemoId === memo.id ? "收起" : "查看"}</span>
                  </button>
                  <button
                    className="icon-action"
                    type="button"
                    title={`归档备忘录 v${memo.version_no}`}
                    aria-label={`归档备忘录 v${memo.version_no}`}
                    disabled={isDeleting || isArchiving}
                    onClick={() => onArchiveMemo(memo.id)}
                  >
                    <Archive aria-hidden="true" size={15} />
                    <span>{isArchivingMemo ? "归档中" : "归档"}</span>
                  </button>
                  <button
                    className="icon-action"
                    type="button"
                    title={`删除备忘录 v${memo.version_no}`}
                    aria-label={`删除备忘录 v${memo.version_no}`}
                    disabled={isDeleting || isArchiving}
                    onClick={() => onDeleteMemo(memo.id)}
                  >
                    <Trash2 aria-hidden="true" size={15} />
                    <span>{isDeletingMemo ? "删除中" : "删除"}</span>
                  </button>
                </li>
              );
            })}
          </ul>
        ) : (
          <div className="inline-empty">暂无历史分析记录</div>
        )}
        {selectedHistoryMemo ? (
          <article className="memo-history-detail">
            <h4>
              v{selectedHistoryMemo.version_no} {selectedHistoryMemo.title}
            </h4>
            <p>{readMemoExecutiveSummary(selectedHistoryMemo)}</p>
            {renderMemoListSection("核心判断", selectedHistoryMemo.sections.core_thesis)}
            {renderMemoListSection("关键风险", selectedHistoryMemo.sections.key_risks)}
            {renderMemoListSection("数据缺口", selectedHistoryMemo.sections.data_gaps)}
            {renderMemoListSection("估值输入队列", readValuationQueue(selectedHistoryMemo))}
          </article>
        ) : null}
      </div>

      <div className="memo-prep-grid">
        <MemoPrepBlock
          title="可用于综合的成功视角"
          items={memoPreparation.successfulProfiles}
          emptyText="暂无成功分析师视角"
        />
        <MemoPrepBlock
          title="缺失或失败视角"
          items={[...memoPreparation.missingProfiles, ...memoPreparation.failedProfiles]}
          emptyText="暂无缺失或失败视角"
        />
        <MemoPrepBlock
          title="风险汇总"
          items={memoPreparation.risks}
          emptyText="暂无分析师风险输出"
        />
        <MemoPrepBlock
          title="反方证据"
          items={memoPreparation.counterEvidence}
          emptyText="暂无反方证据"
        />
        <MemoPrepBlock
          title="数据缺口"
          items={memoPreparation.dataGaps}
          emptyText="暂无数据缺口"
        />
        <MemoPrepBlock
          title="估值假设建议"
          items={memoPreparation.valuationAssumptions}
          emptyText="暂无估值假设建议"
        />
      </div>
    </section>
  );
}

function MemoPrepBlock({
  title,
  items,
  emptyText
}: {
  title: string;
  items: string[];
  emptyText: string;
}) {
  return (
    <div className="memo-prep-block">
      <strong>{title}</strong>
      {items.length > 0 ? (
        <ul>
          {items.slice(0, 8).map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      ) : (
        <p>{emptyText}</p>
      )}
    </div>
  );
}

function renderMemoListSection(title: string, value: unknown) {
  const items = normalizeStringList(value);
  if (items.length === 0) {
    return null;
  }

  return (
    <div className="memo-section">
      <strong>{title}</strong>
      <ul>
        {items.slice(0, 5).map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
    </div>
  );
}

function readMemoExecutiveSummary(memo: InvestmentMemo): string {
  const value = memo.sections.executive_summary;
  return typeof value === "string" && value.trim() ? value : "暂无摘要";
}

function readValuationQueue(memo: InvestmentMemo): string[] {
  const queue = memo.sections.valuation_assumption_queue;
  if (!Array.isArray(queue)) {
    return [];
  }

  return queue
    .map((item) => {
      if (!item || typeof item !== "object") {
        return null;
      }
      const record = item as Record<string, unknown>;
      const reason = typeof record.reason === "string" ? record.reason.trim() : "";
      return reason || null;
    })
    .filter((item): item is string => Boolean(item));
}

function MetricFact({ label, value }: MetricFactProps) {
  return (
    <div>
      <dt>{label}</dt>
      <dd>{value}</dd>
    </div>
  );
}

function ValuationNormalizationAudit({
  audit,
  growthBasis,
  valuationInputs
}: {
  audit: Record<string, unknown>;
  growthBasis: Record<string, unknown>;
  valuationInputs: Record<string, unknown>;
}) {
  const periods = readRecordArray(audit.periods);
  const finalValues = readPlainRecord(audit.final_values);
  const fcfConversion = readPlainRecord(audit.fcf_conversion);
  const sourcePeriods = normalizeStringList(audit.source_periods);
  const ownerNormalization = readPlainRecord(valuationInputs.owner_earnings_normalization);
  const ownerComponents = readRecordArray(ownerNormalization.components);

  return (
    <article className="valuation-card valuation-normalization-audit">
      <div className="valuation-card__heading">
        <Scale aria-hidden="true" size={17} />
        <strong>财务基准正常化审计</strong>
      </div>
      <dl className="valuation-input-grid valuation-input-grid--wide">
        <MetricFact label="统一口径" value={formatNormalizationMethod(audit.method)} />
        <MetricFact
          label="置信度"
          value={formatNormalizationConfidence(valuationInputs.normalization_confidence)}
        />
        <MetricFact
          label="共同来源期间"
          value={sourcePeriods.length > 0 ? sourcePeriods.join("、") : "待补充"}
        />
        <MetricFact
          label="年度权重"
          value={formatWeightList(audit.annual_weights)}
        />
        <MetricFact label="正常化净利润" value={formatFinancialSummaryMoney(finalValues.net_profit)} />
        <MetricFact
          label="上限前自由现金流"
          value={formatFinancialSummaryMoney(fcfConversion.normalized_fcf_before_cap)}
        />
        <MetricFact
          label="上限后自由现金流"
          value={formatFinancialSummaryMoney(finalValues.free_cash_flow)}
        />
        <MetricFact label="正常化所有者盈余" value={formatFinancialSummaryMoney(finalValues.owner_earnings)} />
        <MetricFact
          label="上限前 FCF/净利润"
          value={formatRatio(readNumber(fcfConversion.fcf_to_net_profit_before_cap))}
        />
        <MetricFact
          label="上限后 FCF/净利润"
          value={formatRatio(readNumber(fcfConversion.fcf_to_net_profit_after_cap))}
        />
      </dl>

      <div className="valuation-normalization-subsection">
        <strong>增长基准链路</strong>
        <dl className="valuation-input-grid">
          <MetricFact label="原始增长值" value={formatPercent(readNumber(growthBasis.raw_growth_rate))} />
          <MetricFact label="增长来源" value={formatGrowthSource(growthBasis.growth_source)} />
          <MetricFact
            label="财务基准增长"
            value={formatPercent(readNumber(growthBasis.clamped_financial_base_growth_rate))}
          />
          <MetricFact
            label="现金流分析师增量"
            value={formatPercent(readNumber(growthBasis.analyst_delta_cash_flow_growth_rate))}
          />
          <MetricFact
            label="最终现金流增长"
            value={formatPercent(readNumber(growthBasis.final_base_cash_flow_growth_rate))}
          />
          <MetricFact
            label="最终所有者盈余增长"
            value={formatPercent(readNumber(growthBasis.final_base_owner_earnings_growth_rate))}
          />
        </dl>
      </div>

      {periods.length > 0 ? (
        <div className="valuation-normalization-subsection">
          <strong>期间组件</strong>
          <div className="valuation-normalization-period-list">
            {periods.map((period, index) => {
              const components = readPlainRecord(period.components);
              const owner = readPlainRecord(period.owner_earnings);
              return (
                <div className="valuation-normalization-period" key={`${String(period.period)}-${index}`}>
                  <MetricFact label="期间" value={String(period.period ?? "待补充")} />
                  <MetricFact label="权重" value={formatNullableWeight(period.weight)} />
                  <MetricFact label="净利润" value={formatFinancialSummaryMoney(components.net_profit)} />
                  <MetricFact label="自由现金流" value={formatFinancialSummaryMoney(components.free_cash_flow)} />
                  <MetricFact label="资本开支" value={formatFinancialSummaryMoney(components.capital_expenditure)} />
                  <MetricFact
                    label="所有者盈余"
                    value={
                      readNumber(owner.value) === null && audit.method === "ttm_adjusted"
                        ? "TTM汇总后计算"
                        : formatFinancialSummaryMoney(owner.value)
                    }
                  />
                </div>
              );
            })}
          </div>
          {ownerComponents.length > 0 ? (
            <div className="inline-empty">所有者盈余已按每个共同期间先计算，再按年度权重汇总。</div>
          ) : null}
        </div>
      ) : null}
    </article>
  );
}

function ValuationGapList({ gaps }: { gaps: Array<Record<string, unknown>> }) {
  if (gaps.length === 0) {
    return <p className="inline-empty">未发现估值实验室输入缺口。</p>;
  }

  return (
    <ul className="valuation-gap-list">
      {gaps.slice(0, 8).map((gap) => {
        const field = String(gap.field ?? "unknown");
        const severity = String(gap.severity ?? "medium");
        const reason = String(gap.reason ?? "需要补充估值输入。");
        return (
          <li key={`${field}-${severity}-${reason}`}>
            <span className={`valuation-gap-severity valuation-gap-severity--${severity}`}>
              {formatGapSeverity(severity)}
            </span>
            <strong>{field}</strong>
            <span>{reason}</span>
          </li>
        );
      })}
    </ul>
  );
}

function ValuationMethodResult({ methodResult }: { methodResult: Record<string, unknown> }) {
  const method = formatMethodName(methodResult.method);
  const status = String(methodResult.status ?? "needs_input");
  const scenarioValues = readPlainRecord(methodResult.scenario_values);
  const perShareValues = readPlainRecord(methodResult.per_share_values);
  const inputGaps = readRecordArray(methodResult.input_gaps);

  return (
    <article className="valuation-method">
      <div className="valuation-method__heading">
        <strong>{method}</strong>
        <span>{formatMethodStatus(status)}</span>
      </div>
      <p>{String(methodResult.reason ?? "等待估值输入。")}</p>
      {status === "success" ? (
        <dl className="valuation-range-grid">
          {valuationScenarioNames.map((scenarioName) => (
            <MetricFact
              key={scenarioName}
              label={valuationScenarioLabels[scenarioName]}
              value={formatValuationRangeItem(
                readNumber(scenarioValues[scenarioName]),
                readNumber(perShareValues[scenarioName])
              )}
            />
          ))}
        </dl>
      ) : null}
      {inputGaps.length > 0 ? <ValuationGapList gaps={inputGaps} /> : null}
    </article>
  );
}

function FinancialsPanel({
  financials,
  financialEvidencePack,
  syncState,
  deleteState,
  onSyncFinancials,
  onDeleteFinancialStatement
}: FinancialsPanelProps) {
  const isSyncing = syncState.status === "syncing";
  const isDeleting = deleteState.status === "deleting";
  const financialStatementGroups = useMemo(
    () => groupFinancialStatementsByPeriod(financials.items),
    [financials.items]
  );
  const [expandedPeriods, setExpandedPeriods] = useState<Set<string>>(new Set());

  useEffect(() => {
    setExpandedPeriods((currentPeriods) => {
      const availablePeriods = new Set(financialStatementGroups.map((group) => group.period));
      const nextPeriods = new Set(
        [...currentPeriods].filter((period) => availablePeriods.has(period))
      );
      if (nextPeriods.size === 0 && financialStatementGroups[0]) {
        nextPeriods.add(financialStatementGroups[0].period);
      }
      return nextPeriods;
    });
  }, [financialStatementGroups]);

  function toggleFinancialPeriod(period: string) {
    setExpandedPeriods((currentPeriods) => {
      const nextPeriods = new Set(currentPeriods);
      if (nextPeriods.has(period)) {
        nextPeriods.delete(period);
      } else {
        nextPeriods.add(period);
      }
      return nextPeriods;
    });
  }

  return (
    <section className="data-panel" aria-labelledby="financials-heading">
      <div className="data-panel__heading">
        <div>
          <BarChart3 aria-hidden="true" size={20} />
          <h3 id="financials-heading">财务数据</h3>
        </div>
        <div className="data-panel__actions">
          <span>{financials.total} 条</span>
          <button
            className="panel-action"
            type="button"
            title="搜索并同步财务数据"
            disabled={isSyncing}
            onClick={onSyncFinancials}
          >
            <Search aria-hidden="true" size={15} />
            <span>{isSyncing ? "搜索中" : "搜索财务数据"}</span>
          </button>
        </div>
      </div>

      {syncState.message ? (
        <div
          className={
            syncState.status === "error"
              ? "sync-message sync-message--error"
              : "sync-message"
          }
        >
          {syncState.message}
        </div>
      ) : null}

      {deleteState.message ? (
        <div
          className={
            deleteState.status === "error"
              ? "sync-message sync-message--error"
              : "sync-message"
          }
        >
          {deleteState.message}
        </div>
      ) : null}

      <FinancialEvidenceSummary financialEvidencePack={financialEvidencePack} />

      {financials.items.length === 0 ? (
        <div className="inline-empty">暂无财务数据</div>
      ) : (
        <div className="financial-period-list">
          {financialStatementGroups.map((group, groupIndex) => {
            const isExpanded = expandedPeriods.has(group.period);
            const panelId = `financial-period-${groupIndex}`;
            return (
              <section className="financial-period-group" key={group.period}>
                <button
                  className="financial-period-toggle"
                  type="button"
                  aria-expanded={isExpanded}
                  aria-controls={panelId}
                  onClick={() => toggleFinancialPeriod(group.period)}
                >
                  {isExpanded ? (
                    <ChevronDown aria-hidden="true" size={17} />
                  ) : (
                    <ChevronRight aria-hidden="true" size={17} />
                  )}
                  <span className="financial-period-title">{group.period}</span>
                  <span className="financial-period-meta">{group.statements.length} 张表</span>
                  <span className="financial-period-types">
                    {group.statements
                      .map(
                        (statement) =>
                          statementTypeLabels[statement.statement_type] ??
                          statement.statement_type
                      )
                      .join(" / ")}
                  </span>
                </button>
                {isExpanded ? (
                  <div className="financial-statement-grid" id={panelId}>
                    {group.statements.map((statement) => {
                      const isDeletingStatement =
                        isDeleting && deleteState.statementId === statement.id;
                      return (
                        <div className="financial-statement" key={statement.id}>
                          <div className="statement-heading">
                            <strong>{statement.period}</strong>
                            <span>
                              {statementTypeLabels[statement.statement_type] ??
                                statement.statement_type}
                            </span>
                            <span>{statement.currency}</span>
                            <button
                              className="icon-action icon-action--danger"
                              type="button"
                              title="删除财务数据"
                              aria-label={`删除财务数据：${statement.period}`}
                              disabled={isDeleting}
                              onClick={() => onDeleteFinancialStatement(statement.id)}
                            >
                              <Trash2 aria-hidden="true" size={15} />
                              <span>{isDeletingStatement ? "删除中" : "删除"}</span>
                            </button>
                          </div>
                          <dl className="financial-fields">
                            {orderedFinancialFields(statement.fields).map(([key, value]) => (
                              <div key={key}>
                                <dt>{fieldLabels[key] ?? key}</dt>
                                <dd>{formatFinancialValue(key, value, statement.currency)}</dd>
                              </div>
                            ))}
                          </dl>
                          <div className="financial-statement-footer">
                            {statement.source ? (
                              <span className="data-source">
                                来源：{sourceLabels[statement.source] ?? statement.source}
                              </span>
                            ) : (
                              <span />
                            )}
                            <span className="record-id">#{statement.id}</span>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                ) : null}
              </section>
            );
          })}
        </div>
      )}
    </section>
  );
}

type FinancialEvidenceSummaryProps = {
  financialEvidencePack: FinancialEvidencePack;
};

function FinancialEvidenceSummary({ financialEvidencePack }: FinancialEvidenceSummaryProps) {
  const latestFacts = getPackRecord(financialEvidencePack.financial_facts, "latest");
  const profitability = getPackRecord(financialEvidencePack.financial_metrics, "profitability");
  const growthQuality = getPackRecord(financialEvidencePack.financial_metrics, "growth_quality");
  const cashFlowQuality = financialEvidencePack.cash_flow_quality ?? {};
  const balanceSheetAdjustment = financialEvidencePack.balance_sheet_adjustment ?? {};
  const capitalAllocation = financialEvidencePack.capital_allocation ?? {};
  const financialFlags = readRecordArray(financialEvidencePack.financial_flags);
  const financialDataGaps = readRecordArray(financialEvidencePack.financial_data_gaps);

  return (
    <>
      <dl className="financial-evidence-summary" aria-label="财务证据概览">
        <MetricFact label="最新期间" value={financialEvidencePack.latest_period ?? "待更新"} />
        <MetricFact label="收入" value={formatFinancialSummaryMoney(latestFacts.revenue)} />
        <MetricFact label="净利润" value={formatFinancialSummaryMoney(latestFacts.net_profit)} />
        <MetricFact
          label="自由现金流"
          value={formatFinancialSummaryMoney(cashFlowQuality.free_cash_flow)}
        />
        <MetricFact
          label="货币资金"
          value={formatFinancialSummaryMoney(balanceSheetAdjustment.cash_and_equivalents)}
        />
        <MetricFact
          label="有息负债"
          value={formatFinancialSummaryMoney(balanceSheetAdjustment.interest_bearing_debt)}
        />
        <MetricFact
          label="净现金"
          value={formatFinancialSummaryMoney(balanceSheetAdjustment.net_cash)}
        />
        <MetricFact label="分红" value={formatFinancialSummaryMoney(capitalAllocation.dividend)} />
        <MetricFact label="ROE" value={formatFinancialSummaryPercent(profitability.roe)} />
        <MetricFact label="毛利率" value={formatFinancialSummaryPercent(profitability.gross_margin)} />
        <MetricFact label="净利率" value={formatFinancialSummaryPercent(profitability.net_margin)} />
        <MetricFact label="收入同比" value={formatFinancialSummaryPercent(growthQuality.revenue_yoy)} />
        <MetricFact label="净利润同比" value={formatFinancialSummaryPercent(growthQuality.net_profit_yoy)} />
        <MetricFact label="财务旗标" value={`${financialFlags.length} 项`} />
        <MetricFact label="数据缺口" value={`${financialDataGaps.length} 项`} />
      </dl>
      <FinancialEvidenceDetailList
        flags={financialFlags}
        gaps={financialDataGaps}
      />
    </>
  );
}

function FinancialEvidenceDetailList({
  flags,
  gaps
}: {
  flags: Array<Record<string, unknown>>;
  gaps: Array<Record<string, unknown>>;
}) {
  if (flags.length === 0 && gaps.length === 0) {
    return null;
  }

  return (
    <div className="financial-evidence-details" aria-label="财务旗标和数据缺口明细">
      {flags.length > 0 ? (
        <section className="financial-evidence-detail-section">
          <h4>财务旗标明细</h4>
          <ul className="financial-evidence-detail-list">
            {flags.map((flag, index) => {
              const severity = String(flag.severity ?? "info");
              const message = cleanDisplayText(
                String(flag.message ?? flag.code ?? "需要复核的财务提示。")
              );
              const period = cleanDisplayText(String(flag.period ?? ""));
              return (
                <li key={`${String(flag.code ?? "flag")}-${period}-${index}`}>
                  <span
                    className={`financial-evidence-badge financial-evidence-badge--${severity}`}
                  >
                    {formatFinancialFlagSeverity(severity)}
                  </span>
                  <strong>{period || "未标明期间"}</strong>
                  <span>{message}</span>
                </li>
              );
            })}
          </ul>
        </section>
      ) : null}

      {gaps.length > 0 ? (
        <section className="financial-evidence-detail-section">
          <h4>数据缺口明细</h4>
          <ul className="financial-evidence-detail-list">
            {gaps.map((gap, index) => {
              const field = String(gap.field ?? "unknown");
              const severity = String(gap.severity ?? "medium");
              const reason = cleanDisplayText(String(gap.reason ?? "需要补充财务输入。"));
              const neededBy = formatNeededByList(gap.needed_by);
              const proxyFields = normalizeStringList(gap.proxy_fields).map(
                (proxyField) => fieldLabels[proxyField] ?? proxyField
              );
              const replacementAvailable = Boolean(gap.replacement_available);
              const proxyText =
                replacementAvailable && proxyFields.length > 0
                  ? `已有替代口径：${proxyFields.join("、")}`
                  : null;
              return (
                <li key={`${field}-${severity}-${index}`}>
                  <span
                    className={`financial-evidence-badge financial-evidence-badge--${severity}`}
                  >
                    {formatGapSeverity(severity)}
                  </span>
                  <strong>{fieldLabels[field] ?? field}</strong>
                  <span>
                    {reason}
                    {neededBy ? ` 影响：${neededBy}。` : ""}
                    {proxyText ? ` ${proxyText}。` : ""}
                  </span>
                </li>
              );
            })}
          </ul>
        </section>
      ) : null}
    </div>
  );
}

type AnnouncementsPanelProps = {
  announcements: AnnouncementListResponse;
  syncState: AnnouncementSyncState;
  deleteState: AnnouncementDeleteState;
  summaryState: AnnouncementSummaryState;
  onSyncAnnouncements: () => void;
  onDeleteAnnouncement: (announcementId: number) => void;
  onSummarizeAnnouncement: () => void;
  onSummarizeDeepAnnouncements: () => void;
  onSummarizeSingleAnnouncement: (announcementId: number) => void;
};

function AnnouncementsPanel({
  announcements,
  syncState,
  deleteState,
  summaryState,
  onSyncAnnouncements,
  onDeleteAnnouncement,
  onSummarizeAnnouncement,
  onSummarizeDeepAnnouncements,
  onSummarizeSingleAnnouncement
}: AnnouncementsPanelProps) {
  const isSyncing = syncState.status === "syncing";
  const isDeleting = deleteState.status === "deleting";
  const isSummarizing = summaryState.status === "summarizing";
  const isQuickSummarizing = isSummarizing && summaryState.mode === "quick";
  const isDeepSummarizing = isSummarizing && summaryState.mode === "deep";

  return (
    <section className="data-panel" aria-labelledby="announcements-heading">
      <div className="data-panel__heading">
        <div>
          <FileText aria-hidden="true" size={20} />
          <h3 id="announcements-heading">公告区块</h3>
        </div>
        <div className="data-panel__actions">
          <span>{announcements.total} 条</span>
          <button
            className="panel-action"
            type="button"
            title="一键基于公告标题、分类、时间和来源生成快速关键词摘要"
            disabled={isSummarizing || announcements.items.length === 0}
            onClick={onSummarizeAnnouncement}
          >
            <BrainCircuit aria-hidden="true" size={15} />
            <span>{isQuickSummarizing ? "生成中" : "一键快速摘要"}</span>
          </button>
          <button
            className="panel-action"
            type="button"
            title="一键逐条读取公告原文并生成深度摘要，已深度摘要的公告会跳过"
            disabled={isSummarizing || announcements.items.length === 0}
            onClick={onSummarizeDeepAnnouncements}
          >
            <BrainCircuit aria-hidden="true" size={15} />
            <span>{isDeepSummarizing ? "生成中" : "一键深度摘要"}</span>
          </button>
          <button
            className="panel-action"
            type="button"
            title="搜索并同步公告"
            disabled={isSyncing}
            onClick={onSyncAnnouncements}
          >
            <Search aria-hidden="true" size={15} />
            <span>{isSyncing ? "搜索中" : "搜索公告"}</span>
          </button>
        </div>
      </div>

      {syncState.message ? (
        <div
          className={
            syncState.status === "error"
              ? "sync-message sync-message--error"
              : "sync-message"
          }
        >
          {syncState.message}
        </div>
      ) : null}

      {deleteState.message ? (
        <div
          className={
            deleteState.status === "error"
              ? "sync-message sync-message--error"
              : "sync-message"
          }
        >
          {deleteState.message}
        </div>
      ) : null}

      {summaryState.message ? (
        <div
          className={
            summaryState.status === "error"
              ? "sync-message sync-message--error"
              : "sync-message"
          }
        >
          {summaryState.message}
        </div>
      ) : null}

      {announcements.items.length === 0 ? (
        <div className="inline-empty">暂无公告</div>
      ) : (
        <ul className="announcement-list">
          {announcements.items.map((announcement) => {
            const isDeletingAnnouncement =
              isDeleting && deleteState.announcementId === announcement.id;
            const isSummarizingAnnouncement =
              summaryState.status === "summarizing" &&
              summaryState.announcementId === announcement.id;
            const displayStatus = getAnnouncementDisplayStatus(announcement);
            const keyFacts = Array.isArray(announcement.key_facts) ? announcement.key_facts : [];
            const tags = sanitizeAnnouncementTags(announcement.tags);
            return (
              <li className="announcement-row" key={announcement.id}>
                <div className="announcement-row__title">
                  <strong>{announcement.title}</strong>
                  <span>{formatDate(announcement.published_at)}</span>
                  <button
                    className="icon-action icon-action--danger"
                    type="button"
                    title="删除公告"
                    aria-label={`删除公告：${announcement.title}`}
                    disabled={isDeleting}
                    onClick={() => onDeleteAnnouncement(announcement.id)}
                  >
                    <Trash2 aria-hidden="true" size={15} />
                    <span>{isDeletingAnnouncement ? "删除中" : "删除"}</span>
                  </button>
                  <button
                    className="icon-action"
                    type="button"
                    title="读取公告原文并生成单条深度摘要"
                    aria-label={`深度摘要：${announcement.title}`}
                    disabled={isSummarizing || isDeleting}
                    onClick={() => onSummarizeSingleAnnouncement(announcement.id)}
                  >
                    <BrainCircuit aria-hidden="true" size={15} />
                    <span>{isSummarizingAnnouncement ? "生成中" : "深度摘要"}</span>
                  </button>
                </div>
                <div className="company-meta">
                  <span>ID #{announcement.id}</span>
                  <span>{announcement.category}</span>
                  <span>{announcementSummaryStatusLabels[displayStatus] ?? displayStatus}</span>
                  {announcement.source ? <span>来源 {announcement.source}</span> : null}
                  {announcement.impact_direction ? (
                    <span>
                      {impactDirectionLabels[announcement.impact_direction] ??
                        announcement.impact_direction}
                    </span>
                  ) : null}
                </div>
                {tags.length > 0 ? (
                  <div className="analyst-rule-chip-list" aria-label="公告标签">
                    {tags.slice(0, 8).map((tag) => (
                      <span key={tag}>{tag}</span>
                    ))}
                  </div>
                ) : null}
                {announcement.source_url ? (
                  <a
                    className="source-link"
                    href={announcement.source_url}
                    target="_blank"
                    rel="noreferrer"
                  >
                    查看来源
                  </a>
                ) : null}
                <p>{announcement.summary ?? "待后续智能摘要"}</p>
                {keyFacts.length > 0 ? (
                  <ul className="compact-fact-list">
                    {keyFacts.slice(0, 4).map((fact) => (
                      <li key={fact}>{fact}</li>
                    ))}
                  </ul>
                ) : null}
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}

type EvidencePanelProps = {
  evidence: EvidenceListResponse;
  modelConfig: ModelConfigStatus;
  searchState: EvidenceSearchState;
  importTextState: EvidenceImportTextState;
  modelSmokeTestState: ModelSmokeTestState;
  deleteState: EvidenceDeleteState;
  onSearchEvidence: () => void;
  onImportTextEvidence: (form: EvidenceImportTextForm) => void;
  onSmokeTestModel: () => void;
  onDeleteEvidence: (evidenceId: number) => void;
};

const sourceTypeLabels: Record<string, string> = {
  policy: "政策",
  industry_news: "行业新闻",
  company_news: "公司新闻",
  public_data: "公开数据",
  regulatory: "监管",
  web: "网络"
};

const impactDirectionLabels: Record<string, string> = {
  positive: "正面",
  neutral: "中性",
  negative: "负面",
  mixed: "混合",
  unknown: "未知"
};

const analysisStatusLabels: Record<string, string> = {
  model_analyzed: "模型已分析",
  search_lead: "搜索线索"
};

const announcementSummaryStatusLabels: Record<string, string> = {
  unprocessed: "未摘要",
  processing: "处理中",
  summarized: "已摘要",
  quick_summarized: "已快速摘要",
  deep_summarized: "已深度摘要",
  failed: "失败"
};

function EvidencePanel({
  evidence,
  modelConfig,
  searchState,
  importTextState,
  modelSmokeTestState,
  onSearchEvidence,
  onImportTextEvidence,
  onSmokeTestModel,
  deleteState,
  onDeleteEvidence
}: EvidencePanelProps) {
  const isSearching = searchState.status === "searching";
  const isImportingText = importTextState.status === "importing";
  const isTestingModel = modelSmokeTestState.status === "testing";
  const isDeleting = deleteState.status === "deleting";
  const [importTextForm, setImportTextForm] = useState<EvidenceImportTextForm>({
    title: "",
    content: "",
    source: "",
    source_url: "",
    published_at: "",
    source_type: "web",
    notes: ""
  });

  function updateImportTextForm<K extends keyof EvidenceImportTextForm>(
    key: K,
    value: EvidenceImportTextForm[K]
  ) {
    setImportTextForm((current) => ({ ...current, [key]: value }));
  }

  function submitImportTextForm(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    onImportTextEvidence(importTextForm);
    if (importTextForm.content.trim()) {
      setImportTextForm({
        title: "",
        content: "",
        source: "",
        source_url: "",
        published_at: "",
        source_type: "web",
        notes: ""
      });
    }
  }

  return (
    <section className="data-panel evidence-panel" aria-labelledby="evidence-heading">
      <div className="data-panel__heading">
        <div>
          <ShieldCheck aria-hidden="true" size={20} />
          <h3 id="evidence-heading">外部信息</h3>
        </div>
        <div className="data-panel__actions">
          <span>{evidence.total} 条</span>
          <button
            className="panel-action"
            type="button"
            title="模型连通性自检"
            disabled={isSearching || isImportingText || isTestingModel}
            onClick={onSmokeTestModel}
          >
            <BrainCircuit aria-hidden="true" size={15} />
            <span>{isTestingModel ? "自检中" : "模型自检"}</span>
          </button>
          <button
            className="panel-action"
            type="button"
            title="搜索外部信息"
            disabled={isSearching || isImportingText || isTestingModel}
            onClick={onSearchEvidence}
          >
            <Search aria-hidden="true" size={15} />
            <span>{isSearching ? "搜索中" : "搜索外部信息"}</span>
          </button>
        </div>
      </div>

      <dl className="model-config-grid" aria-label="当前模型配置状态">
        <div>
          <dt>provider</dt>
          <dd>{modelConfig.provider}</dd>
        </div>
        <div>
          <dt>base_url</dt>
          <dd title={modelConfig.base_url ?? "未配置"}>{modelConfig.base_url ?? "未配置"}</dd>
        </div>
        <div>
          <dt>model_name</dt>
          <dd>{modelConfig.model_name ?? "未配置"}</dd>
        </div>
        <div>
          <dt>wire_api</dt>
          <dd>{modelConfig.wire_api ?? "未配置"}</dd>
        </div>
        <div>
          <dt>api_key</dt>
          <dd>{modelConfig.api_key_configured ? "已配置" : "未配置"}</dd>
        </div>
      </dl>

      <form className="manual-evidence-form" onSubmit={submitImportTextForm}>
        <div className="manual-evidence-form__grid">
          <label>
            <span>标题</span>
            <input
              type="text"
              value={importTextForm.title}
              onChange={(event) => updateImportTextForm("title", event.target.value)}
            />
          </label>
          <label>
            <span>来源名称</span>
            <input
              type="text"
              value={importTextForm.source}
              onChange={(event) => updateImportTextForm("source", event.target.value)}
            />
          </label>
          <label>
            <span>来源链接</span>
            <input
              type="url"
              value={importTextForm.source_url}
              onChange={(event) => updateImportTextForm("source_url", event.target.value)}
            />
          </label>
          <label>
            <span>发布日期</span>
            <input
              type="date"
              value={importTextForm.published_at}
              onChange={(event) => updateImportTextForm("published_at", event.target.value)}
            />
          </label>
          <label>
            <span>来源类型</span>
            <select
              value={importTextForm.source_type}
              onChange={(event) =>
                updateImportTextForm("source_type", event.target.value as EvidenceSourceType)
              }
            >
              <option value="web">网络</option>
              <option value="policy">政策</option>
              <option value="industry_news">行业新闻</option>
              <option value="company_news">公司新闻</option>
              <option value="public_data">公开数据</option>
              <option value="regulatory">监管</option>
            </select>
          </label>
        </div>
        <label>
          <span>正文内容</span>
          <textarea
            required
            minLength={20}
            rows={5}
            value={importTextForm.content}
            onChange={(event) => updateImportTextForm("content", event.target.value)}
          />
        </label>
        <label>
          <span>备注</span>
          <input
            type="text"
            value={importTextForm.notes}
            onChange={(event) => updateImportTextForm("notes", event.target.value)}
          />
        </label>
        <div className="manual-evidence-form__actions">
          <button
            className="panel-action"
            type="submit"
            title="导入文本"
            disabled={isSearching || isImportingText || isTestingModel}
          >
            <FileText aria-hidden="true" size={15} />
            <span>{isImportingText ? "导入中" : "导入文本"}</span>
          </button>
        </div>
      </form>

      {importTextState.message ? (
        <div
          className={
            importTextState.status === "error"
              ? "sync-message sync-message--error"
              : "sync-message"
          }
        >
          {importTextState.message}
        </div>
      ) : null}

      {modelSmokeTestState.message ? (
        <div
          className={
            modelSmokeTestState.status === "error"
              ? "sync-message sync-message--error"
              : "sync-message"
          }
        >
          {modelSmokeTestState.message}
        </div>
      ) : null}

      {searchState.message ? (
        <div
          className={
            searchState.status === "error"
              ? "sync-message sync-message--error"
              : "sync-message"
          }
        >
          {searchState.message}
        </div>
      ) : null}

      {deleteState.message ? (
        <div
          className={
            deleteState.status === "error"
              ? "sync-message sync-message--error"
              : "sync-message"
          }
        >
          {deleteState.message}
        </div>
      ) : null}

      {evidence.items.length === 0 ? (
        <div className="inline-empty">暂无外部信息证据</div>
      ) : (
        <ul className="evidence-list">
          {evidence.items.map((item) => {
            const isDeletingItem = isDeleting && deleteState.evidenceId === item.id;
            const keyFacts = Array.isArray(item.key_facts) ? item.key_facts : [];
            const analysisStatus = item.analysis_status ?? "model_analyzed";
            const priceSensitive = item.price_sensitive ?? false;
            return (
              <li className="evidence-row" key={item.id}>
                <div className="evidence-row__header">
                  <span className="evidence-type">{sourceTypeLabels[item.source_type]}</span>
                  <strong>{item.title}</strong>
                  <span className="evidence-row__date">
                    {item.published_at ? formatDate(item.published_at) : "发布时间待复核"}
                  </span>
                  <button
                    className="icon-action icon-action--danger"
                    type="button"
                    title="删除外部信息"
                    aria-label={`删除外部信息：${item.title}`}
                    disabled={isDeleting}
                    onClick={() => onDeleteEvidence(item.id)}
                  >
                    <Trash2 aria-hidden="true" size={15} />
                    <span>{isDeletingItem ? "删除中" : "删除"}</span>
                  </button>
                </div>
              <div className="evidence-meta">
                <span>#{item.id}</span>
                <span>{analysisStatusLabels[analysisStatus] ?? analysisStatus}</span>
                <span>{priceSensitive ? "价格敏感已排除" : "基本面证据"}</span>
                <span>
                  来源：
                  {item.source_url ? (
                    <a className="source-link-inline" href={item.source_url} target="_blank" rel="noreferrer">
                      {item.source ?? "打开来源"}
                    </a>
                  ) : (
                    item.source ?? "未知"
                  )}
                </span>
                {analysisStatus === "model_analyzed" ? (
                  <>
                    <span>影响：{impactDirectionLabels[item.impact_direction]}</span>
                    <span>重要性 {formatImportanceScore(item.importance_score)}</span>
                    <span>可信度 {formatImportanceScore(item.credibility_score)}</span>
                  </>
                ) : (
                  <span>影响、重要性、可信度未完成模型分析</span>
                )}
              </div>
              <p>{item.summary}</p>
              {item.analysis_note ? <p className="evidence-note">{item.analysis_note}</p> : null}
              {keyFacts.length > 0 ? (
                <ul className="key-fact-list">
                  {keyFacts.map((fact) => (
                    <li key={fact}>{fact}</li>
                  ))}
                </ul>
              ) : null}
            </li>
          );
          })}
        </ul>
      )}
    </section>
  );
}

type AnalystPanelProps = {
  profiles: AnalystProfileListResponse;
  runs: AnalysisRunListResponse;
  failedRuns: AnalysisRunListResponse;
  runState: AnalystRunState;
  deleteState: AnalysisRunDeleteState;
  statusUpdateState: AnalysisRuleStatusUpdateState;
  onRunProfile: (profileId: string) => void;
  onRunAllProfiles: () => void;
  onStopRun: () => void;
  onDeleteRun: (runId: number) => void;
  onUpdateRuleStatus: (runId: number, ruleId: string, status: AnalystRuleStatus) => void;
};

const analystRuleStatusLabels: Record<string, string> = {
  pass: "通过",
  neutral: "中性",
  warn: "谨慎",
  fail: "不通过",
  unknown: "未知"
};

const analystRuleStatusOrder: AnalystRuleStatus[] = [
  "pass",
  "neutral",
  "unknown",
  "warn",
  "fail"
];

function AnalystPanel({
  profiles,
  runs,
  failedRuns,
  runState,
  onRunProfile,
  onRunAllProfiles,
  deleteState,
  statusUpdateState,
  onStopRun,
  onDeleteRun,
  onUpdateRuleStatus
}: AnalystPanelProps) {
  const isRunningAll = runState.status === "running_all";
  const isRunningAny = runState.status === "running" || runState.status === "running_all";
  const isDeletingRun = deleteState.status === "deleting";
  const profileIds = new Set(profiles.items.map((profile) => profile.id));
  const currentRuns = runs.items.filter(
    (run) => typeof run.analyst_profile === "string" && profileIds.has(run.analyst_profile)
  );
  const currentFailedRuns = failedRuns.items.filter(
    (run) => typeof run.analyst_profile === "string" && profileIds.has(run.analyst_profile)
  );
  const successfulProfileIds = new Set(
    currentRuns
      .map((run) => run.analyst_profile)
      .filter((profileId): profileId is string => Boolean(profileId))
  );
  const missingProfileCount = profiles.items.filter(
    (profile) => !successfulProfileIds.has(profile.id)
  ).length;
  const sharedAccountingEvents = collectSharedAccountingEvents(currentRuns);

  return (
    <section className="data-panel analyst-panel" aria-labelledby="analyst-view-heading">
      <div className="data-panel__heading">
        <div>
          <BrainCircuit aria-hidden="true" size={20} />
          <h3 id="analyst-view-heading">分析师视角</h3>
        </div>
        <div className="data-panel__actions">
          <span>{currentRuns.length} 个成功 run</span>
          {currentFailedRuns.length > 0 ? (
            <span>{currentFailedRuns.length} 个最近失败</span>
          ) : null}
          <button
            className="panel-action"
            type="button"
            title={
              missingProfileCount > 0
                ? "生成尚无成功 run 的分析师视角"
                : "所有分析师均已有成功 run"
            }
            disabled={isRunningAny || missingProfileCount === 0}
            onClick={onRunAllProfiles}
          >
            <PlayCircle aria-hidden="true" size={15} />
            <span>
              {isRunningAll
                ? "生成中"
                : missingProfileCount > 0
                  ? `生成缺失 (${missingProfileCount})`
                  : "均已生成"}
            </span>
          </button>
          {isRunningAny ? (
            <button
              className="panel-action panel-action--danger"
              type="button"
              title="停止本次分析师生成"
              onClick={onStopRun}
            >
              <Square aria-hidden="true" size={15} />
              <span>停止</span>
            </button>
          ) : null}
        </div>
      </div>

      {runState.message ? (
        <div
          className={
            runState.status === "error"
              ? "sync-message sync-message--error"
              : "sync-message"
          }
        >
          {runState.message}
        </div>
      ) : null}

      {deleteState.message ? (
        <div
          className={
            deleteState.status === "error"
              ? "sync-message sync-message--error"
              : "sync-message"
          }
        >
          {deleteState.message}
        </div>
      ) : null}

      {statusUpdateState.message ? (
        <div
          className={
            statusUpdateState.status === "error"
              ? "sync-message sync-message--error"
              : "sync-message"
          }
        >
          {statusUpdateState.message}
        </div>
      ) : null}

      <div className="analyst-profile-grid">
        {profiles.items.map((profile) => {
          const latestRun = runs.items.find((run) => run.analyst_profile === profile.id);
          const latestFailedRun = failedRuns.items.find(
            (run) => run.analyst_profile === profile.id
          );
          const shouldShowFailure =
            latestFailedRun !== undefined &&
            (latestRun === undefined || isRunNewer(latestFailedRun, latestRun));
          const isRunning = runState.status === "running" && runState.profileId === profile.id;
          const disableProfileRun = isRunningAny;
          const result = latestRun?.result;
          const ruleChecks = result?.rule_checks ?? [];
          const analysisBasisItems = result?.analysis_basis
            ? formatAnalysisBasis(result.analysis_basis)
            : [];
          const scoreExplanationItems = result?.score_explanations
            ? formatScoreExplanations(result.score_explanations)
            : [];

          return (
            <article className="analyst-profile-card" key={profile.id}>
              <div className="analyst-profile-card__heading">
                <div>
                  <strong>{profile.display_name}</strong>
                  <span>{profile.name}</span>
                </div>
                <button
                  className="panel-action"
                  type="button"
                  title={`生成${profile.display_name}视角`}
                  aria-label={`生成${profile.display_name}视角`}
                  disabled={disableProfileRun}
                  onClick={() => onRunProfile(profile.id)}
                >
                  <PlayCircle aria-hidden="true" size={15} />
                  <span>{isRunning ? "生成中" : "生成"}</span>
                </button>
              </div>

              <p>{profile.description}</p>

              <div className="analyst-rule-chip-list" aria-label={`${profile.display_name}规则`}>
                {profile.rules.map((rule) => (
                  <span key={rule.id}>{rule.label}</span>
                ))}
              </div>

              <details className="analyst-profile-details">
                <summary>框架详情</summary>
                <div className="analyst-profile-details__content">
                  <section>
                    <strong>投资哲学</strong>
                    <p>{profile.philosophy}</p>
                  </section>
                  <div className="analyst-profile-details__grid">
                    {[
                      ["核心逻辑", profile.core_logic],
                      ["决策顺序", profile.decision_sequence],
                      ["偏好证据", profile.preferred_evidence],
                      ["失败模式", profile.failure_modes],
                      ["分析焦点", profile.prompt_focus]
                    ].map(([title, items]) => (
                      <section key={title as string}>
                        <strong>{title}</strong>
                        <ul>
                          {((items as string[] | undefined) ?? []).map((item) => (
                            <li key={item}>{item}</li>
                          ))}
                        </ul>
                      </section>
                    ))}
                  </div>
                  <section className="analyst-rule-definitions">
                    <strong>规则判定口径</strong>
                    {profile.rules.map((rule) => (
                      <div className="analyst-rule-definition" key={rule.id}>
                        <div>
                          <strong>{rule.label}</strong>
                          <p>{rule.description}</p>
                        </div>
                        <dl>
                          {analystRuleStatusOrder.map((status) => (
                            <div className={`rule-rubric rule-rubric--${status}`} key={status}>
                              <dt>{analystRuleStatusLabels[status]}</dt>
                              <dd>{rule.status_rubric?.[status] ?? "未提供判定口径"}</dd>
                            </div>
                          ))}
                        </dl>
                      </div>
                    ))}
                  </section>
                </div>
              </details>

              {shouldShowFailure ? (
                <div className="analyst-run-failure">
                  <div className="analyst-run-meta">
                    <span>#{latestFailedRun.id}</span>
                    <span>{formatDateTime(latestFailedRun.created_at)}</span>
                    <span>{String(latestFailedRun.result.error_type ?? "failed")}</span>
                    <button
                      className="icon-action icon-action--danger"
                      type="button"
                      title="删除分析记录"
                      aria-label={`删除${profile.display_name}失败记录 #${latestFailedRun.id}`}
                      disabled={isDeletingRun}
                      onClick={() => onDeleteRun(latestFailedRun.id)}
                    >
                      <Trash2 aria-hidden="true" size={14} />
                      <span>
                        {deleteState.runId === latestFailedRun.id && isDeletingRun
                          ? "删除中"
                          : "删除记录"}
                      </span>
                    </button>
                  </div>
                  <strong>最近生成失败</strong>
                  <p>{getRunFailureMessage(latestFailedRun)}</p>
                </div>
              ) : null}

              {latestRun && result?.overview ? (
                <div className="analyst-run-result">
                  <div className="analyst-run-meta">
                    <span>#{latestRun.id}</span>
                    <span>{formatConfigVersion(latestRun.config_version)}</span>
                    <span>{formatDateTime(latestRun.created_at)}</span>
                    {typeof result.confidence === "number" ? (
                      <span>本次输入数据置信度 {formatImportanceScore(result.confidence)}</span>
                    ) : null}
                    {typeof result.profile_fit_score === "number" ? (
                      <span>视角适配度 {formatImportanceScore(result.profile_fit_score)}</span>
                    ) : null}
                    <button
                      className="icon-action icon-action--danger"
                      type="button"
                      title="删除分析记录"
                      aria-label={`删除${profile.display_name}分析记录 #${latestRun.id}`}
                      disabled={isDeletingRun}
                      onClick={() => onDeleteRun(latestRun.id)}
                    >
                      <Trash2 aria-hidden="true" size={14} />
                      <span>
                        {deleteState.runId === latestRun.id && isDeletingRun
                          ? "删除中"
                          : "删除记录"}
                      </span>
                    </button>
                  </div>
                  <p>{cleanDisplayText(result.overview)}</p>

                  {result.key_observations && result.key_observations.length > 0 ? (
                    <div className="analyst-note-group analyst-note-group--wide-label">
                      <strong>关键观察</strong>
                      <span>{formatSemicolonList(result.key_observations)}</span>
                    </div>
                  ) : null}

                  {analysisBasisItems.length > 0 ? (
                    <div className="analyst-basis">
                      <strong>本次分析依据</strong>
                      <div>
                        {analysisBasisItems.map((item, index) => (
                          <span key={item}>
                            {cleanDisplayText(item)}
                            {index < analysisBasisItems.length - 1 ? " " : ""}
                          </span>
                        ))}
                      </div>
                    </div>
                  ) : null}

                  {scoreExplanationItems.length > 0 ? (
                    <div className="analyst-score-notes">
                      {scoreExplanationItems.map((item, index) => (
                        <span key={item}>
                          {cleanDisplayText(item)}
                          {index < scoreExplanationItems.length - 1 ? " " : ""}
                        </span>
                      ))}
                    </div>
                  ) : null}

                  {ruleChecks.length > 0 ? (
                    <ul className="analyst-rule-check-list">
                      {ruleChecks.map((check) => {
                        const isUpdatingRuleStatus =
                          statusUpdateState.status === "saving" &&
                          statusUpdateState.runId === latestRun.id &&
                          statusUpdateState.ruleId === check.rule_id;
                        const ruleLabel = getRuleLabel(profile, check.rule_id);

                        return (
                          <li key={check.rule_id}>
                            <select
                              className={`rule-status rule-status-select rule-status--${check.status}`}
                              value={check.status}
                              disabled={isUpdatingRuleStatus}
                              aria-label={`调整${profile.display_name}${ruleLabel}结论`}
                              onChange={(event) =>
                                onUpdateRuleStatus(
                                  latestRun.id,
                                  check.rule_id,
                                  event.target.value as AnalystRuleStatus
                                )
                              }
                            >
                              <option value="pass">{analystRuleStatusLabels.pass}</option>
                              <option value="neutral">{analystRuleStatusLabels.neutral}</option>
                              <option value="unknown">{analystRuleStatusLabels.unknown}</option>
                              <option value="warn">{analystRuleStatusLabels.warn}</option>
                              <option value="fail">{analystRuleStatusLabels.fail}</option>
                            </select>
                            <strong>{ruleLabel}</strong>
                            <span>{cleanDisplayText(check.summary)}</span>
                          </li>
                        );
                      })}
                    </ul>
                  ) : null}

                  {result.financial_observations &&
                  result.financial_observations.length > 0 ? (
                    <div className="analyst-note-group analyst-note-group--wide-label">
                      <strong>财务观察</strong>
                      <span>{formatSemicolonList(result.financial_observations)}</span>
                    </div>
                  ) : null}

                  {result.announcement_observations &&
                  result.announcement_observations.length > 0 ? (
                    <div className="analyst-note-group analyst-note-group--wide-label">
                      <strong>公告观察</strong>
                      <span>{formatSemicolonList(result.announcement_observations)}</span>
                    </div>
                  ) : null}

                  {result.risk_flags && result.risk_flags.length > 0 ? (
                    <div className="analyst-note-group">
                      <strong>风险</strong>
                      <span>{formatSemicolonList(result.risk_flags)}</span>
                    </div>
                  ) : null}

                  {result.counter_evidence && result.counter_evidence.length > 0 ? (
                    <div className="analyst-note-group">
                      <strong>反方</strong>
                      <span>{formatSemicolonList(result.counter_evidence)}</span>
                    </div>
                  ) : null}

                  {(result.valuation_assumption_suggestions &&
                    result.valuation_assumption_suggestions.length > 0) ||
                  (result.valuation_assumption_details &&
                    result.valuation_assumption_details.length > 0) ? (
                    <div className="analyst-note-group analyst-note-group--wide-label">
                      <strong>估值假设</strong>
                      <span>{formatValuationAssumptions(result)}</span>
                    </div>
                  ) : null}

                  {result.data_gaps && result.data_gaps.length > 0 ? (
                    <div className="analyst-note-group">
                      <strong>缺口</strong>
                      <span>{formatSemicolonList(result.data_gaps)}</span>
                    </div>
                  ) : null}

                  {result.follow_up_questions && result.follow_up_questions.length > 0 ? (
                    <div className="analyst-note-group analyst-note-group--wide-label">
                      <strong>后续问题</strong>
                      <span>{formatQuestionList(result.follow_up_questions)}</span>
                    </div>
                  ) : null}
                </div>
              ) : (
                <div className="inline-empty inline-empty--compact">暂无分析结果</div>
              )}
            </article>
          );
        })}
      </div>

      {sharedAccountingEvents.length > 0 ? (
        <div className="analyst-accounting-alert analyst-accounting-alert--panel">
          <strong>会计口径提示</strong>
          <ul>
            {sharedAccountingEvents.slice(0, 6).map((event, index) => (
              <li key={`${event.event_type ?? "accounting"}-${event.source_id ?? index}`}>
                {formatAccountingEvent(event)}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </section>
  );
}

function collectSharedAccountingEvents(
  runs: AnalysisRun[]
): NonNullable<AnalysisRun["result"]["accounting_events"]> {
  const events: NonNullable<AnalysisRun["result"]["accounting_events"]> = [];
  const seen = new Set<string>();

  for (const run of runs) {
    const runEvents = Array.isArray(run.result.accounting_events)
      ? run.result.accounting_events
      : [];
    for (const event of runEvents) {
      const key = [
        event.event_type ?? "accounting",
        event.source_type ?? "source",
        event.source_id ?? "",
        event.label ?? ""
      ].join("|");
      if (seen.has(key)) {
        continue;
      }
      seen.add(key);
      events.push(event);
    }
  }

  return events;
}

function getRuleLabel(profile: AnalystProfileListResponse["items"][number], ruleId: string): string {
  return profile.rules.find((rule) => rule.id === ruleId)?.label ?? ruleId;
}

function formatAnalysisBasis(
  basis: NonNullable<AnalysisRun["result"]["analysis_basis"]>
): string[] {
  const items: string[] = [];
  const financialPeriods = normalizeStringList(basis.financial_periods);
  const announcementIds = normalizeNumberList(basis.announcement_ids);
  const externalEvidenceIds = normalizeNumberList(basis.external_evidence_ids);
  const accountingEventCount =
    typeof basis.accounting_event_count === "number" ? basis.accounting_event_count : 0;

  if (financialPeriods.length > 0) {
    items.push(formatBasisPreview("财务期", financialPeriods, 4, "期"));
  }
  if (announcementIds.length > 0) {
    items.push(
      formatBasisPreview(
        "公告",
        announcementIds.map((id) => `#${id}`),
        5,
        "条"
      )
    );
  }
  if (externalEvidenceIds.length > 0) {
    items.push(
      formatBasisPreview(
        "外部证据",
        externalEvidenceIds.map((id) => `#${id}`),
        5,
        "条"
      )
    );
  }
  if (accountingEventCount > 0) {
    items.push(`会计口径事件 ${accountingEventCount} 个`);
  }
  for (const note of normalizeStringList(basis.notes).slice(0, 2)) {
    items.push(note);
  }
  return items;
}

function formatBasisPreview(
  label: string,
  values: string[],
  previewLimit: number,
  unit: string
): string {
  const preview = values.slice(0, previewLimit).join("、");
  if (values.length <= previewLimit) {
    return `${label} ${values.length} ${unit}：${preview}`;
  }
  return `${label} ${values.length} ${unit}（展示 ${previewLimit} ${unit}：${preview}）`;
}

function formatScoreExplanations(
  explanations: NonNullable<AnalysisRun["result"]["score_explanations"]>
): string[] {
  const items: string[] = [];
  const profileReasons = normalizeStringList(explanations.profile_relevance?.reasons);
  const dataReasons = normalizeStringList(explanations.data_confidence?.reasons);

  if (profileReasons.length > 0) {
    items.push(`适配依据：${formatSemicolonList(profileReasons.slice(0, 2))}`);
  }
  if (dataReasons.length > 0) {
    items.push(`数据依据：${formatSemicolonList(dataReasons.slice(0, 2))}`);
  }
  return items;
}

function formatAccountingEvent(
  event: NonNullable<AnalysisRun["result"]["accounting_events"]>[number]
): string {
  const label = event.label || event.event_type || "会计口径事项";
  const summary = stripLeadingAccountingEventLabel(
    cleanDisplayText(
    event.summary || event.comparability_impact || "需要复核同比可比口径。"
    ),
    String(label)
  );
  const source =
    typeof event.source_id === "number" || typeof event.source_id === "string"
      ? ` 来源 ${event.source_type ?? "source"} #${event.source_id}`
      : "";
  return cleanDisplayText(`${label}：${summary}${source}`);
}

function stripLeadingAccountingEventLabel(summary: string, label: string): string {
  const prefixes = [`${label}：`, `${label}:`, `${label} `];
  for (const prefix of prefixes) {
    if (summary.startsWith(prefix)) {
      return summary.slice(prefix.length).trim();
    }
  }
  return summary;
}

function normalizeStringList(value: unknown): string[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value
    .map((item) => cleanDisplayText(String(item)))
    .filter((item, index, items) => item.length > 0 && items.indexOf(item) === index);
}

function sanitizeAnnouncementTags(value: unknown): string[] {
  const genericTags = new Set(["待复核", "其他", "公告", "公司公告", "搜索线索", "智能摘要"]);
  return normalizeStringList(value).filter((tag) => !genericTags.has(tag));
}

function formatSemicolonList(value: unknown): string {
  return normalizeStringList(value)
    .map(stripTrailingDisplayPunctuation)
    .filter((item) => item.length > 0)
    .join("；");
}

function formatValuationAssumptions(result: AnalysisRun["result"]): string {
  const suggestions = normalizeStringList(result.valuation_assumption_suggestions);
  const details = Array.isArray(result.valuation_assumption_details)
    ? result.valuation_assumption_details
    : [];
  const detailItems = details
    .map((item) => {
      const neededInputs = normalizeStringList(item.needed_inputs);
      const assumptionType = stripTrailingDisplayPunctuation(
        cleanDisplayText(String(item.assumption_type ?? "估值假设"))
      ).replace(/[：:]+$/u, "");
      const reason = stripTrailingDisplayPunctuation(
        cleanDisplayText(String(item.reason ?? "需要补充关键输入"))
      );
      const suffix =
        neededInputs.length > 0 ? `，需补充 ${neededInputs.slice(0, 3).join("、")}` : "";
      return cleanDisplayText(`${assumptionType}：${reason}${suffix}`);
    })
    .filter((item) => item.trim().length > 0);
  return formatSemicolonList([...suggestions, ...detailItems]);
}

function formatQuestionList(value: unknown): string {
  return normalizeStringList(value)
    .map((item) => item.replace(/[。；;，,？?]+$/u, ""))
    .filter((item) => item.length > 0)
    .map((item) => `${item}？`)
    .join(" ");
}

function stripTrailingDisplayPunctuation(value: string): string {
  return cleanDisplayText(value).replace(/[。；;，,]+$/u, "");
}

function cleanDisplayText(value: string): string {
  return value
    .replace(/\s+/gu, " ")
    .replace(/[。.!！？?]+(?=[，,])/gu, "")
    .replace(/[；;]+(?=[，,])/gu, "")
    .replace(/([。！？?；;，,])\1+/gu, "$1")
    .replace(/([。！？?])(?=[。！？?；;])/gu, "")
    .trim();
}

function normalizeNumberList(value: unknown): number[] {
  if (!Array.isArray(value)) {
    return [];
  }
  const items: number[] = [];
  for (const item of value) {
    if (typeof item === "number" && Number.isFinite(item) && !items.includes(item)) {
      items.push(item);
    }
  }
  return items;
}

function readPlainRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

function readRecordArray(value: unknown): Array<Record<string, unknown>> {
  if (!Array.isArray(value)) {
    return [];
  }
  return value.filter(
    (item): item is Record<string, unknown> =>
      Boolean(item) && typeof item === "object" && !Array.isArray(item)
  );
}

function readNumber(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) {
    return value;
  }
  if (typeof value === "string" && value.trim().length > 0) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
}

function emptyValuationScenario(): ValuationScenarioDraft[ValuationScenarioName] {
  return {
    cash_flow_growth_rate: null,
    owner_earnings_growth_rate: null,
    discount_rate: null,
    terminal_growth_rate: null
  };
}

function buildEditableValuationScenarios(run: ValuationRun | null): ValuationScenarioDraft {
  const confirmedScenarios = readPlainRecord(run?.assumptions.scenarios);
  const suggestedScenarios = readPlainRecord(run?.model_suggested_assumptions.scenarios);
  const scenarios = Object.keys(confirmedScenarios).length > 0
    ? confirmedScenarios
    : suggestedScenarios;
  return {
    conservative: buildEditableValuationScenario(readPlainRecord(scenarios.conservative)),
    base: buildEditableValuationScenario(readPlainRecord(scenarios.base)),
    optimistic: buildEditableValuationScenario(readPlainRecord(scenarios.optimistic))
  };
}

function buildEditableValuationModelWeights(run: ValuationRun | null): ValuationModelWeightsDraft {
  const confirmedWeights = readPlainRecord(run?.assumptions.model_weights);
  const suggestedWeights = readPlainRecord(run?.model_suggested_assumptions.model_weights);
  const recordedWeights = readPlainRecord(run?.methods.base_weights);
  const weights = Object.keys(confirmedWeights).length > 0
    ? confirmedWeights
    : Object.keys(suggestedWeights).length > 0
      ? suggestedWeights
      : Object.keys(recordedWeights).length > 0
        ? recordedWeights
        : defaultValuationModelWeights;
  const draft = {} as ValuationModelWeightsDraft;
  for (const field of valuationModelWeightFields) {
    const value = readNumber(weights[field.key]);
    draft[field.key] = value === null
      ? defaultValuationModelWeights[field.key]
      : roundPercentForInput(value * 100);
  }
  return draft;
}

function sumValuationModelWeights(draft: ValuationModelWeightsDraft): number {
  return valuationModelWeightFields.reduce(
    (total, field) => total + (draft[field.key] ?? 0),
    0
  );
}

function validateValuationModelWeights(draft: ValuationModelWeightsDraft): string | null {
  const values = valuationModelWeightFields.map((field) => draft[field.key]);
  if (values.some((value) => value === null || !Number.isFinite(value))) {
    return "请填写全部模型配比。";
  }
  if (values.some((value) => value !== null && (value < 0 || value > 100))) {
    return "每个模型配比必须在 0% 到 100% 之间。";
  }
  if (Math.abs(sumValuationModelWeights(draft) - 100) > 0.001) {
    return "五个模型的配比合计必须等于 100%。";
  }
  if ((draft.dcf ?? 0) + (draft.owner_earnings ?? 0) <= 0) {
    return "当前可计算的 DCF 与所有者盈余配比合计必须大于 0%。";
  }
  return null;
}

function formatRuleStatus(value: unknown): string {
  const labels: Record<string, string> = {
    pass: "通过",
    neutral: "中性",
    warn: "谨慎",
    fail: "不通过",
    unknown: "未知"
  };
  return labels[String(value ?? "unknown")] ?? "未知";
}

function formatRuleDimensionContributions(
  rule: Record<string, unknown>,
  dimensionContributions: Record<string, unknown>
): string {
  const labels: string[] = [];
  for (const [dimension, rawItems] of Object.entries(dimensionContributions)) {
    const match = readRecordArray(rawItems).find(
      (item) =>
        item.source_run_id === rule.source_run_id &&
        item.rule_id === rule.rule_id
    );
    if (!match) {
      continue;
    }
    const contribution = readNumber(match.contribution);
    labels.push(
      `${matrixParameterLabel(dimension)} ${
        contribution === null ? "待计算" : formatCompactDecimal(contribution)
      }`
    );
  }
  return labels.length > 0 ? labels.join("、") : "无";
}

function readSafetyMarginContribution(
  rule: Record<string, unknown>,
  contributions: Array<Record<string, unknown>>
): number | null {
  const item = contributions.find(
    (candidate) =>
      candidate.source_run_id === rule.source_run_id && candidate.rule_id === rule.rule_id
  );
  return readNumber(item?.contribution);
}

function formatCompactDecimal(value: number): string {
  return String(Number(value.toFixed(4)));
}

function buildEditableValuationScenario(
  scenario: Record<string, unknown>
): ValuationScenarioDraft[ValuationScenarioName] {
  const draft = emptyValuationScenario();
  for (const field of valuationAssumptionFields) {
    const value = readNumber(scenario[field.key]);
    draft[field.key] = value === null ? null : roundPercentForInput(value * 100);
  }
  return draft;
}

function parseAssumptionInput(value: string): number | null {
  if (value.trim().length === 0) {
    return null;
  }
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function buildValuationAssumptionPayload(
  scenarioDraft: ValuationScenarioDraft,
  modelWeightsDraft: ValuationModelWeightsDraft
): Record<string, unknown> {
  const scenarios: Record<string, Record<string, number>> = {};
  for (const scenarioName of valuationScenarioNames) {
    const scenario: Record<string, number> = {};
    for (const field of valuationAssumptionFields) {
      const value = scenarioDraft[scenarioName][field.key];
      if (value !== null && Number.isFinite(value)) {
        scenario[field.key] = value / 100;
      }
    }
    scenarios[scenarioName] = scenario;
  }
  const modelWeights: Record<string, number> = {};
  for (const field of valuationModelWeightFields) {
    const value = modelWeightsDraft[field.key];
    if (value !== null && Number.isFinite(value)) {
      modelWeights[field.key] = value / 100;
    }
  }
  return { scenarios, model_weights: modelWeights };
}

function formatAssumptionInputValue(value: number | null): string {
  return value === null || !Number.isFinite(value) ? "" : String(value);
}

function roundPercentForInput(value: number): number {
  return Math.round(value * 100) / 100;
}

function formatDraftPercent(value: number): string {
  return `${roundPercentForInput(value).toLocaleString("zh-CN", {
    maximumFractionDigits: 2
  })}%`;
}

function formatValuationRangeItem(totalValue: number | null, perShareValue: number | null): string {
  return `${formatFinancialSummaryMoney(totalValue)} / 每股 ${formatPerShareIntrinsicValue(perShareValue)}`;
}

function formatPerShareIntrinsicValue(value: number | null): string {
  if (value === null || !Number.isFinite(value)) {
    return "待计算";
  }
  return `${value.toLocaleString("zh-CN", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2
  })} CNY`;
}

function formatShareCount(value: unknown): string {
  const numberValue = readNumber(value);
  if (numberValue === null) {
    return "待更新";
  }
  return `${formatLargeNumber(numberValue)} 股`;
}

function formatMethodName(value: unknown): string {
  const method = String(value ?? "");
  const labels: Record<string, string> = {
    dcf: "DCF",
    owner_earnings: "所有者盈余",
    residual_income: "剩余收益",
    dividend_discount: "分红折现",
    asset_value: "资产价值"
  };
  return labels[method] ?? (method || "待命名模型");
}

function formatMethodStatus(status: string): string {
  const labels: Record<string, string> = {
    success: "已计算",
    needs_input: "缺输入",
    skipped: "MVP 预留"
  };
  return labels[status] ?? status;
}

function formatValuationRunStatus(status: string | undefined): string {
  const labels: Record<string, string> = {
    draft: "草稿",
    locked: "历史版本",
    archived: "已归档",
    failed: "失败"
  };
  return status ? (labels[status] ?? status) : "未生成";
}

function formatGapSeverity(severity: string): string {
  const labels: Record<string, string> = {
    high: "高",
    medium: "中",
    low: "低"
  };
  return labels[severity] ?? severity;
}

function formatFinancialFlagSeverity(severity: string): string {
  const labels: Record<string, string> = {
    risk: "风险",
    warn: "观察",
    warning: "观察",
    info: "提示",
    low: "低",
    medium: "中",
    high: "高"
  };
  return labels[severity] ?? severity;
}

function formatNeededByList(value: unknown): string {
  const labels: Record<string, string> = {
    analyst_view: "分析师",
    valuation_lab: "估值实验室"
  };
  return normalizeStringList(value)
    .map((item) => labels[item] ?? item)
    .join("、");
}

function toAnalysisRunListResponse(response: { items: AnalysisRunListResponse["items"] }) {
  return {
    items: response.items,
    total: response.items.length,
    limit: response.items.length,
    offset: 0
  };
}

function buildResearchReadiness({
  financials,
  financialEvidencePack,
  announcements,
  evidence,
  analystProfiles,
  analysisRuns,
  failedAnalysisRuns
}: {
  financials: FinancialStatementListResponse;
  financialEvidencePack: FinancialEvidencePack;
  announcements: AnnouncementListResponse;
  evidence: EvidenceListResponse;
  analystProfiles: AnalystProfileListResponse;
  analysisRuns: AnalysisRunListResponse;
  failedAnalysisRuns: AnalysisRunListResponse;
}): ResearchReadiness {
  const announcementStatusCounts = announcements.items.reduce(
    (counts, announcement) => {
      const status = getAnnouncementDisplayStatus(announcement);
      if (status === "deep_summarized") {
        counts.deep += 1;
      } else if (status === "quick_summarized" || status === "summarized") {
        counts.quick += 1;
      } else {
        counts.unprocessed += 1;
      }
      return counts;
    },
    { unprocessed: 0, quick: 0, deep: 0 }
  );
  const currentProfileIds = new Set(analystProfiles.items.map((profile) => profile.id));
  const successfulProfileIds = new Set(
    analysisRuns.items
      .map((run) => run.analyst_profile)
      .filter((profileId): profileId is string => Boolean(profileId))
      .filter((profileId) => currentProfileIds.has(profileId))
  );
  const failedProfileIds = new Set(
    failedAnalysisRuns.items
      .map((run) => run.analyst_profile)
      .filter((profileId): profileId is string => Boolean(profileId))
      .filter((profileId) => currentProfileIds.has(profileId))
      .filter((profileId) => !successfulProfileIds.has(profileId))
  );
  const missingProfileCount = analystProfiles.items.filter(
    (profile) => !successfulProfileIds.has(profile.id)
  ).length;
  const memoReady = successfulProfileIds.size >= 2;

  return {
    financialRecords: financials.total,
    latestFinancialPeriod: financialEvidencePack.latest_period ?? "待更新",
    financialGapCount: financialEvidencePack.financial_data_gaps.length,
    announcementTotal: announcements.total,
    announcementUnprocessed: announcementStatusCounts.unprocessed,
    announcementQuickSummarized: announcementStatusCounts.quick,
    announcementDeepSummarized: announcementStatusCounts.deep,
    evidenceTotal: evidence.total,
    modelAnalyzedEvidence: evidence.items.filter(
      (item) => (item.analysis_status ?? "model_analyzed") === "model_analyzed"
    ).length,
    searchLeadEvidence: evidence.items.filter((item) => item.analysis_status === "search_lead")
      .length,
    analystSuccessCount: successfulProfileIds.size,
    analystFailureCount: failedProfileIds.size,
    missingProfileCount,
    memoReady,
    memoStatus: memoReady
      ? "已具备综合备忘录素材"
      : "至少需要 2 个成功分析师视角"
  };
}

function buildMemoPreparation(
  profiles: AnalystProfileListResponse,
  runs: AnalysisRunListResponse,
  failedRuns: AnalysisRunListResponse
): MemoPreparation {
  const currentProfileIds = new Set(profiles.items.map((profile) => profile.id));
  const currentRuns = runs.items.filter((run) =>
    currentProfileIds.has(run.analyst_profile ?? "")
  );
  const currentFailedRuns = failedRuns.items.filter((run) =>
    currentProfileIds.has(run.analyst_profile ?? "")
  );
  const successfulProfileIds = new Set(
    currentRuns.map((run) => run.analyst_profile).filter((id): id is string => Boolean(id))
  );
  const failedProfileIds = new Set(
    currentFailedRuns
      .map((run) => run.analyst_profile)
      .filter((id): id is string => Boolean(id))
      .filter((id) => !successfulProfileIds.has(id))
  );
  const successfulProfiles = profiles.items
    .filter((profile) => successfulProfileIds.has(profile.id))
    .map((profile) => profile.display_name);
  const missingProfiles = profiles.items
    .filter((profile) => !successfulProfileIds.has(profile.id))
    .map((profile) => profile.display_name);
  const failedProfiles = profiles.items
    .filter((profile) => failedProfileIds.has(profile.id))
    .map((profile) => `${profile.display_name} 最近失败`);
  const risks = uniqueStrings(currentRuns.flatMap((run) => normalizeStringList(run.result.risk_flags)));
  const counterEvidence = uniqueStrings(
    currentRuns.flatMap((run) => normalizeStringList(run.result.counter_evidence))
  );
  const dataGaps = uniqueStrings(currentRuns.flatMap((run) => normalizeStringList(run.result.data_gaps)));
  const valuationAssumptions = uniqueStrings(
    currentRuns.flatMap((run) => normalizeStringList(run.result.valuation_assumption_suggestions))
  );

  return {
    successfulProfiles,
    missingProfiles,
    failedProfiles,
    risks,
    counterEvidence,
    dataGaps,
    valuationAssumptions
  };
}

async function loadLatestAnalystRuns(companyId: number) {
  return Promise.all([
    getLatestCompanyAnalysisRuns(companyId, {
      run_type: "analyst_view",
      status: "success"
    }),
    getLatestCompanyAnalysisRuns(companyId, {
      run_type: "analyst_view",
      status: "failed"
    })
  ]);
}

async function loadInvestmentMemos(companyId: number) {
  return Promise.all([
    getLatestInvestmentMemo(companyId),
    getInvestmentMemos(companyId, {
      limit: 20,
      offset: 0
    })
  ]);
}

async function loadPriceDecisions(companyId: number) {
  return Promise.all([
    getLatestPriceDecisionRun(companyId),
    getPriceDecisionRuns(companyId, { offset: 0 })
  ]);
}

async function withOptionalWorkspaceData<T>(promise: Promise<T>, fallback: T): Promise<T> {
  try {
    return await promise;
  } catch {
    return fallback;
  }
}

async function refreshFailedAnalystRuns(
  companyId: number,
  setDetailState: Dispatch<SetStateAction<CompanyDetailState>>
) {
  try {
    const refreshedFailedRuns = await getLatestCompanyAnalysisRuns(companyId, {
      run_type: "analyst_view",
      status: "failed"
    });
    setDetailState((currentState) => {
      if (currentState.status !== "ready") {
        return currentState;
      }

      return {
        status: "ready",
        data: {
          ...currentState.data,
          failedAnalysisRuns: toAnalysisRunListResponse(refreshedFailedRuns)
        },
        error: null
      };
    });
  } catch {
    // The direct error message is already visible; a refresh failure should not hide it.
  }
}

async function refreshLatestAnalystRuns(
  companyId: number,
  setDetailState: Dispatch<SetStateAction<CompanyDetailState>>
) {
  try {
    const [refreshedRuns, refreshedFailedRuns] = await loadLatestAnalystRuns(companyId);
    setDetailState((currentState) => {
      if (currentState.status !== "ready") {
        return currentState;
      }

      return {
        status: "ready",
        data: {
          ...currentState.data,
          analysisRuns: toAnalysisRunListResponse(refreshedRuns),
          failedAnalysisRuns: toAnalysisRunListResponse(refreshedFailedRuns)
        },
        error: null
      };
    });
  } catch {
    // The direct action message remains visible; a refresh failure should not hide it.
  }
}

function updateAnnouncementsFromSummaryItems(
  setDetailState: Dispatch<SetStateAction<CompanyDetailState>>,
  items: Array<{ announcement_id: number; announcement: Announcement | null }>
) {
  const nextById = new Map(
    items
      .filter((item) => item.announcement !== null)
      .map((item) => [item.announcement_id, item.announcement as Announcement])
  );
  if (nextById.size === 0) {
    return;
  }

  setDetailState((currentState) => {
    if (currentState.status !== "ready") {
      return currentState;
    }

    const nextItems = currentState.data.announcements.items.map((item) =>
      nextById.has(item.id) ? (nextById.get(item.id) as Announcement) : item
    );

    return {
      status: "ready",
      data: {
        ...currentState.data,
        announcements: {
          ...currentState.data.announcements,
          items: nextItems
        }
      },
      error: null
    };
  });
}

function formatEvidenceSearchMessage(searchResult: EvidenceSearchResponse): string {
  const baseMessage =
    searchResult.status === "partial"
      ? `已保存 ${searchResult.created} 条搜索线索，模型分析未完成，运行记录 #${searchResult.run_id}`
      : `已生成 ${searchResult.created} 条证据，运行记录 #${searchResult.run_id}`;
  const diagnostics = searchResult.diagnostics;
  if (!diagnostics) {
    return baseMessage;
  }

  const providerResultCount = readDiagnosticsNumber(diagnostics, "provider_result_count");
  const filteredOutCount = readDiagnosticsNumber(diagnostics, "filtered_out_count");
  const sentToModelCount = readDiagnosticsNumber(diagnostics, "sent_to_model_count");
  const stats = [
    providerResultCount === null ? null : `候选 ${providerResultCount}`,
    filteredOutCount === null ? null : `过滤 ${filteredOutCount}`,
    sentToModelCount === null ? null : `送模 ${sentToModelCount}`
  ].filter((item): item is string => item !== null);

  return stats.length > 0 ? `${baseMessage}；${stats.join("，")}` : baseMessage;
}

function formatEvidenceImportTextMessage(importResult: EvidenceSearchResponse): string {
  const ids = importResult.items.map((item) => `#${item.id}`);
  const evidenceLabel =
    ids.length > 0 ? `：${ids.join("，")}` : "";
  return `已导入 ${importResult.created} 条外部证据${evidenceLabel}，运行记录 #${importResult.run_id}`;
}

function optionalText(value: string): string | undefined {
  const text = value.trim();
  return text.length > 0 ? text : undefined;
}

function readDiagnosticsNumber(
  diagnostics: Record<string, unknown>,
  key: string
): number | null {
  const value = diagnostics[key];
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function isDeepSummarizedAnnouncement(announcement: Announcement): boolean {
  const modelName = announcement.summary_model_name?.trim();
  return Boolean(
    modelName && modelName !== "metadata_keyword" && !hasStaleEastmoneyPageShellContent(announcement)
  );
}

const EASTMONEY_PAGE_SHELL_MARKERS = [
  "公告正文 _ 数据中心 _ 东方财富网",
  "数据中心 全球财经快讯 行情中心 Choice数据",
  "东方财富网研报中心提供沪深两市最全面的上市公司公告信息"
];

function hasStaleEastmoneyPageShellContent(announcement: Announcement): boolean {
  const content = announcement.raw_content || announcement.content || "";
  return EASTMONEY_PAGE_SHELL_MARKERS.some((marker) => content.includes(marker));
}

function formatBatchRunMessage(
  batchResult: AnalysisBatchRunResponse,
  profiles: AnalystProfileListResponse
): string {
  const baseMessage = `已生成 ${batchResult.succeeded} 个视角，失败 ${batchResult.failed} 个`;
  const failedItems = batchResult.items.filter((item) => item.status === "failed");
  if (failedItems.length === 0) {
    return baseMessage;
  }

  const firstFailure = failedItems[0];
  const profileName = getAnalystDisplayName(profiles, firstFailure.analyst_profile);
  const reason = compactErrorMessage(
    [firstFailure.error_type, firstFailure.error].filter(Boolean).join("：")
  );
  if (failedItems.length === 1) {
    return `${baseMessage}；${profileName}：${reason}`;
  }
  return `${baseMessage}；首个失败 ${profileName}：${reason}`;
}

function getAnalystDisplayName(
  profiles: AnalystProfileListResponse,
  profileId: string | null
): string {
  if (!profileId) {
    return "未知视角";
  }
  return profiles.items.find((profile) => profile.id === profileId)?.display_name ?? profileId;
}

function getRunFailureMessage(run: AnalysisRun): string {
  const errorType = typeof run.result.error_type === "string" ? run.result.error_type : null;
  const error = typeof run.result.error === "string" ? run.result.error : null;
  const message = [errorType, error].filter(Boolean).join("：");
  return compactErrorMessage(message || "后端未返回失败原因");
}

function getUnknownErrorMessage(error: unknown, fallback: string): string {
  if (error instanceof Error) {
    return compactErrorMessage(error.message || fallback);
  }
  const formatted = formatUnknownValue(error);
  return formatted ? compactErrorMessage(formatted) : fallback;
}

function getMemoGenerateErrorMessage(error: unknown): string {
  const message = getUnknownErrorMessage(error, "综合投资备忘录生成失败");
  const normalizedMessage = message.toLowerCase();

  if (normalizedMessage.includes("not found") || normalizedMessage.includes("404")) {
    return "综合投资备忘录接口返回 not found；如果刚更新过 009，请重启后端服务后再试。";
  }

  return message;
}

function formatUnknownValue(value: unknown): string | null {
  if (value === null || typeof value === "undefined") {
    return null;
  }
  if (typeof value === "string") {
    return value;
  }
  if (typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  if (Array.isArray(value)) {
    const items = value
      .map((item) => formatUnknownValue(item))
      .filter((item): item is string => Boolean(item));
    return items.length > 0 ? items.join("；") : null;
  }
  if (typeof value === "object") {
    const record = value as Record<string, unknown>;
    for (const key of ["detail", "message", "error"]) {
      const nested = formatUnknownValue(record[key]);
      if (nested) {
        return nested;
      }
    }
    if (typeof record.msg === "string") {
      const location = Array.isArray(record.loc) ? record.loc.join(".") : null;
      return location ? `${location}: ${record.msg}` : record.msg;
    }
    try {
      return JSON.stringify(value);
    } catch {
      return null;
    }
  }
  return null;
}

function compactErrorMessage(message: unknown): string {
  const rawMessage = formatUnknownValue(message) ?? "";
  const titleMatch = rawMessage.match(/<title>(.*?)<\/title>/is);
  const compacted = titleMatch
    ? rawMessage.replace(/<title>.*?<\/title>/is, titleMatch[1])
    : rawMessage;
  const normalized = compacted
    .replace(/<!DOCTYPE[^>]*>/gi, " ")
    .replace(/<!--.*?-->/gs, " ")
    .replace(/<[^>]+>/g, " ")
    .replace(/\s+/g, " ")
    .trim();
  if (normalized.length <= 180) {
    return normalized;
  }
  return `${normalized.slice(0, 180)}...`;
}

function isRunNewer(candidate: AnalysisRun, current: AnalysisRun): boolean {
  return new Date(candidate.created_at).getTime() > new Date(current.created_at).getTime();
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

function uniqueStrings(items: string[]): string[] {
  return Array.from(new Set(items.map((item) => item.trim()).filter(Boolean)));
}

function formatFinancialValue(key: string, value: unknown, currency: string): string {
  if (typeof value === "number") {
    if (isRatioField(key)) {
      return `${(value * 100).toFixed(1)}%`;
    }

    if (isMoneyField(key)) {
      return `${formatLargeNumber(value)} ${currency}`;
    }

    if (isShareCountField(key)) {
      return `${formatLargeNumber(value)} 股`;
    }

    return value.toLocaleString("zh-CN", { maximumFractionDigits: 4 });
  }

  if (value === null || typeof value === "undefined") {
    return "无";
  }

  return String(value);
}

function orderedFinancialFields(fields: Record<string, unknown>): [string, unknown][] {
  const orderIndex = new Map(
    financialFieldDisplayOrder.map((fieldName, index) => [fieldName, index])
  );
  return Object.entries(fields).sort(([leftKey], [rightKey]) => {
    const leftIndex = orderIndex.get(leftKey) ?? Number.MAX_SAFE_INTEGER;
    const rightIndex = orderIndex.get(rightKey) ?? Number.MAX_SAFE_INTEGER;
    if (leftIndex !== rightIndex) {
      return leftIndex - rightIndex;
    }
    return leftKey.localeCompare(rightKey, "zh-CN");
  });
}

function sortFinancialStatementsForDisplay(statements: FinancialStatement[]): FinancialStatement[] {
  const orderIndex = new Map(
    financialStatementTypeDisplayOrder.map((statementType, index) => [statementType, index])
  );

  return statements
    .map((statement, index) => ({ statement, index }))
    .sort((left, right) => {
      if (left.statement.period !== right.statement.period) {
        return left.index - right.index;
      }

      const leftTypeIndex =
        orderIndex.get(left.statement.statement_type) ?? Number.MAX_SAFE_INTEGER;
      const rightTypeIndex =
        orderIndex.get(right.statement.statement_type) ?? Number.MAX_SAFE_INTEGER;

      if (leftTypeIndex !== rightTypeIndex) {
        return leftTypeIndex - rightTypeIndex;
      }

      return left.index - right.index;
    })
    .map(({ statement }) => statement);
}

type FinancialStatementPeriodGroup = {
  period: string;
  statements: FinancialStatement[];
};

function groupFinancialStatementsByPeriod(
  statements: FinancialStatement[]
): FinancialStatementPeriodGroup[] {
  const groups: FinancialStatementPeriodGroup[] = [];

  for (const statement of sortFinancialStatementsForDisplay(statements)) {
    const existingGroup = groups.find((group) => group.period === statement.period);
    if (existingGroup) {
      existingGroup.statements.push(statement);
    } else {
      groups.push({ period: statement.period, statements: [statement] });
    }
  }

  return groups;
}

function getPackRecord(source: Record<string, unknown>, key: string): Record<string, unknown> {
  const value = source[key];
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

function formatFinancialSummaryMoney(value: unknown): string {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    return "待更新";
  }
  return `${formatLargeNumber(value)} CNY`;
}

function formatNormalizationMethod(value: unknown): string {
  const labels: Record<string, string> = {
    ttm_adjusted: "TTM（同口径滚动年度）",
    weighted_annual_3y: "完整年度加权（3年）",
    weighted_annual_available: "完整年度加权（可用年度）",
    latest_annual_adjusted: "最近完整年度（1年）"
  };
  return labels[String(value ?? "")] ?? "待补充";
}

function formatNormalizationConfidence(value: unknown): string {
  const labels: Record<string, string> = {
    high: "高",
    medium: "中",
    low: "低"
  };
  return labels[String(value ?? "")] ?? "待补充";
}

function formatGrowthSource(value: unknown): string {
  const labels: Record<string, string> = {
    free_cash_flow_cagr_5y: "自由现金流 5 年复合增长率",
    free_cash_flow_cagr_3y: "自由现金流 3 年复合增长率",
    net_profit_cagr_5y: "净利润 5 年复合增长率",
    net_profit_cagr_3y: "净利润 3 年复合增长率",
    revenue_cagr_5y: "收入 5 年复合增长率",
    revenue_cagr_3y: "收入 3 年复合增长率",
    default_growth: "默认增长率"
  };
  return labels[String(value ?? "")] ?? "待补充";
}

function formatWeightList(value: unknown): string {
  const weights = Array.isArray(value)
    ? value.map((item) => readNumber(item)).filter((item): item is number => item !== null)
    : [];
  return weights.length > 0 ? weights.map((item) => formatPercent(item)).join(" / ") : "不适用";
}

function formatNullableWeight(value: unknown): string {
  const weight = readNumber(value);
  return weight === null ? "TTM组件" : formatPercent(weight);
}

function formatFinancialSummaryPercent(value: unknown): string {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    return "待更新";
  }
  return `${(value * 100).toLocaleString("zh-CN", {
    minimumFractionDigits: 1,
    maximumFractionDigits: 1
  })}%`;
}

function isRatioField(key: string): boolean {
  return (
    key.includes("margin") ||
    key.includes("rate") ||
    key.includes("ratio") ||
    key.endsWith("_yoy") ||
    key === "roe" ||
    key === "operating_cash_flow_to_revenue"
  );
}

function isMoneyField(key: string): boolean {
  return [
    "revenue",
    "operating_cost",
    "gross_profit",
    "taxes_and_surcharges",
    "selling_expense",
    "admin_expense",
    "r_and_d_expense",
    "finance_expense",
    "other_income",
    "investment_income",
    "fair_value_change_income",
    "credit_impairment_loss",
    "asset_impairment_loss",
    "operating_profit",
    "non_operating_income",
    "non_operating_expense",
    "total_profit",
    "income_tax_expense",
    "net_profit",
    "parent_net_profit",
    "minority_interest",
    "deducted_net_profit",
    "operating_cash_flow",
    "purchase_fixed_assets_cash_paid",
    "capital_expenditure",
    "free_cash_flow",
    "depreciation_and_amortization",
    "working_capital_change",
    "dividend",
    "net_cash_from_investing",
    "net_cash_from_financing",
    "cash_and_equivalents",
    "short_term_interest_bearing_debt",
    "long_term_interest_bearing_debt",
    "interest_bearing_debt",
    "net_cash",
    "total_assets",
    "total_liabilities",
    "shareholders_equity",
    "total_equity",
    "goodwill",
    "receivables",
    "inventory",
    "treasury_shares",
    "buyback_amount",
    "buyback_amount_proxy",
    "dividend_payable",
    "total_shareholder_return"
  ].includes(key);
}

function isShareCountField(key: string): boolean {
  return ["shares_outstanding"].includes(key);
}

function formatLargeNumber(value: number): string {
  const absValue = Math.abs(value);
  if (absValue >= 100000000) {
    return `${(value / 100000000).toLocaleString("zh-CN", {
      maximumFractionDigits: 2
    })}亿`;
  }

  if (absValue >= 10000) {
    return `${(value / 10000).toLocaleString("zh-CN", {
      maximumFractionDigits: 2
    })}万`;
  }

  return value.toLocaleString("zh-CN", { maximumFractionDigits: 2 });
}

function formatMoney(value: number | null): string {
  if (value === null || !Number.isFinite(value)) {
    return "待更新";
  }
  return `${formatLargeNumber(value)} 元`;
}

function formatPrice(value: number | null): string {
  if (value === null || !Number.isFinite(value)) {
    return "待更新";
  }
  return value.toLocaleString("zh-CN", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2
  });
}

function formatRatio(value: number | null): string {
  if (value === null || !Number.isFinite(value)) {
    return "待更新";
  }
  return `${value.toLocaleString("zh-CN", { maximumFractionDigits: 2 })}x`;
}

function formatPercent(value: number | null): string {
  if (value === null || !Number.isFinite(value)) {
    return "待更新";
  }
  return `${(value * 100).toLocaleString("zh-CN", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2
  })}%`;
}

function formatImportanceScore(score: number): string {
  return `${Math.round(score * 100)}%`;
}

function formatDate(value: string): string {
  return new Intl.DateTimeFormat("zh-CN", {
    timeZone: DISPLAY_TIME_ZONE,
    dateStyle: "medium"
  }).format(parseApiDate(value));
}

function formatDateTime(value: string): string {
  return new Intl.DateTimeFormat("zh-CN", {
    timeZone: DISPLAY_TIME_ZONE,
    dateStyle: "medium",
    timeStyle: "short"
  }).format(parseApiDate(value));
}

function parseApiDate(value: string): Date {
  const normalized = value.trim();
  if (
    /^\d{4}-\d{2}-\d{2}(?:[ T]\d{2}:\d{2}(?::\d{2}(?:\.\d{1,6})?)?)?$/.test(
      normalized
    )
  ) {
    return new Date(`${normalized.replace(" ", "T")}Z`);
  }
  return new Date(normalized);
}
