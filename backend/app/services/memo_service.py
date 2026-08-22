from __future__ import annotations

import hashlib
import json
import re
from collections import Counter, defaultdict
from copy import deepcopy
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
from app.analysis.valuation_parameter_matrix import find_price_anchor
from app.configuration.runtime import parameter_config_context, parameter_value
from app.db.models import AnalysisRun, Company, InvestmentMemo, utc_now
from app.schemas.memo import InvestmentMemoOutput
from app.services.analyst_service import RUN_TYPE_ANALYST_VIEW, list_latest_company_analysis_runs
from app.services.parameter_config_service import get_runtime_parameter_config

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
    source_run_snapshots = [
        _scrub_price_blind_value(_source_run_snapshot(run)) for run in source_runs
    ]
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
            "minimum_successful_profiles": int(
                parameter_value("memo_decision.min_successful_analysts", 2)
            ),
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
    runtime = get_runtime_parameter_config(session)
    with parameter_config_context(runtime.snapshot):
        data_snapshot = build_investment_memo_snapshot(session, company)
        data_snapshot["configuration"] = {
            "version": runtime.version,
            "hash": runtime.config_hash,
            "source": runtime.source,
            "fallback_reason": runtime.fallback_reason,
        }
        source_runs = data_snapshot.get("source_analyst_runs")
        minimum = int(parameter_value("memo_decision.min_successful_analysts", 2))
        if not isinstance(source_runs, list) or len(source_runs) < minimum:
            raise InvestmentMemoInsufficientSourcesError(
                f"至少需要 {minimum} 个成功分析师视角才能生成综合备忘录。"
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
            config_version=runtime.version,
            config_hash=runtime.config_hash,
            config_snapshot=runtime.snapshot,
        )

        try:
            output_payload = _generate_memo_output(
                model_gateway,
                data_snapshot=data_snapshot,
                strict_boundary_retry=False,
                temperature=float(parameter_value("analyst_engine.model_temperatures.memo", 0.2)),
            )
            try:
                _validate_price_blind_output(output_payload)
            except ModelOutputValidationError:
                output_payload = _generate_memo_output(
                    model_gateway,
                    data_snapshot=data_snapshot,
                    strict_boundary_retry=True,
                    temperature=0.0,
                )
                _validate_price_blind_output(output_payload)
            _apply_source_map_override(output_payload, data_snapshot)
            _validate_output_references(output_payload, data_snapshot)
            _validate_no_prohibited_actions(output_payload)
            _complete_memo_run(session, run, output_payload)
            memo = _create_model_memo(
                session,
                company_id=company.id,
                run=run,
                output=output_payload,
            )
            return run, memo
        except (ModelGatewayError, ModelOutputValidationError, ValueError) as exc:
            _fail_memo_run(session, run, exc)
            raise
        except Exception as exc:
            _fail_memo_run(session, run, exc)
            raise


def _generate_memo_output(
    model_gateway: ModelGateway,
    *,
    data_snapshot: dict[str, object],
    strict_boundary_retry: bool,
    temperature: float,
) -> dict[str, object]:
    output = model_gateway.generate_structured(
        system_prompt=MEMO_SYSTEM_PROMPT,
        user_prompt=build_memo_prompt(
            data_snapshot,
            strict_boundary_retry=strict_boundary_retry,
        ),
        schema=InvestmentMemoOutput,
        temperature=temperature,
    )
    return output.model_dump(mode="json")


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
    config_version: int | None,
    config_hash: str,
    config_snapshot: dict[str, object],
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
        config_version=config_version,
        config_hash=config_hash,
        config_snapshot=deepcopy(config_snapshot),
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
    confidence_map = parameter_value("memo_decision.model_confidence_map", {})
    confidence_map = confidence_map if isinstance(confidence_map, dict) else {}
    run.confidence = confidence_map.get(
        str(confidence_level),
        confidence_map.get("medium", 0.65),
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
        config_version=run.config_version,
        config_hash=run.config_hash,
        config_snapshot=deepcopy(run.config_snapshot),
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
    input_snapshot = run.input_snapshot if isinstance(run.input_snapshot, dict) else {}
    return {
        "run_id": run.id,
        "analyst_profile": run.analyst_profile,
        "created_at": run.created_at.isoformat(),
        "data_snapshot_hash": run.data_snapshot_hash,
        "confidence": run.confidence,
        "profile_fit_score": result.get("profile_fit_score"),
        "overview": result.get("overview"),
        "result": _compact_analyst_result(result),
        "market_context": _source_market_context(input_snapshot),
    }


def _source_market_context(input_snapshot: dict[str, object]) -> dict[str, object]:
    company = input_snapshot.get("company")
    company = company if isinstance(company, dict) else {}
    financial_pack = input_snapshot.get("financial_evidence_pack")
    financial_pack = financial_pack if isinstance(financial_pack, dict) else {}
    announcements = input_snapshot.get("announcements")
    announcements = announcements if isinstance(announcements, list) else []
    announcement_rows = [item for item in announcements if isinstance(item, dict)]
    return {
        "issuer": {
            key: company.get(key)
            for key in (
                "canonical_key",
                "legal_name",
                "domicile_country",
                "reporting_currency",
                "fiscal_year_end",
                "primary_listing",
            )
            if company.get(key) is not None
        },
        "reporting_currency": financial_pack.get("reporting_currency"),
        "accounting_standard": financial_pack.get("accounting_standard"),
        "disclosure_languages": sorted(
            {
                str(item["language"])
                for item in announcement_rows
                if item.get("language")
            }
        ),
        "filing_forms": sorted(
            {
                str(item["filing_form"])
                for item in announcement_rows
                if item.get("filing_form")
            }
        ),
        "document_types": sorted(
            {
                str(item["document_type"])
                for item in announcement_rows
                if item.get("document_type")
            }
        ),
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


def _validate_price_blind_output(output: dict[str, object]) -> None:
    for key, value in _walk_dict_values(output):
        if key in {"prohibited_actions_note", "price_decision_status"}:
            continue
        match = find_price_anchor(value)
        if match is not None:
            raise ModelOutputValidationError(f"009 输出包含禁止的价格锚：{match}")


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
    primary_listing = company.primary_listing
    return {
        "id": company.id,
        "ticker": company.ticker,
        "exchange": company.exchange,
        "name": company.name,
        "canonical_key": company.canonical_key,
        "legal_name": company.legal_name,
        "aliases": list(company.aliases or []),
        "domicile_country": company.domicile_country,
        "reporting_currency": company.reporting_currency,
        "fiscal_year_end": company.fiscal_year_end,
        "industry": company.industry,
        "description": company.description,
        "listed_date": company.listed_date.isoformat() if company.listed_date else None,
        "status": company.status,
        "tags": company.tags,
        "primary_listing": (
            {
                "id": primary_listing.id,
                "ticker": primary_listing.ticker,
                "exchange": primary_listing.exchange,
                "market": primary_listing.market,
                "trading_currency": primary_listing.trading_currency,
                "security_type": primary_listing.security_type,
            }
            if primary_listing is not None
            else None
        ),
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
