from __future__ import annotations

import re
from collections.abc import Iterator, Mapping
from dataclasses import dataclass

from app.analysis.analyst_profiles import AnalystProfile, list_analyst_profiles

STATUS_SCORES = {
    "pass": 1.0,
    "neutral": 0.0,
    "unknown": -0.1,
    "warn": -0.5,
    "fail": -2.0,
}

VALUATION_DIMENSIONS = (
    "business_quality",
    "moat_durability",
    "growth_runway",
    "pricing_power",
    "cash_flow_reliability",
    "capital_intensity",
    "balance_sheet_risk",
    "management_quality",
    "cyclicality",
    "accounting_quality",
    "permanent_loss_risk",
    "demand_durability",
    "execution_quality",
)

PRICE_ANCHOR_FIELDS = frozenset(
    {
        "current_price",
        "historical_price",
        "price_history",
        "market_cap",
        "valuation_multiple",
        "pe_ttm",
        "pe_dynamic",
        "pe_static",
        "pb_ratio",
        "ps_ratio",
        "ev_ebitda",
        "position_cost",
        "holding_cost",
        "rating",
        "broker_rating",
        "market_rating",
        "target_price",
        "market_sentiment",
        "safety_margin",
        "trade_action",
        "当前价格",
        "历史价格",
        "股价",
        "市值",
        "估值倍数",
        "市盈率",
        "市净率",
        "市销率",
        "持仓成本",
        "评级",
        "目标价",
        "市场情绪",
        "安全边际",
        "交易动作",
    }
)

PRICE_ANCHOR_TEXT_PATTERNS = (
    ("current_price", re.compile(r"(?<![a-z0-9_])current_price(?![a-z0-9_])", re.I)),
    ("historical_price", re.compile(r"(?<![a-z0-9_])historical_price(?![a-z0-9_])", re.I)),
    ("market_cap", re.compile(r"(?<![a-z0-9_])market_cap(?![a-z0-9_])", re.I)),
    ("valuation_multiple", re.compile(r"(?<![a-z0-9_])valuation_multiple(?![a-z0-9_])", re.I)),
    ("pe", re.compile(r"(?<![a-z0-9_])(?:pe_ttm|pe_dynamic|pe_static)(?![a-z0-9_])", re.I)),
    ("pb_ratio", re.compile(r"(?<![a-z0-9_])pb_ratio(?![a-z0-9_])", re.I)),
    ("ps_ratio", re.compile(r"(?<![a-z0-9_])ps_ratio(?![a-z0-9_])", re.I)),
    ("position_cost", re.compile(r"(?<![a-z0-9_])(?:position|holding)_cost(?![a-z0-9_])", re.I)),
    ("target_price", re.compile(r"(?<![a-z0-9_])target_price(?![a-z0-9_])", re.I)),
    ("market_sentiment", re.compile(r"(?<![a-z0-9_])market_sentiment(?![a-z0-9_])", re.I)),
    ("rating", re.compile(r"\b(?:broker|analyst|market|investment)[ _-]?rating\b", re.I)),
    ("safety_margin", re.compile(r"(?<![a-z0-9_])safety_margin(?![a-z0-9_])", re.I)),
    ("current_price", re.compile(r"当前(?:市场)?价格")),
    ("historical_price", re.compile(r"历史(?:交易)?价格")),
    ("share_price", re.compile(r"(?<!每)股价|每股价格")),
    ("market_cap", re.compile(r"市值")),
    ("valuation_multiple", re.compile(r"估值倍数|市盈率|市净率|市销率")),
    ("position_cost", re.compile(r"持仓成本")),
    ("rating", re.compile(r"(?:券商|机构|市场|投资|分析师)(?:的)?评级")),
    ("target_price", re.compile(r"目标价")),
    ("market_sentiment", re.compile(r"市场情绪")),
    ("safety_margin", re.compile(r"安全边际")),
    ("trade_action", re.compile(r"(?:买入|卖出|持有|加仓|减仓|建仓|清仓)(?:建议|动作|信号)?")),
)


class PriceAnchorOutputError(ValueError):
    pass


@dataclass(frozen=True)
class RuleValuationMapping:
    dimensions: Mapping[str, float]
    calculation_role: str = "compute"
    price_blind_compatible: bool = True


def _rule(dimensions: Mapping[str, float]) -> RuleValuationMapping:
    return RuleValuationMapping(dimensions=dimensions)


RULE_VALUATION_MAPPINGS: dict[tuple[str, str], RuleValuationMapping] = {
    ("buffett", "durable_moat"): _rule(
        {
            "moat_durability": 1.0,
            "pricing_power": 0.7,
            "business_quality": 0.6,
            "demand_durability": 0.4,
        }
    ),
    ("buffett", "owner_earnings_quality"): _rule(
        {
            "cash_flow_reliability": 1.0,
            "accounting_quality": 0.5,
            "capital_intensity": 0.5,
            "business_quality": 0.4,
        }
    ),
    ("buffett", "capital_allocation"): _rule(
        {
            "capital_intensity": 1.0,
            "management_quality": 0.8,
            "execution_quality": 0.5,
            "growth_runway": 0.3,
        }
    ),
    ("buffett", "management_candor"): _rule(
        {"management_quality": 1.0, "accounting_quality": 0.7, "permanent_loss_risk": 0.4}
    ),
    ("peter_lynch", "business_understandability"): _rule(
        {"business_quality": 0.8, "accounting_quality": 0.4, "execution_quality": 0.3}
    ),
    ("peter_lynch", "growth_runway"): _rule(
        {"growth_runway": 1.0, "demand_durability": 0.7, "pricing_power": 0.3}
    ),
    ("peter_lynch", "story_numbers_alignment"): _rule(
        {"execution_quality": 0.8, "accounting_quality": 0.8, "cash_flow_reliability": 0.5}
    ),
    ("peter_lynch", "growth_financial_resilience"): _rule(
        {
            "balance_sheet_risk": 1.0,
            "cash_flow_reliability": 0.6,
            "capital_intensity": 0.6,
            "cyclicality": 0.3,
            "permanent_loss_risk": 0.4,
        }
    ),
    ("munger", "multi_model_resilience"): _rule(
        {
            "business_quality": 0.8,
            "moat_durability": 0.8,
            "demand_durability": 0.5,
            "pricing_power": 0.3,
        }
    ),
    ("munger", "incentive_alignment"): _rule(
        {"management_quality": 0.9, "execution_quality": 0.7, "permanent_loss_risk": 0.5}
    ),
    ("munger", "rational_culture"): _rule(
        {"management_quality": 1.0, "execution_quality": 0.6, "accounting_quality": 0.4}
    ),
    ("munger", "ruin_risk_control"): _rule(
        {
            "permanent_loss_risk": 1.0,
            "balance_sheet_risk": 0.7,
            "accounting_quality": 0.5,
            "cyclicality": 0.4,
        }
    ),
    ("duan_yongping", "right_business"): _rule(
        {
            "business_quality": 1.0,
            "cash_flow_reliability": 0.6,
            "capital_intensity": 0.6,
            "demand_durability": 0.5,
        }
    ),
    ("duan_yongping", "consumer_value_mindshare"): _rule(
        {
            "pricing_power": 0.9,
            "moat_durability": 0.9,
            "demand_durability": 0.8,
            "execution_quality": 0.3,
        }
    ),
    ("duan_yongping", "benfen_culture"): _rule(
        {
            "management_quality": 1.0,
            "accounting_quality": 0.5,
            "permanent_loss_risk": 0.5,
            "execution_quality": 0.4,
        }
    ),
    ("duan_yongping", "cash_reinvestment_discipline"): _rule(
        {
            "cash_flow_reliability": 0.9,
            "capital_intensity": 0.8,
            "management_quality": 0.6,
            "growth_runway": 0.4,
        }
    ),
    ("graham", "working_capital_safety"): _rule(
        {"balance_sheet_risk": 1.0, "cash_flow_reliability": 0.5, "permanent_loss_risk": 0.5}
    ),
    ("graham", "capital_structure_safety"): _rule(
        {"balance_sheet_risk": 1.0, "permanent_loss_risk": 0.8, "cyclicality": 0.4}
    ),
    ("graham", "earnings_record"): _rule(
        {
            "cyclicality": 0.9,
            "cash_flow_reliability": 0.8,
            "accounting_quality": 0.4,
            "business_quality": 0.3,
        }
    ),
    ("graham", "asset_accounting_quality"): _rule(
        {"accounting_quality": 1.0, "balance_sheet_risk": 0.7, "permanent_loss_risk": 0.7}
    ),
    ("fisher", "market_runway"): _rule(
        {"growth_runway": 1.0, "demand_durability": 0.7, "business_quality": 0.3}
    ),
    ("fisher", "innovation_productivity"): _rule(
        {
            "execution_quality": 0.8,
            "growth_runway": 0.8,
            "moat_durability": 0.7,
            "capital_intensity": 0.3,
        }
    ),
    ("fisher", "sales_customer_strength"): _rule(
        {
            "execution_quality": 1.0,
            "demand_durability": 0.7,
            "pricing_power": 0.5,
            "growth_runway": 0.5,
        }
    ),
    ("fisher", "management_depth"): _rule(
        {"management_quality": 1.0, "execution_quality": 0.9, "permanent_loss_risk": 0.3}
    ),
    ("lin_yuan", "must_have_repeat_demand"): _rule(
        {
            "demand_durability": 1.0,
            "business_quality": 0.6,
            "cyclicality": 0.5,
            "growth_runway": 0.4,
        }
    ),
    ("lin_yuan", "monopoly_brand_power"): _rule(
        {
            "pricing_power": 1.0,
            "moat_durability": 1.0,
            "business_quality": 0.5,
            "demand_durability": 0.5,
        }
    ),
    ("lin_yuan", "cash_profitability"): _rule(
        {
            "cash_flow_reliability": 1.0,
            "capital_intensity": 0.7,
            "pricing_power": 0.4,
            "accounting_quality": 0.3,
        }
    ),
    ("lin_yuan", "scalable_compounding"): _rule(
        {
            "growth_runway": 0.9,
            "capital_intensity": 0.6,
            "execution_quality": 0.6,
            "business_quality": 0.5,
        }
    ),
    ("li_lu", "economic_knowability"): _rule(
        {"accounting_quality": 0.8, "business_quality": 0.6, "execution_quality": 0.3}
    ),
    ("li_lu", "moat_growth_coexistence"): _rule(
        {
            "growth_runway": 0.9,
            "moat_durability": 0.8,
            "demand_durability": 0.6,
            "pricing_power": 0.4,
        }
    ),
    ("li_lu", "owner_governance"): _rule(
        {
            "management_quality": 1.0,
            "permanent_loss_risk": 0.7,
            "accounting_quality": 0.6,
            "execution_quality": 0.4,
        }
    ),
    ("li_lu", "permanent_loss_resilience"): _rule(
        {
            "permanent_loss_risk": 1.0,
            "balance_sheet_risk": 0.8,
            "accounting_quality": 0.5,
            "cyclicality": 0.4,
        }
    ),
}


def derive_valuation_parameter_matrix(
    *,
    source_run_id: int,
    profile: AnalystProfile,
    result: dict[str, object],
) -> dict[str, object]:
    price_anchor_match = find_price_anchor(result)
    if price_anchor_match is not None:
        raise PriceAnchorOutputError(
            f"分析师输出包含禁止的价格锚“{price_anchor_match}”；"
            "008 必须保持 price-blind，本次分析已拒绝。"
        )

    checks = result.get("rule_checks")
    if not isinstance(checks, list):
        checks = []
    checks_by_id = {str(item.get("rule_id")): item for item in checks if isinstance(item, dict)}
    status_scores = _parameter_value("valuation_rule_matrix.status_scores", STATUS_SCORES)
    status_scores = status_scores if isinstance(status_scores, dict) else STATUS_SCORES
    rule_impacts: list[dict[str, object]] = []
    for rule in profile.rules:
        check = checks_by_id.get(rule.id, {})
        mapping = _runtime_rule_mapping(profile.id, rule.id)
        status = str(check.get("status") or "unknown").strip().lower()
        if status not in status_scores:
            status = "unknown"
        rule_impacts.append(
            {
                "profile_id": profile.id,
                "profile_name": profile.display_name,
                "source_run_id": source_run_id,
                "profile_fit_score": _number(result.get("profile_fit_score"), 0.6),
                "data_confidence": _number(result.get("confidence"), 0.6),
                "rule_id": rule.id,
                "rule_label": rule.label,
                "status": status,
                "status_score": float(status_scores[status]),
                "price_blind_compatible": True,
                "calculation_role": "compute",
                "dimensions": dict(mapping.dimensions),
                "source_refs": {
                    "evidence_ids": _list(check.get("evidence_ids")),
                    "announcement_ids": _list(check.get("announcement_ids")),
                    "financial_periods": _list(check.get("financial_periods")),
                },
                "summary": str(check.get("summary") or "").strip(),
                "exclusion_reason": None,
            }
        )
    return {
        "source": "analyst_rule_checks",
        "price_blind_compatible": True,
        "status_score_policy": dict(status_scores),
        "analyst_items": [
            {
                "profile_id": profile.id,
                "profile_name": profile.display_name,
                "source_run_id": source_run_id,
                "profile_fit_score": _number(result.get("profile_fit_score"), 0.6),
                "data_confidence": _number(result.get("confidence"), 0.6),
                "rule_impacts": rule_impacts,
            }
        ],
    }


def _runtime_rule_mapping(profile_id: str, rule_id: str) -> RuleValuationMapping:
    configured_mappings = _parameter_value("valuation_rule_matrix.rule_mappings", {})
    configured = (
        configured_mappings.get(f"{profile_id}.{rule_id}")
        if isinstance(configured_mappings, dict)
        else None
    )
    if not isinstance(configured, dict) or not isinstance(configured.get("dimensions"), dict):
        return RULE_VALUATION_MAPPINGS[(profile_id, rule_id)]
    return RuleValuationMapping(
        dimensions={str(key): float(value) for key, value in configured["dimensions"].items()},
        calculation_role=str(configured.get("calculation_role") or "compute"),
        price_blind_compatible=configured.get("price_blind_compatible") is True,
    )


def validate_rule_mapping_coverage() -> None:
    expected = {
        (profile.id, rule.id) for profile in list_analyst_profiles() for rule in profile.rules
    }
    actual = set(RULE_VALUATION_MAPPINGS)
    if expected != actual:
        raise RuntimeError(
            "Invalid valuation rule mapping coverage: "
            f"missing={sorted(expected - actual)}, extra={sorted(actual - expected)}"
        )
    if any(
        mapping.calculation_role != "compute" or not mapping.price_blind_compatible
        for mapping in RULE_VALUATION_MAPPINGS.values()
    ):
        raise RuntimeError("All analyst rules must be compute and price-blind compatible.")
    coefficient_count = sum(len(mapping.dimensions) for mapping in RULE_VALUATION_MAPPINGS.values())
    if coefficient_count != 117:
        raise RuntimeError(
            f"Expected 117 valuation dimension coefficients, got {coefficient_count}."
        )


def find_price_anchor(value: object) -> str | None:
    structured_match = _find_price_anchor_field(value)
    if structured_match is not None:
        return structured_match
    for text in _iter_text_values(value):
        for label, pattern in PRICE_ANCHOR_TEXT_PATTERNS:
            if pattern.search(text):
                return label
    return None


def _find_price_anchor_field(value: object) -> str | None:
    if isinstance(value, Mapping):
        for key, nested in value.items():
            normalized_key = str(key).strip().lower()
            if normalized_key in PRICE_ANCHOR_FIELDS:
                return normalized_key
            nested_match = _find_price_anchor_field(nested)
            if nested_match is not None:
                return nested_match
    elif isinstance(value, (list, tuple)):
        for item in value:
            nested_match = _find_price_anchor_field(item)
            if nested_match is not None:
                return nested_match
    return None


def _iter_text_values(value: object) -> Iterator[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, Mapping):
        for nested in value.values():
            yield from _iter_text_values(nested)
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from _iter_text_values(item)


def _list(value: object) -> list[object]:
    return list(value) if isinstance(value, list) else []


def _number(value: object, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _parameter_value(path: str, default: object) -> object:
    from app.configuration.runtime import parameter_value

    return parameter_value(path, default)


validate_rule_mapping_coverage()
