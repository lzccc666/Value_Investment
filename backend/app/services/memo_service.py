from __future__ import annotations

import hashlib
import json
import re
from collections import Counter, defaultdict
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.analysis.analyst_profiles import list_analyst_profiles
from app.analysis.model_gateway import (
    ModelGateway,
    ModelGatewayError,
    ModelOutputValidationError,
)
from app.analysis.prompts.memo import (
    MEMO_SYSTEM_PROMPT,
    PROMPT_VERSION,
    build_memo_prompt,
)
from app.analysis.result_sanitizer import sanitize_error_text
from app.db.models import AnalysisRun, Company, InvestmentMemo, utc_now
from app.schemas.memo import InvestmentMemoOutput, MemoValuationSignalPack
from app.services.analyst_service import RUN_TYPE_ANALYST_VIEW, list_latest_company_analysis_runs

RUN_TYPE_INVESTMENT_MEMO = "investment_memo"
RUN_VERSION = "009_v1"
MEMO_PROFILE = "investment_committee"
MIN_SOURCE_ANALYST_RUNS = 2
DELETED_MEMO_STATUSES = {"deleted", "archived"}
PROHIBITED_ACTION_TERMS = (
    "买入",
    "卖出",
    "持有",
    "减仓",
    "加仓",
    "仓位",
    "建议配置",
    "当前价格便宜",
    "当前价格昂贵",
    "目标价",
)
CRITICAL_RISK_TERMS = (
    "诚信",
    "现金流恶化",
    "杠杆",
    "偿债",
    "监管",
    "会计",
    "永久性损失",
)
PRICE_BLIND_FORBIDDEN_KEYS = {
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
    "rating",
    "market_rating",
    "broker_rating",
    "target_price",
    "market_sentiment",
}
PRICE_BLIND_FORBIDDEN_TERMS = (
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
    "market_rating",
    "broker_rating",
    "target_price",
    "market_sentiment",
    "current price",
    "historical price",
    "market cap",
    "valuation multiple",
    "target price",
    "position cost",
    "market sentiment",
    "当前价格",
    "历史价格",
    "市值",
    "估值倍数",
    "市盈率",
    "市净率",
    "市销率",
    "持仓成本",
    "评级",
    "目标价",
    "市场情绪",
)


class InvestmentMemoError(ValueError):
    pass


class InvestmentMemoNotFoundError(InvestmentMemoError):
    pass


class InvestmentMemoInsufficientSourcesError(InvestmentMemoError):
    pass


def build_investment_memo_snapshot(session: Session, company: Company) -> dict[str, object]:
    source_runs = list_latest_company_analysis_runs(
        session,
        company_id=company.id,
        run_type=RUN_TYPE_ANALYST_VIEW,
        status="success",
    )
    failed_runs = list_latest_company_analysis_runs(
        session,
        company_id=company.id,
        run_type=RUN_TYPE_ANALYST_VIEW,
        status="failed",
    )
    profiles = list_analyst_profiles()
    source_run_snapshots = [_source_run_snapshot(run) for run in source_runs]
    committee_ledger = build_committee_ledger(
        source_run_snapshots,
        all_profile_ids=[profile.id for profile in profiles],
        failed_profile_ids=[
            str(run.analyst_profile) for run in failed_runs if isinstance(run.analyst_profile, str)
        ],
    )

    return {
        "company": _company_snapshot(company),
        "source_analyst_runs": source_run_snapshots,
        "committee_ledger": committee_ledger,
        "source_boundary": {
            "allowed_sources": ["latest_successful_analyst_view_runs"],
            "forbidden_actions": [
                "web_search",
                "data_collection",
                "announcement_resummarization",
                "price_decision",
            ],
            "decision_policy": "不生成买入、卖出、持有、减仓、加仓或仓位动作。",
            "minimum_successful_profiles": MIN_SOURCE_ANALYST_RUNS,
        },
    }


def build_committee_ledger(
    source_analyst_runs: list[dict[str, object]],
    *,
    all_profile_ids: list[str] | None = None,
    failed_profile_ids: list[str] | None = None,
) -> dict[str, object]:
    source_run_ids = _unique_ints(run.get("run_id") for run in source_analyst_runs)
    successful_profile_ids = _unique_strings(
        run.get("analyst_profile") for run in source_analyst_runs
    )
    missing_profiles = [
        profile_id
        for profile_id in (all_profile_ids or [])
        if profile_id not in successful_profile_ids
    ]
    for profile_id in failed_profile_ids or []:
        label = f"{profile_id} 最近失败"
        if label not in missing_profiles:
            missing_profiles.append(label)

    evidence_ids: list[int] = []
    announcement_ids: list[int] = []
    financial_periods: list[str] = []
    risk_flags: list[dict[str, object]] = []
    data_gaps: list[dict[str, object]] = []
    valuation_assumptions: list[dict[str, object]] = []
    rule_statuses: dict[str, list[dict[str, str]]] = defaultdict(list)
    topic_counter: Counter[str] = Counter()
    topic_profiles: dict[str, set[str]] = defaultdict(set)

    for run in source_analyst_runs:
        run_id = _as_int(run.get("run_id"))
        profile_id = str(run.get("analyst_profile") or "")
        result = run.get("result")
        if not isinstance(result, dict):
            result = {}
        analysis_basis = result.get("analysis_basis")
        if isinstance(analysis_basis, dict):
            evidence_ids.extend(_normalize_int_list(analysis_basis.get("external_evidence_ids")))
            announcement_ids.extend(_normalize_int_list(analysis_basis.get("announcement_ids")))
            financial_periods.extend(_normalize_str_list(analysis_basis.get("financial_periods")))

        for key in ("key_observations", "financial_observations", "announcement_observations"):
            for item in _normalize_str_list(result.get(key)):
                topic = _topic_key(item)
                topic_counter[topic] += 1
                topic_profiles[topic].add(profile_id)

        for item in _normalize_str_list(result.get("risk_flags")):
            risk_flags.append({"summary": item, "source_run_id": run_id, "profile": profile_id})

        for item in _normalize_str_list(result.get("data_gaps")):
            data_gaps.append({"summary": item, "source_run_id": run_id, "profile": profile_id})

        for detail in _normalize_valuation_details(result):
            detail["source_refs"] = _merge_source_refs(
                detail.get("source_refs"),
                default_run_id=run_id,
            )
            valuation_assumptions.append(detail)

        rule_checks = result.get("rule_checks")
        if isinstance(rule_checks, list):
            for item in rule_checks:
                if not isinstance(item, dict):
                    continue
                rule_id = item.get("rule_id")
                status = item.get("status")
                if isinstance(rule_id, str) and isinstance(status, str):
                    rule_statuses[rule_id].append(
                        {
                            "profile": profile_id,
                            "status": status,
                            "summary": str(item.get("summary") or ""),
                        }
                    )
                evidence_ids.extend(_normalize_int_list(item.get("evidence_ids")))
                announcement_ids.extend(_normalize_int_list(item.get("announcement_ids")))
                financial_periods.extend(_normalize_str_list(item.get("financial_periods")))

    consensus_candidates = [
        {
            "topic": topic,
            "supporting_profiles": sorted(topic_profiles[topic]),
            "mention_count": count,
        }
        for topic, count in topic_counter.items()
        if count >= 2 and len(topic_profiles[topic]) >= 2
    ]
    dissent_candidates = [
        {"topic": rule_id, "profile_positions": positions}
        for rule_id, positions in rule_statuses.items()
        if len({position["status"] for position in positions}) >= 2
    ]
    critical_risk_candidates = [
        item for item in risk_flags if any(term in item["summary"] for term in CRITICAL_RISK_TERMS)
    ]

    return {
        "profile_count": len(successful_profile_ids),
        "missing_profiles": missing_profiles,
        "source_run_ids": source_run_ids,
        "shared_evidence_ids": _unique_ints(evidence_ids),
        "shared_announcement_ids": _unique_ints(announcement_ids),
        "financial_periods": _unique_strings(financial_periods),
        "consensus_candidates": consensus_candidates,
        "dissent_candidates": dissent_candidates,
        "critical_risk_candidates": critical_risk_candidates or risk_flags[:6],
        "data_gap_candidates": _dedupe_summary_dicts(data_gaps),
        "valuation_assumption_queue": _dedupe_valuation_assumptions(valuation_assumptions),
    }


def run_company_investment_memo(
    session: Session,
    company: Company,
    *,
    user_note: str | None = None,
    gateway: ModelGateway | None = None,
) -> tuple[AnalysisRun, InvestmentMemo]:
    data_snapshot = build_investment_memo_snapshot(session, company)
    source_runs = data_snapshot.get("source_analyst_runs")
    if not isinstance(source_runs, list) or len(source_runs) < MIN_SOURCE_ANALYST_RUNS:
        raise InvestmentMemoInsufficientSourcesError(
            "至少需要 2 个成功分析师视角才能生成综合备忘录。"
        )

    model_gateway = gateway or ModelGateway()
    snapshot_hash = _hash_snapshot(data_snapshot)
    run = _create_running_memo_run(
        session,
        company_id=company.id,
        model_name=model_gateway.model_name,
        data_snapshot=data_snapshot,
        snapshot_hash=snapshot_hash,
        user_note=user_note,
    )

    try:
        output = model_gateway.generate_structured(
            system_prompt=MEMO_SYSTEM_PROMPT,
            user_prompt=build_memo_prompt(data_snapshot),
            schema=InvestmentMemoOutput,
            temperature=0.2,
        )
        output_payload = output.model_dump(mode="json")
        _apply_source_map_override(output_payload, data_snapshot)
        output_payload["valuation_signal_pack"] = {
            "price_blind_compatible": True,
            "source": "deprecated_009_display_compatibility_only",
            "analyst_signals": [],
            "consensus_parameter_impacts": [],
            "dissent_parameter_impacts": [],
            "risk_constraints": [],
            "data_gaps_for_valuation": [],
            "user_confirmation_required": True,
        }
        _validate_output_references(output_payload, data_snapshot)
        _validate_no_prohibited_actions(output_payload)
        _complete_memo_run(session, run, output_payload)
        memo = _create_model_memo(session, company_id=company.id, run=run, output=output_payload)
        return run, memo
    except (ModelGatewayError, ModelOutputValidationError, ValueError) as exc:
        _fail_memo_run(session, run, exc)
        raise
    except Exception as exc:
        _fail_memo_run(session, run, exc)
        raise


def list_company_investment_memos(
    session: Session,
    *,
    company_id: int,
    limit: int = 20,
    offset: int = 0,
    include_deleted: bool = False,
) -> tuple[list[InvestmentMemo], int]:
    filters = [InvestmentMemo.company_id == company_id]
    if not include_deleted:
        filters.append(InvestmentMemo.status.not_in(DELETED_MEMO_STATUSES))

    total = session.scalar(select(func.count()).select_from(InvestmentMemo).where(*filters)) or 0
    items = session.scalars(
        select(InvestmentMemo)
        .where(*filters)
        .order_by(InvestmentMemo.created_at.desc(), InvestmentMemo.id.desc())
        .offset(offset)
        .limit(limit)
    ).all()
    return items, total


def get_latest_company_investment_memo(
    session: Session,
    *,
    company_id: int,
) -> InvestmentMemo | None:
    memo = session.scalar(
        select(InvestmentMemo)
        .where(
            InvestmentMemo.company_id == company_id,
            InvestmentMemo.is_latest.is_(True),
            InvestmentMemo.status.not_in(DELETED_MEMO_STATUSES),
        )
        .order_by(InvestmentMemo.created_at.desc(), InvestmentMemo.id.desc())
    )
    if memo is not None:
        return memo
    return _recompute_latest_memo(session, company_id=company_id)


def get_latest_memo_for_valuation(
    session: Session,
    *,
    company_id: int,
) -> InvestmentMemo | None:
    return get_latest_company_investment_memo(session, company_id=company_id)


def get_investment_memo(session: Session, memo_id: int) -> InvestmentMemo | None:
    return session.get(InvestmentMemo, memo_id)


def archive_investment_memo(session: Session, memo: InvestmentMemo) -> InvestmentMemo | None:
    memo.status = "archived"
    memo.is_latest = False
    memo.updated_at = utc_now()
    session.commit()
    return _recompute_latest_memo(session, company_id=memo.company_id)


def delete_investment_memo(session: Session, memo: InvestmentMemo) -> InvestmentMemo | None:
    memo.status = "deleted"
    memo.is_latest = False
    memo.updated_at = utc_now()
    session.commit()
    return _recompute_latest_memo(session, company_id=memo.company_id)


def _create_running_memo_run(
    session: Session,
    *,
    company_id: int,
    model_name: str | None,
    data_snapshot: dict[str, object],
    snapshot_hash: str,
    user_note: str | None,
) -> AnalysisRun:
    session.query(AnalysisRun).filter(
        AnalysisRun.company_id == company_id,
        AnalysisRun.run_type == RUN_TYPE_INVESTMENT_MEMO,
        AnalysisRun.is_latest.is_(True),
    ).update({"is_latest": False}, synchronize_session=False)
    run = AnalysisRun(
        company_id=company_id,
        run_type=RUN_TYPE_INVESTMENT_MEMO,
        analyst_profile=MEMO_PROFILE,
        run_version=RUN_VERSION,
        model_name=model_name,
        prompt_version=PROMPT_VERSION,
        data_snapshot_hash=snapshot_hash,
        input_snapshot=data_snapshot,
        result={},
        confidence=None,
        parent_run_id=None,
        is_latest=True,
        user_note=user_note,
        status="running",
        created_at=utc_now(),
    )
    session.add(run)
    session.commit()
    session.refresh(run)
    return run


def _complete_memo_run(session: Session, run: AnalysisRun, output: dict[str, object]) -> None:
    confidence = output.get("confidence_summary")
    confidence_level = confidence.get("level") if isinstance(confidence, dict) else None
    run.result = output
    run.confidence = {"low": 0.35, "medium": 0.65, "high": 0.85}.get(
        str(confidence_level),
        0.65,
    )
    run.status = "success"
    run.is_latest = True
    run.created_at = utc_now()
    session.commit()
    session.refresh(run)


def _fail_memo_run(session: Session, run: AnalysisRun, exc: Exception) -> None:
    run.result = {
        "error": sanitize_error_text(str(exc)),
        "error_type": exc.__class__.__name__,
    }
    run.confidence = None
    run.status = "failed"
    run.is_latest = True
    run.created_at = utc_now()
    session.commit()


def _create_model_memo(
    session: Session,
    *,
    company_id: int,
    run: AnalysisRun,
    output: dict[str, object],
) -> InvestmentMemo:
    session.query(InvestmentMemo).filter(
        InvestmentMemo.company_id == company_id,
        InvestmentMemo.status.not_in(DELETED_MEMO_STATUSES),
    ).update({"is_latest": False}, synchronize_session="fetch")
    version_no = (
        session.scalar(
            select(func.max(InvestmentMemo.version_no)).where(
                InvestmentMemo.company_id == company_id
            )
        )
        or 0
    ) + 1
    memo = InvestmentMemo(
        company_id=company_id,
        generation_run_id=run.id,
        parent_memo_id=None,
        version_no=version_no,
        editor_type="model",
        title=str(output.get("title") or "综合投资备忘录"),
        conclusion=str(output.get("research_conclusion") or "需复核"),
        sections=output,
        markdown=_build_memo_markdown(output),
        source_analyst_run_ids=_normalize_int_list(
            output.get("source_map", {}).get("analyst_run_ids")
            if isinstance(output.get("source_map"), dict)
            else []
        ),
        source_snapshot_hash=run.data_snapshot_hash,
        change_note=None,
        status="draft",
        is_latest=True,
        created_at=utc_now(),
        updated_at=utc_now(),
    )
    session.add(memo)
    session.commit()
    session.refresh(memo)
    return memo


def _recompute_latest_memo(session: Session, *, company_id: int) -> InvestmentMemo | None:
    session.query(InvestmentMemo).filter(InvestmentMemo.company_id == company_id).update(
        {"is_latest": False},
        synchronize_session=False,
    )
    latest = session.scalar(
        select(InvestmentMemo)
        .where(
            InvestmentMemo.company_id == company_id,
            InvestmentMemo.status.not_in(DELETED_MEMO_STATUSES),
        )
        .order_by(InvestmentMemo.created_at.desc(), InvestmentMemo.id.desc())
    )
    if latest is not None:
        latest.is_latest = True
        latest.updated_at = utc_now()
    session.commit()
    if latest is not None:
        session.refresh(latest)
    return latest


def _source_run_snapshot(run: AnalysisRun) -> dict[str, object]:
    result = run.result if isinstance(run.result, dict) else {}
    return {
        "run_id": run.id,
        "analyst_profile": run.analyst_profile,
        "created_at": run.created_at.isoformat(),
        "data_snapshot_hash": run.data_snapshot_hash,
        "confidence": run.confidence,
        "profile_fit_score": result.get("profile_fit_score"),
        "overview": result.get("overview"),
        "result": _compact_analyst_result(result),
    }


def _compact_analyst_result(result: dict[str, object]) -> dict[str, object]:
    keys = (
        "overview",
        "key_observations",
        "rule_checks",
        "financial_observations",
        "announcement_observations",
        "risk_flags",
        "counter_evidence",
        "valuation_assumption_suggestions",
        "valuation_assumption_details",
        "data_gaps",
        "follow_up_questions",
        "analysis_basis",
    )
    return {key: result.get(key) for key in keys if key in result}


def _prepare_valuation_signal_pack(
    model_pack: object,
    data_snapshot: dict[str, object],
) -> dict[str, object]:
    pack = _build_service_valuation_signal_pack(data_snapshot)
    sanitized_model_pack = _scrub_price_blind_value(model_pack)
    if isinstance(sanitized_model_pack, dict):
        for key in (
            "consensus_parameter_impacts",
            "dissent_parameter_impacts",
            "risk_constraints",
            "data_gaps_for_valuation",
        ):
            values = sanitized_model_pack.get(key)
            if isinstance(values, list) and values:
                pack[key] = values

    scrubbed_pack = _scrub_price_blind_value(pack)
    validated = MemoValuationSignalPack.model_validate(scrubbed_pack).model_dump(mode="json")
    validated["price_blind_compatible"] = True
    validated["user_confirmation_required"] = True
    _assert_price_blind_signal_pack(validated)
    return validated


def _build_service_valuation_signal_pack(data_snapshot: dict[str, object]) -> dict[str, object]:
    source_runs = data_snapshot.get("source_analyst_runs")
    if not isinstance(source_runs, list):
        source_runs = []
    profile_names = {profile.id: profile.display_name for profile in list_analyst_profiles()}
    analyst_signals = [
        _build_analyst_valuation_signal(run, profile_names)
        for run in source_runs
        if isinstance(run, dict)
    ]
    ledger = data_snapshot.get("committee_ledger")
    if not isinstance(ledger, dict):
        ledger = {}
    return {
        "price_blind_compatible": True,
        "source": "latest_successful_analyst_view_runs",
        "analyst_signals": analyst_signals,
        "consensus_parameter_impacts": _build_consensus_parameter_impacts(ledger),
        "dissent_parameter_impacts": [],
        "risk_constraints": [
            str(item.get("summary") or "")
            for item in ledger.get("critical_risk_candidates", [])
            if isinstance(item, dict) and str(item.get("summary") or "").strip()
        ][:12],
        "data_gaps_for_valuation": [
            str(item.get("summary") or "")
            for item in ledger.get("data_gap_candidates", [])
            if isinstance(item, dict) and str(item.get("summary") or "").strip()
        ][:12],
        "user_confirmation_required": True,
    }


def _build_analyst_valuation_signal(
    run: dict[str, object],
    profile_names: dict[str, str],
) -> dict[str, object]:
    run_id = _as_int(run.get("run_id"))
    profile_id = str(run.get("analyst_profile") or "").strip()
    result = run.get("result")
    if not isinstance(result, dict):
        result = {}
    text = _analyst_text(result)
    source_refs = _source_refs_from_result(result, default_run_id=run_id)
    cash_signal = _signal_from_terms(
        text,
        positive=("cash flow", "free cash flow", "现金流", "自由现金流", "现金创造"),
        negative=("cash flow risk", "现金流恶化", "现金流不足", "缺少现金流"),
    )
    balance_sheet_signal = _signal_from_terms(
        text,
        positive=("net cash", "low leverage", "现金充足", "低杠杆", "净现金"),
        negative=("debt", "leverage", "偿债", "杠杆", "负债压力"),
    )
    return {
        "profile_id": profile_id,
        "profile_name": profile_names.get(profile_id, profile_id),
        "source_run_id": run_id,
        "profile_fit_score": _as_float(run.get("profile_fit_score")),
        "data_confidence": _as_float(run.get("confidence")),
        "business_quality_signal": _signal_from_terms(
            text,
            positive=("business quality", "商业质量", "生意模式", "高质量"),
            negative=("business risk", "模式风险", "质量下滑"),
        ),
        "moat_durability_signal": _signal_from_terms(
            text,
            positive=("moat", "brand", "护城河", "品牌", "竞争优势"),
            negative=("moat erosion", "竞争恶化", "护城河削弱"),
        ),
        "growth_runway_signal": _signal_from_terms(
            text,
            positive=("growth", "runway", "成长", "增长", "天花板"),
            negative=("growth slowdown", "增长放缓", "增长质量下调"),
        ),
        "pricing_power_signal": _signal_from_terms(
            text,
            positive=("pricing power", "gross margin", "定价权", "毛利率"),
            negative=("price war", "定价权削弱", "毛利率下滑"),
        ),
        "capital_intensity_signal": _signal_from_terms(
            text,
            positive=("asset light", "low capex", "轻资产", "低资本开支"),
            negative=("capital expenditure", "capex", "资本开支", "重资产"),
        ),
        "cash_flow_reliability_signal": cash_signal,
        "balance_sheet_risk_signal": balance_sheet_signal,
        "management_capital_allocation_signal": _signal_from_terms(
            text,
            positive=("capital allocation", "dividend", "buyback", "资本配置", "分红", "回购"),
            negative=("misallocation", "资本配置风险", "激进扩张"),
        ),
        "cyclicality_signal": _signal_from_terms(
            text,
            positive=("stable demand", "稳定需求", "刚需"),
            negative=("cyclical", "macro", "周期", "宏观"),
            default="unknown",
        ),
        "permanent_loss_risk_signal": _signal_from_terms(
            text,
            positive=("downside protection", "下行保护", "资产保护"),
            negative=("permanent loss", "永久损失", "诚信", "治理风险"),
            default="unknown",
        ),
        "valuation_method_preference": _derive_method_preferences(
            text,
            cash_signal=cash_signal,
            balance_sheet_signal=balance_sheet_signal,
        ),
        "parameter_impacts": _derive_parameter_impacts(result, source_refs),
        "source_refs": source_refs,
    }


def _build_consensus_parameter_impacts(ledger: dict[str, object]) -> list[dict[str, object]]:
    impacts: list[dict[str, object]] = []
    for item in ledger.get("valuation_assumption_queue", []):
        if not isinstance(item, dict):
            continue
        source_refs = item.get("source_refs") if isinstance(item.get("source_refs"), dict) else {}
        impacts.append(
            {
                "parameter": _map_parameter_name(str(item.get("assumption_type") or "")),
                "direction": _direction_from_text(str(item.get("reason") or "")),
                "magnitude": "low",
                "scenario": "all",
                "reason": str(item.get("reason") or ""),
                "confidence": 0.45,
                "requires_user_review": True,
                "source_refs": source_refs,
            }
        )
    return impacts[:20]


def _derive_method_preferences(
    text: str,
    *,
    cash_signal: str,
    balance_sheet_signal: str,
) -> list[dict[str, object]]:
    preferences: list[dict[str, object]] = []
    if cash_signal in {"positive", "neutral"} or _has_any(text, ("现金流", "cash flow")):
        preferences.append(
            {
                "method": "dcf",
                "direction": "up",
                "reason": "cash-flow-oriented analyst signal",
                "confidence": 0.55,
            }
        )
        preferences.append(
            {
                "method": "owner_earnings",
                "direction": "up",
                "reason": "owner-earnings inputs should be reviewed",
                "confidence": 0.55,
            }
        )
    if _has_any(text, ("dividend", "payout", "分红", "股东回报")):
        preferences.append(
            {
                "method": "dividend_discount",
                "direction": "up",
                "reason": "shareholder-return signal",
                "confidence": 0.45,
            }
        )
    if balance_sheet_signal in {"positive", "negative"} or _has_any(text, ("资产", "负债", "roe")):
        preferences.append(
            {
                "method": "residual_income",
                "direction": "neutral",
                "reason": "balance-sheet and profitability inputs should be cross-checked",
                "confidence": 0.4,
            }
        )
    return _dedupe_dicts(preferences, ("method", "direction"))


def _derive_parameter_impacts(
    result: dict[str, object],
    source_refs: dict[str, object],
) -> list[dict[str, object]]:
    impacts: list[dict[str, object]] = []
    for detail in _normalize_valuation_details(result):
        reason = str(detail.get("reason") or "")
        refs = _merge_source_refs(detail.get("source_refs"), default_run_id=None)
        if not refs.get("analyst_run_ids"):
            refs = source_refs
        impacts.append(
            {
                "parameter": _map_parameter_name(str(detail.get("assumption_type") or "")),
                "direction": _direction_from_text(reason),
                "magnitude": "medium" if _has_any(reason, ("核心", "critical", "key")) else "low",
                "scenario": "all",
                "reason": reason,
                "confidence": 0.5,
                "requires_user_review": True,
                "source_refs": refs,
            }
        )
    for risk in _normalize_str_list(result.get("risk_flags")):
        impacts.append(
            {
                "parameter": "discount_rate",
                "direction": "up",
                "magnitude": "low",
                "scenario": "conservative",
                "reason": risk,
                "confidence": 0.45,
                "requires_user_review": True,
                "source_refs": source_refs,
            }
        )
        impacts.append(
            {
                "parameter": "scenario_spread",
                "direction": "widen",
                "magnitude": "low",
                "scenario": "all",
                "reason": risk,
                "confidence": 0.45,
                "requires_user_review": True,
                "source_refs": source_refs,
            }
        )
    for gap in _normalize_str_list(result.get("data_gaps")):
        impacts.append(
            {
                "parameter": "scenario_spread",
                "direction": "widen",
                "magnitude": "medium",
                "scenario": "all",
                "reason": gap,
                "confidence": 0.35,
                "requires_user_review": True,
                "source_refs": source_refs,
            }
        )
    return _dedupe_dicts(impacts, ("parameter", "direction", "reason"))[:20]


def _source_refs_from_result(
    result: dict[str, object],
    *,
    default_run_id: int | None,
) -> dict[str, object]:
    refs: dict[str, object] = {}
    analysis_basis = result.get("analysis_basis")
    if isinstance(analysis_basis, dict):
        refs["evidence_ids"] = analysis_basis.get("external_evidence_ids")
        refs["announcement_ids"] = analysis_basis.get("announcement_ids")
        refs["financial_periods"] = analysis_basis.get("financial_periods")
    rule_checks = result.get("rule_checks")
    if isinstance(rule_checks, list):
        evidence_ids: list[int] = _normalize_int_list(refs.get("evidence_ids"))
        announcement_ids: list[int] = _normalize_int_list(refs.get("announcement_ids"))
        financial_periods: list[str] = _normalize_str_list(refs.get("financial_periods"))
        for item in rule_checks:
            if not isinstance(item, dict):
                continue
            evidence_ids.extend(_normalize_int_list(item.get("evidence_ids")))
            announcement_ids.extend(_normalize_int_list(item.get("announcement_ids")))
            financial_periods.extend(_normalize_str_list(item.get("financial_periods")))
        refs["evidence_ids"] = evidence_ids
        refs["announcement_ids"] = announcement_ids
        refs["financial_periods"] = financial_periods
    return _merge_source_refs(refs, default_run_id=default_run_id)


def _analyst_text(result: dict[str, object]) -> str:
    keys = (
        "overview",
        "key_observations",
        "rule_checks",
        "financial_observations",
        "announcement_observations",
        "risk_flags",
        "counter_evidence",
        "valuation_assumption_suggestions",
        "valuation_assumption_details",
        "data_gaps",
        "follow_up_questions",
    )
    payload = {key: result.get(key) for key in keys if key in result}
    return json.dumps(payload, ensure_ascii=False, default=str).lower()


def _signal_from_terms(
    text: str,
    *,
    positive: tuple[str, ...],
    negative: tuple[str, ...],
    default: str = "neutral",
) -> str:
    if _has_any(text, negative):
        return "negative"
    if _has_any(text, positive):
        return "positive"
    return default


def _direction_from_text(text: str) -> str:
    lowered = text.lower()
    if _has_any(lowered, ("down", "lower", "下调", "压低", "下降", "恶化")):
        return "down"
    if _has_any(lowered, ("widen", "扩大", "波动", "不确定", "缺口")):
        return "widen"
    if _has_any(lowered, ("cap", "上限", "封顶")):
        return "cap"
    if _has_any(lowered, ("up", "raise", "提高", "上调", "增长", "改善")):
        return "up"
    return "neutral"


def _map_parameter_name(value: str) -> str:
    lowered = value.lower()
    if _has_any(lowered, ("owner", "earnings", "净利润", "利润")):
        return "owner_earnings_growth_rate"
    if _has_any(lowered, ("discount", "折现")):
        return "discount_rate"
    if _has_any(lowered, ("terminal", "永续", "终值")):
        return "terminal_growth_rate"
    if _has_any(lowered, ("spread", "scenario", "情景")):
        return "scenario_spread"
    if _has_any(lowered, ("method", "weight", "方法", "权重")):
        return "method_weight_adjustment"
    return "cash_flow_growth_rate" if _has_any(lowered, ("cash", "现金")) else "review_parameter"


def _has_any(text: str, terms: tuple[str, ...]) -> bool:
    lowered = text.lower()
    return any(term.lower() in lowered for term in terms)


def _as_float(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return max(0.0, min(1.0, float(value)))
    if isinstance(value, str):
        try:
            return max(0.0, min(1.0, float(value.strip())))
        except ValueError:
            return None
    return None


def _dedupe_dicts(
    values: list[dict[str, object]],
    keys: tuple[str, ...],
) -> list[dict[str, object]]:
    unique: list[dict[str, object]] = []
    seen: set[tuple[str, ...]] = set()
    for item in values:
        key = tuple(str(item.get(field) or "") for field in keys)
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique


def _scrub_price_blind_value(value: object) -> object:
    if isinstance(value, dict):
        scrubbed: dict[str, object] = {}
        for key, nested in value.items():
            key_text = str(key)
            if _is_forbidden_price_key(key_text):
                continue
            scrubbed[key_text] = _scrub_price_blind_value(nested)
        return scrubbed
    if isinstance(value, list):
        return [_scrub_price_blind_value(item) for item in value]
    if isinstance(value, str):
        return _sanitize_price_blind_text(value)
    return value


def _is_forbidden_price_key(key: str) -> bool:
    if key in {"price_blind_compatible", "pricing_power_signal"}:
        return False
    lowered = key.lower()
    return lowered in PRICE_BLIND_FORBIDDEN_KEYS or any(
        term in lowered for term in PRICE_BLIND_FORBIDDEN_KEYS if term != "rating"
    )


def _sanitize_price_blind_text(value: str) -> str:
    lowered = value.lower()
    if any(_contains_forbidden_price_term(lowered, term) for term in PRICE_BLIND_FORBIDDEN_TERMS):
        return "anchor_removed_for_010"
    return value


def _assert_price_blind_signal_pack(pack: dict[str, object]) -> None:
    serialized = json.dumps(pack, ensure_ascii=False, sort_keys=True, default=str).lower()
    for allowed in ("price_blind_compatible", "pricing_power_signal"):
        serialized = serialized.replace(allowed, "")
    matched = [
        term
        for term in PRICE_BLIND_FORBIDDEN_TERMS
        if _contains_forbidden_price_term(serialized, term)
    ]
    if matched:
        raise ModelOutputValidationError(
            f"valuation_signal_pack contains price anchor: {matched[0]}"
        )


def _contains_forbidden_price_term(text: str, term: str) -> bool:
    lowered = term.lower()
    if lowered == "rating":
        return re.search(r"(?<![a-z])rating(?![a-z])", text) is not None
    return lowered in text


def _apply_source_map_override(
    output: dict[str, object],
    data_snapshot: dict[str, object],
) -> None:
    ledger = data_snapshot.get("committee_ledger")
    if not isinstance(ledger, dict):
        return
    output["source_map"] = {
        "analyst_run_ids": _normalize_int_list(ledger.get("source_run_ids")),
        "evidence_ids": _normalize_int_list(ledger.get("shared_evidence_ids")),
        "announcement_ids": _normalize_int_list(ledger.get("shared_announcement_ids")),
        "financial_periods": _normalize_str_list(ledger.get("financial_periods")),
    }


def _validate_output_references(
    output: dict[str, object],
    data_snapshot: dict[str, object],
) -> None:
    allowed = _allowed_source_refs(data_snapshot)
    for key, value in _walk_dict_values(output):
        if key in {"source_run_ids", "analyst_run_ids"}:
            invalid = set(_normalize_int_list(value)) - allowed["analyst_run_ids"]
            if invalid:
                raise ModelOutputValidationError(
                    f"模型引用了不存在的 analyst run：{sorted(invalid)}"
                )
        elif key == "evidence_ids":
            invalid = set(_normalize_int_list(value)) - allowed["evidence_ids"]
            if invalid:
                raise ModelOutputValidationError(f"模型引用了不存在的 Evidence：{sorted(invalid)}")
        elif key == "announcement_ids":
            invalid = set(_normalize_int_list(value)) - allowed["announcement_ids"]
            if invalid:
                raise ModelOutputValidationError(f"模型引用了不存在的公告：{sorted(invalid)}")
        elif key == "financial_periods":
            invalid_periods = set(_normalize_str_list(value)) - allowed["financial_periods"]
            if invalid_periods:
                raise ModelOutputValidationError(
                    f"模型引用了不存在的财务期间：{sorted(invalid_periods)}"
                )


def _allowed_source_refs(data_snapshot: dict[str, object]) -> dict[str, set[Any]]:
    ledger = data_snapshot.get("committee_ledger")
    if not isinstance(ledger, dict):
        return {
            "analyst_run_ids": set(),
            "evidence_ids": set(),
            "announcement_ids": set(),
            "financial_periods": set(),
        }
    return {
        "analyst_run_ids": set(_normalize_int_list(ledger.get("source_run_ids"))),
        "evidence_ids": set(_normalize_int_list(ledger.get("shared_evidence_ids"))),
        "announcement_ids": set(_normalize_int_list(ledger.get("shared_announcement_ids"))),
        "financial_periods": set(_normalize_str_list(ledger.get("financial_periods"))),
    }


def _validate_no_prohibited_actions(output: dict[str, object]) -> None:
    for key, value in _walk_dict_values(output):
        if key == "prohibited_actions_note":
            continue
        if isinstance(value, str):
            matched = [term for term in PROHIBITED_ACTION_TERMS if term in value]
            if matched:
                raise ModelOutputValidationError(
                    f"009 输出包含禁止的交易动作或价格判断：{matched[0]}"
                )


def _walk_dict_values(value: object) -> list[tuple[str, object]]:
    items: list[tuple[str, object]] = []
    if isinstance(value, dict):
        for key, nested in value.items():
            items.append((str(key), nested))
            items.extend(_walk_dict_values(nested))
    elif isinstance(value, list):
        for nested in value:
            items.extend(_walk_dict_values(nested))
    return items


def _build_memo_markdown(output: dict[str, object]) -> str:
    lines = [
        f"# {output.get('title') or '综合投资备忘录'}",
        "",
        f"研究结论：{output.get('research_conclusion') or '需复核'}",
        "",
        str(output.get("executive_summary") or ""),
    ]
    for title, key in (
        ("核心判断", "core_thesis"),
        ("关键风险", "key_risks"),
        ("反方证据", "counter_evidence"),
        ("数据缺口", "data_gaps"),
        ("后续问题", "follow_up_questions"),
    ):
        values = _normalize_str_list(output.get(key))
        if not values:
            continue
        lines.extend(["", f"## {title}"])
        lines.extend(f"- {item}" for item in values)
    return "\n".join(lines).strip()


def _normalize_valuation_details(result: dict[str, object]) -> list[dict[str, object]]:
    details = result.get("valuation_assumption_details")
    if isinstance(details, list) and details:
        return [dict(item) for item in details if isinstance(item, dict)]

    assumptions = []
    for item in _normalize_str_list(result.get("valuation_assumption_suggestions")):
        assumptions.append(
            {
                "assumption_type": "review_only",
                "scenario_bias": "review_only",
                "reason": item,
                "needed_inputs": [],
                "risk_adjustments": [],
                "source_refs": {},
            }
        )
    return assumptions


def _merge_source_refs(value: object, *, default_run_id: int | None) -> dict[str, object]:
    source_refs = value if isinstance(value, dict) else {}
    analyst_run_ids = _normalize_int_list(source_refs.get("analyst_run_ids"))
    if default_run_id is not None and default_run_id not in analyst_run_ids:
        analyst_run_ids.append(default_run_id)
    return {
        "analyst_run_ids": analyst_run_ids,
        "evidence_ids": _normalize_int_list(source_refs.get("evidence_ids")),
        "announcement_ids": _normalize_int_list(source_refs.get("announcement_ids")),
        "financial_periods": _normalize_str_list(source_refs.get("financial_periods")),
    }


def _dedupe_valuation_assumptions(values: list[dict[str, object]]) -> list[dict[str, object]]:
    unique: list[dict[str, object]] = []
    seen: set[tuple[str, str]] = set()
    for item in values:
        key = (str(item.get("assumption_type") or ""), str(item.get("reason") or ""))
        if key in seen or not key[1]:
            continue
        seen.add(key)
        unique.append(item)
    return unique


def _dedupe_summary_dicts(values: list[dict[str, object]]) -> list[dict[str, object]]:
    unique: list[dict[str, object]] = []
    seen: set[str] = set()
    for item in values:
        summary = str(item.get("summary") or "")
        if not summary or summary in seen:
            continue
        seen.add(summary)
        unique.append(item)
    return unique


def _topic_key(value: str) -> str:
    normalized = value.strip().rstrip("。；;")
    return normalized[:30] if normalized else "未分类主题"


def _company_snapshot(company: Company) -> dict[str, object]:
    return {
        "id": company.id,
        "ticker": company.ticker,
        "exchange": company.exchange,
        "name": company.name,
        "industry": company.industry,
        "description": company.description,
        "listed_date": company.listed_date.isoformat() if company.listed_date else None,
        "status": company.status,
        "tags": company.tags,
    }


def _hash_snapshot(snapshot: dict[str, object]) -> str:
    payload = json.dumps(snapshot, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _as_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None


def _normalize_int_list(value: object) -> list[int]:
    if isinstance(value, int) and not isinstance(value, bool):
        value = [value]
    if not isinstance(value, list):
        return []
    return _unique_ints(value)


def _unique_ints(values: object) -> list[int]:
    items: list[int] = []
    if not isinstance(values, list):
        values = list(values) if values is not None else []
    for value in values:
        parsed = _as_int(value)
        if parsed is not None and parsed not in items:
            items.append(parsed)
    return items


def _normalize_str_list(value: object) -> list[str]:
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return []
    return _unique_strings(value)


def _unique_strings(values: object) -> list[str]:
    items: list[str] = []
    if not isinstance(values, list):
        values = list(values) if values is not None else []
    for value in values:
        normalized = str(value).strip()
        if normalized and normalized not in items:
            items.append(normalized)
    return items
