import {
  ArrowLeft,
  BarChart3,
  BrainCircuit,
  Building2,
  FileText,
  PlayCircle,
  RefreshCw,
  Search,
  ShieldCheck,
  Square,
  Trash2
} from "lucide-react";
import { useEffect, useRef, useState, type Dispatch, type SetStateAction } from "react";

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
  refreshCompanyProfile,
  runEvidenceModelSmokeTest,
  runCompanyAnalysis,
  runCompanyAnalysisBatch,
  searchCompanyEvidence,
  summarizeCompanyAnnouncement,
  summarizeCompanyAnnouncements,
  summarizeCompanyAnnouncementsDeep,
  syncCompanyAnnouncements,
  syncCompanyFinancials,
  type AnalysisBatchRunResponse,
  type AnalysisRun,
  type AnalysisRunListResponse,
  type AnalystProfileListResponse,
  type Announcement,
  type AnnouncementListResponse,
  type Company,
  type EvidenceSearchResponse,
  type EvidenceListResponse,
  type FinancialEvidencePack,
  type FinancialStatementListResponse,
  type ModelConfigStatus
} from "../services/api";

type CompanyWorkspaceViewProps = {
  companyId: number | null;
  onBackToSearch: () => void;
  onCompanyUnavailable: () => void;
  refreshToken: number;
};

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

type ProfileRefreshState =
  | { status: "idle"; message: null }
  | { status: "refreshing"; message: string }
  | { status: "success"; message: string }
  | { status: "error"; message: string };

const statementTypeLabels: Record<string, string> = {
  income_statement: "利润表",
  balance_sheet: "资产负债表",
  cash_flow_statement: "现金流量表",
  main_financial_indicators: "主要财务指标"
};

const fieldLabels: Record<string, string> = {
  report_date: "报告日期",
  report_type: "报告类型",
  notice_date: "披露日期",
  revenue: "收入",
  gross_profit: "毛利",
  gross_margin: "毛利率",
  net_profit: "净利润",
  deducted_net_profit: "扣非净利润",
  eps: "每股收益",
  bps: "每股净资产",
  roe: "净资产收益率",
  net_margin: "净利率",
  asset_liability_ratio: "资产负债率",
  revenue_yoy: "收入同比",
  net_profit_yoy: "净利润同比",
  operating_cash_flow: "经营现金流",
  operating_cash_flow_per_share: "每股经营现金流",
  operating_cash_flow_to_revenue: "经营现金流/收入",
  total_assets_turnover: "总资产周转率",
  inventory_turnover_days: "存货周转天数",
  raw_secucode: "数据源代码",
  raw_security_name: "数据源名称"
};

const financialFieldDisplayOrder = [
  "report_date",
  "report_type",
  "notice_date",
  "revenue",
  "revenue_yoy",
  "gross_profit",
  "gross_margin",
  "net_profit",
  "net_profit_yoy",
  "deducted_net_profit",
  "eps",
  "bps",
  "roe",
  "net_margin",
  "asset_liability_ratio",
  "operating_cash_flow_per_share",
  "operating_cash_flow_to_revenue",
  "total_assets_turnover",
  "inventory_turnover_days",
  "raw_secucode",
  "raw_security_name"
];

const ANNOUNCEMENT_LOOKBACK_YEARS = 1;
const ANNOUNCEMENT_LIST_LIMIT = 50;
const ANNOUNCEMENT_SUMMARY_BATCH_LIMIT = ANNOUNCEMENT_LIST_LIMIT;
const FINANCIAL_STATEMENT_LIST_LIMIT = 60;
const DISPLAY_TIME_ZONE = "Asia/Shanghai";

export function CompanyWorkspaceView({
  companyId,
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
    setModelSmokeTestState({ status: "idle", message: null });
    setEvidenceDeleteState({ status: "idle", evidenceId: null, message: null });
    setAnalystRunState({ status: "idle", profileId: null, message: null });
    setAnalysisRunDeleteState({ status: "idle", runId: null, message: null });
    setProfileRefreshState({ status: "idle", message: null });
    analystRunAbortControllerRef.current?.abort();
    analystRunAbortControllerRef.current = null;

    Promise.all([
      getCompany(companyId, controller.signal),
      getCompanyFinancials(companyId, {
        limit: FINANCIAL_STATEMENT_LIST_LIMIT,
        offset: 0,
        signal: controller.signal
      }),
      getCompanyFinancialEvidencePack(companyId, controller.signal),
      getCompanyAnnouncements(companyId, {
        limit: ANNOUNCEMENT_LIST_LIMIT,
        offset: 0,
        signal: controller.signal
      }),
      getCompanyEvidence(companyId, { limit: 10, offset: 0, signal: controller.signal }),
      getEvidenceModelConfig(controller.signal),
      getAnalystProfiles(controller.signal),
      getLatestCompanyAnalysisRuns(companyId, {
        run_type: "analyst_view",
        status: "success",
        signal: controller.signal
      }),
      getLatestCompanyAnalysisRuns(companyId, {
        run_type: "analyst_view",
        status: "failed",
        signal: controller.signal
      })
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
          failedAnalysisRuns
        ]) => {
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
            failedAnalysisRuns: toAnalysisRunListResponse(failedAnalysisRuns)
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
    failedAnalysisRuns
  } = detailState.data;

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
        limit: FINANCIAL_STATEMENT_LIST_LIMIT
      });
      const refreshedFinancials = await getCompanyFinancials(company.id, {
        limit: FINANCIAL_STATEMENT_LIST_LIMIT,
        offset: 0
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
        keywords: [company.name, company.industry ?? ""].filter(Boolean),
        max_results: 10
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
    analystRunAbortControllerRef.current?.abort();
    const controller = new AbortController();
    analystRunAbortControllerRef.current = controller;
    setAnalystRunState({
      status: "running_all",
      profileId: null,
      message: "正在生成全部分析师视角"
    });

    try {
      const batchResult = await runCompanyAnalysisBatch(company.id, {
        analyst_profiles: analystProfiles.items.map((profile) => profile.id),
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

      <div className="company-data-grid">
        <FinancialsPanel
          financials={financials}
          financialEvidencePack={financialEvidencePack}
          syncState={financialSyncState}
          deleteState={financialDeleteState}
          onSyncFinancials={handleSyncFinancials}
          onDeleteFinancialStatement={handleDeleteFinancialStatement}
        />
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
      </div>
      <EvidencePanel
        evidence={evidence}
        modelConfig={modelConfig}
        searchState={evidenceSearchState}
        modelSmokeTestState={modelSmokeTestState}
        deleteState={evidenceDeleteState}
        onSearchEvidence={handleSearchEvidence}
        onSmokeTestModel={handleSmokeTestModel}
        onDeleteEvidence={handleDeleteEvidence}
      />
      <AnalystPanel
        profiles={analystProfiles}
        runs={analysisRuns}
        failedRuns={failedAnalysisRuns}
        runState={analystRunState}
        deleteState={analysisRunDeleteState}
        onRunProfile={handleRunAnalystAnalysis}
        onRunAllProfiles={handleRunAllAnalystAnalysis}
        onStopRun={handleStopAnalystAnalysis}
        onDeleteRun={handleDeleteAnalysisRun}
      />
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

type MetricFactProps = {
  label: string;
  value: string;
};

function MetricFact({ label, value }: MetricFactProps) {
  return (
    <div>
      <dt>{label}</dt>
      <dd>{value}</dd>
    </div>
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
        financials.items.map((statement) => {
          const isDeletingStatement = isDeleting && deleteState.statementId === statement.id;
          return (
            <div className="financial-statement" key={statement.id}>
              <div className="statement-heading">
                <strong>{statement.period}</strong>
                <span>{statementTypeLabels[statement.statement_type] ?? statement.statement_type}</span>
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
              {statement.source ? (
                <span className="data-source">来源：{statement.source}</span>
              ) : null}
            </div>
          );
        })
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

  return (
    <dl className="financial-evidence-summary" aria-label="财务证据概览">
      <MetricFact label="最新期间" value={financialEvidencePack.latest_period ?? "待更新"} />
      <MetricFact label="收入" value={formatFinancialSummaryMoney(latestFacts.revenue)} />
      <MetricFact label="净利润" value={formatFinancialSummaryMoney(latestFacts.net_profit)} />
      <MetricFact label="ROE" value={formatFinancialSummaryPercent(profitability.roe)} />
      <MetricFact label="毛利率" value={formatFinancialSummaryPercent(profitability.gross_margin)} />
      <MetricFact label="净利率" value={formatFinancialSummaryPercent(profitability.net_margin)} />
      <MetricFact label="收入同比" value={formatFinancialSummaryPercent(growthQuality.revenue_yoy)} />
      <MetricFact label="净利润同比" value={formatFinancialSummaryPercent(growthQuality.net_profit_yoy)} />
      <MetricFact label="财务旗标" value={`${financialEvidencePack.financial_flags.length} 项`} />
      <MetricFact label="数据缺口" value={`${financialEvidencePack.financial_data_gaps.length} 项`} />
    </dl>
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
  modelSmokeTestState: ModelSmokeTestState;
  deleteState: EvidenceDeleteState;
  onSearchEvidence: () => void;
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
  modelSmokeTestState,
  onSearchEvidence,
  onSmokeTestModel,
  deleteState,
  onDeleteEvidence
}: EvidencePanelProps) {
  const isSearching = searchState.status === "searching";
  const isTestingModel = modelSmokeTestState.status === "testing";
  const isDeleting = deleteState.status === "deleting";

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
            disabled={isSearching || isTestingModel}
            onClick={onSmokeTestModel}
          >
            <BrainCircuit aria-hidden="true" size={15} />
            <span>{isTestingModel ? "自检中" : "模型自检"}</span>
          </button>
          <button
            className="panel-action"
            type="button"
            title="搜索外部信息"
            disabled={isSearching || isTestingModel}
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
  onRunProfile: (profileId: string) => void;
  onRunAllProfiles: () => void;
  onStopRun: () => void;
  onDeleteRun: (runId: number) => void;
};

const analystRuleStatusLabels: Record<string, string> = {
  pass: "通过",
  warn: "观察",
  fail: "风险",
  unknown: "未知"
};

function AnalystPanel({
  profiles,
  runs,
  failedRuns,
  runState,
  onRunProfile,
  onRunAllProfiles,
  deleteState,
  onStopRun,
  onDeleteRun
}: AnalystPanelProps) {
  const isRunningAll = runState.status === "running_all";
  const isRunningAny = runState.status === "running" || runState.status === "running_all";
  const isDeletingRun = deleteState.status === "deleting";

  return (
    <section className="data-panel analyst-panel" aria-labelledby="analyst-view-heading">
      <div className="data-panel__heading">
        <div>
          <BrainCircuit aria-hidden="true" size={20} />
          <h3 id="analyst-view-heading">分析师视角</h3>
        </div>
        <div className="data-panel__actions">
          <span>{runs.total} 个成功 run</span>
          {failedRuns.total > 0 ? <span>{failedRuns.total} 个最近失败</span> : null}
          <button
            className="panel-action"
            type="button"
            title="生成全部分析师视角"
            disabled={isRunningAny}
            onClick={onRunAllProfiles}
          >
            <PlayCircle aria-hidden="true" size={15} />
            <span>{isRunningAll ? "生成中" : "生成全部"}</span>
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
                    <span>{formatDateTime(latestRun.created_at)}</span>
                    {typeof result.confidence === "number" ? (
                      <span>数据置信度 {formatImportanceScore(result.confidence)}</span>
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
                  <p>{result.overview}</p>

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
                        {analysisBasisItems.map((item) => (
                          <span key={item}>{item}</span>
                        ))}
                      </div>
                    </div>
                  ) : null}

                  {scoreExplanationItems.length > 0 ? (
                    <div className="analyst-score-notes">
                      {scoreExplanationItems.map((item) => (
                        <span key={item}>{item}</span>
                      ))}
                    </div>
                  ) : null}

                  {result.accounting_events && result.accounting_events.length > 0 ? (
                    <div className="analyst-accounting-alert">
                      <strong>会计口径提示</strong>
                      <ul>
                        {result.accounting_events.slice(0, 3).map((event, index) => (
                          <li key={`${event.event_type ?? "accounting"}-${event.source_id ?? index}`}>
                            {formatAccountingEvent(event)}
                          </li>
                        ))}
                      </ul>
                    </div>
                  ) : null}

                  {ruleChecks.length > 0 ? (
                    <ul className="analyst-rule-check-list">
                      {ruleChecks.map((check) => (
                        <li key={check.rule_id}>
                          <span className={`rule-status rule-status--${check.status}`}>
                            {analystRuleStatusLabels[check.status] ?? check.status}
                          </span>
                          <strong>{getRuleLabel(profile, check.rule_id)}</strong>
                          <span>{check.summary}</span>
                        </li>
                      ))}
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
    </section>
  );
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
  const summary = event.summary || event.comparability_impact || "需要复核同比可比口径。";
  const source =
    typeof event.source_id === "number" || typeof event.source_id === "string"
      ? ` 来源 ${event.source_type ?? "source"} #${event.source_id}`
      : "";
  return `${label}：${summary}${source}`;
}

function normalizeStringList(value: unknown): string[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value
    .map((item) => String(item).trim())
    .filter((item, index, items) => item.length > 0 && items.indexOf(item) === index);
}

function sanitizeAnnouncementTags(value: unknown): string[] {
  const genericTags = new Set(["待复核", "其他", "公告", "公司公告", "搜索线索", "智能摘要"]);
  return normalizeStringList(value).filter((tag) => !genericTags.has(tag));
}

function formatSemicolonList(value: unknown): string {
  return normalizeStringList(value)
    .map((item) => item.replace(/[。；;]+$/u, ""))
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
      const suffix =
        neededInputs.length > 0 ? `，需补充 ${neededInputs.slice(0, 3).join("、")}` : "";
      return `${item.assumption_type}：${item.reason}${suffix}`;
    })
    .filter((item) => item.trim().length > 0);
  return formatSemicolonList([...suggestions, ...detailItems]);
}

function formatQuestionList(value: unknown): string {
  return normalizeStringList(value)
    .map((item) => item.replace(/[。；;？?]+$/u, ""))
    .filter((item) => item.length > 0)
    .map((item) => `${item}？`)
    .join(" ");
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

function toAnalysisRunListResponse(response: { items: AnalysisRunListResponse["items"] }) {
  return {
    items: response.items,
    total: response.items.length,
    limit: response.items.length,
    offset: 0
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

function formatFinancialValue(key: string, value: unknown, currency: string): string {
  if (typeof value === "number") {
    if (isRatioField(key)) {
      return `${(value * 100).toFixed(1)}%`;
    }

    if (isMoneyField(key)) {
      return `${formatLargeNumber(value)} ${currency}`;
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
  return `${formatLargeNumber(value)} 元`;
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
    "gross_profit",
    "net_profit",
    "deducted_net_profit",
    "operating_cash_flow"
  ].includes(key);
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
