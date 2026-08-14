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
  created_at: string;
};

export type FinancialStatementListResponse = {
  items: FinancialStatement[];
  total: number;
  limit: number;
  offset: number;
};

export type FinancialEvidencePack = {
  latest_period: string | null;
  periods: string[];
  financial_facts: Record<string, unknown>;
  financial_metrics: Record<string, unknown>;
  financial_trends: Record<string, unknown>;
  financial_flags: Array<Record<string, unknown>>;
  financial_data_gaps: string[];
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
  title: string;
  published_at: string;
  category: string;
  content: string | null;
  raw_content: string | null;
  summary: string | null;
  source: string | null;
  source_url: string | null;
  raw_url: string | null;
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
};

export type AnalystProfile = {
  id: string;
  name: string;
  display_name: string;
  description: string;
  philosophy: string;
  rules: AnalystRule[];
  prompt_focus: string[];
};

export type AnalystProfileListResponse = {
  items: AnalystProfile[];
};

export type AnalystRuleCheck = {
  rule_id: string;
  status: "pass" | "warn" | "fail" | "unknown";
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

type RequestJsonOptions = {
  signal?: AbortSignal;
  method?: "GET" | "POST" | "DELETE";
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
  params: { limit?: number; offset?: number; signal?: AbortSignal } = {}
): Promise<FinancialStatementListResponse> {
  const queryString = buildPaginationQuery(params);
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
  params: { limit?: number; signal?: AbortSignal } = {}
): Promise<FinancialStatementSyncResponse> {
  const searchParams = new URLSearchParams();

  if (typeof params.limit === "number") {
    searchParams.set("limit", String(params.limit));
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
  params: { years?: number; signal?: AbortSignal } = {}
): Promise<AnnouncementSyncResponse> {
  const searchParams = new URLSearchParams();

  if (typeof params.years === "number") {
    searchParams.set("years", String(params.years));
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
  return fetchJson<EvidenceSearchResponse>(`/companies/${companyId}/evidence/search`, {
    method: "POST",
    body: {
      keywords: params.keywords ?? [],
      max_results: params.max_results ?? 5
    },
    signal: params.signal
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
