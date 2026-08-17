from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Literal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.analysis.analyst_profiles import (
    AnalystProfile,
    get_analyst_profile,
    list_analyst_profiles,
)
from app.analysis.model_gateway import (
    ModelGateway,
    ModelGatewayError,
    ModelOutputValidationError,
)
from app.analysis.prompts.analyst import (
    ANALYST_SYSTEM_PROMPT,
    PROMPT_VERSION,
    build_analyst_prompt,
)
from app.analysis.result_sanitizer import sanitize_error_text
from app.analysis.valuation_parameter_matrix import derive_valuation_parameter_matrix
from app.configuration.runtime import parameter_config_context, parameter_value
from app.db.models import (
    AnalysisRun,
    Announcement,
    Company,
    Evidence,
    FinancialStatement,
    utc_now,
)
from app.schemas.analysis import AnalystAnalysisOutput
from app.services.financial_metrics import (
    build_financial_evidence_pack,
    order_financial_statement_query,
)
from app.services.parameter_config_service import get_runtime_parameter_config

RUN_TYPE_ANALYST_VIEW = "analyst_view"
RUN_VERSION = "008_v1"
MAX_RESULT_LIST_ITEMS = 6
PRICE_SENSITIVE_TEXT_TERMS = (
    "当前价格",
    "历史价格",
    "目标价",
    "市值",
    "持仓成本",
    "估值倍数",
    "市盈率",
    "市净率",
    "市销率",
    "评级",
    "市场情绪",
    "安全边际",
    "买入",
    "卖出",
    "加仓",
    "减仓",
    "current price",
    "historical price",
    "target price",
    "market cap",
    "holding cost",
    "market sentiment",
    "safety margin",
)
PRICE_SENSITIVE_FIELD_NAMES = {
    "current_price",
    "historical_price",
    "history_price",
    "target_price",
    "market_cap",
    "holding_cost",
    "position_cost",
    "valuation_multiple",
    "ev_ebitda",
    "rating",
    "broker_rating",
    "market_rating",
    "market_sentiment",
    "safety_margin",
    "trade_action",
    "pe_ttm",
    "pe_dynamic",
    "pe_static",
    "pb_ratio",
    "ps_ratio",
    "market_data_source",
    "market_data_source_url",
    "market_data_updated_at",
}
ANALYST_EXTERNAL_EVIDENCE_FIELDS = (
    "id",
    "title",
    "published_at",
    "source_type",
    "summary",
)
ANNOUNCEMENT_PRIORITY_CATEGORIES = (
    "annual_report",
    "semi_annual_report",
    "quarterly_report",
    "financial_report",
    "audit_report",
    "major_event",
    "regulatory",
    "penalty",
    "governance",
    "dividend",
    "repurchase",
    "会计政策",
    "年度报告",
    "半年度报告",
    "季度报告",
    "分红",
    "回购",
    "处罚",
    "监管",
    "重大事项",
)
ANNOUNCEMENT_PRIORITY_TERMS = (
    "年度报告",
    "年报",
    "半年度报告",
    "季报",
    "审计",
    "会计政策",
    "会计估计",
    "收入确认",
    "核算方式",
    "追溯调整",
    "差错更正",
    "分红",
    "利润分配",
    "回购",
    "重大合同",
    "关联交易",
    "处罚",
    "监管",
    "问询函",
    "管理层",
    "董事",
    "高管",
    "控制权",
    "诉讼",
    "担保",
    "减值",
    "非经常性",
)
EVIDENCE_SOURCE_PRIORITY = {
    "regulatory": 0.2,
    "public_data": 0.18,
    "policy": 0.16,
    "web": 0.1,
    "company_news": 0.08,
    "industry_news": 0.06,
}
INCOME_STATEMENT_FLAG_OBSERVATIONS = {
    "high_investment_income_to_profit": "投资收益占净利润较高，需要复核利润可持续性。",
    "high_fair_value_change_to_profit": "公允价值变动占净利润较高，需要复核利润质量。",
    "high_impairment_loss_to_profit": "减值损失占净利润较高，需要复核资产质量。",
    "high_non_operating_profit_to_profit": "营业外收支占净利润较高，需要识别非经常性利润贡献。",
    "deducted_profit_lags_parent_profit": (
        "扣非净利润显著弱于归母净利润，需要识别非经常性利润贡献。"
    ),
    "period_expense_ratio_rise": "期间费用率连续上升，费用纪律需要关注。",
    "finance_expense_ratio_rise": "财务费用率上升，融资成本或杠杆压力需要关注。",
    "operating_margin_decline": "营业利润率下滑，需要复核主营盈利能力。",
    "abnormal_effective_tax_rate": "有效税率异常，需要复核所得税费用和利润口径。",
}
INCOME_STATEMENT_GAP_FIELDS = {
    "income_statement",
    "operating_cost",
    "expense_breakdown",
    "operating_profit",
    "impairment_losses",
    "non_operating_items",
    "income_tax_expense",
}
ANALYST_AMOUNT_SERIES_FIELDS = (
    "revenue",
    "net_profit",
    "deducted_net_profit",
    "operating_cash_flow",
    "capital_expenditure",
    "free_cash_flow",
    "dividend",
)
ANALYST_PERCENTAGE_METRIC_PATHS = (
    ("profitability", "roe"),
    ("profitability", "gross_margin"),
    ("profitability", "net_margin"),
    ("profit_structure", "operating_margin"),
    ("profit_structure", "deducted_net_profit_to_net_profit"),
    ("profit_structure", "investment_income_to_net_profit"),
    ("profit_structure", "fair_value_change_to_net_profit"),
    ("profit_structure", "impairment_loss_to_net_profit"),
    ("profit_structure", "non_operating_profit_to_net_profit"),
    ("profit_structure", "effective_tax_rate"),
    ("expense_control", "selling_expense_ratio"),
    ("expense_control", "admin_expense_ratio"),
    ("expense_control", "r_and_d_expense_ratio"),
    ("expense_control", "finance_expense_ratio"),
    ("expense_control", "period_expense_ratio"),
    ("cash_quality", "operating_cash_flow_to_revenue"),
    ("cash_quality", "free_cash_flow_margin"),
    ("growth_quality", "revenue_yoy"),
    ("growth_quality", "net_profit_yoy"),
    ("balance_sheet_safety", "asset_liability_ratio"),
    ("balance_sheet_safety", "interest_bearing_debt_to_equity"),
    ("shareholder_return", "dividend_payout_ratio"),
    ("shareholder_return", "buyback_ratio"),
    ("shareholder_return", "share_dilution_rate"),
    ("capital_allocation", "capital_expenditure_to_revenue"),
)
OPERATING_CASH_FLOW_TO_REVENUE_LABELS = (
    "operating_cash_flow_to_revenue",
    "经营现金流/收入",
    "经营现金流／收入",
    "经营现金流/营收",
    "经营现金流／营收",
    "经营现金流占收入",
    "经营现金流占营收",
    "经营现金流收入比",
    "经营现金流收入比例",
)

CONSUMER_BRAND_TERMS = (
    "白酒",
    "酒",
    "消费",
    "食品",
    "饮料",
    "医药",
    "品牌",
    "零售",
    "餐饮",
    "日化",
)
TECH_GROWTH_TERMS = (
    "科技",
    "软件",
    "半导体",
    "芯片",
    "互联网",
    "新能源",
    "研发",
    "创新",
    "云",
    "人工智能",
)
CYCLICAL_MACRO_TERMS = (
    "银行",
    "保险",
    "地产",
    "房地产",
    "钢铁",
    "煤炭",
    "有色",
    "化工",
    "航运",
    "航空",
    "能源",
    "汽车",
    "证券",
    "周期",
)
ASSET_HEAVY_TERMS = (
    "银行",
    "保险",
    "地产",
    "房地产",
    "基础设施",
    "公用事业",
    "电力",
    "交通",
    "钢铁",
    "煤炭",
)
ACCOUNTING_KEYWORDS: tuple[tuple[str, str, str, tuple[str, ...]], ...] = (
    (
        "accounting_policy_change",
        "会计政策变更",
        "会计政策或核算政策发生变化，跨期同比需要先确认可比口径。",
        ("会计政策变更", "会计政策", "核算政策", "新会计准则"),
    ),
    (
        "accounting_estimate_change",
        "会计估计变更",
        "会计估计变化可能影响利润释放节奏，需要拆分经营变化和估计影响。",
        ("会计估计变更", "会计估计"),
    ),
    (
        "prior_period_error_correction",
        "前期差错更正",
        "前期差错更正会影响历史基数，应避免直接把重述后变化当作经营趋势。",
        ("前期差错更正", "差错更正", "前期会计差错", "会计差错"),
    ),
    (
        "retrospective_adjustment",
        "追溯调整/重述",
        "追溯调整或重述会改变同比基数，利润或收入大幅变化需要按调整后口径复核。",
        ("追溯调整", "追溯重述", "重述", "重新列报", "调整上年同期"),
    ),
    (
        "revenue_recognition_change",
        "收入确认/核算方式变化",
        "收入确认或核算方式变化可能放大利润和收入波动，不能直接判定为经营改善或恶化。",
        ("收入确认", "收入核算", "核算方式", "总额法", "净额法", "部分业务收入确认"),
    ),
    (
        "non_recurring_factor",
        "非经常性因素",
        "非经常性损益或一次性项目会影响利润质量，需要和主营经营分开看。",
        ("非经常性", "一次性", "资产处置", "政府补助", "减值", "公允价值变动"),
    ),
)
ACCOUNTING_SELECTION_TERMS = tuple(
    sorted({keyword for _, _, _, keywords in ACCOUNTING_KEYWORDS for keyword in keywords})
)


class AnalystProfileNotFoundError(ValueError):
    pass


class AnalysisRunNotFoundError(ValueError):
    pass


class AnalysisRuleCheckNotFoundError(ValueError):
    pass


@dataclass(frozen=True)
class AnalystBatchRunResult:
    analyst_profile: str
    status: Literal["success", "failed"]
    run: AnalysisRun | None = None
    error: str | None = None
    error_type: str | None = None


def list_profiles() -> list[dict[str, object]]:
    return [profile.to_read_model() for profile in list_analyst_profiles()]


def list_company_analysis_runs(
    session: Session,
    *,
    company_id: int,
    run_type: str | None = None,
    analyst_profile: str | None = None,
    status: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> tuple[list[AnalysisRun], int]:
    filters = [AnalysisRun.company_id == company_id]
    if run_type:
        filters.append(AnalysisRun.run_type == run_type)
    if analyst_profile:
        filters.append(AnalysisRun.analyst_profile == analyst_profile)
    if status and run_type != RUN_TYPE_ANALYST_VIEW:
        filters.append(AnalysisRun.status == status)

    if run_type == RUN_TYPE_ANALYST_VIEW:
        runs = session.scalars(
            select(AnalysisRun)
            .where(*filters)
            .order_by(
                AnalysisRun.analyst_profile.asc().nullslast(),
                AnalysisRun.created_at.desc(),
                AnalysisRun.id.desc(),
            )
        ).all()
        deduped_runs = _dedupe_latest_analyst_runs(runs)
        if status:
            deduped_runs = [run for run in deduped_runs if run.status == status]
        total = len(deduped_runs)
        return deduped_runs[offset : offset + limit], total

    base_stmt = select(AnalysisRun).where(*filters)
    total_stmt = select(func.count()).select_from(AnalysisRun).where(*filters)
    items = session.scalars(
        base_stmt.order_by(AnalysisRun.created_at.desc(), AnalysisRun.id.desc())
        .offset(offset)
        .limit(limit)
    ).all()
    total = session.scalar(total_stmt) or 0
    return items, total


def list_latest_company_analysis_runs(
    session: Session,
    *,
    company_id: int,
    run_type: str | None = RUN_TYPE_ANALYST_VIEW,
    analyst_profile: str | None = None,
    status: str | None = "success",
) -> list[AnalysisRun]:
    filters = [AnalysisRun.company_id == company_id]
    current_profile_ids = [profile.id for profile in list_analyst_profiles()]
    if run_type:
        filters.append(AnalysisRun.run_type == run_type)
    if run_type == RUN_TYPE_ANALYST_VIEW:
        filters.append(AnalysisRun.analyst_profile.in_(current_profile_ids))
        if status == "success":
            filters.append(AnalysisRun.status == "success")
    if analyst_profile:
        filters.append(AnalysisRun.analyst_profile == analyst_profile)
    if status and run_type != RUN_TYPE_ANALYST_VIEW:
        filters.append(AnalysisRun.status == status)

    runs = session.scalars(
        select(AnalysisRun)
        .where(*filters)
        .order_by(
            AnalysisRun.analyst_profile.asc().nullslast(),
            AnalysisRun.created_at.desc(),
            AnalysisRun.id.desc(),
        )
    ).all()

    latest_runs = (
        _dedupe_latest_analyst_runs(runs)
        if run_type == RUN_TYPE_ANALYST_VIEW
        else _dedupe_latest_runs_by_type_and_profile(runs)
    )
    if status and status != "success":
        latest_runs = [run for run in latest_runs if run.status == status]
    if run_type == RUN_TYPE_ANALYST_VIEW:
        profile_order = {profile_id: index for index, profile_id in enumerate(current_profile_ids)}
        latest_runs.sort(
            key=lambda run: profile_order.get(str(run.analyst_profile or ""), len(profile_order))
        )
    return latest_runs


def delete_company_analysis_run(
    session: Session,
    *,
    company_id: int,
    run_id: int,
) -> int:
    run = session.get(AnalysisRun, run_id)
    if run is None or run.company_id != company_id:
        raise AnalysisRunNotFoundError("Analysis run not found")

    session.delete(run)
    session.commit()
    return run_id


def update_analysis_run_rule_status(
    session: Session,
    *,
    company_id: int,
    run_id: int,
    rule_id: str,
    status: Literal["pass", "neutral", "unknown", "warn", "fail"],
) -> AnalysisRun:
    run = session.get(AnalysisRun, run_id)
    if run is None or run.company_id != company_id or run.run_type != RUN_TYPE_ANALYST_VIEW:
        raise AnalysisRunNotFoundError("Analysis run not found")

    result = deepcopy(run.result) if isinstance(run.result, dict) else {}
    rule_checks = result.get("rule_checks")
    if not isinstance(rule_checks, list):
        raise AnalysisRuleCheckNotFoundError("Rule check not found")

    for check in rule_checks:
        if isinstance(check, dict) and check.get("rule_id") == rule_id:
            check["status"] = status
            profile = _get_profile_or_raise(str(run.analyst_profile or ""))
            config_snapshot = run.config_snapshot if isinstance(run.config_snapshot, dict) else {}
            with parameter_config_context(config_snapshot):
                result["valuation_parameter_matrix"] = derive_valuation_parameter_matrix(
                    source_run_id=run.id,
                    profile=profile,
                    result=result,
                )
            run.result = result
            session.commit()
            session.refresh(run)
            return run

    raise AnalysisRuleCheckNotFoundError("Rule check not found")


def run_company_analyst_view(
    session: Session,
    company: Company,
    analyst_profile_id: str,
    *,
    user_note: str | None = None,
    gateway: ModelGateway | None = None,
) -> AnalysisRun:
    profile = _get_profile_or_raise(analyst_profile_id)
    model_gateway = gateway or ModelGateway()
    runtime = get_runtime_parameter_config(session)
    with parameter_config_context(runtime.snapshot):
        data_snapshot = build_company_analysis_snapshot(
            session,
            company,
            profile=profile,
            config_version=runtime.version,
            config_hash=runtime.config_hash,
            config_source=runtime.source,
            config_fallback_reason=runtime.fallback_reason,
        )
        snapshot_hash = _hash_snapshot(data_snapshot)
        run = _create_running_run(
            session,
            company_id=company.id,
            profile=profile,
            model_name=model_gateway.model_name,
            data_snapshot=data_snapshot,
            snapshot_hash=snapshot_hash,
            parent_run_id=None,
            user_note=user_note,
            config_version=runtime.version,
            config_hash=runtime.config_hash,
            config_snapshot=runtime.snapshot,
        )

        try:
            output = model_gateway.generate_structured(
                system_prompt=ANALYST_SYSTEM_PROMPT,
                user_prompt=build_analyst_prompt(profile=profile, data_snapshot=data_snapshot),
                schema=AnalystAnalysisOutput,
                temperature=float(
                    parameter_value("analyst_engine.model_temperatures.analyst", 0.2)
                ),
            )
            output = _apply_fact_ledger_overrides(output, data_snapshot)
            output = _apply_financial_unit_corrections(output, data_snapshot)
            _validate_output_profile(output, profile, data_snapshot=data_snapshot)
            _complete_run(session, run, output)
            return run
        except (ModelGatewayError, ModelOutputValidationError, ValueError) as exc:
            _fail_run(session, run, exc)
            raise
        except Exception as exc:
            _fail_run(session, run, exc)
            raise


def run_company_analyst_views_batch(
    session: Session,
    company: Company,
    analyst_profile_ids: list[str],
    *,
    user_note: str | None = None,
    gateway: ModelGateway | None = None,
) -> list[AnalystBatchRunResult]:
    profile_ids = _normalize_batch_profile_ids(analyst_profile_ids)
    results: list[AnalystBatchRunResult] = []

    for profile_id in profile_ids:
        try:
            run = run_company_analyst_view(
                session,
                company,
                profile_id,
                user_note=user_note,
                gateway=gateway,
            )
        except Exception as exc:
            results.append(
                AnalystBatchRunResult(
                    analyst_profile=profile_id,
                    status="failed",
                    error=str(exc),
                    error_type=exc.__class__.__name__,
                )
            )
            continue

        results.append(
            AnalystBatchRunResult(
                analyst_profile=profile_id,
                status="success",
                run=run,
            )
        )

    return results


def _build_financial_model_display(
    financial_evidence_pack: dict[str, object],
) -> dict[str, object]:
    facts = financial_evidence_pack.get("financial_facts")
    metrics = financial_evidence_pack.get("financial_metrics")
    latest_facts = facts.get("latest") if isinstance(facts, dict) else None
    fact_series = facts.get("series") if isinstance(facts, dict) else None

    latest_amounts: dict[str, object] = {}
    if isinstance(latest_facts, dict):
        for field, value in latest_facts.items():
            if field == "shares_outstanding" or not _is_number(value):
                continue
            amount_100m_cny = float(value) / 100_000_000
            latest_amounts[str(field)] = {
                "raw_cny": float(value),
                "value_100m_cny": round(amount_100m_cny, 4),
                "display": f"{amount_100m_cny:.2f}亿元",
            }

    amount_series: dict[str, object] = {}
    if isinstance(fact_series, dict):
        for field in ANALYST_AMOUNT_SERIES_FIELDS:
            items = fact_series.get(field)
            if not isinstance(items, list):
                continue
            display_items: list[dict[str, object]] = []
            for item in items:
                if not isinstance(item, dict) or not _is_number(item.get("value")):
                    continue
                raw_value = float(item["value"])
                amount_100m_cny = raw_value / 100_000_000
                display_items.append(
                    {
                        "period": item.get("period"),
                        "value_100m_cny": round(amount_100m_cny, 4),
                        "display": f"{amount_100m_cny:.2f}亿元",
                    }
                )
            if display_items:
                amount_series[field] = display_items

    latest_percentages: dict[str, object] = {}
    if isinstance(metrics, dict):
        for section, field in ANALYST_PERCENTAGE_METRIC_PATHS:
            section_values = metrics.get(section)
            value = section_values.get(field) if isinstance(section_values, dict) else None
            if not _is_number(value):
                continue
            percent_value = float(value) * 100
            latest_percentages[field] = {
                "source_path": f"financial_metrics.{section}.{field}",
                "raw_decimal": float(value),
                "percent_value": round(percent_value, 4),
                "display": f"{percent_value:.2f}%",
            }

    return {
        "latest_period": financial_evidence_pack.get("latest_period"),
        "unit_contract": {
            "raw_monetary_unit": "CNY元",
            "display_monetary_unit": "亿元",
            "cny_per_100m": 100_000_000,
            "raw_ratio_unit": "0-1小数",
            "display_ratio_unit": "百分比",
            "ratio_conversion": "raw_decimal * 100",
            "usage": (
                "模型写金额和百分比时必须使用本对象中的 display；"
                "原始金额和原始小数只供程序计算，不得直接拼接亿元或百分号。"
            ),
        },
        "latest_amounts_100m_cny": latest_amounts,
        "amount_series_100m_cny": amount_series,
        "latest_percentages": latest_percentages,
    }


def build_company_analysis_snapshot(
    session: Session,
    company: Company,
    *,
    profile: AnalystProfile,
    config_version: int | None = None,
    config_hash: str | None = None,
    config_source: str = "builtin_fallback",
    config_fallback_reason: str | None = None,
) -> dict[str, object]:
    financials = _select_financial_snapshot_statements(session, company_id=company.id)
    announcements = session.scalars(
        select(Announcement)
        .where(Announcement.company_id == company.id)
        .order_by(Announcement.published_at.desc())
        .limit(int(parameter_value("data_sampling.analysis_announcement_pool", 80)))
    ).all()
    evidence_count = (
        session.scalar(
            select(func.count()).select_from(Evidence).where(Evidence.company_id == company.id)
        )
        or 0
    )
    evidence_items = session.scalars(
        select(Evidence)
        .where(Evidence.company_id == company.id)
        .order_by(
            (Evidence.importance_score + Evidence.credibility_score).desc(),
            Evidence.published_at.desc().nullslast(),
            Evidence.created_at.desc(),
            Evidence.id.desc(),
        )
        .limit(int(parameter_value("data_sampling.analysis_evidence_items", 10)) * 3)
    ).all()
    evidence_items = [
        item
        for item in evidence_items
        if not item.price_sensitive and not _model_contains_price_sensitive_text(item)
    ][: int(parameter_value("data_sampling.analysis_evidence_items", 10))]

    financial_snapshots = [_financial_snapshot(item) for item in financials]
    financial_evidence_pack = build_financial_evidence_pack(financials)
    financial_evidence_pack["model_display"] = _build_financial_model_display(
        financial_evidence_pack
    )
    announcement_snapshots = _select_announcement_snapshots(announcements)
    all_external_evidence_snapshots = [_evidence_snapshot(item) for item in evidence_items]
    selected_external_evidence_snapshots = _select_external_evidence_snapshots(
        all_external_evidence_snapshots
    )
    external_evidence_snapshots = [
        _project_external_evidence_snapshot(item) for item in selected_external_evidence_snapshots
    ]
    intrinsic_valuation_evidence_snapshots = [
        _project_external_evidence_snapshot(item)
        for item in selected_external_evidence_snapshots
        if "intrinsic_valuation" in _snapshot_use_scope(item)
    ]
    fact_ledger = _build_fact_ledger(
        company=company,
        profile=profile,
        financials=financial_snapshots,
        financial_evidence_pack=financial_evidence_pack,
        announcements=announcement_snapshots,
        external_evidence=selected_external_evidence_snapshots,
    )

    return {
        "configuration": {
            "version": config_version,
            "hash": config_hash,
            "source": config_source,
            "fallback_reason": config_fallback_reason,
        },
        "source_boundary": {
            "allowed_sources": [
                "external_evidence",
                "financial_statements",
                "announcements",
            ],
            "disallowed_actions": ["web_search", "data_collection", "third_party_fetch"],
            "input_policy": "008-010 保持 price-blind，行情、估值倍数和价格敏感证据不得进入快照。",
            "output_policy": "只输出基本面规则判断，不输出价格、交易动作或仓位建议。",
            "allowed_outputs": [
                "business_quality",
                "management_quality",
                "moat",
                "growth_quality",
                "risks",
                "counter_evidence",
                "valuation_assumption_suggestions",
                "valuation_sensitivity",
            ],
            "run_isolation_policy": (
                "每次 analyst_view 生成完全独立，不读取历史 run，不把历史结论作为输入。"
            ),
            "snapshot_limits": {
                "financial_statement_periods": int(
                    parameter_value("data_sampling.analysis_financial_periods", 40)
                ),
                "announcements": int(
                    parameter_value("data_sampling.analysis_announcement_items", 20)
                ),
                "evidence": int(parameter_value("data_sampling.analysis_evidence_items", 10)),
            },
            "selection_policy": {
                "financial_statements": (
                    "按 fields.report_date、period、id 倒序选最近 40 个财务期间；"
                    "每个期间保留已入库的主要财务指标、利润表（income_statement）、现金流量表、"
                    "资产负债表以及其他后续扩展分表记录。"
                ),
                "announcements": (
                    "从最近公告候选池按公告类型、会计口径/治理/分红回购/"
                    "重大事项信号和可复核内容排序，选 20 条。"
                ),
                "external_evidence": ("按重要性和可信度排序，最多选 10 条。"),
            },
            "price_sensitive_policy": {
                "rule": (
                    "price_sensitive=true 的 Evidence 不进入 008-010；"
                    "仅可在 011 价格决策阶段使用价格。"
                ),
                "analyst_view_allows_price_sensitive": False,
            },
            "source_aliases": {
                "evidence": "external_evidence",
            },
            "terminology": {
                "external_evidence": "007 外部信息模块已入库的公开信息记录。",
                "evidence": "兼容旧字段名，含义等同 external_evidence。",
            },
        },
        "profile": {
            "id": profile.id,
            "display_name": profile.display_name,
            "rules": [
                {
                    "id": rule.id,
                    "label": rule.label,
                    "description": rule.description,
                }
                for rule in profile.rules
            ],
        },
        "company": _company_snapshot(company),
        "fact_ledger": fact_ledger,
        "source_coverage_matrix": fact_ledger.get("source_coverage_matrix", {}),
        "pre_model_observations": fact_ledger.get("pre_model_observations", []),
        "financial_statements": financial_snapshots,
        "financial_evidence_pack": financial_evidence_pack,
        "announcements": announcement_snapshots,
        "external_evidence": external_evidence_snapshots,
        "evidence": external_evidence_snapshots,
        "intrinsic_valuation_input": {
            "external_evidence": intrinsic_valuation_evidence_snapshots,
        },
        "data_counts": {
            "financial_statements": len(financials),
            "financial_statement_periods": len(_financial_periods(financial_snapshots)),
            "financial_flags": len(financial_evidence_pack.get("financial_flags", [])),
            "financial_data_gaps": len(financial_evidence_pack.get("financial_data_gaps", [])),
            "announcements": len(announcement_snapshots),
            "external_evidence": len(external_evidence_snapshots),
            "evidence": len(external_evidence_snapshots),
            "announcement_candidates": len(announcements),
            "external_evidence_candidates": evidence_count,
            "price_sensitive_external_evidence": 0,
            "intrinsic_valuation_external_evidence": len(intrinsic_valuation_evidence_snapshots),
        },
    }


def _get_profile_or_raise(profile_id: str) -> AnalystProfile:
    profile = get_analyst_profile(profile_id)
    if profile is None:
        raise AnalystProfileNotFoundError(f"未知分析师 Profile：{profile_id}")
    return profile


def _normalize_batch_profile_ids(profile_ids: list[str]) -> list[str]:
    if not profile_ids:
        return [profile.id for profile in list_analyst_profiles()]

    normalized: list[str] = []
    for profile_id in profile_ids:
        profile = _get_profile_or_raise(profile_id)
        if profile.id not in normalized:
            normalized.append(profile.id)
    return normalized


def _select_financial_snapshot_statements(
    session: Session,
    *,
    company_id: int,
) -> list[FinancialStatement]:
    statements = session.scalars(
        order_financial_statement_query(
            select(FinancialStatement).where(FinancialStatement.company_id == company_id)
        )
    ).all()
    selected_periods: list[str] = []
    selected_statements: list[FinancialStatement] = []

    for statement in statements:
        if statement.period not in selected_periods:
            if len(selected_periods) >= int(
                parameter_value("data_sampling.analysis_financial_periods", 40)
            ):
                continue
            selected_periods.append(statement.period)
        if statement.period in selected_periods:
            selected_statements.append(statement)

    return selected_statements


def _create_running_run(
    session: Session,
    *,
    company_id: int,
    profile: AnalystProfile,
    model_name: str | None,
    data_snapshot: dict[str, object],
    snapshot_hash: str,
    parent_run_id: int | None,
    user_note: str | None,
    config_version: int | None,
    config_hash: str,
    config_snapshot: dict[str, object],
) -> AnalysisRun:
    existing_runs = session.scalars(
        select(AnalysisRun).where(
            AnalysisRun.company_id == company_id,
            AnalysisRun.run_type == RUN_TYPE_ANALYST_VIEW,
            AnalysisRun.analyst_profile == profile.id,
            AnalysisRun.is_latest.is_(True),
        )
    ).all()
    for existing in existing_runs:
        existing.is_latest = False
    run = AnalysisRun(
        company_id=company_id,
        run_type=RUN_TYPE_ANALYST_VIEW,
        analyst_profile=profile.id,
    )
    session.add(run)

    run.run_version = RUN_VERSION
    run.model_name = model_name
    run.prompt_version = PROMPT_VERSION
    run.data_snapshot_hash = snapshot_hash
    run.input_snapshot = data_snapshot
    run.result = {}
    run.config_version = config_version
    run.config_hash = config_hash
    run.config_snapshot = deepcopy(config_snapshot)
    run.confidence = None
    run.parent_run_id = parent_run_id
    run.is_latest = True
    run.user_note = user_note
    run.status = "running"
    run.created_at = utc_now()
    session.commit()
    session.refresh(run)
    return run


def _dedupe_latest_analyst_runs(runs: list[AnalysisRun]) -> list[AnalysisRun]:
    latest_runs: list[AnalysisRun] = []
    seen_profiles: set[str | None] = set()
    for run in runs:
        if run.analyst_profile in seen_profiles:
            continue
        seen_profiles.add(run.analyst_profile)
        latest_runs.append(run)
    return latest_runs


def _dedupe_latest_runs_by_type_and_profile(runs: list[AnalysisRun]) -> list[AnalysisRun]:
    latest_runs: list[AnalysisRun] = []
    seen_keys: set[tuple[str, str | None]] = set()
    for run in runs:
        key = (run.run_type, run.analyst_profile)
        if key in seen_keys:
            continue
        seen_keys.add(key)
        latest_runs.append(run)
    return latest_runs


def _complete_run(
    session: Session,
    run: AnalysisRun,
    output: AnalystAnalysisOutput,
) -> None:
    run.status = "success"
    result = output.model_dump(mode="json")
    profile = _get_profile_or_raise(str(run.analyst_profile or ""))
    result["valuation_parameter_matrix"] = derive_valuation_parameter_matrix(
        source_run_id=run.id,
        profile=profile,
        result=result,
    )
    run.result = result
    run.confidence = output.confidence
    run.is_latest = True
    session.commit()
    session.refresh(run)


def _fail_run(session: Session, run: AnalysisRun, exc: Exception) -> None:
    run.status = "failed"
    run.result = {
        "error": sanitize_error_text(str(exc)),
        "error_type": exc.__class__.__name__,
    }
    run.confidence = None
    run.is_latest = True
    session.commit()
    session.refresh(run)


def _validate_output_profile(
    output: AnalystAnalysisOutput,
    profile: AnalystProfile,
    *,
    data_snapshot: dict[str, object],
) -> None:
    if output.analyst_profile != profile.id:
        raise ModelOutputValidationError(
            f"模型输出 analyst_profile={output.analyst_profile}，但请求 Profile={profile.id}"
        )
    expected_rule_ids = {rule.id for rule in profile.rules}
    output_rule_ids = {check.rule_id for check in output.rule_checks}
    missing = expected_rule_ids - output_rule_ids
    if missing:
        raise ModelOutputValidationError(f"模型输出缺少规则检查：{', '.join(sorted(missing))}")

    _validate_output_references(output, data_snapshot)


def _validate_output_references(
    output: AnalystAnalysisOutput,
    data_snapshot: dict[str, object],
) -> None:
    evidence_ids = _snapshot_ids(data_snapshot.get("evidence"))
    announcement_ids = _snapshot_ids(data_snapshot.get("announcements"))
    financial_periods = _snapshot_periods(data_snapshot.get("financial_statements"))

    invalid_supporting_evidence = sorted(set(output.supporting_evidence_ids) - evidence_ids)
    if invalid_supporting_evidence:
        raise ModelOutputValidationError(
            "模型输出引用了不存在的 Evidence："
            + ", ".join(str(item) for item in invalid_supporting_evidence)
        )

    invalid_rule_evidence: set[int] = set()
    invalid_rule_announcements: set[int] = set()
    invalid_rule_periods: set[str] = set()
    for check in output.rule_checks:
        invalid_rule_evidence.update(set(check.evidence_ids) - evidence_ids)
        invalid_rule_announcements.update(set(check.announcement_ids) - announcement_ids)
        invalid_rule_periods.update(set(check.financial_periods) - financial_periods)

    if invalid_rule_evidence:
        raise ModelOutputValidationError(
            "模型规则检查引用了不存在的 Evidence："
            + ", ".join(str(item) for item in sorted(invalid_rule_evidence))
        )
    if invalid_rule_announcements:
        raise ModelOutputValidationError(
            "模型规则检查引用了不存在的公告："
            + ", ".join(str(item) for item in sorted(invalid_rule_announcements))
        )
    if invalid_rule_periods:
        raise ModelOutputValidationError(
            "模型规则检查引用了不存在的财务期间：" + ", ".join(sorted(invalid_rule_periods))
        )


def _apply_fact_ledger_overrides(
    output: AnalystAnalysisOutput,
    data_snapshot: dict[str, object],
) -> AnalystAnalysisOutput:
    fact_ledger = data_snapshot.get("fact_ledger")
    if not isinstance(fact_ledger, dict):
        return output

    profile_relevance = fact_ledger.get("profile_relevance")
    data_confidence = fact_ledger.get("data_confidence")
    analysis_basis = fact_ledger.get("analysis_basis")
    accounting_events = fact_ledger.get("accounting_events")

    patch: dict[str, object] = {}
    if isinstance(profile_relevance, dict):
        score = profile_relevance.get("score")
        if isinstance(score, (int, float)):
            patch["profile_fit_score"] = float(score)
    if isinstance(data_confidence, dict):
        score = data_confidence.get("score")
        if isinstance(score, (int, float)):
            patch["confidence"] = float(score)
    if isinstance(profile_relevance, dict) or isinstance(data_confidence, dict):
        patch["score_explanations"] = {
            "profile_relevance": profile_relevance if isinstance(profile_relevance, dict) else {},
            "data_confidence": data_confidence if isinstance(data_confidence, dict) else {},
        }
    if isinstance(analysis_basis, dict):
        patch["analysis_basis"] = analysis_basis
    if isinstance(accounting_events, list):
        patch["accounting_events"] = accounting_events

    if not patch:
        return output
    return output.model_copy(update=patch)


def _apply_financial_unit_corrections(
    output: AnalystAnalysisOutput,
    data_snapshot: dict[str, object],
) -> AnalystAnalysisOutput:
    financial_pack = data_snapshot.get("financial_evidence_pack")
    if not isinstance(financial_pack, dict):
        return output
    model_display = financial_pack.get("model_display")
    if not isinstance(model_display, dict):
        return output
    percentages = model_display.get("latest_percentages")
    if not isinstance(percentages, dict):
        return output
    cash_to_revenue = percentages.get("operating_cash_flow_to_revenue")
    if not isinstance(cash_to_revenue, dict):
        return output
    raw_decimal = cash_to_revenue.get("raw_decimal")
    display = cash_to_revenue.get("display")
    if not _is_number(raw_decimal) or not isinstance(display, str):
        return output

    payload = output.model_dump(mode="json")
    corrected = _correct_financial_unit_texts(
        payload,
        raw_decimal=float(raw_decimal),
        display=display,
    )
    return AnalystAnalysisOutput.model_validate(corrected)


def _correct_financial_unit_texts(
    value: object,
    *,
    raw_decimal: float,
    display: str,
) -> object:
    if isinstance(value, dict):
        return {
            key: _correct_financial_unit_texts(
                item,
                raw_decimal=raw_decimal,
                display=display,
            )
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [
            _correct_financial_unit_texts(
                item,
                raw_decimal=raw_decimal,
                display=display,
            )
            for item in value
        ]
    if not isinstance(value, str) or not any(
        label in value for label in OPERATING_CASH_FLOW_TO_REVENUE_LABELS
    ):
        return value

    corrected = value
    candidates = {str(raw_decimal)}
    for precision in range(1, 7):
        candidates.add(f"{raw_decimal:.{precision}f}".rstrip("0").rstrip("."))
    for candidate in sorted(candidates, key=len, reverse=True):
        for suffix in ("%", "％", " %", " ％"):
            corrected = corrected.replace(f"{candidate}{suffix}", display)
    return corrected


def _select_announcement_snapshots(items: list[Announcement]) -> list[dict[str, object]]:
    selected_items = sorted(
        [item for item in items if not _model_contains_price_sensitive_text(item)],
        key=_announcement_selection_key,
        reverse=True,
    )[: int(parameter_value("data_sampling.analysis_announcement_items", 20))]
    return [_announcement_snapshot(item) for item in selected_items]


def _announcement_selection_key(item: Announcement) -> tuple[int, float, str]:
    text = _join_text_parts(
        item.title,
        item.category,
        item.summary,
    )
    score = 0.0
    category = str(item.category or "").lower()
    if any(term.lower() in category for term in ANNOUNCEMENT_PRIORITY_CATEGORIES):
        score += float(parameter_value("analyst_engine.announcement_ranking.category_bonus", 0.26))
    if _contains_any(text, ACCOUNTING_SELECTION_TERMS):
        score += float(
            parameter_value("analyst_engine.announcement_ranking.accounting_bonus", 0.24)
        )
    matched_terms = sum(1 for term in ANNOUNCEMENT_PRIORITY_TERMS if term in text)
    score += min(
        float(parameter_value("analyst_engine.announcement_ranking.term_bonus_cap", 0.22)),
        matched_terms
        * float(parameter_value("analyst_engine.announcement_ranking.term_bonus_each", 0.04)),
    )
    if item.summary:
        score += float(parameter_value("analyst_engine.announcement_ranking.summary_bonus", 0.06))
    return (_deep_summary_rank(item), score, item.published_at.isoformat())


def _deep_summary_rank(item: Announcement) -> int:
    model_name = (item.summary_model_name or "").strip()
    return int(bool(model_name and model_name != "metadata_keyword"))


def _select_external_evidence_snapshots(
    snapshots: list[dict[str, object]],
) -> list[dict[str, object]]:
    return sorted(
        snapshots,
        key=_external_evidence_selection_key,
        reverse=True,
    )[: int(parameter_value("data_sampling.analysis_evidence_items", 10))]


def _external_evidence_selection_key(snapshot: dict[str, object]) -> tuple[float, str]:
    score = 0.0
    credibility_score = snapshot.get("credibility_score")
    if isinstance(credibility_score, (int, float)):
        score += float(credibility_score) * float(
            parameter_value("analyst_engine.evidence_ranking.credibility_weight", 0.5)
        )
    importance_score = snapshot.get("importance_score")
    if isinstance(importance_score, (int, float)):
        score += float(importance_score) * float(
            parameter_value("analyst_engine.evidence_ranking.importance_weight", 0.5)
        )
    source_priority = parameter_value("analyst_engine.source_priority", {})
    if isinstance(source_priority, dict):
        score += float(source_priority.get(str(snapshot.get("source_type") or ""), 0.0))
    return (score, str(snapshot.get("published_at") or ""))


def _build_fact_ledger(
    *,
    company: Company,
    profile: AnalystProfile,
    financials: list[dict[str, object]],
    financial_evidence_pack: dict[str, object],
    announcements: list[dict[str, object]],
    external_evidence: list[dict[str, object]],
) -> dict[str, object]:
    accounting_events = _detect_accounting_events(
        announcements=announcements,
        external_evidence=external_evidence,
        financials=financials,
    )
    financial_quality = _build_financial_quality_summary(
        financials,
        accounting_events,
        financial_evidence_pack=financial_evidence_pack,
    )
    external_evidence_quality = _build_external_evidence_quality_summary(external_evidence)
    source_coverage_matrix = _build_source_coverage_matrix(
        financial_evidence_pack=financial_evidence_pack,
        announcements=announcements,
        external_evidence=external_evidence,
    )
    pre_model_observations = _build_pre_model_observations(
        financial_evidence_pack=financial_evidence_pack,
        financial_quality=financial_quality,
        external_evidence_quality=external_evidence_quality,
        accounting_events=accounting_events,
        source_coverage_matrix=source_coverage_matrix,
    )
    analysis_basis = _build_analysis_basis(
        financials=financials,
        announcements=announcements,
        external_evidence=external_evidence,
        accounting_events=accounting_events,
    )
    profile_relevance = _compute_profile_relevance(
        company=company,
        profile=profile,
        financials=financials,
        announcements=announcements,
        external_evidence=external_evidence,
        source_coverage_matrix=source_coverage_matrix,
    )
    data_confidence = _compute_data_confidence(
        financials=financials,
        announcements=announcements,
        external_evidence=external_evidence,
        accounting_events=accounting_events,
        financial_evidence_pack=financial_evidence_pack,
        source_coverage_matrix=source_coverage_matrix,
    )
    return {
        "basis_label": "本次分析依据",
        "terminology": {
            "external_evidence": (
                "由 007 外部信息模块入库的政策、新闻、公开资料、监管信息或网页线索；"
                "不是财务报表和公告本身。"
            ),
            "profile_relevance_score": "分析师框架与公司类型的适配度，主要由规则计算。",
            "view_confidence": "本次快照数据质量和完整度，不代表观点正确概率。",
        },
        "analysis_basis": analysis_basis,
        "profile_relevance": profile_relevance,
        "data_confidence": data_confidence,
        "financial_quality": financial_quality,
        "external_evidence_quality": external_evidence_quality,
        "source_coverage_matrix": source_coverage_matrix,
        "pre_model_observations": pre_model_observations,
        "accounting_events": accounting_events,
    }


def _build_source_coverage_matrix(
    *,
    financial_evidence_pack: dict[str, object],
    announcements: list[dict[str, object]],
    external_evidence: list[dict[str, object]],
) -> dict[str, object]:
    matrix: dict[str, dict[str, dict[str, object]]] = {
        "financial": {},
        "announcement": {},
        "external_evidence": {},
    }

    _add_financial_coverage(matrix["financial"], financial_evidence_pack)
    for item in announcements:
        _add_text_coverage(
            matrix["announcement"],
            text=_join_text_parts(
                item.get("title"),
                item.get("category"),
                item.get("summary"),
                item.get("key_facts"),
                item.get("tags"),
            ),
            ref=item.get("id"),
        )
    for item in external_evidence:
        _add_text_coverage(
            matrix["external_evidence"],
            text=_join_text_parts(
                item.get("title"),
                item.get("summary"),
                item.get("key_facts"),
                item.get("tags"),
                item.get("analysis_note"),
            ),
            ref=item.get("id"),
        )

    covered_topics = sorted(
        {
            topic
            for source_topics in matrix.values()
            for topic, payload in source_topics.items()
            if payload.get("covered") is True
        }
    )
    important_topics = {
        "profitability",
        "profit_structure",
        "expense_control",
        "accounting_quality",
        "cash_flow",
        "balance_sheet",
        "growth",
        "governance",
        "regulatory",
        "industry_supply_demand",
        "consumer_channel",
        "capital_allocation",
        "shareholder_return",
        "valuation_inputs",
    }
    return {
        **matrix,
        "summary": {
            "covered_topics": covered_topics,
            "missing_core_topics": sorted(important_topics - set(covered_topics)),
            "source_count": {
                "financial": len(financial_evidence_pack.get("periods", []))
                if isinstance(financial_evidence_pack.get("periods"), list)
                else 0,
                "announcement": len(announcements),
                "external_evidence": len(external_evidence),
            },
        },
    }


def _add_financial_coverage(
    topics: dict[str, dict[str, object]],
    financial_evidence_pack: dict[str, object],
) -> None:
    latest_period = financial_evidence_pack.get("latest_period")
    metrics = financial_evidence_pack.get("financial_metrics")
    trends = financial_evidence_pack.get("financial_trends")
    facts = financial_evidence_pack.get("financial_facts")
    data_gaps = financial_evidence_pack.get("financial_data_gaps")
    cash_flow_quality = financial_evidence_pack.get("cash_flow_quality")
    balance_sheet_adjustment = financial_evidence_pack.get("balance_sheet_adjustment")
    capital_allocation = financial_evidence_pack.get("capital_allocation")
    valuation_readiness = financial_evidence_pack.get("valuation_readiness")
    quality_matrix = financial_evidence_pack.get("quality_matrix")
    income_statement_quality = financial_evidence_pack.get("income_statement_quality")
    profit_composition = financial_evidence_pack.get("profit_composition")

    if isinstance(facts, dict) and _has_nested_number(facts.get("latest")):
        _mark_topic(topics, "profitability", latest_period, "财务事实包含收入或利润字段。")
    if isinstance(metrics, dict):
        if _has_nested_number(metrics.get("profitability")):
            _mark_topic(topics, "profitability", latest_period, "财务指标包含盈利能力字段。")
        if _has_nested_number(metrics.get("profit_structure")):
            _mark_topic(topics, "profit_structure", latest_period, "财务证据包包含利润构成指标。")
            _mark_topic(topics, "accounting_quality", latest_period, "利润构成可辅助识别利润质量。")
        if _has_nested_number(metrics.get("expense_control")):
            _mark_topic(
                topics,
                "expense_control",
                latest_period,
                "财务证据包包含费用率和费用纪律指标。",
            )
        if _has_nested_number(metrics.get("cash_quality")):
            _mark_topic(topics, "cash_flow", latest_period, "财务指标包含现金质量字段。")
        if _has_nested_number(metrics.get("growth_quality")):
            _mark_topic(topics, "growth", latest_period, "财务指标包含同比成长字段。")
        if _has_nested_number(metrics.get("balance_sheet_safety")):
            _mark_topic(topics, "balance_sheet", latest_period, "财务指标包含资产负债字段。")
        if _has_nested_number(metrics.get("efficiency")):
            _mark_topic(topics, "operating_efficiency", latest_period, "财务指标包含周转效率字段。")
        if _has_nested_number(metrics.get("shareholder_return")):
            _mark_topic(topics, "shareholder_return", latest_period, "财务指标包含股东回报字段。")
        if _has_nested_number(metrics.get("capital_allocation")):
            _mark_topic(topics, "capital_allocation", latest_period, "财务指标包含资本配置字段。")
    if isinstance(cash_flow_quality, dict) and _has_nested_number(cash_flow_quality):
        _mark_topic(topics, "cash_flow", latest_period, "财务证据包包含现金流质量底稿。")
    if isinstance(balance_sheet_adjustment, dict) and _has_nested_number(balance_sheet_adjustment):
        _mark_topic(topics, "balance_sheet", latest_period, "财务证据包包含资产负债调整底稿。")
    if isinstance(capital_allocation, dict) and _has_nested_number(capital_allocation):
        _mark_topic(topics, "capital_allocation", latest_period, "财务证据包包含资本配置底稿。")
    if isinstance(valuation_readiness, dict) and valuation_readiness.get("ready_methods"):
        _mark_topic(topics, "valuation_inputs", latest_period, "财务证据包包含估值准备度判断。")
    if isinstance(income_statement_quality, dict) and _has_nested_number(income_statement_quality):
        _mark_topic(topics, "accounting_quality", latest_period, "财务证据包包含利润表质量底稿。")
        _mark_topic(topics, "profit_structure", latest_period, "利润表质量底稿包含利润构成。")
    if isinstance(profit_composition, dict) and _has_nested_number(profit_composition):
        _mark_topic(topics, "profit_structure", latest_period, "财务证据包包含利润构成摘要。")
    if isinstance(quality_matrix, dict):
        for topic in ("profit_structure", "expense_control", "accounting_quality"):
            topic_payload = quality_matrix.get(topic)
            if _has_nested_number(topic_payload) or (
                isinstance(topic_payload, dict) and bool(topic_payload)
            ):
                _mark_topic(topics, topic, latest_period, f"quality_matrix 包含 {topic} 覆盖。")
    if isinstance(trends, dict) and any(value is not None for value in trends.values()):
        _mark_topic(topics, "growth", latest_period, "财务证据包包含趋势指标。")
    if isinstance(data_gaps, list) and data_gaps:
        _mark_topic(topics, "data_gaps", latest_period, f"财务证据包存在 {len(data_gaps)} 项缺口。")


def _add_text_coverage(
    topics: dict[str, dict[str, object]],
    *,
    text: str,
    ref: object,
) -> None:
    topic_terms = {
        "governance": ("治理", "董事", "高管", "管理层", "股东大会", "控制权", "关联交易"),
        "regulatory": ("监管", "处罚", "问询函", "整改", "合规", "行政处罚", "反垄断"),
        "industry_supply_demand": ("行业", "供需", "产量", "库存", "消费", "政策", "税收"),
        "consumer_channel": ("消费者", "渠道", "经销商", "品牌", "终端", "提价", "合同价"),
        "accounting": ("会计政策", "会计估计", "收入确认", "追溯调整", "差错更正"),
        "capital_return": ("分红", "派息", "回购", "股东回报", "利润分配"),
        "major_event": ("重大事项", "诉讼", "仲裁", "担保", "减值", "重大合同"),
        "price_sensitive": ("当前价格", "历史价格", "目标价", "市值", "持仓成本", "估值倍数"),
    }
    for topic, terms in topic_terms.items():
        if _contains_any(text, terms):
            _mark_topic(topics, topic, ref, "文本命中相关主题关键词。")


def _mark_topic(
    topics: dict[str, dict[str, object]],
    topic: str,
    ref: object,
    note: str,
) -> None:
    payload = topics.setdefault(
        topic,
        {
            "covered": True,
            "evidence_count": 0,
            "refs": [],
            "notes": [],
        },
    )
    payload["covered"] = True
    payload["evidence_count"] = int(payload.get("evidence_count") or 0) + 1
    refs = payload.get("refs")
    if isinstance(refs, list) and ref is not None and ref not in refs:
        refs.append(ref)
    notes = payload.get("notes")
    if isinstance(notes, list) and note not in notes:
        notes.append(note)


def _build_pre_model_observations(
    *,
    financial_evidence_pack: dict[str, object],
    financial_quality: dict[str, object],
    external_evidence_quality: dict[str, object],
    accounting_events: list[dict[str, object]],
    source_coverage_matrix: dict[str, object],
) -> list[str]:
    observations: list[str] = []
    flags = financial_evidence_pack.get("financial_flags")
    if isinstance(flags, list):
        observations.extend(_income_statement_flag_observations(flags))

    income_statement_observation = _income_statement_structured_observation(financial_evidence_pack)
    if income_statement_observation:
        observations.append(income_statement_observation)
    if isinstance(flags, list):
        for flag in flags[:3]:
            if isinstance(flag, dict) and flag.get("message"):
                observations.append(f"财务旗标：{flag.get('message')}")

    data_gaps = financial_quality.get("data_gaps")
    if isinstance(data_gaps, list) and data_gaps:
        first_gap = data_gaps[0]
        if isinstance(first_gap, dict) and first_gap.get("reason"):
            observations.append(
                f"财务证据包存在 {len(data_gaps)} 项结构化数据缺口；"
                f"首要缺口：{first_gap.get('reason')}"
            )
        else:
            observations.append(f"财务证据包存在 {len(data_gaps)} 项数据缺口，估值假设需要补充。")

    valuation_readiness = financial_quality.get("valuation_readiness")
    if isinstance(valuation_readiness, dict):
        ready_methods = valuation_readiness.get("ready_methods")
        if isinstance(ready_methods, list) and ready_methods:
            observations.append(
                "估值准备度：已具备 "
                + "、".join(str(item) for item in ready_methods[:3])
                + " 的部分基础输入。"
            )

    cash_flow_coverage = financial_quality.get("cash_flow_coverage")
    if isinstance(cash_flow_coverage, dict) and cash_flow_coverage.get("note"):
        observations.append(str(cash_flow_coverage["note"]))

    status_counts = external_evidence_quality.get("status_counts")
    if isinstance(status_counts, dict) and status_counts.get("search_lead"):
        observations.append(
            f"{status_counts.get('search_lead')} 条外部信息仍是 search_lead，不能当作已验证事实。"
        )

    if accounting_events:
        observations.append("检测到会计口径事件，评价收入、利润和同比变化前必须说明可比口径。")

    summary = source_coverage_matrix.get("summary")
    if isinstance(summary, dict):
        missing_topics = summary.get("missing_core_topics")
        if isinstance(missing_topics, list) and missing_topics:
            observations.append(
                "核心主题仍有缺口：" + "、".join(str(topic) for topic in missing_topics[:4])
            )

    return _unique_strings(observations)[:8]


def _income_statement_flag_observations(flags: list[object]) -> list[str]:
    observations: list[str] = []
    for flag in flags:
        if not isinstance(flag, dict):
            continue
        code = flag.get("code")
        if isinstance(code, str) and code in INCOME_STATEMENT_FLAG_OBSERVATIONS:
            observations.append("利润表确定性提示：" + INCOME_STATEMENT_FLAG_OBSERVATIONS[code])
    return observations


def _income_statement_structured_observation(
    financial_evidence_pack: dict[str, object],
) -> str | None:
    metrics = financial_evidence_pack.get("financial_metrics")
    if not isinstance(metrics, dict):
        metrics = {}
    quality_matrix = financial_evidence_pack.get("quality_matrix")
    if not isinstance(quality_matrix, dict):
        quality_matrix = {}
    analyst_summary = financial_evidence_pack.get("analyst_summary")
    if not isinstance(analyst_summary, dict):
        analyst_summary = {}

    available_parts: list[str] = []
    if _has_nested_number(metrics.get("profit_structure")):
        available_parts.append("profit_structure")
    if _has_nested_number(metrics.get("expense_control")):
        available_parts.append("expense_control")
    if _has_nested_number(quality_matrix.get("accounting_quality")) or isinstance(
        analyst_summary.get("income_statement_quality"), (dict, str)
    ):
        available_parts.append("accounting_quality")
    if isinstance(analyst_summary.get("profit_composition"), (dict, str)):
        available_parts.append("profit_composition")

    if not available_parts:
        return None
    return (
        "利润表结构化字段可用："
        + "、".join(_unique_strings(available_parts))
        + "；财务质量判断应优先使用 financial_evidence_pack，不要从原始 JSON 现场猜公式。"
    )


def _detect_accounting_events(
    *,
    announcements: list[dict[str, object]],
    external_evidence: list[dict[str, object]],
    financials: list[dict[str, object]],
) -> list[dict[str, object]]:
    events: list[dict[str, object]] = []
    seen: set[tuple[str, str, int | str | None]] = set()

    for item in announcements:
        text = _join_text_parts(
            item.get("title"),
            item.get("category"),
            item.get("summary"),
            item.get("content_excerpt"),
        )
        for event in _match_accounting_events(
            text,
            source_type="announcement",
            source_id=item.get("id"),
            title=item.get("title"),
        ):
            key = (event["event_type"], event["source_type"], event["source_id"])
            if key not in seen:
                seen.add(key)
                events.append(event)

    for item in external_evidence:
        text = _join_text_parts(
            item.get("title"),
            item.get("summary"),
            item.get("analysis_note"),
            item.get("tags"),
            item.get("key_facts"),
        )
        for event in _match_accounting_events(
            text,
            source_type="external_evidence",
            source_id=item.get("id"),
            title=item.get("title"),
        ):
            key = (event["event_type"], event["source_type"], event["source_id"])
            if key not in seen:
                seen.add(key)
                events.append(event)

    for item in financials:
        fields = item.get("fields") if isinstance(item.get("fields"), dict) else {}
        text = _join_text_parts(
            item.get("period"),
            item.get("statement_type"),
            fields,
        )
        for event in _match_accounting_events(
            text,
            source_type="financial_statement",
            source_id=item.get("period"),
            title=f"{item.get('period')} {item.get('statement_type')}",
        ):
            key = (event["event_type"], event["source_type"], event["source_id"])
            if key not in seen:
                seen.add(key)
                events.append(event)

    return events[:8]


def _match_accounting_events(
    text: str,
    *,
    source_type: str,
    source_id: object,
    title: object,
) -> list[dict[str, object]]:
    matched_events: list[dict[str, object]] = []
    if not text:
        return matched_events

    for event_type, label, implication, keywords in ACCOUNTING_KEYWORDS:
        matched_keywords = [keyword for keyword in keywords if keyword in text]
        if not matched_keywords:
            continue
        matched_events.append(
            {
                "event_type": event_type,
                "label": label,
                "source_type": source_type,
                "source_id": source_id,
                "source_title": str(title) if title is not None else None,
                "matched_keywords": matched_keywords[:4],
                "summary": f"{label}：{implication}",
                "comparability_impact": "财务同比和利润质量判断必须先调整或说明口径差异。",
                "confidence": 0.76 if source_type == "announcement" else 0.62,
            }
        )
    return matched_events


def _build_financial_quality_summary(
    financials: list[dict[str, object]],
    accounting_events: list[dict[str, object]],
    *,
    financial_evidence_pack: dict[str, object] | None = None,
) -> dict[str, object]:
    periods = _financial_periods(financials)
    pack = financial_evidence_pack or {}
    financial_flags = pack.get("financial_flags")
    financial_data_gaps = pack.get("financial_data_gaps")
    cash_flow_coverage = pack.get("cash_flow_coverage")
    valuation_readiness = pack.get("valuation_readiness")
    balance_sheet_adjustment = pack.get("balance_sheet_adjustment")
    capital_allocation = pack.get("capital_allocation")
    data_quality = pack.get("data_quality")
    statement_types = sorted(
        {
            str(item.get("statement_type"))
            for item in financials
            if isinstance(item.get("statement_type"), str)
        }
    )
    comparability_notes: list[str] = []
    if accounting_events:
        comparability_notes.append(
            "检测到会计口径、收入确认、追溯调整或非经常性因素信号；同比变化需区分经营变化和口径变化。"
        )
    if len(periods) < 3:
        comparability_notes.append("财务期数少于 3 个，长期趋势判断置信度受限。")
    if not financials:
        comparability_notes.append("没有可用财务快照。")
    if isinstance(financial_data_gaps, list) and financial_data_gaps:
        comparability_notes.append(
            f"财务证据包存在 {len(financial_data_gaps)} 项数据缺口，估值和质量判断需降置信度。"
        )

    return {
        "periods": periods,
        "latest_period": pack.get("latest_period") if isinstance(pack, dict) else None,
        "statement_types": statement_types,
        "comparability_notes": comparability_notes,
        "has_accounting_event": bool(accounting_events),
        "flags_count": len(financial_flags) if isinstance(financial_flags, list) else 0,
        "structured_gaps_count": (
            len(financial_data_gaps) if isinstance(financial_data_gaps, list) else 0
        ),
        "data_gaps": financial_data_gaps if isinstance(financial_data_gaps, list) else [],
        "cash_flow_coverage": cash_flow_coverage if isinstance(cash_flow_coverage, dict) else {},
        "valuation_readiness": valuation_readiness if isinstance(valuation_readiness, dict) else {},
        "balance_sheet_safety": balance_sheet_adjustment
        if isinstance(balance_sheet_adjustment, dict)
        else {},
        "shareholder_return_coverage": capital_allocation
        if isinstance(capital_allocation, dict)
        else {},
        "data_quality": data_quality if isinstance(data_quality, dict) else {},
        "income_statement_coverage": _build_income_statement_coverage(
            statement_types=statement_types,
            financial_evidence_pack=pack,
        ),
    }


def _build_external_evidence_quality_summary(
    external_evidence: list[dict[str, object]],
) -> dict[str, object]:
    status_counts: dict[str, int] = {}
    source_type_counts: dict[str, int] = {}
    review_required_count = 0
    credibility_scores: list[float] = []

    for item in external_evidence:
        status = str(item.get("analysis_status") or "unknown")
        source_type = str(item.get("source_type") or "unknown")
        status_counts[status] = status_counts.get(status, 0) + 1
        source_type_counts[source_type] = source_type_counts.get(source_type, 0) + 1
        if item.get("requires_review") is True:
            review_required_count += 1
        credibility = item.get("credibility_score")
        if isinstance(credibility, (int, float)):
            credibility_scores.append(float(credibility))

    average_credibility = (
        round(sum(credibility_scores) / len(credibility_scores), 2) if credibility_scores else None
    )
    return {
        "total": len(external_evidence),
        "status_counts": status_counts,
        "source_type_counts": source_type_counts,
        "requires_review_count": review_required_count,
        "average_credibility": average_credibility,
    }


def _build_income_statement_coverage(
    *,
    statement_types: list[str],
    financial_evidence_pack: dict[str, object],
) -> dict[str, object]:
    metrics = financial_evidence_pack.get("financial_metrics")
    if not isinstance(metrics, dict):
        metrics = {}
    income_statement_quality = financial_evidence_pack.get("income_statement_quality")
    if not isinstance(income_statement_quality, dict):
        income_statement_quality = {}
    profit_structure = metrics.get("profit_structure")
    if not isinstance(profit_structure, dict):
        profit_structure = {}
    expense_control = metrics.get("expense_control")
    if not isinstance(expense_control, dict):
        expense_control = {}
    data_gaps = financial_evidence_pack.get("financial_data_gaps")
    gap_fields = _financial_gap_fields(data_gaps)

    has_income_statement = "income_statement" in statement_types or _has_nested_number(
        income_statement_quality
    )
    has_expense_breakdown = _has_nested_number(expense_control) or _has_nested_number(
        income_statement_quality.get("expense_control")
    )
    has_operating_profit = _is_number(
        income_statement_quality.get("operating_profit")
    ) or _is_number(profit_structure.get("operating_margin"))
    has_impairment_items = any(
        _is_number(income_statement_quality.get(field))
        for field in ("credit_impairment_loss", "asset_impairment_loss")
    ) or _is_number(profit_structure.get("impairment_loss_to_net_profit"))
    has_non_operating_items = any(
        _is_number(income_statement_quality.get(field))
        for field in ("non_operating_income", "non_operating_expense")
    ) or _is_number(profit_structure.get("non_operating_profit_to_net_profit"))
    has_tax_expense = _is_number(income_statement_quality.get("income_tax_expense")) or _is_number(
        profit_structure.get("effective_tax_rate")
    )

    missing_fields = sorted(INCOME_STATEMENT_GAP_FIELDS & gap_fields)
    if has_income_statement:
        note = "已接入利润表或利润表质量结构化字段，利润质量判断优先使用 evidence_pack。"
    elif missing_fields:
        note = "利润表明细仍有缺口，利润构成和费用纪律判断需要降置信度。"
    else:
        note = "未识别到利润表明细覆盖，必要时只能使用主财务指标中的结果项。"

    return {
        "has_income_statement": has_income_statement,
        "has_expense_breakdown": has_expense_breakdown,
        "has_operating_profit": has_operating_profit,
        "has_impairment_items": has_impairment_items,
        "has_non_operating_items": has_non_operating_items,
        "has_tax_expense": has_tax_expense,
        "missing_fields": missing_fields,
        "note": note,
    }


def _build_analysis_basis(
    *,
    financials: list[dict[str, object]],
    announcements: list[dict[str, object]],
    external_evidence: list[dict[str, object]],
    accounting_events: list[dict[str, object]],
) -> dict[str, object]:
    return {
        "financial_periods": _financial_periods(financials),
        "announcement_ids": [
            item["id"] for item in announcements if isinstance(item.get("id"), int)
        ],
        "external_evidence_ids": [
            item["id"] for item in external_evidence if isinstance(item.get("id"), int)
        ],
        "accounting_event_count": len(accounting_events),
        "accounting_event_labels": _unique_strings(
            event.get("label") for event in accounting_events
        ),
        "notes": _build_analysis_basis_notes(financials, announcements, external_evidence),
    }


def _build_analysis_basis_notes(
    financials: list[dict[str, object]],
    announcements: list[dict[str, object]],
    external_evidence: list[dict[str, object]],
) -> list[str]:
    notes: list[str] = []
    if not financials:
        notes.append("缺少财务数据。")
    if not announcements:
        notes.append("缺少公告数据。")
    if not external_evidence:
        notes.append("缺少 007 外部信息。")
    search_leads = sum(
        1 for item in external_evidence if item.get("analysis_status") == "search_lead"
    )
    if search_leads:
        notes.append(f"{search_leads} 条外部信息仍是搜索线索，尚未完成模型结构化。")
    return notes


def _compute_profile_relevance(
    *,
    company: Company,
    profile: AnalystProfile,
    financials: list[dict[str, object]],
    announcements: list[dict[str, object]],
    external_evidence: list[dict[str, object]],
    source_coverage_matrix: dict[str, object],
) -> dict[str, object]:
    text = _build_company_feature_text(company, announcements, external_evidence)
    signals = {
        "consumer_brand": _contains_any(text, CONSUMER_BRAND_TERMS),
        "tech_growth": _contains_any(text, TECH_GROWTH_TERMS),
        "cyclical_macro": _contains_any(text, CYCLICAL_MACRO_TERMS),
        "asset_heavy": _contains_any(text, ASSET_HEAVY_TERMS),
        "has_cash_flow": _has_any_financial_field(
            financials,
            (
                "operating_cash_flow",
                "operating_cash_flow_per_share",
                "operating_cash_flow_to_revenue",
            ),
        ),
        "has_brand_term": _contains_any(text, ("品牌", "高端", "渠道", "复购", "消费心智")),
    }

    base_score_by_profile = parameter_value("analyst_engine.base_profile_scores", {})
    score = (
        float(
            base_score_by_profile.get(
                profile.id,
                parameter_value("analyst_engine.profile_default_score", 0.56),
            )
        )
        if isinstance(base_score_by_profile, dict)
        else 0.56
    )
    feature = parameter_value("analyst_engine.feature_adjustments", {})
    feature = feature if isinstance(feature, dict) else {}
    reasons: list[str] = []

    if signals["consumer_brand"]:
        if profile.id in {"lin_yuan", "buffett", "duan_yongping"}:
            score += float(feature.get("consumer_brand_primary", 0.2))
            reasons.append("公司具有消费/品牌属性，该视角对消费刚需、品牌壁垒和现金创造更适配。")
        elif profile.id in {"munger", "peter_lynch", "li_lu"}:
            score += float(feature.get("consumer_brand_secondary", 0.1))
            reasons.append("消费品牌生意较容易映射到业务质量、增长兑现和能力圈框架。")
    if signals["tech_growth"] and profile.id in {"fisher", "peter_lynch"}:
        score += float(feature.get("tech_growth", 0.16))
        reasons.append("公司文本包含科技、研发或创新信号，成长质量视角更适配。")
    if signals["cyclical_macro"] and profile.id in {"graham", "li_lu"}:
        score += float(feature.get("cyclical_macro_defensive", 0.08))
        reasons.append("周期行业需要强调资本结构、资产质量和永久损失风险。")
    if signals["asset_heavy"] and profile.id == "graham":
        score += float(feature.get("asset_heavy_graham", 0.12))
        reasons.append("资产较重或金融地产属性更适合做资产保护和保守假设检查。")
    if signals["has_cash_flow"] and profile.id in {"buffett", "lin_yuan", "duan_yongping"}:
        score += float(feature.get("cash_flow_quality", 0.06))
        reasons.append("快照含经营现金流字段，可支持现金创造和长期质量判断。")
    if not reasons:
        reasons.append("当前仅基于行业、标签、文本和可用财务字段给出基础适配度。")

    fit_config = parameter_value("analyst_engine.profile_fit", {})
    fit_config = fit_config if isinstance(fit_config, dict) else {}
    fit_min = float(fit_config.get("minimum", 0.2))
    fit_max = float(fit_config.get("maximum", 0.92))
    industry_framework_fit = round(
        max(fit_min, min(float(fit_config.get("industry_maximum", 0.95)), score)), 2
    )
    required_topics = _profile_required_topics(profile.id)
    covered_topics = _coverage_topics(source_coverage_matrix)
    covered_topics.update(_inferred_company_topics(signals, financials))
    covered_required_topics = sorted(set(required_topics) & covered_topics)
    rule_coverage = len(covered_required_topics) / len(required_topics) if required_topics else 0.5
    evidence_support = _profile_evidence_support(
        profile.id,
        financials=financials,
        external_evidence=external_evidence,
        source_coverage_matrix=source_coverage_matrix,
    )
    uncertainty_penalty = (
        float(fit_config.get("few_financial_penalty", 0.08))
        if len(financials) < int(fit_config.get("few_financial_periods", 3))
        else 0.0
    )
    if not external_evidence:
        uncertainty_penalty += float(fit_config.get("missing_external_penalty", 0.04))

    normalized_score = round(
        max(
            fit_min,
            min(
                fit_max,
                industry_framework_fit * float(fit_config.get("industry_weight", 0.55))
                + rule_coverage * float(fit_config.get("rule_coverage_weight", 0.30))
                + evidence_support * float(fit_config.get("evidence_support_weight", 0.15))
                - uncertainty_penalty,
            ),
        ),
        2,
    )
    reasons.append(
        f"当前证据覆盖该视角核心主题 {len(covered_required_topics)}/{len(required_topics)} 个。"
    )
    return {
        "score": normalized_score,
        "tier": _score_tier(normalized_score),
        "method": "rule_based_company_profile_fit_v2",
        "score_type": "framework_applicability_estimate",
        "components": {
            "industry_framework_fit": industry_framework_fit,
            "rule_topic_coverage": round(rule_coverage, 2),
            "evidence_support": round(evidence_support, 2),
            "uncertainty_penalty": round(uncertainty_penalty, 2),
        },
        "signals": signals,
        "required_topics": required_topics,
        "covered_required_topics": covered_required_topics,
        "reasons": reasons[:4],
        "limitations": [
            "该分数只表示当前公司和证据对该分析框架的适配度，不表示看多或看空。",
            "行业和文本信号仍是启发式判断，后续可由人工校准权重。",
        ],
    }


def _compute_data_confidence(
    *,
    financials: list[dict[str, object]],
    announcements: list[dict[str, object]],
    external_evidence: list[dict[str, object]],
    accounting_events: list[dict[str, object]],
    financial_evidence_pack: dict[str, object],
    source_coverage_matrix: dict[str, object],
) -> dict[str, object]:
    reasons: list[str] = []
    limitations: list[str] = []
    confidence_config = parameter_value("analyst_engine.data_confidence", {})
    confidence_config = confidence_config if isinstance(confidence_config, dict) else {}

    periods = _financial_periods(financials)
    financial_data_gaps = financial_evidence_pack.get("financial_data_gaps")
    financial_gap_count = len(financial_data_gaps) if isinstance(financial_data_gaps, list) else 0
    financial_score = 0.0
    if financials:
        financial_score += float(confidence_config.get("financial_present", 0.35))
        reasons.append("存在财务快照。")
    if len(periods) >= int(confidence_config.get("financial_periods_required", 3)):
        financial_score += float(confidence_config.get("financial_periods_bonus", 0.20))
        reasons.append("财务期数达到 3 期以上。")
    if financial_evidence_pack.get("latest_period"):
        financial_score += float(confidence_config.get("latest_period_bonus", 0.15))
    if _coverage_has_topic(source_coverage_matrix, "profitability"):
        financial_score += float(confidence_config.get("profitability_bonus", 0.12))
    if _coverage_has_topic(source_coverage_matrix, "cash_flow"):
        financial_score += float(confidence_config.get("cash_flow_bonus", 0.08))
    financial_score -= min(
        float(confidence_config.get("financial_gap_penalty_cap", 0.25)),
        financial_gap_count * float(confidence_config.get("financial_gap_penalty_each", 0.03)),
    )
    financial_score = max(0.0, min(1.0, financial_score))

    summarized_announcements = sum(1 for item in announcements if item.get("summary"))
    announcement_score = 0.0
    if announcements:
        announcement_cap = float(confidence_config.get("announcement_count_cap", 0.55))
        announcement_score += min(
            announcement_cap,
            len(announcements)
            / float(confidence_config.get("announcement_target_count", 20))
            * announcement_cap,
        )
        summary_cap = float(confidence_config.get("announcement_summary_cap", 0.30))
        announcement_score += min(
            summary_cap, summarized_announcements / len(announcements) * summary_cap
        )
        if _coverage_has_topic(source_coverage_matrix, "accounting"):
            announcement_score += float(confidence_config.get("accounting_bonus", 0.10))
        if _coverage_has_topic(source_coverage_matrix, "governance"):
            announcement_score += float(confidence_config.get("governance_bonus", 0.05))
        reasons.append("存在公告快照。")
    announcement_score = max(0.0, min(1.0, announcement_score))

    model_analyzed = sum(
        1 for item in external_evidence if item.get("analysis_status") == "model_analyzed"
    )
    search_leads = sum(
        1 for item in external_evidence if item.get("analysis_status") == "search_lead"
    )
    external_score = 0.0
    if external_evidence:
        analyzed_ratio = model_analyzed / len(external_evidence)
        external_score += float(confidence_config.get("external_present", 0.35))
        external_score += analyzed_ratio * float(
            confidence_config.get("external_analyzed_weight", 0.35)
        )
        external_score += min(
            float(confidence_config.get("external_source_bonus_cap", 0.20)),
            len(
                {
                    str(item.get("source_type"))
                    for item in external_evidence
                    if item.get("source_type")
                }
            )
            * float(confidence_config.get("external_source_bonus_each", 0.05)),
        )
        external_score -= min(
            float(confidence_config.get("search_lead_penalty_cap", 0.25)),
            search_leads * float(confidence_config.get("search_lead_penalty_each", 0.04)),
        )
        reasons.append("存在 007 外部信息。")
    else:
        limitations.append("缺少 007 外部信息，外部约束和行业信息覆盖不足。")
    external_score = max(0.0, min(1.0, external_score))

    source_presence = sum(
        1 for present in (bool(financials), bool(announcements), bool(external_evidence)) if present
    )
    source_balance = source_presence / 3
    accounting_penalty = 0.0
    if accounting_events:
        accounting_penalty = float(confidence_config.get("accounting_event_penalty", 0.06))
        limitations.append("检测到会计口径事件，财务同比结论需要降置信度并单独说明。")
    if search_leads:
        limitations.append("部分外部信息仍是待复核搜索线索，不能当作已验证事实。")
    if not announcements:
        limitations.append("缺少公告数据，治理、重大事项和会计口径判断受限。")
    if not financials:
        limitations.append("缺少财务数据，核心质量判断只能低置信度输出。")

    normalized_score = round(
        max(
            float(confidence_config.get("minimum", 0.20)),
            min(
                float(confidence_config.get("maximum", 0.92)),
                financial_score * float(confidence_config.get("financial_weight", 0.45))
                + announcement_score * float(confidence_config.get("announcement_weight", 0.25))
                + external_score * float(confidence_config.get("external_weight", 0.20))
                + source_balance * float(confidence_config.get("source_balance_weight", 0.10))
                - accounting_penalty,
            ),
        ),
        2,
    )
    return {
        "score": normalized_score,
        "tier": _score_tier(normalized_score),
        "method": "snapshot_quality_v2",
        "score_type": "source_coverage_quality_estimate",
        "components": {
            "financial_coverage": round(financial_score, 2),
            "announcement_coverage": round(announcement_score, 2),
            "external_evidence_quality": round(external_score, 2),
            "source_balance": round(source_balance, 2),
            "accounting_complexity_penalty": round(accounting_penalty, 2),
        },
        "reasons": reasons[:6],
        "limitations": limitations[:6],
    }


def _build_company_feature_text(
    company: Company,
    announcements: list[dict[str, object]],
    external_evidence: list[dict[str, object]],
) -> str:
    parts: list[object] = [
        company.name,
        company.ticker,
        company.exchange,
        company.industry,
        company.description,
        company.tags,
    ]
    for item in announcements[:MAX_RESULT_LIST_ITEMS]:
        parts.extend(
            [
                item.get("title"),
                item.get("summary"),
                item.get("tags"),
                item.get("key_facts"),
            ]
        )
    for item in external_evidence[:MAX_RESULT_LIST_ITEMS]:
        parts.extend(
            [
                item.get("title"),
                item.get("summary"),
                item.get("tags"),
                item.get("key_facts"),
            ]
        )
    return _join_text_parts(*parts)


def _profile_required_topics(profile_id: str) -> list[str]:
    topics_by_profile = {
        "buffett": ["profitability", "cash_flow", "capital_allocation", "governance"],
        "peter_lynch": ["growth", "consumer_channel", "balance_sheet", "industry_supply_demand"],
        "munger": ["governance", "regulatory", "balance_sheet", "major_event"],
        "duan_yongping": ["consumer_channel", "profitability", "cash_flow", "capital_return"],
        "graham": ["balance_sheet", "profitability", "accounting_quality", "data_gaps"],
        "fisher": ["growth", "industry_supply_demand", "governance", "operating_efficiency"],
        "lin_yuan": ["consumer_channel", "profitability", "cash_flow", "growth"],
        "li_lu": ["profitability", "balance_sheet", "governance", "data_gaps"],
    }
    return topics_by_profile.get(profile_id, ["profitability", "growth", "data_gaps"])


def _coverage_topics(source_coverage_matrix: dict[str, object]) -> set[str]:
    topics: set[str] = set()
    for source_name in ("financial", "announcement", "external_evidence"):
        source_topics = source_coverage_matrix.get(source_name)
        if not isinstance(source_topics, dict):
            continue
        for topic, payload in source_topics.items():
            if isinstance(payload, dict) and payload.get("covered") is True:
                topics.add(str(topic))
    return topics


def _coverage_has_topic(source_coverage_matrix: dict[str, object], topic: str) -> bool:
    return topic in _coverage_topics(source_coverage_matrix)


def _inferred_company_topics(
    signals: dict[str, bool],
    financials: list[dict[str, object]],
) -> set[str]:
    topics: set[str] = set()
    if signals.get("consumer_brand") or signals.get("has_brand_term"):
        topics.add("consumer_channel")
    if signals.get("tech_growth"):
        topics.add("growth")
    if signals.get("cyclical_macro"):
        topics.add("industry_supply_demand")
    if signals.get("asset_heavy"):
        topics.add("balance_sheet")
    if signals.get("has_cash_flow"):
        topics.add("cash_flow")
    if financials:
        topics.add("profitability")
    return topics


def _profile_evidence_support(
    profile_id: str,
    *,
    financials: list[dict[str, object]],
    external_evidence: list[dict[str, object]],
    source_coverage_matrix: dict[str, object],
) -> float:
    required_topics = _profile_required_topics(profile_id)
    covered_topics = _coverage_topics(source_coverage_matrix)
    topic_support = (
        len(set(required_topics) & covered_topics) / len(required_topics)
        if required_topics
        else 0.5
    )
    source_support = 0.0
    if financials:
        source_support += 0.35
    if external_evidence:
        source_support += 0.25
    if any(item.get("analysis_status") == "model_analyzed" for item in external_evidence):
        source_support += 0.15
    return max(0.2, min(0.95, topic_support * 0.7 + source_support * 0.3))


def _score_tier(score: float) -> str:
    thresholds = parameter_value("analyst_engine.tier_thresholds", {})
    thresholds = thresholds if isinstance(thresholds, dict) else {}
    if score >= float(thresholds.get("high", 0.78)):
        return "high"
    if score >= float(thresholds.get("medium", 0.55)):
        return "medium"
    return "low"


def _project_external_evidence_snapshot(
    snapshot: dict[str, object],
) -> dict[str, object]:
    return {key: snapshot.get(key) for key in ANALYST_EXTERNAL_EVIDENCE_FIELDS}


def _has_financial_field(financials: list[dict[str, object]], field_name: str) -> bool:
    for item in financials:
        fields = item.get("fields")
        if (
            isinstance(fields, dict)
            and (value := fields.get(field_name)) is not None
            and value != ""
        ):
            return True
    return False


def _has_any_financial_field(
    financials: list[dict[str, object]],
    field_names: tuple[str, ...],
) -> bool:
    return any(_has_financial_field(financials, field_name) for field_name in field_names)


def _has_nested_number(value: object) -> bool:
    if isinstance(value, bool) or value is None:
        return False
    if isinstance(value, (int, float)):
        return True
    if isinstance(value, dict):
        return any(_has_nested_number(item) for item in value.values())
    if isinstance(value, list):
        return any(_has_nested_number(item) for item in value)
    return False


def _is_number(value: object) -> bool:
    return not isinstance(value, bool) and isinstance(value, (int, float))


def _financial_gap_fields(value: object) -> set[str]:
    if not isinstance(value, list):
        return set()
    fields: set[str] = set()
    for item in value:
        if isinstance(item, dict) and isinstance(item.get("field"), str):
            fields.add(str(item["field"]))
        elif isinstance(item, str):
            fields.add(item)
    return fields


def _financial_periods(financials: list[dict[str, object]]) -> list[str]:
    periods: list[str] = []
    for item in financials:
        period = item.get("period")
        if isinstance(period, str) and period not in periods:
            periods.append(period)
    return periods


def _contains_any(text: str, keywords: tuple[str, ...]) -> bool:
    return any(keyword.lower() in text.lower() for keyword in keywords)


def _model_contains_price_sensitive_text(item: Announcement | Evidence) -> bool:
    text = _join_text_parts(
        item.title,
        getattr(item, "summary", None),
        getattr(item, "key_facts", None),
        getattr(item, "tags", None),
        getattr(item, "analysis_note", None),
    )
    return _contains_any(text, PRICE_SENSITIVE_TEXT_TERMS)


def _remove_price_sensitive_fields(value: object) -> object:
    if isinstance(value, dict):
        return {
            key: _remove_price_sensitive_fields(item)
            for key, item in value.items()
            if str(key).lower() not in PRICE_SENSITIVE_FIELD_NAMES
        }
    if isinstance(value, list):
        return [_remove_price_sensitive_fields(item) for item in value]
    return value


def _join_text_parts(*parts: object) -> str:
    text_parts: list[str] = []
    for part in parts:
        if part is None:
            continue
        if isinstance(part, dict):
            text_parts.extend(_stringify_nested_text(part.values()))
        elif isinstance(part, (list, tuple, set)):
            text_parts.extend(_stringify_nested_text(part))
        else:
            text_parts.append(str(part))
    return " ".join(item for item in text_parts if item)


def _snapshot_use_scope(item: dict[str, object]) -> list[str]:
    value = item.get("use_scope")
    if not isinstance(value, list) or not value:
        return ["fundamental_analysis", "analyst_view", "intrinsic_valuation"]
    return [str(scope) for scope in value if isinstance(scope, str)]


def _stringify_nested_text(values: object) -> list[str]:
    items: list[str] = []
    if isinstance(values, dict):
        iterable = values.values()
    elif isinstance(values, (list, tuple, set)):
        iterable = values
    else:
        return [str(values)]

    for value in iterable:
        if value is None:
            continue
        if isinstance(value, dict):
            items.extend(_stringify_nested_text(value.values()))
        elif isinstance(value, (list, tuple, set)):
            items.extend(_stringify_nested_text(value))
        else:
            items.append(str(value))
    return items


def _unique_strings(values: object) -> list[str]:
    items: list[str] = []
    if not isinstance(values, (list, tuple, set)):
        values = list(values) if values is not None else []
    for value in values:
        if isinstance(value, str):
            normalized = value.strip()
        elif value is not None:
            normalized = str(value).strip()
        else:
            normalized = ""
        if normalized and normalized not in items:
            items.append(normalized)
    return items


def _snapshot_ids(value: object) -> set[int]:
    if not isinstance(value, list):
        return set()

    ids: set[int] = set()
    for item in value:
        if not isinstance(item, dict):
            continue
        raw_id = item.get("id")
        if isinstance(raw_id, int):
            ids.add(raw_id)
    return ids


def _snapshot_periods(value: object) -> set[str]:
    if not isinstance(value, list):
        return set()

    periods: set[str] = set()
    for item in value:
        if not isinstance(item, dict):
            continue
        period = item.get("period")
        if isinstance(period, str):
            periods.add(period)
    return periods


def _hash_snapshot(snapshot: dict[str, object]) -> str:
    payload = json.dumps(snapshot, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _company_snapshot(company: Company) -> dict[str, Any]:
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


def _financial_snapshot(item: FinancialStatement) -> dict[str, object]:
    return {
        "id": item.id,
        "period": item.period,
        "statement_type": item.statement_type,
        "currency": item.currency,
        "fields": _remove_price_sensitive_fields(item.fields),
        "source": item.source,
        "source_url": item.source_url,
        "created_at": item.created_at.isoformat(),
    }


def _announcement_snapshot(item: Announcement) -> dict[str, object]:
    return {
        "id": item.id,
        "title": item.title,
        "published_at": item.published_at.isoformat(),
        "category": item.category,
        "summary": _truncate_text(
            item.summary,
            max_length=int(parameter_value("data_sampling.analysis_excerpt_chars", 360)),
        ),
        "key_facts": _compact_text_list(
            item.key_facts,
            max_items=6,
        ),
        "tags": item.tags,
    }


def _evidence_snapshot(item: Evidence) -> dict[str, object]:
    return {
        "id": item.id,
        "source_type": item.source_type,
        "title": item.title,
        "source": item.source,
        "source_url": item.source_url,
        "published_at": item.published_at.isoformat() if item.published_at else None,
        "summary": _truncate_text(
            item.summary,
            max_length=int(parameter_value("data_sampling.analysis_excerpt_chars", 360)),
        ),
        "key_facts": _compact_text_list(
            item.key_facts,
            max_items=MAX_RESULT_LIST_ITEMS,
        ),
        "impact_direction": item.impact_direction,
        "importance_score": item.importance_score,
        "credibility_score": item.credibility_score,
        "price_sensitive": item.price_sensitive,
        "use_scope": item.use_scope
        or ["fundamental_analysis", "analyst_view", "intrinsic_valuation"],
        "tags": item.tags,
        "requires_review": item.requires_review,
        "analysis_status": item.analysis_status,
        "analysis_note": _truncate_text(
            item.analysis_note,
            max_length=int(parameter_value("data_sampling.analysis_excerpt_chars", 360)),
        ),
    }


def _history_run_snapshot(item: AnalysisRun) -> dict[str, object]:
    return {
        "id": item.id,
        "run_type": item.run_type,
        "analyst_profile": item.analyst_profile,
        "status": item.status,
        "is_latest": item.is_latest,
        "created_at": item.created_at.isoformat(),
        "confidence": item.confidence,
        "result": _compact_result(item.result),
    }


def _compact_result(result: dict[str, object]) -> dict[str, object]:
    if not isinstance(result, dict):
        return {}

    compact: dict[str, object] = {}
    scalar_keys = (
        "analyst_profile",
        "overview",
        "summary",
        "profile_fit_score",
        "confidence",
        "created_evidence_count",
    )
    list_keys = (
        "key_observations",
        "financial_observations",
        "announcement_observations",
        "risk_flags",
        "counter_evidence",
        "valuation_assumption_suggestions",
        "data_gaps",
        "follow_up_questions",
        "accounting_events",
    )

    for key in scalar_keys:
        value = result.get(key)
        if isinstance(value, str):
            compact[key] = _truncate_text(
                sanitize_error_text(value),
                max_length=int(parameter_value("data_sampling.analysis_excerpt_chars", 360)),
            )
        elif value is not None:
            compact[key] = value

    for key in list_keys:
        value = result.get(key)
        if isinstance(value, list):
            compact[key] = _compact_text_list(value, max_items=MAX_RESULT_LIST_ITEMS)

    rule_checks = result.get("rule_checks")
    if isinstance(rule_checks, list):
        compact["rule_checks"] = [
            _compact_rule_check(item)
            for item in rule_checks[:MAX_RESULT_LIST_ITEMS]
            if isinstance(item, dict)
        ]

    for key in ("analysis_basis", "score_explanations"):
        value = result.get(key)
        if isinstance(value, dict):
            compact[key] = value

    return compact


def _compact_rule_check(item: dict[str, object]) -> dict[str, object]:
    compact: dict[str, object] = {}
    for key in ("rule_id", "status"):
        value = item.get(key)
        if isinstance(value, str):
            compact[key] = value
    summary = item.get("summary")
    if isinstance(summary, str):
        compact["summary"] = _truncate_text(
            sanitize_error_text(summary),
            max_length=int(parameter_value("data_sampling.analysis_excerpt_chars", 360)),
        )
    return compact


def _compact_text_list(value: list[object], *, max_items: int) -> list[str]:
    items: list[str] = []
    for item in value:
        normalized = _truncate_text(
            sanitize_error_text(str(item)),
            max_length=int(parameter_value("data_sampling.analysis_excerpt_chars", 360)),
        )
        if normalized and normalized not in items:
            items.append(normalized)
        if len(items) >= max_items:
            break
    return items


def _truncate_text(value: str | None, *, max_length: int) -> str | None:
    if not value:
        return None
    normalized = " ".join(value.split())
    if len(normalized) <= max_length:
        return normalized
    return f"{normalized[:max_length]}..."
