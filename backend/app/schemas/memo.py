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


class InvestmentMemoOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

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
