from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from app.analysis.analyst_profiles import AnalystProfile, list_analyst_profiles

STATUS_SCORES = {
    "pass": 1.0,
    "warn": -0.35,
    "fail": -2.0,
    "unknown": 0.0,
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

PRICE_ANCHOR_TERMS = (
    "current_price",
    "historical_price",
    "market_cap",
    "valuation_multiple",
    "pe_ttm",
    "pb_ratio",
    "ps_ratio",
    "position_cost",
    "rating",
    "target_price",
    "market_sentiment",
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
)


@dataclass(frozen=True)
class RuleValuationMapping:
    dimensions: Mapping[str, float]
    parameter_impacts: Mapping[str, float]
    calculation_role: str = "compute"
    price_blind_compatible: bool = True


def _rule(
    dimensions: Mapping[str, float],
    parameter_impacts: Mapping[str, float],
    *,
    calculation_role: str = "compute",
    price_blind_compatible: bool = True,
) -> RuleValuationMapping:
    return RuleValuationMapping(
        dimensions=dimensions,
        parameter_impacts=parameter_impacts,
        calculation_role=calculation_role,
        price_blind_compatible=price_blind_compatible,
    )


RULE_VALUATION_MAPPINGS: dict[tuple[str, str], RuleValuationMapping] = {
    ("buffett", "moat"): _rule(
        {"business_quality": 0.7, "moat_durability": 1.0, "pricing_power": 0.6},
        {
            "discount_rate": -0.4,
            "terminal_growth_rate": 0.5,
            "scenario_spread": -0.3,
            "method_weight_dcf": 0.3,
        },
    ),
    ("buffett", "quality"): _rule(
        {
            "business_quality": 0.5,
            "cash_flow_reliability": 1.0,
            "accounting_quality": 0.4,
            "capital_intensity": 0.3,
        },
        {
            "cash_flow_growth_rate": 0.3,
            "discount_rate": -0.4,
            "scenario_spread": -0.4,
            "method_weight_dcf": 0.6,
        },
    ),
    ("buffett", "management"): _rule(
        {"management_quality": 1.0, "execution_quality": 0.5, "business_quality": 0.3},
        {
            "owner_earnings_growth_rate": 0.4,
            "discount_rate": -0.3,
            "method_weight_owner_earnings": 0.6,
        },
    ),
    ("buffett", "margin_of_safety"): _rule(
        {"permanent_loss_risk": 0.8},
        {},
        calculation_role="price_reference",
        price_blind_compatible=False,
    ),
    ("peter_lynch", "understandable_business"): _rule(
        {"business_quality": 0.7, "demand_durability": 0.5, "execution_quality": 0.3},
        {"discount_rate": -0.2, "scenario_spread": -0.3},
    ),
    ("peter_lynch", "growth_runway"): _rule(
        {"growth_runway": 1.0, "demand_durability": 0.6, "pricing_power": 0.3},
        {
            "cash_flow_growth_rate": 0.8,
            "owner_earnings_growth_rate": 0.6,
            "terminal_growth_rate": 0.2,
        },
    ),
    ("peter_lynch", "story_vs_numbers"): _rule(
        {"accounting_quality": 0.7, "cash_flow_reliability": 0.5, "execution_quality": 0.7},
        {"cash_flow_growth_rate": 0.3, "discount_rate": -0.2, "scenario_spread": -0.4},
    ),
    ("peter_lynch", "balance_sheet_risk"): _rule(
        {"balance_sheet_risk": 1.0, "permanent_loss_risk": 0.5, "cash_flow_reliability": 0.3},
        {"discount_rate": -0.7, "scenario_spread": -0.4},
    ),
    ("munger", "mental_models"): _rule(
        {"business_quality": 0.8, "moat_durability": 0.6, "demand_durability": 0.4},
        {"discount_rate": -0.3, "terminal_growth_rate": 0.3, "scenario_spread": -0.2},
    ),
    ("munger", "incentives"): _rule(
        {"management_quality": 0.9, "execution_quality": 0.5, "permanent_loss_risk": 0.4},
        {
            "owner_earnings_growth_rate": 0.3,
            "discount_rate": -0.4,
            "method_weight_owner_earnings": 0.4,
        },
    ),
    ("munger", "culture"): _rule(
        {"management_quality": 1.0, "business_quality": 0.4, "moat_durability": 0.3},
        {"discount_rate": -0.3, "scenario_spread": -0.2},
    ),
    ("munger", "avoid_stupidity"): _rule(
        {"permanent_loss_risk": 1.0, "balance_sheet_risk": 0.5, "accounting_quality": 0.4},
        {"discount_rate": -0.8, "scenario_spread": -0.6},
    ),
    ("duan_yongping", "business_quality"): _rule(
        {"business_quality": 1.0, "moat_durability": 0.5, "demand_durability": 0.5},
        {"cash_flow_growth_rate": 0.3, "discount_rate": -0.4, "terminal_growth_rate": 0.3},
    ),
    ("duan_yongping", "benfen_culture"): _rule(
        {"management_quality": 1.0, "execution_quality": 0.4, "permanent_loss_risk": 0.4},
        {"owner_earnings_growth_rate": 0.3, "discount_rate": -0.4},
    ),
    ("duan_yongping", "consumer_mindshare"): _rule(
        {"pricing_power": 0.9, "moat_durability": 0.8, "demand_durability": 0.8},
        {"cash_flow_growth_rate": 0.5, "terminal_growth_rate": 0.5, "scenario_spread": -0.2},
    ),
    ("duan_yongping", "shareholder_return"): _rule(
        {"cash_flow_reliability": 0.7, "management_quality": 0.7, "capital_intensity": 0.5},
        {"owner_earnings_growth_rate": 0.5, "method_weight_owner_earnings": 0.6},
    ),
    ("graham", "asset_protection"): _rule(
        {"balance_sheet_risk": 1.0, "permanent_loss_risk": 0.8, "accounting_quality": 0.3},
        {"discount_rate": -0.8, "scenario_spread": -0.5},
    ),
    ("graham", "earnings_stability"): _rule(
        {"cash_flow_reliability": 0.7, "cyclicality": 0.8, "business_quality": 0.3},
        {"cash_flow_growth_rate": 0.2, "discount_rate": -0.5, "scenario_spread": -0.6},
    ),
    ("graham", "conservatism"): _rule(
        {"accounting_quality": 0.8, "permanent_loss_risk": 0.5},
        {"discount_rate": -0.4, "scenario_spread": -0.4},
    ),
    ("graham", "valuation_discipline"): _rule(
        {"permanent_loss_risk": 0.8},
        {},
        calculation_role="price_reference",
        price_blind_compatible=False,
    ),
    ("fisher", "long_term_growth"): _rule(
        {"growth_runway": 1.0, "demand_durability": 0.6, "business_quality": 0.3},
        {
            "cash_flow_growth_rate": 0.8,
            "owner_earnings_growth_rate": 0.6,
            "terminal_growth_rate": 0.2,
        },
    ),
    ("fisher", "innovation"): _rule(
        {"growth_runway": 0.7, "moat_durability": 0.5, "execution_quality": 0.7},
        {"cash_flow_growth_rate": 0.5, "scenario_spread": -0.2},
    ),
    ("fisher", "sales_execution"): _rule(
        {"execution_quality": 1.0, "growth_runway": 0.6, "demand_durability": 0.5},
        {"cash_flow_growth_rate": 0.6, "owner_earnings_growth_rate": 0.4},
    ),
    ("fisher", "management_depth"): _rule(
        {"management_quality": 0.9, "execution_quality": 0.8},
        {"owner_earnings_growth_rate": 0.4, "discount_rate": -0.3, "scenario_spread": -0.2},
    ),
    ("lin_yuan", "must_have_demand"): _rule(
        {"demand_durability": 1.0, "growth_runway": 0.5, "business_quality": 0.5},
        {"cash_flow_growth_rate": 0.5, "terminal_growth_rate": 0.3, "scenario_spread": -0.3},
    ),
    ("lin_yuan", "brand_power"): _rule(
        {"pricing_power": 1.0, "moat_durability": 0.9, "business_quality": 0.5},
        {"cash_flow_growth_rate": 0.4, "discount_rate": -0.3, "terminal_growth_rate": 0.5},
    ),
    ("lin_yuan", "cash_generation"): _rule(
        {"cash_flow_reliability": 1.0, "capital_intensity": 0.5, "accounting_quality": 0.4},
        {"cash_flow_growth_rate": 0.4, "discount_rate": -0.4, "method_weight_dcf": 0.7},
    ),
    ("lin_yuan", "compounding"): _rule(
        {"growth_runway": 0.8, "business_quality": 0.6, "execution_quality": 0.5},
        {
            "cash_flow_growth_rate": 0.6,
            "owner_earnings_growth_rate": 0.5,
            "terminal_growth_rate": 0.3,
        },
    ),
    ("li_lu", "circle_of_competence"): _rule(
        {"business_quality": 0.5, "accounting_quality": 0.6, "permanent_loss_risk": 0.4},
        {"discount_rate": -0.3, "scenario_spread": -0.4},
    ),
    ("li_lu", "depth_of_research"): _rule(
        {"accounting_quality": 0.9, "execution_quality": 0.3},
        {"discount_rate": -0.3, "scenario_spread": -0.5},
    ),
    ("li_lu", "intrinsic_value"): _rule(
        {"business_quality": 0.7, "cash_flow_reliability": 0.8, "moat_durability": 0.5},
        {
            "cash_flow_growth_rate": 0.3,
            "discount_rate": -0.3,
            "terminal_growth_rate": 0.3,
            "method_weight_dcf": 0.4,
        },
    ),
    ("li_lu", "permanent_loss"): _rule(
        {"permanent_loss_risk": 1.0, "balance_sheet_risk": 0.6, "accounting_quality": 0.4},
        {"discount_rate": -0.9, "scenario_spread": -0.7},
    ),
    ("ray_dalio", "macro_sensitivity"): _rule(
        {"cyclicality": 0.9, "demand_durability": 0.4},
        {"discount_rate": -0.4, "scenario_spread": -0.7},
    ),
    ("ray_dalio", "cycle_position"): _rule(
        {"cyclicality": 1.0, "growth_runway": 0.4},
        {"cash_flow_growth_rate": 0.3, "discount_rate": -0.3, "scenario_spread": -0.8},
    ),
    ("ray_dalio", "credit_liquidity"): _rule(
        {"balance_sheet_risk": 1.0, "cash_flow_reliability": 0.5, "permanent_loss_risk": 0.5},
        {"discount_rate": -0.8, "scenario_spread": -0.5},
    ),
    ("ray_dalio", "portfolio_risk_signal"): _rule(
        {"cyclicality": 0.8, "permanent_loss_risk": 0.7},
        {"discount_rate": -0.5, "scenario_spread": -0.8},
    ),
    ("george_soros", "reflexivity"): _rule(
        {"cyclicality": 0.7, "execution_quality": 0.4, "permanent_loss_risk": 0.4},
        {"cash_flow_growth_rate": 0.2, "discount_rate": -0.4, "scenario_spread": -0.8},
    ),
    ("george_soros", "narrative_gap"): _rule(
        {"accounting_quality": 0.7, "execution_quality": 0.8, "business_quality": 0.4},
        {"cash_flow_growth_rate": 0.4, "discount_rate": -0.4, "scenario_spread": -0.6},
    ),
    ("george_soros", "macro_fragility"): _rule(
        {"cyclicality": 1.0, "balance_sheet_risk": 0.5, "permanent_loss_risk": 0.6},
        {"discount_rate": -0.7, "scenario_spread": -0.9},
    ),
    ("george_soros", "counter_evidence"): _rule(
        {"accounting_quality": 0.5, "permanent_loss_risk": 0.8, "execution_quality": 0.4},
        {"discount_rate": -0.6, "scenario_spread": -0.8},
    ),
}


def derive_valuation_parameter_matrix(
    *,
    source_run_id: int,
    profile: AnalystProfile,
    result: dict[str, object],
) -> dict[str, object]:
    checks = result.get("rule_checks")
    if not isinstance(checks, list):
        checks = []
    checks_by_id = {str(item.get("rule_id")): item for item in checks if isinstance(item, dict)}
    rule_impacts = []
    for rule in profile.rules:
        check = checks_by_id.get(rule.id, {})
        mapping = RULE_VALUATION_MAPPINGS[(profile.id, rule.id)]
        status = str(check.get("status") or "unknown").strip().lower()
        if status not in STATUS_SCORES:
            status = "unknown"
        source_refs = {
            "evidence_ids": _list(check.get("evidence_ids")),
            "announcement_ids": _list(check.get("announcement_ids")),
            "financial_periods": _list(check.get("financial_periods")),
        }
        price_anchor_match = _find_price_anchor(check)
        price_blind = (
            mapping.price_blind_compatible
            and mapping.calculation_role == "compute"
            and price_anchor_match is None
        )
        calculation_role = (
            mapping.calculation_role if price_anchor_match is None else "price_reference"
        )
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
                "status_score": STATUS_SCORES[status],
                "price_blind_compatible": price_blind,
                "calculation_role": calculation_role,
                "dimensions": dict(mapping.dimensions),
                "parameter_impacts": dict(mapping.parameter_impacts),
                "source_refs": source_refs,
                "summary": str(check.get("summary") or "").strip(),
                "exclusion_reason": (
                    f"price_anchor:{price_anchor_match}"
                    if price_anchor_match
                    else (
                        "configured_price_reference"
                        if calculation_role == "price_reference"
                        else None
                    )
                ),
            }
        )
    return {
        "source": "analyst_rule_checks",
        "price_blind_compatible": all(
            item["price_blind_compatible"]
            for item in rule_impacts
            if item["calculation_role"] == "compute"
        ),
        "status_score_policy": dict(STATUS_SCORES),
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


def validate_rule_mapping_coverage() -> None:
    expected = {
        (profile.id, rule.id) for profile in list_analyst_profiles() for rule in profile.rules
    }
    actual = set(RULE_VALUATION_MAPPINGS)
    if expected != actual:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        raise RuntimeError(
            f"Invalid valuation rule mapping coverage: missing={missing}, extra={extra}"
        )


def _find_price_anchor(value: object) -> str | None:
    text = str(value).lower()
    return next((term for term in PRICE_ANCHOR_TERMS if term.lower() in text), None)


def _list(value: object) -> list[object]:
    return list(value) if isinstance(value, list) else []


def _number(value: object, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


validate_rule_mapping_coverage()
