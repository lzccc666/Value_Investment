export type HealthResponse = {
  status: "ok";
  service: string;
  version: string;
  environment: string;
  checked_at: string;
};

export type Company = {
  id: number;
  ticker: string;
  exchange: string;
  name: string;
  canonical_key?: string | null;
  legal_name?: string | null;
  aliases?: string[];
  domicile_country?: string | null;
  reporting_currency?: string | null;
  fiscal_year_end?: string | null;
  external_ids?: Record<string, unknown>;
  industry: string | null;
  description: string | null;
  listed_date: string | null;
  status: string;
  tags: string[];
  market_cap: number | null;
  current_price: number | null;
  pe_ttm: number | null;
  pe_dynamic: number | null;
  pe_static: number | null;
  pb_ratio: number | null;
  ps_ratio: number | null;
  dividend_yield_ttm: number | null;
  dividend_yield_static: number | null;
  market_data_source: string | null;
  market_data_source_url: string | null;
  market_data_updated_at: string | null;
  created_at: string;
  updated_at: string;
  primary_listing?: SecurityListing | null;
};

export type SecurityListing = {
  id: number;
  company_id: number;
  ticker: string;
  symbol: string;
  exchange: string;
  market: string;
  trading_currency: string;
  security_type: string;
  listed_date: string | null;
  is_primary: boolean;
  is_active: boolean;
  underlying_shares_per_listing_unit: number | null;
  provider_identifiers: Record<string, unknown>;
  created_at: string;
  updated_at: string;
};

export type SecurityListingListResponse = {
  company_id: number;
  items: SecurityListing[];
};

export type MarketSnapshot = {
  id: number;
  listing_id: number;
  price: number;
  currency: string;
  market_cap: number | null;
  pe_ttm: number | null;
  pe_dynamic: number | null;
  pe_static: number | null;
  pb_ratio: number | null;
  ps_ratio: number | null;
  dividend_yield_ttm: number | null;
  dividend_yield_static: number | null;
  price_as_of: string;
  fetched_at: string;
  source: string;
  source_url: string | null;
  raw_snapshot_hash: string | null;
};

export type CapabilityStatus = "available" | "partial" | "unavailable" | "stale" | "blocked";

export type ProviderCapability = {
  status: CapabilityStatus;
  provider?: string | null;
  reason?: string | null;
  remediation?: string | null;
};

export type MarketCapabilitiesResponse = {
  company_id: number;
  listing_id: number;
  market: string;
  capabilities: Record<string, ProviderCapability>;
};

export type CompanyListResponse = {
  items: Company[];
  total: number;
  limit: number;
  offset: number;
};

export type NewCompanyPayload = {
  ticker: string;
  exchange: string;
  name: string;
  industry?: string | null;
  description?: string | null;
  listed_date?: string | null;
  status?: string;
  tags?: string[];
};

export type FinancialStatement = {
  id: number;
  company_id: number;
  period: string;
  statement_type: string;
  currency: string;
  fields: Record<string, unknown>;
  source: string | null;
  source_url: string | null;
  source_record_id?: string | null;
  filing_type?: string | null;
  taxonomy?: string | null;
  period_start?: string | null;
  period_end?: string | null;
  period_type?: string | null;
  fiscal_year?: number | null;
  fiscal_period?: string | null;
  filed_at?: string | null;
  unit_scale?: number;
  is_amendment?: boolean;
  raw_snapshot_hash?: string | null;
  created_at: string;
};

export type FinancialStatementListResponse = {
  items: FinancialStatement[];
  total: number;
  limit: number;
  offset: number;
};

export type FinancialEvidencePack = {
  reporting_currency?: string | null;
  accounting_standard?: string | null;
  source_coverage?: Record<string, unknown>;
  mapping_diagnostics?: Array<Record<string, unknown>>;
  latest_period: string | null;
  periods: string[];
  financial_facts: Record<string, unknown>;
  financial_metrics: Record<string, unknown>;
  cash_flow_coverage?: Record<string, unknown>;
  financial_trends: Record<string, unknown>;
  financial_flags: Array<Record<string, unknown>>;
  financial_data_gaps: Array<Record<string, unknown>>;
  financial_data_gap_messages?: string[];
  cash_flow_quality?: Record<string, unknown>;
  balance_sheet_adjustment?: Record<string, unknown>;
  capital_allocation?: Record<string, unknown>;
  valuation_readiness?: Record<string, unknown>;
  quality_matrix?: Record<string, unknown>;
  analyst_summary?: Record<string, unknown>;
  data_quality?: Record<string, unknown>;
};

export type FinancialStatementSyncResponse = {
  company_id: number;
  source: string;
  fetched: number;
  created: number;
  updated: number;
  items: FinancialStatement[];
};

export type FinancialStatementDeleteResponse = {
  id: number;
  deleted: boolean;
};

export type Announcement = {
  id: number;
  company_id: number;
  listing_id?: number | null;
  title: string;
  published_at: string;
  category: string;
  content: string | null;
  raw_content: string | null;
  summary: string | null;
  source: string | null;
  source_url: string | null;
  raw_url: string | null;
  source_document_id?: string | null;
  document_type?: string | null;
  filing_form?: string | null;
  language?: string | null;
  period_end?: string | null;
  content_type?: string | null;
  content_source?: string | null;
  content_fetched_at?: string | null;
  raw_content_hash?: string | null;
  key_facts: string[];
  impact_direction: string | null;
  sentiment: string | null;
  positive_impacts: string[];
  negative_impacts: string[];
  neutral_impacts: string[];
  risk_tips: string[];
  review_questions: string[];
  tags: string[];
  summary_status: string;
  summary_model_name: string | null;
  summary_prompt_version: string | null;
  summarized_at: string | null;
  created_at: string;
};

export function getAnnouncementDisplayStatus(announcement: Announcement): string {
  if (announcement.summary_model_name && announcement.summary_model_name !== "metadata_keyword") {
    return "deep_summarized";
  }
  if (announcement.summary_model_name === "metadata_keyword" || announcement.summary) {
    return "quick_summarized";
  }
  return announcement.summary_status || "unprocessed";
}

export type AnnouncementListResponse = {
  items: Announcement[];
  total: number;
  limit: number;
  offset: number;
};

export type AnnouncementSyncResponse = {
  company_id: number;
  source: string;
  fetched: number;
  created: number;
  updated: number;
  skipped: number;
  pruned: number;
  errors: string[];
  items: Announcement[];
};

export type AnnouncementDeleteResponse = {
  id: number;
  deleted: boolean;
};

export type AnnouncementSummaryResponse = {
  company_id: number;
  announcement_id: number;
  run_id: number | null;
  status: "success" | "failed";
  summary_status: string;
  announcement: Announcement;
};

export type AnnouncementSummaryBatchItem = {
  announcement_id: number;
  status: "success" | "failed" | "skipped";
  summary_status: string;
  run_id: number | null;
  announcement: Announcement | null;
  error: string | null;
  error_type: string | null;
};

export type AnnouncementSummaryBatchResponse = {
  company_id: number;
  requested: number;
  processed: number;
  remaining: number;
  succeeded: number;
  failed: number;
  status: "success" | "partial" | "failed";
  items: AnnouncementSummaryBatchItem[];
};

export type EvidenceSourceType =
  | "policy"
  | "industry_news"
  | "company_news"
  | "public_data"
  | "regulatory"
  | "web";

export type ImpactDirection = "positive" | "neutral" | "negative" | "mixed" | "unknown";
export type EvidenceAnalysisStatus = "model_analyzed" | "search_lead";
export type EvidenceUseScope =
  | "fundamental_analysis"
  | "analyst_view"
  | "intrinsic_valuation";

export type Evidence = {
  id: number;
  company_id: number;
  source_type: EvidenceSourceType;
  title: string;
  source: string | null;
  source_url: string | null;
  published_at: string | null;
  summary: string;
  key_facts: string[];
  impact_direction: ImpactDirection;
  importance_score: number;
  credibility_score: number;
  tags: string[];
  requires_review: boolean;
  price_sensitive: boolean;
  use_scope: EvidenceUseScope[];
  analysis_status: EvidenceAnalysisStatus;
  analysis_note: string | null;
  raw_snapshot: Record<string, unknown>;
  created_at: string;
};

export type EvidenceListResponse = {
  items: Evidence[];
  total: number;
  limit: number;
  offset: number;
};

export type EvidenceSearchResponse = {
  company_id: number;
  run_id: number;
  status: "success" | "partial" | "failed";
  created: number;
  items: Evidence[];
  diagnostics?: Record<string, unknown> | null;
};

export type EvidenceImportTextRequest = {
  title?: string;
  content: string;
  source?: string;
  source_url?: string;
  published_at?: string;
  source_type?: EvidenceSourceType;
  notes?: string;
};

export type EvidenceImportTextResponse = EvidenceSearchResponse;

export type EvidenceDeleteResponse = {
  id: number;
  deleted: boolean;
};

export type ModelConfigStatus = {
  provider: string;
  base_url: string | null;
  model_name: string | null;
  wire_api: string | null;
  api_key_configured: boolean;
};

export type ModelSmokeTestResponse = ModelConfigStatus & {
  ok: boolean;
  message: string;
};

export type AnalystRule = {
  id: string;
  label: string;
  description: string;
  status_rubric: Record<AnalystRuleStatus, string>;
};

export type AnalystProfile = {
  id: string;
  name: string;
  display_name: string;
  description: string;
  philosophy: string;
  core_logic: string[];
  decision_sequence: string[];
  preferred_evidence: string[];
  failure_modes: string[];
  rules: AnalystRule[];
  prompt_focus: string[];
};

export type AnalystProfileListResponse = {
  items: AnalystProfile[];
};

export type AnalystRuleStatus = "pass" | "neutral" | "unknown" | "warn" | "fail";

export type AnalystRuleCheck = {
  rule_id: string;
  status: AnalystRuleStatus;
  summary: string;
  evidence_ids: number[];
  financial_periods: string[];
  announcement_ids: number[];
};

export type AnalystAnalysisResult = {
  analyst_profile: string;
  overview: string;
  profile_fit_score: number;
  confidence: number;
  key_observations: string[];
  rule_checks: AnalystRuleCheck[];
  supporting_evidence_ids: number[];
  financial_observations: string[];
  announcement_observations: string[];
  risk_flags: string[];
  counter_evidence: string[];
  valuation_assumption_suggestions: string[];
  valuation_assumption_details?: Array<{
    assumption_type: string;
    reason: string;
    needed_inputs: string[];
    source_refs: Record<string, Array<number | string>>;
  }>;
  data_gaps: string[];
  follow_up_questions: string[];
  analysis_basis: {
    financial_periods?: string[];
    announcement_ids?: number[];
    external_evidence_ids?: number[];
    accounting_event_count?: number;
    accounting_event_labels?: string[];
    notes?: string[];
  };
  accounting_events: Array<{
    event_type?: string;
    label?: string;
    source_type?: string;
    source_id?: number | string | null;
    source_title?: string | null;
    summary?: string;
    comparability_impact?: string;
    matched_keywords?: string[];
    confidence?: number;
  }>;
  score_explanations: {
    profile_relevance?: {
      score?: number;
      method?: string;
      reasons?: string[];
      signals?: Record<string, boolean>;
    };
    data_confidence?: {
      score?: number;
      method?: string;
      reasons?: string[];
    };
  };
};

export type AnalysisRun = {
  id: number;
  company_id: number;
  run_type: string;
  analyst_profile: string | null;
  run_version: string | null;
  model_name: string | null;
  prompt_version: string | null;
  data_snapshot_hash: string | null;
  config_version: number | null;
  config_hash: string | null;
  config_snapshot: Record<string, unknown>;
  result: Partial<AnalystAnalysisResult> & Record<string, unknown>;
  confidence: number | null;
  parent_run_id: number | null;
  is_latest: boolean;
  user_note: string | null;
  status: string;
  created_at: string;
};

export type AnalysisRunListResponse = {
  items: AnalysisRun[];
  total: number;
  limit: number;
  offset: number;
};

export type AnalysisLatestRunsResponse = {
  company_id: number;
  run_type: string | null;
  analyst_profile: string | null;
  status: string | null;
  items: AnalysisRun[];
};

export type AnalysisBatchRunItem = {
  analyst_profile: string;
  status: "success" | "failed";
  run: AnalysisRun | null;
  error: string | null;
  error_type: string | null;
};

export type AnalysisBatchRunResponse = {
  company_id: number;
  requested: number;
  succeeded: number;
  failed: number;
  items: AnalysisBatchRunItem[];
};

export type AnalysisRunDeleteResponse = {
  id: number;
  deleted: boolean;
};

export type InvestmentMemo = {
  id: number;
  company_id: number;
  generation_run_id: number | null;
  parent_memo_id: number | null;
  version_no: number;
  editor_type: string;
  title: string;
  conclusion: string;
  sections: Record<string, unknown>;
  markdown: string;
  source_analyst_run_ids: number[];
  source_snapshot_hash: string | null;
  config_version: number | null;
  config_hash: string | null;
  config_snapshot: Record<string, unknown>;
  change_note: string | null;
  status: string;
  is_latest: boolean;
  created_at: string;
  updated_at: string;
};

export type InvestmentMemoLatestResponse = {
  company_id: number;
  item: InvestmentMemo | null;
};

export type InvestmentMemoListResponse = {
  items: InvestmentMemo[];
  total: number;
  limit: number;
  offset: number;
};

export type InvestmentMemoGenerateResponse = {
  company_id: number;
  run: AnalysisRun;
  memo: InvestmentMemo;
};

export type InvestmentMemoDeleteResponse = {
  id: number;
  deleted: boolean;
  latest_memo_id: number | null;
};

export type InvestmentMemoArchiveResponse = {
  id: number;
  archived: boolean;
  latest_memo_id: number | null;
};

export type ValuationRun = {
  id: number;
  company_id: number;
  memo_id: number | null;
  run_version: string;
  status: "draft" | "locked" | "archived" | "failed";
  price_blind: boolean;
  forbidden_price_inputs: Record<string, unknown>;
  input_snapshot: Record<string, unknown>;
  input_snapshot_hash: string | null;
  config_version: number | null;
  config_hash: string | null;
  config_snapshot: Record<string, unknown>;
  valuation_inputs: Record<string, unknown>;
  model_suggested_assumptions: Record<string, unknown>;
  user_adjusted_assumptions: Record<string, unknown>;
  assumptions: Record<string, unknown>;
  methods: Record<string, unknown>;
  results: Record<string, unknown>;
  sensitivity: Record<string, unknown>;
  confidence: number | null;
  confidence_summary: Record<string, unknown>;
  source_map: Record<string, unknown>;
  valuation_currency?: string | null;
  share_basis_snapshot?: Record<string, unknown>;
  user_note: string | null;
  created_at: string;
  updated_at: string;
};

export type ValuationRunLatestResponse = {
  company_id: number;
  item: ValuationRun | null;
};

export type ValuationRunListResponse = {
  items: ValuationRun[];
  total: number;
  limit: number;
  offset: number;
};

export type ValuationRunMutationResponse = {
  company_id: number;
  item: ValuationRun;
};

export type PriceDecisionRun = {
  id: number;
  company_id: number;
  valuation_run_id: number;
  memo_id: number;
  listing_id?: number | null;
  market_snapshot_id?: number | null;
  fx_rate_snapshot_id?: number | null;
  version_no: number;
  run_version: string;
  formula_version: string;
  status: "active" | "deleted";
  input_snapshot: Record<string, unknown>;
  input_snapshot_hash: string;
  config_version: number | null;
  config_hash: string | null;
  config_snapshot: Record<string, unknown>;
  intrinsic_values_per_share: Record<string, number>;
  issuer_intrinsic_values_per_share?: Record<string, number>;
  valuation_currency?: string | null;
  trading_currency?: string | null;
  underlying_shares_per_listing_unit?: number | null;
  fx_rate?: number | null;
  current_price: number;
  market_data_updated_at: string;
  suggested_safety_margin: number;
  safety_margin_override: number | null;
  effective_safety_margin: number;
  scenario_buy_prices: Record<string, number>;
  suggested_buy_price: number;
  current_margin: number;
  price_status: string;
  created_at: string;
  updated_at: string;
  deleted_at: string | null;
};

export type PriceDecisionLatestResponse = {
  company_id: number;
  item: PriceDecisionRun | null;
};

export type PriceDecisionListResponse = {
  items: PriceDecisionRun[];
  total: number;
  limit: number;
  offset: number;
};

export type PriceDecisionMutationResponse = {
  company_id: number;
  item: PriceDecisionRun;
};

export type PriceDecisionDeleteResponse = {
  id: number;
  deleted: boolean;
  latest_price_decision_run_id: number | null;
};

export type ParameterValidationIssue = {
  path: string;
  message: string;
  severity: "error" | "warning";
  code: string;
};

export type ParameterValidationResult = {
  valid: boolean;
  errors: ParameterValidationIssue[];
  warnings: ParameterValidationIssue[];
  actual_parameter_count: number;
  audit_parameter_count: number;
};

export type ParameterMetadataItem = {
  path: string;
  domain: string;
  label: string;
  code_name: string;
  description: string;
  unit: string;
  default_value: unknown;
  current_value: unknown;
  minimum: number | null;
  maximum: number | null;
  editable: boolean;
  expert: boolean;
  audit_only: boolean;
  risk: "low" | "medium" | "high";
};

export type ParameterConfigCurrentResponse = {
  config_json: Record<string, unknown>;
  config_hash: string;
  source: "source_file" | "builtin_default" | "builtin_fallback";
  fallback_reason: string | null;
  validation: ParameterValidationResult;
  metadata: ParameterMetadataItem[];
};

export type ParameterConfigPublishResponse = {
  config_json: Record<string, unknown>;
  config_hash: string;
  source: "source_file";
  validation: ParameterValidationResult;
  metadata: ParameterMetadataItem[];
};

export type DataOperationType =
  | "reset_company_research_data"
  | "clear_analysis_history"
  | "initialize_database"
  | "prune_versions"
  | "purge_deleted_and_vacuum"
  | "restore_backup"
  | "delete_backup";

export type DataOperationParameters = {
  company_id?: number | null;
  keep_count?: number | null;
  backup_id?: string | null;
};

export type ProtectedRecord = {
  table: string;
  record_id: number;
  reason: string;
};

export type DataOperationPreview = {
  operation_token: string;
  operation_type: DataOperationType;
  parameters: DataOperationParameters;
  affected_counts: Record<string, number>;
  protected_records: ProtectedRecord[];
  estimated_reclaim_bytes: number;
  requires_backup: boolean;
  confirmation_phrase: string;
  expires_at: string;
};

export type DataOperationResult = {
  operation_type: DataOperationType;
  affected_counts: Record<string, number>;
  backup_id: string | null;
  protected_records: ProtectedRecord[];
  database_size_before: number | null;
  database_size_after: number | null;
  reclaimed_bytes: number | null;
  integrity_check: string | null;
  restart_required: boolean;
  message: string;
};

export type BackupManifest = {
  backup_id: string;
  created_at: string;
  database_filename: string;
  file_size: number;
  sha256: string;
  schema_version: number;
  record_counts: Record<string, number>;
  reason: string;
  application_version: string;
  verified: boolean | null;
  integrity_check: string | null;
};

export type AutomaticBackupSettings = {
  enabled: boolean;
  interval_hours: number;
  max_backups: number;
  last_auto_backup_at: string | null;
};

export type DataManagementSummary = {
  database_path: string;
  database_size: number;
  record_counts: Record<string, number>;
  soft_deleted_counts: Record<string, number>;
  latest_backup: BackupManifest | null;
  automatic_backup: AutomaticBackupSettings;
  maintenance_active: boolean;
  maintenance_operation: string | null;
  schema_version: number;
  integrity_check: string;
};

export type BackupListResponse = {
  items: BackupManifest[];
  total: number;
};

export type BackupVerifyResponse = {
  backup_id: string;
  valid: boolean;
  sha256_matches: boolean;
  integrity_check: string;
};

export type PortfolioOwnerType = "self" | "investor";
export type PortfolioCurrency = "CNY" | "HKD" | "USD";

export type PortfolioOwner = {
  id: number;
  name: string;
  owner_type: PortfolioOwnerType;
  notes: string | null;
  display_order: number;
  created_at: string;
  updated_at: string;
};

export type PortfolioOwnerListResponse = {
  items: PortfolioOwner[];
  total: number;
};

export type PortfolioSnapshot = {
  id: number;
  owner_id: number;
  title: string;
  as_of_date: string;
  base_currency: PortfolioCurrency;
  notes: string | null;
  display_order: number;
  created_at: string;
  updated_at: string;
};

export type PortfolioSnapshotListResponse = {
  owner_id: number;
  items: PortfolioSnapshot[];
  total: number;
};

export type PortfolioHolding = {
  id: number;
  snapshot_id: number;
  listing_id: number;
  company_id: number;
  company_name: string;
  ticker: string;
  exchange: string;
  market: string;
  trading_currency: string;
  security_type: string;
  quantity: string;
  notes: string | null;
  display_order: number;
  created_at: string;
  updated_at: string;
};

export type PortfolioHoldingListResponse = {
  snapshot_id: number;
  items: PortfolioHolding[];
  total: number;
};

export type PortfolioListingSearchItem = {
  id: number;
  company_id: number;
  company_name: string;
  ticker: string;
  symbol: string;
  exchange: string;
  market: string;
  trading_currency: string;
  security_type: string;
  is_primary: boolean;
};

export type PortfolioListingSearchResponse = {
  items: PortfolioListingSearchItem[];
  total: number;
};

export type SecUsListingCatalogItem = {
  cik: string;
  company_name: string;
  symbol: string;
  ticker: string;
  exchange: "NASDAQ" | "NYSE";
};

export type SecUsListingCatalogResponse = {
  items: SecUsListingCatalogItem[];
  total: number;
  source: string;
};

export type AhListingCatalogItem = {
  quote_id: string;
  company_name: string;
  symbol: string;
  ticker: string;
  exchange: "SSE" | "SZSE" | "BSE" | "HKEX";
  market: "A_SHARE" | "HK";
  trading_currency: "CNY" | "HKD";
  security_type: "common_stock";
};

export type AhListingCatalogResponse = {
  items: AhListingCatalogItem[];
  total: number;
  source: string;
};

export type BuyMemoCompanyCandidate = {
  company_id: number;
  company_name: string;
  primary_ticker: string;
  decision_count: number;
};

export type BuyMemoDecisionCandidate = {
  price_decision_run_id: number;
  version_no: number;
  run_version: string;
  listing_ticker: string;
  exchange: string | null;
  trading_currency: string | null;
  base_intrinsic_value: string;
  suggested_buy_price: string;
  designed_safety_margin: string;
  latest_report_period: string | null;
  created_at: string;
  already_imported: boolean;
};

export type BuyMemoEntry = {
  id: number;
  company_id: number;
  source_price_decision_run_id: number | null;
  company_name: string;
  listing_ticker: string;
  exchange: string | null;
  trading_currency: string | null;
  base_intrinsic_value: string;
  suggested_buy_price: string;
  designed_safety_margin: string;
  latest_report_period: string | null;
  price_decision_version_no: number;
  price_decision_run_version: string;
  price_decision_created_at: string;
  created_at: string;
  updated_at: string;
};

export type PortfolioValuationItem = {
  holding_id: number;
  listing_id: number;
  company_id: number;
  company_name: string;
  ticker: string;
  exchange: string;
  market: string;
  trading_currency: string;
  security_type: string;
  quantity: string;
  latest_price: string | null;
  quote_currency: string | null;
  quote_as_of: string | null;
  quote_source: string | null;
  quote_source_url: string | null;
  local_market_value: string | null;
  fx_rate: string | null;
  fx_rate_date: string | null;
  fx_source: string | null;
  base_market_value: string | null;
  weight: string | null;
  data_status:
    | "priced"
    | "missing_price"
    | "missing_fx"
    | "currency_mismatch"
    | "inactive_listing";
  status_reason: string;
};

export type PortfolioValuation = {
  snapshot: PortfolioSnapshot;
  owner: PortfolioOwner;
  priced_total: string | null;
  base_currency: PortfolioCurrency;
  holding_count: number;
  priced_count: number;
  unpriced_count: number;
  valuation_status: "empty" | "complete" | "incomplete";
  items: PortfolioValuationItem[];
};

export type PortfolioRefreshResult = {
  snapshot_id: number;
  status: "success" | "partial" | "failed";
  succeeded: number;
  failed: number;
  quote_results: Array<{
    listing_id: number;
    ticker: string;
    status: "success" | "failed";
    market_snapshot_id: number | null;
    error: string | null;
  }>;
  fx_results: Array<{
    base_currency: string;
    quote_currency: string;
    status: "identity" | "success" | "failed";
    fx_rate_snapshot_id: number | null;
    error: string | null;
  }>;
  valuation: PortfolioValuation;
};

export type MarketFearIndicator = {
  market: "A_SHARE" | "HK" | "US";
  indicator_code: string;
  indicator_name: string;
  value: string | null;
  data_date: string | null;
  daily_change: string | null;
  moving_average_20: string | null;
  percentile_3y: string | null;
  temperature_score: string | null;
  temperature_level: string | null;
  source: string | null;
  source_url: string | null;
  fetched_at: string | null;
  observation_count: number | null;
  freshness: "fresh" | "stale" | "unavailable";
  refresh_error: string | null;
  is_proxy: boolean;
  proxy_notice: string | null;
};

export type MarketFearResponse = {
  status: "success" | "partial" | "failed";
  items: MarketFearIndicator[];
  notice: string;
};

type RequestJsonOptions = {
  signal?: AbortSignal;
  method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  body?: unknown;
};

const apiBaseUrl = import.meta.env.VITE_API_BASE_URL ?? "/api";

async function fetchJson<T>(path: string, options: RequestJsonOptions = {}): Promise<T> {
  const response = await fetch(`${apiBaseUrl}${path}`, {
    method: options.method ?? "GET",
    headers: options.body ? { "Content-Type": "application/json" } : undefined,
    body: options.body ? JSON.stringify(options.body) : undefined,
    signal: options.signal
  });

  if (!response.ok) {
    const detail = await readErrorDetail(response);
    throw new Error(detail ?? `Request failed: ${response.status}`);
  }

  return response.json() as Promise<T>;
}

async function readErrorDetail(response: Response): Promise<string | null> {
  try {
    const payload = (await response.json()) as unknown;
    return formatApiErrorPayload(payload);
  } catch {
    return null;
  }
}

function formatApiErrorPayload(payload: unknown): string | null {
  if (payload === null || typeof payload === "undefined") {
    return null;
  }
  if (typeof payload === "string") {
    return payload.trim() || null;
  }
  if (typeof payload === "number" || typeof payload === "boolean") {
    return String(payload);
  }
  if (Array.isArray(payload)) {
    const messages = payload
      .map((item) => formatApiErrorPayload(item))
      .filter((item): item is string => Boolean(item));
    return messages.length > 0 ? messages.join("；") : null;
  }
  if (typeof payload === "object") {
    const record = payload as Record<string, unknown>;
    for (const key of ["detail", "message", "error"]) {
      const nested = formatApiErrorPayload(record[key]);
      if (nested) {
        return nested;
      }
    }
    if (typeof record.msg === "string") {
      const location = Array.isArray(record.loc) ? record.loc.join(".") : null;
      return location ? `${location}: ${record.msg}` : record.msg;
    }
    try {
      return JSON.stringify(payload);
    } catch {
      return null;
    }
  }
  return null;
}

export async function getHealth(): Promise<HealthResponse> {
  return fetchJson<HealthResponse>("/health");
}

export async function getCompanies(
  params: { q?: string; limit?: number; offset?: number; signal?: AbortSignal } = {}
): Promise<CompanyListResponse> {
  const searchParams = new URLSearchParams();

  if (params.q) {
    searchParams.set("q", params.q);
  }
  if (typeof params.limit === "number") {
    searchParams.set("limit", String(params.limit));
  }
  if (typeof params.offset === "number") {
    searchParams.set("offset", String(params.offset));
  }

  const queryString = searchParams.toString();
  return fetchJson<CompanyListResponse>(`/companies${queryString ? `?${queryString}` : ""}`, {
    signal: params.signal
  });
}

export async function getCompany(companyId: number, signal?: AbortSignal): Promise<Company> {
  return fetchJson<Company>(`/companies/${companyId}`, { signal });
}

export async function getCompanyListings(
  companyId: number,
  signal?: AbortSignal
): Promise<SecurityListingListResponse> {
  return fetchJson<SecurityListingListResponse>(`/companies/${companyId}/listings`, { signal });
}

export async function getCompanyMarketCapabilities(
  companyId: number,
  listingId?: number | null,
  signal?: AbortSignal
): Promise<MarketCapabilitiesResponse> {
  const query = listingId ? `?listing_id=${listingId}` : "";
  return fetchJson<MarketCapabilitiesResponse>(
    `/companies/${companyId}/market-capabilities${query}`,
    { signal }
  );
}

export async function getLatestListingMarketSnapshot(
  listingId: number,
  signal?: AbortSignal
): Promise<MarketSnapshot | null> {
  const response = await fetchJson<{ listing_id: number; item: MarketSnapshot | null }>(
    `/listings/${listingId}/market-snapshots/latest`,
    { signal }
  );
  return response.item;
}

export async function refreshListingProfile(listingId: number): Promise<Company> {
  return fetchJson<Company>(`/listings/${listingId}/profile/refresh`, { method: "POST" });
}

export async function refreshListingMarketSnapshot(listingId: number): Promise<MarketSnapshot> {
  return fetchJson<MarketSnapshot>(`/listings/${listingId}/market-snapshots/refresh`, {
    method: "POST"
  });
}

export async function refreshFxRate(
  baseCurrency: string,
  quoteCurrency: string
): Promise<{
  id: number;
  base_currency: string;
  quote_currency: string;
  rate: number;
  rate_date: string;
  calculation_audit: Record<string, unknown> | null;
}> {
  const query = new URLSearchParams({
    base_currency: baseCurrency,
    quote_currency: quoteCurrency
  });
  return fetchJson(`/fx-rates/refresh?${query.toString()}`, { method: "POST" });
}

export async function createCompany(payload: NewCompanyPayload): Promise<Company> {
  return fetchJson<Company>("/companies", {
    method: "POST",
    body: payload
  });
}

export async function refreshCompanyProfile(companyId: number): Promise<Company> {
  return fetchJson<Company>(`/companies/${companyId}/profile/refresh`, {
    method: "POST"
  });
}

export async function getCompanyFinancials(
  companyId: number,
  params: {
    limit?: number;
    offset?: number;
    period_limit?: number;
    period_offset?: number;
    signal?: AbortSignal;
  } = {}
): Promise<FinancialStatementListResponse> {
  const queryString = buildFinancialStatementQuery(params);
  return fetchJson<FinancialStatementListResponse>(
    `/companies/${companyId}/financials${queryString}`,
    {
      signal: params.signal
    }
  );
}

export async function getCompanyFinancialEvidencePack(
  companyId: number,
  signal?: AbortSignal
): Promise<FinancialEvidencePack> {
  return fetchJson<FinancialEvidencePack>(`/companies/${companyId}/financials/evidence-pack`, {
    signal
  });
}

export async function syncCompanyFinancials(
  companyId: number,
  params: { limit?: number; listing_id?: number | null; signal?: AbortSignal } = {}
): Promise<FinancialStatementSyncResponse> {
  const searchParams = new URLSearchParams();

  if (typeof params.limit === "number") {
    searchParams.set("limit", String(params.limit));
  }
  if (typeof params.listing_id === "number") {
    searchParams.set("listing_id", String(params.listing_id));
  }

  const queryString = searchParams.toString();
  return fetchJson<FinancialStatementSyncResponse>(
    `/companies/${companyId}/financials/sync${queryString ? `?${queryString}` : ""}`,
    {
      method: "POST",
      signal: params.signal
    }
  );
}

export async function deleteCompanyFinancialStatement(
  companyId: number,
  statementId: number,
  signal?: AbortSignal
): Promise<FinancialStatementDeleteResponse> {
  return fetchJson<FinancialStatementDeleteResponse>(
    `/companies/${companyId}/financials/${statementId}`,
    {
      method: "DELETE",
      signal
    }
  );
}

export async function getCompanyAnnouncements(
  companyId: number,
  params: { limit?: number; offset?: number; signal?: AbortSignal } = {}
): Promise<AnnouncementListResponse> {
  const queryString = buildPaginationQuery(params);
  return fetchJson<AnnouncementListResponse>(
    `/companies/${companyId}/announcements${queryString}`,
    {
      signal: params.signal
    }
  );
}

export async function syncCompanyAnnouncements(
  companyId: number,
  params: { years?: number; listing_id?: number | null; signal?: AbortSignal } = {}
): Promise<AnnouncementSyncResponse> {
  const searchParams = new URLSearchParams();

  if (typeof params.years === "number") {
    searchParams.set("years", String(params.years));
  }
  if (typeof params.listing_id === "number") {
    searchParams.set("listing_id", String(params.listing_id));
  }

  const queryString = searchParams.toString();
  return fetchJson<AnnouncementSyncResponse>(
    `/companies/${companyId}/announcements/sync${queryString ? `?${queryString}` : ""}`,
    {
      method: "POST",
      signal: params.signal
    }
  );
}

export async function deleteCompanyAnnouncement(
  companyId: number,
  announcementId: number,
  signal?: AbortSignal
): Promise<AnnouncementDeleteResponse> {
  return fetchJson<AnnouncementDeleteResponse>(
    `/companies/${companyId}/announcements/${announcementId}`,
    {
      method: "DELETE",
      signal
    }
  );
}

export async function getEvidenceModelConfig(signal?: AbortSignal): Promise<ModelConfigStatus> {
  return fetchJson<ModelConfigStatus>("/evidence/model-config", { signal });
}

export async function runEvidenceModelSmokeTest(
  signal?: AbortSignal
): Promise<ModelSmokeTestResponse> {
  return fetchJson<ModelSmokeTestResponse>("/evidence/model-smoke-test", {
    method: "POST",
    signal
  });
}

export async function summarizeCompanyAnnouncement(
  companyId: number,
  announcementId: number,
  signal?: AbortSignal
): Promise<AnnouncementSummaryResponse> {
  return fetchJson<AnnouncementSummaryResponse>(
    `/companies/${companyId}/announcements/${announcementId}/summarize`,
    {
      method: "POST",
      signal
    }
  );
}

export async function summarizeCompanyAnnouncements(
  companyId: number,
  params: {
    limit?: number;
    only_missing?: boolean;
    include_failed?: boolean;
    signal?: AbortSignal;
  } = {}
): Promise<AnnouncementSummaryBatchResponse> {
  const searchParams = new URLSearchParams();

  if (typeof params.limit === "number") {
    searchParams.set("limit", String(params.limit));
  }
  if (typeof params.only_missing === "boolean") {
    searchParams.set("only_missing", String(params.only_missing));
  }
  if (typeof params.include_failed === "boolean") {
    searchParams.set("include_failed", String(params.include_failed));
  }

  const queryString = searchParams.toString();
  return fetchJson<AnnouncementSummaryBatchResponse>(
    `/companies/${companyId}/announcements/summarize-all${queryString ? `?${queryString}` : ""}`,
    {
      method: "POST",
      signal: params.signal
    }
  );
}

export async function summarizeCompanyAnnouncementsDeep(
  companyId: number,
  params: {
    limit?: number;
    signal?: AbortSignal;
  } = {}
): Promise<AnnouncementSummaryBatchResponse> {
  const searchParams = new URLSearchParams();

  if (typeof params.limit === "number") {
    searchParams.set("limit", String(params.limit));
  }

  const queryString = searchParams.toString();
  return fetchJson<AnnouncementSummaryBatchResponse>(
    `/companies/${companyId}/announcements/summarize-all-deep${queryString ? `?${queryString}` : ""}`,
    {
      method: "POST",
      signal: params.signal
    }
  );
}

export async function getCompanyEvidence(
  companyId: number,
  params: { limit?: number; offset?: number; signal?: AbortSignal } = {}
): Promise<EvidenceListResponse> {
  const queryString = buildPaginationQuery(params);
  return fetchJson<EvidenceListResponse>(`/companies/${companyId}/evidence${queryString}`, {
    signal: params.signal
  });
}

export async function searchCompanyEvidence(
  companyId: number,
  params: { keywords?: string[]; max_results?: number; signal?: AbortSignal } = {}
): Promise<EvidenceSearchResponse> {
  const body: { keywords: string[]; max_results?: number } = {
    keywords: params.keywords ?? []
  };
  if (typeof params.max_results === "number") {
    body.max_results = params.max_results;
  }
  return fetchJson<EvidenceSearchResponse>(`/companies/${companyId}/evidence/search`, {
    method: "POST",
    body,
    signal: params.signal
  });
}

export async function importTextEvidence(
  companyId: number,
  payload: EvidenceImportTextRequest,
  signal?: AbortSignal
): Promise<EvidenceImportTextResponse> {
  return fetchJson<EvidenceImportTextResponse>(`/companies/${companyId}/evidence/import-text`, {
    method: "POST",
    body: payload,
    signal
  });
}

export async function deleteEvidence(
  evidenceId: number,
  signal?: AbortSignal
): Promise<EvidenceDeleteResponse> {
  return fetchJson<EvidenceDeleteResponse>(`/evidence/${evidenceId}`, {
    method: "DELETE",
    signal
  });
}

export async function getAnalystProfiles(
  signal?: AbortSignal
): Promise<AnalystProfileListResponse> {
  return fetchJson<AnalystProfileListResponse>("/analyst-profiles", { signal });
}

export async function getCompanyAnalysisRuns(
  companyId: number,
  params: {
    run_type?: string;
    analyst_profile?: string;
    status?: string;
    limit?: number;
    offset?: number;
    signal?: AbortSignal;
  } = {}
): Promise<AnalysisRunListResponse> {
  const searchParams = new URLSearchParams();

  if (params.run_type) {
    searchParams.set("run_type", params.run_type);
  }
  if (params.analyst_profile) {
    searchParams.set("analyst_profile", params.analyst_profile);
  }
  if (params.status) {
    searchParams.set("status", params.status);
  }
  if (typeof params.limit === "number") {
    searchParams.set("limit", String(params.limit));
  }
  if (typeof params.offset === "number") {
    searchParams.set("offset", String(params.offset));
  }

  const queryString = searchParams.toString();
  return fetchJson<AnalysisRunListResponse>(
    `/companies/${companyId}/analysis/runs${queryString ? `?${queryString}` : ""}`,
    {
      signal: params.signal
    }
  );
}

export async function getLatestCompanyAnalysisRuns(
  companyId: number,
  params: {
    run_type?: string;
    analyst_profile?: string;
    status?: string;
    signal?: AbortSignal;
  } = {}
): Promise<AnalysisLatestRunsResponse> {
  const searchParams = new URLSearchParams();

  if (params.run_type) {
    searchParams.set("run_type", params.run_type);
  }
  if (params.analyst_profile) {
    searchParams.set("analyst_profile", params.analyst_profile);
  }
  if (params.status) {
    searchParams.set("status", params.status);
  }

  const queryString = searchParams.toString();
  return fetchJson<AnalysisLatestRunsResponse>(
    `/companies/${companyId}/analysis/runs/latest${queryString ? `?${queryString}` : ""}`,
    {
      signal: params.signal
    }
  );
}

export async function runCompanyAnalysis(
  companyId: number,
  params: { analyst_profile: string; user_note?: string | null; signal?: AbortSignal }
): Promise<AnalysisRun> {
  return fetchJson<AnalysisRun>(`/companies/${companyId}/analysis/runs`, {
    method: "POST",
    body: {
      analyst_profile: params.analyst_profile,
      user_note: params.user_note ?? null
    },
    signal: params.signal
  });
}

export async function runCompanyAnalysisBatch(
  companyId: number,
  params: { analyst_profiles?: string[]; user_note?: string | null; signal?: AbortSignal } = {}
): Promise<AnalysisBatchRunResponse> {
  return fetchJson<AnalysisBatchRunResponse>(`/companies/${companyId}/analysis/runs/batch`, {
    method: "POST",
    body: {
      analyst_profiles: params.analyst_profiles ?? [],
      user_note: params.user_note ?? null
    },
    signal: params.signal
  });
}

export async function deleteCompanyAnalysisRun(
  companyId: number,
  runId: number,
  signal?: AbortSignal
): Promise<AnalysisRunDeleteResponse> {
  return fetchJson<AnalysisRunDeleteResponse>(`/companies/${companyId}/analysis/runs/${runId}`, {
    method: "DELETE",
    signal
  });
}

export async function updateAnalysisRunRuleStatus(
  companyId: number,
  runId: number,
  ruleId: string,
  status: AnalystRuleStatus,
  signal?: AbortSignal
): Promise<AnalysisRun> {
  return fetchJson<AnalysisRun>(
    `/companies/${companyId}/analysis/runs/${runId}/rule-checks/${encodeURIComponent(ruleId)}`,
    {
      method: "PATCH",
      body: { status },
      signal
    }
  );
}

export async function getLatestInvestmentMemo(
  companyId: number,
  signal?: AbortSignal
): Promise<InvestmentMemoLatestResponse> {
  return fetchJson<InvestmentMemoLatestResponse>(
    `/companies/${companyId}/investment-memos/latest`,
    { signal }
  );
}

export async function getInvestmentMemos(
  companyId: number,
  params: {
    limit?: number;
    offset?: number;
    include_deleted?: boolean;
    signal?: AbortSignal;
  } = {}
): Promise<InvestmentMemoListResponse> {
  const searchParams = new URLSearchParams();

  if (typeof params.limit === "number") {
    searchParams.set("limit", String(params.limit));
  }
  if (typeof params.offset === "number") {
    searchParams.set("offset", String(params.offset));
  }
  if (typeof params.include_deleted === "boolean") {
    searchParams.set("include_deleted", String(params.include_deleted));
  }

  const queryString = searchParams.toString();
  return fetchJson<InvestmentMemoListResponse>(
    `/companies/${companyId}/investment-memos${queryString ? `?${queryString}` : ""}`,
    { signal: params.signal }
  );
}

export async function getInvestmentMemo(
  memoId: number,
  signal?: AbortSignal
): Promise<InvestmentMemo> {
  return fetchJson<InvestmentMemo>(`/investment-memos/${memoId}`, { signal });
}

export async function generateInvestmentMemo(
  companyId: number,
  params: { user_note?: string | null; signal?: AbortSignal } = {}
): Promise<InvestmentMemoGenerateResponse> {
  return fetchJson<InvestmentMemoGenerateResponse>(
    `/companies/${companyId}/investment-memos/generate`,
    {
      method: "POST",
      body: {
        user_note: params.user_note ?? null
      },
      signal: params.signal
    }
  );
}

export async function archiveInvestmentMemo(
  memoId: number,
  signal?: AbortSignal
): Promise<InvestmentMemoArchiveResponse> {
  return fetchJson<InvestmentMemoArchiveResponse>(`/investment-memos/${memoId}/archive`, {
    method: "POST",
    signal
  });
}

export async function deleteInvestmentMemo(
  memoId: number,
  signal?: AbortSignal
): Promise<InvestmentMemoDeleteResponse> {
  return fetchJson<InvestmentMemoDeleteResponse>(`/investment-memos/${memoId}`, {
    method: "DELETE",
    signal
  });
}

export async function getLatestValuationRun(
  companyId: number,
  signal?: AbortSignal
): Promise<ValuationRunLatestResponse> {
  return fetchJson<ValuationRunLatestResponse>(
    `/companies/${companyId}/valuation-runs/latest`,
    { signal }
  );
}

export async function getValuationRuns(
  companyId: number,
  params: { limit?: number; offset?: number; signal?: AbortSignal } = {}
): Promise<ValuationRunListResponse> {
  const queryString = buildPaginationQuery(params);
  return fetchJson<ValuationRunListResponse>(
    `/companies/${companyId}/valuation-runs${queryString}`,
    { signal: params.signal }
  );
}

export async function createValuationDraft(
  companyId: number,
  params: { assumptions?: Record<string, unknown>; user_note?: string | null; signal?: AbortSignal } = {}
): Promise<ValuationRunMutationResponse> {
  return fetchJson<ValuationRunMutationResponse>(
    `/companies/${companyId}/valuation-runs/draft`,
    {
      method: "POST",
      body: {
        assumptions: params.assumptions ?? null,
        user_note: params.user_note ?? null
      },
      signal: params.signal
    }
  );
}

export async function recalculateValuationRun(
  runId: number,
  params: { assumptions: Record<string, unknown>; user_note?: string | null; signal?: AbortSignal }
): Promise<ValuationRunMutationResponse> {
  return fetchJson<ValuationRunMutationResponse>(`/valuation-runs/${runId}/recalculate`, {
    method: "POST",
    body: {
      assumptions: params.assumptions,
      user_note: params.user_note ?? null
    },
    signal: params.signal
  });
}

export async function getLatestPriceDecisionRun(
  companyId: number,
  signal?: AbortSignal
): Promise<PriceDecisionLatestResponse> {
  return fetchJson<PriceDecisionLatestResponse>(
    `/companies/${companyId}/price-decision-runs/latest`,
    { signal }
  );
}

export async function getPriceDecisionRuns(
  companyId: number,
  params: { limit?: number; offset?: number; signal?: AbortSignal } = {}
): Promise<PriceDecisionListResponse> {
  const queryString = buildPaginationQuery(params);
  return fetchJson<PriceDecisionListResponse>(
    `/companies/${companyId}/price-decision-runs${queryString}`,
    { signal: params.signal }
  );
}

export async function createPriceDecisionRun(
  companyId: number,
  params: {
    valuation_run_id?: number | null;
    safety_margin_override?: number | null;
    listing_id?: number | null;
    signal?: AbortSignal;
  } = {}
): Promise<PriceDecisionMutationResponse> {
  return fetchJson<PriceDecisionMutationResponse>(
    `/companies/${companyId}/price-decision-runs`,
    {
      method: "POST",
      body: {
        valuation_run_id: params.valuation_run_id ?? null,
        safety_margin_override: params.safety_margin_override ?? null,
        listing_id: params.listing_id ?? null
      },
      signal: params.signal
    }
  );
}

export async function deletePriceDecisionRun(
  runId: number,
  signal?: AbortSignal
): Promise<PriceDecisionDeleteResponse> {
  return fetchJson<PriceDecisionDeleteResponse>(`/price-decision-runs/${runId}`, {
    method: "DELETE",
    signal
  });
}

export async function getCurrentParameterConfig(
  signal?: AbortSignal
): Promise<ParameterConfigCurrentResponse> {
  return fetchJson<ParameterConfigCurrentResponse>("/parameter-config/current", { signal });
}

export async function getDefaultParameterConfig(
  signal?: AbortSignal
): Promise<ParameterConfigCurrentResponse> {
  return fetchJson<ParameterConfigCurrentResponse>("/parameter-config/defaults", { signal });
}

export async function validateParameterConfig(
  configJson: Record<string, unknown>
): Promise<ParameterValidationResult> {
  return fetchJson<ParameterValidationResult>("/parameter-config/validate", {
    method: "POST",
    body: { config_json: configJson }
  });
}

export async function publishParameterConfig(
  configJson: Record<string, unknown>,
  warningsAcknowledged: boolean
): Promise<ParameterConfigPublishResponse> {
  return fetchJson<ParameterConfigPublishResponse>("/parameter-config/current", {
    method: "PUT",
    body: { config_json: configJson, warnings_acknowledged: warningsAcknowledged }
  });
}

export async function getDataManagementSummary(
  signal?: AbortSignal
): Promise<DataManagementSummary> {
  return fetchJson<DataManagementSummary>("/data-management/summary", { signal });
}

export async function previewDataOperation(
  operationType: DataOperationType,
  parameters: DataOperationParameters = {},
  signal?: AbortSignal
): Promise<DataOperationPreview> {
  return fetchJson<DataOperationPreview>("/data-management/operations/preview", {
    method: "POST",
    body: { operation_type: operationType, parameters },
    signal
  });
}

export async function executeDataOperation(
  operationToken: string,
  confirmationPhrase: string,
  signal?: AbortSignal
): Promise<DataOperationResult> {
  return fetchJson<DataOperationResult>("/data-management/operations/execute", {
    method: "POST",
    body: { operation_token: operationToken, confirmation_phrase: confirmationPhrase },
    signal
  });
}

export async function getBackups(signal?: AbortSignal): Promise<BackupListResponse> {
  return fetchJson<BackupListResponse>("/data-management/backups", { signal });
}

export async function createBackup(
  reason = "manual",
  signal?: AbortSignal
): Promise<BackupManifest> {
  return fetchJson<BackupManifest>("/data-management/backups", {
    method: "POST",
    body: { reason },
    signal
  });
}

export async function verifyBackup(
  backupId: string,
  signal?: AbortSignal
): Promise<BackupVerifyResponse> {
  return fetchJson<BackupVerifyResponse>(
    `/data-management/backups/${encodeURIComponent(backupId)}/verify`,
    { method: "POST", signal }
  );
}

export async function previewBackupRestore(
  backupId: string,
  signal?: AbortSignal
): Promise<DataOperationPreview> {
  return fetchJson<DataOperationPreview>(
    `/data-management/backups/${encodeURIComponent(backupId)}/restore/preview`,
    { method: "POST", signal }
  );
}

export async function deleteBackup(
  backupId: string,
  operationToken: string,
  confirmationPhrase: string,
  signal?: AbortSignal
): Promise<DataOperationResult> {
  return fetchJson<DataOperationResult>(
    `/data-management/backups/${encodeURIComponent(backupId)}`,
    {
      method: "DELETE",
      body: { operation_token: operationToken, confirmation_phrase: confirmationPhrase },
      signal
    }
  );
}

export async function getAutomaticBackupSettings(
  signal?: AbortSignal
): Promise<AutomaticBackupSettings> {
  return fetchJson<AutomaticBackupSettings>("/data-management/settings", { signal });
}

export async function updateAutomaticBackupSettings(
  settings: Pick<AutomaticBackupSettings, "enabled" | "interval_hours" | "max_backups">,
  signal?: AbortSignal
): Promise<AutomaticBackupSettings> {
  return fetchJson<AutomaticBackupSettings>("/data-management/settings", {
    method: "PUT",
    body: settings,
    signal
  });
}

export async function getPortfolioOwners(signal?: AbortSignal): Promise<PortfolioOwnerListResponse> {
  return fetchJson<PortfolioOwnerListResponse>("/investment-tools/portfolio-owners", { signal });
}

export async function createPortfolioOwner(
  payload: { name: string; owner_type: PortfolioOwnerType; notes?: string | null },
  signal?: AbortSignal
): Promise<PortfolioOwner> {
  return fetchJson<PortfolioOwner>("/investment-tools/portfolio-owners", {
    method: "POST",
    body: payload,
    signal
  });
}

export async function updatePortfolioOwner(
  ownerId: number,
  payload: Partial<{ name: string; owner_type: PortfolioOwnerType; notes: string | null }>,
  signal?: AbortSignal
): Promise<PortfolioOwner> {
  return fetchJson<PortfolioOwner>(`/investment-tools/portfolio-owners/${ownerId}`, {
    method: "PATCH",
    body: payload,
    signal
  });
}

export async function deletePortfolioOwner(
  ownerId: number,
  signal?: AbortSignal
): Promise<{ id: number; deleted: boolean }> {
  return fetchJson(`/investment-tools/portfolio-owners/${ownerId}`, {
    method: "DELETE",
    signal
  });
}

export async function reorderPortfolioOwners(
  orderedIds: number[],
  signal?: AbortSignal
): Promise<PortfolioOwnerListResponse> {
  return fetchJson<PortfolioOwnerListResponse>("/investment-tools/portfolio-owners/reorder", {
    method: "PUT",
    body: { ordered_ids: orderedIds },
    signal
  });
}

export async function getPortfolioSnapshots(
  ownerId: number,
  signal?: AbortSignal
): Promise<PortfolioSnapshotListResponse> {
  return fetchJson<PortfolioSnapshotListResponse>(
    `/investment-tools/portfolio-owners/${ownerId}/snapshots`,
    { signal }
  );
}

export async function createPortfolioSnapshot(
  ownerId: number,
  payload: {
    title: string;
    as_of_date: string;
    base_currency: PortfolioCurrency;
    notes?: string | null;
    copy_from_snapshot_id?: number | null;
  },
  signal?: AbortSignal
): Promise<PortfolioSnapshot> {
  return fetchJson<PortfolioSnapshot>(
    `/investment-tools/portfolio-owners/${ownerId}/snapshots`,
    { method: "POST", body: payload, signal }
  );
}

export async function updatePortfolioSnapshot(
  snapshotId: number,
  payload: Partial<{
    title: string;
    as_of_date: string;
    base_currency: PortfolioCurrency;
    notes: string | null;
  }>,
  signal?: AbortSignal
): Promise<PortfolioSnapshot> {
  return fetchJson<PortfolioSnapshot>(`/investment-tools/portfolio-snapshots/${snapshotId}`, {
    method: "PATCH",
    body: payload,
    signal
  });
}

export async function deletePortfolioSnapshot(
  snapshotId: number,
  signal?: AbortSignal
): Promise<{ id: number; deleted: boolean }> {
  return fetchJson(`/investment-tools/portfolio-snapshots/${snapshotId}`, {
    method: "DELETE",
    signal
  });
}

export async function reorderPortfolioSnapshots(
  ownerId: number,
  orderedIds: number[],
  signal?: AbortSignal
): Promise<PortfolioSnapshotListResponse> {
  return fetchJson<PortfolioSnapshotListResponse>(
    `/investment-tools/portfolio-owners/${ownerId}/snapshots/reorder`,
    { method: "PUT", body: { ordered_ids: orderedIds }, signal }
  );
}

export async function searchPortfolioListings(
  query: string,
  signal?: AbortSignal
): Promise<PortfolioListingSearchResponse> {
  const searchParams = new URLSearchParams({ q: query, limit: "20" });
  return fetchJson<PortfolioListingSearchResponse>(
    `/investment-tools/portfolio-listings/search?${searchParams.toString()}`,
    { signal }
  );
}

export async function searchSecUsListingCatalog(
  query: string,
  signal?: AbortSignal
): Promise<SecUsListingCatalogResponse> {
  const searchParams = new URLSearchParams({ q: query, limit: "20" });
  return fetchJson<SecUsListingCatalogResponse>(
    `/investment-tools/portfolio-listings/us-catalog/search?${searchParams.toString()}`,
    { signal }
  );
}

export async function searchAhListingCatalog(
  query: string,
  signal?: AbortSignal
): Promise<AhListingCatalogResponse> {
  const searchParams = new URLSearchParams({ q: query, limit: "20" });
  return fetchJson<AhListingCatalogResponse>(
    `/investment-tools/portfolio-listings/ah-catalog/search?${searchParams.toString()}`,
    { signal }
  );
}

export async function importAhListing(
  payload: { quote_id: string },
  signal?: AbortSignal
): Promise<PortfolioListingSearchItem> {
  return fetchJson<PortfolioListingSearchItem>(
    "/investment-tools/portfolio-listings/ah-catalog/import",
    { method: "POST", body: payload, signal }
  );
}

export async function importSecUsListing(
  payload: { cik: string; symbol: string },
  signal?: AbortSignal
): Promise<PortfolioListingSearchItem> {
  return fetchJson<PortfolioListingSearchItem>(
    "/investment-tools/portfolio-listings/us-catalog/import",
    { method: "POST", body: payload, signal }
  );
}

export async function getBuyMemoEntries(
  signal?: AbortSignal
): Promise<{ items: BuyMemoEntry[]; total: number }> {
  return fetchJson<{ items: BuyMemoEntry[]; total: number }>(
    "/investment-tools/buy-memo-entries",
    { signal }
  );
}

export async function searchBuyMemoCompanies(
  query = "",
  signal?: AbortSignal
): Promise<{ items: BuyMemoCompanyCandidate[]; total: number }> {
  const searchParams = new URLSearchParams({ q: query, limit: "100" });
  return fetchJson<{ items: BuyMemoCompanyCandidate[]; total: number }>(
    `/investment-tools/buy-memo-companies?${searchParams.toString()}`,
    { signal }
  );
}

export async function getBuyMemoDecisions(
  companyId: number,
  signal?: AbortSignal
): Promise<{ company_id: number; items: BuyMemoDecisionCandidate[]; total: number }> {
  return fetchJson<{ company_id: number; items: BuyMemoDecisionCandidate[]; total: number }>(
    `/investment-tools/buy-memo-companies/${companyId}/price-decisions`,
    { signal }
  );
}

export async function createBuyMemoEntry(
  priceDecisionRunId: number,
  signal?: AbortSignal
): Promise<BuyMemoEntry> {
  return fetchJson<BuyMemoEntry>("/investment-tools/buy-memo-entries", {
    method: "POST",
    body: { price_decision_run_id: priceDecisionRunId },
    signal
  });
}

export async function deleteBuyMemoEntry(
  entryId: number,
  signal?: AbortSignal
): Promise<{ id: number; deleted: boolean }> {
  return fetchJson<{ id: number; deleted: boolean }>(`/investment-tools/buy-memo-entries/${entryId}`, {
    method: "DELETE",
    signal
  });
}

export async function getPortfolioHoldings(
  snapshotId: number,
  signal?: AbortSignal
): Promise<PortfolioHoldingListResponse> {
  return fetchJson<PortfolioHoldingListResponse>(
    `/investment-tools/portfolio-snapshots/${snapshotId}/holdings`,
    { signal }
  );
}

export async function createPortfolioHolding(
  snapshotId: number,
  payload: { listing_id: number; quantity: string; notes?: string | null; display_order?: number },
  signal?: AbortSignal
): Promise<PortfolioHolding> {
  return fetchJson<PortfolioHolding>(
    `/investment-tools/portfolio-snapshots/${snapshotId}/holdings`,
    { method: "POST", body: payload, signal }
  );
}

export async function updatePortfolioHolding(
  holdingId: number,
  payload: Partial<{
    listing_id: number;
    quantity: string;
    notes: string | null;
    display_order: number;
  }>,
  signal?: AbortSignal
): Promise<PortfolioHolding> {
  return fetchJson<PortfolioHolding>(`/investment-tools/portfolio-holdings/${holdingId}`, {
    method: "PATCH",
    body: payload,
    signal
  });
}

export async function deletePortfolioHolding(
  holdingId: number,
  signal?: AbortSignal
): Promise<{ id: number; deleted: boolean }> {
  return fetchJson(`/investment-tools/portfolio-holdings/${holdingId}`, {
    method: "DELETE",
    signal
  });
}

export async function getPortfolioValuation(
  snapshotId: number,
  signal?: AbortSignal
): Promise<PortfolioValuation> {
  return fetchJson<PortfolioValuation>(
    `/investment-tools/portfolio-snapshots/${snapshotId}/valuation`,
    { signal }
  );
}

export async function refreshPortfolioQuotes(
  snapshotId: number,
  signal?: AbortSignal
): Promise<PortfolioRefreshResult> {
  return fetchJson<PortfolioRefreshResult>(
    `/investment-tools/portfolio-snapshots/${snapshotId}/refresh-quotes`,
    { method: "POST", signal }
  );
}

export async function getMarketFear(signal?: AbortSignal): Promise<MarketFearResponse> {
  return fetchJson<MarketFearResponse>("/investment-tools/market-fear", { signal });
}

export async function refreshMarketFear(
  market?: MarketFearIndicator["market"],
  signal?: AbortSignal
): Promise<MarketFearResponse> {
  const query = market ? `?market=${market}` : "";
  return fetchJson<MarketFearResponse>(`/investment-tools/market-fear/refresh${query}`, {
    method: "POST",
    signal
  });
}

function buildPaginationQuery(params: { limit?: number; offset?: number }): string {
  const searchParams = new URLSearchParams();

  if (typeof params.limit === "number") {
    searchParams.set("limit", String(params.limit));
  }
  if (typeof params.offset === "number") {
    searchParams.set("offset", String(params.offset));
  }

  const queryString = searchParams.toString();
  return queryString ? `?${queryString}` : "";
}

function buildFinancialStatementQuery(params: {
  limit?: number;
  offset?: number;
  period_limit?: number;
  period_offset?: number;
}): string {
  const searchParams = new URLSearchParams();

  if (typeof params.period_limit === "number") {
    searchParams.set("period_limit", String(params.period_limit));
  }
  if (typeof params.period_offset === "number") {
    searchParams.set("period_offset", String(params.period_offset));
  }
  if (typeof params.limit === "number") {
    searchParams.set("limit", String(params.limit));
  }
  if (typeof params.offset === "number") {
    searchParams.set("offset", String(params.offset));
  }

  const queryString = searchParams.toString();
  return queryString ? `?${queryString}` : "";
}
