from __future__ import annotations

from dataclasses import dataclass
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


class EastmoneyFinancialClient:
    api_url = "https://datacenter.eastmoney.com/securities/api/data/get"
    source_name = "eastmoney_f10_main_finance"

    def __init__(self, timeout: float = 12.0) -> None:
        self._timeout = timeout

    def fetch_main_financials(
        self, secucode: str, limit: int = 60
    ) -> list[FetchedFinancialStatement]:
        normalized_secucode = secucode.strip().upper()
        params = {
            "type": "RPT_F10_FINANCE_MAINFINADATA",
            "sty": "APP_F10_MAINFINADATA",
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
            _map_eastmoney_row(row, self.source_name, str(response.url))
            for row in raw_items
            if isinstance(row, dict)
        ]


def _map_eastmoney_row(
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
        "operating_cash_flow_to_revenue": _percent_to_ratio(row.get("JYXJLYYSR")),
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


def _percent_to_ratio(value: object) -> float | None:
    number = _number_or_none(value)
    if number is None:
        return None
    return round(number / 100, 10)
