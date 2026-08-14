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

  return {
    company,
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
    deleteEvidence: vi.fn(),
    getAnalystProfiles: vi.fn(),
    getCompanyAnalysisRuns: vi.fn(),
    getLatestCompanyAnalysisRuns: vi.fn(),
    runCompanyAnalysis: vi.fn(),
    runCompanyAnalysisBatch: vi.fn(),
    deleteCompanyAnalysisRun: vi.fn()
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
  deleteEvidence: mocks.deleteEvidence,
  getAnalystProfiles: mocks.getAnalystProfiles,
  getCompanyAnalysisRuns: mocks.getCompanyAnalysisRuns,
  getLatestCompanyAnalysisRuns: mocks.getLatestCompanyAnalysisRuns,
  runCompanyAnalysis: mocks.runCompanyAnalysis,
  runCompanyAnalysisBatch: mocks.runCompanyAnalysisBatch,
  deleteCompanyAnalysisRun: mocks.deleteCompanyAnalysisRun
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
                    }
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
  mocks.deleteEvidence.mockClear();
  mocks.getAnalystProfiles.mockClear();
  mocks.getCompanyAnalysisRuns.mockClear();
  mocks.getLatestCompanyAnalysisRuns.mockClear();
  mocks.runCompanyAnalysis.mockClear();
  mocks.runCompanyAnalysisBatch.mockClear();
  mocks.deleteCompanyAnalysisRun.mockClear();
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
      efficiency: {},
      per_share: {}
    },
    financial_trends: {},
    financial_flags: [],
    financial_data_gaps: ["缺少资本开支，无法计算严格自由现金流。"]
  };
}

describe("App", () => {
  it("renders the dashboard shell", async () => {
    render(<App />);

    expect(screen.getByRole("heading", { name: "价值投资研究工作台" })).toBeInTheDocument();
    expect(screen.getByRole("navigation")).toBeInTheDocument();
    expect(await screen.findByText("Value Investment API 0.1.0")).toBeInTheDocument();
  });

  it("opens company search and company workspace", async () => {
    render(<App />);

    fireEvent.click(screen.getByRole("button", { name: "Company Search" }));

    expect(await screen.findByRole("heading", { name: "公司搜索", level: 2 })).toBeInTheDocument();
    expect(await screen.findByText("贵州茅台")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "档案" }));

    await waitFor(() => {
      expect(mocks.getCompany).toHaveBeenCalledWith(1, expect.any(AbortSignal));
    });
    expect(mocks.getCompanyFinancials).toHaveBeenCalledWith(1, {
      limit: 60,
      offset: 0,
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
    expect(await screen.findByText("财务数据")).toBeInTheDocument();
    expect(await screen.findByText("最新期间")).toBeInTheDocument();
    expect(await screen.findByText("财务旗标")).toBeInTheDocument();
    expect(await screen.findByText("数据缺口")).toBeInTheDocument();
    expect((await screen.findAllByText("收入")).length).toBeGreaterThan(0);
    expect((await screen.findAllByText("年度经营摘要已导入")).length).toBeGreaterThan(0);
    expect(await screen.findByText("外部信息")).toBeInTheDocument();
    expect(await screen.findByText("测试行业证据已入库")).toBeInTheDocument();
    expect(await screen.findByText("基本面证据")).toBeInTheDocument();
    expect(await screen.findByRole("link", { name: "test_fixture" })).toHaveAttribute(
      "href",
      "https://example.test/evidence"
    );
    expect(await screen.findByText("model_name")).toBeInTheDocument();
    expect(await screen.findByText("fake-model")).toBeInTheDocument();
    expect(await screen.findByText("分析师视角")).toBeInTheDocument();
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
    expect(await screen.findByText("种子财务显示利润和现金流匹配")).toBeInTheDocument();
    expect(await screen.findByText("2025A 毛利率 58%")).toBeInTheDocument();
    expect(
      await screen.findByText("现金流是否能连续多年覆盖利润？ 渠道库存是否需要继续跟踪？")
    ).toBeInTheDocument();
    expect(await screen.findByText("估值数据缺失；管理层证据不足")).toBeInTheDocument();
    expect(
      await screen.findByText("缺少估值和更长周期财务数据；缺少渠道库存数据")
    ).toBeInTheDocument();
    expect(screen.queryByText(/。；/)).not.toBeInTheDocument();
    expect(screen.queryByText(/？；/)).not.toBeInTheDocument();
  });

  it("refreshes company profile market data from the workspace", async () => {
    render(<App />);

    fireEvent.click(screen.getByRole("button", { name: "Company Search" }));
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

    fireEvent.click(screen.getByRole("button", { name: "Company Search" }));
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

    fireEvent.click(screen.getByRole("button", { name: "Company Search" }));
    expect(await screen.findByText("贵州茅台")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "档案" }));
    expect(await screen.findByText("财务数据")).toBeInTheDocument();

    mocks.getCompanyFinancials.mockResolvedValueOnce({
      items: [
        {
          id: 2,
          company_id: 1,
          period: "2025年报",
          statement_type: "main_financial_indicators",
          currency: "CNY",
          fields: {
            operating_cash_flow_to_revenue: 0.421,
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

    expect(await screen.findByText("已搜索 2 条，新增 2 条，更新 0 条")).toBeInTheDocument();
    expect((await screen.findAllByText("2025年报")).length).toBeGreaterThan(0);
    expect(await screen.findByText("1,720.54亿 元")).toBeInTheDocument();
    expect(await screen.findAllByText("净资产收益率")).toHaveLength(2);
    expect(await screen.findByText("42.1%")).toBeInTheDocument();
  });

  it("deletes an unwanted financial statement from the company workspace", async () => {
    mocks.getCompanyFinancials.mockResolvedValueOnce(makeSyncedFinancialStatements());

    render(<App />);

    fireEvent.click(screen.getByRole("button", { name: "Company Search" }));
    expect(await screen.findByText("贵州茅台")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "档案" }));
    expect(await screen.findByText("2025年报")).toBeInTheDocument();
    expect(await screen.findByText("2016年报")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "删除财务数据：2025年报" }));

    await waitFor(() => {
      expect(mocks.deleteCompanyFinancialStatement).toHaveBeenCalledWith(1, 2);
    });
    expect(await screen.findByText("已删除财务数据")).toBeInTheDocument();
    expect(screen.queryByText("2025年报")).not.toBeInTheDocument();
    expect(screen.getByText("2016年报")).toBeInTheDocument();
  });

  it("shows financial statement delete failures without removing the item", async () => {
    mocks.deleteCompanyFinancialStatement.mockRejectedValueOnce(
      new Error("Financial statement not found")
    );
    mocks.getCompanyFinancials.mockResolvedValueOnce(makeSyncedFinancialStatements());

    render(<App />);

    fireEvent.click(screen.getByRole("button", { name: "Company Search" }));
    expect(await screen.findByText("贵州茅台")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "档案" }));
    expect(await screen.findByText("2025年报")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "删除财务数据：2025年报" }));

    await waitFor(() => {
      expect(mocks.deleteCompanyFinancialStatement).toHaveBeenCalledWith(1, 2);
    });
    expect(await screen.findByText("Financial statement not found")).toBeInTheDocument();
    expect(screen.getByText("2025年报")).toBeInTheDocument();
  });

  it("searches announcements and refreshes the announcement list", async () => {
    render(<App />);

    fireEvent.click(screen.getByRole("button", { name: "Company Search" }));
    expect(await screen.findByText("贵州茅台")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "档案" }));
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

    fireEvent.click(screen.getByRole("button", { name: "Company Search" }));
    expect(await screen.findByText("贵州茅台")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "档案" }));
    expect(await screen.findByText("公告区块")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "搜索公告" }));

    expect(await screen.findByText("当前公告同步第一版仅支持 A 股证券代码")).toBeInTheDocument();
  });

  it("summarizes all announcements and displays each model result in place", async () => {
    render(<App />);

    fireEvent.click(screen.getByRole("button", { name: "Company Search" }));
    expect(await screen.findByText("贵州茅台")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "档案" }));
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

    fireEvent.click(screen.getByRole("button", { name: "Company Search" }));
    expect(await screen.findByText("贵州茅台")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "档案" }));
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

    fireEvent.click(screen.getByRole("button", { name: "Company Search" }));
    expect(await screen.findByText("贵州茅台")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "档案" }));
    expect(await screen.findByText("公告区块")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "一键快速摘要" }));

    expect(await screen.findByText("公告快速摘要失败：后端返回对象错误")).toBeInTheDocument();
    expect(screen.queryByText("[object Object]")).not.toBeInTheDocument();
  });

  it("summarizes a single announcement deeply and displays the result in place", async () => {
    render(<App />);

    fireEvent.click(screen.getByRole("button", { name: "Company Search" }));
    expect(await screen.findByText("贵州茅台")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "档案" }));
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

    fireEvent.click(screen.getByRole("button", { name: "Company Search" }));
    expect(await screen.findByText("贵州茅台")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "档案" }));
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

    fireEvent.click(screen.getByRole("button", { name: "Company Search" }));
    expect(await screen.findByText("贵州茅台")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "档案" }));
    expect(await screen.findByText("公告区块")).toBeInTheDocument();

    expect(screen.getByRole("button", { name: "一键快速摘要" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "一键深度摘要" })).toBeInTheDocument();
  });

  it("hides generic announcement tags such as 待复核", async () => {
    render(<App />);

    fireEvent.click(screen.getByRole("button", { name: "Company Search" }));
    expect(await screen.findByText("贵州茅台")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "档案" }));
    expect(await screen.findByText("公告区块")).toBeInTheDocument();

    expect(screen.queryByText("待复核")).not.toBeInTheDocument();
  });

  it("deletes an announcement from the company workspace", async () => {
    render(<App />);

    fireEvent.click(screen.getByRole("button", { name: "Company Search" }));
    expect(await screen.findByText("贵州茅台")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "档案" }));
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

    fireEvent.click(screen.getByRole("button", { name: "Company Search" }));
    expect(await screen.findByText("贵州茅台")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "档案" }));
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

    fireEvent.click(screen.getByRole("button", { name: "Company Search" }));
    expect(await screen.findByText("贵州茅台")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "档案" }));
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
        keywords: ["贵州茅台", "白酒"],
        max_results: 10
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

  it("deletes an irrelevant external evidence item and refreshes the list", async () => {
    render(<App />);

    fireEvent.click(screen.getByRole("button", { name: "Company Search" }));
    expect(await screen.findByText("贵州茅台")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "档案" }));
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

    fireEvent.click(screen.getByRole("button", { name: "Company Search" }));
    expect(await screen.findByText("贵州茅台")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "档案" }));
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

    fireEvent.click(screen.getByRole("button", { name: "Company Search" }));
    expect(await screen.findByText("贵州茅台")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "档案" }));
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

    fireEvent.click(screen.getByRole("button", { name: "Company Search" }));
    expect(await screen.findByText("贵州茅台")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "档案" }));
    expect(await screen.findByText("外部信息")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "搜索外部信息" }));

    expect(
      await screen.findByText("模型未配置，请先在 .env 中设置：MODEL_API_KEY")
    ).toBeInTheDocument();
  });

  it("runs model smoke test without creating evidence or analyst runs", async () => {
    render(<App />);

    fireEvent.click(screen.getByRole("button", { name: "Company Search" }));
    expect(await screen.findByText("贵州茅台")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "档案" }));
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

    fireEvent.click(screen.getByRole("button", { name: "Company Search" }));
    expect(await screen.findByText("贵州茅台")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "档案" }));
    expect(await screen.findByText("分析师视角")).toBeInTheDocument();

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

    fireEvent.click(screen.getByRole("button", { name: "Company Search" }));
    expect(await screen.findByText("贵州茅台")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "档案" }));
    expect(await screen.findByText("分析师视角")).toBeInTheDocument();

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

    fireEvent.click(screen.getByRole("button", { name: "Company Search" }));
    expect(await screen.findByText("贵州茅台")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "档案" }));

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

    fireEvent.click(screen.getByRole("button", { name: "Company Search" }));
    expect(await screen.findByText("贵州茅台")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "档案" }));
    expect(await screen.findByText("分析师视角")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "生成全部" }));

    expect(
      await screen.findByText(/已生成 1 个视角，失败 1 个；彼得林奇：ModelGatewayError/)
    ).toBeInTheDocument();
    expect(await screen.findByText(/HTTP 504/)).toBeInTheDocument();
  });

  it("deletes an analyst run only after an explicit user action", async () => {
    render(<App />);

    fireEvent.click(screen.getByRole("button", { name: "Company Search" }));
    expect(await screen.findByText("贵州茅台")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "档案" }));
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

    fireEvent.click(screen.getByRole("button", { name: "Company Search" }));
    expect(await screen.findByText("贵州茅台")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "档案" }));
    expect(await screen.findByText("分析师视角")).toBeInTheDocument();

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

    fireEvent.click(screen.getByRole("button", { name: "Company Search" }));

    expect(await screen.findByText("公司池共 21 家，第 1-20 家")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "上一页" })).toBeDisabled();

    fireEvent.click(screen.getByRole("button", { name: "下一页" }));

    expect(await screen.findByText("五粮液")).toBeInTheDocument();
    await waitFor(() => {
      expect(mocks.getCompanies).toHaveBeenLastCalledWith(
        expect.objectContaining({
          limit: 20,
          offset: 20,
          signal: expect.any(AbortSignal)
        })
      );
    });
    expect(screen.getByText("21-21 / 21")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "下一页" })).toBeDisabled();

    fireEvent.click(screen.getByRole("button", { name: "上一页" }));

    expect(await screen.findByText("贵州茅台")).toBeInTheDocument();
    await waitFor(() => {
      expect(mocks.getCompanies).toHaveBeenLastCalledWith(
        expect.objectContaining({
          limit: 20,
          offset: 0,
          signal: expect.any(AbortSignal)
        })
      );
    });
  });
 
  it("creates a company from the fixed new company panel", async () => {
    render(<App />);

    fireEvent.click(screen.getByRole("button", { name: "Company Search" }));

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
});

