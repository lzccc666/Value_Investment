from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from sqlalchemy import Select

from app.db.models import FinancialStatement

FACT_FIELDS = (
    "revenue",
    "gross_profit",
    "net_profit",
    "deducted_net_profit",
)
KEY_GAP_FIELDS = {
    "operating_cash_flow": "缺少经营现金流绝对值，无法计算经营现金流/净利润。",
    "capital_expenditure": "缺少资本开支，无法计算严格自由现金流。",
    "free_cash_flow": "缺少自由现金流，无法直接用于 DCF 或所有者盈余估值。",
    "interest_bearing_debt": "缺少有息负债，无法计算现金/有息负债。",
    "cash_and_equivalents": "缺少货币资金，无法判断净现金或偿债安全垫。",
    "dividend": "缺少分红总额，无法计算分红折现和分红率。",
    "buyback_amount": "缺少回购金额，无法评估股东回报中的回购贡献。",
    "shares_outstanding": "缺少总股本，无法换算每股内在价值。",
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
    ordered_statements = list(statements)
    snapshots = [_statement_snapshot(item) for item in ordered_statements]
    latest = snapshots[0] if snapshots else None
    data_gaps = _build_data_gaps(snapshots)
    trends = _build_trends(snapshots, data_gaps)

    return {
        "latest_period": latest["period"] if latest else None,
        "periods": [item["period"] for item in snapshots],
        "financial_facts": _build_facts(snapshots, latest),
        "financial_metrics": _build_metrics(latest),
        "financial_trends": trends,
        "financial_flags": _build_flags(snapshots),
        "financial_data_gaps": data_gaps,
    }


def _statement_snapshot(statement: FinancialStatement) -> dict[str, object]:
    fields = statement.fields if isinstance(statement.fields, dict) else {}
    return {
        "id": statement.id,
        "period": statement.period,
        "statement_type": statement.statement_type,
        "fields": fields,
    }


def _build_facts(
    snapshots: list[dict[str, object]],
    latest: dict[str, object] | None,
) -> dict[str, object]:
    latest_fields = _fields(latest)
    return {
        "latest": {field: _number_or_none(latest_fields.get(field)) for field in FACT_FIELDS},
        "series": {
            field: [
                {"period": item["period"], "value": value}
                for item in snapshots
                if (value := _number_or_none(_fields(item).get(field))) is not None
            ]
            for field in FACT_FIELDS
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
        "cash_quality": {
            "operating_cash_flow_to_revenue": _number_or_none(
                latest_fields.get("operating_cash_flow_to_revenue")
            ),
        },
        "growth_quality": {
            "revenue_yoy": _number_or_none(latest_fields.get("revenue_yoy")),
            "net_profit_yoy": _number_or_none(latest_fields.get("net_profit_yoy")),
        },
        "balance_sheet_safety": {
            "asset_liability_ratio": _number_or_none(
                latest_fields.get("asset_liability_ratio")
            ),
        },
        "efficiency": {
            "total_assets_turnover": _number_or_none(
                latest_fields.get("total_assets_turnover")
            ),
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
    }


def _build_trends(
    snapshots: list[dict[str, object]],
    data_gaps: list[str],
) -> dict[str, object]:
    annual_snapshots = [item for item in snapshots if _looks_like_annual_report(item)]
    trends = {
        "revenue_cagr_3y": _cagr(annual_snapshots, "revenue", years=3),
        "revenue_cagr_5y": _cagr(annual_snapshots, "revenue", years=5),
        "net_profit_cagr_3y": _cagr(annual_snapshots, "net_profit", years=3),
        "net_profit_cagr_5y": _cagr(annual_snapshots, "net_profit", years=5),
        "roe_stability": _stability(snapshots, "roe"),
        "gross_margin_stability": _stability(snapshots, "gross_margin"),
        "net_margin_stability": _stability(snapshots, "net_margin"),
    }
    if annual_snapshots and trends["revenue_cagr_3y"] is None:
        _append_unique(data_gaps, "年报收入样本不足或存在非正数，无法计算 3 年收入 CAGR。")
    if annual_snapshots and trends["net_profit_cagr_3y"] is None:
        _append_unique(data_gaps, "年报净利润样本不足或存在非正数，无法计算 3 年净利润 CAGR。")
    if not annual_snapshots and snapshots:
        _append_unique(data_gaps, "缺少可识别年报数据，CAGR 口径暂不稳定。")
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

    if revenue_yoy is not None and revenue_yoy < 0:
        flags.append(
            _flag("revenue_growth_negative", "warn", "收入同比为负，需要复核增长压力。", period)
        )
    if net_profit_yoy is not None and net_profit_yoy < 0:
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
        and net_profit_yoy - revenue_yoy < -0.10
    ):
        flags.append(
            _flag(
                "profit_growth_lags_revenue",
                "warn",
                "净利润增速明显弱于收入增速，利润质量需要复核。",
                period,
            )
        )
    if asset_liability_ratio is not None and asset_liability_ratio > 0.70:
        flags.append(
            _flag(
                "high_asset_liability_ratio",
                "risk",
                "资产负债率高于 70%，财务安全边际偏弱。",
                period,
            )
        )
    if cash_to_revenue is not None and cash_to_revenue < 0.05:
        flags.append(
            _flag(
                "low_operating_cash_flow_to_revenue",
                "warn",
                "经营现金流/收入低于 5%，收入现金含量偏弱。",
                period,
            )
        )

    for field, code, label in (
        ("gross_margin", "gross_margin_decline", "毛利率较上一有效期下降超过 5 个百分点。"),
        ("net_margin", "net_margin_decline", "净利率较上一有效期下降超过 5 个百分点。"),
    ):
        latest_value, previous_value = _latest_two_values(snapshots, field)
        if (
            latest_value is not None
            and previous_value is not None
            and latest_value - previous_value < -0.05
        ):
            flags.append(_flag(code, "warn", label, period))

    return flags


def _build_data_gaps(snapshots: list[dict[str, object]]) -> list[str]:
    data_gaps: list[str] = []
    available_fields = {
        key
        for snapshot in snapshots
        for key, value in _fields(snapshot).items()
        if _number_or_none(value) is not None
    }
    for field, message in KEY_GAP_FIELDS.items():
        if field not in available_fields:
            data_gaps.append(message)
    if not snapshots:
        data_gaps.append("缺少财务记录，无法构建财务证据包。")
    return data_gaps


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
        for item in snapshots[:5]
        if (value := _number_or_none(_fields(item).get(field))) is not None
    ]
    if len(values) < 3:
        return "insufficient_data"
    if max(values) - min(values) <= 0.05:
        return "stable"
    return "volatile"


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


def _append_unique(items: list[str], message: str) -> None:
    if message not in items:
        items.append(message)
