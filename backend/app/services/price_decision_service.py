from __future__ import annotations

import hashlib
import json
import math
from copy import deepcopy
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.configuration.runtime import parameter_config_context, parameter_value
from app.db.models import Company, InvestmentMemo, PriceDecisionRun, ValuationRun, utc_now
from app.services.parameter_config_service import get_runtime_parameter_config

RUN_VERSION = "011_v1"
FORMULA_VERSION = "011_v1"
CALCULATED_VALUATION_STATUS = "calculated_after_user_confirmation"
ACTIVE_STATUS = "active"
DELETED_STATUS = "deleted"

PRICE_STATUS_TARGET_MARGIN = "达到目标安全边际"
PRICE_STATUS_BELOW_VALUE = "低于内在价值但安全边际不足"
PRICE_STATUS_UPPER_RANGE = "处于估值区间上半部"
PRICE_STATUS_ABOVE_OPTIMISTIC = "高于乐观内在价值"


class PriceDecisionError(ValueError):
    pass


class PriceDecisionInputError(PriceDecisionError):
    pass


def create_price_decision_run(
    session: Session,
    company: Company,
    *,
    valuation_run_id: int | None = None,
    safety_margin_override: float | None = None,
) -> PriceDecisionRun:
    runtime = get_runtime_parameter_config(session)
    with parameter_config_context(runtime.snapshot):
        return _create_price_decision_run_with_config(
            session,
            company,
            valuation_run_id=valuation_run_id,
            safety_margin_override=safety_margin_override,
            config_version=runtime.version,
            config_hash=runtime.config_hash,
            config_snapshot=runtime.snapshot,
        )


def _create_price_decision_run_with_config(
    session: Session,
    company: Company,
    *,
    valuation_run_id: int | None,
    safety_margin_override: float | None,
    config_version: int | None,
    config_hash: str,
    config_snapshot: dict[str, object],
) -> PriceDecisionRun:
    valuation_run = _resolve_valuation_run(
        session,
        company_id=company.id,
        valuation_run_id=valuation_run_id,
    )
    memo = _resolve_bound_memo(session, company_id=company.id, valuation_run=valuation_run)
    intrinsic_values = _read_intrinsic_values(valuation_run)
    suggested_margin = _read_valuation_safety_margin(valuation_run)
    current_price, market_data_updated_at = _read_market_price(company)
    override = _validate_margin_override(safety_margin_override)
    effective_margin = suggested_margin if override is None else override

    scenario_buy_prices = {
        scenario: value * (1.0 - effective_margin) for scenario, value in intrinsic_values.items()
    }
    buy_price_scenario = str(parameter_value("price_decision.buy_price_scenario", "base"))
    suggested_buy_price = scenario_buy_prices[buy_price_scenario]
    current_margin = 1.0 - current_price / intrinsic_values["base"]
    price_status = determine_price_status(
        current_price=current_price,
        suggested_buy_price=suggested_buy_price,
        base_intrinsic_value=intrinsic_values["base"],
        optimistic_intrinsic_value=intrinsic_values["optimistic"],
    )

    input_snapshot = {
        "company": {
            "id": company.id,
            "current_price": current_price,
            "market_data_updated_at": _datetime_to_iso(market_data_updated_at),
        },
        "valuation_run": {
            "id": valuation_run.id,
            "company_id": valuation_run.company_id,
            "memo_id": valuation_run.memo_id,
            "run_version": valuation_run.run_version,
            "status": valuation_run.status,
            "results_status": valuation_run.results.get("status"),
            "input_snapshot_hash": valuation_run.input_snapshot_hash,
            "intrinsic_values_per_share": intrinsic_values,
        },
        "memo": {
            "id": memo.id,
            "company_id": memo.company_id,
            "version_no": memo.version_no,
            "source_snapshot_hash": memo.source_snapshot_hash,
        },
        "valuation_dynamic_safety_margin": {
            "suggested": suggested_margin,
            "formula_version": valuation_run.results.get("dynamic_safety_margin_formula_version"),
        },
        "margin": {
            "suggested": suggested_margin,
            "override": override,
            "effective": effective_margin,
        },
        "formula_version": FORMULA_VERSION,
        "configuration": {
            "version": config_version,
            "hash": config_hash,
        },
    }
    snapshot_hash = _hash_snapshot(input_snapshot)
    version_no = (
        session.scalar(
            select(func.max(PriceDecisionRun.version_no)).where(
                PriceDecisionRun.company_id == company.id
            )
        )
        or 0
    ) + 1

    run = PriceDecisionRun(
        company_id=company.id,
        valuation_run_id=valuation_run.id,
        memo_id=memo.id,
        version_no=version_no,
        run_version=RUN_VERSION,
        formula_version=FORMULA_VERSION,
        status=ACTIVE_STATUS,
        input_snapshot=input_snapshot,
        input_snapshot_hash=snapshot_hash,
        config_version=config_version,
        config_hash=config_hash,
        config_snapshot=deepcopy(config_snapshot),
        intrinsic_values_per_share=intrinsic_values,
        current_price=current_price,
        market_data_updated_at=market_data_updated_at,
        analyst_score_total=None,
        analyst_scorecard_snapshot={},
        suggested_safety_margin=suggested_margin,
        safety_margin_override=override,
        effective_safety_margin=effective_margin,
        scenario_buy_prices=scenario_buy_prices,
        suggested_buy_price=suggested_buy_price,
        current_margin=current_margin,
        price_status=price_status,
    )
    session.add(run)
    session.commit()
    session.refresh(run)
    return run


def determine_price_status(
    *,
    current_price: float,
    suggested_buy_price: float,
    base_intrinsic_value: float,
    optimistic_intrinsic_value: float,
) -> str:
    if current_price <= suggested_buy_price:
        return PRICE_STATUS_TARGET_MARGIN
    if current_price < base_intrinsic_value:
        return PRICE_STATUS_BELOW_VALUE
    if current_price <= optimistic_intrinsic_value:
        return PRICE_STATUS_UPPER_RANGE
    return PRICE_STATUS_ABOVE_OPTIMISTIC


def get_price_decision_run(session: Session, run_id: int) -> PriceDecisionRun | None:
    return session.get(PriceDecisionRun, run_id)


def get_latest_company_price_decision_run(
    session: Session, *, company_id: int
) -> PriceDecisionRun | None:
    return session.scalar(
        select(PriceDecisionRun)
        .where(
            PriceDecisionRun.company_id == company_id,
            PriceDecisionRun.status != DELETED_STATUS,
        )
        .order_by(PriceDecisionRun.created_at.desc(), PriceDecisionRun.id.desc())
        .limit(1)
    )


def list_company_price_decision_runs(
    session: Session,
    *,
    company_id: int,
    limit: int = 20,
    offset: int = 0,
    include_deleted: bool = False,
) -> tuple[list[PriceDecisionRun], int]:
    filters = [PriceDecisionRun.company_id == company_id]
    if not include_deleted:
        filters.append(PriceDecisionRun.status != DELETED_STATUS)
    total = session.scalar(select(func.count()).select_from(PriceDecisionRun).where(*filters)) or 0
    items = list(
        session.scalars(
            select(PriceDecisionRun)
            .where(*filters)
            .order_by(PriceDecisionRun.created_at.desc(), PriceDecisionRun.id.desc())
            .limit(limit)
            .offset(offset)
        )
    )
    return items, total


def delete_price_decision_run(session: Session, run: PriceDecisionRun) -> PriceDecisionRun:
    if run.status != DELETED_STATUS:
        run.status = DELETED_STATUS
        run.deleted_at = utc_now()
        session.commit()
        session.refresh(run)
    return run


def _resolve_valuation_run(
    session: Session, *, company_id: int, valuation_run_id: int | None
) -> ValuationRun:
    if valuation_run_id is not None:
        valuation_run = session.get(ValuationRun, valuation_run_id)
        if valuation_run is None:
            raise PriceDecisionInputError("指定的 010 估值版本不存在。")
        if valuation_run.company_id != company_id:
            raise PriceDecisionInputError("指定的 010 估值版本不属于当前公司。")
        _validate_calculated_valuation(valuation_run)
        return valuation_run

    candidates = session.scalars(
        select(ValuationRun)
        .where(ValuationRun.company_id == company_id)
        .order_by(ValuationRun.created_at.desc(), ValuationRun.id.desc())
    )
    for valuation_run in candidates:
        if valuation_run.results.get("status") == CALCULATED_VALUATION_STATUS:
            return valuation_run
    raise PriceDecisionInputError(
        "缺少已确认参数并完成计算的 010 估值，请先在无锚定估值中确认参数并计算。"
    )


def _validate_calculated_valuation(valuation_run: ValuationRun) -> None:
    results_status = valuation_run.results.get("status")
    if results_status != CALCULATED_VALUATION_STATUS:
        raise PriceDecisionInputError(
            "指定的 010 估值尚未完成计算，请先确认参数并重新计算；估值记录本身可以保持 draft。"
        )


def _resolve_bound_memo(
    session: Session, *, company_id: int, valuation_run: ValuationRun
) -> InvestmentMemo:
    if valuation_run.memo_id is None:
        raise PriceDecisionInputError("该 010 估值没有绑定 Memo，请重新生成 Memo 和 010 估值。")
    memo = session.get(InvestmentMemo, valuation_run.memo_id)
    if memo is None:
        raise PriceDecisionInputError(
            "该 010 估值绑定的 Memo 不存在，请重新生成 Memo 和 010 估值。"
        )
    if memo.company_id != company_id or memo.company_id != valuation_run.company_id:
        raise PriceDecisionInputError("010 估值、绑定 Memo 与当前公司的归属关系不一致。")
    return memo


def _read_intrinsic_values(valuation_run: ValuationRun) -> dict[str, float]:
    intrinsic_range = valuation_run.results.get("intrinsic_value_range")
    if not isinstance(intrinsic_range, dict):
        raise PriceDecisionInputError("010 估值缺少每股内在价值区间，请重新计算 010 估值。")
    per_share = intrinsic_range.get("per_share_value")
    if not isinstance(per_share, dict):
        raise PriceDecisionInputError("010 估值缺少每股内在价值区间，请重新计算 010 估值。")
    values: dict[str, float] = {}
    labels = {"conservative": "保守", "base": "中性", "optimistic": "乐观"}
    for scenario, label in labels.items():
        value = _finite_number(per_share.get(scenario))
        if value is None or value <= 0:
            raise PriceDecisionInputError(f"010 估值缺少有效的{label}每股内在价值。")
        values[scenario] = value
    if not values["conservative"] <= values["base"] <= values["optimistic"]:
        raise PriceDecisionInputError("010 三情景每股内在价值顺序异常，请重新检查并计算 010 估值。")
    return values


def _read_valuation_safety_margin(valuation_run: ValuationRun) -> float:
    suggested_margin = _finite_number(valuation_run.results.get("dynamic_safety_margin"))
    if suggested_margin is None:
        raise PriceDecisionInputError(
            "该 010 估值没有冻结动态安全边际，请使用完整 8 位分析师结果重新生成 010。"
        )
    minimum = float(parameter_value("price_decision.safety_margin_min", 0.1))
    maximum = float(parameter_value("price_decision.safety_margin_max", 0.5))
    if not minimum <= suggested_margin <= maximum:
        raise PriceDecisionInputError(
            f"绑定 010 的动态安全边际超出 {_margin_range_label(minimum, maximum)}，"
            "请重新生成 010。"
        )
    return suggested_margin


def _read_market_price(company: Company) -> tuple[float, datetime]:
    current_price = _finite_number(company.current_price)
    if current_price is None or current_price <= 0:
        raise PriceDecisionInputError("缺少有效的当前价格，请先更新公司基本信息和行情数据。")
    if company.market_data_updated_at is None:
        raise PriceDecisionInputError("缺少当前价格的更新时间，请先更新公司基本信息和行情数据。")
    return current_price, company.market_data_updated_at


def _validate_margin_override(value: float | None) -> float | None:
    if value is None:
        return None
    normalized = _finite_number(value)
    minimum = float(parameter_value("price_decision.safety_margin_min", 0.1))
    maximum = float(parameter_value("price_decision.safety_margin_max", 0.5))
    if normalized is None or not minimum <= normalized <= maximum:
        raise PriceDecisionInputError(
            f"用户覆盖安全边际必须位于 {_margin_range_label(minimum, maximum)}。"
        )
    return normalized


def _margin_range_label(minimum: float, maximum: float) -> str:
    return f"{minimum:.0%}-{maximum:.0%}"


def _finite_number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    result = float(value)
    return result if math.isfinite(result) else None


def _datetime_to_iso(value: datetime) -> str:
    return value.isoformat()


def _hash_snapshot(snapshot: dict[str, object]) -> str:
    serialized = json.dumps(snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()
