from __future__ import annotations

import hashlib
import json
import math
from copy import deepcopy
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import Company, InvestmentMemo, PriceDecisionRun, ValuationRun, utc_now

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
    valuation_run = _resolve_valuation_run(
        session,
        company_id=company.id,
        valuation_run_id=valuation_run_id,
    )
    memo = _resolve_bound_memo(session, company_id=company.id, valuation_run=valuation_run)
    intrinsic_values = _read_intrinsic_values(valuation_run)
    analyst_score_total, suggested_margin, scorecard_snapshot = _read_scorecard(memo)
    current_price, market_data_updated_at = _read_market_price(company)
    override = _validate_margin_override(safety_margin_override)
    effective_margin = suggested_margin if override is None else override

    scenario_buy_prices = {
        scenario: value * (1.0 - effective_margin)
        for scenario, value in intrinsic_values.items()
    }
    suggested_buy_price = scenario_buy_prices["base"]
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
            "analyst_score_total": analyst_score_total,
            "suggested_safety_margin": suggested_margin,
        },
        "margin": {
            "suggested": suggested_margin,
            "override": override,
            "effective": effective_margin,
        },
        "formula_version": FORMULA_VERSION,
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
        intrinsic_values_per_share=intrinsic_values,
        current_price=current_price,
        market_data_updated_at=market_data_updated_at,
        analyst_score_total=analyst_score_total,
        analyst_scorecard_snapshot=scorecard_snapshot,
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
    total = session.scalar(
        select(func.count()).select_from(PriceDecisionRun).where(*filters)
    ) or 0
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


def _read_scorecard(memo: InvestmentMemo) -> tuple[float, float, dict[str, object]]:
    sections = memo.sections
    scorecard = sections.get("analyst_scorecard") if isinstance(sections, dict) else None
    if not isinstance(scorecard, dict):
        raise PriceDecisionInputError(
            "该估值绑定的旧 Memo 缺少分析师评分，请重新生成 Memo 和 010 估值。"
        )
    suggested_margin = _finite_number(scorecard.get("suggested_safety_margin"))
    if suggested_margin is None:
        raise PriceDecisionInputError(
            "该估值绑定的旧 Memo 没有动态安全边际，请重新生成 Memo 和 010 估值。"
        )
    if not 0.0 <= suggested_margin <= 0.5:
        raise PriceDecisionInputError("绑定 Memo 的动态安全边际超出 0%-50%，请重新生成 Memo。")
    analyst_score_total = _finite_number(scorecard.get("total_score"))
    if analyst_score_total is None:
        raise PriceDecisionInputError(
            "该估值绑定的 Memo 缺少分析师综合评分，请重新生成 Memo 和 010 估值。"
        )
    return analyst_score_total, suggested_margin, deepcopy(scorecard)


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
    if normalized is None or not 0.0 <= normalized <= 0.5:
        raise PriceDecisionInputError("用户覆盖安全边际必须位于 0%-50%。")
    return normalized


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
