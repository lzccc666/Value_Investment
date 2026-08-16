from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from sqlalchemy import Select

from app.configuration.runtime import parameter_value
from app.db.models import FinancialStatement

FACT_FIELDS = (
    "revenue",
    "gross_profit",
    "net_profit",
    "deducted_net_profit",
    "operating_cash_flow",
    "capital_expenditure",
    "free_cash_flow",
    "cash_and_equivalents",
    "interest_bearing_debt",
    "net_cash",
    "total_assets",
    "total_liabilities",
    "shareholders_equity",
    "dividend",
    "buyback_amount",
    "shares_outstanding",
    "depreciation_and_amortization",
    "working_capital_change",
)
INCOME_STATEMENT_FACT_FIELDS = (
    "operating_cost",
    "taxes_and_surcharges",
    "selling_expense",
    "admin_expense",
    "r_and_d_expense",
    "finance_expense",
    "other_income",
    "investment_income",
    "fair_value_change_income",
    "credit_impairment_loss",
    "asset_impairment_loss",
    "operating_profit",
    "non_operating_income",
    "non_operating_expense",
    "total_profit",
    "income_tax_expense",
    "minority_interest",
)
ALL_FACT_FIELDS = FACT_FIELDS + INCOME_STATEMENT_FACT_FIELDS
OPERATING_CASH_FLOW_PROXY_FIELDS = (
    "operating_cash_flow_per_share",
    "operating_cash_flow_to_revenue",
)
BUYBACK_PROXY_FIELDS = ("buyback_amount_proxy", "treasury_shares")
EXPENSE_BREAKDOWN_FIELDS = (
    "selling_expense",
    "admin_expense",
    "r_and_d_expense",
    "finance_expense",
)
IMPAIRMENT_FIELDS = ("credit_impairment_loss", "asset_impairment_loss")
NON_OPERATING_FIELDS = ("non_operating_income", "non_operating_expense")
STRUCTURED_GAP_DEFINITIONS = {
    "operating_cash_flow": {
        "severity": "medium",
        "reason": "缺少经营现金流绝对值，无法计算经营现金流/净利润。",
        "needed_by": ["analyst_view", "valuation_lab"],
    },
    "capital_expenditure": {
        "severity": "high",
        "reason": "缺少资本开支，无法计算严格自由现金流。",
        "needed_by": ["valuation_lab", "analyst_view"],
    },
    "free_cash_flow": {
        "severity": "high",
        "reason": "缺少自由现金流，无法直接用于 DCF 或所有者盈余估值。",
        "needed_by": ["valuation_lab", "analyst_view"],
    },
    "interest_bearing_debt": {
        "severity": "high",
        "reason": "缺少有息负债，无法计算现金/有息负债和估值资产负债调整。",
        "needed_by": ["valuation_lab", "analyst_view"],
    },
    "cash_and_equivalents": {
        "severity": "high",
        "reason": "缺少货币资金，无法判断净现金或偿债安全垫。",
        "needed_by": ["valuation_lab", "analyst_view"],
    },
    "dividend": {
        "severity": "medium",
        "reason": "缺少分红总额，无法计算分红折现和分红率。",
        "needed_by": ["valuation_lab", "analyst_view"],
    },
    "buyback_amount": {
        "severity": "medium",
        "reason": "缺少回购金额，无法评估股东回报中的回购贡献。",
        "needed_by": ["valuation_lab", "analyst_view"],
    },
    "shares_outstanding": {
        "severity": "high",
        "reason": "缺少总股本，无法换算每股内在价值。",
        "needed_by": ["valuation_lab"],
    },
    "income_statement": {
        "severity": "medium",
        "reason": (
            "缺少利润表明细；已有收入/净利润等结果项但缺少利润构成明细，会降低利润质量判断置信度。"
        ),
        "needed_by": ["analyst_view", "valuation_lab"],
    },
    "operating_cost": {
        "severity": "medium",
        "reason": "缺少营业成本，无法复核毛利和成本压力。",
        "needed_by": ["analyst_view", "valuation_lab"],
    },
    "expense_breakdown": {
        "severity": "medium",
        "reason": "缺少费用明细，无法判断销售、管理、研发和财务费用纪律。",
        "needed_by": ["analyst_view", "valuation_lab"],
    },
    "operating_profit": {
        "severity": "medium",
        "reason": "缺少营业利润，无法判断主营利润对净利润的支撑。",
        "needed_by": ["analyst_view", "valuation_lab"],
    },
    "impairment_losses": {
        "severity": "low",
        "reason": "缺少减值损失明细，资产质量和利润质量判断置信度下降。",
        "needed_by": ["analyst_view", "valuation_lab"],
    },
    "non_operating_items": {
        "severity": "low",
        "reason": "缺少营业外收支明细，无法识别非经常性利润贡献。",
        "needed_by": ["analyst_view", "valuation_lab"],
    },
    "income_tax_expense": {
        "severity": "low",
        "reason": "缺少所得税费用，无法计算有效税率。",
        "needed_by": ["analyst_view", "valuation_lab"],
    },
}


def financial_statement_ordering() -> tuple[object, object, object]:
    report_date = FinancialStatement.fields["report_date"].as_string()
    return (report_date.desc(), FinancialStatement.period.desc(), FinancialStatement.id.desc())


def order_financial_statement_query(
    stmt: Select[tuple[FinancialStatement]],
) -> Select[tuple[FinancialStatement]]:
    return stmt.order_by(*financial_statement_ordering())


def build_financial_evidence_pack(
    statements: Iterable[FinancialStatement],
) -> dict[str, object]:
    statement_snapshots = [_statement_snapshot(item) for item in statements]
    snapshots = _merge_snapshots_by_period(statement_snapshots)
    latest = snapshots[0] if snapshots else None
    data_gaps = _build_structured_data_gaps(snapshots)
    trends = _build_trends(snapshots, data_gaps)
    facts = _build_facts(snapshots, latest)
    metrics = _build_metrics(latest)
    flags = _build_flags(snapshots)
    cash_flow_coverage = _build_cash_flow_coverage(snapshots)
    cash_flow_quality = _build_cash_flow_quality(latest, cash_flow_coverage)
    income_statement_quality = _build_income_statement_quality(latest)
    balance_sheet_adjustment = _build_balance_sheet_adjustment(latest)
    capital_allocation = _build_capital_allocation(latest)
    valuation_readiness = _build_valuation_readiness(latest, data_gaps)
    data_quality = _build_data_quality(snapshots, data_gaps, cash_flow_coverage)

    return {
        "latest_period": latest["period"] if latest else None,
        "periods": [item["period"] for item in snapshots],
        "financial_facts": facts,
        "financial_metrics": metrics,
        "cash_flow_coverage": cash_flow_coverage,
        "financial_trends": trends,
        "financial_flags": flags,
        "financial_data_gaps": data_gaps,
        "financial_data_gap_messages": [str(item["reason"]) for item in data_gaps],
        "cash_flow_quality": cash_flow_quality,
        "income_statement_quality": income_statement_quality,
        "profit_composition": income_statement_quality,
        "balance_sheet_adjustment": balance_sheet_adjustment,
        "capital_allocation": capital_allocation,
        "valuation_readiness": valuation_readiness,
        "quality_matrix": _build_quality_matrix(
            metrics=metrics,
            trends=trends,
            cash_flow_quality=cash_flow_quality,
            income_statement_quality=income_statement_quality,
            balance_sheet_adjustment=balance_sheet_adjustment,
            capital_allocation=capital_allocation,
            valuation_readiness=valuation_readiness,
        ),
        "analyst_summary": _build_analyst_summary(
            latest=latest,
            metrics=metrics,
            flags=flags,
            data_gaps=data_gaps,
            cash_flow_quality=cash_flow_quality,
            income_statement_quality=income_statement_quality,
            balance_sheet_adjustment=balance_sheet_adjustment,
            capital_allocation=capital_allocation,
        ),
        "data_quality": data_quality,
    }


def _statement_snapshot(statement: FinancialStatement) -> dict[str, object]:
    fields = statement.fields if isinstance(statement.fields, dict) else {}
    return {
        "id": statement.id,
        "period": statement.period,
        "statement_type": statement.statement_type,
        "fields": dict(fields),
    }


def _merge_snapshots_by_period(
    statements: list[dict[str, object]],
) -> list[dict[str, object]]:
    by_period: dict[str, dict[str, object]] = {}
    for statement in statements:
        period = str(statement["period"])
        fields = _fields(statement)
        snapshot = by_period.setdefault(
            period,
            {
                "period": period,
                "statement_types": [],
                "fields": {},
                "source_statement_ids": [],
            },
        )
        snapshot["source_statement_ids"].append(statement["id"])
        statement_type = str(statement["statement_type"])
        if statement_type not in snapshot["statement_types"]:
            snapshot["statement_types"].append(statement_type)
        merged_fields = _fields(snapshot)
        for key, value in fields.items():
            if value is not None:
                merged_fields[key] = value

    snapshots = list(by_period.values())
    for snapshot in snapshots:
        _derive_period_fields(snapshot)
    return sorted(
        snapshots,
        key=lambda item: (str(_fields(item).get("report_date") or ""), str(item["period"])),
        reverse=True,
    )


def _derive_period_fields(snapshot: dict[str, object]) -> None:
    fields = _fields(snapshot)
    operating_cash_flow = _number_or_none(fields.get("operating_cash_flow"))
    capital_expenditure = _number_or_none(fields.get("capital_expenditure"))
    if capital_expenditure is None:
        purchase = _number_or_none(fields.get("purchase_fixed_assets_cash_paid"))
        if purchase is not None:
            capital_expenditure = abs(purchase)
            fields["capital_expenditure"] = capital_expenditure
    if _number_or_none(fields.get("free_cash_flow")) is None:
        if operating_cash_flow is not None and capital_expenditure is not None:
            fields["free_cash_flow"] = operating_cash_flow - capital_expenditure

    cash = _number_or_none(fields.get("cash_and_equivalents"))
    debt = _number_or_none(fields.get("interest_bearing_debt"))
    if _number_or_none(fields.get("net_cash")) is None and cash is not None and debt is not None:
        fields["net_cash"] = cash - debt

    total_assets = _number_or_none(fields.get("total_assets"))
    total_liabilities = _number_or_none(fields.get("total_liabilities"))
    if (
        _number_or_none(fields.get("asset_liability_ratio")) is None
        and total_assets is not None
        and total_assets != 0
        and total_liabilities is not None
    ):
        fields["asset_liability_ratio"] = total_liabilities / total_assets

    net_profit = _number_or_none(fields.get("net_profit"))
    revenue = _number_or_none(fields.get("revenue"))
    free_cash_flow = _number_or_none(fields.get("free_cash_flow"))
    operating_cost = _number_or_none(fields.get("operating_cost"))
    if (
        _number_or_none(fields.get("gross_profit")) is None
        and revenue is not None
        and operating_cost is not None
    ):
        fields["gross_profit"] = revenue - operating_cost
    gross_profit = _number_or_none(fields.get("gross_profit"))
    if _number_or_none(fields.get("gross_margin")) is None and gross_profit is not None and revenue:
        fields["gross_margin"] = gross_profit / revenue
    if _number_or_none(fields.get("net_margin")) is None and net_profit is not None and revenue:
        fields["net_margin"] = net_profit / revenue
    if (
        _number_or_none(fields.get("operating_cash_flow_to_net_profit")) is None
        and operating_cash_flow is not None
        and net_profit
    ):
        fields["operating_cash_flow_to_net_profit"] = operating_cash_flow / net_profit
    if (
        _number_or_none(fields.get("free_cash_flow_to_net_profit")) is None
        and free_cash_flow is not None
        and net_profit
    ):
        fields["free_cash_flow_to_net_profit"] = free_cash_flow / net_profit
    if (
        _number_or_none(fields.get("free_cash_flow_margin")) is None
        and free_cash_flow is not None
        and revenue
    ):
        fields["free_cash_flow_margin"] = free_cash_flow / revenue
    if (
        _number_or_none(fields.get("cash_to_interest_bearing_debt")) is None
        and cash is not None
        and debt
    ):
        fields["cash_to_interest_bearing_debt"] = cash / debt
    equity = _number_or_none(fields.get("shareholders_equity"))
    if (
        _number_or_none(fields.get("interest_bearing_debt_to_equity")) is None
        and debt is not None
        and equity
    ):
        fields["interest_bearing_debt_to_equity"] = debt / equity
    dividend = _number_or_none(fields.get("dividend"))
    if (
        _number_or_none(fields.get("dividend_payout_ratio")) is None
        and dividend is not None
        and net_profit
    ):
        fields["dividend_payout_ratio"] = dividend / net_profit
    buyback = _number_or_none(fields.get("buyback_amount"))
    if _number_or_none(fields.get("buyback_ratio")) is None and buyback is not None and net_profit:
        fields["buyback_ratio"] = buyback / net_profit
    if (
        _number_or_none(fields.get("capital_expenditure_to_revenue")) is None
        and capital_expenditure is not None
        and revenue
    ):
        fields["capital_expenditure_to_revenue"] = capital_expenditure / revenue
    operating_profit = _number_or_none(fields.get("operating_profit"))
    if (
        _number_or_none(fields.get("operating_margin")) is None
        and operating_profit is not None
        and revenue
    ):
        fields["operating_margin"] = operating_profit / revenue
    if (
        _number_or_none(fields.get("operating_profit_to_net_profit")) is None
        and operating_profit is not None
        and net_profit
    ):
        fields["operating_profit_to_net_profit"] = operating_profit / net_profit
    deducted_net_profit = _number_or_none(fields.get("deducted_net_profit"))
    if (
        _number_or_none(fields.get("deducted_net_profit_to_net_profit")) is None
        and deducted_net_profit is not None
        and net_profit
    ):
        fields["deducted_net_profit_to_net_profit"] = deducted_net_profit / net_profit
    for source_field, ratio_field in (
        ("investment_income", "investment_income_to_net_profit"),
        ("fair_value_change_income", "fair_value_change_to_net_profit"),
    ):
        value = _number_or_none(fields.get(source_field))
        if _number_or_none(fields.get(ratio_field)) is None and value is not None and net_profit:
            fields[ratio_field] = value / net_profit
    impairment_loss = _sum_abs_known_numbers(
        fields.get("credit_impairment_loss"),
        fields.get("asset_impairment_loss"),
    )
    if (
        _number_or_none(fields.get("impairment_loss_to_net_profit")) is None
        and impairment_loss is not None
        and net_profit
    ):
        fields["impairment_loss_to_net_profit"] = impairment_loss / abs(net_profit)
    non_operating_income = _number_or_none(fields.get("non_operating_income"))
    non_operating_expense = _number_or_none(fields.get("non_operating_expense"))
    non_operating_profit = _subtract_optional(non_operating_income, non_operating_expense)
    if (
        _number_or_none(fields.get("non_operating_profit_to_net_profit")) is None
        and non_operating_profit is not None
        and net_profit
    ):
        fields["non_operating_profit_to_net_profit"] = non_operating_profit / net_profit
    total_profit = _number_or_none(fields.get("total_profit"))
    income_tax = _number_or_none(fields.get("income_tax_expense"))
    if (
        _number_or_none(fields.get("effective_tax_rate")) is None
        and income_tax is not None
        and total_profit
    ):
        fields["effective_tax_rate"] = income_tax / total_profit
    for source_field, ratio_field in (
        ("selling_expense", "selling_expense_ratio"),
        ("admin_expense", "admin_expense_ratio"),
        ("r_and_d_expense", "r_and_d_expense_ratio"),
        ("finance_expense", "finance_expense_ratio"),
    ):
        value = _number_or_none(fields.get(source_field))
        if _number_or_none(fields.get(ratio_field)) is None and value is not None and revenue:
            fields[ratio_field] = value / revenue
    period_expense = _sum_known_numbers(
        fields.get("selling_expense"),
        fields.get("admin_expense"),
        fields.get("r_and_d_expense"),
        fields.get("finance_expense"),
    )
    if (
        _number_or_none(fields.get("period_expense_ratio")) is None
        and period_expense is not None
        and revenue
    ):
        fields["period_expense_ratio"] = period_expense / revenue
    if _number_or_none(fields.get("total_shareholder_return")) is None and (
        dividend is not None or buyback is not None
    ):
        fields["total_shareholder_return"] = (dividend or 0.0) + (buyback or 0.0)


def _build_facts(
    snapshots: list[dict[str, object]],
    latest: dict[str, object] | None,
) -> dict[str, object]:
    latest_fields = _fields(latest)
    return {
        "latest": {field: _number_or_none(latest_fields.get(field)) for field in ALL_FACT_FIELDS},
        "series": {
            field: [
                {"period": item["period"], "value": value}
                for item in snapshots
                if (value := _number_or_none(_fields(item).get(field))) is not None
            ]
            for field in ALL_FACT_FIELDS
        },
    }


def _build_metrics(latest: dict[str, object] | None) -> dict[str, object]:
    latest_fields = _fields(latest)
    return {
        "profitability": {
            "roe": _number_or_none(latest_fields.get("roe")),
            "gross_margin": _number_or_none(latest_fields.get("gross_margin")),
            "net_margin": _number_or_none(latest_fields.get("net_margin")),
        },
        "profit_structure": {
            "operating_margin": _number_or_none(latest_fields.get("operating_margin")),
            "operating_profit_to_net_profit": _number_or_none(
                latest_fields.get("operating_profit_to_net_profit")
            ),
            "deducted_net_profit_to_net_profit": _number_or_none(
                latest_fields.get("deducted_net_profit_to_net_profit")
            ),
            "investment_income_to_net_profit": _number_or_none(
                latest_fields.get("investment_income_to_net_profit")
            ),
            "fair_value_change_to_net_profit": _number_or_none(
                latest_fields.get("fair_value_change_to_net_profit")
            ),
            "impairment_loss_to_net_profit": _number_or_none(
                latest_fields.get("impairment_loss_to_net_profit")
            ),
            "non_operating_profit_to_net_profit": _number_or_none(
                latest_fields.get("non_operating_profit_to_net_profit")
            ),
            "effective_tax_rate": _number_or_none(latest_fields.get("effective_tax_rate")),
        },
        "expense_control": {
            "selling_expense_ratio": _number_or_none(latest_fields.get("selling_expense_ratio")),
            "admin_expense_ratio": _number_or_none(latest_fields.get("admin_expense_ratio")),
            "r_and_d_expense_ratio": _number_or_none(latest_fields.get("r_and_d_expense_ratio")),
            "finance_expense_ratio": _number_or_none(latest_fields.get("finance_expense_ratio")),
            "period_expense_ratio": _number_or_none(latest_fields.get("period_expense_ratio")),
        },
        "cash_quality": {
            "operating_cash_flow_to_revenue": _number_or_none(
                latest_fields.get("operating_cash_flow_to_revenue")
            ),
            "operating_cash_flow_to_net_profit": _number_or_none(
                latest_fields.get("operating_cash_flow_to_net_profit")
            ),
            "free_cash_flow_to_net_profit": _number_or_none(
                latest_fields.get("free_cash_flow_to_net_profit")
            ),
            "free_cash_flow_margin": _number_or_none(latest_fields.get("free_cash_flow_margin")),
        },
        "growth_quality": {
            "revenue_yoy": _number_or_none(latest_fields.get("revenue_yoy")),
            "net_profit_yoy": _number_or_none(latest_fields.get("net_profit_yoy")),
        },
        "balance_sheet_safety": {
            "asset_liability_ratio": _number_or_none(latest_fields.get("asset_liability_ratio")),
            "cash_to_interest_bearing_debt": _number_or_none(
                latest_fields.get("cash_to_interest_bearing_debt")
            ),
            "net_cash": _number_or_none(latest_fields.get("net_cash")),
            "interest_bearing_debt_to_equity": _number_or_none(
                latest_fields.get("interest_bearing_debt_to_equity")
            ),
        },
        "efficiency": {
            "total_assets_turnover": _number_or_none(latest_fields.get("total_assets_turnover")),
            "inventory_turnover_days": _number_or_none(
                latest_fields.get("inventory_turnover_days")
            ),
        },
        "per_share": {
            "eps": _number_or_none(latest_fields.get("eps")),
            "bps": _number_or_none(latest_fields.get("bps")),
            "operating_cash_flow_per_share": _number_or_none(
                latest_fields.get("operating_cash_flow_per_share")
            ),
        },
        "shareholder_return": {
            "dividend_payout_ratio": _number_or_none(latest_fields.get("dividend_payout_ratio")),
            "buyback_ratio": _number_or_none(latest_fields.get("buyback_ratio")),
            "share_dilution_rate": _number_or_none(latest_fields.get("share_dilution_rate")),
        },
        "capital_allocation": {
            "capital_expenditure_to_revenue": _number_or_none(
                latest_fields.get("capital_expenditure_to_revenue")
            ),
            "dividend": _number_or_none(latest_fields.get("dividend")),
            "buyback_amount": _number_or_none(latest_fields.get("buyback_amount")),
            "total_shareholder_return": _number_or_none(
                latest_fields.get("total_shareholder_return")
            ),
        },
    }


def _build_cash_flow_coverage(snapshots: list[dict[str, object]]) -> dict[str, object]:
    available_fields = _available_numeric_fields(snapshots)
    proxy_fields = [
        field for field in OPERATING_CASH_FLOW_PROXY_FIELDS if field in available_fields
    ]
    return {
        "has_operating_cash_flow": "operating_cash_flow" in available_fields,
        "has_cash_flow_proxy": bool(proxy_fields),
        "proxy_fields": proxy_fields,
        "note": (
            "已有经营现金流代理指标，但缺少经营现金流绝对值。"
            if proxy_fields and "operating_cash_flow" not in available_fields
            else None
        ),
    }


def _build_cash_flow_quality(
    latest: dict[str, object] | None, cash_flow_coverage: dict[str, object]
) -> dict[str, object]:
    fields = _fields(latest)
    return {
        "operating_cash_flow": _number_or_none(fields.get("operating_cash_flow")),
        "capital_expenditure": _number_or_none(fields.get("capital_expenditure")),
        "free_cash_flow": _number_or_none(fields.get("free_cash_flow")),
        "operating_cash_flow_to_net_profit": _number_or_none(
            fields.get("operating_cash_flow_to_net_profit")
        ),
        "free_cash_flow_to_net_profit": _number_or_none(fields.get("free_cash_flow_to_net_profit")),
        "free_cash_flow_margin": _number_or_none(fields.get("free_cash_flow_margin")),
        "cash_flow_coverage": cash_flow_coverage,
    }


def _build_income_statement_quality(latest: dict[str, object] | None) -> dict[str, object]:
    fields = _fields(latest)
    return {
        "revenue": _number_or_none(fields.get("revenue")),
        "operating_cost": _number_or_none(fields.get("operating_cost")),
        "gross_profit": _number_or_none(fields.get("gross_profit")),
        "operating_profit": _number_or_none(fields.get("operating_profit")),
        "total_profit": _number_or_none(fields.get("total_profit")),
        "net_profit": _number_or_none(fields.get("net_profit")),
        "parent_net_profit": _number_or_none(fields.get("parent_net_profit")),
        "deducted_net_profit": _number_or_none(fields.get("deducted_net_profit")),
        "investment_income": _number_or_none(fields.get("investment_income")),
        "fair_value_change_income": _number_or_none(fields.get("fair_value_change_income")),
        "credit_impairment_loss": _number_or_none(fields.get("credit_impairment_loss")),
        "asset_impairment_loss": _number_or_none(fields.get("asset_impairment_loss")),
        "non_operating_income": _number_or_none(fields.get("non_operating_income")),
        "non_operating_expense": _number_or_none(fields.get("non_operating_expense")),
        "income_tax_expense": _number_or_none(fields.get("income_tax_expense")),
        "profit_structure": {
            "operating_margin": _number_or_none(fields.get("operating_margin")),
            "operating_profit_to_net_profit": _number_or_none(
                fields.get("operating_profit_to_net_profit")
            ),
            "deducted_net_profit_to_net_profit": _number_or_none(
                fields.get("deducted_net_profit_to_net_profit")
            ),
            "investment_income_to_net_profit": _number_or_none(
                fields.get("investment_income_to_net_profit")
            ),
            "fair_value_change_to_net_profit": _number_or_none(
                fields.get("fair_value_change_to_net_profit")
            ),
            "impairment_loss_to_net_profit": _number_or_none(
                fields.get("impairment_loss_to_net_profit")
            ),
            "non_operating_profit_to_net_profit": _number_or_none(
                fields.get("non_operating_profit_to_net_profit")
            ),
            "effective_tax_rate": _number_or_none(fields.get("effective_tax_rate")),
        },
        "expense_control": {
            "selling_expense_ratio": _number_or_none(fields.get("selling_expense_ratio")),
            "admin_expense_ratio": _number_or_none(fields.get("admin_expense_ratio")),
            "r_and_d_expense_ratio": _number_or_none(fields.get("r_and_d_expense_ratio")),
            "finance_expense_ratio": _number_or_none(fields.get("finance_expense_ratio")),
            "period_expense_ratio": _number_or_none(fields.get("period_expense_ratio")),
        },
    }


def _build_balance_sheet_adjustment(latest: dict[str, object] | None) -> dict[str, object]:
    fields = _fields(latest)
    return {
        "cash_and_equivalents": _number_or_none(fields.get("cash_and_equivalents")),
        "interest_bearing_debt": _number_or_none(fields.get("interest_bearing_debt")),
        "net_cash": _number_or_none(fields.get("net_cash")),
        "asset_liability_ratio": _number_or_none(fields.get("asset_liability_ratio")),
        "cash_to_interest_bearing_debt": _number_or_none(
            fields.get("cash_to_interest_bearing_debt")
        ),
    }


def _build_capital_allocation(latest: dict[str, object] | None) -> dict[str, object]:
    fields = _fields(latest)
    return {
        "capital_expenditure": _number_or_none(fields.get("capital_expenditure")),
        "dividend": _number_or_none(fields.get("dividend")),
        "buyback_amount": _number_or_none(fields.get("buyback_amount")),
        "buyback_amount_proxy": _number_or_none(fields.get("buyback_amount_proxy")),
        "shares_outstanding": _number_or_none(fields.get("shares_outstanding")),
        "share_dilution_rate": _number_or_none(fields.get("share_dilution_rate")),
    }


def _build_valuation_readiness(
    latest: dict[str, object] | None, data_gaps: list[dict[str, object]]
) -> dict[str, object]:
    fields = _fields(latest)
    structured_gap_fields = {str(item["field"]) for item in data_gaps}
    has_fcf = _number_or_none(fields.get("free_cash_flow")) is not None
    has_ocf_proxy = any(
        _number_or_none(fields.get(field)) is not None for field in OPERATING_CASH_FLOW_PROXY_FIELDS
    )
    has_owner_earnings_inputs = all(
        _number_or_none(fields.get(field)) is not None
        for field in ("net_profit", "operating_cash_flow", "capital_expenditure")
    )
    readiness = {
        "dcf_ready": has_fcf or has_ocf_proxy,
        "owner_earnings_ready": has_owner_earnings_inputs,
        "dividend_discount_ready": all(
            _number_or_none(fields.get(field)) is not None
            for field in ("dividend", "dividend_payout_ratio")
        ),
        "residual_income_ready": all(
            _number_or_none(fields.get(field)) is not None
            for field in ("shareholders_equity", "roe")
        ),
        "asset_value_ready": all(
            _number_or_none(fields.get(field)) is not None
            for field in (
                "cash_and_equivalents",
                "interest_bearing_debt",
                "total_assets",
                "total_liabilities",
            )
        ),
    }
    return {
        **readiness,
        "ready_methods": [key for key, value in readiness.items() if value],
        "blocking_fields": sorted(structured_gap_fields),
    }


def _build_trends(
    snapshots: list[dict[str, object]],
    data_gaps: list[dict[str, object]],
) -> dict[str, object]:
    annual_snapshots = [item for item in snapshots if _looks_like_annual_report(item)]
    cagr_years = [int(value) for value in parameter_value("financial_flags.cagr_years", [3, 5])]
    trends = {
        "roe_stability": _stability(snapshots, "roe"),
        "gross_margin_stability": _stability(snapshots, "gross_margin"),
        "net_margin_stability": _stability(snapshots, "net_margin"),
        "operating_margin_stability": _stability(snapshots, "operating_margin"),
        "period_expense_ratio_trend": _trend_direction(snapshots, "period_expense_ratio"),
        "r_and_d_expense_ratio_trend": _trend_direction(snapshots, "r_and_d_expense_ratio"),
        "finance_expense_ratio_trend": _trend_direction(snapshots, "finance_expense_ratio"),
        "investment_income_to_net_profit_trend": _trend_direction(
            snapshots, "investment_income_to_net_profit"
        ),
        "impairment_loss_to_net_profit_trend": _trend_direction(
            snapshots, "impairment_loss_to_net_profit"
        ),
        "effective_tax_rate_trend": _trend_direction(snapshots, "effective_tax_rate"),
        "capital_expenditure_to_revenue_trend": _trend_direction(
            snapshots, "capital_expenditure_to_revenue"
        ),
        "interest_bearing_debt_trend": _trend_direction(snapshots, "interest_bearing_debt"),
        "dividend_stability": _stability(snapshots, "dividend"),
        "share_count_trend": _trend_direction(snapshots, "shares_outstanding"),
    }
    for years in cagr_years:
        for field in ("revenue", "net_profit", "free_cash_flow"):
            trends[f"{field}_cagr_{years}y"] = _cagr(annual_snapshots, field, years=years)
    primary_cagr_year = min(cagr_years) if cagr_years else 3
    if annual_snapshots and trends.get(f"revenue_cagr_{primary_cagr_year}y") is None:
        _append_gap(
            data_gaps,
            field="revenue_cagr_3y",
            severity="low",
            reason="年报收入样本不足或存在非正数，无法计算 3 年收入 CAGR。",
            needed_by=["analyst_view", "valuation_lab"],
        )
    if annual_snapshots and trends.get(f"net_profit_cagr_{primary_cagr_year}y") is None:
        _append_gap(
            data_gaps,
            field="net_profit_cagr_3y",
            severity="low",
            reason="年报净利润样本不足或存在非正数，无法计算 3 年净利润 CAGR。",
            needed_by=["analyst_view", "valuation_lab"],
        )
    if not annual_snapshots and snapshots:
        _append_gap(
            data_gaps,
            field="annual_report_series",
            severity="medium",
            reason="缺少可识别年报数据，CAGR 口径暂不稳定。",
            needed_by=["analyst_view", "valuation_lab"],
        )
    return trends


def _build_flags(snapshots: list[dict[str, object]]) -> list[dict[str, object]]:
    if not snapshots:
        return []

    flags: list[dict[str, object]] = []
    latest = snapshots[0]
    fields = _fields(latest)
    period = str(latest["period"])
    revenue_yoy = _number_or_none(fields.get("revenue_yoy"))
    net_profit_yoy = _number_or_none(fields.get("net_profit_yoy"))
    asset_liability_ratio = _number_or_none(fields.get("asset_liability_ratio"))
    cash_to_revenue = _number_or_none(fields.get("operating_cash_flow_to_revenue"))
    free_cash_flow_to_profit = _number_or_none(fields.get("free_cash_flow_to_net_profit"))
    deducted_profit_ratio = _number_or_none(fields.get("deducted_net_profit_to_net_profit"))
    investment_profit_ratio = _number_or_none(fields.get("investment_income_to_net_profit"))
    fair_value_profit_ratio = _number_or_none(fields.get("fair_value_change_to_net_profit"))
    impairment_profit_ratio = _number_or_none(fields.get("impairment_loss_to_net_profit"))
    non_operating_profit_ratio = _number_or_none(fields.get("non_operating_profit_to_net_profit"))
    effective_tax_rate = _number_or_none(fields.get("effective_tax_rate"))

    if revenue_yoy is not None and revenue_yoy < float(
        parameter_value("financial_flags.revenue_yoy_min", 0.0)
    ):
        flags.append(
            _flag("revenue_growth_negative", "warn", "收入同比为负，需要复核增长压力。", period)
        )
    if net_profit_yoy is not None and net_profit_yoy < float(
        parameter_value("financial_flags.net_profit_yoy_min", 0.0)
    ):
        flags.append(
            _flag(
                "profit_growth_negative",
                "risk",
                "净利润同比为负，需要结合公告复核原因。",
                period,
            )
        )
    if (
        revenue_yoy is not None
        and net_profit_yoy is not None
        and net_profit_yoy - revenue_yoy
        < float(parameter_value("financial_flags.profit_revenue_gap_min", -0.10))
    ):
        flags.append(
            _flag(
                "profit_growth_lags_revenue",
                "warn",
                "净利润增速明显弱于收入增速，利润质量需要复核。",
                period,
            )
        )
    if asset_liability_ratio is not None and asset_liability_ratio > float(
        parameter_value("financial_flags.asset_liability_ratio_max", 0.70)
    ):
        flags.append(
            _flag(
                "high_asset_liability_ratio",
                "risk",
                "资产负债率高于 70%，财务安全边际偏弱。",
                period,
            )
        )
    if cash_to_revenue is not None and cash_to_revenue < float(
        parameter_value("financial_flags.ocf_to_revenue_min", 0.05)
    ):
        flags.append(
            _flag(
                "low_operating_cash_flow_to_revenue",
                "warn",
                "经营现金流/收入低于 5%，收入现金含量偏弱。",
                period,
            )
        )
    if free_cash_flow_to_profit is not None and free_cash_flow_to_profit < float(
        parameter_value("financial_flags.fcf_to_profit_min", 0.0)
    ):
        flags.append(
            _flag(
                "negative_free_cash_flow_to_profit",
                "risk",
                "自由现金流为负或无法覆盖利润，估值假设需保守。",
                period,
            )
        )
    if investment_profit_ratio is not None and abs(investment_profit_ratio) > float(
        parameter_value("financial_flags.investment_profit_ratio_abs_max", 0.20)
    ):
        flags.append(
            _flag(
                "high_investment_income_to_profit",
                "warn",
                "投资收益占净利润比例较高，利润可持续性需要复核。",
                period,
            )
        )
    if fair_value_profit_ratio is not None and abs(fair_value_profit_ratio) > float(
        parameter_value("financial_flags.fair_value_profit_ratio_abs_max", 0.10)
    ):
        flags.append(
            _flag(
                "high_fair_value_change_to_profit",
                "warn",
                "公允价值变动占净利润比例较高，利润质量需要复核。",
                period,
            )
        )
    if impairment_profit_ratio is not None and impairment_profit_ratio > float(
        parameter_value("financial_flags.impairment_profit_ratio_max", 0.10)
    ):
        flags.append(
            _flag(
                "high_impairment_loss_to_profit",
                "risk",
                "减值损失占净利润比例较高，需复核资产质量和利润质量。",
                period,
            )
        )
    if non_operating_profit_ratio is not None and abs(non_operating_profit_ratio) > float(
        parameter_value("financial_flags.non_operating_profit_ratio_abs_max", 0.10)
    ):
        flags.append(
            _flag(
                "high_non_operating_profit_to_profit",
                "warn",
                "营业外收支占净利润比例较高，需识别非经常性利润贡献。",
                period,
            )
        )
    if effective_tax_rate is not None and (
        effective_tax_rate < float(parameter_value("financial_flags.effective_tax_rate_min", 0.0))
        or effective_tax_rate
        > float(parameter_value("financial_flags.effective_tax_rate_max", 0.35))
    ):
        flags.append(
            _flag(
                "abnormal_effective_tax_rate",
                "warn",
                "有效税率异常，需复核所得税费用和利润口径。",
                period,
            )
        )
    if deducted_profit_ratio is not None and deducted_profit_ratio < float(
        parameter_value("financial_flags.deducted_profit_ratio_min", 0.80)
    ):
        flags.append(
            _flag(
                "deducted_profit_lags_parent_profit",
                "warn",
                "扣非净利润显著弱于归母净利润，需复核非经常性收益。",
                period,
            )
        )

    for field, code, label in (
        ("gross_margin", "gross_margin_decline", "毛利率较上一有效期下降超过 5 个百分点。"),
        ("net_margin", "net_margin_decline", "净利率较上一有效期下降超过 5 个百分点。"),
        (
            "operating_margin",
            "operating_margin_decline",
            "营业利润率较上一有效期下降超过 5 个百分点。",
        ),
    ):
        latest_value, previous_value = _latest_two_values(snapshots, field)
        if (
            latest_value is not None
            and previous_value is not None
            and latest_value - previous_value
            < -float(parameter_value("financial_flags.margin_decline", 0.05))
        ):
            flags.append(_flag(code, "warn", label, period))

    for field, code, label in (
        (
            "period_expense_ratio",
            "period_expense_ratio_rise",
            "期间费用率较上一有效期上升超过 5 个百分点。",
        ),
        (
            "finance_expense_ratio",
            "finance_expense_ratio_rise",
            "财务费用率较上一有效期上升超过 3 个百分点。",
        ),
    ):
        latest_value, previous_value = _latest_two_values(snapshots, field)
        threshold = float(
            parameter_value(
                "financial_flags.finance_expense_rise"
                if field == "finance_expense_ratio"
                else "financial_flags.period_expense_rise",
                0.03 if field == "finance_expense_ratio" else 0.05,
            )
        )
        if (
            latest_value is not None
            and previous_value is not None
            and latest_value - previous_value > threshold
        ):
            flags.append(_flag(code, "warn", label, period))

    return flags


def _build_structured_data_gaps(snapshots: list[dict[str, object]]) -> list[dict[str, object]]:
    data_gaps: list[dict[str, object]] = []
    available_fields = _available_numeric_fields(snapshots)
    if "operating_cash_flow" not in available_fields:
        has_proxy = any(field in available_fields for field in OPERATING_CASH_FLOW_PROXY_FIELDS)
        _append_gap(
            data_gaps,
            field="operating_cash_flow",
            severity="medium",
            reason=(
                "缺少经营现金流绝对值；当前已有每股经营现金流或经营现金流/收入等"
                "代理口径，严格估值前需补充现金流量表绝对值或总股本复核。"
                if has_proxy
                else "缺少经营现金流绝对值，无法计算经营现金流/净利润。"
            ),
            needed_by=["analyst_view", "valuation_lab"],
            replacement_available=has_proxy,
            proxy_fields=[
                field for field in OPERATING_CASH_FLOW_PROXY_FIELDS if field in available_fields
            ],
        )

    for field, definition in STRUCTURED_GAP_DEFINITIONS.items():
        if field == "operating_cash_flow":
            continue
        if field == "income_statement":
            if not any("income_statement" in item.get("statement_types", []) for item in snapshots):
                replacement_available = _has_any(available_fields, "revenue", "net_profit")
                _append_gap(
                    data_gaps,
                    field=field,
                    severity=str(definition["severity"]),
                    reason=str(definition["reason"]),
                    needed_by=list(definition["needed_by"]),
                    replacement_available=replacement_available,
                    proxy_fields=[
                        proxy
                        for proxy in ("revenue", "net_profit", "deducted_net_profit")
                        if proxy in available_fields
                    ],
                )
            continue
        if field == "buyback_amount":
            proxy_fields = [item for item in BUYBACK_PROXY_FIELDS if item in available_fields]
            if field not in available_fields:
                _append_gap(
                    data_gaps,
                    field=field,
                    severity=str(definition["severity"]),
                    reason=str(definition["reason"]),
                    needed_by=list(definition["needed_by"]),
                    replacement_available=bool(proxy_fields),
                    proxy_fields=proxy_fields,
                )
            continue
        if field == "expense_breakdown":
            if not any(item in available_fields for item in EXPENSE_BREAKDOWN_FIELDS):
                _append_gap(
                    data_gaps,
                    field=field,
                    severity=str(definition["severity"]),
                    reason=str(definition["reason"]),
                    needed_by=list(definition["needed_by"]),
                )
            continue
        if field == "impairment_losses":
            if not any(item in available_fields for item in IMPAIRMENT_FIELDS):
                _append_gap(
                    data_gaps,
                    field=field,
                    severity=str(definition["severity"]),
                    reason=str(definition["reason"]),
                    needed_by=list(definition["needed_by"]),
                )
            continue
        if field == "non_operating_items":
            if not any(item in available_fields for item in NON_OPERATING_FIELDS):
                _append_gap(
                    data_gaps,
                    field=field,
                    severity=str(definition["severity"]),
                    reason=str(definition["reason"]),
                    needed_by=list(definition["needed_by"]),
                )
            continue
        if field not in available_fields:
            _append_gap(
                data_gaps,
                field=field,
                severity=str(definition["severity"]),
                reason=str(definition["reason"]),
                needed_by=list(definition["needed_by"]),
            )
    if not snapshots:
        _append_gap(
            data_gaps,
            field="financial_statements",
            severity="high",
            reason="缺少财务记录，无法构建财务证据包。",
            needed_by=["analyst_view", "valuation_lab"],
        )
    return data_gaps


def _build_data_quality(
    snapshots: list[dict[str, object]],
    data_gaps: list[dict[str, object]],
    cash_flow_coverage: dict[str, object],
) -> dict[str, object]:
    available_fields = _available_numeric_fields(snapshots)
    coverage_by_topic = {
        "profitability": _has_any(available_fields, "roe", "gross_margin", "net_margin"),
        "profit_structure": _has_any(
            available_fields,
            "operating_margin",
            "operating_profit_to_net_profit",
            "deducted_net_profit_to_net_profit",
        ),
        "expense_control": _has_any(
            available_fields,
            "selling_expense_ratio",
            "admin_expense_ratio",
            "r_and_d_expense_ratio",
            "finance_expense_ratio",
            "period_expense_ratio",
        ),
        "accounting_quality": _has_any(
            available_fields,
            "investment_income_to_net_profit",
            "fair_value_change_to_net_profit",
            "impairment_loss_to_net_profit",
            "non_operating_profit_to_net_profit",
            "effective_tax_rate",
        ),
        "cash_flow": _has_any(
            available_fields,
            "operating_cash_flow",
            "free_cash_flow",
            *OPERATING_CASH_FLOW_PROXY_FIELDS,
        ),
        "balance_sheet": _has_any(
            available_fields,
            "cash_and_equivalents",
            "interest_bearing_debt",
            "total_assets",
            "total_liabilities",
        ),
        "capital_allocation": _has_any(
            available_fields,
            "capital_expenditure",
            "dividend",
            "buyback_amount",
            "shares_outstanding",
        ),
        "shareholder_return": _has_any(
            available_fields, "dividend", "buyback_amount", "shares_outstanding"
        ),
        "valuation_inputs": _has_any(
            available_fields,
            "free_cash_flow",
            "net_profit",
            "cash_and_equivalents",
            "interest_bearing_debt",
            "shares_outstanding",
        ),
    }
    return {
        "structured_gaps": data_gaps,
        "coverage_by_topic": coverage_by_topic,
        "proxy_fields": cash_flow_coverage.get("proxy_fields", []),
        "confidence_penalties": [
            item for item in data_gaps if item.get("severity") in {"high", "medium"}
        ],
    }


def _build_quality_matrix(
    *,
    metrics: dict[str, object],
    trends: dict[str, object],
    cash_flow_quality: dict[str, object],
    income_statement_quality: dict[str, object],
    balance_sheet_adjustment: dict[str, object],
    capital_allocation: dict[str, object],
    valuation_readiness: dict[str, object],
) -> dict[str, object]:
    return {
        "profitability": {
            "metrics": metrics.get("profitability", {}),
            "trend": {
                "roe_stability": trends.get("roe_stability"),
                "gross_margin_stability": trends.get("gross_margin_stability"),
                "net_margin_stability": trends.get("net_margin_stability"),
            },
        },
        "profit_structure": {
            "metrics": metrics.get("profit_structure", {}),
            "trend": {
                "operating_margin_stability": trends.get("operating_margin_stability"),
                "investment_income_to_net_profit_trend": trends.get(
                    "investment_income_to_net_profit_trend"
                ),
                "impairment_loss_to_net_profit_trend": trends.get(
                    "impairment_loss_to_net_profit_trend"
                ),
                "effective_tax_rate_trend": trends.get("effective_tax_rate_trend"),
            },
        },
        "expense_control": {
            "metrics": metrics.get("expense_control", {}),
            "trend": {
                "period_expense_ratio_trend": trends.get("period_expense_ratio_trend"),
                "r_and_d_expense_ratio_trend": trends.get("r_and_d_expense_ratio_trend"),
                "finance_expense_ratio_trend": trends.get("finance_expense_ratio_trend"),
            },
        },
        "accounting_quality": income_statement_quality,
        "cash_flow": cash_flow_quality,
        "growth": {
            "metrics": metrics.get("growth_quality", {}),
            "trend": {
                "revenue_cagr_3y": trends.get("revenue_cagr_3y"),
                "net_profit_cagr_3y": trends.get("net_profit_cagr_3y"),
                "free_cash_flow_cagr_3y": trends.get("free_cash_flow_cagr_3y"),
            },
        },
        "balance_sheet": balance_sheet_adjustment,
        "capital_allocation": capital_allocation,
        "shareholder_return": metrics.get("shareholder_return", {}),
        "valuation_inputs": valuation_readiness,
    }


def _build_analyst_summary(
    *,
    latest: dict[str, object] | None,
    metrics: dict[str, object],
    flags: list[dict[str, object]],
    data_gaps: list[dict[str, object]],
    cash_flow_quality: dict[str, object],
    income_statement_quality: dict[str, object],
    balance_sheet_adjustment: dict[str, object],
    capital_allocation: dict[str, object],
) -> dict[str, object]:
    latest_fields = _fields(latest)
    return {
        "latest_period": latest["period"] if latest else None,
        "business_scale": {
            "revenue": _number_or_none(latest_fields.get("revenue")),
            "net_profit": _number_or_none(latest_fields.get("net_profit")),
            "total_assets": _number_or_none(latest_fields.get("total_assets")),
        },
        "profitability": metrics.get("profitability", {}),
        "profit_composition": income_statement_quality,
        "income_statement_quality": income_statement_quality,
        "cash_flow_quality": cash_flow_quality,
        "balance_sheet_safety": metrics.get("balance_sheet_safety", {}),
        "capital_allocation": capital_allocation,
        "shareholder_return": metrics.get("shareholder_return", {}),
        "main_flags": flags[:5],
        "main_data_gaps": data_gaps[:5],
    }


def _available_numeric_fields(snapshots: list[dict[str, object]]) -> set[str]:
    return {
        key
        for snapshot in snapshots
        for key, value in _fields(snapshot).items()
        if _number_or_none(value) is not None
    }


def _cagr(
    annual_snapshots: list[dict[str, object]],
    field: str,
    *,
    years: int,
) -> float | None:
    if len(annual_snapshots) < years + 1:
        return None
    latest_value = _number_or_none(_fields(annual_snapshots[0]).get(field))
    base_value = _number_or_none(_fields(annual_snapshots[years]).get(field))
    if latest_value is None or base_value is None or latest_value <= 0 or base_value <= 0:
        return None
    return (latest_value / base_value) ** (1 / years) - 1


def _stability(snapshots: list[dict[str, object]], field: str) -> str:
    values = [
        value
        for item in snapshots[: int(parameter_value("financial_flags.stability_periods", 5))]
        if (value := _number_or_none(_fields(item).get(field))) is not None
    ]
    if len(values) < 3:
        return "insufficient_data"
    if max(values) - min(values) <= float(parameter_value("financial_flags.stability_range", 0.05)):
        return "stable"
    return "volatile"


def _trend_direction(snapshots: list[dict[str, object]], field: str) -> str:
    latest, previous = _latest_two_values(snapshots, field)
    if latest is None or previous is None:
        return "insufficient_data"
    if previous == 0:
        return "flat" if latest == 0 else "up"
    change = (latest - previous) / abs(previous)
    threshold = float(parameter_value("financial_flags.trend_change", 0.05))
    if change > threshold:
        return "up"
    if change < -threshold:
        return "down"
    return "flat"


def _looks_like_annual_report(snapshot: dict[str, object]) -> bool:
    period = str(snapshot.get("period") or "")
    fields = _fields(snapshot)
    report_type = str(fields.get("report_type") or "")
    report_date = str(fields.get("report_date") or "")
    return (
        "年报" in period
        or period.endswith("A")
        or "年度" in report_type
        or report_date.endswith("12-31 00:00:00")
        or report_date.endswith("12-31")
    )


def _latest_two_values(
    snapshots: list[dict[str, object]], field: str
) -> tuple[float | None, float | None]:
    values = [
        value
        for item in snapshots
        if (value := _number_or_none(_fields(item).get(field))) is not None
    ]
    latest = values[0] if len(values) >= 1 else None
    previous = values[1] if len(values) >= 2 else None
    return latest, previous


def _flag(code: str, severity: str, message: str, period: str) -> dict[str, object]:
    return {
        "code": code,
        "severity": severity,
        "message": message,
        "period": period,
    }


def _fields(snapshot: dict[str, object] | None) -> dict[str, Any]:
    if not snapshot:
        return {}
    fields = snapshot.get("fields")
    return fields if isinstance(fields, dict) else {}


def _number_or_none(value: object) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        normalized = value.strip().replace(",", "")
        if not normalized:
            return None
        try:
            return float(normalized)
        except ValueError:
            return None
    return None


def _sum_known_numbers(*values: object) -> float | None:
    numbers = [_number_or_none(value) for value in values]
    known = [number for number in numbers if number is not None]
    if not known:
        return None
    return float(sum(known))


def _sum_abs_known_numbers(*values: object) -> float | None:
    numbers = [_number_or_none(value) for value in values]
    known = [abs(number) for number in numbers if number is not None]
    if not known:
        return None
    return float(sum(known))


def _subtract_optional(left: float | None, right: float | None) -> float | None:
    if left is None and right is None:
        return None
    return (left or 0.0) - (right or 0.0)


def _append_gap(
    items: list[dict[str, object]],
    *,
    field: str,
    severity: str,
    reason: str,
    needed_by: list[str],
    replacement_available: bool = False,
    proxy_fields: list[str] | None = None,
) -> None:
    if any(item.get("field") == field for item in items):
        return
    gap: dict[str, object] = {
        "field": field,
        "severity": severity,
        "reason": reason,
        "needed_by": needed_by,
        "replacement_available": replacement_available,
    }
    if proxy_fields:
        gap["proxy_fields"] = proxy_fields
    items.append(gap)


def _has_any(available_fields: set[str], *fields: str) -> bool:
    return any(field in available_fields for field in fields)
