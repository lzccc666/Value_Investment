from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import date, datetime
from typing import Any

import httpx


class FinancialDataSourceError(RuntimeError):
    """Raised when a financial data source cannot return usable data."""


@dataclass(frozen=True)
class FetchedFinancialStatement:
    period: str
    statement_type: str
    currency: str
    fields: dict[str, object]
    source: str
    source_url: str
    source_record_id: str | None = None
    filing_type: str | None = None
    taxonomy: str | None = None
    period_start: date | None = None
    period_end: date | None = None
    period_type: str | None = None
    fiscal_year: int | None = None
    fiscal_period: str | None = None
    filed_at: datetime | None = None
    unit_scale: float = 1.0
    is_amendment: bool = False
    raw_snapshot_hash: str | None = None
    mapping_diagnostics: tuple[dict[str, object], ...] = ()


class EastmoneyFinancialClient:
    api_url = "https://datacenter.eastmoney.com/securities/api/data/get"
    source_name = "eastmoney_f10_main_finance"

    def __init__(self, timeout: float = 12.0) -> None:
        self._timeout = timeout

    def fetch_main_financials(
        self, secucode: str, limit: int = 60
    ) -> list[FetchedFinancialStatement]:
        return self._fetch_statement_rows(
            secucode=secucode,
            limit=limit,
            report_type="RPT_F10_FINANCE_MAINFINADATA",
            style="APP_F10_MAINFINADATA",
            mapper=_map_eastmoney_main_finance_row,
            source_name=self.source_name,
        )

    def fetch_financials(self, secucode: str, limit: int = 60) -> list[FetchedFinancialStatement]:
        statements: list[FetchedFinancialStatement] = []
        statements.extend(self.fetch_main_financials(secucode, limit=limit))
        statements.extend(self.fetch_income_statements(secucode, limit=limit))
        statements.extend(self.fetch_cash_flow_statements(secucode, limit=limit))
        statements.extend(self.fetch_balance_sheets(secucode, limit=limit))
        return statements

    def fetch_income_statements(
        self, secucode: str, limit: int = 60
    ) -> list[FetchedFinancialStatement]:
        return self._fetch_statement_rows(
            secucode=secucode,
            limit=limit,
            report_type="RPT_F10_FINANCE_GINCOME",
            style="ALL",
            mapper=_map_eastmoney_income_statement_row,
            source_name="eastmoney_f10_income_statement",
        )

    def fetch_cash_flow_statements(
        self, secucode: str, limit: int = 60
    ) -> list[FetchedFinancialStatement]:
        return self._fetch_statement_rows(
            secucode=secucode,
            limit=limit,
            report_type="RPT_F10_FINANCE_GCASHFLOW",
            style="ALL",
            mapper=_map_eastmoney_cash_flow_row,
            source_name="eastmoney_f10_cash_flow",
        )

    def fetch_balance_sheets(
        self, secucode: str, limit: int = 60
    ) -> list[FetchedFinancialStatement]:
        return self._fetch_statement_rows(
            secucode=secucode,
            limit=limit,
            report_type="RPT_F10_FINANCE_GBALANCE",
            style="ALL",
            mapper=_map_eastmoney_balance_sheet_row,
            source_name="eastmoney_f10_balance_sheet",
        )

    def _fetch_statement_rows(
        self,
        *,
        secucode: str,
        limit: int,
        report_type: str,
        style: str,
        mapper: Callable[[dict[str, Any], str, str], FetchedFinancialStatement],
        source_name: str,
    ) -> list[FetchedFinancialStatement]:
        normalized_secucode = secucode.strip().upper()
        params = {
            "type": report_type,
            "sty": style,
            "filter": f'(SECUCODE="{normalized_secucode}")',
            "p": "1",
            "ps": str(limit),
            "sr": "-1",
            "st": "REPORT_DATE",
            "source": "HSF10",
            "client": "PC",
        }

        try:
            response = httpx.get(self.api_url, params=params, timeout=self._timeout)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise FinancialDataSourceError(f"东方财富财务数据请求失败：{exc}") from exc

        payload = response.json()
        if payload.get("success") is not True:
            message = payload.get("message") or "未知错误"
            raise FinancialDataSourceError(f"东方财富财务数据返回失败：{message}")

        raw_items = payload.get("result", {}).get("data", [])
        if not isinstance(raw_items, list):
            raise FinancialDataSourceError("东方财富财务数据结构异常")

        return [
            _with_explicit_period_contract(
                mapper(row, source_name, str(response.url)),
                raw_row=row,
            )
            for row in raw_items
            if isinstance(row, dict)
        ]


def _with_explicit_period_contract(
    statement: FetchedFinancialStatement, *, raw_row: dict[str, Any]
) -> FetchedFinancialStatement:
    report_date = _date_or_none(statement.fields.get("report_date"))
    if report_date is None:
        return statement
    report_type = str(statement.fields.get("report_type") or statement.period)
    if report_date.month == 12 and report_date.day == 31 or "年报" in report_type:
        period_type = "annual"
        fiscal_period = "FY"
    elif report_date.month == 6 and report_date.day == 30 or "中报" in report_type:
        period_type = "interim_ytd"
        fiscal_period = "H1"
    else:
        period_type = "quarterly_ytd"
        fiscal_period = {3: "Q1", 9: "Q3"}.get(report_date.month, "Q")
    source_record_id = ":".join(
        [statement.source, statement.statement_type, report_date.isoformat()]
    )
    raw_hash = hashlib.sha256(
        json.dumps(raw_row, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()
    return replace(
        statement,
        source_record_id=source_record_id,
        filing_type=report_type,
        taxonomy="eastmoney_f10",
        period_start=date(report_date.year, 1, 1),
        period_end=report_date,
        period_type=period_type,
        fiscal_year=report_date.year,
        fiscal_period=fiscal_period,
        raw_snapshot_hash=raw_hash,
    )


def _date_or_none(value: object) -> date | None:
    if value is None:
        return None
    normalized = str(value).strip()[:10]
    try:
        return date.fromisoformat(normalized)
    except ValueError:
        return None


def _map_eastmoney_main_finance_row(
    row: dict[str, Any], source_name: str, source_url: str
) -> FetchedFinancialStatement:
    report_date_name = _string_or_none(row.get("REPORT_DATE_NAME"))
    period = report_date_name or _format_period(row)
    report_type = _string_or_none(row.get("REPORT_TYPE")) or "主要财务指标"
    currency = _string_or_none(row.get("CURRENCY")) or "CNY"

    fields = {
        "report_date": _string_or_none(row.get("REPORT_DATE")),
        "report_type": report_type,
        "notice_date": _string_or_none(row.get("NOTICE_DATE")),
        "revenue": _number_or_none(row.get("TOTALOPERATEREVE")),
        "gross_profit": _number_or_none(row.get("MLR")),
        "net_profit": _number_or_none(row.get("PARENTNETPROFIT")),
        "deducted_net_profit": _number_or_none(row.get("KCFJCXSYJLR")),
        "eps": _number_or_none(row.get("EPSJB")),
        "bps": _number_or_none(row.get("BPS")),
        "roe": _percent_to_ratio(row.get("ROEJQ")),
        "gross_margin": _percent_to_ratio(row.get("XSMLL")),
        "net_margin": _percent_to_ratio(row.get("XSJLL")),
        "asset_liability_ratio": _percent_to_ratio(row.get("ZCFZL")),
        "revenue_yoy": _percent_to_ratio(row.get("TOTALOPERATEREVETZ")),
        "net_profit_yoy": _percent_to_ratio(row.get("PARENTNETPROFITTZ")),
        "operating_cash_flow_per_share": _number_or_none(row.get("MGJYXJJE")),
        "operating_cash_flow_to_revenue": _ratio_or_percent_to_ratio(row.get("JYXJLYYSR")),
        "total_assets_turnover": _number_or_none(row.get("TOAZZL")),
        "inventory_turnover_days": _number_or_none(row.get("CHZZTS")),
        "raw_secucode": _string_or_none(row.get("SECUCODE")),
        "raw_security_name": _string_or_none(row.get("SECURITY_NAME_ABBR")),
    }

    return FetchedFinancialStatement(
        period=period,
        statement_type="main_financial_indicators",
        currency=currency,
        fields={key: value for key, value in fields.items() if value is not None},
        source=source_name,
        source_url=source_url,
    )


def _map_eastmoney_income_statement_row(
    row: dict[str, Any], source_name: str, source_url: str
) -> FetchedFinancialStatement:
    period, report_type, currency = _common_period_fields(row, "利润表")
    revenue = _number_or_none(row.get("TOTAL_OPERATE_INCOME"))
    operating_cost = _number_or_none(row.get("OPERATE_COST"))
    gross_profit = (
        revenue - operating_cost if revenue is not None and operating_cost is not None else None
    )

    fields = {
        "report_date": _string_or_none(row.get("REPORT_DATE")),
        "report_type": report_type,
        "notice_date": _string_or_none(row.get("NOTICE_DATE")),
        "revenue": revenue,
        "operating_cost": operating_cost,
        "gross_profit": gross_profit,
        "taxes_and_surcharges": _number_or_none(row.get("OPERATE_TAX_ADD")),
        "selling_expense": _number_or_none(row.get("SALE_EXPENSE")),
        "admin_expense": _number_or_none(row.get("MANAGE_EXPENSE")),
        "r_and_d_expense": _coalesce_number(
            row.get("RESEARCH_EXPENSE"),
            row.get("ME_RESEARCH_EXPENSE"),
        ),
        "finance_expense": _number_or_none(row.get("FINANCE_EXPENSE")),
        "other_income": _number_or_none(row.get("OTHER_INCOME")),
        "investment_income": _number_or_none(row.get("INVEST_INCOME")),
        "fair_value_change_income": _number_or_none(row.get("FAIRVALUE_CHANGE_INCOME")),
        "credit_impairment_loss": _coalesce_number(
            row.get("CREDIT_IMPAIRMENT_LOSS"),
            row.get("CREDIT_IMPAIRMENT_INCOME"),
        ),
        "asset_impairment_loss": _coalesce_number(
            row.get("ASSET_IMPAIRMENT_LOSS"),
            row.get("ASSET_IMPAIRMENT_INCOME"),
        ),
        "operating_profit": _number_or_none(row.get("OPERATE_PROFIT")),
        "non_operating_income": _number_or_none(row.get("NONBUSINESS_INCOME")),
        "non_operating_expense": _number_or_none(row.get("NONBUSINESS_EXPENSE")),
        "total_profit": _number_or_none(row.get("TOTAL_PROFIT")),
        "income_tax_expense": _number_or_none(row.get("INCOME_TAX")),
        "net_profit": _number_or_none(row.get("NETPROFIT")),
        "parent_net_profit": _number_or_none(row.get("PARENT_NETPROFIT")),
        "minority_interest": _number_or_none(row.get("MINORITY_INTEREST")),
        "deducted_net_profit": _number_or_none(row.get("DEDUCT_PARENT_NETPROFIT")),
        "eps": _number_or_none(row.get("BASIC_EPS")),
        "raw_secucode": _string_or_none(row.get("SECUCODE")),
        "raw_security_name": _string_or_none(row.get("SECURITY_NAME_ABBR")),
    }

    return FetchedFinancialStatement(
        period=period,
        statement_type="income_statement",
        currency=currency,
        fields={key: value for key, value in fields.items() if value is not None},
        source=source_name,
        source_url=source_url,
    )


def _map_eastmoney_cash_flow_row(
    row: dict[str, Any], source_name: str, source_url: str
) -> FetchedFinancialStatement:
    period, report_type, currency = _common_period_fields(row, "现金流量表")
    operating_cash_flow = _number_or_none(row.get("NETCASH_OPERATE"))
    purchase_fixed_assets_cash_paid = _number_or_none(row.get("CONSTRUCT_LONG_ASSET"))
    capital_expenditure = (
        abs(purchase_fixed_assets_cash_paid)
        if purchase_fixed_assets_cash_paid is not None
        else None
    )
    free_cash_flow = (
        operating_cash_flow - capital_expenditure
        if operating_cash_flow is not None and capital_expenditure is not None
        else None
    )
    depreciation_and_amortization = _sum_known_numbers(
        row.get("LPE_AMORTIZE"),
        row.get("IA_AMORTIZE"),
        row.get("USERIGHT_ASSET_AMORTIZE"),
        row.get("DEFER_INCOME_AMORTIZE"),
    )
    working_capital_change = _sum_known_numbers(
        row.get("OPERATE_RECE_REDUCE"),
        row.get("INVENTORY_REDUCE"),
        row.get("OPERATE_PAYABLE_ADD"),
    )

    fields = {
        "report_date": _string_or_none(row.get("REPORT_DATE")),
        "report_type": report_type,
        "notice_date": _string_or_none(row.get("NOTICE_DATE")),
        "operating_cash_flow": operating_cash_flow,
        "purchase_fixed_assets_cash_paid": purchase_fixed_assets_cash_paid,
        "capital_expenditure": capital_expenditure,
        "free_cash_flow": free_cash_flow,
        "depreciation_and_amortization": depreciation_and_amortization,
        "working_capital_change": working_capital_change,
        "dividend": _number_or_none(row.get("ASSIGN_DIVIDEND_PORFIT")),
        "net_cash_from_investing": _number_or_none(row.get("NETCASH_INVEST")),
        "net_cash_from_financing": _number_or_none(row.get("NETCASH_FINANCE")),
        "raw_secucode": _string_or_none(row.get("SECUCODE")),
        "raw_security_name": _string_or_none(row.get("SECURITY_NAME_ABBR")),
    }

    return FetchedFinancialStatement(
        period=period,
        statement_type="cash_flow_statement",
        currency=currency,
        fields={key: value for key, value in fields.items() if value is not None},
        source=source_name,
        source_url=source_url,
    )


def _map_eastmoney_balance_sheet_row(
    row: dict[str, Any], source_name: str, source_url: str
) -> FetchedFinancialStatement:
    period, report_type, currency = _common_period_fields(row, "资产负债表")
    short_term_debt = _sum_known_numbers(
        row.get("SHORT_LOAN"),
        row.get("SHORT_BOND_PAYABLE"),
        row.get("SHORT_FIN_PAYABLE"),
        row.get("NONCURRENT_LIAB_1YEAR"),
    )
    long_term_debt = _sum_known_numbers(
        row.get("LONG_LOAN"),
        row.get("BOND_PAYABLE"),
        row.get("LEASE_LIAB"),
    )
    interest_bearing_debt = _sum_known_numbers(short_term_debt, long_term_debt)
    cash_and_equivalents = _number_or_none(row.get("MONETARYFUNDS"))
    net_cash = (
        cash_and_equivalents - interest_bearing_debt
        if cash_and_equivalents is not None and interest_bearing_debt is not None
        else None
    )

    fields = {
        "report_date": _string_or_none(row.get("REPORT_DATE")),
        "report_type": report_type,
        "notice_date": _string_or_none(row.get("NOTICE_DATE")),
        "cash_and_equivalents": cash_and_equivalents,
        "short_term_interest_bearing_debt": short_term_debt,
        "long_term_interest_bearing_debt": long_term_debt,
        "interest_bearing_debt": interest_bearing_debt,
        "net_cash": net_cash,
        "total_assets": _number_or_none(row.get("TOTAL_ASSETS")),
        "total_liabilities": _number_or_none(row.get("TOTAL_LIABILITIES")),
        "shareholders_equity": _number_or_none(row.get("TOTAL_PARENT_EQUITY")),
        "total_equity": _number_or_none(row.get("TOTAL_EQUITY")),
        "goodwill": _number_or_none(row.get("GOODWILL")),
        "receivables": _sum_known_numbers(
            row.get("ACCOUNTS_RECE"),
            row.get("NOTE_RECE"),
            row.get("OTHER_RECE"),
        ),
        "inventory": _number_or_none(row.get("INVENTORY")),
        "shares_outstanding": _number_or_none(row.get("SHARE_CAPITAL")),
        "treasury_shares": _number_or_none(row.get("TREASURY_SHARES")),
        "buyback_amount_proxy": _number_or_none(row.get("TREASURY_SHARES")),
        "dividend_payable": _number_or_none(row.get("DIVIDEND_PAYABLE")),
        "raw_secucode": _string_or_none(row.get("SECUCODE")),
        "raw_security_name": _string_or_none(row.get("SECURITY_NAME_ABBR")),
    }

    return FetchedFinancialStatement(
        period=period,
        statement_type="balance_sheet",
        currency=currency,
        fields={key: value for key, value in fields.items() if value is not None},
        source=source_name,
        source_url=source_url,
    )


def _common_period_fields(row: dict[str, Any], default_report_type: str) -> tuple[str, str, str]:
    report_date_name = _string_or_none(row.get("REPORT_DATE_NAME"))
    period = report_date_name or _format_period(row)
    report_type = _string_or_none(row.get("REPORT_TYPE")) or default_report_type
    currency = _string_or_none(row.get("CURRENCY")) or "CNY"
    return period, report_type, currency


def _format_period(row: dict[str, Any]) -> str:
    report_year = _string_or_none(row.get("REPORT_YEAR"))
    report_type = _string_or_none(row.get("REPORT_TYPE"))
    if report_year and report_type:
        return f"{report_year}{report_type}"
    if report_year:
        return report_year
    return "unknown"


def _string_or_none(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _number_or_none(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
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


def _coalesce_number(*values: object) -> float | None:
    for value in values:
        number = _number_or_none(value)
        if number is not None:
            return number
    return None


def _percent_to_ratio(value: object) -> float | None:
    number = _number_or_none(value)
    if number is None:
        return None
    return round(number / 100, 10)


def _ratio_or_percent_to_ratio(value: object) -> float | None:
    number = _number_or_none(value)
    if number is None:
        return None
    if abs(number) <= 1:
        return round(number, 10)
    return round(number / 100, 10)
