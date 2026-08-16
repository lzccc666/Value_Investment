import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => {
  const company = {
    id: 1,
    ticker: "600519.SH",
    exchange: "SSE",
    name: "贵州茅台",
    industry: "白酒",
    description: "A股白酒公司，真实公司主数据样本。",
    listed_date: "2001-08-27",
    status: "未研究",
    tags: ["A股", "白酒", "消费"],
    market_cap: 1694223093019.29,
    current_price: 1355.29,
    pe_ttm: 20.48,
    pe_dynamic: 15.55,
    pe_static: 20.58,
    pb_ratio: 7.18,
    ps_ratio: 10.57,
    dividend_yield_ttm: 0.03838277861071787,
    dividend_yield_static: 0.03838527303964923,
    market_data_source: "eastmoney_quote_snapshot",
    market_data_source_url: "https://example.test/quote",
    market_data_updated_at: "2026-08-13T12:00:00Z",
    created_at: "2026-08-09T00:00:00Z",
    updated_at: "2026-08-09T00:00:00Z"
  };
  const investmentMemo = {
    id: 101,
    company_id: 1,
    generation_run_id: 301,
    parent_memo_id: null,
    version_no: 1,
    editor_type: "model",
    title: "综合投资备忘录",
    conclusion: "需复核",
    sections: {
      executive_summary: "多视角显示公司质量较好，但估值输入仍需复核。",
      core_thesis: ["现金流质量是后续估值的核心输入。"],
      key_risks: ["渠道库存恶化会削弱增长质量。"],
      analyst_scorecard: {
        total_score: 0.07,
        suggested_safety_margin: 0.155,
        coverage: {
          successful_profiles: 2,
          total_profiles: 10,
          known_rules: 8,
          total_rules: 40
        },
        analyst_items: [
          {
            profile_id: "buffett",
            profile_name: "巴菲特",
            availability: "success",
            rule_score_total: 4,
            analyst_weight: 0.1,
            weighted_score: 0.1,
            rule_scores: [
              { rule_id: "moat", rule_label: "护城河", status: "pass", score: 1 },
              { rule_id: "quality", rule_label: "盈利质量", status: "pass", score: 1 },
              { rule_id: "management", rule_label: "管理层", status: "pass", score: 1 },
              { rule_id: "margin_of_safety", rule_label: "安全边际", status: "pass", score: 1 }
            ]
          },
          {
            profile_id: "fisher",
            profile_name: "费雪",
            availability: "success",
            rule_score_total: -1.2,
            analyst_weight: 0.1,
            weighted_score: -0.03
          }
        ]
      },
      valuation_assumption_queue: [
        {
          assumption_type: "base_free_cash_flow",
          reason: "010 需要复核自由现金流基准。"
        }
      ]
    },
    markdown: "# 综合投资备忘录",
    source_analyst_run_ids: [11, 13],
    source_snapshot_hash: "memo-hash",
    change_note: null,
    status: "draft",
    is_latest: true,
    created_at: "2026-08-09T01:00:00Z",
    updated_at: "2026-08-09T01:00:00Z"
  };

  return {
    company,
    investmentMemo,
    createdCompany: {
      ...company,
      id: 99,
      ticker: "SONY.US",
      exchange: "NYSE",
      name: "Sony Group Corporation 索尼集团",
      industry: "消费电子",
      description: "手动新增的研究对象。",
      listed_date: "1970-09-17",
      status: "观察中",
      tags: ["美股", "消费电子"],
      market_cap: null,
      current_price: null,
      pe_ttm: null,
      pe_dynamic: null,
      pe_static: null,
      pb_ratio: null,
      ps_ratio: null,
      dividend_yield_ttm: null,
      dividend_yield_static: null,
      market_data_source: null,
      market_data_source_url: null,
      market_data_updated_at: null
    },
    getHealth: vi.fn(),
    getCompanies: vi.fn(),
    createCompany: vi.fn(),
    getCompany: vi.fn(),
    refreshCompanyProfile: vi.fn(),
    getCompanyFinancials: vi.fn(),
    getCompanyFinancialEvidencePack: vi.fn(),
    syncCompanyFinancials: vi.fn(),
    deleteCompanyFinancialStatement: vi.fn(),
    getCompanyAnnouncements: vi.fn(),
    syncCompanyAnnouncements: vi.fn(),
    deleteCompanyAnnouncement: vi.fn(),
    summarizeCompanyAnnouncement: vi.fn(),
    summarizeCompanyAnnouncements: vi.fn(),
    summarizeCompanyAnnouncementsDeep: vi.fn(),
    getCompanyEvidence: vi.fn(),
    getEvidenceModelConfig: vi.fn(),
    runEvidenceModelSmokeTest: vi.fn(),
    searchCompanyEvidence: vi.fn(),
    importTextEvidence: vi.fn(),
    deleteEvidence: vi.fn(),
    getAnalystProfiles: vi.fn(),
    getCompanyAnalysisRuns: vi.fn(),
    getLatestCompanyAnalysisRuns: vi.fn(),
    runCompanyAnalysis: vi.fn(),
    runCompanyAnalysisBatch: vi.fn(),
    deleteCompanyAnalysisRun: vi.fn(),
    updateAnalysisRunRuleStatus: vi.fn(),
    getLatestInvestmentMemo: vi.fn(),
    getInvestmentMemos: vi.fn(),
    getInvestmentMemo: vi.fn(),
    generateInvestmentMemo: vi.fn(),
    archiveInvestmentMemo: vi.fn(),
    deleteInvestmentMemo: vi.fn(),
    getLatestValuationRun: vi.fn(),
    getValuationRuns: vi.fn(),
    createValuationDraft: vi.fn(),
    recalculateValuationRun: vi.fn(),
    getLatestPriceDecisionRun: vi.fn(),
    getPriceDecisionRuns: vi.fn(),
    createPriceDecisionRun: vi.fn(),
    deletePriceDecisionRun: vi.fn(),
    getDataManagementSummary: vi.fn(),
    previewDataOperation: vi.fn(),
    executeDataOperation: vi.fn(),
    getBackups: vi.fn(),
    createBackup: vi.fn(),
    verifyBackup: vi.fn(),
    previewBackupRestore: vi.fn(),
    deleteBackup: vi.fn(),
    getAutomaticBackupSettings: vi.fn(),
    updateAutomaticBackupSettings: vi.fn(),
    getCurrentParameterConfig: vi.fn(),
    getDefaultParameterConfig: vi.fn(),
    validateParameterConfig: vi.fn(),
    publishParameterConfig: vi.fn()
  };
});

vi.mock("../services/api", () => ({
  getHealth: mocks.getHealth,
  getCompanies: mocks.getCompanies,
  createCompany: mocks.createCompany,
  getCompany: mocks.getCompany,
  refreshCompanyProfile: mocks.refreshCompanyProfile,
  getCompanyFinancials: mocks.getCompanyFinancials,
  getCompanyFinancialEvidencePack: mocks.getCompanyFinancialEvidencePack,
  syncCompanyFinancials: mocks.syncCompanyFinancials,
  deleteCompanyFinancialStatement: mocks.deleteCompanyFinancialStatement,
  getCompanyAnnouncements: mocks.getCompanyAnnouncements,
  syncCompanyAnnouncements: mocks.syncCompanyAnnouncements,
  deleteCompanyAnnouncement: mocks.deleteCompanyAnnouncement,
  summarizeCompanyAnnouncement: mocks.summarizeCompanyAnnouncement,
  summarizeCompanyAnnouncements: mocks.summarizeCompanyAnnouncements,
  summarizeCompanyAnnouncementsDeep: mocks.summarizeCompanyAnnouncementsDeep,
  getAnnouncementDisplayStatus: (announcement: {
    summary?: string | null;
    summary_status?: string | null;
    summary_model_name?: string | null;
  }) => {
    if (announcement.summary_model_name && announcement.summary_model_name !== "metadata_keyword") {
      return "deep_summarized";
    }
    if (announcement.summary_model_name === "metadata_keyword" || announcement.summary) {
      return "quick_summarized";
    }
    return announcement.summary_status || "unprocessed";
  },
  getCompanyEvidence: mocks.getCompanyEvidence,
  getEvidenceModelConfig: mocks.getEvidenceModelConfig,
  runEvidenceModelSmokeTest: mocks.runEvidenceModelSmokeTest,
  searchCompanyEvidence: mocks.searchCompanyEvidence,
  importTextEvidence: mocks.importTextEvidence,
  deleteEvidence: mocks.deleteEvidence,
  getAnalystProfiles: mocks.getAnalystProfiles,
  getCompanyAnalysisRuns: mocks.getCompanyAnalysisRuns,
  getLatestCompanyAnalysisRuns: mocks.getLatestCompanyAnalysisRuns,
  runCompanyAnalysis: mocks.runCompanyAnalysis,
  runCompanyAnalysisBatch: mocks.runCompanyAnalysisBatch,
  deleteCompanyAnalysisRun: mocks.deleteCompanyAnalysisRun,
  updateAnalysisRunRuleStatus: mocks.updateAnalysisRunRuleStatus,
  getLatestInvestmentMemo: mocks.getLatestInvestmentMemo,
  getInvestmentMemos: mocks.getInvestmentMemos,
  getInvestmentMemo: mocks.getInvestmentMemo,
  generateInvestmentMemo: mocks.generateInvestmentMemo,
  archiveInvestmentMemo: mocks.archiveInvestmentMemo,
  deleteInvestmentMemo: mocks.deleteInvestmentMemo,
  getLatestValuationRun: mocks.getLatestValuationRun,
  getValuationRuns: mocks.getValuationRuns,
  createValuationDraft: mocks.createValuationDraft,
  recalculateValuationRun: mocks.recalculateValuationRun,
  getLatestPriceDecisionRun: mocks.getLatestPriceDecisionRun,
  getPriceDecisionRuns: mocks.getPriceDecisionRuns,
  createPriceDecisionRun: mocks.createPriceDecisionRun,
  deletePriceDecisionRun: mocks.deletePriceDecisionRun,
  getDataManagementSummary: mocks.getDataManagementSummary,
  previewDataOperation: mocks.previewDataOperation,
  executeDataOperation: mocks.executeDataOperation,
  getBackups: mocks.getBackups,
  createBackup: mocks.createBackup,
  verifyBackup: mocks.verifyBackup,
  previewBackupRestore: mocks.previewBackupRestore,
  deleteBackup: mocks.deleteBackup,
  getAutomaticBackupSettings: mocks.getAutomaticBackupSettings,
  updateAutomaticBackupSettings: mocks.updateAutomaticBackupSettings,
  getCurrentParameterConfig: mocks.getCurrentParameterConfig,
  getDefaultParameterConfig: mocks.getDefaultParameterConfig,
  validateParameterConfig: mocks.validateParameterConfig,
  publishParameterConfig: mocks.publishParameterConfig
}));

import { App } from "../app/App";

beforeEach(() => {
  mocks.getHealth.mockResolvedValue({
    status: "ok",
    service: "Value Investment API",
    version: "0.1.0",
    environment: "development",
    checked_at: "2026-01-01T00:00:00Z"
  });
  mocks.getCompanies.mockResolvedValue({
    items: [mocks.company],
    total: 1,
    limit: 20,
    offset: 0
  });
  mocks.createCompany.mockResolvedValue(mocks.createdCompany);
  mocks.getCompany.mockImplementation((companyId: number) =>
    Promise.resolve(companyId === 99 ? mocks.createdCompany : mocks.company)
  );
  mocks.refreshCompanyProfile.mockResolvedValue({
    ...mocks.company,
    market_cap: 1800000000000,
    current_price: 1420.5,
    pe_dynamic: 16.12,
    pe_static: 21.34,
    pb_ratio: 7.56,
    ps_ratio: 11.2,
    dividend_yield_ttm: 0.0408,
    dividend_yield_static: 0.0384,
    market_data_updated_at: "2026-08-13T14:30:00Z",
    updated_at: "2026-08-13T14:30:00Z"
  });
  mocks.getCompanyFinancials.mockResolvedValue({
    items: [
      {
        id: 1,
        company_id: 1,
        period: "2025A",
        statement_type: "income_statement",
        currency: "CNY",
        fields: {
          revenue: 100,
          gross_margin: 0.58,
          net_profit: 24,
          operating_cash_flow: 28
        },
        source: "test_fixture",
        source_url: null,
        created_at: "2026-08-09T00:00:00Z"
      }
    ],
    total: 1,
    limit: 60,
    offset: 0
  });
  mocks.getCompanyFinancialEvidencePack.mockResolvedValue(makeFinancialEvidencePack());
  mocks.syncCompanyFinancials.mockResolvedValue({
    company_id: 1,
    source: "eastmoney_f10_main_finance",
    fetched: 2,
    created: 2,
    updated: 0,
    items: [
      {
        id: 2,
        company_id: 1,
        period: "2025年报",
        statement_type: "main_financial_indicators",
        currency: "CNY",
        fields: {
          revenue: 172054171890.91,
          net_profit: 82320067101.68,
          roe: 0.3253
        },
        source: "eastmoney_f10_main_finance",
        source_url: "https://example.test/financials",
        created_at: "2026-08-09T00:00:00Z"
      },
      {
        id: 3,
        company_id: 1,
        period: "2016年报",
        statement_type: "main_financial_indicators",
        currency: "CNY",
        fields: {
          revenue: 40155000000,
          net_profit: 16718000000,
          roe: 0.246
        },
        source: "eastmoney_f10_main_finance",
        source_url: "https://example.test/financials",
        created_at: "2026-08-09T00:00:00Z"
      }
    ]
  });
  mocks.deleteCompanyFinancialStatement.mockResolvedValue({ id: 2, deleted: true });
  mocks.getCompanyAnnouncements.mockResolvedValue({
    items: [
      {
        id: 1,
        company_id: 1,
        title: "年度经营摘要已导入",
        published_at: "2026-01-15T00:00:00Z",
        category: "annual_report",
        content: null,
        raw_content: null,
        summary: "示例公告用于验证公告列表和后续摘要工作流。",
        source: "test_fixture",
        source_url: null,
        raw_url: null,
        created_at: "2026-08-09T00:00:00Z"
      }
    ],
    total: 1,
    limit: 40,
    offset: 0
  });
  mocks.syncCompanyAnnouncements.mockResolvedValue({
    company_id: 1,
    source: "eastmoney_announcements",
    fetched: 1,
    created: 1,
    updated: 0,
    skipped: 0,
    pruned: 0,
    errors: [],
    items: [
      {
        id: 2,
        company_id: 1,
        title: "贵州茅台:重大事项公告",
        published_at: "2026-07-18T00:00:00Z",
        category: "其他",
        content: null,
        raw_content: null,
        summary: null,
        source: "eastmoney_announcements",
        source_url: "https://example.test/notices/detail/600519/AN1.html",
        raw_url: "https://example.test/pdf/AN1.pdf",
        created_at: "2026-08-09T00:00:00Z"
      }
    ]
  });
  mocks.deleteCompanyAnnouncement.mockResolvedValue({ id: 1, deleted: true });
  mocks.summarizeCompanyAnnouncement.mockResolvedValue({
    company_id: 1,
    announcement_id: 1,
    run_id: null,
    status: "success",
    summary_status: "summarized",
    announcement: {
      id: 1,
      company_id: 1,
      title: "年度经营摘要已导入",
      published_at: "2026-01-15T00:00:00Z",
      category: "annual_report",
      content: null,
      raw_content: "年度经营摘要原文。",
      summary: "深度摘要：年度经营保持稳定。",
      source: "test_fixture",
      source_url: null,
      raw_url: null,
      key_facts: ["年度经营保持稳定"],
      impact_direction: "neutral",
      sentiment: "neutral",
      positive_impacts: [],
      negative_impacts: [],
      neutral_impacts: ["需要结合财报继续复核"],
      risk_tips: ["关注经营现金流"],
      review_questions: ["复核公告原文数字"],
      tags: ["财报"],
      summary_status: "summarized",
      summary_model_name: "test-model",
      summary_prompt_version: "announcement_summary_keywords_v3",
      summarized_at: "2026-08-11T00:00:00Z",
      created_at: "2026-08-09T00:00:00Z"
    }
  });
  mocks.summarizeCompanyAnnouncements.mockResolvedValue({
    company_id: 1,
    requested: 1,
    processed: 1,
    remaining: 0,
    succeeded: 1,
    failed: 0,
    status: "success",
    items: [
      {
        announcement_id: 1,
        run_id: 100,
        status: "success",
        summary_status: "summarized",
        error: null,
        error_type: null,
        announcement: {
          id: 1,
          company_id: 1,
          title: "年度经营摘要已导入",
          published_at: "2026-01-15T00:00:00Z",
          category: "annual_report",
          content: null,
          raw_content: "年度经营摘要原文。",
          summary: "模型摘要：年度经营保持稳定。",
          source: "test_fixture",
          source_url: null,
          raw_url: null,
          key_facts: ["年度经营保持稳定"],
          impact_direction: "neutral",
          sentiment: "neutral",
          positive_impacts: [],
          negative_impacts: [],
          neutral_impacts: ["需要结合财报继续复核"],
          risk_tips: ["关注经营现金流"],
          review_questions: ["复核公告原文数字"],
          tags: ["财报"],
          summary_status: "summarized",
          summary_model_name: "metadata_keyword",
          summary_prompt_version: "announcement_summary_keywords_v3",
          summarized_at: "2026-08-11T00:00:00Z",
          created_at: "2026-08-09T00:00:00Z"
        }
      }
    ]
  });
  mocks.summarizeCompanyAnnouncementsDeep.mockResolvedValue({
    company_id: 1,
    requested: 1,
    processed: 1,
    remaining: 0,
    succeeded: 1,
    failed: 0,
    status: "success",
    items: [
      {
        announcement_id: 1,
        run_id: null,
        status: "success",
        summary_status: "summarized",
        error: null,
        error_type: null,
        announcement: {
          id: 1,
          company_id: 1,
          title: "年度经营摘要已导入",
          published_at: "2026-01-15T00:00:00Z",
          category: "annual_report",
          content: null,
          raw_content: "年度经营摘要原文。",
          summary: "深度摘要：年度经营保持稳定。",
          source: "test_fixture",
          source_url: null,
          raw_url: null,
          key_facts: ["年度经营保持稳定"],
          impact_direction: "neutral",
          sentiment: "neutral",
          positive_impacts: [],
          negative_impacts: [],
          neutral_impacts: ["需要结合财报继续复核"],
          risk_tips: ["关注经营现金流"],
          review_questions: ["复核公告原文数字"],
          tags: ["财报"],
          summary_status: "summarized",
          summary_model_name: "metadata_keyword",
          summary_prompt_version: "announcement_summary_keywords_v3",
          summarized_at: "2026-08-11T00:00:00Z",
          created_at: "2026-08-09T00:00:00Z"
        }
      }
    ]
  });
  mocks.getCompanyEvidence.mockResolvedValue({
    items: [
      {
        id: 1,
        company_id: 1,
        source_type: "industry_news",
        title: "测试行业证据已入库",
        source: "test_fixture",
        source_url: "https://example.test/evidence",
        published_at: "2026-02-01T00:00:00Z",
        summary: "示例外部信息用于验证 Evidence 列表、模型搜索入口和复核状态展示。",
        key_facts: ["行业需求变化需要结合公告和财务数据继续复核"],
        impact_direction: "mixed",
        importance_score: 0.62,
        credibility_score: 0.55,
        tags: ["示例", "行业"],
        requires_review: true,
        price_sensitive: false,
        use_scope: ["fundamental_analysis", "analyst_view", "intrinsic_valuation"],
        analysis_status: "model_analyzed",
        analysis_note: "模型按测试 fixture 完成结构化。",
        raw_snapshot: {
          query: "贵州茅台 行业需求",
          title: "测试行业证据已入库"
        },
        created_at: "2026-08-09T00:00:00Z"
      }
    ],
    total: 1,
    limit: 10,
    offset: 0
  });
  mocks.getEvidenceModelConfig.mockResolvedValue({
    provider: "openai_compatible",
    base_url: "https://api.deepseek.com",
    model_name: "fake-model",
    wire_api: "chat_completions",
    api_key_configured: true
  });
  mocks.runEvidenceModelSmokeTest.mockResolvedValue({
    provider: "openai_compatible",
    base_url: "https://api.deepseek.com",
    model_name: "fake-model",
    wire_api: "chat_completions",
    api_key_configured: true,
    ok: true,
    message: "model gateway ok"
  });
  mocks.searchCompanyEvidence.mockResolvedValue({
    company_id: 1,
    run_id: 8,
    status: "success",
    created: 1,
    diagnostics: {
      provider_result_count: 12,
      filtered_out_count: 4,
      sent_to_model_count: 8
    },
    items: [
      {
        id: 2,
        company_id: 1,
        source_type: "policy",
        title: "白酒行业监管政策变化",
        source: "example.test",
        source_url: "https://example.test/policy",
        published_at: "2026-08-01T00:00:00Z",
        summary: "政策信息可能影响高端白酒渠道监管，需要后续复核原文。",
        key_facts: ["监管政策提到渠道合规要求"],
        impact_direction: "mixed",
        importance_score: 0.82,
        credibility_score: 0.76,
        tags: ["政策", "白酒"],
        requires_review: true,
        price_sensitive: false,
        use_scope: ["fundamental_analysis", "analyst_view", "intrinsic_valuation"],
        analysis_status: "model_analyzed",
        analysis_note: "来源为政策页面，重要性较高。",
        raw_snapshot: {
          query: "贵州茅台 白酒政策",
          title: "白酒行业监管政策变化"
        },
        created_at: "2026-08-09T00:00:00Z"
      }
    ]
  });
  mocks.importTextEvidence.mockResolvedValue({
    company_id: 1,
    run_id: 10,
    status: "success",
    created: 1,
    diagnostics: {
      mode: "manual_text_import"
    },
    items: [
      {
        id: 7,
        company_id: 1,
        source_type: "web",
        title: "手动导入渠道调研纪要",
        source: "用户粘贴资料",
        source_url: "https://example.test/manual-source",
        published_at: "2026-08-10T00:00:00Z",
        summary: "手动导入文本提到渠道库存和经销商回款节奏需要继续复核。",
        key_facts: ["渠道库存去化节奏仍需复核"],
        impact_direction: "mixed",
        importance_score: 0.68,
        credibility_score: 0.6,
        tags: ["手动导入", "渠道"],
        requires_review: true,
        price_sensitive: false,
        use_scope: ["fundamental_analysis", "analyst_view", "intrinsic_valuation"],
        analysis_status: "model_analyzed",
        analysis_note: "由用户手动导入文本生成，需复核来源。",
        raw_snapshot: {
          import_mode: "manual_text_import"
        },
        created_at: "2026-08-10T00:00:00Z"
      }
    ]
  });
  mocks.deleteEvidence.mockResolvedValue({ id: 1, deleted: true });
  mocks.getAnalystProfiles.mockResolvedValue({
    items: [
      {
        id: "buffett",
        name: "Warren Buffett",
        display_name: "巴菲特",
        description: "从护城河、长期盈利质量、管理层可信度和安全边际看公司。",
        philosophy: "只在证据支持的范围内判断企业长期经济特征。",
        rules: [
          { id: "moat", label: "护城河", description: "业务是否具备可持续竞争优势。" },
          { id: "quality", label: "盈利质量", description: "利润是否由现金流支撑。" },
          { id: "management", label: "管理层", description: "管理层是否审慎透明。" },
          { id: "margin_of_safety", label: "安全边际", description: "是否有足够容错。" }
        ],
        prompt_focus: ["长期业务质量", "现金流质量"]
      },
      {
        id: "peter_lynch",
        name: "Peter Lynch",
        display_name: "彼得林奇",
        description: "从可理解业务、成长路径、行业景气和财务兑现度看公司。",
        philosophy: "先理解生意和增长来源，再核对财务是否兑现。",
        rules: [
          { id: "understandable_business", label: "可理解业务", description: "业务模式是否清楚。" }
        ],
        prompt_focus: ["业务故事", "增长兑现"]
      }
    ]
  });
  mocks.getCompanyAnalysisRuns.mockResolvedValue({
    items: [],
    total: 0,
    limit: 10,
    offset: 0
  });
  mocks.getLatestCompanyAnalysisRuns.mockImplementation(
    (_companyId: number, params: { status?: string } = {}) =>
      Promise.resolve(
        params.status === "failed"
          ? {
              company_id: 1,
              run_type: "analyst_view",
              analyst_profile: null,
              status: "failed",
              items: []
            }
          : {
              company_id: 1,
              run_type: "analyst_view",
              analyst_profile: null,
              status: "success",
              items: [
                {
                  id: 11,
                  company_id: 1,
                  run_type: "analyst_view",
                  analyst_profile: "buffett",
                  run_version: "008_v1",
                  model_name: "fake-model",
                  prompt_version: "analyst_view_v1",
                  data_snapshot_hash: "hash",
                  result: {
                    analyst_profile: "buffett",
                    overview: "现金流质量较好，但证据仍需补充。",
                    profile_fit_score: 0.68,
                    confidence: 0.73,
                    key_observations: ["种子财务显示利润和现金流匹配。"],
                    rule_checks: [
                      {
                        rule_id: "moat",
                        status: "warn",
                        summary: "有白酒标签和行业证据，但护城河证据还不足。",
                        evidence_ids: [1],
                        financial_periods: ["2025A"],
                        announcement_ids: [1]
                      }
                    ],
                    supporting_evidence_ids: [1],
                    financial_observations: ["2025A 毛利率 58%。"],
                    announcement_observations: ["年度经营摘要已导入。"],
                    risk_flags: ["估值数据缺失。", "管理层证据不足。"],
                    counter_evidence: ["如果渠道库存恶化，护城河判断需要下调。"],
                    valuation_assumption_suggestions: ["后续估值模块应验证自由现金流可持续性。"],
                    valuation_assumption_details: [
                      {
                        assumption_type: "利润可持续性",
                        reason: "会计政策变更可能影响同比口径。",
                        needed_inputs: ["会计政策变更具体影响说明"],
                        source_refs: {
                          financial_periods: ["2025年报"],
                          announcement_ids: [44],
                          external_evidence_ids: []
                        }
                      }
                    ],
                    data_gaps: ["缺少估值和更长周期财务数据。", "缺少渠道库存数据。"],
                    follow_up_questions: [
                      "现金流是否能连续多年覆盖利润？",
                      "渠道库存是否需要继续跟踪？"
                    ],
                    analysis_basis: {
                      financial_periods: [
                        "2026一季报",
                        "2025年报",
                        "2025三季报",
                        "2025中报",
                        "2025一季报"
                      ],
                      announcement_ids: [44, 1313, 37, 43, 35, 28],
                      external_evidence_ids: [1, 2, 3, 4, 5, 6],
                      accounting_event_count: 1,
                      accounting_event_labels: ["收入确认/核算方式变化"],
                      notes: ["缺少 007 外部信息。"]
                    },
                    accounting_events: [
                      {
                        event_type: "accounting_policy_change",
                        label: "会计政策变更",
                        source_type: "announcement",
                        source_id: 1336,
                        source_title: "会计政策变更公告",
                        summary: "会计政策或核算政策发生变化，跨期同比需要先确认可比口径。",
                        comparability_impact: "同比变化需要按可比口径复核。",
                        matched_keywords: ["会计政策变更"],
                        confidence: 0.76
                      }
                    ]
                  },
                  confidence: 0.73,
                  parent_run_id: null,
                  is_latest: true,
                  user_note: null,
                  status: "success",
                  created_at: "2026-08-09T00:00:00Z"
                }
              ]
            }
      )
  );
  mocks.runCompanyAnalysisBatch.mockResolvedValue({
    company_id: 1,
    requested: 2,
    succeeded: 2,
    failed: 0,
    items: [
      {
        analyst_profile: "buffett",
        status: "success",
        error: null,
        error_type: null,
        run: {
          id: 12,
          company_id: 1,
          run_type: "analyst_view",
          analyst_profile: "buffett",
          run_version: "008_v1",
          model_name: "fake-model",
          prompt_version: "analyst_view_v1",
          data_snapshot_hash: "hash-next",
          result: {
            analyst_profile: "buffett",
            overview: "最新视角已生成。",
            profile_fit_score: 0.72,
            confidence: 0.76,
            key_observations: [],
            rule_checks: [],
            supporting_evidence_ids: [],
            financial_observations: [],
            announcement_observations: [],
            risk_flags: [],
            counter_evidence: [],
            valuation_assumption_suggestions: [],
            data_gaps: [],
            follow_up_questions: []
          },
          confidence: 0.76,
          parent_run_id: 11,
          is_latest: true,
          user_note: null,
          status: "success",
          created_at: "2026-08-09T00:30:00Z"
        }
      },
      {
        analyst_profile: "peter_lynch",
        status: "success",
        error: null,
        error_type: null,
        run: {
          id: 13,
          company_id: 1,
          run_type: "analyst_view",
          analyst_profile: "peter_lynch",
          run_version: "008_v1",
          model_name: "fake-model",
          prompt_version: "analyst_view_v1",
          data_snapshot_hash: "hash-next",
          result: {
            analyst_profile: "peter_lynch",
            overview: "彼得林奇视角已生成。",
            profile_fit_score: 0.64,
            confidence: 0.71,
            key_observations: [],
            rule_checks: [],
            supporting_evidence_ids: [],
            financial_observations: [],
            announcement_observations: [],
            risk_flags: [],
            counter_evidence: [],
            valuation_assumption_suggestions: [],
            data_gaps: [],
            follow_up_questions: []
          },
          confidence: 0.71,
          parent_run_id: null,
          is_latest: true,
          user_note: null,
          status: "success",
          created_at: "2026-08-09T00:31:00Z"
        }
      }
    ]
  });
  mocks.deleteCompanyAnalysisRun.mockResolvedValue({ id: 11, deleted: true });
  mocks.updateAnalysisRunRuleStatus.mockImplementation(
    (_companyId: number, _runId: number, ruleId: string, status: string) =>
      Promise.resolve({
        id: 11,
        company_id: 1,
        run_type: "analyst_view",
        analyst_profile: "buffett",
        run_version: "008_v1",
        model_name: "fake-model",
        prompt_version: "analyst_view_v1",
        data_snapshot_hash: "hash",
        result: {
          analyst_profile: "buffett",
          overview: "现金流质量较好，但证据仍需补充。",
          profile_fit_score: 0.68,
          confidence: 0.73,
          key_observations: ["种子财务显示利润和现金流匹配。"],
          rule_checks: [
            {
              rule_id: "moat",
              status: ruleId === "moat" ? status : "warn",
              summary: "有白酒标签和行业证据，但护城河证据还不足。",
              evidence_ids: [1],
              financial_periods: ["2025A"],
              announcement_ids: [1]
            }
          ],
          supporting_evidence_ids: [1],
          financial_observations: ["2025A 毛利率 58%。"],
          announcement_observations: ["年度经营摘要已导入。"],
          risk_flags: ["估值数据缺失。", "管理层证据不足。"],
          counter_evidence: ["如果渠道库存恶化，护城河判断需要下调。"],
          valuation_assumption_suggestions: ["后续估值模块应验证自由现金流可持续性。"],
          data_gaps: ["缺少估值和更长周期财务数据。", "缺少渠道库存数据。"],
          follow_up_questions: ["现金流是否能连续多年覆盖利润？"],
          accounting_events: [
            {
              event_type: "accounting_policy_change",
              label: "会计政策变更",
              source_type: "announcement",
              source_id: 1336,
              source_title: "会计政策变更公告",
              summary: "会计政策或核算政策发生变化，跨期同比需要先确认可比口径。",
              comparability_impact: "同比变化需要按可比口径复核。",
              matched_keywords: ["会计政策变更"],
              confidence: 0.76
            }
          ]
        },
        confidence: 0.73,
        parent_run_id: null,
        is_latest: true,
        user_note: null,
        status: "success",
        created_at: "2026-08-09T00:00:00Z"
      })
  );
  mocks.getLatestInvestmentMemo.mockResolvedValue({
    company_id: 1,
    item: null
  });
  mocks.getInvestmentMemos.mockResolvedValue({
    items: [],
    total: 0,
    limit: 20,
    offset: 0
  });
  mocks.getInvestmentMemo.mockResolvedValue(mocks.investmentMemo);
  mocks.generateInvestmentMemo.mockResolvedValue({
    company_id: 1,
    run: {
      id: 301,
      company_id: 1,
      run_type: "investment_memo",
      analyst_profile: "investment_committee",
      run_version: "009_v1",
      model_name: "fake-model",
      prompt_version: "investment_memo_v1",
      data_snapshot_hash: "memo-hash",
      result: mocks.investmentMemo.sections,
      confidence: 0.65,
      parent_run_id: null,
      is_latest: true,
      user_note: null,
      status: "success",
      created_at: "2026-08-09T01:00:00Z"
    },
    memo: mocks.investmentMemo
  });
  mocks.archiveInvestmentMemo.mockResolvedValue({
    id: 101,
    archived: true,
    latest_memo_id: null
  });
  mocks.deleteInvestmentMemo.mockResolvedValue({
    id: 101,
    deleted: true,
    latest_memo_id: null
  });
  mocks.getLatestValuationRun.mockResolvedValue({
    company_id: 1,
    item: null
  });
  mocks.getValuationRuns.mockResolvedValue({
    items: [],
    total: 0,
    limit: 20,
    offset: 0
  });
  mocks.createValuationDraft.mockResolvedValue({
    company_id: 1,
    item: makeValuationRun()
  });
  mocks.recalculateValuationRun.mockResolvedValue({
    company_id: 1,
    item: makeValuationRun({ id: 502 })
  });
  mocks.getLatestPriceDecisionRun.mockResolvedValue({ company_id: 1, item: null });
  mocks.getPriceDecisionRuns.mockResolvedValue({
    items: [],
    total: 0,
    limit: 20,
    offset: 0
  });
  mocks.createPriceDecisionRun.mockResolvedValue({
    company_id: 1,
    item: makePriceDecisionRun()
  });
  mocks.deletePriceDecisionRun.mockResolvedValue({
    id: 601,
    deleted: true,
    latest_price_decision_run_id: null
  });
  const backup = {
    backup_id: "20260816T100000000000Z-test",
    created_at: "2026-08-16T10:00:00Z",
    database_filename: "database.sqlite3",
    file_size: 2048,
    sha256: "a".repeat(64),
    schema_version: 0,
    record_counts: { companies: 61 },
    reason: "manual",
    application_version: "0.1.0",
    verified: true,
    integrity_check: "ok"
  };
  const automaticBackupSettings = {
    enabled: false,
    interval_hours: 24,
    max_backups: 10,
    last_auto_backup_at: null
  };
  mocks.getDataManagementSummary.mockResolvedValue({
    database_path: "D:/data/value_investment.db",
    database_size: 4096,
    record_counts: {
      companies: 61,
      financial_statements: 10,
      announcements: 5,
      evidence: 2,
      analysis_runs: 4,
      investment_memos: 2,
      valuation_runs: 2,
      price_decision_runs: 1
    },
    soft_deleted_counts: { investment_memos: 0, price_decision_runs: 1 },
    latest_backup: backup,
    automatic_backup: automaticBackupSettings,
    maintenance_active: false,
    maintenance_operation: null,
    schema_version: 0,
    integrity_check: "ok"
  });
  mocks.getBackups.mockResolvedValue({ items: [backup], total: 1 });
  mocks.getAutomaticBackupSettings.mockResolvedValue(automaticBackupSettings);
  mocks.previewDataOperation.mockImplementation((operationType: string, parameters = {}) =>
    Promise.resolve({
      operation_token: `token-${operationType}-01234567890123456789`,
      operation_type: operationType,
      parameters,
      affected_counts: { analysis_runs: 3, investment_memos: 1 },
      protected_records: operationType === "prune_versions"
        ? [{ table: "analysis_runs", record_id: 11, reason: "被保留的 Memo JSON 来源引用" }]
        : [],
      estimated_reclaim_bytes: 4096,
      requires_backup: operationType !== "delete_backup",
      confirmation_phrase: operationType === "prune_versions" ? "清理旧版本" : "清空公司研究数据",
      expires_at: "2026-08-16T11:00:00Z"
    })
  );
  mocks.executeDataOperation.mockResolvedValue({
    operation_type: "reset_company_research_data",
    affected_counts: { analysis_runs: 3, investment_memos: 1 },
    backup_id: backup.backup_id,
    protected_records: [],
    database_size_before: 4096,
    database_size_after: 4096,
    reclaimed_bytes: 0,
    integrity_check: "ok",
    restart_required: false,
    message: "数据管理操作已完成。"
  });
  mocks.createBackup.mockResolvedValue(backup);
  mocks.verifyBackup.mockResolvedValue({
    backup_id: backup.backup_id,
    valid: true,
    sha256_matches: true,
    integrity_check: "ok"
  });
  mocks.previewBackupRestore.mockResolvedValue({
    operation_token: "restore-token-01234567890123456789",
    operation_type: "restore_backup",
    parameters: { backup_id: backup.backup_id },
    affected_counts: { companies: 61 },
    protected_records: [],
    estimated_reclaim_bytes: 0,
    requires_backup: true,
    confirmation_phrase: "恢复指定备份",
    expires_at: "2026-08-16T11:00:00Z"
  });
  mocks.deleteBackup.mockResolvedValue({
    operation_type: "delete_backup",
    affected_counts: { backups: 1 },
    backup_id: null,
    protected_records: [],
    database_size_before: null,
    database_size_after: null,
    reclaimed_bytes: null,
    integrity_check: null,
    restart_required: false,
    message: "备份已删除。"
  });
  mocks.updateAutomaticBackupSettings.mockResolvedValue({
    ...automaticBackupSettings,
    enabled: true
  });
  const parameterConfig = {
    data_sampling: { company_list_limit: 20.000000000000004, company_list_limit_max: 100 },
    financial_flags: {},
    analyst_engine: {},
    valuation_rule_matrix: { rule_mappings: {} },
    memo_decision: {},
    valuation_models: {},
    price_decision: {}
  };
  const parameterValidation = {
    valid: true,
    errors: [],
    warnings: [],
    actual_parameter_count: 372,
    audit_parameter_count: 92
  };
  const currentParameterConfig = {
    config_json: parameterConfig,
    config_hash: "0123456789abcdef",
    source: "source_file",
    fallback_reason: null,
    validation: parameterValidation,
    metadata: [
      {
        path: "data_sampling.company_list_limit",
        domain: "data_sampling",
        label: "公司列表每页默认数量",
        code_name: "data_sampling.company_list_limit",
        description: "004 公司搜索未指定每页数量时返回的公司数；调大后每页公司更多、请求和渲染量也更大，调小后分页更频繁。",
        unit: "家公司",
        default_value: 20.000000000000004,
        current_value: 20.000000000000004,
        minimum: 1,
        maximum: 100,
        editable: true,
        expert: false,
        audit_only: false,
        risk: "medium"
      },
      {
        path: "data_sampling.company_list_limit_max",
        domain: "data_sampling",
        label: "公司列表单次请求上限",
        code_name: "data_sampling.company_list_limit_max",
        description: "004 公司列表接口允许请求的最大公司数；只限制单次请求规模，不改变公司池总数，也不进入分析或估值。",
        unit: "家公司",
        default_value: 100,
        current_value: 100,
        minimum: 20,
        maximum: 500,
        editable: true,
        expert: true,
        audit_only: false,
        risk: "medium"
      }
    ]
  };
  mocks.getCurrentParameterConfig.mockResolvedValue(currentParameterConfig);
  mocks.getDefaultParameterConfig.mockResolvedValue({
    ...currentParameterConfig,
    source: "builtin_default"
  });
  mocks.validateParameterConfig.mockResolvedValue(parameterValidation);
  mocks.runCompanyAnalysis.mockResolvedValue({
    id: 12,
    company_id: 1,
    run_type: "analyst_view",
    analyst_profile: "buffett",
    run_version: "008_v1",
    model_name: "fake-model",
    prompt_version: "analyst_view_v1",
    data_snapshot_hash: "hash-next",
    result: {
      analyst_profile: "buffett",
      overview: "最新视角已生成。",
      profile_fit_score: 0.72,
      confidence: 0.76,
      key_observations: [],
      rule_checks: [],
      supporting_evidence_ids: [],
      financial_observations: [],
      announcement_observations: [],
      risk_flags: [],
      counter_evidence: [],
      valuation_assumption_suggestions: [],
      data_gaps: [],
      follow_up_questions: []
    },
    confidence: 0.76,
    parent_run_id: 11,
    is_latest: true,
    user_note: null,
    status: "success",
    created_at: "2026-08-09T00:30:00Z"
  });
  mocks.getHealth.mockClear();
  mocks.getCompanies.mockClear();
  mocks.createCompany.mockClear();
  mocks.getCompany.mockClear();
  mocks.refreshCompanyProfile.mockClear();
  mocks.getCompanyFinancials.mockClear();
  mocks.getCompanyFinancialEvidencePack.mockClear();
  mocks.syncCompanyFinancials.mockClear();
  mocks.deleteCompanyFinancialStatement.mockClear();
  mocks.getCompanyAnnouncements.mockClear();
  mocks.syncCompanyAnnouncements.mockClear();
  mocks.deleteCompanyAnnouncement.mockClear();
  mocks.getCompanyEvidence.mockClear();
  mocks.getEvidenceModelConfig.mockClear();
  mocks.runEvidenceModelSmokeTest.mockClear();
  mocks.searchCompanyEvidence.mockClear();
  mocks.importTextEvidence.mockClear();
  mocks.deleteEvidence.mockClear();
  mocks.getAnalystProfiles.mockClear();
  mocks.getCompanyAnalysisRuns.mockClear();
  mocks.getLatestCompanyAnalysisRuns.mockClear();
  mocks.runCompanyAnalysis.mockClear();
  mocks.runCompanyAnalysisBatch.mockClear();
  mocks.deleteCompanyAnalysisRun.mockClear();
  mocks.updateAnalysisRunRuleStatus.mockClear();
  mocks.getLatestInvestmentMemo.mockClear();
  mocks.getInvestmentMemos.mockClear();
  mocks.getInvestmentMemo.mockClear();
  mocks.generateInvestmentMemo.mockClear();
  mocks.archiveInvestmentMemo.mockClear();
  mocks.deleteInvestmentMemo.mockClear();
  mocks.getLatestValuationRun.mockClear();
  mocks.getValuationRuns.mockClear();
  mocks.createValuationDraft.mockClear();
  mocks.recalculateValuationRun.mockClear();
  mocks.getLatestPriceDecisionRun.mockClear();
  mocks.getPriceDecisionRuns.mockClear();
  mocks.createPriceDecisionRun.mockClear();
  mocks.deletePriceDecisionRun.mockClear();
  mocks.getDataManagementSummary.mockClear();
  mocks.previewDataOperation.mockClear();
  mocks.executeDataOperation.mockClear();
  mocks.getBackups.mockClear();
  mocks.createBackup.mockClear();
  mocks.verifyBackup.mockClear();
  mocks.previewBackupRestore.mockClear();
  mocks.deleteBackup.mockClear();
  mocks.getAutomaticBackupSettings.mockClear();
  mocks.updateAutomaticBackupSettings.mockClear();
  mocks.getCurrentParameterConfig.mockClear();
  mocks.getDefaultParameterConfig.mockClear();
  mocks.validateParameterConfig.mockClear();
  mocks.publishParameterConfig.mockClear();
});

function makeSyncedFinancialStatements() {
  return {
    items: [
      {
        id: 2,
        company_id: 1,
        period: "2025年报",
        statement_type: "main_financial_indicators",
        currency: "CNY",
        fields: {
          revenue: 172054171890.91,
          net_profit: 82320067101.68,
          roe: 0.3253
        },
        source: "eastmoney_f10_main_finance",
        source_url: "https://example.test/financials",
        created_at: "2026-08-09T00:00:00Z"
      },
      {
        id: 3,
        company_id: 1,
        period: "2016年报",
        statement_type: "main_financial_indicators",
        currency: "CNY",
        fields: {
          revenue: 40155000000,
          net_profit: 16718000000,
          roe: 0.246
        },
        source: "eastmoney_f10_main_finance",
        source_url: "https://example.test/financials",
        created_at: "2026-08-09T00:00:00Z"
      }
    ],
    total: 2,
    limit: 60,
    offset: 0
  };
}

function makeValuationRun(
  overrides: Partial<{
    id: number;
    status: "draft" | "locked" | "archived" | "failed";
    analystParameterMatrixSnapshot: Record<string, unknown>;
  }> = {}
) {
  const id = overrides.id ?? 501;
  const status = overrides.status ?? "draft";
  const scenarios = {
    conservative: {
      cash_flow_growth_rate: 0.02,
      owner_earnings_growth_rate: 0.015,
      discount_rate: 0.115,
      terminal_growth_rate: 0.01
    },
    base: {
      cash_flow_growth_rate: 0.05,
      owner_earnings_growth_rate: 0.045,
      discount_rate: 0.1,
      terminal_growth_rate: 0.02
    },
    optimistic: {
      cash_flow_growth_rate: 0.08,
      owner_earnings_growth_rate: 0.075,
      discount_rate: 0.09,
      terminal_growth_rate: 0.03
    }
  };

  return {
    id,
    company_id: 1,
    memo_id: 101,
    run_version: "010_v1",
    status,
    price_blind: true,
    forbidden_price_inputs: {
      price_blind: true,
      scrubbed_items: []
    },
    input_snapshot: {
      latest_memo: {
        id: 101,
        version_no: 1
      }
    },
    input_snapshot_hash: "valuation-hash",
    valuation_inputs: {
      base_revenue: 172054171890.91,
      base_net_profit: 82320067101.68,
      base_free_cash_flow: 72320067101.68,
      capital_expenditure: 12000000000,
      cash_and_equivalents: 150000000000,
      interest_bearing_debt: 8000000000,
      shares_outstanding: 1256197800,
      latest_period: "2025年报"
    },
    model_suggested_assumptions: {
      scenarios,
      model_weights: {
        owner_earnings: 0.35,
        dcf: 0.35,
        residual_income: 0.15,
        dividend_discount: 0.1,
        asset_value: 0.05
      },
      ...(overrides.analystParameterMatrixSnapshot
        ? { analyst_parameter_matrix_snapshot: overrides.analystParameterMatrixSnapshot }
        : {})
    },
    user_adjusted_assumptions: {},
    assumptions: {
      scenarios,
      model_weights: {
        owner_earnings: 0.35,
        dcf: 0.35,
        residual_income: 0.15,
        dividend_discount: 0.1,
        asset_value: 0.05
      },
      memo_assumption_queue: [
        {
          assumption_type: "base_free_cash_flow",
          reason: "010 需要复核自由现金流基准。"
        }
      ]
    },
    methods: {
      selected_methods: ["dcf", "owner_earnings"],
      reserved_methods: ["residual_income", "dividend_discount", "asset_value"],
      base_weights: {
        owner_earnings: 0.35,
        dcf: 0.35,
        residual_income: 0.15,
        dividend_discount: 0.1,
        asset_value: 0.05
      },
      forecast_years: 5
    },
    results: {
      status: "calculated_after_user_confirmation",
      title: "无锚定估值实验",
      price_blind: true,
      method_results: [
        {
          method: "dcf",
          status: "success",
          applicability: 0.35,
          reason: "自由现金流口径可用，DCF 作为无锚定主模型。",
          scenario_values: {
            conservative: 900000000000,
            base: 1200000000000,
            optimistic: 1500000000000
          },
          per_share_values: {
            conservative: 716.45,
            base: 955.26,
            optimistic: 1194.07
          },
          input_gaps: []
        },
        {
          method: "owner_earnings",
          status: "success",
          applicability: 0.35,
          reason: "采用所有者盈余和 DCF 交叉验证。",
          scenario_values: {
            conservative: 850000000000,
            base: 1120000000000,
            optimistic: 1420000000000
          },
          per_share_values: {
            conservative: 676.64,
            base: 891.58,
            optimistic: 1130.4
          },
          input_gaps: []
        },
        {
          method: "residual_income",
          status: "skipped",
          reason: "MVP 预留。",
          input_gaps: []
        }
      ],
      model_weighting: [
        {
          method: "dcf",
          weight: 0.5,
          reason: "按用户确认的模型基准权重分配；缺失模型剔除后按比例重分配。"
        },
        {
          method: "owner_earnings",
          weight: 0.5,
          reason: "按用户确认的模型基准权重分配；缺失模型剔除后按比例重分配。"
        }
      ],
      intrinsic_value_range: {
        total_equity_value: {
          conservative: 876165000000,
          base: 1161860000000,
          optimistic: 1461850000000
        },
        per_share_value: {
          conservative: 697.47,
          base: 924.84,
          optimistic: 1163.71
        },
        unit: "CNY",
        per_share_status: "success"
      },
      valuation_input_gaps: [
        {
          field: "long_term_cash_flow_history",
          severity: "low",
          reason: "长周期现金流样本不足，仅降低置信度。",
          source: "financial_evidence_pack"
        }
      ],
      dispersion_warning: null
    },
    sensitivity: {},
    confidence: 0.72,
    confidence_summary: {
      reasons: ["估值数字来自服务层确定性公式，且保留单模型结果。"]
    },
    source_map: {
      memo_id: 101
    },
    user_note: null,
    created_at: "2026-08-09T02:00:00Z",
    updated_at: "2026-08-09T02:00:00Z"
  };
}

function makePriceDecisionRun(
  overrides: Partial<{
    id: number;
    version_no: number;
    price_status: string;
    safety_margin_override: number | null;
    effective_safety_margin: number;
  }> = {}
) {
  const effectiveMargin = overrides.effective_safety_margin ?? 0.155;
  const intrinsicValues = {
    conservative: 697.47,
    base: 924.84,
    optimistic: 1163.71
  };
  return {
    id: overrides.id ?? 601,
    company_id: 1,
    valuation_run_id: 501,
    memo_id: 101,
    version_no: overrides.version_no ?? 1,
    run_version: "011_v1",
    formula_version: "011_v1",
    status: "active",
    input_snapshot: {
      memo: { id: 101, version_no: 1 },
      valuation_run: { id: 501 }
    },
    input_snapshot_hash: "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
    intrinsic_values_per_share: intrinsicValues,
    current_price: 1355.29,
    market_data_updated_at: "2026-08-13T12:00:00Z",
    analyst_score_total: 0.07,
    analyst_scorecard_snapshot: mocks.investmentMemo.sections.analyst_scorecard,
    suggested_safety_margin: 0.155,
    safety_margin_override: overrides.safety_margin_override ?? null,
    effective_safety_margin: effectiveMargin,
    scenario_buy_prices: {
      conservative: intrinsicValues.conservative * (1 - effectiveMargin),
      base: intrinsicValues.base * (1 - effectiveMargin),
      optimistic: intrinsicValues.optimistic * (1 - effectiveMargin)
    },
    suggested_buy_price: intrinsicValues.base * (1 - effectiveMargin),
    current_margin: 1 - 1355.29 / intrinsicValues.base,
    price_status: overrides.price_status ?? "高于乐观内在价值",
    created_at: "2026-08-16T04:00:00Z",
    updated_at: "2026-08-16T04:00:00Z",
    deleted_at: null
  };
}

function makeFinancialEvidencePack(
  latestPeriod = "2025A",
  facts: Record<string, number> = {
    revenue: 100,
    net_profit: 24
  }
) {
  return {
    latest_period: latestPeriod,
    periods: latestPeriod ? [latestPeriod] : [],
    financial_facts: {
      latest: facts,
      series: {
        revenue: latestPeriod ? [{ period: latestPeriod, value: facts.revenue }] : [],
        net_profit: latestPeriod ? [{ period: latestPeriod, value: facts.net_profit }] : []
      }
    },
    financial_metrics: {
      profitability: {
        roe: 0.32,
        gross_margin: 0.58,
        net_margin: 0.24
      },
      cash_quality: {
        operating_cash_flow_to_revenue: 0.28
      },
      growth_quality: {
        revenue_yoy: 0.15,
        net_profit_yoy: 0.16
      },
      balance_sheet_safety: {},
      shareholder_return: {},
      capital_allocation: {},
      efficiency: {},
      per_share: {}
    },
    cash_flow_coverage: {
      has_operating_cash_flow: false,
      has_cash_flow_proxy: true,
      proxy_fields: ["operating_cash_flow_to_revenue"],
      note: "已有经营现金流代理指标，但缺少经营现金流绝对值。"
    },
    financial_trends: {},
    financial_flags: [
      {
        code: "profit_growth_negative",
        severity: "risk",
        message: "净利润同比为负，需要结合公告复核原因。",
        period: latestPeriod
      }
    ],
    financial_data_gaps: [
      {
        field: "capital_expenditure",
        severity: "high",
        reason: "缺少资本开支，无法计算严格自由现金流。",
        needed_by: ["valuation_lab", "analyst_view"],
        replacement_available: false
      }
    ],
    financial_data_gap_messages: ["缺少资本开支，无法计算严格自由现金流。"],
    cash_flow_quality: {
      operating_cash_flow: null,
      capital_expenditure: null,
      free_cash_flow: null,
      operating_cash_flow_to_net_profit: null,
      free_cash_flow_to_net_profit: null,
      free_cash_flow_margin: null
    },
    balance_sheet_adjustment: {
      cash_and_equivalents: null,
      interest_bearing_debt: null,
      net_cash: null,
      asset_liability_ratio: null,
      cash_to_interest_bearing_debt: null
    },
    capital_allocation: {
      capital_expenditure: null,
      dividend: null,
      buyback_amount: null,
      shares_outstanding: null,
      share_dilution_rate: null
    },
    valuation_readiness: {
      ready_methods: []
    },
    quality_matrix: {},
    analyst_summary: {},
    data_quality: {
      structured_gaps: [],
      coverage_by_topic: {},
      proxy_fields: ["operating_cash_flow_to_revenue"],
      confidence_penalties: []
    }
  };
}

async function openWorkspaceSection(sectionLabel: string) {
  const tabs = await screen.findByRole("navigation", { name: "公司工作台模块" });
  fireEvent.click(within(tabs).getByRole("button", { name: new RegExp(sectionLabel) }));
}

describe("App", () => {
  it("opens the source-backed parameter configuration center", async () => {
    render(<App />);

    fireEvent.click(screen.getByRole("button", { name: "参数配置" }));

    expect(
      await screen.findByRole("heading", { name: "参数配置中心", level: 1 })
    ).toBeInTheDocument();
    expect(await screen.findByText("当前源码参数")).toBeInTheDocument();
    expect(screen.getByText(/372 个生效参数/)).toBeInTheDocument();
    expect(screen.queryByText(/审计参数/)).not.toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "数据采样" })).toBeInTheDocument();
    expect(screen.getByText("公司列表每页默认数量")).toBeInTheDocument();
    expect(screen.getByText("公司列表单次请求上限")).toBeInTheDocument();
    expect(
      screen.getByText("公司列表每页默认数量").closest("label")?.querySelector("input")
    ).toHaveValue(20);
    expect(screen.queryByRole("button", { name: "普通参数" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "专家参数" })).not.toBeInTheDocument();
    expect(screen.queryByText("data_sampling.company_list_limit")).not.toBeInTheDocument();
    expect(screen.queryByText(/风险 medium/)).not.toBeInTheDocument();
    expect(mocks.getCurrentParameterConfig).toHaveBeenCalled();
    expect(mocks.getDefaultParameterConfig).toHaveBeenCalled();
  });

  it("renders the dashboard shell", async () => {
    render(<App />);

    expect(screen.getByRole("heading", { name: "价值投资研究工作台" })).toBeInTheDocument();
    expect(screen.getByRole("navigation")).toBeInTheDocument();
    const mainNavigation = screen.getByLabelText("主导航");
    const mainNavigationText = mainNavigation.textContent ?? "";
    const navigationLabels = [
      "概览",
      "公司搜索",
      "公司工作台",
      "财务底稿",
      "公司公告",
      "外部证据",
      "分析师视角",
      "投资备忘录",
      "估值实验室",
      "价格决策",
      "参数配置",
      "数据管理"
    ];
    navigationLabels.forEach((label) => {
      expect(within(mainNavigation).getByRole("button", { name: label })).toBeInTheDocument();
    });
    expect(mainNavigationText.indexOf("投资备忘录")).toBeLessThan(
      mainNavigationText.indexOf("估值实验室")
    );
    expect(mainNavigationText).not.toContain("Dashboard");
    expect(mainNavigationText).not.toContain("Company Search");
    expect(mainNavigationText).not.toContain("Data Management");
    expect(mainNavigationText).not.toContain("Portfolio");
    expect(mainNavigationText).not.toContain("Settings");
    expect(screen.queryByText("假设追踪")).not.toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "研究主链路" })).toBeInTheDocument();
    expect(screen.getByText("8 / 8")).toBeInTheDocument();
    expect(screen.getByText("8 / 8 已接通")).toBeInTheDocument();
    expect(screen.getAllByText("价格对照与投资决策")).toHaveLength(1);
    expect(screen.queryByTitle("模块待实现")).not.toBeInTheDocument();
    expect(screen.queryByText("下一阶段")).not.toBeInTheDocument();
    expect(screen.queryByText("仓位与组合管理")).not.toBeInTheDocument();
    expect(screen.queryByText("阶段边界")).not.toBeInTheDocument();
    expect(await within(screen.getByLabelText("研究公司")).findByText("1")).toBeInTheDocument();
    expect(await screen.findByText("Value Investment API 0.1.0")).toBeInTheDocument();
  });

  it("opens a recent company from the dashboard", async () => {
    render(<App />);

    fireEvent.click(await screen.findByRole("button", { name: "打开贵州茅台公司档案" }));

    expect(await screen.findByRole("heading", { name: "公司档案", level: 1 })).toBeInTheDocument();
    expect(await screen.findByText("基础档案")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "概览" }));
    expect(await within(screen.getByLabelText("研究公司")).findByText("1")).toBeInTheDocument();
    const currentCompanyMetric = screen.getByLabelText("当前研究对象");
    expect(within(currentCompanyMetric).getByText("贵州茅台 600519.SH")).toBeInTheDocument();
    expect(within(currentCompanyMetric).getByText("已选择")).toBeInTheDocument();
  });

  it("opens company search and company workspace", async () => {
    render(<App />);

    fireEvent.click(screen.getByRole("button", { name: "公司搜索" }));

    expect(await screen.findByRole("heading", { name: "公司搜索", level: 2 })).toBeInTheDocument();
    expect(await screen.findByText("贵州茅台")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "档案" }));

    await waitFor(() => {
      expect(mocks.getCompany).toHaveBeenCalledWith(1, expect.any(AbortSignal));
    });
    expect(mocks.getCompanyFinancials).toHaveBeenCalledWith(1, {
      period_offset: 0,
      signal: expect.any(AbortSignal)
    });
    expect(mocks.getCompanyFinancialEvidencePack).toHaveBeenCalledWith(1, expect.any(AbortSignal));

    expect(await screen.findByRole("heading", { name: "公司档案", level: 1 })).toBeInTheDocument();
    expect(await screen.findByText("基础档案")).toBeInTheDocument();
    expect(await screen.findByText("2001-08-27")).toBeInTheDocument();
    expect((await screen.findAllByText("2026年8月9日 08:00")).length).toBeGreaterThan(0);
    expect(await screen.findByText("基本信息")).toBeInTheDocument();
    expect(await screen.findByText("16,942.23亿 元")).toBeInTheDocument();
    expect(await screen.findByText("1,355.29")).toBeInTheDocument();
    expect(await screen.findByText("20.48x")).toBeInTheDocument();
    expect(await screen.findByText("15.55x")).toBeInTheDocument();
    expect(screen.queryByText("研究状态")).not.toBeInTheDocument();
    expect(await screen.findByRole("heading", { name: "研究准备度" })).toBeInTheDocument();
    expect(await screen.findByText("最新 2025A，缺口 1 项")).toBeInTheDocument();
    expect((await screen.findAllByText("至少需要 2 个成功分析师视角")).length).toBeGreaterThan(0);

    await openWorkspaceSection("Financials");
    expect(await screen.findByText("财务数据")).toBeInTheDocument();
    expect(await screen.findByText("最新期间")).toBeInTheDocument();
    expect(await screen.findByText("财务旗标")).toBeInTheDocument();
    expect(await screen.findByText("数据缺口")).toBeInTheDocument();
    expect(await screen.findByText("财务旗标明细")).toBeInTheDocument();
    expect(await screen.findByText("净利润同比为负，需要结合公告复核原因。")).toBeInTheDocument();
    expect(await screen.findByText("数据缺口明细")).toBeInTheDocument();
    expect(await screen.findByText("资本开支")).toBeInTheDocument();
    expect(await screen.findByText(/缺少资本开支，无法计算严格自由现金流。/)).toBeInTheDocument();
    expect((await screen.findAllByText("收入")).length).toBeGreaterThan(0);

    await openWorkspaceSection("Announcements");
    expect((await screen.findAllByText("年度经营摘要已导入")).length).toBeGreaterThan(0);

    await openWorkspaceSection("Evidence");
    expect(await screen.findByText("外部信息")).toBeInTheDocument();
    expect(await screen.findByText("测试行业证据已入库")).toBeInTheDocument();
    expect(await screen.findByText("#1")).toBeInTheDocument();
    expect(await screen.findByText("基本面证据")).toBeInTheDocument();
    expect(await screen.findByRole("link", { name: "test_fixture" })).toHaveAttribute(
      "href",
      "https://example.test/evidence"
    );
    expect(await screen.findByText("model_name")).toBeInTheDocument();
    expect(await screen.findByText("fake-model")).toBeInTheDocument();

    await openWorkspaceSection("Analyst Views");
    expect(
      await screen.findByRole("heading", { name: "分析师视角", level: 3 })
    ).toBeInTheDocument();
    expect(await screen.findByText("巴菲特")).toBeInTheDocument();
    expect(await screen.findByText("现金流质量较好，但证据仍需补充。")).toBeInTheDocument();
    expect(
      await screen.findByText(
        "财务期 5 期（展示 4 期：2026一季报、2025年报、2025三季报、2025中报）"
      )
    ).toBeInTheDocument();
    expect(
      await screen.findByText("公告 6 条（展示 5 条：#44、#1313、#37、#43、#35）")
    ).toBeInTheDocument();
    expect(
      await screen.findByText("外部证据 6 条（展示 5 条：#1、#2、#3、#4、#5）")
    ).toBeInTheDocument();
    const analysisBasis = screen.getByText("本次分析依据").closest(".analyst-basis");
    expect(analysisBasis).toHaveTextContent("会计口径事件 1 个 缺少 007 外部信息");
    expect(analysisBasis?.textContent).not.toContain("个缺少");
    expect(screen.getAllByText("会计口径提示")).toHaveLength(1);
    const accountingAlert = screen.getByText("会计口径提示").closest(".analyst-accounting-alert");
    expect(accountingAlert).toHaveClass("analyst-accounting-alert--panel");
    expect(accountingAlert).toHaveTextContent(
      "会计政策变更：会计政策或核算政策发生变化，跨期同比需要先确认可比口径。 来源 announcement #1336"
    );
    expect(await screen.findByText("种子财务显示利润和现金流匹配")).toBeInTheDocument();
    expect(await screen.findByText("2025A 毛利率 58%")).toBeInTheDocument();
    expect(
      await screen.findByText("现金流是否能连续多年覆盖利润？ 渠道库存是否需要继续跟踪？")
    ).toBeInTheDocument();
    expect(await screen.findByText("估值数据缺失；管理层证据不足")).toBeInTheDocument();
    expect(
      await screen.findByText(
        /利润可持续性：会计政策变更可能影响同比口径，需补充 会计政策变更具体影响说明/
      )
    ).toBeInTheDocument();
    expect(
      await screen.findByText("缺少估值和更长周期财务数据；缺少渠道库存数据")
    ).toBeInTheDocument();
    expect(screen.queryByText(/。，/)).not.toBeInTheDocument();
    expect(screen.queryByText(/。；/)).not.toBeInTheDocument();
    expect(screen.queryByText(/？；/)).not.toBeInTheDocument();

    await openWorkspaceSection("Memo");
    expect(await screen.findByText("综合备忘录准备区")).toBeInTheDocument();
    expect(screen.queryByText(/当前内容不是买卖或仓位建议/)).not.toBeInTheDocument();
    expect(await screen.findByText("可用于综合的成功视角")).toBeInTheDocument();
  });

  it("hides the new company panel while searching companies", async () => {
    render(<App />);

    fireEvent.click(screen.getByRole("button", { name: "公司搜索" }));

    expect(await screen.findByRole("heading", { name: "新增公司" })).toBeInTheDocument();

    fireEvent.change(screen.getByPlaceholderText("输入代码、名称、交易所、行业或标签"), {
      target: { value: "茅台" }
    });

    await waitFor(() => {
      expect(mocks.getCompanies).toHaveBeenLastCalledWith(
        expect.objectContaining({
          q: "茅台",
          offset: 0,
          signal: expect.any(AbortSignal)
        })
      );
    });
    expect(screen.queryByRole("heading", { name: "新增公司" })).not.toBeInTheDocument();
  });

  it("keeps the company profile visible when optional workspace modules fail", async () => {
    mocks.getLatestInvestmentMemo.mockRejectedValueOnce(new Error("Request failed: 404"));
    mocks.getInvestmentMemos.mockRejectedValueOnce(new Error("Request failed: 404"));

    render(<App />);

    fireEvent.click(screen.getByRole("button", { name: "公司搜索" }));
    expect(await screen.findByText("贵州茅台")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "档案" }));

    expect(await screen.findByRole("heading", { name: "公司档案", level: 1 })).toBeInTheDocument();
    expect(await screen.findByText("基础档案")).toBeInTheDocument();
    expect(screen.queryByText("公司档案加载失败")).not.toBeInTheDocument();
  });

  it("opens the price-blind valuation lab and recalculates editable assumptions", async () => {
    mocks.getLatestInvestmentMemo.mockResolvedValue({
      company_id: 1,
      item: mocks.investmentMemo
    });
    mocks.getLatestValuationRun.mockResolvedValue({
      company_id: 1,
      item: makeValuationRun({
        analystParameterMatrixSnapshot: {
          analyst_weights: [
            {
              profile_id: "george_soros",
              profile_name: "乔治索罗斯",
              source_run_id: 92,
              weight: 0.4
            },
            {
              profile_id: "buffett",
              profile_name: "巴菲特",
              source_run_id: 91,
              weight: 0.6
            }
          ],
          rule_impacts: [
            {
              profile_id: "george_soros",
              profile_name: "乔治索罗斯",
              source_run_id: 92,
              rule_id: "reflexivity",
              rule_label: "反身性",
              status: "warn",
              dimensions: { cyclicality: 1 },
              calculation_role: "compute"
            },
            {
              profile_id: "buffett",
              profile_name: "巴菲特",
              source_run_id: 91,
              rule_id: "moat",
              rule_label: "护城河",
              status: "pass",
              dimensions: { moat_durability: 1 },
              calculation_role: "compute"
            }
          ],
          price_reference_rules: [],
          parameter_contributions: {
            discount_rate: [
              {
                source_run_id: 91,
                rule_id: "moat",
                contribution: 0.10000000000000002
              }
            ]
          }
        }
      })
    });

    render(<App />);

    fireEvent.click(screen.getByRole("button", { name: "公司搜索" }));
    expect(await screen.findByText("贵州茅台")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "档案" }));
    await openWorkspaceSection("Valuation Lab");

    expect(await screen.findByRole("heading", { name: "无锚定估值实验室" })).toBeInTheDocument();
    const workspaceTabsText =
      screen.getByRole("navigation", { name: "公司工作台模块" }).textContent ?? "";
    expect(workspaceTabsText.indexOf("Memo")).toBeLessThan(
      workspaceTabsText.indexOf("Valuation Lab")
    );
    expect(await screen.findByText("price_blind=true")).toBeInTheDocument();
    expect(await screen.findByText("估值假设队列")).toBeInTheDocument();
    expect(await screen.findByText("010 需要复核自由现金流基准。")).toBeInTheDocument();
    expect(screen.queryByText(/base_free_cash_flow:/)).not.toBeInTheDocument();
    expect(await screen.findByText("单模型交叉验证")).toBeInTheDocument();
    expect((await screen.findAllByText("所有者盈余")).length).toBeGreaterThan(0);
    const analystAudit = screen.getByText("008 规则到参数审计").closest("article");
    const analystAuditText = analystAudit?.textContent ?? "";
    expect(analystAuditText.indexOf("巴菲特")).toBeLessThan(
      analystAuditText.indexOf("乔治索罗斯")
    );
    expect(analystAuditText).toContain("护城河持久性");
    expect(analystAuditText).toContain("周期性");
    expect(analystAuditText).toContain("折现率 0.1");
    expect(analystAuditText).not.toContain("moat_durability");
    expect(analystAuditText).not.toContain("cyclicality");
    expect(analystAuditText).not.toContain("discount_rate");
    expect(screen.getByText("行情更新时间")).toBeInTheDocument();
    expect(screen.getByText("基本信息")).toBeInTheDocument();
    expect(screen.getByText("1,355.29")).toBeInTheDocument();

    const discountRateInputs = screen.getAllByLabelText("折现率");
    fireEvent.change(discountRateInputs[1], { target: { value: "10.5" } });
    expect(screen.getByLabelText("所有者盈余权重")).toHaveValue(35);
    expect(screen.getByLabelText("DCF权重")).toHaveValue(35);
    fireEvent.change(screen.getByLabelText("DCF权重"), { target: { value: "45" } });
    expect(screen.getByRole("button", { name: "确认参数并计算" })).toBeDisabled();
    expect(screen.getByText("五个模型的配比合计必须等于 100%。")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("所有者盈余权重"), {
      target: { value: "25" }
    });
    fireEvent.click(screen.getByRole("button", { name: "确认参数并计算" }));

    await waitFor(() => {
      expect(mocks.recalculateValuationRun).toHaveBeenCalledWith(501, {
        assumptions: expect.objectContaining({
          scenarios: expect.objectContaining({
            base: expect.objectContaining({
              discount_rate: 0.105
            })
          }),
          model_weights: {
            owner_earnings: 0.25,
            dcf: 0.45,
            residual_income: 0.15,
            dividend_discount: 0.1,
            asset_value: 0.05
          }
        })
      });
    });
    expect(await screen.findByText("已确认参数并生成估值草稿 #502")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /锁定/ })).not.toBeInTheDocument();
  });

  it("generates a deterministic price decision from the latest calculated valuation", async () => {
    const valuation = makeValuationRun();
    const priceDecision = makePriceDecisionRun();
    mocks.getLatestValuationRun.mockResolvedValue({ company_id: 1, item: valuation });
    mocks.getValuationRuns.mockResolvedValue({
      items: [valuation], total: 1, limit: 20, offset: 0
    });
    mocks.getLatestPriceDecisionRun
      .mockResolvedValueOnce({ company_id: 1, item: null })
      .mockResolvedValue({ company_id: 1, item: priceDecision });
    mocks.getPriceDecisionRuns
      .mockResolvedValueOnce({ items: [], total: 0, limit: 20, offset: 0 })
      .mockResolvedValue({ items: [priceDecision], total: 1, limit: 20, offset: 0 });

    render(<App />);
    fireEvent.click(screen.getByRole("button", { name: "公司搜索" }));
    expect(await screen.findByText("贵州茅台")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "档案" }));
    await openWorkspaceSection("Price Decision");

    expect(await screen.findByRole("heading", { name: "价格对照与投资决策" })).toBeInTheDocument();
    expect(screen.getByText("已确认并计算")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "生成价格决策" }));

    await waitFor(() => {
      expect(mocks.createPriceDecisionRun).toHaveBeenCalledWith(1, {
        valuation_run_id: 501,
        safety_margin_override: null
      });
    });
    expect(await screen.findByText("已生成价格决策 v1")).toBeInTheDocument();
    expect(screen.getAllByText("高于乐观内在价值").length).toBeGreaterThan(0);
    expect(screen.getByText("建议买入上限")).toBeInTheDocument();
    expect(screen.getByText("-46.54%")).toBeInTheDocument();
    expect(screen.getByText(/Memo v1/)).toBeInTheDocument();
    expect(screen.queryByText(/仓位建议|强制卖出/)).not.toBeInTheDocument();
  });

  it("allows a 0%-50% margin override while keeping the suggested margin visible", async () => {
    const valuation = makeValuationRun();
    const first = makePriceDecisionRun();
    const overridden = makePriceDecisionRun({
      id: 602,
      version_no: 2,
      safety_margin_override: 0.2,
      effective_safety_margin: 0.2
    });
    mocks.getLatestValuationRun.mockResolvedValue({ company_id: 1, item: valuation });
    mocks.getValuationRuns.mockResolvedValue({ items: [valuation], total: 1, limit: 20, offset: 0 });
    mocks.getLatestPriceDecisionRun
      .mockResolvedValueOnce({ company_id: 1, item: first })
      .mockResolvedValue({ company_id: 1, item: overridden });
    mocks.getPriceDecisionRuns
      .mockResolvedValueOnce({ items: [first], total: 1, limit: 20, offset: 0 })
      .mockResolvedValue({ items: [overridden, first], total: 2, limit: 20, offset: 0 });
    mocks.createPriceDecisionRun.mockResolvedValue({ company_id: 1, item: overridden });

    render(<App />);
    fireEvent.click(screen.getByRole("button", { name: "公司搜索" }));
    expect(await screen.findByText("贵州茅台")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "档案" }));
    await openWorkspaceSection("Price Decision");

    expect(screen.getByText("系统建议值")).toBeInTheDocument();
    expect(screen.getAllByText("15.50%").length).toBeGreaterThan(0);
    fireEvent.click(screen.getByLabelText("手动覆盖安全边际"));
    fireEvent.change(screen.getByLabelText("覆盖安全边际（%）"), {
      target: { value: "20" }
    });
    fireEvent.click(screen.getByRole("button", { name: "重新计算" }));

    await waitFor(() => {
      expect(mocks.createPriceDecisionRun).toHaveBeenCalledWith(1, {
        valuation_run_id: 501,
        safety_margin_override: 0.2
      });
    });
    expect(await screen.findByText("已生成价格决策 v2")).toBeInTheDocument();
    expect(screen.getByText("用户覆盖值")).toBeInTheDocument();
    expect(screen.getAllByText("20.00%").length).toBeGreaterThan(0);
  });

  it("views and manually deletes price decision history", async () => {
    const valuation = makeValuationRun();
    const first = makePriceDecisionRun();
    const second = makePriceDecisionRun({ id: 602, version_no: 2 });
    mocks.getLatestValuationRun.mockResolvedValue({ company_id: 1, item: valuation });
    mocks.getValuationRuns.mockResolvedValue({ items: [valuation], total: 1, limit: 20, offset: 0 });
    mocks.getLatestPriceDecisionRun
      .mockResolvedValueOnce({ company_id: 1, item: second })
      .mockResolvedValue({ company_id: 1, item: first });
    mocks.getPriceDecisionRuns
      .mockResolvedValueOnce({ items: [second, first], total: 2, limit: 20, offset: 0 })
      .mockResolvedValue({ items: [first], total: 1, limit: 20, offset: 0 });

    render(<App />);
    fireEvent.click(screen.getByRole("button", { name: "公司搜索" }));
    expect(await screen.findByText("贵州茅台")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "档案" }));
    await openWorkspaceSection("Price Decision");

    fireEvent.click(screen.getByRole("button", { name: "查看价格决策 v1" }));
    expect(screen.getAllByText("建议买入上限").length).toBeGreaterThan(1);
    expect(screen.queryByText("公式版本")).not.toBeInTheDocument();
    expect(screen.queryByText("快照")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "删除价格决策 v2" }));

    await waitFor(() => expect(mocks.deletePriceDecisionRun).toHaveBeenCalledWith(602));
    expect(await screen.findByText("已删除价格决策版本")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "删除价格决策 v2" })).not.toBeInTheDocument();
  });

  it("shows actionable missing-input and old Memo errors", async () => {
    const firstRender = render(<App />);
    fireEvent.click(screen.getByRole("button", { name: "公司搜索" }));
    expect(await screen.findByText("贵州茅台")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "档案" }));
    await openWorkspaceSection("Price Decision");
    expect(await screen.findByText("缺少已完成计算的 010 估值")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "前往无锚定估值" })).toBeInTheDocument();
    firstRender.unmount();

    const valuation = makeValuationRun();
    mocks.getLatestValuationRun.mockResolvedValue({ company_id: 1, item: valuation });
    mocks.getValuationRuns.mockResolvedValue({ items: [valuation], total: 1, limit: 20, offset: 0 });
    mocks.createPriceDecisionRun.mockRejectedValueOnce(
      new Error("该估值绑定的旧 Memo 没有动态安全边际，请重新生成 Memo 和 010 估值。")
    );
    render(<App />);
    fireEvent.click(screen.getByRole("button", { name: "公司搜索" }));
    expect(await screen.findByText("贵州茅台")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "档案" }));
    await openWorkspaceSection("Price Decision");
    fireEvent.click(screen.getByRole("button", { name: "生成价格决策" }));
    expect(
      await screen.findByText("该估值绑定的旧 Memo 没有动态安全边际，请重新生成 Memo 和 010 估值。")
    ).toBeInTheDocument();
  });

  it("generates and deletes investment memo history from the memo panel", async () => {
    mocks.getLatestInvestmentMemo
      .mockResolvedValueOnce({ company_id: 1, item: null })
      .mockResolvedValueOnce({ company_id: 1, item: mocks.investmentMemo })
      .mockResolvedValue({ company_id: 1, item: null });
    mocks.getInvestmentMemos
      .mockResolvedValueOnce({ items: [], total: 0, limit: 20, offset: 0 })
      .mockResolvedValueOnce({ items: [mocks.investmentMemo], total: 1, limit: 20, offset: 0 })
      .mockResolvedValue({ items: [], total: 0, limit: 20, offset: 0 });

    render(<App />);

    fireEvent.click(screen.getByRole("button", { name: "公司搜索" }));
    expect(await screen.findByText("贵州茅台")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "档案" }));

    await openWorkspaceSection("Memo");
    expect(await screen.findByText("暂无综合投资备忘录")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "生成备忘录" }));

    expect(await screen.findByText("已生成综合投资备忘录 v1")).toBeInTheDocument();
    expect(await screen.findByText("最新综合备忘录")).toBeInTheDocument();
    expect(
      await screen.findByText("多视角显示公司质量较好，但估值输入仍需复核。")
    ).toBeInTheDocument();
    expect(await screen.findAllByText("010 需要复核自由现金流基准。")).not.toHaveLength(0);
    expect(await screen.findByText("分析师评分")).toBeInTheDocument();
    expect(await screen.findByText("+0.07")).toBeInTheDocument();
    expect(await screen.findByText("+0.10")).toBeInTheDocument();
    expect(await screen.findByText(/动态安全边际 15\.50%/)).toBeInTheDocument();
    const latestMemoPanel = screen.getByText("最新综合备忘录").closest(".memo-latest");
    expect(latestMemoPanel).not.toBeNull();
    expect(within(latestMemoPanel as HTMLElement).queryByText("研究结论")).not.toBeInTheDocument();
    expect(within(latestMemoPanel as HTMLElement).queryByText("来源视角")).not.toBeInTheDocument();
    expect(within(latestMemoPanel as HTMLElement).queryByText("状态")).not.toBeInTheDocument();
    fireEvent.click(screen.getByText("40 项指标明细"));
    expect(await screen.findByText(/护城河 \+1\.00/)).toBeInTheDocument();
    expect(screen.queryByText(/base_free_cash_flow:/)).not.toBeInTheDocument();
    expect(await screen.findByText("历史分析记录")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "查看备忘录 v1" }));
    expect(await screen.findByText("v1 综合投资备忘录")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "删除备忘录 v1" }));

    expect(await screen.findByText("已删除综合投资备忘录")).toBeInTheDocument();
    expect(await screen.findByText("暂无历史分析记录")).toBeInTheDocument();
    expect(mocks.generateInvestmentMemo).toHaveBeenCalledWith(1);
    expect(mocks.deleteInvestmentMemo).toHaveBeenCalledWith(101);
  });

  it("archives investment memo history without exposing edit or trade actions", async () => {
    mocks.getLatestInvestmentMemo
      .mockResolvedValueOnce({ company_id: 1, item: mocks.investmentMemo })
      .mockResolvedValue({ company_id: 1, item: null });
    mocks.getInvestmentMemos
      .mockResolvedValueOnce({ items: [mocks.investmentMemo], total: 1, limit: 20, offset: 0 })
      .mockResolvedValue({ items: [], total: 0, limit: 20, offset: 0 });

    render(<App />);

    fireEvent.click(screen.getByRole("button", { name: "公司搜索" }));
    expect(await screen.findByText("贵州茅台")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "档案" }));

    await openWorkspaceSection("Memo");
    expect(await screen.findByText("综合备忘录准备区")).toBeInTheDocument();
    expect(screen.queryByText(/当前内容不是买卖或仓位建议/)).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /编辑|保存新版本/ })).not.toBeInTheDocument();
    expect(screen.queryByText(/买入|卖出|持有|减仓/)).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "归档备忘录 v1" }));

    expect(await screen.findByText("已归档综合投资备忘录")).toBeInTheDocument();
    expect(await screen.findByText("暂无历史分析记录")).toBeInTheDocument();
    expect(mocks.archiveInvestmentMemo).toHaveBeenCalledWith(101);
  });

  it("does not show stale failed analyst labels when that profile has a successful latest run", async () => {
    mocks.getAnalystProfiles.mockResolvedValueOnce({
      items: [
        {
          id: "buffett",
          name: "Warren Buffett",
          display_name: "巴菲特",
          description: "从护城河、长期盈利质量、管理层可信度和安全边际看公司。",
          philosophy: "只在证据支持的范围内判断企业长期经济特征。",
          rules: [{ id: "moat", label: "护城河", description: "业务是否具备可持续竞争优势。" }],
          prompt_focus: ["长期业务质量"]
        },
        {
          id: "duan_yongping",
          name: "Duan Yongping",
          display_name: "段永平",
          description: "从生意质量、本分文化、消费者心智和股东回报看公司。",
          philosophy: "好生意和好文化需要长期证据验证。",
          rules: [{ id: "business_quality", label: "生意质量", description: "生意是否长期优秀。" }],
          prompt_focus: ["生意质量"]
        }
      ]
    });
    mocks.getLatestCompanyAnalysisRuns.mockImplementation(
      (_companyId: number, params: { status?: string } = {}) =>
        Promise.resolve(
          params.status === "failed"
            ? {
                company_id: 1,
                run_type: "analyst_view",
                analyst_profile: null,
                status: "failed",
                items: [
                  {
                    id: 21,
                    company_id: 1,
                    run_type: "analyst_view",
                    analyst_profile: "duan_yongping",
                    run_version: "008_v1",
                    model_name: "fake-model",
                    prompt_version: "analyst_view_v1",
                    data_snapshot_hash: "hash-old-failed",
                    result: { error_type: "ModelGatewayError", error: "之前生成失败" },
                    confidence: null,
                    parent_run_id: null,
                    is_latest: false,
                    user_note: null,
                    status: "failed",
                    created_at: "2026-08-09T00:40:00Z"
                  }
                ]
              }
            : {
                company_id: 1,
                run_type: "analyst_view",
                analyst_profile: null,
                status: "success",
                items: [
                  {
                    id: 11,
                    company_id: 1,
                    run_type: "analyst_view",
                    analyst_profile: "buffett",
                    run_version: "008_v1",
                    model_name: "fake-model",
                    prompt_version: "analyst_view_v1",
                    data_snapshot_hash: "hash-buffett",
                    result: {
                      analyst_profile: "buffett",
                      overview: "巴菲特视角已生成。",
                      risk_flags: [],
                      counter_evidence: [],
                      valuation_assumption_suggestions: [],
                      data_gaps: []
                    },
                    confidence: 0.7,
                    parent_run_id: null,
                    is_latest: true,
                    user_note: null,
                    status: "success",
                    created_at: "2026-08-09T01:00:00Z"
                  },
                  {
                    id: 22,
                    company_id: 1,
                    run_type: "analyst_view",
                    analyst_profile: "duan_yongping",
                    run_version: "008_v1",
                    model_name: "fake-model",
                    prompt_version: "analyst_view_v1",
                    data_snapshot_hash: "hash-duan-success",
                    result: {
                      analyst_profile: "duan_yongping",
                      overview: "段永平视角已重新生成。",
                      risk_flags: [],
                      counter_evidence: [],
                      valuation_assumption_suggestions: [],
                      data_gaps: []
                    },
                    confidence: 0.72,
                    parent_run_id: null,
                    is_latest: true,
                    user_note: null,
                    status: "success",
                    created_at: "2026-08-09T01:10:00Z"
                  }
                ]
              }
        )
    );

    render(<App />);

    fireEvent.click(screen.getByRole("button", { name: "公司搜索" }));
    expect(await screen.findByText("贵州茅台")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "档案" }));

    await openWorkspaceSection("Memo");

    expect(await screen.findByText("段永平")).toBeInTheDocument();
    expect(screen.queryByText("段永平 最近失败")).not.toBeInTheDocument();
  });

  it("shows a clear restart hint when investment memo generation returns not found", async () => {
    mocks.generateInvestmentMemo.mockRejectedValueOnce(new Error("Not Found"));

    render(<App />);

    fireEvent.click(screen.getByRole("button", { name: "公司搜索" }));
    expect(await screen.findByText("贵州茅台")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "档案" }));

    await openWorkspaceSection("Memo");
    fireEvent.click(screen.getByRole("button", { name: "生成备忘录" }));

    expect(
      await screen.findByText(
        "综合投资备忘录接口返回 not found；如果刚更新过 009，请重启后端服务后再试。"
      )
    ).toBeInTheDocument();
  });

  it("opens external evidence from the sidebar", async () => {
    render(<App />);

    fireEvent.click(screen.getByRole("button", { name: "公司搜索" }));
    expect(await screen.findByText("贵州茅台")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "档案" }));
    expect(await screen.findByRole("heading", { name: "公司档案", level: 1 })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "外部证据" }));

    expect(await screen.findByText("外部信息")).toBeInTheDocument();
    expect(await screen.findByText("测试行业证据已入库")).toBeInTheDocument();
  });

  it("refreshes company profile market data from the workspace", async () => {
    render(<App />);

    fireEvent.click(screen.getByRole("button", { name: "公司搜索" }));
    expect(await screen.findByText("贵州茅台")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "档案" }));
    expect(await screen.findByText("基础档案")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "更新" }));

    await waitFor(() => {
      expect(mocks.refreshCompanyProfile).toHaveBeenCalledWith(1);
    });
    expect(await screen.findByText("基本信息已更新")).toBeInTheDocument();
    expect(await screen.findByText("18,000亿 元")).toBeInTheDocument();
    expect(await screen.findByText("1,420.50")).toBeInTheDocument();
    expect(await screen.findByText("21.34x")).toBeInTheDocument();
    expect(await screen.findByText("16.12x")).toBeInTheDocument();
    expect(await screen.findByText("4.08%")).toBeInTheDocument();
    expect((await screen.findAllByText("2026年8月13日 22:30")).length).toBeGreaterThan(0);
  });

  it("returns to company search when the selected company is gone", async () => {
    mocks.getCompany.mockRejectedValueOnce(new Error("Company not found"));

    render(<App />);

    fireEvent.click(screen.getByRole("button", { name: "公司搜索" }));
    expect(await screen.findByText("贵州茅台")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "档案" }));

    await waitFor(() => {
      expect(mocks.getCompany).toHaveBeenCalledWith(1, expect.any(AbortSignal));
    });

    expect(await screen.findByRole("heading", { name: "公司搜索", level: 2 })).toBeInTheDocument();
    expect(await screen.findByRole("heading", { name: "新增公司" })).toBeInTheDocument();
    expect(screen.queryByText("公司档案加载失败")).not.toBeInTheDocument();
  });

  it("searches and refreshes company financial data", async () => {
    render(<App />);

    fireEvent.click(screen.getByRole("button", { name: "公司搜索" }));
    expect(await screen.findByText("贵州茅台")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "档案" }));
    await openWorkspaceSection("Financials");
    expect(await screen.findByText("财务数据")).toBeInTheDocument();

    mocks.getCompanyFinancials.mockResolvedValueOnce({
      items: [
        {
          id: 4,
          company_id: 1,
          period: "2025年报",
          statement_type: "balance_sheet",
          currency: "CNY",
          fields: {
            cash_and_equivalents: 152340000000,
            interest_bearing_debt: 12500000000
          },
          source: "eastmoney_f10_balance_sheet",
          source_url: "https://example.test/financials",
          created_at: "2026-08-09T00:00:00Z"
        },
        {
          id: 5,
          company_id: 1,
          period: "2025年报",
          statement_type: "cash_flow_statement",
          currency: "CNY",
          fields: {
            operating_cash_flow: 101400000000,
            capital_expenditure: 9130000000
          },
          source: "eastmoney_f10_cash_flow",
          source_url: "https://example.test/financials",
          created_at: "2026-08-09T00:00:00Z"
        },
        {
          id: 6,
          company_id: 1,
          period: "2025年报",
          statement_type: "income_statement",
          currency: "CNY",
          fields: {
            operating_cost: 15000000000,
            selling_expense: 6200000000,
            operating_profit: 108000000000,
            income_tax_expense: 26300000000
          },
          source: "eastmoney_f10_income_statement",
          source_url: "https://example.test/financials",
          created_at: "2026-08-09T00:00:00Z"
        },
        {
          id: 2,
          company_id: 1,
          period: "2025年报",
          statement_type: "main_financial_indicators",
          currency: "CNY",
          fields: {
            operating_cash_flow_to_revenue: 0.421,
            free_cash_flow: 92278000000,
            revenue: 172054171890.91,
            net_profit: 82320067101.68,
            roe: 0.3253
          },
          source: "eastmoney_f10_main_finance",
          source_url: "https://example.test/financials",
          created_at: "2026-08-09T00:00:00Z"
        },
        {
          id: 3,
          company_id: 1,
          period: "2016年报",
          statement_type: "main_financial_indicators",
          currency: "CNY",
          fields: {
            revenue: 40155000000,
            net_profit: 16718000000,
            roe: 0.246
          },
          source: "eastmoney_f10_main_finance",
          source_url: "https://example.test/financials",
          created_at: "2026-08-09T00:00:00Z"
        }
      ],
      total: 5,
      limit: 60,
      offset: 0
    });
    mocks.getCompanyFinancialEvidencePack.mockResolvedValueOnce(
      makeFinancialEvidencePack("2025年报", {
        revenue: 172054171890.91,
        net_profit: 82320067101.68
      })
    );

    fireEvent.click(screen.getByRole("button", { name: "搜索财务数据" }));

    await waitFor(() => {
      expect(mocks.syncCompanyFinancials).toHaveBeenCalledWith(1, { limit: 60 });
    });
    await waitFor(() => {
      expect(mocks.getCompanyFinancials).toHaveBeenLastCalledWith(1, {
        period_offset: 0
      });
    });

    expect(await screen.findByText("已搜索 2 条，新增 2 条，更新 0 条")).toBeInTheDocument();
    expect((await screen.findAllByText("2025年报")).length).toBeGreaterThan(0);
    expect((await screen.findAllByText("1,720.54亿 CNY")).length).toBeGreaterThan(0);
    expect(await screen.findByText("922.78亿 CNY")).toBeInTheDocument();
    expect((await screen.findAllByText("自由现金流")).length).toBeGreaterThan(0);
    expect(await screen.findByText("利润表")).toBeInTheDocument();
    expect(await screen.findByText("营业成本")).toBeInTheDocument();
    expect(await screen.findByText("150亿 CNY")).toBeInTheDocument();
    expect((await screen.findAllByText(/东方财富 F10 利润表/)).length).toBeGreaterThan(0);
    expect((await screen.findAllByText(/东方财富 F10 主要财务指标/)).length).toBeGreaterThan(0);
    expect(screen.queryByText("401.55亿 CNY")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /2016年报/, expanded: false }));
    expect(await screen.findByText("401.55亿 CNY")).toBeInTheDocument();
    expect(await screen.findAllByText("净资产收益率")).toHaveLength(2);
    fireEvent.click(screen.getByRole("button", { name: /2016年报/, expanded: true }));
    expect(screen.queryByText("401.55亿 CNY")).not.toBeInTheDocument();
    expect(await screen.findByText("#2")).toBeInTheDocument();
    expect(await screen.findByText("#4")).toBeInTheDocument();
    expect(await screen.findByText("#5")).toBeInTheDocument();
    expect(await screen.findByText("#6")).toBeInTheDocument();
    const mainFinancialIndicatorLabel = (await screen.findAllByText("主要财务指标"))[0];
    const incomeStatementLabel = await screen.findByText("利润表");
    const cashFlowStatementLabel = await screen.findByText("现金流量表");
    const balanceSheetLabel = await screen.findByText("资产负债表");
    expect(
      mainFinancialIndicatorLabel.compareDocumentPosition(incomeStatementLabel) &
        Node.DOCUMENT_POSITION_FOLLOWING
    ).toBeTruthy();
    expect(
      incomeStatementLabel.compareDocumentPosition(cashFlowStatementLabel) &
        Node.DOCUMENT_POSITION_FOLLOWING
    ).toBeTruthy();
    expect(
      cashFlowStatementLabel.compareDocumentPosition(balanceSheetLabel) &
        Node.DOCUMENT_POSITION_FOLLOWING
    ).toBeTruthy();
    expect(await screen.findAllByText("净资产收益率")).toHaveLength(1);
    expect(await screen.findByText("42.1%")).toBeInTheDocument();
  });

  it("deletes an unwanted financial statement from the company workspace", async () => {
    mocks.getCompanyFinancials.mockResolvedValueOnce(makeSyncedFinancialStatements());

    render(<App />);

    fireEvent.click(screen.getByRole("button", { name: "公司搜索" }));
    expect(await screen.findByText("贵州茅台")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "档案" }));
    await openWorkspaceSection("Financials");
    expect((await screen.findAllByText("2025年报")).length).toBeGreaterThan(0);
    expect(await screen.findByText("2016年报")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "删除财务数据：2025年报" }));

    await waitFor(() => {
      expect(mocks.deleteCompanyFinancialStatement).toHaveBeenCalledWith(1, 2);
    });
    expect(await screen.findByText("已删除财务数据")).toBeInTheDocument();
    expect(screen.queryByText("2025年报")).not.toBeInTheDocument();
    expect(screen.getAllByText("2016年报").length).toBeGreaterThan(0);
  });

  it("shows financial statement delete failures without removing the item", async () => {
    mocks.deleteCompanyFinancialStatement.mockRejectedValueOnce(
      new Error("Financial statement not found")
    );
    mocks.getCompanyFinancials.mockResolvedValueOnce(makeSyncedFinancialStatements());

    render(<App />);

    fireEvent.click(screen.getByRole("button", { name: "公司搜索" }));
    expect(await screen.findByText("贵州茅台")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "档案" }));
    await openWorkspaceSection("Financials");
    expect((await screen.findAllByText("2025年报")).length).toBeGreaterThan(0);

    fireEvent.click(screen.getByRole("button", { name: "删除财务数据：2025年报" }));

    await waitFor(() => {
      expect(mocks.deleteCompanyFinancialStatement).toHaveBeenCalledWith(1, 2);
    });
    expect(await screen.findByText("Financial statement not found")).toBeInTheDocument();
    expect(screen.getAllByText("2025年报").length).toBeGreaterThan(0);
  });

  it("searches announcements and refreshes the announcement list", async () => {
    render(<App />);

    fireEvent.click(screen.getByRole("button", { name: "公司搜索" }));
    expect(await screen.findByText("贵州茅台")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "档案" }));
    await openWorkspaceSection("Announcements");
    expect(await screen.findByText("公告区块")).toBeInTheDocument();

    mocks.getCompanyAnnouncements.mockResolvedValueOnce({
      items: [
        {
          id: 2,
          company_id: 1,
          title: "贵州茅台:重大事项公告",
          published_at: "2026-07-18T00:00:00Z",
          category: "其他",
          content: null,
          raw_content: null,
          summary: null,
          source: "eastmoney_announcements",
          source_url: "https://example.test/notices/detail/600519/AN1.html",
          raw_url: "https://example.test/pdf/AN1.pdf",
          created_at: "2026-08-09T00:00:00Z"
        }
      ],
      total: 1,
      limit: 50,
      offset: 0
    });

    fireEvent.click(screen.getByRole("button", { name: "搜索公告" }));

    await waitFor(() => {
      expect(mocks.syncCompanyAnnouncements).toHaveBeenCalledWith(1, { years: 1 });
    });

    expect(
      await screen.findByText("已搜索 1 条，新增 1 条，更新 0 条，跳过 0 条，清理 0 条")
    ).toBeInTheDocument();
    expect(await screen.findByText("贵州茅台:重大事项公告")).toBeInTheDocument();
    expect(await screen.findByText("ID #2")).toBeInTheDocument();
    expect(await screen.findByText("待后续智能摘要")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "查看来源" })).toHaveAttribute(
      "href",
      "https://example.test/notices/detail/600519/AN1.html"
    );
  });

  it("shows announcement search failures", async () => {
    mocks.syncCompanyAnnouncements.mockRejectedValueOnce(
      new Error("当前公告同步第一版仅支持 A 股证券代码")
    );

    render(<App />);

    fireEvent.click(screen.getByRole("button", { name: "公司搜索" }));
    expect(await screen.findByText("贵州茅台")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "档案" }));
    await openWorkspaceSection("Announcements");
    expect(await screen.findByText("公告区块")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "搜索公告" }));

    expect(await screen.findByText("当前公告同步第一版仅支持 A 股证券代码")).toBeInTheDocument();
  });

  it("summarizes all announcements and displays each model result in place", async () => {
    render(<App />);

    fireEvent.click(screen.getByRole("button", { name: "公司搜索" }));
    expect(await screen.findByText("贵州茅台")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "档案" }));
    await openWorkspaceSection("Announcements");
    expect(await screen.findByText("公告区块")).toBeInTheDocument();

    mocks.getCompanyAnnouncements.mockResolvedValueOnce({
      items: [
        {
          id: 1,
          company_id: 1,
          title: "年度经营摘要已导入",
          published_at: "2026-01-15T00:00:00Z",
          category: "annual_report",
          content: null,
          raw_content: "年度经营摘要原文。",
          summary: "模型摘要：年度经营保持稳定。",
          source: "test_fixture",
          source_url: null,
          raw_url: null,
          key_facts: ["年度经营保持稳定"],
          impact_direction: "neutral",
          sentiment: "neutral",
          positive_impacts: [],
          negative_impacts: [],
          neutral_impacts: ["需要结合财报继续复核"],
          risk_tips: ["关注经营现金流"],
          review_questions: ["复核公告原文数字"],
          tags: ["财报"],
          summary_status: "summarized",
          summary_model_name: "metadata_keyword",
          summary_prompt_version: "announcement_summary_keywords_v3",
          summarized_at: "2026-08-11T00:00:00Z",
          created_at: "2026-08-09T00:00:00Z"
        }
      ],
      total: 1,
      limit: 50,
      offset: 0
    });

    fireEvent.click(screen.getByRole("button", { name: "一键快速摘要" }));

    await waitFor(() => {
      expect(mocks.summarizeCompanyAnnouncements).toHaveBeenCalledWith(1, {
        limit: 50,
        only_missing: false,
        include_failed: true
      });
    });
    expect(await screen.findByText("已生成 1 条公告快速摘要")).toBeInTheDocument();
    expect(await screen.findByText("模型摘要：年度经营保持稳定。")).toBeInTheDocument();
    expect(await screen.findByText("年度经营保持稳定")).toBeInTheDocument();
    expect(await screen.findByText("已快速摘要")).toBeInTheDocument();
  });

  it("shows announcement batch summary failures", async () => {
    mocks.summarizeCompanyAnnouncements.mockRejectedValueOnce(
      new Error("模型未配置，请先在 .env 中设置：MODEL_API_KEY")
    );

    render(<App />);

    fireEvent.click(screen.getByRole("button", { name: "公司搜索" }));
    expect(await screen.findByText("贵州茅台")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "档案" }));
    await openWorkspaceSection("Announcements");
    expect(await screen.findByText("公告区块")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "一键快速摘要" }));

    expect(await screen.findByText("模型未配置，请先在 .env 中设置：MODEL_API_KEY")).toBeInTheDocument();
  });

  it("shows structured object errors for announcement batch summary failures", async () => {
    mocks.summarizeCompanyAnnouncements.mockRejectedValueOnce({
      detail: {
        message: "公告快速摘要失败：后端返回对象错误"
      }
    });

    render(<App />);

    fireEvent.click(screen.getByRole("button", { name: "公司搜索" }));
    expect(await screen.findByText("贵州茅台")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "档案" }));
    await openWorkspaceSection("Announcements");
    expect(await screen.findByText("公告区块")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "一键快速摘要" }));

    expect(await screen.findByText("公告快速摘要失败：后端返回对象错误")).toBeInTheDocument();
    expect(screen.queryByText("[object Object]")).not.toBeInTheDocument();
  });

  it("summarizes a single announcement deeply and displays the result in place", async () => {
    render(<App />);

    fireEvent.click(screen.getByRole("button", { name: "公司搜索" }));
    expect(await screen.findByText("贵州茅台")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "档案" }));
    await openWorkspaceSection("Announcements");
    expect((await screen.findAllByText("年度经营摘要已导入")).length).toBeGreaterThan(0);

    fireEvent.click(screen.getByRole("button", { name: "深度摘要：年度经营摘要已导入" }));

    await waitFor(() => {
      expect(mocks.summarizeCompanyAnnouncement).toHaveBeenCalledWith(1, 1);
    });
    expect(await screen.findByText("已生成单条深度摘要")).toBeInTheDocument();
    expect(await screen.findByText("深度摘要：年度经营保持稳定。")).toBeInTheDocument();
    expect(await screen.findByText("已深度摘要")).toBeInTheDocument();
  });

  it("summarizes all announcements deeply and skips already deep-summarized items", async () => {
    render(<App />);

    fireEvent.click(screen.getByRole("button", { name: "公司搜索" }));
    expect(await screen.findByText("贵州茅台")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "档案" }));
    await openWorkspaceSection("Announcements");
    expect(await screen.findByText("公告区块")).toBeInTheDocument();

    mocks.getCompanyAnnouncements.mockResolvedValueOnce({
      items: [
        {
          id: 1,
          company_id: 1,
          title: "年度经营摘要已导入",
          published_at: "2026-01-15T00:00:00Z",
          category: "annual_report",
          content: null,
          raw_content: "年度经营摘要原文。",
          summary: "深度摘要：年度经营保持稳定。",
          source: "test_fixture",
          source_url: null,
          raw_url: null,
          key_facts: ["年度经营保持稳定"],
          impact_direction: "neutral",
          sentiment: "neutral",
          positive_impacts: [],
          negative_impacts: [],
          neutral_impacts: ["需要结合财报继续复核"],
          risk_tips: ["关注经营现金流"],
          review_questions: ["复核公告原文数字"],
          tags: ["财报"],
          summary_status: "summarized",
          summary_model_name: "test-model",
          summary_prompt_version: "announcement_summary_keywords_v3",
          summarized_at: "2026-08-11T00:00:00Z",
          created_at: "2026-08-09T00:00:00Z"
        }
      ],
      total: 1,
      limit: 50,
      offset: 0
    });

    fireEvent.click(screen.getByRole("button", { name: "一键深度摘要" }));

    await waitFor(() => {
      expect(mocks.summarizeCompanyAnnouncementsDeep).toHaveBeenCalledWith(1, {
        limit: 50
      });
    });
    expect(await screen.findByText("已生成 1 条公告深度摘要")).toBeInTheDocument();
    expect(await screen.findByText("深度摘要：年度经营保持稳定。")).toBeInTheDocument();
    expect(await screen.findByText("已深度摘要")).toBeInTheDocument();
  });

  it("shows the one-click announcement summary entry in the panel header", async () => {
    render(<App />);

    fireEvent.click(screen.getByRole("button", { name: "公司搜索" }));
    expect(await screen.findByText("贵州茅台")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "档案" }));
    await openWorkspaceSection("Announcements");
    expect(await screen.findByText("公告区块")).toBeInTheDocument();

    expect(screen.getByRole("button", { name: "一键快速摘要" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "一键深度摘要" })).toBeInTheDocument();
  });

  it("hides generic announcement tags such as 待复核", async () => {
    render(<App />);

    fireEvent.click(screen.getByRole("button", { name: "公司搜索" }));
    expect(await screen.findByText("贵州茅台")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "档案" }));
    await openWorkspaceSection("Announcements");
    expect(await screen.findByText("公告区块")).toBeInTheDocument();

    expect(screen.queryByText("待复核")).not.toBeInTheDocument();
  });

  it("deletes an announcement from the company workspace", async () => {
    render(<App />);

    fireEvent.click(screen.getByRole("button", { name: "公司搜索" }));
    expect(await screen.findByText("贵州茅台")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "档案" }));
    await openWorkspaceSection("Announcements");
    expect((await screen.findAllByText("年度经营摘要已导入")).length).toBeGreaterThan(0);

    fireEvent.click(screen.getByRole("button", { name: "删除公告：年度经营摘要已导入" }));

    await waitFor(() => {
      expect(mocks.deleteCompanyAnnouncement).toHaveBeenCalledWith(1, 1);
    });
    expect(await screen.findByText("已删除公告")).toBeInTheDocument();
    expect(await screen.findByText("暂无公告")).toBeInTheDocument();
  });

  it("shows announcement delete failures without removing the item", async () => {
    mocks.deleteCompanyAnnouncement.mockRejectedValueOnce(new Error("Announcement not found"));

    render(<App />);

    fireEvent.click(screen.getByRole("button", { name: "公司搜索" }));
    expect(await screen.findByText("贵州茅台")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "档案" }));
    await openWorkspaceSection("Announcements");
    expect((await screen.findAllByText("年度经营摘要已导入")).length).toBeGreaterThan(0);

    fireEvent.click(screen.getByRole("button", { name: "删除公告：年度经营摘要已导入" }));

    await waitFor(() => {
      expect(mocks.deleteCompanyAnnouncement).toHaveBeenCalledWith(1, 1);
    });
    expect(await screen.findByText("Announcement not found")).toBeInTheDocument();
    expect(screen.getAllByText("年度经营摘要已导入").length).toBeGreaterThan(0);
  });

  it("searches external evidence and refreshes the evidence list", async () => {
    render(<App />);

    fireEvent.click(screen.getByRole("button", { name: "公司搜索" }));
    expect(await screen.findByText("贵州茅台")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "档案" }));
    await openWorkspaceSection("Evidence");
    expect(await screen.findByText("外部信息")).toBeInTheDocument();

    mocks.getCompanyEvidence.mockResolvedValueOnce({
      items: [
        {
          id: 2,
          company_id: 1,
          source_type: "policy",
          title: "白酒行业监管政策变化",
          source: "example.test",
          source_url: "https://example.test/policy",
          published_at: "2026-08-01T00:00:00Z",
          summary: "政策信息可能影响高端白酒渠道监管，需要后续复核原文。",
          key_facts: ["监管政策提到渠道合规要求"],
          impact_direction: "mixed",
          importance_score: 0.82,
          credibility_score: 0.76,
          tags: ["政策", "白酒"],
          requires_review: true,
        price_sensitive: false,
        use_scope: ["fundamental_analysis", "analyst_view", "intrinsic_valuation"],
        analysis_status: "model_analyzed",
          analysis_note: "来源为政策页面，重要性较高。",
          raw_snapshot: {
            query: "贵州茅台 白酒政策",
            title: "白酒行业监管政策变化"
          },
          created_at: "2026-08-09T00:00:00Z"
        }
      ],
      total: 1,
      limit: 10,
      offset: 0
    });

    fireEvent.click(screen.getByRole("button", { name: "搜索外部信息" }));

    await waitFor(() => {
      expect(mocks.searchCompanyEvidence).toHaveBeenCalledWith(1, {
        keywords: ["贵州茅台", "白酒"]
      });
    });

    expect(
      await screen.findByText("已生成 1 条证据，运行记录 #8；候选 12，过滤 4，送模 8")
    ).toBeInTheDocument();
    expect(await screen.findByText("白酒行业监管政策变化")).toBeInTheDocument();
    expect(await screen.findByText("可信度 76%")).toBeInTheDocument();
    expect(screen.queryByText(/用途：/)).not.toBeInTheDocument();
    expect(screen.queryByText(/需要复核/)).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "example.test" })).toHaveAttribute(
      "href",
      "https://example.test/policy"
    );
  });

  it("imports manual text evidence and refreshes the evidence list", async () => {
    render(<App />);

    fireEvent.click(screen.getByRole("button", { name: "公司搜索" }));
    expect(await screen.findByText("贵州茅台")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "档案" }));
    await openWorkspaceSection("Evidence");
    const evidencePanel = await screen.findByRole("region", { name: "外部信息" });

    mocks.getCompanyEvidence.mockResolvedValueOnce({
      items: [
        {
          id: 7,
          company_id: 1,
          source_type: "web",
          title: "手动导入渠道调研纪要",
          source: "用户粘贴资料",
          source_url: "https://example.test/manual-source",
          published_at: "2026-08-10T00:00:00Z",
          summary: "手动导入文本提到渠道库存和经销商回款节奏需要继续复核。",
          key_facts: ["渠道库存去化节奏仍需复核"],
          impact_direction: "mixed",
          importance_score: 0.68,
          credibility_score: 0.6,
          tags: ["手动导入", "渠道"],
          requires_review: true,
          price_sensitive: false,
          use_scope: ["fundamental_analysis", "analyst_view", "intrinsic_valuation"],
          analysis_status: "model_analyzed",
          analysis_note: "由用户手动导入文本生成，需复核来源。",
          raw_snapshot: {
            import_mode: "manual_text_import"
          },
          created_at: "2026-08-10T00:00:00Z"
        }
      ],
      total: 1,
      limit: 10,
      offset: 0
    });

    fireEvent.change(within(evidencePanel).getByLabelText("标题"), {
      target: { value: "手动导入渠道调研纪要" }
    });
    fireEvent.change(within(evidencePanel).getByLabelText("来源名称"), {
      target: { value: "用户粘贴资料" }
    });
    fireEvent.change(within(evidencePanel).getByLabelText("来源链接"), {
      target: { value: "https://example.test/manual-source" }
    });
    fireEvent.change(within(evidencePanel).getByLabelText("正文内容"), {
      target: {
        value:
          "渠道调研文本显示，经销商回款节奏和库存去化仍需结合后续公告与经营数据继续复核。"
      }
    });

    fireEvent.click(within(evidencePanel).getByRole("button", { name: "导入文本" }));

    await waitFor(() => {
      expect(mocks.importTextEvidence).toHaveBeenCalledWith(1, {
        title: "手动导入渠道调研纪要",
        content: "渠道调研文本显示，经销商回款节奏和库存去化仍需结合后续公告与经营数据继续复核。",
        source: "用户粘贴资料",
        source_url: "https://example.test/manual-source",
        published_at: undefined,
        source_type: "web",
        notes: undefined
      });
    });

    expect(await screen.findByText("已导入 1 条外部证据：#7，运行记录 #10")).toBeInTheDocument();
    expect(await screen.findByText("手动导入渠道调研纪要")).toBeInTheDocument();
    expect(screen.getByText("#7")).toBeInTheDocument();
  });

  it("shows manual text import failures", async () => {
    mocks.importTextEvidence.mockRejectedValueOnce(
      new Error("模型未从手动导入文本中生成可入库外部证据")
    );

    render(<App />);

    fireEvent.click(screen.getByRole("button", { name: "公司搜索" }));
    expect(await screen.findByText("贵州茅台")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "档案" }));
    await openWorkspaceSection("Evidence");
    const evidencePanel = await screen.findByRole("region", { name: "外部信息" });

    fireEvent.change(within(evidencePanel).getByLabelText("正文内容"), {
      target: {
        value: "这段导入文本只有短线交易观点和目标价，不应该污染默认基本面外部证据库。"
      }
    });
    fireEvent.click(within(evidencePanel).getByRole("button", { name: "导入文本" }));

    await waitFor(() => {
      expect(mocks.importTextEvidence).toHaveBeenCalledTimes(1);
    });
    expect(
      await screen.findByText("模型未从手动导入文本中生成可入库外部证据")
    ).toBeInTheDocument();
  });

  it("deletes an irrelevant external evidence item and refreshes the list", async () => {
    render(<App />);

    fireEvent.click(screen.getByRole("button", { name: "公司搜索" }));
    expect(await screen.findByText("贵州茅台")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "档案" }));
    await openWorkspaceSection("Evidence");
    expect(await screen.findByText("测试行业证据已入库")).toBeInTheDocument();

    mocks.getCompanyEvidence.mockResolvedValueOnce({
      items: [],
      total: 0,
      limit: 10,
      offset: 0
    });

    fireEvent.click(screen.getByRole("button", { name: "删除外部信息：测试行业证据已入库" }));

    await waitFor(() => {
      expect(mocks.deleteEvidence).toHaveBeenCalledWith(1);
    });
    expect(await screen.findByText("已删除外部信息")).toBeInTheDocument();
    expect(await screen.findByText("暂无外部信息证据")).toBeInTheDocument();
  });

  it("shows external evidence delete failures without removing the item", async () => {
    mocks.deleteEvidence.mockRejectedValueOnce(new Error("Evidence not found"));

    render(<App />);

    fireEvent.click(screen.getByRole("button", { name: "公司搜索" }));
    expect(await screen.findByText("贵州茅台")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "档案" }));
    await openWorkspaceSection("Evidence");
    expect(await screen.findByText("测试行业证据已入库")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "删除外部信息：测试行业证据已入库" }));

    await waitFor(() => {
      expect(mocks.deleteEvidence).toHaveBeenCalledWith(1);
    });
    expect(await screen.findByText("Evidence not found")).toBeInTheDocument();
    expect(screen.getByText("测试行业证据已入库")).toBeInTheDocument();
  });

  it("shows fallback search leads without model scores", async () => {
    mocks.searchCompanyEvidence.mockResolvedValueOnce({
      company_id: 1,
      run_id: 9,
      status: "partial",
      created: 1,
      items: [
        {
          id: 3,
          company_id: 1,
          source_type: "web",
          title: "贵州茅台 上交所公告检索入口",
          source: "www.sse.com.cn",
          source_url: "https://www.sse.com.cn/disclosure/listedinfo/announcement/",
          published_at: null,
          summary: "上交所公告检索入口，可用于复核公司公告和公开披露文件。该条由搜索结果兜底入库，需要人工打开来源复核。",
          key_facts: ["搜索结果线索已入库，尚未完成模型摘要和事实抽取。"],
          impact_direction: "unknown",
          importance_score: 0.3,
          credibility_score: 0.4,
          tags: ["待复核", "搜索线索"],
          requires_review: true,
        price_sensitive: false,
        use_scope: ["fundamental_analysis", "analyst_view", "intrinsic_valuation"],
        analysis_status: "search_lead",
          analysis_note: "模型结构化失败或超时，本条仅为搜索线索。",
          raw_snapshot: {},
          created_at: "2026-08-09T00:00:00Z"
        }
      ]
    });
    mocks.getCompanyEvidence.mockResolvedValueOnce({
      items: [
        {
          id: 1,
          company_id: 1,
          source_type: "industry_news",
          title: "测试行业证据已入库",
          source: "test_fixture",
          source_url: "https://example.test/evidence",
          published_at: "2026-02-01T00:00:00Z",
          summary: "示例外部信息用于验证 Evidence 列表、模型搜索入口和复核状态展示。",
          key_facts: ["行业需求变化需要结合公告和财务数据继续复核"],
          impact_direction: "mixed",
          importance_score: 0.62,
          credibility_score: 0.55,
          tags: ["示例", "行业"],
          requires_review: true,
        price_sensitive: false,
        use_scope: ["fundamental_analysis", "analyst_view", "intrinsic_valuation"],
        analysis_status: "model_analyzed",
          analysis_note: "模型按测试 fixture 完成结构化。",
          raw_snapshot: {
            query: "贵州茅台 行业需求",
            title: "测试行业证据已入库"
          },
          created_at: "2026-08-09T00:00:00Z"
        }
      ],
      total: 1,
      limit: 10,
      offset: 0
    });
    mocks.getCompanyEvidence.mockResolvedValueOnce({
      items: [
        {
          id: 3,
          company_id: 1,
          source_type: "web",
          title: "贵州茅台 上交所公告检索入口",
          source: "www.sse.com.cn",
          source_url: "https://www.sse.com.cn/disclosure/listedinfo/announcement/",
          published_at: null,
          summary: "上交所公告检索入口，可用于复核公司公告和公开披露文件。该条由搜索结果兜底入库，需要人工打开来源复核。",
          key_facts: ["搜索结果线索已入库，尚未完成模型摘要和事实抽取。"],
          impact_direction: "unknown",
          importance_score: 0.3,
          credibility_score: 0.4,
          tags: ["待复核", "搜索线索"],
          requires_review: true,
        price_sensitive: false,
        use_scope: ["fundamental_analysis", "analyst_view", "intrinsic_valuation"],
        analysis_status: "search_lead",
          analysis_note: "模型结构化失败或超时，本条仅为搜索线索。",
          raw_snapshot: {},
          created_at: "2026-08-09T00:00:00Z"
        }
      ],
      total: 1,
      limit: 10,
      offset: 0
    });

    render(<App />);

    fireEvent.click(screen.getByRole("button", { name: "公司搜索" }));
    expect(await screen.findByText("贵州茅台")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "档案" }));
    await openWorkspaceSection("Evidence");
    expect(await screen.findByText("外部信息")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "搜索外部信息" }));

    expect(await screen.findByText("已保存 1 条搜索线索，模型分析未完成，运行记录 #9")).toBeInTheDocument();
    expect(await screen.findByText("搜索线索")).toBeInTheDocument();
    expect(await screen.findByText("影响、重要性、可信度未完成模型分析")).toBeInTheDocument();
    expect(screen.queryByText("重要性 30%")).not.toBeInTheDocument();
    expect(screen.queryByText("可信度 40%")).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "www.sse.com.cn" })).toHaveAttribute(
      "href",
      "https://www.sse.com.cn/disclosure/listedinfo/announcement/"
    );
  });

  it("shows external evidence search failures", async () => {
    mocks.searchCompanyEvidence.mockRejectedValueOnce(
      new Error("模型未配置，请先在 .env 中设置：MODEL_API_KEY")
    );

    render(<App />);

    fireEvent.click(screen.getByRole("button", { name: "公司搜索" }));
    expect(await screen.findByText("贵州茅台")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "档案" }));
    await openWorkspaceSection("Evidence");
    expect(await screen.findByText("外部信息")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "搜索外部信息" }));

    expect(
      await screen.findByText("模型未配置，请先在 .env 中设置：MODEL_API_KEY")
    ).toBeInTheDocument();
  });

  it("runs model smoke test without creating evidence or analyst runs", async () => {
    render(<App />);

    fireEvent.click(screen.getByRole("button", { name: "公司搜索" }));
    expect(await screen.findByText("贵州茅台")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "档案" }));
    await openWorkspaceSection("Evidence");
    expect(await screen.findByText("外部信息")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "模型自检" }));

    await waitFor(() => {
      expect(mocks.runEvidenceModelSmokeTest).toHaveBeenCalledTimes(1);
    });
    expect(await screen.findByText("model gateway ok")).toBeInTheDocument();
    expect(mocks.searchCompanyEvidence).not.toHaveBeenCalled();
    expect(mocks.runCompanyAnalysis).not.toHaveBeenCalled();
    expect(mocks.runCompanyAnalysisBatch).not.toHaveBeenCalled();
  });

  it("generates an analyst view and refreshes analysis runs", async () => {
    render(<App />);

    fireEvent.click(screen.getByRole("button", { name: "公司搜索" }));
    expect(await screen.findByText("贵州茅台")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "档案" }));
    await openWorkspaceSection("Analyst Views");
    expect(
      await screen.findByRole("heading", { name: "分析师视角", level: 3 })
    ).toBeInTheDocument();

    mocks.getLatestCompanyAnalysisRuns.mockResolvedValueOnce({
      company_id: 1,
      run_type: "analyst_view",
      analyst_profile: null,
      status: "success",
      items: [
        {
          id: 12,
          company_id: 1,
          run_type: "analyst_view",
          analyst_profile: "buffett",
          run_version: "008_v1",
          model_name: "fake-model",
          prompt_version: "analyst_view_v1",
          data_snapshot_hash: "hash-next",
          result: {
            analyst_profile: "buffett",
            overview: "最新视角已生成。",
            profile_fit_score: 0.72,
            confidence: 0.76,
            key_observations: [],
            rule_checks: [
              {
                rule_id: "quality",
                status: "pass",
                summary: "利润和现金流匹配度较好。",
                evidence_ids: [],
                financial_periods: ["2025A"],
                announcement_ids: []
              }
            ],
            supporting_evidence_ids: [],
            financial_observations: [],
            announcement_observations: [],
            risk_flags: [],
            counter_evidence: [],
            valuation_assumption_suggestions: [],
            data_gaps: [],
            follow_up_questions: []
          },
          confidence: 0.76,
          parent_run_id: 11,
          is_latest: true,
          user_note: null,
          status: "success",
          created_at: "2026-08-09T00:30:00Z"
        }
      ]
    });

    fireEvent.click(screen.getByRole("button", { name: "生成巴菲特视角" }));

    await waitFor(() => {
      expect(mocks.runCompanyAnalysis).toHaveBeenCalledWith(
        1,
        expect.objectContaining({
          analyst_profile: "buffett",
          signal: expect.any(AbortSignal)
        })
      );
    });

    expect(await screen.findByText("已生成分析师视角，运行记录 #12")).toBeInTheDocument();
    expect(await screen.findByText("最新视角已生成。")).toBeInTheDocument();
    expect(await screen.findByText("利润和现金流匹配度较好。")).toBeInTheDocument();
  });

  it("generates all analyst views and refreshes latest runs", async () => {
    render(<App />);

    fireEvent.click(screen.getByRole("button", { name: "公司搜索" }));
    expect(await screen.findByText("贵州茅台")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "档案" }));
    await openWorkspaceSection("Analyst Views");
    expect(
      await screen.findByRole("heading", { name: "分析师视角", level: 3 })
    ).toBeInTheDocument();

    mocks.getLatestCompanyAnalysisRuns.mockResolvedValueOnce({
      company_id: 1,
      run_type: "analyst_view",
      analyst_profile: null,
      status: "success",
      items: [
        {
          id: 12,
          company_id: 1,
          run_type: "analyst_view",
          analyst_profile: "buffett",
          run_version: "008_v1",
          model_name: "fake-model",
          prompt_version: "analyst_view_v1",
          data_snapshot_hash: "hash-next",
          result: {
            analyst_profile: "buffett",
            overview: "最新视角已生成。",
            profile_fit_score: 0.72,
            confidence: 0.76,
            key_observations: [],
            rule_checks: [],
            supporting_evidence_ids: [],
            financial_observations: [],
            announcement_observations: [],
            risk_flags: [],
            counter_evidence: [],
            valuation_assumption_suggestions: [],
            data_gaps: [],
            follow_up_questions: []
          },
          confidence: 0.76,
          parent_run_id: 11,
          is_latest: true,
          user_note: null,
          status: "success",
          created_at: "2026-08-09T00:30:00Z"
        },
        {
          id: 13,
          company_id: 1,
          run_type: "analyst_view",
          analyst_profile: "peter_lynch",
          run_version: "008_v1",
          model_name: "fake-model",
          prompt_version: "analyst_view_v1",
          data_snapshot_hash: "hash-next",
          result: {
            analyst_profile: "peter_lynch",
            overview: "彼得林奇视角已生成。",
            profile_fit_score: 0.64,
            confidence: 0.71,
            key_observations: [],
            rule_checks: [],
            supporting_evidence_ids: [],
            financial_observations: [],
            announcement_observations: [],
            risk_flags: [],
            counter_evidence: [],
            valuation_assumption_suggestions: [],
            data_gaps: [],
            follow_up_questions: []
          },
          confidence: 0.71,
          parent_run_id: null,
          is_latest: true,
          user_note: null,
          status: "success",
          created_at: "2026-08-09T00:31:00Z"
        }
      ]
    });

    fireEvent.click(screen.getByRole("button", { name: "生成全部" }));

    await waitFor(() => {
      expect(mocks.runCompanyAnalysisBatch).toHaveBeenCalledWith(
        1,
        expect.objectContaining({
          analyst_profiles: ["buffett", "peter_lynch"],
          signal: expect.any(AbortSignal)
        })
      );
    });

    expect(await screen.findByText("已生成 2 个视角，失败 0 个")).toBeInTheDocument();
    expect(await screen.findByText("彼得林奇视角已生成。")).toBeInTheDocument();
  });

  it("shows the latest failed analyst run reason", async () => {
    mocks.getLatestCompanyAnalysisRuns.mockImplementation(
      (_companyId: number, params: { status?: string } = {}) =>
        Promise.resolve(
          params.status === "failed"
            ? {
                company_id: 1,
                run_type: "analyst_view",
                analyst_profile: null,
                status: "failed",
                items: [
                  {
                    id: 21,
                    company_id: 1,
                    run_type: "analyst_view",
                    analyst_profile: "peter_lynch",
                    run_version: "008_v1",
                    model_name: "fake-model",
                    prompt_version: "analyst_view_v1",
                    data_snapshot_hash: "hash-failed",
                    result: {
                      error_type: "ModelGatewayError",
                      error: "模型接口返回错误：HTTP 502；pumpkinai.vip | 502: Bad gateway"
                    },
                    confidence: null,
                    parent_run_id: null,
                    is_latest: false,
                    user_note: null,
                    status: "failed",
                    created_at: "2026-08-09 00:40:00.000000"
                  }
                ]
              }
            : {
                company_id: 1,
                run_type: "analyst_view",
                analyst_profile: null,
                status: "success",
                items: []
              }
        )
    );

    render(<App />);

    fireEvent.click(screen.getByRole("button", { name: "公司搜索" }));
    expect(await screen.findByText("贵州茅台")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "档案" }));
    await openWorkspaceSection("Analyst Views");

    expect(await screen.findByText("1 个最近失败")).toBeInTheDocument();
    expect(await screen.findByText("最近生成失败")).toBeInTheDocument();
    expect(await screen.findByText("2026年8月9日 08:40")).toBeInTheDocument();
    expect(await screen.findByText(/HTTP 502/)).toBeInTheDocument();
  });

  it("shows the first failed analyst in the batch result message", async () => {
    mocks.runCompanyAnalysisBatch.mockResolvedValueOnce({
      company_id: 1,
      requested: 2,
      succeeded: 1,
      failed: 1,
      items: [
        {
          analyst_profile: "buffett",
          status: "success",
          error: null,
          error_type: null,
          run: null
        },
        {
          analyst_profile: "peter_lynch",
          status: "failed",
          error: "模型接口返回错误：HTTP 504；pumpkinai.vip | 504: Gateway time-out",
          error_type: "ModelGatewayError",
          run: null
        }
      ]
    });

    render(<App />);

    fireEvent.click(screen.getByRole("button", { name: "公司搜索" }));
    expect(await screen.findByText("贵州茅台")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "档案" }));
    await openWorkspaceSection("Analyst Views");
    expect(
      await screen.findByRole("heading", { name: "分析师视角", level: 3 })
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "生成全部" }));

    expect(
      await screen.findByText(/已生成 1 个视角，失败 1 个；彼得林奇：ModelGatewayError/)
    ).toBeInTheDocument();
    expect(await screen.findByText(/HTTP 504/)).toBeInTheDocument();
  });

  it("deletes an analyst run only after an explicit user action", async () => {
    render(<App />);

    fireEvent.click(screen.getByRole("button", { name: "公司搜索" }));
    expect(await screen.findByText("贵州茅台")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "档案" }));
    await openWorkspaceSection("Analyst Views");
    expect(await screen.findByText("现金流质量较好，但证据仍需补充。")).toBeInTheDocument();

    mocks.getLatestCompanyAnalysisRuns.mockResolvedValueOnce({
      company_id: 1,
      run_type: "analyst_view",
      analyst_profile: null,
      status: "success",
      items: []
    });
    mocks.getLatestCompanyAnalysisRuns.mockResolvedValueOnce({
      company_id: 1,
      run_type: "analyst_view",
      analyst_profile: null,
      status: "failed",
      items: []
    });

    fireEvent.click(screen.getByRole("button", { name: "删除巴菲特分析记录 #11" }));

    await waitFor(() => {
      expect(mocks.deleteCompanyAnalysisRun).toHaveBeenCalledWith(1, 11);
    });
    expect(await screen.findByText("已删除分析记录")).toBeInTheDocument();
  });

  it("allows directly correcting an analyst rule status", async () => {
    render(<App />);

    fireEvent.click(screen.getByRole("button", { name: "公司搜索" }));
    expect(await screen.findByText("贵州茅台")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "档案" }));
    await openWorkspaceSection("Analyst Views");

    const statusSelect = await screen.findByLabelText("调整巴菲特护城河结论");
    expect(statusSelect).toHaveValue("warn");

    fireEvent.change(statusSelect, { target: { value: "pass" } });

    await waitFor(() => {
      expect(mocks.updateAnalysisRunRuleStatus).toHaveBeenCalledWith(1, 11, "moat", "pass");
    });
    expect(await screen.findByText("已保存规则结论")).toBeInTheDocument();
    expect(statusSelect).toHaveValue("pass");
  });

  it("can stop an analyst generation request", async () => {
    mocks.runCompanyAnalysis.mockImplementation(
      (_companyId: number, params: { signal?: AbortSignal }) =>
        new Promise((_resolve, reject) => {
          params.signal?.addEventListener("abort", () => {
            reject(new DOMException("Aborted", "AbortError"));
          });
        })
    );

    render(<App />);

    fireEvent.click(screen.getByRole("button", { name: "公司搜索" }));
    expect(await screen.findByText("贵州茅台")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "档案" }));
    await openWorkspaceSection("Analyst Views");
    expect(
      await screen.findByRole("heading", { name: "分析师视角", level: 3 })
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "生成巴菲特视角" }));
    expect(await screen.findByText("正在生成分析师视角")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "停止" }));

    expect(await screen.findByText("已停止本次生成请求")).toBeInTheDocument();
  });

  it("pages through the company search results", async () => {
    const firstPageCompanies = Array.from({ length: 20 }, (_, index) => ({
      ...mocks.company,
      id: index + 1,
      ticker: `6005${String(index).padStart(2, "0")}.SH`,
      name: index === 0 ? "贵州茅台" : `第一页公司 ${index + 1}`
    }));
    const nextPageCompany = {
      ...mocks.company,
      id: 21,
      ticker: "000858.SZ",
      exchange: "SZSE",
      name: "五粮液",
      industry: "白酒",
      description: "第二页公司样本。",
      tags: ["A股", "白酒"]
    };
    mocks.getCompanies.mockImplementation(
      (params: { q?: string; limit?: number; offset?: number; signal?: AbortSignal } = {}) =>
        Promise.resolve(
          params.offset === 20
            ? {
                items: [nextPageCompany],
                total: 21,
                limit: 20,
                offset: 20
              }
            : {
                items: firstPageCompanies,
                total: 21,
                limit: 20,
                offset: 0
              }
        )
    );

    render(<App />);

    fireEvent.click(screen.getByRole("button", { name: "公司搜索" }));

    expect(await screen.findByText("公司池共 21 家，第 1-20 家")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "上一页" })).toBeDisabled();

    const searchInput = screen.getByPlaceholderText("输入代码、名称、交易所、行业或标签");
    fireEvent.change(searchInput, { target: { value: "白酒" } });
    expect(await screen.findByText("匹配 21 家公司，第 1-20 家")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "下一页" }));

    expect(await screen.findByText("五粮液")).toBeInTheDocument();
    await waitFor(() => {
      expect(mocks.getCompanies).toHaveBeenLastCalledWith(
        expect.objectContaining({
          offset: 20,
          signal: expect.any(AbortSignal)
        })
      );
    });
    expect(screen.getByText("21-21 / 21")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "下一页" })).toBeDisabled();

    const scrollTo = vi.fn();
    Object.defineProperty(window, "scrollY", { configurable: true, value: 640 });
    Object.defineProperty(window, "scrollTo", { configurable: true, value: scrollTo });

    fireEvent.click(screen.getByRole("button", { name: "档案" }));
    expect(await screen.findByRole("heading", { name: "公司档案", level: 1 })).toBeInTheDocument();

    fireEvent.click(await screen.findByRole("button", { name: "返回搜索" }));

    expect(await screen.findByText("五粮液")).toBeInTheDocument();
    expect(screen.getByPlaceholderText("输入代码、名称、交易所、行业或标签")).toHaveValue("白酒");
    await waitFor(() => {
      expect(mocks.getCompanies).toHaveBeenLastCalledWith(
        expect.objectContaining({
          q: "白酒",
          offset: 20,
          signal: expect.any(AbortSignal)
        })
      );
      expect(scrollTo).toHaveBeenCalledWith(0, 640);
    });

    fireEvent.click(screen.getByRole("button", { name: "上一页" }));

    expect(await screen.findByText("贵州茅台")).toBeInTheDocument();
    await waitFor(() => {
      expect(mocks.getCompanies).toHaveBeenLastCalledWith(
        expect.objectContaining({
          offset: 0,
          signal: expect.any(AbortSignal)
        })
      );
    });
  });
 
  it("creates a company from the fixed new company panel", async () => {
    render(<App />);

    fireEvent.click(screen.getByRole("button", { name: "公司搜索" }));

    expect(await screen.findByRole("heading", { name: "新增公司" })).toBeInTheDocument();
    const newCompanyPanel = screen.getByRole("region", { name: "新增公司" });

    fireEvent.change(within(newCompanyPanel).getByLabelText(/证券代码/), {
      target: { value: "sony.us" }
    });
    fireEvent.change(within(newCompanyPanel).getByLabelText(/交易所/), { target: { value: "nyse" } });
    fireEvent.change(within(newCompanyPanel).getByLabelText(/公司名称/), {
      target: { value: "Sony Group Corporation 索尼集团" }
    });
    fireEvent.change(within(newCompanyPanel).getByLabelText(/所属行业/), { target: { value: "消费电子" } });
    fireEvent.change(within(newCompanyPanel).getByLabelText(/上市日期/), {
      target: { value: "1970-09-17" }
    });
    fireEvent.change(within(newCompanyPanel).getByLabelText(/研究状态/), { target: { value: "观察中" } });
    fireEvent.change(within(newCompanyPanel).getByLabelText(/^标签$/), {
      target: { value: "美股, 消费电子" }
    });
    fireEvent.change(within(newCompanyPanel).getByLabelText(/公司简介/), {
      target: { value: "手动新增的研究对象。" }
    });

    fireEvent.click(within(newCompanyPanel).getByRole("button", { name: "保存并进入档案" }));

    await waitFor(() => {
      expect(mocks.createCompany).toHaveBeenCalledWith({
        ticker: "sony.us",
        exchange: "nyse",
        name: "Sony Group Corporation 索尼集团",
        industry: "消费电子",
        description: "手动新增的研究对象。",
        listed_date: "1970-09-17",
        status: "观察中",
        tags: ["美股", "消费电子"]
      });
    });

    expect(await screen.findByText("Sony Group Corporation 索尼集团")).toBeInTheDocument();
  });

  it("opens Data Management independently while Dashboard remains 8 of 8", async () => {
    render(<App />);

    expect(await screen.findByText("8 / 8")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "数据管理" }));

    expect(await screen.findByRole("heading", { name: "数据管理", level: 1 })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "数据库概览" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "备份与恢复" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "数据库维护" })).toBeInTheDocument();
    expect(mocks.getDataManagementSummary).toHaveBeenCalled();
  });

  it("previews and confirms company cleanup with the backend phrase", async () => {
    render(<App />);
    fireEvent.click(screen.getByRole("button", { name: "数据管理" }));
    await screen.findByRole("heading", { name: "数据库概览" });

    fireEvent.change(screen.getByLabelText("目标公司"), { target: { value: "1" } });
    fireEvent.click(screen.getByRole("button", { name: "预览影响" }));

    expect(await screen.findByRole("dialog", { name: "确认数据库操作" })).toBeInTheDocument();
    expect(mocks.previewDataOperation).toHaveBeenCalledWith(
      "reset_company_research_data",
      { company_id: 1 }
    );
    const confirmButton = screen.getByRole("button", { name: "确认执行" });
    expect(confirmButton).toBeDisabled();
    fireEvent.change(screen.getByLabelText(/输入确认短语/), {
      target: { value: "清空公司研究数据" }
    });
    fireEvent.click(confirmButton);

    await waitFor(() => {
      expect(mocks.executeDataOperation).toHaveBeenCalledWith(
        "token-reset_company_research_data-01234567890123456789",
        "清空公司研究数据"
      );
    });
    expect(await screen.findByText("数据管理操作已完成。")).toBeInTheDocument();
  });

  it("validates N, shows prune protection, and supports backup controls", async () => {
    render(<App />);
    fireEvent.click(screen.getByRole("button", { name: "数据管理" }));
    await screen.findByRole("heading", { name: "版本保留" });

    const keepInput = screen.getByLabelText("每组保留版本");
    fireEvent.change(keepInput, { target: { value: "0" } });
    expect(screen.getByRole("button", { name: "生成 prune plan" })).toBeDisabled();
    fireEvent.change(keepInput, { target: { value: "2" } });
    fireEvent.click(screen.getByRole("button", { name: "生成 prune plan" }));
    expect(await screen.findByText(/被保留的 Memo JSON 来源引用/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "取消" }));

    fireEvent.click(screen.getByRole("button", { name: "创建备份" }));
    await waitFor(() => expect(mocks.createBackup).toHaveBeenCalledWith("manual"));
    fireEvent.click(screen.getByTitle("校验备份"));
    await waitFor(() => expect(mocks.verifyBackup).toHaveBeenCalled());
    fireEvent.click(screen.getByTitle("恢复备份"));
    await waitFor(() => expect(mocks.previewBackupRestore).toHaveBeenCalled());
  });

  it("keeps backend data-management errors visible", async () => {
    mocks.getDataManagementSummary.mockRejectedValueOnce(
      new Error("数据库正在维护，新的写请求已暂停。")
    );
    render(<App />);
    fireEvent.click(screen.getByRole("button", { name: "数据管理" }));

    expect(
      await screen.findByText("数据库正在维护，新的写请求已暂停。")
    ).toBeInTheDocument();
  });
});

