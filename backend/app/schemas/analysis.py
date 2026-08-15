from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.analysis.result_sanitizer import sanitize_result_payload


class AnalystRuleRead(BaseModel):
    id: str
    label: str
    description: str


class AnalystProfileRead(BaseModel):
    id: str
    name: str
    display_name: str
    description: str
    philosophy: str
    rules: list[AnalystRuleRead]
    prompt_focus: list[str]


class AnalystProfileListResponse(BaseModel):
    items: list[AnalystProfileRead]


class AnalystRuleCheckOutput(BaseModel):
    rule_id: str = Field(min_length=1)
    status: Literal["pass", "warn", "fail", "unknown"]
    summary: str = Field(min_length=1)
    evidence_ids: list[int] = Field(default_factory=list)
    financial_periods: list[str] = Field(default_factory=list)
    announcement_ids: list[int] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def normalize_model_aliases(cls, value):
        if not isinstance(value, dict):
            return value

        normalized = dict(value)
        if "rule_id" not in normalized and "id" in normalized:
            normalized["rule_id"] = normalized["id"]
        if "summary" not in normalized:
            normalized["summary"] = (
                normalized.get("reasoning")
                or normalized.get("assessment")
                or normalized.get("conclusion")
                or normalized.get("comment")
                or "快照证据不足，需继续验证该规则。"
            )
        normalized["status"] = _normalize_rule_status(normalized.get("status"))

        if "evidence_ids" not in normalized:
            normalized["evidence_ids"] = _normalize_int_list(
                normalized.get("supporting_evidence_ids")
                or normalized.get("evidence_used")
                or normalized.get("evidence")
            )
        if "announcement_ids" not in normalized:
            normalized["announcement_ids"] = _normalize_int_list(
                normalized.get("supporting_announcement_ids") or normalized.get("announcements")
            )
        if "financial_periods" not in normalized:
            normalized["financial_periods"] = _normalize_str_list(
                normalized.get("supporting_financial_periods") or normalized.get("periods")
            )

        return normalized

    @field_validator("summary")
    @classmethod
    def strip_summary(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("字段不能为空")
        return normalized


class ValuationAssumptionDetail(BaseModel):
    assumption_type: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    needed_inputs: list[str] = Field(default_factory=list)
    source_refs: dict[str, list[int | str]] = Field(default_factory=dict)

    @field_validator("assumption_type", "reason")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("字段不能为空")
        return normalized

    @field_validator("needed_inputs", mode="before")
    @classmethod
    def normalize_needed_inputs(cls, value):
        return _normalize_str_list(value)


class AnalystAnalysisOutput(BaseModel):
    analyst_profile: str = Field(min_length=1)
    overview: str = Field(min_length=1)
    profile_fit_score: float = Field(ge=0, le=1)
    confidence: float = Field(ge=0, le=1)
    key_observations: list[str] = Field(default_factory=list)
    rule_checks: list[AnalystRuleCheckOutput] = Field(default_factory=list)
    supporting_evidence_ids: list[int] = Field(default_factory=list)
    financial_observations: list[str] = Field(default_factory=list)
    announcement_observations: list[str] = Field(default_factory=list)
    risk_flags: list[str] = Field(default_factory=list)
    counter_evidence: list[str] = Field(default_factory=list)
    valuation_assumption_suggestions: list[str] = Field(default_factory=list)
    valuation_assumption_details: list[ValuationAssumptionDetail] = Field(default_factory=list)
    data_gaps: list[str] = Field(default_factory=list)
    follow_up_questions: list[str] = Field(default_factory=list)
    analysis_basis: dict[str, object] = Field(default_factory=dict)
    accounting_events: list[dict[str, object]] = Field(default_factory=list)
    score_explanations: dict[str, object] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def normalize_model_aliases(cls, value):
        if not isinstance(value, dict):
            return value

        normalized = dict(value)
        rule_checks = normalized.get("rule_checks")
        if not isinstance(rule_checks, list):
            rule_checks = []
            normalized["rule_checks"] = rule_checks

        if "overview" not in normalized:
            normalized["overview"] = _build_overview_from_payload(normalized, rule_checks)
        if "profile_fit_score" not in normalized:
            normalized["profile_fit_score"] = _derive_profile_fit_score(rule_checks)
        else:
            normalized["profile_fit_score"] = _normalize_score(normalized.get("profile_fit_score"))
        if "confidence" not in normalized:
            normalized["confidence"] = _derive_confidence(normalized, rule_checks)
        else:
            normalized["confidence"] = _normalize_score(normalized.get("confidence"))

        if "key_observations" not in normalized:
            normalized["key_observations"] = _build_key_observations(rule_checks)
        if "supporting_evidence_ids" not in normalized:
            normalized["supporting_evidence_ids"] = _collect_rule_evidence_ids(rule_checks)

        alias_map = {
            "financial_observations": ("financial_analysis", "financial_notes"),
            "announcement_observations": ("announcement_analysis", "announcement_notes"),
            "risk_flags": ("risks", "risk_factors"),
            "counter_evidence": ("bear_case", "contrary_evidence", "disconfirming_evidence"),
            "valuation_assumption_suggestions": (
                "valuation_assumptions",
                "valuation_questions",
                "valuation_inputs",
            ),
            "data_gaps": ("limitations", "missing_data"),
            "follow_up_questions": ("questions", "next_questions"),
            "accounting_events": ("accounting_notes", "accounting_adjustments"),
            "analysis_basis": ("basis", "source_basis"),
        }
        for target_key, alias_keys in alias_map.items():
            if target_key in normalized:
                continue
            for alias_key in alias_keys:
                if alias_key in normalized:
                    normalized[target_key] = normalized[alias_key]
                    break

        suggestions, details = _normalize_valuation_assumptions(
            normalized.get("valuation_assumption_suggestions"),
            normalized.get("valuation_assumption_details"),
        )
        normalized["valuation_assumption_suggestions"] = suggestions
        normalized["valuation_assumption_details"] = details

        return normalized

    @field_validator(
        "overview",
        "key_observations",
        "financial_observations",
        "announcement_observations",
        "risk_flags",
        "counter_evidence",
        "valuation_assumption_suggestions",
        "data_gaps",
        "follow_up_questions",
        mode="before",
    )
    @classmethod
    def normalize_text_fields(cls, value):
        if isinstance(value, str):
            return value.strip()
        if isinstance(value, list):
            items: list[str] = []
            for item in value:
                normalized = str(item).strip()
                if normalized and normalized not in items:
                    items.append(normalized)
            return items
        return value


def _normalize_rule_status(value: object) -> str:
    if not isinstance(value, str):
        return "unknown"
    status = value.strip().lower()
    status_aliases = {
        "pass": "pass",
        "passed": "pass",
        "positive": "pass",
        "stable": "pass",
        "acceptable": "pass",
        "good": "pass",
        "strong": "pass",
        "warn": "warn",
        "warning": "warn",
        "mixed": "warn",
        "partial": "warn",
        "neutral": "warn",
        "moderate": "warn",
        "watch": "warn",
        "down_cycle": "warn",
        "fail": "fail",
        "failed": "fail",
        "negative": "fail",
        "weak": "fail",
        "poor": "fail",
        "risk": "fail",
        "high_risk": "fail",
        "unknown": "unknown",
        "uncertain": "unknown",
        "inconclusive": "unknown",
        "unclear": "unknown",
        "insufficient": "unknown",
    }
    return status_aliases.get(status, "unknown")


def _normalize_score(value: object) -> float:
    if isinstance(value, (int, float)):
        score = float(value)
    elif isinstance(value, str):
        normalized = value.strip().removesuffix("%")
        try:
            score = float(normalized)
        except ValueError:
            return 0.5
    else:
        return 0.5
    if score > 1 and score <= 100:
        score = score / 100
    return max(0, min(1, score))


def _normalize_int_list(value: object) -> list[int]:
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


def _normalize_valuation_assumptions(
    suggestions_value: object,
    details_value: object,
) -> tuple[list[str], list[dict[str, object]]]:
    suggestions: list[str] = []
    details: list[dict[str, object]] = []

    if isinstance(details_value, list):
        for item in details_value:
            if isinstance(item, dict):
                detail = _normalize_valuation_detail(item)
                if detail is not None:
                    details.append(detail)

    if isinstance(suggestions_value, str):
        suggestions_value = [suggestions_value]
    if isinstance(suggestions_value, list):
        for item in suggestions_value:
            if isinstance(item, dict):
                detail = _normalize_valuation_detail(item)
                if detail is not None:
                    details.append(detail)
                    summary = _summarize_valuation_detail(detail)
                    if summary not in suggestions:
                        suggestions.append(summary)
                continue
            normalized = str(item).strip()
            if normalized and normalized not in suggestions:
                suggestions.append(normalized)

    unique_details: list[dict[str, object]] = []
    seen_detail_keys: set[tuple[str, str]] = set()
    for detail in details:
        key = (str(detail.get("assumption_type")), str(detail.get("reason")))
        if key not in seen_detail_keys:
            seen_detail_keys.add(key)
            unique_details.append(detail)

    return suggestions, unique_details


def _normalize_valuation_detail(value: dict[str, object]) -> dict[str, object] | None:
    assumption_type = (
        value.get("assumption_type")
        or value.get("type")
        or value.get("category")
        or value.get("name")
    )
    reason = value.get("reason") or value.get("rationale") or value.get("summary")
    if not assumption_type or not reason:
        return None

    source_refs = value.get("source_refs")
    if not isinstance(source_refs, dict):
        source_refs = {}

    normalized_refs: dict[str, list[int | str]] = {}
    for key, ref_value in source_refs.items():
        refs: list[int | str] = []
        if isinstance(ref_value, list):
            for item in ref_value:
                if isinstance(item, bool):
                    continue
                if isinstance(item, int | str):
                    refs.append(item)
        elif isinstance(ref_value, int | str) and not isinstance(ref_value, bool):
            refs.append(ref_value)
        if refs:
            normalized_refs[str(key)] = refs

    return {
        "assumption_type": str(assumption_type).strip(),
        "reason": str(reason).strip(),
        "needed_inputs": _normalize_str_list(value.get("needed_inputs")),
        "source_refs": normalized_refs,
    }


def _summarize_valuation_detail(detail: dict[str, object]) -> str:
    assumption_type = str(detail.get("assumption_type") or "估值假设").strip()
    reason = str(detail.get("reason") or "").strip().rstrip("。；;")
    needed_inputs = _normalize_str_list(detail.get("needed_inputs"))
    if needed_inputs:
        return f"{assumption_type}：{reason}；需补充 {('、').join(needed_inputs[:3])}"
    return f"{assumption_type}：{reason}"


def _build_overview_from_payload(payload: dict[str, object], rule_checks: list[object]) -> str:
    for key in ("summary", "conclusion", "investment_thesis", "assessment"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()

    observations = payload.get("key_observations")
    if isinstance(observations, list) and observations:
        return str(observations[0]).strip()

    summaries = _build_key_observations(rule_checks)
    if summaries:
        return _join_chinese_clauses(summaries[:2])
    return "模型已基于快照生成初步视角，但可用证据有限，需结合数据缺口继续复核。"


def _build_key_observations(rule_checks: list[object]) -> list[str]:
    observations: list[str] = []
    for item in rule_checks:
        if not isinstance(item, dict):
            continue
        summary = (
            item.get("summary")
            or item.get("reasoning")
            or item.get("assessment")
            or item.get("conclusion")
        )
        if isinstance(summary, str):
            normalized = summary.strip()
            if normalized and normalized not in observations:
                observations.append(normalized)
        if len(observations) >= 4:
            break
    return observations


def _collect_rule_evidence_ids(rule_checks: list[object]) -> list[int]:
    evidence_ids: list[int] = []
    for item in rule_checks:
        if not isinstance(item, dict):
            continue
        for evidence_id in _normalize_int_list(
            item.get("evidence_ids")
            or item.get("supporting_evidence_ids")
            or item.get("evidence_used")
        ):
            if evidence_id not in evidence_ids:
                evidence_ids.append(evidence_id)
    return evidence_ids


def _derive_profile_fit_score(rule_checks: list[object]) -> float:
    statuses = [
        _normalize_rule_status(item.get("status")) for item in rule_checks if isinstance(item, dict)
    ]
    if not statuses:
        return 0.5
    score_by_status = {"pass": 0.8, "warn": 0.55, "fail": 0.25, "unknown": 0.45}
    return round(sum(score_by_status[status] for status in statuses) / len(statuses), 2)


def _derive_confidence(payload: dict[str, object], rule_checks: list[object]) -> float:
    confidence = 0.62
    data_gaps = payload.get("data_gaps") or payload.get("limitations") or []
    if isinstance(data_gaps, list):
        confidence -= min(0.18, len(data_gaps) * 0.03)
    unknown_count = sum(
        1
        for item in rule_checks
        if isinstance(item, dict) and _normalize_rule_status(item.get("status")) == "unknown"
    )
    confidence -= min(0.16, unknown_count * 0.04)
    return round(max(0.35, min(0.75, confidence)), 2)


def _join_chinese_clauses(values: list[str]) -> str:
    clauses = [value.strip().rstrip("。；;") for value in values if value.strip()]
    return "；".join(value for value in clauses if value)


class AnalystRunRequest(BaseModel):
    analyst_profile: str = Field(min_length=1, max_length=80)
    user_note: str | None = Field(default=None, max_length=2000)

    @field_validator("analyst_profile")
    @classmethod
    def normalize_profile(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("字段不能为空")
        return normalized

    @field_validator("user_note")
    @classmethod
    def normalize_user_note(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None


class AnalystBatchRunRequest(BaseModel):
    analyst_profiles: list[str] = Field(default_factory=list, max_length=20)
    user_note: str | None = Field(default=None, max_length=2000)

    @field_validator("analyst_profiles")
    @classmethod
    def normalize_profiles(cls, value: list[str]) -> list[str]:
        profile_ids: list[str] = []
        for item in value:
            normalized = item.strip()
            if normalized and normalized not in profile_ids:
                profile_ids.append(normalized)
        return profile_ids

    @field_validator("user_note")
    @classmethod
    def normalize_user_note(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None


class AnalysisRuleStatusUpdateRequest(BaseModel):
    status: Literal["pass", "warn", "fail", "unknown"]


class AnalysisRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    company_id: int
    run_type: str
    analyst_profile: str | None = None
    run_version: str | None = None
    model_name: str | None = None
    prompt_version: str | None = None
    data_snapshot_hash: str | None = None
    result: dict[str, object] = Field(default_factory=dict)
    confidence: float | None = None
    parent_run_id: int | None = None
    is_latest: bool
    user_note: str | None = None
    status: str
    created_at: datetime

    @field_validator("result")
    @classmethod
    def sanitize_result(cls, value: dict[str, object]) -> dict[str, object]:
        return sanitize_result_payload(value)


class AnalysisRunListResponse(BaseModel):
    items: list[AnalysisRunRead]
    total: int
    limit: int
    offset: int


class AnalysisRunDeleteResponse(BaseModel):
    id: int
    deleted: bool


class AnalysisLatestRunsResponse(BaseModel):
    company_id: int
    run_type: str | None = None
    analyst_profile: str | None = None
    status: str | None = None
    items: list[AnalysisRunRead]


class AnalysisBatchRunItem(BaseModel):
    analyst_profile: str
    status: Literal["success", "failed"]
    run: AnalysisRunRead | None = None
    error: str | None = None
    error_type: str | None = None


class AnalysisBatchRunResponse(BaseModel):
    company_id: int
    requested: int
    succeeded: int
    failed: int
    items: list[AnalysisBatchRunItem]
