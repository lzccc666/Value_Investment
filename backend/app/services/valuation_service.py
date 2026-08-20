from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from math import isfinite
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.analysis.analyst_profiles import list_analyst_profiles
from app.analysis.analyst_weights import (
    analyst_raw_weight,
    differentiate_and_normalize_analyst_weights,
)
from app.analysis.valuation_parameter_matrix import (
    STATUS_SCORES,
    VALUATION_DIMENSIONS,
    derive_valuation_parameter_matrix,
)
from app.configuration.runtime import parameter_config_context, parameter_value
from app.db.models import AnalysisRun, Company, ValuationRun, utc_now
from app.services.companies import list_company_financials
from app.services.financial_metrics import build_financial_evidence_pack
from app.services.memo_service import get_latest_memo_for_valuation
from app.services.parameter_config_service import get_runtime_parameter_config

RUN_VERSION = "010_v1"
FORBIDDEN_PRICE_FIELDS = {
    "current_price",
    "market_cap",
    "historical_price",
    "price_history",
    "valuation_multiple",
    "pe_ttm",
    "pe_dynamic",
    "pe_static",
    "pb_ratio",
    "ps_ratio",
    "ev_ebitda",
    "position_cost",
    "market_rating",
    "target_price",
    "broker_rating",
    "market_sentiment",
    "safety_margin",
    "trade_action",
}
FORBIDDEN_PRICE_TERMS = (
    "当前价格",
    "历史价格",
    "股价",
    "市值",
    "估值倍数",
    "市盈率",
    "市净率",
    "市销率",
    "目标价",
    "券商评级",
    "持仓成本",
    "浮盈",
    "浮亏",
    "市场情绪",
    "安全边际",
    "买入",
    "卖出",
    "持有",
    "加仓",
    "减仓",
)


class ValuationRunError(ValueError):
    pass


class ValuationInputError(ValuationRunError):
    pass


def build_valuation_snapshot(session: Session, company: Company) -> dict[str, object]:
    memo = get_latest_memo_for_valuation(session, company_id=company.id)
    if memo is None:
        raise ValuationInputError("需要先生成最新综合投资备忘录，010 只读取最新未删除 memo。")

    financials, _ = list_company_financials(
        session,
        company_id=company.id,
        limit=int(parameter_value("data_sampling.valuation_financial_records", 120)),
        offset=0,
    )
    financial_evidence_pack = build_financial_evidence_pack(financials)
    if not financial_evidence_pack.get("latest_period"):
        raise ValuationInputError("需要先同步财务数据，当前没有可用于估值的财务证据包。")

    scrubber = _PriceBlindScrubber()
    memo_sections = memo.sections if isinstance(memo.sections, dict) else {}
    memo_inputs = scrubber.scrub(
        {
            "memo_id": memo.id,
            "version_no": memo.version_no,
            "title": memo.title,
            "source_snapshot_hash": memo.source_snapshot_hash,
            "research_conclusion": memo.conclusion,
            "valuation_assumption_queue": memo_sections.get("valuation_assumption_queue", []),
            "key_risks": memo_sections.get("key_risks", []),
            "counter_evidence": memo_sections.get("counter_evidence", []),
            "data_gaps": memo_sections.get("data_gaps", []),
            "follow_up_questions": memo_sections.get("follow_up_questions", []),
            "confidence_summary": memo_sections.get("confidence_summary", {}),
            "source_map": memo_sections.get("source_map", {}),
        }
    )
    snapshot = {
        "company": {
            "id": company.id,
            "ticker": company.ticker,
            "exchange": company.exchange,
            "name": company.name,
            "industry": company.industry,
            "status": company.status,
            "tags": company.tags,
        },
        "price_blind_boundary": {
            "price_blind": True,
            "forbidden_inputs": sorted(FORBIDDEN_PRICE_FIELDS),
            "scrubbed_items": scrubber.scrubbed_items,
        },
        "financial_evidence_pack": financial_evidence_pack,
        "memo_inputs": memo_inputs,
        "analyst_parameter_matrices": _latest_analyst_parameter_matrices(
            session,
            company_id=company.id,
        ),
    }
    return snapshot


def _latest_analyst_parameter_matrices(
    session: Session,
    *,
    company_id: int,
) -> list[dict[str, object]]:
    runs = session.scalars(
        select(AnalysisRun)
        .where(
            AnalysisRun.company_id == company_id,
            AnalysisRun.run_type == "analyst_view",
        )
        .order_by(AnalysisRun.created_at.desc(), AnalysisRun.id.desc())
    ).all()
    latest_by_profile: dict[str, AnalysisRun] = {}
    for run in runs:
        profile_id = str(run.analyst_profile or "")
        if profile_id and profile_id not in latest_by_profile:
            latest_by_profile[profile_id] = run

    allowed_statuses = {"pass", "neutral", "unknown", "warn", "fail"}
    issues: list[str] = []
    matrices: list[dict[str, object]] = []
    for profile in list_analyst_profiles():
        run = latest_by_profile.get(profile.id)
        if run is None:
            issues.append(f"{profile.display_name}：缺少最新运行")
            continue
        if run.status != "success":
            issues.append(f"{profile.display_name}：最新运行状态为 {run.status}，不是 success")
            continue
        result = _dict(run.result)
        checks = result.get("rule_checks")
        if not isinstance(checks, list):
            issues.append(f"{profile.display_name}：缺少四条规则结果")
            continue
        check_rows = [item for item in checks if isinstance(item, dict)]
        actual_ids = [str(item.get("rule_id") or "") for item in check_rows]
        expected_ids = [rule.id for rule in profile.rules]
        invalid_statuses = sorted(
            {
                str(item.get("status") or "")
                for item in check_rows
                if str(item.get("status") or "") not in allowed_statuses
            }
        )
        if len(check_rows) != 4 or actual_ids != expected_ids or invalid_statuses:
            details: list[str] = []
            if len(check_rows) != 4:
                details.append(f"规则数={len(check_rows)}")
            if actual_ids != expected_ids:
                details.append("规则 ID 或顺序不完整")
            if invalid_statuses:
                details.append(f"非法状态={invalid_statuses}")
            issues.append(f"{profile.display_name}：{'，'.join(details)}")
            continue
        try:
            matrices.append(
                derive_valuation_parameter_matrix(
                    source_run_id=run.id,
                    profile=profile,
                    result=result,
                )
            )
        except ValueError as exc:
            issues.append(f"{profile.display_name}：{exc}")
    if issues:
        raise ValuationInputError("010 完整性门槛未通过：" + "；".join(issues))
    return matrices


def create_draft_valuation_run(
    session: Session,
    company: Company,
    *,
    user_assumptions: dict[str, object] | None = None,
    user_note: str | None = None,
) -> ValuationRun:
    runtime = get_runtime_parameter_config(session)
    with parameter_config_context(runtime.snapshot):
        snapshot = build_valuation_snapshot(session, company)
        snapshot["configuration"] = {
            "version": runtime.version,
            "hash": runtime.config_hash,
            "source": runtime.source,
            "fallback_reason": runtime.fallback_reason,
        }
        memo_inputs = snapshot.get("memo_inputs")
        memo_id = _as_int(memo_inputs.get("memo_id")) if isinstance(memo_inputs, dict) else None
        payload = _calculate_valuation_payload(snapshot, user_assumptions or {})
        run = ValuationRun(
            company_id=company.id,
            memo_id=memo_id,
            run_version=RUN_VERSION,
            status="draft",
            price_blind=True,
            forbidden_price_inputs=payload["forbidden_price_inputs"],
            input_snapshot=snapshot,
            input_snapshot_hash=_hash_snapshot(snapshot),
            config_version=runtime.version,
            config_hash=runtime.config_hash,
            config_snapshot=deepcopy(runtime.snapshot),
            valuation_inputs=payload["valuation_inputs"],
            model_suggested_assumptions=payload["model_suggested_assumptions"],
            user_adjusted_assumptions=payload["user_adjusted_assumptions"],
            assumptions=payload["assumptions"],
            methods=payload["methods"],
            results=payload["results"],
            sensitivity=payload["sensitivity"],
            confidence=payload["confidence"],
            confidence_summary=payload["confidence_summary"],
            source_map=payload["source_map"],
            user_note=user_note,
            created_at=utc_now(),
            updated_at=utc_now(),
        )
        session.add(run)
        session.commit()
        session.refresh(run)
        return run


def recalculate_valuation_run(
    session: Session,
    run: ValuationRun,
    *,
    user_assumptions: dict[str, object],
    user_note: str | None = None,
) -> ValuationRun:
    company = session.get(Company, run.company_id)
    if company is None:
        raise ValuationInputError("估值记录所属公司不存在。")
    return create_draft_valuation_run(
        session,
        company,
        user_assumptions=user_assumptions,
        user_note=user_note if user_note is not None else run.user_note,
    )


def get_valuation_run(session: Session, run_id: int) -> ValuationRun | None:
    return session.get(ValuationRun, run_id)


def get_latest_company_valuation_run(
    session: Session,
    *,
    company_id: int,
) -> ValuationRun | None:
    return session.scalar(
        select(ValuationRun)
        .where(ValuationRun.company_id == company_id)
        .order_by(ValuationRun.created_at.desc(), ValuationRun.id.desc())
    )


def list_company_valuation_runs(
    session: Session,
    *,
    company_id: int,
    limit: int = 20,
    offset: int = 0,
) -> tuple[list[ValuationRun], int]:
    filters = [ValuationRun.company_id == company_id]
    total = session.scalar(select(func.count()).select_from(ValuationRun).where(*filters)) or 0
    items = session.scalars(
        select(ValuationRun)
        .where(*filters)
        .order_by(ValuationRun.created_at.desc(), ValuationRun.id.desc())
        .offset(offset)
        .limit(limit)
    ).all()
    return items, total


def _calculate_valuation_payload(
    snapshot: dict[str, object],
    user_assumptions: dict[str, object],
) -> dict[str, Any]:
    financial_pack = _dict(snapshot.get("financial_evidence_pack"))
    memo_inputs = _dict(snapshot.get("memo_inputs"))
    valuation_inputs = _derive_valuation_inputs(financial_pack)
    input_gaps = _derive_valuation_input_gaps(financial_pack, valuation_inputs)
    analyst_matrices = [
        item for item in _list(snapshot.get("analyst_parameter_matrices")) if isinstance(item, dict)
    ]
    suggested_assumptions = _derive_assumptions(
        financial_pack,
        memo_inputs,
        input_gaps,
        analyst_matrices,
    )
    analyst_snapshot = _dict(suggested_assumptions.get("analyst_parameter_matrix_snapshot"))
    user_confirmed = bool(user_assumptions)
    final_assumptions = (
        _deep_merge(suggested_assumptions, user_assumptions) if user_confirmed else {}
    )
    configured_model_weights = _resolve_model_weights(
        final_assumptions if user_confirmed else suggested_assumptions
    )
    if user_confirmed:
        parameter_sources = _dict(final_assumptions.get("parameter_sources"))
        parameter_sources["user_adjusted"] = sorted(user_assumptions.keys())
        final_assumptions["parameter_sources"] = parameter_sources
    if user_confirmed:
        method_results = [
            _calculate_dcf(valuation_inputs, final_assumptions, input_gaps),
            _calculate_owner_earnings(valuation_inputs, final_assumptions, input_gaps),
            _calculate_residual_income(valuation_inputs, final_assumptions, input_gaps),
            _calculate_dividend_discount(valuation_inputs, final_assumptions, input_gaps),
            _calculate_asset_value(valuation_inputs, input_gaps),
        ]
        for method_result in method_results:
            method = _safe_str(method_result.get("method"))
            method_result["applicability"] = configured_model_weights.get(method, 0.0)
        intrinsic_value_range, weighting, dispersion_warning = _combine_method_results(
            method_results,
            valuation_inputs,
        )
    else:
        method_results = []
        intrinsic_value_range = {
            "total_equity_value": {},
            "per_share_value": {},
            "currency": "CNY",
            "status": "needs_user_confirmation",
        }
        weighting = []
        dispersion_warning = None
    confidence, confidence_summary = _build_confidence_summary(
        input_gaps=input_gaps,
        method_results=method_results,
        dispersion_warning=dispersion_warning,
    )
    return {
        "forbidden_price_inputs": {
            "price_blind": True,
            "forbidden_fields": sorted(FORBIDDEN_PRICE_FIELDS),
            "forbidden_terms": list(FORBIDDEN_PRICE_TERMS),
            "scrubbed_items": _dict(snapshot.get("price_blind_boundary")).get(
                "scrubbed_items",
                [],
            ),
        },
        "valuation_inputs": valuation_inputs,
        "model_suggested_assumptions": suggested_assumptions,
        "user_adjusted_assumptions": user_assumptions,
        "assumptions": final_assumptions,
        "methods": {
            "selected_methods": [
                "dcf",
                "owner_earnings",
                "residual_income",
                "dividend_discount",
                "asset_value",
            ],
            "reserved_methods": [],
            "base_weights": configured_model_weights,
            "default_base_weights": dict(parameter_value("valuation_models.model_weights", {})),
            "forecast_years": int(parameter_value("valuation_models.forecast_years", 5)),
        },
        "results": {
            "title": "无锚定估值实验",
            "price_blind": True,
            "status": (
                "calculated_after_user_confirmation"
                if user_confirmed
                else "needs_user_confirmation"
            ),
            "method_results": method_results,
            "model_weighting": weighting,
            "intrinsic_value_range": intrinsic_value_range,
            "valuation_input_gaps": input_gaps,
            "dispersion_warning": dispersion_warning,
            "dynamic_safety_margin": analyst_snapshot.get("dynamic_safety_margin"),
            "dynamic_safety_margin_contributions": analyst_snapshot.get(
                "dynamic_safety_margin_contributions", []
            ),
            "dynamic_safety_margin_policy": analyst_snapshot.get(
                "dynamic_safety_margin_policy", {}
            ),
            "analyst_weight_snapshot": analyst_snapshot.get("analyst_weights", []),
            "dynamic_safety_margin_formula_version": "010_dynamic_safety_margin_v2",
            "next_step": (
                "参数已确认，估值结果已生成。" if user_confirmed else "请先确认或调整模型建议参数。"
            ),
        },
        "sensitivity": (
            _build_sensitivity(valuation_inputs, final_assumptions) if user_confirmed else {}
        ),
        "confidence": confidence,
        "confidence_summary": confidence_summary,
        "source_map": _dict(memo_inputs.get("source_map")),
    }


def _derive_valuation_inputs(financial_pack: dict[str, object]) -> dict[str, object]:
    facts = _dict(financial_pack.get("financial_facts"))
    latest = _dict(facts.get("latest"))
    metrics = _dict(financial_pack.get("financial_metrics"))
    profitability = _dict(metrics.get("profitability"))
    balance_sheet = _dict(financial_pack.get("balance_sheet_adjustment"))
    capital_allocation = _dict(financial_pack.get("capital_allocation"))
    trends = _dict(financial_pack.get("financial_trends"))
    normalized = _derive_normalized_financial_bases(financial_pack)
    normalized_base_values = _dict(normalized.get("values"))
    normalized_metrics = _dict(normalized.get("metrics"))
    normalized_fcf = _dict(normalized_metrics.get("free_cash_flow"))
    normalized_profit = _dict(normalized_metrics.get("net_profit"))
    normalized_owner_earnings = _dict(normalized_metrics.get("owner_earnings"))
    return {
        "base_revenue": normalized_base_values.get("revenue"),
        "base_gross_profit": normalized_base_values.get("gross_profit"),
        "base_net_profit": normalized_profit.get("value"),
        "base_deducted_net_profit": normalized_metrics.get("deducted_net_profit", {}).get("value")
        if isinstance(normalized_metrics.get("deducted_net_profit"), dict)
        else None,
        "base_operating_cash_flow": normalized_base_values.get("operating_cash_flow"),
        "base_free_cash_flow": normalized_fcf.get("value"),
        "base_period_method": normalized.get("method"),
        "base_period_type": normalized.get("period_type"),
        "base_source_periods": normalized.get("source_periods", []),
        "base_free_cash_flow_source": "normalized_free_cash_flow",
        "normalized_free_cash_flow": normalized_fcf.get("value"),
        "normalization_method": normalized.get("method"),
        "normalization_confidence": normalized_fcf.get("confidence", "low"),
        "latest_period_type": normalized.get("latest_period_type"),
        "latest_period_used_as_dcf_base": normalized.get("latest_period_used_as_dcf_base", False),
        "normalization_adjustments": normalized_fcf.get("adjustments", []),
        "normalization_warnings": normalized.get("warnings", []),
        "normalization_source_periods": normalized_fcf.get("source_periods", []),
        "normalized_fcf_to_net_profit": normalized_fcf.get("fcf_to_net_profit"),
        "net_profit_normalization_method": normalized_profit.get("method"),
        "net_profit_source_periods": normalized_profit.get("source_periods", []),
        "net_profit_normalization_confidence": normalized_profit.get("confidence", "low"),
        "owner_earnings_base": normalized_owner_earnings.get("value"),
        "owner_earnings_normalization_method": normalized_owner_earnings.get("method"),
        "owner_earnings_source_periods": normalized_owner_earnings.get("source_periods", []),
        "owner_earnings_normalization_confidence": normalized_owner_earnings.get(
            "confidence", "low"
        ),
        "owner_earnings_normalization": normalized_owner_earnings,
        "free_cash_flow_normalization": normalized_fcf,
        "net_profit_normalization": normalized_profit,
        "normalization_audit": normalized.get("audit", {}),
        "normalization_year_weights": normalized.get("year_weights", []),
        "capital_expenditure": normalized_base_values.get("capital_expenditure"),
        "depreciation_and_amortization": normalized_base_values.get(
            "depreciation_and_amortization"
        ),
        "working_capital_change": normalized_base_values.get("working_capital_change"),
        "cash_and_equivalents": _num(balance_sheet.get("cash_and_equivalents"))
        or _num(latest.get("cash_and_equivalents")),
        "interest_bearing_debt": _num(balance_sheet.get("interest_bearing_debt"))
        or _num(latest.get("interest_bearing_debt")),
        "net_cash": _num(balance_sheet.get("net_cash")) or _num(latest.get("net_cash")),
        "shareholders_equity": _num(latest.get("shareholders_equity")),
        "total_assets": _num(latest.get("total_assets")),
        "total_liabilities": _num(latest.get("total_liabilities")),
        "dividend": normalized_base_values.get("dividend"),
        "shares_outstanding": _num(capital_allocation.get("shares_outstanding"))
        or _num(latest.get("shares_outstanding")),
        "roe": _num(profitability.get("roe")),
        "gross_margin": _num(profitability.get("gross_margin")),
        "net_margin": _num(profitability.get("net_margin")),
        "revenue_cagr_3y": _num(trends.get("revenue_cagr_3y")),
        "revenue_cagr_5y": _num(trends.get("revenue_cagr_5y")),
        "net_profit_cagr_3y": _num(trends.get("net_profit_cagr_3y")),
        "net_profit_cagr_5y": _num(trends.get("net_profit_cagr_5y")),
        "free_cash_flow_cagr_3y": _num(trends.get("free_cash_flow_cagr_3y")),
        "free_cash_flow_cagr_5y": _num(trends.get("free_cash_flow_cagr_5y")),
        "latest_period": financial_pack.get("latest_period"),
    }


def _derive_normalized_statement_bases(financial_pack: dict[str, object]) -> dict[str, object]:
    facts = _dict(financial_pack.get("financial_facts"))
    series = _dict(facts.get("series"))
    latest_period = _safe_str(financial_pack.get("latest_period"))
    latest_period_type = _period_type(latest_period)
    fields = [
        "revenue",
        "gross_profit",
        "net_profit",
        "deducted_net_profit",
        "operating_cash_flow",
        "capital_expenditure",
        "depreciation_and_amortization",
        "working_capital_change",
        "dividend",
    ]
    values: dict[str, float | None] = {}
    method = "latest_period"
    source_periods: list[str] = [latest_period] if latest_period else []
    for field in fields:
        derived = _derive_normalized_series_value(
            series=series,
            field=field,
            latest_period=latest_period,
            latest_period_type=latest_period_type,
        )
        values[field] = derived["value"]
        if derived["method"] == "ttm_adjusted":
            method = "ttm_adjusted"
            source_periods = list(derived["source_periods"])
        elif method != "ttm_adjusted" and derived["method"] == "latest_annual":
            method = "latest_annual"
            source_periods = list(derived["source_periods"])
    return {
        "values": values,
        "method": method,
        "period_type": (
            "ttm"
            if method == "ttm_adjusted"
            else "annual"
            if method == "latest_annual"
            else latest_period_type
        ),
        "source_periods": source_periods,
    }


def _derive_normalized_series_value(
    *,
    series: dict[str, object],
    field: str,
    latest_period: str,
    latest_period_type: str,
) -> dict[str, object]:
    values_by_period = _series_value_by_period(series, field)
    if latest_period_type in {"half_year", "quarter"}:
        ttm_value = _derive_ttm_value(values_by_period, latest_period, latest_period_type)
        if ttm_value is not None:
            return {
                "value": ttm_value["value"],
                "method": "ttm_adjusted",
                "source_periods": ttm_value["source_periods"],
            }
    annual_items = [
        {"period": period, "value": value}
        for period, value in values_by_period.items()
        if _period_type(period) == "annual"
    ]
    if annual_items:
        latest_annual = annual_items[0]
        return {
            "value": latest_annual["value"],
            "method": "latest_annual",
            "source_periods": [latest_annual["period"]],
        }
    return {
        "value": values_by_period.get(latest_period),
        "method": "latest_period",
        "source_periods": [latest_period] if latest_period else [],
    }


def _derive_normalized_free_cash_flow(financial_pack: dict[str, object]) -> dict[str, object]:
    facts = _dict(financial_pack.get("financial_facts"))
    series = _dict(facts.get("series"))
    latest_period = _safe_str(financial_pack.get("latest_period"))
    latest_period_type = _period_type(latest_period)
    warnings: list[str] = []
    adjustments: list[dict[str, object]] = []
    normalization_weights = _normalization_year_weights()

    fcf_by_period = _series_value_by_period(series, "free_cash_flow")
    profit_by_period = _series_value_by_period(series, "net_profit")
    annual_fcf = [
        {"period": period, "value": value}
        for period, value in fcf_by_period.items()
        if _period_type(period) == "annual"
    ]
    annual_profit = [
        {"period": period, "value": value}
        for period, value in profit_by_period.items()
        if _period_type(period) == "annual"
    ]

    if latest_period_type in {"half_year", "quarter"}:
        warnings.append("最新期为季报或中报，单期自由现金流不直接作为 DCF 基数。")

    ttm_fcf = _derive_ttm_fcf(fcf_by_period, latest_period, latest_period_type)
    source_periods: list[str] = []
    method: str | None = None
    confidence = "low"
    value: float | None = None

    if ttm_fcf is not None:
        value = ttm_fcf["value"]
        method = "ttm_adjusted"
        confidence = "medium"
        source_periods = ttm_fcf["source_periods"]
    elif len(annual_fcf) >= 3:
        value = _weighted_values(
            [item["value"] for item in annual_fcf[:3]],
            normalization_weights[:3],
        )
        method = "weighted_annual_3y"
        confidence = "high"
        source_periods = [str(item["period"]) for item in annual_fcf[:3]]
    elif len(annual_fcf) == 2:
        value = _weighted_values(
            [item["value"] for item in annual_fcf],
            normalization_weights[:2],
        )
        method = "weighted_annual_available"
        confidence = "medium"
        source_periods = [str(item["period"]) for item in annual_fcf]
        warnings.append("可用完整年度自由现金流不足三年，已使用可用年度加权平均。")
    elif len(annual_fcf) == 1:
        value = float(annual_fcf[0]["value"])
        method = "latest_annual_adjusted"
        confidence = "low"
        source_periods = [str(annual_fcf[0]["period"])]
        warnings.append("可用完整年度自由现金流不足三年，仅使用最近完整年度，需降低置信度。")
    elif latest_period_type in {"half_year", "quarter"}:
        warnings.append("缺少完整年度或 TTM 自由现金流，DCF 基数无法自动派生。")

    if value is not None and latest_period_type in {"half_year", "quarter"} and ttm_fcf is None:
        warnings.append("缺少去年同期现金流，无法构造 TTM，已退回完整年度口径。")

    if method == "ttm_adjusted":
        normalized_profit = _num(
            _derive_normalized_series_value(
                series=series,
                field="net_profit",
                latest_period=latest_period,
                latest_period_type=latest_period_type,
            ).get("value")
        )
    else:
        normalized_profit = _matching_normalized_profit(
            annual_profit=annual_profit,
            source_periods=source_periods,
        )
    fcf_to_net_profit = (
        value / normalized_profit
        if value is not None and normalized_profit is not None and normalized_profit > 0
        else None
    )
    if value is not None and normalized_profit is not None and normalized_profit > 0:
        fcf_profit_cap = float(parameter_value("valuation_models.fcf_profit_cap", 1.30))
        cap = normalized_profit * fcf_profit_cap
        if value > cap:
            cap_text = f"{fcf_profit_cap:g}"
            adjustments.append(
                {
                    "type": "cash_conversion_cap",
                    "from": value,
                    "to": cap,
                    "reason": f"正常化 FCF/净利润超过 {cap_text}，已限制 DCF 基数。",
                }
            )
            value = cap
            confidence = "low" if confidence == "medium" else confidence
            warnings.append(
                f"正常化 FCF/净利润超过 {cap_text}，已按 {cap_text} 倍净利润设置保守上限。"
            )
        elif fcf_to_net_profit is not None:
            weak_threshold = float(parameter_value("valuation_models.fcf_profit_weak", 0.60))
            if fcf_to_net_profit < weak_threshold:
                threshold_text = f"{weak_threshold:g}"
                warnings.append(
                    f"正常化 FCF/净利润低于 {threshold_text}，现金转化偏弱，基准置信度已降低。"
                )
                confidence = "low"

    return {
        "value": value,
        "method": method,
        "confidence": confidence if value is not None else "low",
        "latest_period_type": latest_period_type,
        "latest_period_used_as_dcf_base": (
            latest_period_type == "annual" and method == "latest_annual_adjusted"
        ),
        "adjustments": adjustments,
        "warnings": warnings,
        "source_periods": source_periods,
        "fcf_to_net_profit": fcf_to_net_profit,
    }


def _derive_normalized_financial_bases(financial_pack: dict[str, object]) -> dict[str, object]:
    """Build one shared period basis for profit, FCF and owner earnings.

    The selected periods are determined before any aggregation. This prevents an
    annual-weighted profit from being combined with a single-period capex or
    working-capital value.
    """
    facts = _dict(financial_pack.get("financial_facts"))
    series = _dict(facts.get("series"))
    latest_period = _safe_str(financial_pack.get("latest_period"))
    latest_period_type = _period_type(latest_period)
    fields = (
        "revenue",
        "gross_profit",
        "net_profit",
        "deducted_net_profit",
        "operating_cash_flow",
        "capital_expenditure",
        "depreciation_and_amortization",
        "working_capital_change",
        "dividend",
        "free_cash_flow",
    )
    values_by_field = {field: _series_value_by_period(series, field) for field in fields}
    year_weights = _normalization_year_weights()
    warnings: list[str] = []
    method: str | None = None
    period_type = "unknown"
    source_periods: list[str] = []
    selected_weights: list[float] = []
    period_records: list[dict[str, object]] = []
    normalized_values: dict[str, float | None] = {field: None for field in fields}
    normalized_values["owner_earnings"] = None
    metric_confidence = "low"

    ttm_values: dict[str, float | None] = {}
    if latest_period_type in {"half_year", "quarter"}:
        ttm_candidates = {
            field: _derive_ttm_value(values_by_field[field], latest_period, latest_period_type)
            for field in fields
        }
        has_core_ttm = all(
            ttm_candidates[field] is not None for field in ("net_profit", "free_cash_flow")
        )
        if has_core_ttm:
            method = "ttm_adjusted"
            period_type = "ttm"
            metric_confidence = "medium"
            source_periods = list(ttm_candidates["net_profit"]["source_periods"])
            ttm_values = {
                field: (
                    float(ttm_candidates[field]["value"])
                    if ttm_candidates[field] is not None
                    else None
                )
                for field in fields
            }
            period_records = [
                {
                    "period": period,
                    "weight": None,
                    "components": {
                        field: values_by_field[field].get(period) for field in fields
                    },
                }
                for period in source_periods
            ]
            normalized_values.update(ttm_values)
        else:
            warnings.append("最新中报或季报缺少完整的 FCF 与净利润 TTM 组件，已尝试完整年度口径。")

    if method is None:
        annual_periods = sorted(
            set(
                period
                for period in values_by_field["net_profit"]
                if _period_type(period) == "annual"
            )
            & {
                period
                for period in values_by_field["free_cash_flow"]
                if _period_type(period) == "annual"
            },
            key=lambda period: (_period_year(period) or -1, period),
            reverse=True,
        )
        source_periods = annual_periods[:3]
        if source_periods:
            selected_weights = _renormalize_year_weights(year_weights, len(source_periods))
            method = (
                "weighted_annual_3y"
                if len(source_periods) == 3
                else "latest_annual_adjusted"
                if len(source_periods) == 1
                else "weighted_annual_available"
            )
            period_type = "annual"
            metric_confidence = {3: "high", 2: "medium", 1: "low"}[len(source_periods)]
            period_records = []
            for period, weight in zip(source_periods, selected_weights, strict=True):
                components = {field: values_by_field[field].get(period) for field in fields}
                owner = _owner_earnings_from_components(components)
                period_records.append(
                    {
                        "period": period,
                        "weight": weight,
                        "components": components,
                        "owner_earnings": owner,
                    }
                )
            for field in fields:
                normalized_values[field] = _weighted_complete_metric(
                    [record["components"].get(field) for record in period_records],
                    selected_weights,
                )
            owner_values = [record.get("owner_earnings") for record in period_records]
            normalized_values["owner_earnings"] = _weighted_complete_metric(
                [
                    owner.get("value") if isinstance(owner, dict) else None
                    for owner in owner_values
                ],
                selected_weights,
            )
            if len(source_periods) == 2:
                warnings.append("可用完整年度不足三年，已将前两年权重重新归一化为 62.5%/37.5%。")
            elif len(source_periods) == 1:
                warnings.append("可用完整年度只有一年，已使用最近完整年度并降低置信度。")
        else:
            warnings.append(
                "没有可用完整年度，且无法构造 TTM；"
                "不使用未年度化中报或季报作为估值基数。"
            )

    if method is None:
        normalized_values = {field: None for field in fields}
        normalized_values["owner_earnings"] = None
        metric_confidence = "low"

    owner_components = _owner_earnings_components_for_basis(
        period_records=period_records,
        normalized_values=normalized_values,
        method=method,
    )
    normalized_values["owner_earnings"] = owner_components.get("value")
    if method == "ttm_adjusted":
        selected_weights = []

    metrics: dict[str, dict[str, object]] = {}
    for field in fields:
        metrics[field] = {
            "value": normalized_values.get(field),
            "method": method,
            "source_periods": list(source_periods),
            "confidence": metric_confidence,
            "annual_weights": list(selected_weights),
        }
    owner_confidence = (
        metric_confidence if normalized_values.get("owner_earnings") is not None else "low"
    )
    metrics["owner_earnings"] = {
        "value": normalized_values.get("owner_earnings"),
        "method": method,
        "source_periods": list(source_periods),
        "confidence": owner_confidence,
        "annual_weights": list(selected_weights),
        "components": owner_components,
    }

    fcf_value = _num(metrics["free_cash_flow"].get("value"))
    fcf_value_before_cap = fcf_value
    profit_value = _num(metrics["net_profit"].get("value"))
    fcf_adjustments: list[dict[str, object]] = []
    fcf_to_profit_before_cap: float | None = None
    fcf_to_profit: float | None = None
    if fcf_value is not None and profit_value is not None and profit_value > 0:
        fcf_to_profit_before_cap = fcf_value / profit_value
        fcf_profit_cap = float(parameter_value("valuation_models.fcf_profit_cap", 1.30))
        cap = profit_value * fcf_profit_cap
        if fcf_value > cap:
            fcf_adjustments.append(
                {
                    "type": "cash_conversion_cap",
                    "from": fcf_value,
                    "to": cap,
                    "matched_normalized_net_profit": profit_value,
                    "fcf_to_net_profit_before_cap": fcf_to_profit_before_cap,
                    "fcf_to_net_profit_after_cap": fcf_profit_cap,
                    "source_periods": list(source_periods),
                    "reason": (
                        f"正常化 FCF/同口径正常化净利润超过 {fcf_profit_cap:g}，"
                        "已限制 DCF 基数。"
                    ),
                }
            )
            fcf_value = cap
            metrics["free_cash_flow"]["value"] = cap
            normalized_values["free_cash_flow"] = cap
            if metric_confidence == "medium":
                metric_confidence = "low"
            warnings.append(
                f"正常化 FCF/同口径正常化净利润超过 {fcf_profit_cap:g}，"
                "已按同口径净利润设置保守上限。"
            )
        fcf_to_profit = fcf_value / profit_value
        weak_threshold = float(parameter_value("valuation_models.fcf_profit_weak", 0.60))
        if fcf_to_profit < weak_threshold:
            warnings.append(
                f"正常化 FCF/同口径正常化净利润低于 {weak_threshold:g}，"
                "现金转化偏弱，仅降低置信度。"
            )
            metric_confidence = "low"
    for metric in metrics.values():
        metric["confidence"] = metric_confidence
    metrics["free_cash_flow"]["adjustments"] = fcf_adjustments
    metrics["free_cash_flow"]["value_before_cap"] = fcf_value_before_cap
    metrics["free_cash_flow"]["value_after_cap"] = fcf_value
    metrics["free_cash_flow"]["fcf_to_net_profit"] = fcf_to_profit
    metrics["free_cash_flow"]["fcf_to_net_profit_before_cap"] = (
        fcf_to_profit_before_cap
        if fcf_value is not None and profit_value is not None and profit_value > 0
        else None
    )
    metrics["free_cash_flow"]["warnings"] = list(warnings)

    audit = {
        "policy": {
            "ttm_formula": "上一完整年度 + 本年最新累计期 - 上年同期累计期",
            "annual_formula": "最近三个完整年度按配置权重加权；可用年度不足时对可用权重重新归一化",
            "annual_weights_config": list(year_weights),
            "capital_expenditure_policy": "全部资本开支作为维持性资本开支保守代理",
            "unannualized_interim_fallback": False,
        },
        "method": method,
        "period_type": period_type,
        "source_periods": list(source_periods),
        "annual_weights": list(selected_weights),
        "periods": period_records,
        "final_values": {
            "net_profit": metrics["net_profit"].get("value"),
            "free_cash_flow": metrics["free_cash_flow"].get("value"),
            "owner_earnings": metrics["owner_earnings"].get("value"),
        },
        "fcf_conversion": {
            "matched_normalized_net_profit": profit_value,
            "normalized_fcf_before_cap": fcf_value_before_cap,
            "normalized_fcf_after_cap": fcf_value,
            "fcf_to_net_profit_before_cap": (
                fcf_to_profit_before_cap
                if fcf_value is not None and profit_value is not None and profit_value > 0
                else None
            ),
            "fcf_to_net_profit_after_cap": fcf_to_profit,
            "profit_cap_multiple": parameter_value("valuation_models.fcf_profit_cap", 1.30),
            "weak_conversion_threshold": parameter_value("valuation_models.fcf_profit_weak", 0.60),
        },
        "fcf_cap_adjustments": fcf_adjustments,
        "warnings": list(warnings),
    }
    return {
        "values": normalized_values,
        "metrics": metrics,
        "method": method,
        "period_type": period_type,
        "latest_period_type": latest_period_type,
        "source_periods": list(source_periods),
        "year_weights": list(selected_weights),
        "confidence": metric_confidence,
        "latest_period_used_as_dcf_base": (
            latest_period_type == "annual" and method == "latest_annual_adjusted"
        ),
        "warnings": warnings,
        "audit": audit,
    }


def _owner_earnings_components_for_basis(
    *,
    period_records: list[dict[str, object]],
    normalized_values: dict[str, float | None],
    method: str | None,
) -> dict[str, object]:
    if method == "ttm_adjusted":
        components = {
            "net_profit": normalized_values.get("net_profit"),
            "depreciation_and_amortization": normalized_values.get(
                "depreciation_and_amortization"
            ),
            "capital_expenditure": normalized_values.get("capital_expenditure"),
            "working_capital_cash_effect": normalized_values.get("working_capital_change"),
        }
        return _owner_earnings_from_components(components)
    values = [record.get("owner_earnings") for record in period_records]
    if any(not isinstance(value, dict) or value.get("value") is None for value in values):
        return {
            "value": None,
            "formula": (
                "net_profit + depreciation_and_amortization - total_capital_expenditure "
                "- max(-working_capital_cash_effect, 0)"
            ),
            "components": [],
            "reason": "至少一个共同年度缺少净利润或资本开支，无法保持所有者盈余组件期间一致。",
        }
    return {
        "value": normalized_values.get("owner_earnings"),
        "formula": "先逐年计算所有者盈余，再按统一年度权重加权",
        "components": values,
    }


def _owner_earnings_from_components(components: dict[str, object]) -> dict[str, object]:
    net_profit = _num(components.get("net_profit"))
    capital_expenditure = _num(components.get("capital_expenditure"))
    working_capital_raw = components.get(
        "working_capital_cash_effect", components.get("working_capital_change")
    )
    if net_profit is None or capital_expenditure is None:
        return {
            "value": None,
            "components": {
                "net_profit": net_profit,
                "depreciation_and_amortization": _num(
                    components.get("depreciation_and_amortization")
                ),
                "capital_expenditure": capital_expenditure,
                "working_capital_cash_effect": _num(
                    working_capital_raw
                ),
            },
        }
    depreciation = _num(components.get("depreciation_and_amortization")) or 0.0
    working_capital = _num(working_capital_raw) or 0.0
    investment = max(-working_capital, 0.0)
    return {
        "value": net_profit + depreciation - capital_expenditure - investment,
        "components": {
            "net_profit": net_profit,
            "depreciation_and_amortization": depreciation,
            "capital_expenditure": capital_expenditure,
            "working_capital_cash_effect": working_capital,
            "working_capital_investment_deducted": investment,
        },
    }


def _weighted_complete_metric(values: list[object], weights: list[float]) -> float | None:
    numbers = [_num(value) for value in values]
    if len(numbers) != len(weights) or any(value is None for value in numbers):
        return None
    return _weighted_values([float(value) for value in numbers if value is not None], weights)


def _normalization_year_weights() -> list[float]:
    raw = parameter_value("valuation_models.normalization_year_weights", [0.50, 0.30, 0.20])
    if not isinstance(raw, list) or len(raw) != 3:
        return [0.50, 0.30, 0.20]
    values = [_num(value) for value in raw]
    if any(value is None or value < 0 for value in values):
        return [0.50, 0.30, 0.20]
    total = sum(value for value in values if value is not None)
    return [float(value) / total for value in values] if total > 0 else [0.50, 0.30, 0.20]


def _renormalize_year_weights(weights: list[float], count: int) -> list[float]:
    selected = weights[:count]
    total = sum(selected)
    if total <= 0:
        return [1.0 / count] * count
    return [value / total for value in selected]


def _derive_ttm_fcf(
    fcf_by_period: dict[str, float],
    latest_period: str,
    latest_period_type: str,
) -> dict[str, object] | None:
    return _derive_ttm_value(fcf_by_period, latest_period, latest_period_type)


def _derive_ttm_value(
    values_by_period: dict[str, float],
    latest_period: str,
    latest_period_type: str,
) -> dict[str, object] | None:
    if latest_period_type not in {"half_year", "quarter"}:
        return None
    latest_value = values_by_period.get(latest_period)
    if latest_value is None:
        return None
    latest_year = _period_year(latest_period)
    latest_suffix = _period_suffix(latest_period)
    if latest_year is None or not latest_suffix:
        return None
    latest_annual_period = _find_annual_period(values_by_period, latest_year - 1)
    prior_interim_period = _find_period_by_suffix(
        values_by_period,
        latest_year - 1,
        latest_suffix,
    )
    if latest_annual_period is None or prior_interim_period is None:
        return None
    value = (
        values_by_period[latest_annual_period]
        + latest_value
        - values_by_period[prior_interim_period]
    )
    return {
        "value": value,
        "source_periods": [latest_annual_period, latest_period, prior_interim_period],
    }


def _series_value_by_period(series: dict[str, object], field: str) -> dict[str, float]:
    values: dict[str, float] = {}
    for item in _list(series.get(field)):
        if not isinstance(item, dict):
            continue
        period = _safe_str(item.get("period"))
        value = _num(item.get("value"))
        if period and value is not None:
            values[period] = value
    return values


def _weighted_values(values: list[float], weights: list[float]) -> float:
    usable = list(zip(values, weights, strict=False))
    total_weight = sum(weight for _, weight in usable)
    if total_weight <= 0:
        return 0.0
    return sum(value * weight for value, weight in usable) / total_weight


def _matching_normalized_profit(
    *,
    annual_profit: list[dict[str, object]],
    source_periods: list[str],
) -> float | None:
    if not annual_profit:
        return None
    source_set = set(source_periods)
    matching = [
        float(item["value"])
        for item in annual_profit
        if str(item["period"]) in source_set and _num(item["value"]) is not None
    ]
    if len(matching) >= 3:
        return _weighted_values(
            matching[:3],
            _normalization_year_weights()[:3],
        )
    if len(matching) == 2:
        return _weighted_values(
            matching,
            _normalization_year_weights()[:2],
        )
    if len(matching) == 1:
        return matching[0]
    latest = _num(annual_profit[0].get("value"))
    return latest


def _period_type(period: str) -> str:
    normalized = period.strip().upper()
    if not normalized:
        return "unknown"
    if normalized.endswith("A") or "ANNUAL" in normalized or "年报" in period or "年度" in period:
        return "annual"
    if (
        "H1" in normalized
        or "HY" in normalized
        or "06-30" in normalized
        or "中报" in period
        or "半年度" in period
    ):
        return "half_year"
    if (
        "Q1" in normalized
        or "Q2" in normalized
        or "Q3" in normalized
        or "Q4" in normalized
        or "03-31" in normalized
        or "09-30" in normalized
        or "季报" in period
    ):
        return "quarter"
    return "unknown"


def _period_year(period: str) -> int | None:
    digits = "".join(char for char in period if char.isdigit())
    if len(digits) < 4:
        return None
    return int(digits[:4])


def _period_suffix(period: str) -> str:
    normalized = period.strip().upper()
    for suffix in ("H1", "Q1", "Q2", "Q3", "Q4"):
        if suffix in normalized:
            return suffix
    if "06-30" in normalized or "中报" in period or "半年度" in period:
        return "H1"
    if "03-31" in normalized:
        return "Q1"
    if "09-30" in normalized:
        return "Q3"
    return ""


def _find_annual_period(values_by_period: dict[str, float], year: int) -> str | None:
    for period in values_by_period:
        if _period_year(period) == year and _period_type(period) == "annual":
            return period
    return None


def _find_period_by_suffix(
    values_by_period: dict[str, float],
    year: int,
    suffix: str,
) -> str | None:
    for period in values_by_period:
        if _period_year(period) == year and _period_suffix(period) == suffix:
            return period
    return None


def _derive_valuation_input_gaps(
    financial_pack: dict[str, object],
    valuation_inputs: dict[str, object],
) -> list[dict[str, object]]:
    gaps: list[dict[str, object]] = []
    seen: set[str] = set()
    for item in _list(financial_pack.get("financial_data_gaps")):
        if not isinstance(item, dict):
            continue
        needed_by = _str_list(item.get("needed_by"))
        if "valuation_lab" not in needed_by:
            continue
        field = str(item.get("field") or "")
        if not field or field in seen:
            continue
        seen.add(field)
        gaps.append(
            {
                "field": field,
                "severity": str(item.get("severity") or "medium"),
                "reason": str(item.get("reason") or "估值输入缺失。"),
                "replacement_available": bool(item.get("replacement_available", False)),
                "source": "financial_evidence_pack",
            }
        )

    for field, reason in (
        ("base_net_profit", "缺少基准净利润，所有者盈余估值无法运行。"),
        ("base_free_cash_flow", "缺少基准自由现金流，DCF 无法运行。"),
        ("owner_earnings_base", "缺少正常化所有者盈余，所有者盈余估值无法运行。"),
    ):
        if valuation_inputs.get(field) is None and field not in seen:
            gaps.append(
                {
                    "field": field,
                    "severity": "high",
                    "reason": reason,
                    "replacement_available": False,
                    "source": "valuation_input_derivation",
                }
            )
            seen.add(field)
    shared_history_method = valuation_inputs.get("normalization_method") in {
        "weighted_annual_available",
        "latest_annual_adjusted",
    }
    if shared_history_method and "normalized_free_cash_flow_history" not in seen:
        gaps.append(
            {
                "field": "normalized_free_cash_flow_history",
                "severity": "low",
                "reason": (
                    "可用完整年度不足三年，已对可用年度重新归一化，"
                    "估值允许运行但需降低置信度。"
                ),
                "replacement_available": True,
                "source": "valuation_input_derivation",
            }
        )
        seen.add("normalized_free_cash_flow_history")
    if (
        valuation_inputs.get("base_free_cash_flow") is not None
        and valuation_inputs.get("latest_period_type") in {"half_year", "quarter"}
        and valuation_inputs.get("normalization_method") != "ttm_adjusted"
        and "ttm_free_cash_flow" not in seen
    ):
        gaps.append(
            {
                "field": "ttm_free_cash_flow",
                "severity": "low",
                "reason": "最新期为季报或中报但无法构造共同口径 TTM，已退回完整年度口径。",
                "replacement_available": True,
                "source": "valuation_input_derivation",
            }
        )
        seen.add("ttm_free_cash_flow")
    if (
        any(
            isinstance(adjustment, dict)
            and adjustment.get("type") == "cash_conversion_cap"
            for adjustment in _list(valuation_inputs.get("normalization_adjustments"))
        )
        and "normalized_fcf_to_net_profit" not in seen
    ):
        gaps.append(
            {
                "field": "normalized_fcf_to_net_profit",
                "severity": "medium",
                "reason": "正常化 FCF/同口径净利润超过配置上限，已按保守上限处理。",
                "replacement_available": True,
                "source": "valuation_input_derivation",
            }
        )
        seen.add("normalized_fcf_to_net_profit")
    if valuation_inputs.get("shares_outstanding") is None and "shares_outstanding" not in seen:
        gaps.append(
            {
                "field": "shares_outstanding",
                "severity": "high",
                "reason": "缺少总股本，无法换算每股内在价值。",
                "replacement_available": False,
                "source": "valuation_input_derivation",
            }
        )
    return gaps


def _derive_assumptions(
    financial_pack: dict[str, object],
    memo_inputs: dict[str, object],
    input_gaps: list[dict[str, object]],
    analyst_matrices: list[dict[str, object]],
) -> dict[str, object]:
    trends = _dict(financial_pack.get("financial_trends"))
    flags = _list(financial_pack.get("financial_flags"))
    growth_priority = parameter_value("valuation_models.growth_source_priority", [])
    growth_values = (
        [trends.get(str(key)) for key in growth_priority]
        if isinstance(growth_priority, list)
        else []
    )
    fallback_growth = float(parameter_value("valuation_models.default_growth", 0.04))
    raw_growth = fallback_growth
    growth_source = "default_growth"
    if isinstance(growth_priority, list):
        for key, value in zip(growth_priority, growth_values, strict=False):
            number = _num(value)
            if number is not None:
                raw_growth = number
                growth_source = str(key)
                break
    financial_growth_min = float(parameter_value("valuation_models.financial_growth_min", -0.05))
    financial_growth_max = float(parameter_value("valuation_models.financial_growth_max", 0.12))
    financial_base_growth = _clamp(raw_growth, financial_growth_min, financial_growth_max)
    base_growth = financial_base_growth
    risk_penalty = min(
        float(parameter_value("valuation_models.discount_penalty_cap", 0.025)),
        float(parameter_value("valuation_models.flag_discount_penalty", 0.005)) * len(flags)
        + float(parameter_value("valuation_models.gap_discount_penalty", 0.003)) * len(input_gaps),
    )
    base_discount = _clamp(
        float(parameter_value("valuation_models.base_discount_rate", 0.095)) + risk_penalty,
        float(parameter_value("valuation_models.financial_discount_min", 0.08)),
        float(parameter_value("valuation_models.financial_discount_max", 0.14)),
    )
    base_terminal = float(parameter_value("valuation_models.base_terminal_growth", 0.02))
    analyst_adjustment = _derive_analyst_matrix_adjustment(
        matrices=analyst_matrices,
        input_gaps=input_gaps,
    )
    analyst_delta_growth = float(analyst_adjustment["delta_growth"])
    analyst_delta_owner_growth = float(analyst_adjustment["delta_owner_growth"])
    base_growth = _clamp(
        financial_base_growth + analyst_delta_growth,
        *_configured_bounds("growth", (-0.08, 0.16)),
    )
    base_owner_growth = _clamp(
        financial_base_growth + analyst_delta_owner_growth,
        *_configured_bounds("owner_growth", (-0.08, 0.15)),
    )
    base_discount = _clamp(
        base_discount + float(analyst_adjustment["delta_discount"]),
        *_configured_bounds("discount", (0.075, 0.16)),
    )
    base_terminal = min(
        base_discount - float(parameter_value("valuation_models.discount_terminal_gap", 0.01)),
        _clamp(
            base_terminal + float(analyst_adjustment["delta_terminal"]),
            *_configured_bounds("terminal", (0.0, 0.035)),
        ),
    )
    spread = _clamp(
        float(analyst_adjustment["scenario_spread"]),
        float(parameter_value("valuation_models.scenario_spread_min", 0.015)),
        float(parameter_value("valuation_models.scenario_spread_max", 0.08)),
    )
    conservative = parameter_value("valuation_models.scenarios.conservative", {})
    optimistic = parameter_value("valuation_models.scenarios.optimistic", {})
    conservative = conservative if isinstance(conservative, dict) else {}
    optimistic = optimistic if isinstance(optimistic, dict) else {}
    conservative_terminal = _clamp(
        base_terminal + spread * float(conservative.get("terminal_spread", -0.30)),
        *_scenario_bounds(conservative, "terminal_bounds", (0.0, 0.035)),
    )
    optimistic_terminal = _clamp(
        base_terminal + spread * float(optimistic.get("terminal_spread", 0.25)),
        *_scenario_bounds(optimistic, "terminal_bounds", (0.0, 0.035)),
    )
    if float(analyst_adjustment["permanent_loss_risk_negative"]) > float(
        parameter_value("valuation_models.permanent_loss_optimistic_cap", 0.50)
    ):
        optimistic_terminal = min(optimistic_terminal, base_terminal)
    scenario_inputs = {
        "conservative": {
            "cash_flow_growth_rate": _clamp(
                base_growth + spread * float(conservative.get("growth_spread", -1.0)),
                *_scenario_bounds(conservative, "growth_bounds", (-0.10, 0.10)),
            ),
            "owner_earnings_growth_rate": _clamp(
                base_owner_growth + spread * float(conservative.get("owner_growth_spread", -1.0)),
                *_scenario_bounds(conservative, "owner_growth_bounds", (-0.10, 0.10)),
            ),
            "discount_rate": _clamp(
                base_discount + spread * float(conservative.get("discount_spread", 0.60)),
                *_scenario_bounds(conservative, "discount_bounds", (0.09, 0.18)),
            ),
            "terminal_growth_rate": conservative_terminal,
        },
        "base": {
            "cash_flow_growth_rate": base_growth,
            "owner_earnings_growth_rate": base_owner_growth,
            "discount_rate": base_discount,
            "terminal_growth_rate": base_terminal,
        },
        "optimistic": {
            "cash_flow_growth_rate": _clamp(
                base_growth + spread * float(optimistic.get("growth_spread", 1.0)),
                *_scenario_bounds(optimistic, "growth_bounds", (-0.02, 0.18)),
            ),
            "owner_earnings_growth_rate": _clamp(
                base_owner_growth + spread * float(optimistic.get("owner_growth_spread", 1.0)),
                *_scenario_bounds(optimistic, "owner_growth_bounds", (-0.02, 0.16)),
            ),
            "discount_rate": _clamp(
                base_discount + spread * float(optimistic.get("discount_spread", -0.35)),
                *_scenario_bounds(optimistic, "discount_bounds", (0.075, 0.14)),
            ),
            "terminal_growth_rate": optimistic_terminal,
        },
    }
    return {
        "forecast_years": int(parameter_value("valuation_models.forecast_years", 5)),
        "scenarios": scenario_inputs,
        "model_weights": dict(parameter_value("valuation_models.model_weights", {})),
        "growth_basis": {
            "raw_growth_rate": raw_growth,
            "growth_source": growth_source,
            "source_priority": [str(key) for key in growth_priority]
            if isinstance(growth_priority, list)
            else [],
            "fallback_growth_rate": fallback_growth,
            "financial_growth_min": financial_growth_min,
            "financial_growth_max": financial_growth_max,
            "clamped_financial_base_growth_rate": financial_base_growth,
            "analyst_delta_cash_flow_growth_rate": analyst_delta_growth,
            "final_base_cash_flow_growth_rate": base_growth,
            "analyst_delta_owner_earnings_growth_rate": analyst_delta_owner_growth,
            "final_base_owner_earnings_growth_rate": base_owner_growth,
        },
        "source": {
            "growth": f"financial_evidence_pack.financial_trends.{growth_source}",
            "discount_rate": "rule_based_quality_and_gap_adjustment",
            "terminal_growth_rate": "system_default_with_conservative_cap",
        },
        "parameter_sources": {
            "system_default": [
                "forecast_years",
                "terminal_growth_rate_bounds",
                "model_weights",
            ],
            "financial_evidence_pack": [
                "growth_rates",
                "cash_flow_quality",
                "balance_sheet_adjustment",
                "capital_allocation",
                "valuation_readiness",
                "financial_data_gaps",
            ],
            "memo_assumption": [
                "valuation_assumption_queue",
                "key_risks",
                "counter_evidence",
                "data_gaps",
            ],
            "analyst_rule_matrix": [
                "dimension_scores",
                "quality_score",
                "growth_score",
                "risk_score",
                "scenario_spread",
            ]
            if analyst_adjustment["has_signals"]
            else [],
            "model_suggested": [],
            "user_adjusted": [],
        },
        "rules": {
            "terminal_growth_rate_max": _configured_bounds("terminal", (0.0, 0.035))[1],
            "discount_rate_min": _configured_bounds("discount", (0.075, 0.16))[0],
            "price_blind": True,
            "analyst_status_score_policy": analyst_adjustment["status_score_policy"],
        },
        "analyst_parameter_matrix_snapshot": analyst_adjustment,
        "memo_assumption_queue": memo_inputs.get("valuation_assumption_queue", []),
        "risk_adjustments": {
            "key_risks": memo_inputs.get("key_risks", []),
            "counter_evidence": memo_inputs.get("counter_evidence", []),
        },
    }


def _derive_analyst_matrix_adjustment(
    *,
    matrices: list[dict[str, object]],
    input_gaps: list[dict[str, object]],
) -> dict[str, object]:
    status_scores = parameter_value("valuation_rule_matrix.status_scores", STATUS_SCORES)
    status_scores = status_scores if isinstance(status_scores, dict) else STATUS_SCORES
    composite = parameter_value("valuation_models.composite_weights", {})
    composite = composite if isinstance(composite, dict) else {}
    quality_weights = _dict(composite.get("quality"))
    growth_weights = _dict(composite.get("growth"))
    risk_weights = _dict(composite.get("risk"))
    deltas = parameter_value("valuation_models.parameter_deltas", {})
    deltas = deltas if isinstance(deltas, dict) else {}
    impact_scale = float(parameter_value("valuation_models.analyst_impact_scale", 2.0))
    analyst_rows = []
    for matrix in matrices:
        for item in _list(matrix.get("analyst_items")):
            if not isinstance(item, dict):
                continue
            rules = [rule for rule in _list(item.get("rule_impacts")) if isinstance(rule, dict)]
            total_count = len(rules)
            if total_count == 0:
                continue
            known_count = sum(str(rule.get("status")) != "unknown" for rule in rules)
            compute_count = sum(
                rule.get("calculation_role") == "compute"
                and rule.get("price_blind_compatible") is True
                for rule in rules
            )
            analyst_min = float(parameter_value("valuation_rule_matrix.analyst_score_min", 0.2))
            analyst_max = float(parameter_value("valuation_rule_matrix.analyst_score_max", 1.0))
            fit = _clamp(_num(item.get("profile_fit_score")) or 0.6, analyst_min, analyst_max)
            confidence = _clamp(_num(item.get("data_confidence")) or 0.6, analyst_min, analyst_max)
            known_completeness = known_count / total_count
            price_blind_completeness = compute_count / total_count
            raw_weight = analyst_raw_weight(
                data_confidence=confidence,
                profile_fit_score=fit,
            )
            analyst_rows.append(
                {
                    "profile_id": item.get("profile_id"),
                    "profile_name": item.get("profile_name"),
                    "source_run_id": item.get("source_run_id"),
                    "profile_fit_score": fit,
                    "data_confidence": confidence,
                    "known_rule_completeness": known_completeness,
                    "price_blind_completeness": price_blind_completeness,
                    "raw_weight": raw_weight,
                    "rules": rules,
                }
            )

    weight_components = differentiate_and_normalize_analyst_weights(
        [float(item["raw_weight"]) for item in analyst_rows]
    )
    for item, components in zip(analyst_rows, weight_components, strict=True):
        item.update(components)

    dimension_scores: dict[str, float] = {}
    dimension_disagreement: dict[str, float] = {}
    dimension_traces: dict[str, list[dict[str, object]]] = {}
    all_compute_rules = 0
    unknown_compute_rules = 0
    rule_audit = []
    safety_margin_additions = parameter_value(
        "valuation_rule_matrix.safety_margin_additions",
        {"pass": 0.0, "neutral": 0.009, "unknown": 0.012, "warn": 0.016, "fail": 0.03},
    )
    safety_margin_additions = (
        safety_margin_additions if isinstance(safety_margin_additions, dict) else {}
    )
    safety_margin_scale = float(
        parameter_value("valuation_rule_matrix.safety_margin_analyst_scale", 8.0)
    )
    safety_margin_contributions: list[dict[str, object]] = []
    for analyst in analyst_rows:
        analyst_weight = float(analyst["weight"])
        for rule in analyst["rules"]:
            status = str(rule.get("status") or "unknown")
            status_score = float(status_scores.get(status, 0.0))
            gate = (
                rule.get("calculation_role") == "compute"
                and rule.get("price_blind_compatible") is True
            )
            if gate:
                all_compute_rules += 1
                if status == "unknown":
                    unknown_compute_rules += 1
            trace_base = {
                "profile_id": analyst["profile_id"],
                "profile_name": analyst["profile_name"],
                "source_run_id": analyst["source_run_id"],
                "rule_id": rule.get("rule_id"),
                "rule_label": rule.get("rule_label"),
                "status": status,
                "status_score": status_score,
                "analyst_weight": analyst_weight,
                "calculation_role": rule.get("calculation_role"),
                "price_blind_compatible": rule.get("price_blind_compatible"),
                "source_refs": rule.get("source_refs", {}),
                "summary": rule.get("summary"),
                "exclusion_reason": rule.get("exclusion_reason"),
            }
            rule_audit.append(
                {
                    **trace_base,
                    "dimensions": rule.get("dimensions", {}),
                }
            )
            if gate:
                margin_addition = float(safety_margin_additions.get(status, 0.0))
                safety_margin_contributions.append(
                    {
                        "profile_id": analyst["profile_id"],
                        "profile_name": analyst["profile_name"],
                        "source_run_id": analyst["source_run_id"],
                        "rule_id": rule.get("rule_id"),
                        "rule_label": rule.get("rule_label"),
                        "status": status,
                        "status_addition": margin_addition,
                        "analyst_weight": analyst_weight,
                        "analyst_scale": safety_margin_scale,
                        "contribution": margin_addition * analyst_weight * safety_margin_scale,
                    }
                )
            if not gate:
                continue
            for dimension, raw_weight in _dict(rule.get("dimensions")).items():
                dimension_weight = _num(raw_weight)
                if dimension_weight is None:
                    continue
                contribution = status_score * dimension_weight * analyst_weight
                dimension_traces.setdefault(dimension, []).append(
                    {
                        **trace_base,
                        "mapping_weight": dimension_weight,
                        "contribution": contribution,
                    }
                )

    for dimension in VALUATION_DIMENSIONS:
        traces = dimension_traces.get(dimension, [])
        denominator = sum(
            float(item["analyst_weight"]) * abs(float(item["mapping_weight"])) for item in traces
        )
        score = (
            sum(float(item["contribution"]) for item in traces) / denominator
            if denominator
            else 0.0
        )
        dimension_scores[dimension] = _clamp(
            score,
            float(parameter_value("valuation_rule_matrix.dimension_score_min", -2.0)),
            float(parameter_value("valuation_rule_matrix.dimension_score_max", 1.0)),
        )
        dimension_disagreement[dimension] = _weighted_std(
            [float(item["status_score"]) * float(item["mapping_weight"]) for item in traces],
            [float(item["analyst_weight"]) for item in traces],
        )

    disagreement_avg = (
        sum(dimension_disagreement.values()) / len(dimension_disagreement)
        if dimension_disagreement
        else 0.0
    )
    unknown_ratio = unknown_compute_rules / all_compute_rules if all_compute_rules else 1.0
    data_gap_penalty = _data_gap_penalty(input_gaps, {})

    def negative(name: str) -> float:
        return max(0.0, -dimension_scores[name])

    quality_score = (
        float(quality_weights.get("business_quality", 0.30)) * dimension_scores["business_quality"]
        + float(quality_weights.get("moat_durability", 0.25)) * dimension_scores["moat_durability"]
        + float(quality_weights.get("cash_flow_reliability", 0.20))
        * dimension_scores["cash_flow_reliability"]
        + float(quality_weights.get("management_quality", 0.15))
        * dimension_scores["management_quality"]
        + float(quality_weights.get("pricing_power", 0.10)) * dimension_scores["pricing_power"]
    )
    growth_score = (
        float(growth_weights.get("growth_runway", 0.40)) * dimension_scores["growth_runway"]
        + float(growth_weights.get("pricing_power", 0.25)) * dimension_scores["pricing_power"]
        + float(growth_weights.get("demand_durability", 0.20))
        * dimension_scores["demand_durability"]
        + float(growth_weights.get("execution_quality", 0.15))
        * dimension_scores["execution_quality"]
        - float(growth_weights.get("capital_intensity_penalty", 0.15))
        * negative("capital_intensity")
    )
    risk_score = (
        float(risk_weights.get("balance_sheet_risk", 0.25)) * negative("balance_sheet_risk")
        + float(risk_weights.get("permanent_loss_risk", 0.25)) * negative("permanent_loss_risk")
        + float(risk_weights.get("cyclicality", 0.20)) * negative("cyclicality")
        + float(risk_weights.get("accounting_quality", 0.15)) * negative("accounting_quality")
        + float(risk_weights.get("data_gap_penalty", 0.15)) * data_gap_penalty
    )
    delta_growth = impact_scale * (
        float(deltas.get("growth_growth", 0.030)) * growth_score
        + float(deltas.get("growth_quality", 0.012)) * quality_score
        + float(deltas.get("growth_risk", -0.020)) * risk_score
    )
    delta_owner_growth = impact_scale * (
        float(deltas.get("owner_growth_growth", 0.020)) * growth_score
        + float(deltas.get("owner_growth_quality", 0.018)) * quality_score
        + float(deltas.get("owner_growth_capital", -0.025)) * negative("capital_intensity")
        + float(deltas.get("owner_growth_risk", -0.018)) * risk_score
    )
    delta_discount = impact_scale * (
        float(deltas.get("discount_quality", -0.018)) * quality_score
        + float(deltas.get("discount_risk", 0.030)) * risk_score
        + float(deltas.get("discount_disagreement", 0.012)) * disagreement_avg
    )
    delta_terminal = impact_scale * (
        float(deltas.get("terminal_moat", 0.012)) * dimension_scores["moat_durability"]
        + float(deltas.get("terminal_pricing", 0.006)) * dimension_scores["pricing_power"]
        + float(deltas.get("terminal_risk", -0.014)) * risk_score
    )
    scenario_spread = _clamp(
        float(parameter_value("valuation_models.scenario_spread_base", 0.020))
        + impact_scale
        * (
            float(deltas.get("spread_risk", 0.020)) * risk_score
            + float(deltas.get("spread_disagreement", 0.012)) * disagreement_avg
            + float(deltas.get("spread_unknown", 0.012)) * unknown_ratio
        ),
        float(parameter_value("valuation_models.scenario_spread_min", 0.015)),
        float(parameter_value("valuation_models.scenario_spread_max", 0.080)),
    )
    raw_safety_margin = sum(
        float(item["contribution"]) for item in safety_margin_contributions
    )
    margin_addition_values = [float(value) for value in safety_margin_additions.values()]
    raw_safety_margin_minimum = min(margin_addition_values) * 4 * safety_margin_scale
    raw_safety_margin_maximum = max(margin_addition_values) * 4 * safety_margin_scale
    safety_margin_minimum = float(
        parameter_value("valuation_rule_matrix.safety_margin_min", 0.1)
    )
    safety_margin_maximum = float(
        parameter_value("valuation_rule_matrix.safety_margin_max", 0.5)
    )
    raw_safety_margin_range = raw_safety_margin_maximum - raw_safety_margin_minimum
    normalized_safety_margin = (
        (raw_safety_margin - raw_safety_margin_minimum) / raw_safety_margin_range
        if raw_safety_margin_range > 0
        else 0.0
    )
    dynamic_safety_margin = _clamp(
        safety_margin_minimum
        + _clamp(normalized_safety_margin, 0.0, 1.0)
        * (safety_margin_maximum - safety_margin_minimum),
        safety_margin_minimum,
        safety_margin_maximum,
    )
    return {
        "source": "latest_successful_008_analyst_view_runs",
        "has_signals": bool(analyst_rows),
        "analyst_parameter_impact_scale": impact_scale,
        "status_score_policy": dict(status_scores),
        "analyst_weights": [
            {key: value for key, value in item.items() if key != "rules"} for item in analyst_rows
        ],
        "rule_impacts": rule_audit,
        "dimension_scores": dimension_scores,
        "dimension_disagreement": dimension_disagreement,
        "dimension_disagreement_avg": disagreement_avg,
        "dimension_contributions": dimension_traces,
        "unknown_ratio": unknown_ratio,
        "data_gap_penalty": data_gap_penalty,
        "quality_score": quality_score,
        "growth_score": growth_score,
        "risk_score": risk_score,
        "permanent_loss_risk_negative": negative("permanent_loss_risk"),
        "delta_growth": delta_growth,
        "delta_owner_growth": delta_owner_growth,
        "delta_discount": delta_discount,
        "delta_terminal": delta_terminal,
        "scenario_spread": scenario_spread,
        "dynamic_safety_margin": dynamic_safety_margin,
        "dynamic_safety_margin_contributions": safety_margin_contributions,
        "dynamic_safety_margin_policy": {
            "status_additions": dict(safety_margin_additions),
            "analyst_scale": safety_margin_scale,
            "raw_margin": raw_safety_margin,
            "raw_minimum": raw_safety_margin_minimum,
            "raw_maximum": raw_safety_margin_maximum,
            "minimum": safety_margin_minimum,
            "maximum": safety_margin_maximum,
            "formula": (
                "minimum + clamp((raw_margin - raw_minimum) / "
                "(raw_maximum - raw_minimum), 0, 1) * (maximum - minimum)"
            ),
        },
    }


def _data_gap_penalty(input_gaps: list[dict[str, object]], pack: dict[str, object]) -> float:
    high = sum(1 for item in input_gaps if item.get("severity") == "high")
    medium = sum(1 for item in input_gaps if item.get("severity") == "medium")
    low = sum(1 for item in input_gaps if item.get("severity") == "low")
    pack_gaps = len(_list(pack.get("data_gaps_for_valuation")))
    penalties = parameter_value("valuation_models.gap_penalties", {})
    penalties = penalties if isinstance(penalties, dict) else {}
    return _clamp(
        float(penalties.get("high", 0.25)) * high
        + float(penalties.get("medium", 0.12)) * medium
        + float(penalties.get("low", 0.05)) * low
        + float(penalties.get("pack", 0.04)) * pack_gaps,
        0.0,
        float(parameter_value("valuation_models.gap_penalty_cap", 1.0)),
    )


def _weighted_std(values: list[float], weights: list[float]) -> float:
    if not values or not weights:
        return 0.0
    total_weight = sum(weights)
    if total_weight <= 0:
        return 0.0
    mean = sum(value * weight for value, weight in zip(values, weights, strict=False))
    mean /= total_weight
    variance = (
        sum(weight * ((value - mean) ** 2) for value, weight in zip(values, weights, strict=False))
        / total_weight
    )
    return variance**0.5


def _calculate_dcf(
    valuation_inputs: dict[str, object],
    assumptions: dict[str, object],
    input_gaps: list[dict[str, object]],
) -> dict[str, object]:
    base_fcf = _num(valuation_inputs.get("base_free_cash_flow"))
    if base_fcf is None:
        return _needs_input_method(
            "dcf",
            "缺少基准自由现金流，DCF 不生成估值数字。",
            input_gaps,
            required_fields=["base_free_cash_flow"],
        )
    return _cash_flow_method_result(
        method="dcf",
        base_cash_flow=base_fcf,
        growth_key="cash_flow_growth_rate",
        assumptions=assumptions,
        valuation_inputs=valuation_inputs,
        applicability=_model_weights()["dcf"],
        reason="自由现金流口径可用，DCF 作为价值投资估值的交叉验证模型。",
    )


def _calculate_owner_earnings(
    valuation_inputs: dict[str, object],
    assumptions: dict[str, object],
    input_gaps: list[dict[str, object]],
) -> dict[str, object]:
    net_profit = _num(valuation_inputs.get("base_net_profit"))
    capital_expenditure = _num(valuation_inputs.get("capital_expenditure"))
    normalized_owner_earnings = _num(valuation_inputs.get("owner_earnings_base"))
    base_period_method = _safe_str(valuation_inputs.get("base_period_method"))
    base_period_type = _safe_str(valuation_inputs.get("base_period_type"))
    if base_period_type in {"half_year", "quarter"} and base_period_method != "ttm_adjusted":
        return _needs_input_method(
            "owner_earnings",
            "所有者盈余必须使用 TTM 或完整年度基数，不能直接使用中报或单季数据。",
            input_gaps,
            required_fields=["owner_earnings_annualized_base"],
        )
    if normalized_owner_earnings is None and (net_profit is None or capital_expenditure is None):
        required = []
        if net_profit is None:
            required.append("base_net_profit")
        if capital_expenditure is None:
            required.append("capital_expenditure")
        return _needs_input_method(
            "owner_earnings",
            "缺少净利润或资本开支，所有者盈余估值不生成数字。",
            input_gaps,
            required_fields=required,
        )
    depreciation = _num(valuation_inputs.get("depreciation_and_amortization")) or 0.0
    working_capital_change = _num(valuation_inputs.get("working_capital_change")) or 0.0
    working_capital_investment = max(-working_capital_change, 0.0)
    owner_earnings = normalized_owner_earnings
    if owner_earnings is None:
        owner_earnings = (
            net_profit + depreciation - capital_expenditure - working_capital_investment
        )
    if owner_earnings <= 0:
        return _needs_input_method(
            "owner_earnings",
            "所有者盈余基数为非正数，MVP 不强行估值。",
            input_gaps,
            required_fields=["owner_earnings_base"],
        )
    result = _cash_flow_method_result(
        method="owner_earnings",
        base_cash_flow=owner_earnings,
        growth_key="owner_earnings_growth_rate",
        assumptions=assumptions,
        valuation_inputs=valuation_inputs,
        applicability=_model_weights()["owner_earnings"],
        reason="净利润、资本开支可用，所有者盈余作为价值投资估值的主要模型。",
    )
    result["calculation_basis"] = {
        "base_cash_flow": owner_earnings,
        "period_method": base_period_method,
        "period_type": base_period_type,
        "source_periods": _str_list(valuation_inputs.get("base_source_periods")),
        "formula": (
            "per period: net_profit + depreciation_and_amortization - total_capex "
            "- max(-working_capital_cash_effect, 0); then aggregate normalized periods"
        ),
        "normalization_method": valuation_inputs.get("owner_earnings_normalization_method"),
        "normalization_confidence": valuation_inputs.get("owner_earnings_normalization_confidence"),
        "normalization_audit": valuation_inputs.get("owner_earnings_normalization", {}),
        "components": {
            "net_profit": net_profit,
            "depreciation_and_amortization": depreciation,
            "capital_expenditure": capital_expenditure,
            "working_capital_cash_effect": working_capital_change,
            "working_capital_investment_deducted": working_capital_investment,
        },
        "capital_expenditure_policy": "total_capex_as_conservative_maintenance_capex_proxy",
    }
    return result


def _calculate_residual_income(
    valuation_inputs: dict[str, object],
    assumptions: dict[str, object],
    input_gaps: list[dict[str, object]],
) -> dict[str, object]:
    equity = _num(valuation_inputs.get("shareholders_equity"))
    net_profit = _num(valuation_inputs.get("base_net_profit"))
    base_period_method = _safe_str(valuation_inputs.get("base_period_method"))
    base_period_type = _safe_str(valuation_inputs.get("base_period_type"))
    if base_period_type in {"half_year", "quarter"} and base_period_method != "ttm_adjusted":
        return _needs_input_method(
            "residual_income",
            "剩余收益模型必须使用 TTM 或完整年度利润基数，不能直接使用中报或单季利润。",
            input_gaps,
            required_fields=["residual_income_annualized_base"],
        )
    if equity is None or equity <= 0 or net_profit is None:
        required = []
        if equity is None or equity <= 0:
            required.append("shareholders_equity")
        if net_profit is None:
            required.append("base_net_profit")
        return _needs_input_method(
            "residual_income",
            "缺少股东权益或年度化净利润，剩余收益模型不生成估值数字。",
            input_gaps,
            required_fields=required,
        )

    scenarios = _dict(assumptions.get("scenarios"))
    shares = _num(valuation_inputs.get("shares_outstanding"))
    scenario_values: dict[str, float | None] = {}
    per_share_values: dict[str, float | None] = {}
    scenario_basis: dict[str, dict[str, float]] = {}
    for scenario_name in ("conservative", "base", "optimistic"):
        scenario = _dict(scenarios.get(scenario_name))
        discount_rate = _num(scenario.get("discount_rate")) or 0.1
        growth_rate = _num(scenario.get("owner_earnings_growth_rate")) or 0.0
        terminal_growth_rate = min(
            _num(scenario.get("terminal_growth_rate")) or 0.0,
            _configured_bounds("terminal", (0.0, 0.035))[1],
        )
        value, basis = _residual_income_value(
            beginning_equity=equity,
            base_net_profit=net_profit,
            growth_rate=growth_rate,
            cost_of_equity=discount_rate,
            terminal_growth_rate=terminal_growth_rate,
        )
        scenario_values[scenario_name] = value
        per_share_values[scenario_name] = value / shares if shares and shares > 0 else None
        scenario_basis[scenario_name] = basis

    return {
        "method": "residual_income",
        "status": "success",
        "applicability": _model_weights()["residual_income"],
        "reason": "股东权益和年度化净利润可用，剩余收益模型用于检验 ROE 是否覆盖权益资本成本。",
        "scenario_values": scenario_values,
        "per_share_values": per_share_values,
        "key_assumptions": scenarios,
        "input_gaps": [],
        "source_refs": {"financial_periods": [_safe_str(valuation_inputs.get("latest_period"))]},
        "calculation_basis": {
            "formula": (
                "shareholders_equity + PV(net_profit_t - cost_of_equity * beginning_equity) "
                "+ PV(terminal_residual_income)"
            ),
            "components": {
                "shareholders_equity": equity,
                "base_net_profit": net_profit,
                "period_method": base_period_method,
                "period_type": base_period_type,
            },
            "scenario_basis": scenario_basis,
            "policy": "book_equity_is_not_adjusted_by_cash_or_debt_to_avoid_double_counting",
        },
    }


def _residual_income_value(
    *,
    beginning_equity: float,
    base_net_profit: float,
    growth_rate: float,
    cost_of_equity: float,
    terminal_growth_rate: float,
) -> tuple[float, dict[str, float]]:
    cost_of_equity = max(
        cost_of_equity,
        terminal_growth_rate
        + float(parameter_value("valuation_models.discount_terminal_gap", 0.01)),
    )
    present_value = beginning_equity
    net_profit = base_net_profit
    last_residual_income = 0.0
    forecast_years = _forecast_years()
    for year in range(1, forecast_years + 1):
        net_profit *= 1 + growth_rate
        residual_income = net_profit - (cost_of_equity * beginning_equity)
        last_residual_income = residual_income
        present_value += residual_income / ((1 + cost_of_equity) ** year)
    terminal_residual_income = last_residual_income * (1 + terminal_growth_rate)
    terminal_value = terminal_residual_income / (cost_of_equity - terminal_growth_rate)
    present_value += terminal_value / ((1 + cost_of_equity) ** forecast_years)
    return max(0.0, present_value), {
        "beginning_equity": beginning_equity,
        "base_net_profit": base_net_profit,
        "cost_of_equity": cost_of_equity,
        "growth_rate": growth_rate,
        "terminal_growth_rate": terminal_growth_rate,
        "year_5_residual_income": last_residual_income,
        "terminal_residual_income": terminal_residual_income,
    }


def _calculate_dividend_discount(
    valuation_inputs: dict[str, object],
    assumptions: dict[str, object],
    input_gaps: list[dict[str, object]],
) -> dict[str, object]:
    dividend = _num(valuation_inputs.get("dividend"))
    base_period_method = _safe_str(valuation_inputs.get("base_period_method"))
    base_period_type = _safe_str(valuation_inputs.get("base_period_type"))
    if base_period_type in {"half_year", "quarter"} and base_period_method != "ttm_adjusted":
        return _needs_input_method(
            "dividend_discount",
            "分红折现模型必须使用 TTM 或完整年度分红基数，不能直接使用中报或单季分红。",
            input_gaps,
            required_fields=["dividend_annualized_base"],
        )
    if dividend is None or dividend <= 0:
        return _needs_input_method(
            "dividend_discount",
            "缺少年度化现金分红或分红为零，分红折现模型不生成估值数字。",
            input_gaps,
            required_fields=["dividend"],
        )

    scenarios = _dict(assumptions.get("scenarios"))
    shares = _num(valuation_inputs.get("shares_outstanding"))
    scenario_values: dict[str, float | None] = {}
    per_share_values: dict[str, float | None] = {}
    scenario_basis: dict[str, dict[str, float]] = {}
    for scenario_name in ("conservative", "base", "optimistic"):
        scenario = _dict(scenarios.get(scenario_name))
        discount_rate = _num(scenario.get("discount_rate")) or 0.1
        growth_rate = _num(scenario.get("owner_earnings_growth_rate")) or 0.0
        terminal_growth_rate = min(
            _num(scenario.get("terminal_growth_rate")) or 0.0,
            _configured_bounds("terminal", (0.0, 0.035))[1],
        )
        value, basis = _dividend_discount_value(
            base_dividend=dividend,
            growth_rate=growth_rate,
            discount_rate=discount_rate,
            terminal_growth_rate=terminal_growth_rate,
        )
        scenario_values[scenario_name] = value
        per_share_values[scenario_name] = value / shares if shares and shares > 0 else None
        scenario_basis[scenario_name] = basis

    return {
        "method": "dividend_discount",
        "status": "success",
        "applicability": _model_weights()["dividend_discount"],
        "reason": "年度化现金分红可用，分红折现模型用于检验股东现金回报价值。",
        "scenario_values": scenario_values,
        "per_share_values": per_share_values,
        "key_assumptions": scenarios,
        "input_gaps": [],
        "source_refs": {"financial_periods": [_safe_str(valuation_inputs.get("latest_period"))]},
        "calculation_basis": {
            "formula": "PV(dividend_t) + PV(terminal_dividend_value)",
            "components": {
                "base_dividend": dividend,
                "period_method": base_period_method,
                "period_type": base_period_type,
            },
            "scenario_basis": scenario_basis,
            "policy": "dividend_is_equity_cash_flow_so_cash_and_debt_are_not_added_again",
        },
    }


def _dividend_discount_value(
    *,
    base_dividend: float,
    growth_rate: float,
    discount_rate: float,
    terminal_growth_rate: float,
) -> tuple[float, dict[str, float]]:
    discount_rate = max(
        discount_rate,
        terminal_growth_rate
        + float(parameter_value("valuation_models.discount_terminal_gap", 0.01)),
    )
    present_value = 0.0
    dividend = base_dividend
    forecast_years = _forecast_years()
    for year in range(1, forecast_years + 1):
        dividend *= 1 + growth_rate
        present_value += dividend / ((1 + discount_rate) ** year)
    terminal_dividend = dividend * (1 + terminal_growth_rate)
    terminal_value = terminal_dividend / (discount_rate - terminal_growth_rate)
    present_value += terminal_value / ((1 + discount_rate) ** forecast_years)
    return max(0.0, present_value), {
        "base_dividend": base_dividend,
        "growth_rate": growth_rate,
        "discount_rate": discount_rate,
        "terminal_growth_rate": terminal_growth_rate,
        "year_5_dividend": dividend,
        "terminal_dividend": terminal_dividend,
    }


def _calculate_asset_value(
    valuation_inputs: dict[str, object],
    input_gaps: list[dict[str, object]],
) -> dict[str, object]:
    total_assets = _num(valuation_inputs.get("total_assets"))
    total_liabilities = _num(valuation_inputs.get("total_liabilities"))
    cash = _num(valuation_inputs.get("cash_and_equivalents")) or 0.0
    equity = _num(valuation_inputs.get("shareholders_equity"))
    shares = _num(valuation_inputs.get("shares_outstanding"))
    if total_assets is None or total_liabilities is None:
        if equity is None or equity <= 0:
            required = []
            if total_assets is None:
                required.append("total_assets")
            if total_liabilities is None:
                required.append("total_liabilities")
            required.append("shareholders_equity")
            return _needs_input_method(
                "asset_value",
                "缺少总资产/总负债，且无法用股东权益兜底，资产价值模型不生成估值数字。",
                input_gaps,
                required_fields=required,
            )
        haircuts = dict(parameter_value("valuation_models.equity_fallback_haircuts", {}))
        scenario_values = {
            scenario_name: max(0.0, equity * haircut) for scenario_name, haircut in haircuts.items()
        }
        scenario_basis = {
            scenario_name: {
                "shareholders_equity": equity,
                "equity_haircut": haircut,
            }
            for scenario_name, haircut in haircuts.items()
        }
        policy = "shareholders_equity_fallback_when_assets_and_liabilities_are_missing"
    else:
        non_cash_assets = max(total_assets - cash, 0.0)
        haircuts = dict(parameter_value("valuation_models.non_cash_asset_haircuts", {}))
        scenario_values = {}
        scenario_basis = {}
        for scenario_name, haircut in haircuts.items():
            value = max(0.0, cash + (non_cash_assets * haircut) - total_liabilities)
            scenario_values[scenario_name] = value
            scenario_basis[scenario_name] = {
                "total_assets": total_assets,
                "cash_and_equivalents": cash,
                "non_cash_assets": non_cash_assets,
                "non_cash_asset_haircut": haircut,
                "total_liabilities": total_liabilities,
            }
        policy = "cash_at_full_value_and_non_cash_assets_haircut_against_total_liabilities"

    per_share_values = {
        scenario_name: value / shares if shares and shares > 0 else None
        for scenario_name, value in scenario_values.items()
    }
    return {
        "method": "asset_value",
        "status": "success",
        "applicability": _model_weights()["asset_value"],
        "reason": "资产负债表关键字段可用，资产价值模型作为下行保护和清算价值交叉验证。",
        "scenario_values": scenario_values,
        "per_share_values": per_share_values,
        "key_assumptions": {
            scenario: {"non_cash_asset_haircut": haircut} for scenario, haircut in haircuts.items()
        },
        "input_gaps": [],
        "source_refs": {"financial_periods": [_safe_str(valuation_inputs.get("latest_period"))]},
        "calculation_basis": {
            "formula": "cash + non_cash_assets * haircut - total_liabilities",
            "scenario_basis": scenario_basis,
            "policy": policy,
        },
    }


def _cash_flow_method_result(
    *,
    method: str,
    base_cash_flow: float,
    growth_key: str,
    assumptions: dict[str, object],
    valuation_inputs: dict[str, object],
    applicability: float,
    reason: str,
) -> dict[str, object]:
    scenario_values: dict[str, float | None] = {}
    per_share_values: dict[str, float | None] = {}
    scenarios = _dict(assumptions.get("scenarios"))
    shares = _num(valuation_inputs.get("shares_outstanding"))
    for scenario_name in ("conservative", "base", "optimistic"):
        scenario = _dict(scenarios.get(scenario_name))
        value = _discount_cash_flow(
            base_cash_flow=base_cash_flow,
            growth_rate=_num(scenario.get(growth_key)) or 0.0,
            discount_rate=_num(scenario.get("discount_rate")) or 0.1,
            terminal_growth_rate=min(
                _num(scenario.get("terminal_growth_rate")) or 0.0,
                _configured_bounds("terminal", (0.0, 0.035))[1],
            ),
            cash=_num(valuation_inputs.get("cash_and_equivalents")),
            debt=_num(valuation_inputs.get("interest_bearing_debt")),
        )
        scenario_values[scenario_name] = value
        per_share_values[scenario_name] = value / shares if shares and shares > 0 else None
    return {
        "method": method,
        "status": "success",
        "applicability": applicability,
        "reason": reason,
        "scenario_values": scenario_values,
        "per_share_values": per_share_values,
        "key_assumptions": scenarios,
        "input_gaps": [],
        "source_refs": {"financial_periods": [_safe_str(valuation_inputs.get("latest_period"))]},
    }


def _discount_cash_flow(
    *,
    base_cash_flow: float,
    growth_rate: float,
    discount_rate: float,
    terminal_growth_rate: float,
    cash: float | None,
    debt: float | None,
) -> float:
    discount_rate = max(
        discount_rate,
        terminal_growth_rate
        + float(parameter_value("valuation_models.discount_terminal_gap", 0.01)),
    )
    present_value = 0.0
    cash_flow = base_cash_flow
    forecast_years = _forecast_years()
    for year in range(1, forecast_years + 1):
        cash_flow *= 1 + growth_rate
        present_value += cash_flow / ((1 + discount_rate) ** year)
    terminal_cash_flow = cash_flow * (1 + terminal_growth_rate)
    terminal_value = terminal_cash_flow / (discount_rate - terminal_growth_rate)
    present_value += terminal_value / ((1 + discount_rate) ** forecast_years)
    return present_value + (cash or 0.0) - (debt or 0.0)


def _resolve_model_weights(assumptions: dict[str, object]) -> dict[str, float]:
    defaults = _model_weights()
    raw_weights = assumptions.get("model_weights")
    if raw_weights is None:
        return defaults
    if not isinstance(raw_weights, dict):
        raise ValuationInputError("模型配比必须是包含五个模型权重的对象。")

    unknown_methods = sorted(set(raw_weights) - set(defaults))
    if unknown_methods:
        raise ValuationInputError(f"模型配比包含未知模型：{', '.join(unknown_methods)}。")

    weights: dict[str, float] = {}
    for method, default_weight in defaults.items():
        weight = _num(raw_weights.get(method, default_weight))
        if weight is None or not isfinite(weight) or weight < 0 or weight > 1:
            raise ValuationInputError(f"模型 {method} 的权重必须在 0% 到 100% 之间。")
        weights[method] = weight

    total_weight = sum(weights.values())
    if abs(total_weight - 1.0) > float(
        parameter_value("valuation_models.model_weight_tolerance", 0.000001)
    ):
        raise ValuationInputError("五个模型的配置权重合计必须等于 100%。")
    return weights


def _combine_method_results(
    method_results: list[dict[str, object]],
    valuation_inputs: dict[str, object],
) -> tuple[dict[str, object], list[dict[str, object]], dict[str, object] | None]:
    successful = [item for item in method_results if item.get("status") == "success"]
    weights = []
    available_baseline_total = sum(float(item.get("applicability") or 0.0) for item in successful)
    if successful and available_baseline_total <= 0:
        raise ValuationInputError("当前可计算模型的配置权重合计必须大于 0。")
    for item in successful:
        applicability = float(item.get("applicability") or 0.0)
        available_baseline_weight = (
            applicability / available_baseline_total if available_baseline_total > 0 else 0.0
        )
        weights.append(
            {
                "method": item.get("method"),
                "weight": available_baseline_weight,
                "components": {
                    "applicability": applicability,
                    "baseline_weight": applicability,
                    "available_baseline_weight": available_baseline_weight,
                    "weighting_policy": "configured_available_baseline",
                },
                "reason": "按用户确认的模型基准权重分配；缺失模型剔除后按比例重分配。",
            }
        )
    normalized_weights = weights
    total_values: dict[str, float | None] = {}
    per_share_values: dict[str, float | None] = {}
    shares = _num(valuation_inputs.get("shares_outstanding"))
    for scenario_name in ("conservative", "base", "optimistic"):
        weighted = 0.0
        for item in successful:
            method_weight = next(
                weight["weight"]
                for weight in normalized_weights
                if weight["method"] == item.get("method")
            )
            scenario_values = _dict(item.get("scenario_values"))
            weighted += float(scenario_values.get(scenario_name) or 0.0) * method_weight
        total_values[scenario_name] = weighted if successful else None
        per_share_values[scenario_name] = (
            weighted / shares if successful and shares and shares > 0 else None
        )
    dispersion_warning = _build_dispersion_warning(successful)
    return (
        {
            "total_equity_value": total_values,
            "per_share_value": per_share_values,
            "unit": "CNY",
            "per_share_status": "success" if shares else "needs_input",
        },
        normalized_weights,
        dispersion_warning,
    )


def _build_dispersion_warning(
    successful: list[dict[str, object]],
) -> dict[str, object] | None:
    base_values = []
    for item in successful:
        scenario_values = _dict(item.get("scenario_values"))
        value = _num(scenario_values.get("base"))
        if value is not None and value > 0:
            base_values.append(value)
    if len(base_values) < 2:
        return None
    low = min(base_values)
    high = max(base_values)
    if low <= 0 or high / low <= float(parameter_value("valuation_models.dispersion_ratio", 1.35)):
        return None
    return {
        "level": "medium",
        "message": "可用估值模型的中性结果分歧较大，综合区间已降低置信度。",
        "base_value_spread": high / low,
    }


def _build_confidence_summary(
    *,
    input_gaps: list[dict[str, object]],
    method_results: list[dict[str, object]],
    dispersion_warning: dict[str, object] | None,
) -> tuple[float, dict[str, object]]:
    confidence_config = parameter_value("valuation_models.confidence", {})
    confidence_config = confidence_config if isinstance(confidence_config, dict) else {}
    confidence = float(confidence_config.get("base", 0.78))
    reasons = ["估值数字来自服务层确定性公式，且保留单模型结果。"]
    high_gaps = _high_severity_gaps(input_gaps)
    low_gaps = [item for item in input_gaps if item.get("severity") == "low"]
    medium_gaps = [item for item in input_gaps if item.get("severity") == "medium"]
    confidence -= float(confidence_config.get("high_gap_penalty", 0.16)) * len(high_gaps)
    confidence -= float(confidence_config.get("medium_gap_penalty", 0.06)) * len(medium_gaps)
    confidence -= float(confidence_config.get("low_gap_penalty", 0.03)) * len(low_gaps)
    successful_methods = [item for item in method_results if item.get("status") == "success"]
    if len(successful_methods) < 2:
        confidence -= float(confidence_config.get("skipped_method_penalty", 0.12))
        reasons.append("可参与综合的成功估值模型少于 2 个。")
    if high_gaps:
        reasons.append("存在高严重度输入缺口，估值结果仅供复核。")
    elif medium_gaps or low_gaps:
        reasons.append("存在中低严重度输入缺口，允许形成草稿但降低置信度。")
    if dispersion_warning:
        confidence -= float(confidence_config.get("dispersion_penalty", 0.08))
        reasons.append(str(dispersion_warning["message"]))
    confidence = _clamp(
        confidence,
        float(confidence_config.get("minimum", 0.10)),
        float(confidence_config.get("maximum", 0.90)),
    )
    if confidence >= float(confidence_config.get("high_threshold", 0.72)):
        level = "high"
    elif confidence >= float(confidence_config.get("medium_threshold", 0.45)):
        level = "medium"
    else:
        level = "low"
    return confidence, {"level": level, "reasons": reasons}


def _build_sensitivity(
    valuation_inputs: dict[str, object],
    assumptions: dict[str, object],
) -> dict[str, object]:
    base_fcf = _num(valuation_inputs.get("base_free_cash_flow"))
    if base_fcf is None:
        return {"status": "needs_input", "items": []}
    base = _dict(_dict(assumptions.get("scenarios")).get("base"))
    discount_rate = _num(base.get("discount_rate")) or 0.1
    terminal_growth_rate = _num(base.get("terminal_growth_rate")) or 0.02
    rows = []
    growth_step = float(parameter_value("valuation_models.sensitivity.growth_step", 0.02))
    discount_step = float(parameter_value("valuation_models.sensitivity.discount_step", 0.01))
    for growth_delta in (-growth_step, 0.0, growth_step):
        row = []
        for discount_delta in (-discount_step, 0.0, discount_step):
            row.append(
                _discount_cash_flow(
                    base_cash_flow=base_fcf,
                    growth_rate=(_num(base.get("cash_flow_growth_rate")) or 0.0) + growth_delta,
                    discount_rate=discount_rate + discount_delta,
                    terminal_growth_rate=terminal_growth_rate,
                    cash=_num(valuation_inputs.get("cash_and_equivalents")),
                    debt=_num(valuation_inputs.get("interest_bearing_debt")),
                )
            )
        rows.append({"growth_delta": growth_delta, "values": row})
    return {
        "status": "success",
        "axes": {
            "growth_delta": [-growth_step, 0.0, growth_step],
            "discount_delta": [-discount_step, 0.0, discount_step],
        },
        "items": rows,
    }


def _needs_input_method(
    method: str,
    reason: str,
    input_gaps: list[dict[str, object]],
    *,
    required_fields: list[str],
) -> dict[str, object]:
    method_gaps = [item for item in input_gaps if str(item.get("field")) in set(required_fields)]
    return {
        "method": method,
        "status": "needs_input",
        "applicability": _model_weights().get(method, 0.0),
        "reason": reason,
        "scenario_values": {"conservative": None, "base": None, "optimistic": None},
        "per_share_values": {"conservative": None, "base": None, "optimistic": None},
        "key_assumptions": {},
        "input_gaps": method_gaps,
        "source_refs": {},
    }


def _skipped_method(method: str, reason: str) -> dict[str, object]:
    return {
        "method": method,
        "status": "skipped",
        "applicability": _model_weights().get(method, 0.0),
        "reason": reason,
        "scenario_values": {"conservative": None, "base": None, "optimistic": None},
        "per_share_values": {"conservative": None, "base": None, "optimistic": None},
        "key_assumptions": {},
        "input_gaps": [],
        "source_refs": {},
    }


def _high_severity_gaps(value: object) -> list[dict[str, object]]:
    return [
        item for item in _list(value) if isinstance(item, dict) and item.get("severity") == "high"
    ]


def _hash_snapshot(snapshot: dict[str, object]) -> str:
    payload = json.dumps(snapshot, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class _PriceBlindScrubber:
    def __init__(self) -> None:
        self.scrubbed_items: list[dict[str, object]] = []

    def scrub(self, value: object, path: str = "$") -> object:
        if isinstance(value, dict):
            cleaned: dict[str, object] = {}
            for key, nested in value.items():
                normalized_key = str(key)
                if _is_forbidden_key(normalized_key):
                    self.scrubbed_items.append({"path": f"{path}.{normalized_key}", "kind": "key"})
                    continue
                cleaned[normalized_key] = self.scrub(nested, f"{path}.{normalized_key}")
            return cleaned
        if isinstance(value, list):
            cleaned_list = []
            for index, nested in enumerate(value):
                cleaned = self.scrub(nested, f"{path}[{index}]")
                if cleaned is not None:
                    cleaned_list.append(cleaned)
            return cleaned_list
        if isinstance(value, str) and _contains_forbidden_term(value):
            self.scrubbed_items.append({"path": path, "kind": "text"})
            return None
        return value


def _is_forbidden_key(key: str) -> bool:
    normalized = key.strip().lower()
    return normalized in FORBIDDEN_PRICE_FIELDS or any(
        field in normalized for field in FORBIDDEN_PRICE_FIELDS
    )


def _contains_forbidden_term(value: str) -> bool:
    return any(term in value for term in FORBIDDEN_PRICE_TERMS)


def _deep_merge(base: dict[str, object], updates: dict[str, object]) -> dict[str, object]:
    merged = deepcopy(base)
    for key, value in updates.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(_dict(merged[key]), value)
        else:
            merged[key] = value
    return merged


def _forecast_years() -> int:
    return int(parameter_value("valuation_models.forecast_years", 5))


def _model_weights() -> dict[str, float]:
    configured = parameter_value("valuation_models.model_weights", {})
    if not isinstance(configured, dict):
        configured = {}
    defaults = {
        "owner_earnings": 0.35,
        "dcf": 0.35,
        "residual_income": 0.15,
        "dividend_discount": 0.10,
        "asset_value": 0.05,
    }
    return {key: float(configured.get(key, value)) for key, value in defaults.items()}


def _configured_bounds(name: str, fallback: tuple[float, float]) -> tuple[float, float]:
    bounds = parameter_value(f"valuation_models.base_bounds.{name}", list(fallback))
    if isinstance(bounds, list) and len(bounds) == 2:
        low = _num(bounds[0])
        high = _num(bounds[1])
        if low is not None and high is not None:
            return low, high
    return fallback


def _scenario_bounds(
    scenario: dict[str, object],
    key: str,
    fallback: tuple[float, float],
) -> tuple[float, float]:
    bounds = scenario.get(key)
    if isinstance(bounds, list) and len(bounds) == 2:
        low = _num(bounds[0])
        high = _num(bounds[1])
        if low is not None and high is not None:
            return low, high
    return fallback


def _clamp(value: float, low: float, high: float) -> float:
    return min(high, max(low, value))


def _dict(value: object) -> dict[str, object]:
    return value if isinstance(value, dict) else {}


def _list(value: object) -> list[object]:
    return value if isinstance(value, list) else []


def _str_list(value: object) -> list[str]:
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item).strip()]


def _num(value: object) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return None
    return None


def _as_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None


def _safe_str(value: object) -> str:
    return str(value) if value is not None else ""
