from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_serializer,
    field_validator,
    model_validator,
)

DISPLAY_TIME_ZONE = timezone(timedelta(hours=8), "Asia/Shanghai")
MemoSignal = Literal["positive", "neutral", "negative", "unknown"]
MemoDirection = Literal["up", "down", "neutral", "widen", "narrow", "cap"]
MemoMagnitude = Literal["low", "medium", "high"]
MemoScenario = Literal["conservative", "base", "optimistic", "all"]
MemoValuationMethod = Literal[
    "dcf",
    "owner_earnings",
    "residual_income",
    "dividend_discount",
    "asset_value",
]
ResearchConclusion = Literal["优质", "普通", "存疑", "回避", "需复核"]


class MemoSourceRefs(BaseModel):
    analyst_run_ids: list[int] = Field(default_factory=list)
    evidence_ids: list[int] = Field(default_factory=list)
    announcement_ids: list[int] = Field(default_factory=list)
    financial_periods: list[str] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def normalize_source_aliases(cls, value):
        if not isinstance(value, dict):
            return value
        normalized = dict(value)
        _copy_first_present(normalized, "analyst_run_ids", "source_run_ids", "run_ids")
        return normalized

    @field_validator("analyst_run_ids", "evidence_ids", "announcement_ids", mode="before")
    @classmethod
    def normalize_int_refs(cls, value):
        return _normalize_int_list(value)

    @field_validator("financial_periods", mode="before")
    @classmethod
    def normalize_period_refs(cls, value):
        return _normalize_str_list(value)


class MemoConsensusPoint(BaseModel):
    topic: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    supporting_profiles: list[str] = Field(default_factory=list)
    source_run_ids: list[int] = Field(default_factory=list)
    evidence_ids: list[int] = Field(default_factory=list)
    announcement_ids: list[int] = Field(default_factory=list)
    financial_periods: list[str] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def normalize_point_aliases(cls, value):
        if not isinstance(value, dict):
            return value
        normalized = dict(value)
        _copy_first_present(
            normalized,
            "summary",
            "assessment",
            "reasoning",
            "conclusion",
            "description",
            "point",
        )
        _copy_first_present(normalized, "supporting_profiles", "profiles", "analysts")
        source_refs = normalized.get("source_refs")
        if isinstance(source_refs, dict):
            _copy_first_present(normalized, "source_run_ids", "analyst_run_ids")
            for field_name in (
                "source_run_ids",
                "evidence_ids",
                "announcement_ids",
                "financial_periods",
            ):
                if field_name not in normalized and field_name in source_refs:
                    normalized[field_name] = source_refs[field_name]
            if "source_run_ids" not in normalized and "analyst_run_ids" in source_refs:
                normalized["source_run_ids"] = source_refs["analyst_run_ids"]
        if "topic" not in normalized and "title" in normalized:
            normalized["topic"] = normalized["title"]
        return normalized

    @field_validator("topic", "summary")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("字段不能为空")
        return normalized

    @field_validator("supporting_profiles", "financial_periods", mode="before")
    @classmethod
    def normalize_strings(cls, value):
        return _normalize_str_list(value)

    @field_validator("source_run_ids", "evidence_ids", "announcement_ids", mode="before")
    @classmethod
    def normalize_ids(cls, value):
        return _normalize_int_list(value)


class MemoDissentPoint(BaseModel):
    topic: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    profile_positions: list[dict[str, object]] = Field(default_factory=list)
    why_it_matters: str = ""

    @model_validator(mode="before")
    @classmethod
    def normalize_point_aliases(cls, value):
        if not isinstance(value, dict):
            return value
        normalized = dict(value)
        _copy_first_present(
            normalized,
            "summary",
            "assessment",
            "reasoning",
            "conclusion",
            "description",
            "point",
        )
        _copy_first_present(normalized, "why_it_matters", "importance", "impact")
        if "topic" not in normalized and "title" in normalized:
            normalized["topic"] = normalized["title"]
        return normalized

    @field_validator("topic", "summary", "why_it_matters")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return value.strip()


class MemoValuationAssumption(BaseModel):
    assumption_type: str = Field(min_length=1)
    scenario_bias: str = "review_only"
    reason: str = Field(min_length=1)
    suggested_range: dict[str, object] = Field(default_factory=dict)
    needed_inputs: list[str] = Field(default_factory=list)
    risk_adjustments: list[str] = Field(default_factory=list)
    source_refs: MemoSourceRefs = Field(default_factory=MemoSourceRefs)

    @model_validator(mode="before")
    @classmethod
    def normalize_assumption_aliases(cls, value):
        if not isinstance(value, dict):
            return value
        normalized = dict(value)
        _copy_first_present(normalized, "assumption_type", "type", "name", "metric", "item")
        _copy_first_present(
            normalized,
            "reason",
            "rationale",
            "summary",
            "description",
            "why_it_matters",
        )
        _copy_first_present(normalized, "needed_inputs", "inputs", "required_inputs", "data_needed")
        _copy_first_present(
            normalized,
            "risk_adjustments",
            "risks",
            "risk_adjustment",
            "sensitivity",
        )
        _copy_first_present(normalized, "source_refs", "sources", "source_map")
        if "assumption_type" not in normalized and "reason" in normalized:
            normalized["assumption_type"] = "review_assumption"
        if "reason" not in normalized and "assumption_type" in normalized:
            normalized["reason"] = str(normalized["assumption_type"])
        return normalized

    @field_validator("assumption_type", "scenario_bias", "reason")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("字段不能为空")
        return normalized

    @field_validator("needed_inputs", "risk_adjustments", mode="before")
    @classmethod
    def normalize_strings(cls, value):
        return _normalize_str_list(value)


class MemoConfidenceSummary(BaseModel):
    level: Literal["low", "medium", "high"] = "medium"
    reasons: list[str] = Field(default_factory=list)

    @field_validator("reasons", mode="before")
    @classmethod
    def normalize_reasons(cls, value):
        return _normalize_str_list(value)


class MemoAnalystRuleScore(BaseModel):
    rule_id: str
    rule_label: str
    status: Literal["pass", "warn", "fail", "unknown"]
    score: float


class MemoAnalystScoreItem(BaseModel):
    profile_id: str
    profile_name: str
    availability: Literal["success", "missing"]
    source_run_id: int | None = None
    profile_fit_score: float | None = None
    data_confidence: float | None = None
    raw_weight: float | None = None
    base_weight: float | None = None
    differentiated_raw_weight: float | None = None
    analyst_weight: float = 0.0
    rule_score_total: float = 0.0
    weighted_score: float = 0.0
    rule_scores: list[MemoAnalystRuleScore] = Field(default_factory=list)


class MemoAnalystScorecard(BaseModel):
    source: str = "latest_successful_008_rule_checks"
    independent_from_valuation: bool = True
    status_score_policy: dict[str, float] = Field(default_factory=dict)
    weight_policy: dict[str, object] = Field(default_factory=dict)
    coverage: dict[str, int] = Field(default_factory=dict)
    analyst_items: list[MemoAnalystScoreItem] = Field(default_factory=list)
    total_score: float = 0.0
    score_range: dict[str, float] = Field(default_factory=dict)
    suggested_safety_margin: float | None = Field(default=None, ge=0.0, le=0.5)
    safety_margin_policy: dict[str, object] = Field(default_factory=dict)


class MemoValuationMethodPreference(BaseModel):
    method: MemoValuationMethod
    direction: Literal["up", "down", "neutral"] = "neutral"
    reason: str = ""
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)

    @model_validator(mode="before")
    @classmethod
    def normalize_method_aliases(cls, value):
        if isinstance(value, str):
            normalized_value = value.strip()
            return {"method": normalized_value, "reason": normalized_value}
        if not isinstance(value, dict):
            return value
        normalized = dict(value)
        _copy_first_present(normalized, "method", "valuation_method", "name", "type")
        _copy_first_present(normalized, "reason", "rationale", "summary", "description")
        return normalized

    @field_validator("reason")
    @classmethod
    def strip_reason(cls, value: str) -> str:
        return value.strip()

    @field_validator("method", mode="before")
    @classmethod
    def normalize_method_value(cls, value):
        return _normalize_method_value(value)

    @field_validator("direction", mode="before")
    @classmethod
    def normalize_method_direction(cls, value):
        direction = _normalize_direction_value(value)
        if direction in {"up", "down", "neutral"}:
            return direction
        return "neutral"

    @field_validator("confidence", mode="before")
    @classmethod
    def normalize_confidence(cls, value):
        return _normalize_score_value(value, default=0.0)


class MemoParameterImpact(BaseModel):
    parameter: str = Field(min_length=1)
    direction: MemoDirection = "neutral"
    magnitude: MemoMagnitude = "low"
    scenario: MemoScenario = "all"
    reason: str = ""
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    requires_user_review: bool = True
    source_refs: MemoSourceRefs = Field(default_factory=MemoSourceRefs)

    @model_validator(mode="before")
    @classmethod
    def normalize_impact_aliases(cls, value):
        if isinstance(value, str):
            normalized_value = value.strip()
            return {"parameter": "review_parameter", "reason": normalized_value}
        if not isinstance(value, dict):
            return value
        normalized = dict(value)
        _copy_first_present(normalized, "parameter", "name", "metric", "assumption_type")
        _copy_first_present(normalized, "reason", "rationale", "summary", "description")
        _copy_first_present(normalized, "source_refs", "sources", "source_map")
        _copy_first_present(
            normalized,
            "requires_user_review",
            "user_confirmation_required",
            "needs_review",
        )
        if "parameter" not in normalized and "reason" in normalized:
            normalized["parameter"] = "review_parameter"
        return normalized

    @field_validator("parameter")
    @classmethod
    def strip_parameter(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("parameter cannot be empty")
        return normalized

    @field_validator("reason")
    @classmethod
    def strip_impact_reason(cls, value: str) -> str:
        return value.strip()

    @field_validator("direction", mode="before")
    @classmethod
    def normalize_direction(cls, value):
        return _normalize_direction_value(value)

    @field_validator("magnitude", mode="before")
    @classmethod
    def normalize_magnitude(cls, value):
        return _normalize_magnitude_value(value)

    @field_validator("scenario", mode="before")
    @classmethod
    def normalize_scenario(cls, value):
        return _normalize_scenario_value(value)

    @field_validator("confidence", mode="before")
    @classmethod
    def normalize_confidence(cls, value):
        return _normalize_score_value(value, default=0.0)

    @field_validator("requires_user_review", mode="before")
    @classmethod
    def force_user_review(cls, value):
        return True


class MemoAnalystValuationSignal(BaseModel):
    profile_id: str = Field(min_length=1)
    profile_name: str = ""
    source_run_id: int | None = None
    profile_fit_score: float | None = Field(default=None, ge=0.0, le=1.0)
    data_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    business_quality_signal: MemoSignal = "unknown"
    moat_durability_signal: MemoSignal = "unknown"
    growth_runway_signal: MemoSignal = "unknown"
    pricing_power_signal: MemoSignal = "unknown"
    capital_intensity_signal: MemoSignal = "unknown"
    cash_flow_reliability_signal: MemoSignal = "unknown"
    balance_sheet_risk_signal: MemoSignal = "unknown"
    management_capital_allocation_signal: MemoSignal = "unknown"
    cyclicality_signal: MemoSignal = "unknown"
    permanent_loss_risk_signal: MemoSignal = "unknown"
    valuation_method_preference: list[MemoValuationMethodPreference] = Field(default_factory=list)
    parameter_impacts: list[MemoParameterImpact] = Field(default_factory=list)
    source_refs: MemoSourceRefs = Field(default_factory=MemoSourceRefs)

    @model_validator(mode="before")
    @classmethod
    def normalize_signal_aliases(cls, value):
        if not isinstance(value, dict):
            return value
        normalized = dict(value)
        _copy_first_present(normalized, "profile_id", "analyst_profile", "profile")
        _copy_first_present(normalized, "profile_name", "analyst_name", "display_name")
        _copy_first_present(normalized, "source_run_id", "run_id", "analyst_run_id")
        _copy_first_present(normalized, "data_confidence", "confidence")
        _copy_first_present(normalized, "source_refs", "sources", "source_map")
        _copy_first_present(
            normalized,
            "valuation_method_preference",
            "method_preferences",
            "valuation_methods",
        )
        _copy_first_present(
            normalized,
            "parameter_impacts",
            "parameter_signals",
            "assumption_impacts",
        )
        return normalized

    @field_validator("profile_id", "profile_name")
    @classmethod
    def strip_profile_text(cls, value: str) -> str:
        return value.strip()

    @field_validator("profile_fit_score", "data_confidence", mode="before")
    @classmethod
    def normalize_optional_score(cls, value):
        return _normalize_score_value(value, default=None)

    @field_validator(
        "business_quality_signal",
        "moat_durability_signal",
        "growth_runway_signal",
        "pricing_power_signal",
        "capital_intensity_signal",
        "cash_flow_reliability_signal",
        "balance_sheet_risk_signal",
        "management_capital_allocation_signal",
        "cyclicality_signal",
        "permanent_loss_risk_signal",
        mode="before",
    )
    @classmethod
    def normalize_signal_value(cls, value):
        return _normalize_signal_value(value)

    @field_validator("valuation_method_preference", mode="before")
    @classmethod
    def normalize_method_preferences(cls, value):
        return _normalize_method_preference_list(value)

    @field_validator("parameter_impacts", mode="before")
    @classmethod
    def normalize_parameter_impacts(cls, value):
        return _normalize_parameter_impact_list(value)


class MemoValuationSignalPack(BaseModel):
    price_blind_compatible: bool = True
    source: Literal["latest_successful_analyst_view_runs"] = "latest_successful_analyst_view_runs"
    analyst_signals: list[MemoAnalystValuationSignal] = Field(default_factory=list)
    consensus_parameter_impacts: list[MemoParameterImpact] = Field(default_factory=list)
    dissent_parameter_impacts: list[MemoParameterImpact] = Field(default_factory=list)
    risk_constraints: list[str] = Field(default_factory=list)
    data_gaps_for_valuation: list[str] = Field(default_factory=list)
    user_confirmation_required: bool = True

    @model_validator(mode="before")
    @classmethod
    def normalize_pack_aliases(cls, value):
        if not isinstance(value, dict):
            return value
        normalized = dict(value)
        _copy_first_present(normalized, "analyst_signals", "analyst_valuation_matrix")
        _copy_first_present(
            normalized,
            "consensus_parameter_impacts",
            "consensus_impacts",
            "consensus_parameter_signals",
        )
        _copy_first_present(
            normalized,
            "dissent_parameter_impacts",
            "dissent_impacts",
            "dissent_parameter_signals",
        )
        _copy_first_present(normalized, "risk_constraints", "risks", "risk_adjustments")
        _copy_first_present(
            normalized,
            "data_gaps_for_valuation",
            "data_gaps",
            "valuation_data_gaps",
        )
        return normalized

    @field_validator("price_blind_compatible", "user_confirmation_required", mode="before")
    @classmethod
    def force_true(cls, value):
        return True

    @field_validator("risk_constraints", "data_gaps_for_valuation", mode="before")
    @classmethod
    def normalize_pack_strings(cls, value):
        return _normalize_str_list(value)

    @field_validator("consensus_parameter_impacts", "dissent_parameter_impacts", mode="before")
    @classmethod
    def normalize_pack_impacts(cls, value):
        return _normalize_parameter_impact_list(value)


class InvestmentMemoOutput(BaseModel):
    title: str = "综合投资备忘录"
    research_conclusion: ResearchConclusion = "需复核"
    executive_summary: str = Field(min_length=1)
    core_thesis: list[str] = Field(default_factory=list)
    consensus_points: list[MemoConsensusPoint] = Field(default_factory=list)
    dissent_points: list[MemoDissentPoint] = Field(default_factory=list)
    business_quality: list[str] = Field(default_factory=list)
    financial_quality: list[str] = Field(default_factory=list)
    management_and_capital_allocation: list[str] = Field(default_factory=list)
    moat_and_growth: list[str] = Field(default_factory=list)
    key_risks: list[str] = Field(default_factory=list)
    counter_evidence: list[str] = Field(default_factory=list)
    data_gaps: list[str] = Field(default_factory=list)
    follow_up_questions: list[str] = Field(default_factory=list)
    valuation_assumption_queue: list[MemoValuationAssumption] = Field(default_factory=list)
    analyst_scorecard: MemoAnalystScorecard = Field(default_factory=MemoAnalystScorecard)
    valuation_signal_pack: MemoValuationSignalPack = Field(default_factory=MemoValuationSignalPack)
    watch_signals: list[str] = Field(default_factory=list)
    price_decision_status: Literal["not_started"] = "not_started"
    prohibited_actions_note: str = (
        "本备忘录未生成买卖、持有、减仓、加仓或仓位建议，价格对照留给 011。"
    )
    source_map: MemoSourceRefs = Field(default_factory=MemoSourceRefs)
    confidence_summary: MemoConfidenceSummary = Field(default_factory=MemoConfidenceSummary)

    @model_validator(mode="before")
    @classmethod
    def normalize_output_aliases(cls, value):
        if not isinstance(value, dict):
            return value
        normalized = _unwrap_memo_payload(value)
        _copy_first_present(
            normalized,
            "executive_summary",
            "summary",
            "overall_summary",
            "research_summary",
            "memo_summary",
            "investment_summary",
            "conclusion_summary",
        )
        _copy_first_present(normalized, "core_thesis", "core_theses", "investment_thesis")
        _copy_first_present(normalized, "consensus_points", "consensus", "consensus_candidates")
        _copy_first_present(normalized, "dissent_points", "dissent", "dissent_candidates")
        _copy_first_present(normalized, "key_risks", "risks", "critical_risks")
        _copy_first_present(normalized, "counter_evidence", "contrary_evidence", "counterarguments")
        _copy_first_present(normalized, "data_gaps", "missing_data", "data_gap_candidates")
        _copy_first_present(normalized, "follow_up_questions", "questions", "followups")
        _copy_first_present(
            normalized,
            "valuation_assumption_queue",
            "valuation_assumptions",
            "valuation_assumption_suggestions",
            "valuation_inputs",
        )
        _copy_first_present(
            normalized,
            "valuation_signal_pack",
            "analyst_valuation_matrix",
            "valuation_signals",
        )
        _copy_first_present(normalized, "source_map", "sources", "source_refs")
        _copy_first_present(normalized, "confidence_summary", "confidence")
        if "executive_summary" not in normalized:
            normalized["executive_summary"] = _derive_executive_summary(normalized)
        return normalized

    @field_validator(
        "title",
        "executive_summary",
        "prohibited_actions_note",
    )
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("字段不能为空")
        return normalized

    @field_validator(
        "core_thesis",
        "business_quality",
        "financial_quality",
        "management_and_capital_allocation",
        "moat_and_growth",
        "key_risks",
        "counter_evidence",
        "data_gaps",
        "follow_up_questions",
        "watch_signals",
        mode="before",
    )
    @classmethod
    def normalize_string_list_fields(cls, value):
        return _normalize_str_list(value)


class InvestmentMemoGenerateRequest(BaseModel):
    user_note: str | None = Field(default=None, max_length=2000)

    @field_validator("user_note")
    @classmethod
    def normalize_user_note(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None


class InvestmentMemoRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    company_id: int
    generation_run_id: int
    parent_memo_id: int | None = None
    version_no: int
    editor_type: str
    title: str
    conclusion: str
    sections: dict[str, object] = Field(default_factory=dict)
    markdown: str | None = None
    source_analyst_run_ids: list[int] = Field(default_factory=list)
    source_snapshot_hash: str | None = None
    config_version: int | None = None
    config_hash: str | None = None
    config_snapshot: dict[str, object] = Field(default_factory=dict)
    change_note: str | None = None
    status: str
    is_latest: bool
    created_at: datetime
    updated_at: datetime

    @field_serializer("created_at", "updated_at")
    def serialize_time(self, value: datetime) -> str:
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value.astimezone(DISPLAY_TIME_ZONE).isoformat()


class InvestmentMemoLatestResponse(BaseModel):
    company_id: int
    item: InvestmentMemoRead | None = None


class InvestmentMemoListResponse(BaseModel):
    items: list[InvestmentMemoRead]
    total: int
    limit: int
    offset: int


class InvestmentMemoGenerateResponse(BaseModel):
    company_id: int
    run_id: int
    memo: InvestmentMemoRead


class InvestmentMemoDeleteResponse(BaseModel):
    id: int
    deleted: bool
    latest_memo_id: int | None = None


class InvestmentMemoArchiveResponse(BaseModel):
    id: int
    archived: bool
    latest_memo_id: int | None = None


def _normalize_int_list(value: object) -> list[int]:
    if isinstance(value, int) and not isinstance(value, bool):
        value = [value]
    if not isinstance(value, list):
        return []
    items: list[int] = []
    for item in value:
        if isinstance(item, bool):
            continue
        if isinstance(item, int) and item not in items:
            items.append(item)
        elif isinstance(item, str) and item.strip().isdigit():
            parsed = int(item.strip())
            if parsed not in items:
                items.append(parsed)
    return items


def _normalize_str_list(value: object) -> list[str]:
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return []
    items: list[str] = []
    for item in value:
        normalized = str(item).strip()
        if normalized and normalized not in items:
            items.append(normalized)
    return items


def _normalize_method_preference_list(value: object) -> list[object]:
    if value is None:
        return []
    if isinstance(value, str | dict):
        value = [value]
    if not isinstance(value, list):
        return []
    items: list[object] = []
    for item in value:
        if isinstance(item, dict):
            items.append(item)
            continue
        normalized = str(item).strip()
        if normalized:
            items.append({"method": normalized, "reason": normalized})
    return items


def _normalize_parameter_impact_list(value: object) -> list[object]:
    if value is None:
        return []
    if isinstance(value, str | dict):
        value = [value]
    if not isinstance(value, list):
        return []
    items: list[object] = []
    for item in value:
        if isinstance(item, dict):
            items.append(item)
            continue
        normalized = str(item).strip()
        if normalized:
            items.append({"parameter": "review_parameter", "reason": normalized})
    return items


def _normalize_text_token(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip().lower().replace("-", "_").replace(" ", "_")


def _normalize_signal_value(value: object) -> str:
    token = _normalize_text_token(value)
    if token in {"positive", "neutral", "negative", "unknown"}:
        return token
    raw = str(value or "").strip().lower()
    if not raw:
        return "unknown"
    if any(
        keyword in raw
        for keyword in (
            "unknown",
            "uncertain",
            "needs_review",
            "not_sure",
            "不确定",
            "无法判断",
            "证据不足",
            "未知",
            "待复核",
        )
    ):
        return "unknown"
    if any(
        keyword in raw
        for keyword in (
            "negative",
            "down",
            "weak",
            "unfavorable",
            "bearish",
            "负向",
            "消极",
            "偏负",
            "较弱",
            "偏弱",
            "低",
            "下调",
            "不利",
            "风险",
            "恶化",
        )
    ):
        return "negative"
    if any(
        keyword in raw
        for keyword in (
            "positive",
            "up",
            "strong",
            "favorable",
            "bullish",
            "正向",
            "积极",
            "偏正",
            "较强",
            "偏强",
            "强",
            "高",
            "提升",
            "有利",
            "改善",
        )
    ):
        return "positive"
    if any(
        keyword in raw
        for keyword in (
            "neutral",
            "mixed",
            "balanced",
            "stable",
            "中性",
            "一般",
            "稳定",
            "平衡",
            "混合",
        )
    ):
        return "neutral"
    return "unknown"


def _normalize_direction_value(value: object) -> str:
    token = _normalize_text_token(value)
    if token in {"up", "down", "neutral", "widen", "narrow", "cap"}:
        return token
    raw = str(value or "").strip().lower()
    if any(keyword in raw for keyword in ("widen", "expand", "扩大", "放宽", "拉宽")):
        return "widen"
    if any(keyword in raw for keyword in ("narrow", "shrink", "收窄", "缩窄", "压缩")):
        return "narrow"
    if any(keyword in raw for keyword in ("cap", "ceiling", "上限", "封顶", "约束")):
        return "cap"
    if any(
        keyword in raw
        for keyword in ("up", "raise", "increase", "higher", "上调", "提高", "提升", "增加")
    ):
        return "up"
    if any(
        keyword in raw
        for keyword in ("down", "lower", "decrease", "reduce", "下调", "降低", "压低", "减少")
    ):
        return "down"
    return "neutral"


def _normalize_magnitude_value(value: object) -> str:
    token = _normalize_text_token(value)
    if token in {"low", "medium", "high"}:
        return token
    raw = str(value or "").strip().lower()
    if any(
        keyword in raw for keyword in ("high", "strong", "large", "significant", "高", "大", "强")
    ):
        return "high"
    if any(keyword in raw for keyword in ("medium", "moderate", "mid", "中", "适中", "一般")):
        return "medium"
    return "low"


def _normalize_scenario_value(value: object) -> str:
    token = _normalize_text_token(value)
    if token in {"conservative", "base", "optimistic", "all"}:
        return token
    raw = str(value or "").strip().lower()
    if any(keyword in raw for keyword in ("conservative", "bear", "保守", "悲观")):
        return "conservative"
    if any(keyword in raw for keyword in ("base", "neutral", "central", "基准", "中性", "中位")):
        return "base"
    if any(keyword in raw for keyword in ("optimistic", "bull", "乐观", "上行")):
        return "optimistic"
    return "all"


def _normalize_method_value(value: object) -> str:
    token = _normalize_text_token(value)
    if token in {"dcf", "owner_earnings", "residual_income", "dividend_discount", "asset_value"}:
        return token
    raw = str(value or "").strip().lower()
    if any(keyword in raw for keyword in ("owner", "所有者盈余", "股东盈余")):
        return "owner_earnings"
    if any(keyword in raw for keyword in ("residual", "剩余收益")):
        return "residual_income"
    if any(keyword in raw for keyword in ("dividend", "ddm", "分红", "股息")):
        return "dividend_discount"
    if any(keyword in raw for keyword in ("asset", "资产", "清算")):
        return "asset_value"
    return "dcf"


def _normalize_score_value(value: object, *, default: float | None) -> float | None:
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        return default
    if isinstance(value, int | float):
        score = float(value)
    else:
        raw = str(value).strip()
        if not raw:
            return default
        is_percent = raw.endswith("%") or "％" in raw
        raw = raw.rstrip("%％").strip()
        try:
            score = float(raw)
        except ValueError:
            return default
        if is_percent:
            score = score / 100
    if score > 1 and score <= 100:
        score = score / 100
    if score < 0:
        return 0.0
    if score > 1:
        return 1.0
    return score


def _copy_first_present(target: dict[str, object], canonical_key: str, *aliases: str) -> None:
    if canonical_key in target:
        return
    for alias in aliases:
        if alias in target:
            target[canonical_key] = target[alias]
            return


def _unwrap_memo_payload(value: dict[str, object]) -> dict[str, object]:
    normalized = dict(value)
    for wrapper_key in ("memo", "investment_memo", "output", "result"):
        wrapped = normalized.get(wrapper_key)
        if isinstance(wrapped, dict):
            merged = dict(wrapped)
            for key, item in normalized.items():
                if key != wrapper_key and key not in merged:
                    merged[key] = item
            return merged
    sections = normalized.get("sections")
    if isinstance(sections, dict):
        merged = dict(sections)
        for key, item in normalized.items():
            if key != "sections" and key not in merged:
                merged[key] = item
        return merged
    return normalized


def _derive_executive_summary(payload: dict[str, object]) -> str:
    for key in ("research_conclusion", "title"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()

    for key in ("core_thesis", "consensus_points", "business_quality", "financial_quality"):
        value = payload.get(key)
        if isinstance(value, list) and value:
            first_item = value[0]
            if isinstance(first_item, str) and first_item.strip():
                return first_item.strip()
            if isinstance(first_item, dict):
                for item_key in ("summary", "assessment", "reasoning", "description", "topic"):
                    item_value = first_item.get(item_key)
                    if isinstance(item_value, str) and item_value.strip():
                        return item_value.strip()

    return "综合投资备忘录已生成，后续仍需结合关键风险、数据缺口和估值输入继续复核。"
