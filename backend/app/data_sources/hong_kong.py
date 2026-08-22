from __future__ import annotations

import hashlib
import importlib
import json
import math
import re
from dataclasses import dataclass
from datetime import UTC, date, datetime
from types import ModuleType
from typing import Protocol

from app.data_sources.eastmoney_company_profile import FetchedCompanyProfile
from app.data_sources.eastmoney_financials import FetchedFinancialStatement
from app.market_data.contracts import (
    MarketContext,
    MarketDataNotConfiguredError,
    MarketDataParseError,
    MarketDataUpstreamError,
    MarketDataValidationError,
)

AKSHARE_HK_PROFILE_URL = (
    "https://emweb.securities.eastmoney.com/PC_HKF10/pages/home/index.html"
)
AKSHARE_HK_FINANCIAL_URL = (
    "https://emweb.securities.eastmoney.com/PC_HKF10/FinancialAnalysis/index"
)


class RecordFrame(Protocol):
    def to_dict(self, orient: str) -> list[dict[str, object]]: ...


class AkshareHongKongGateway(Protocol):
    def stock_hk_security_profile_em(self, *, symbol: str) -> object: ...

    def stock_hk_company_profile_em(self, *, symbol: str) -> object: ...

    def stock_financial_hk_report_em(
        self, *, stock: str, symbol: str, indicator: str
    ) -> object: ...

    def stock_financial_hk_analysis_indicator_em(
        self, *, symbol: str, indicator: str
    ) -> object: ...

    def stock_hk_dividend_payout_em(self, *, symbol: str) -> object: ...


@dataclass(frozen=True)
class FetchedDividendRecord:
    fiscal_year: str | None
    announcement_date: date | None
    plan: str
    ex_date: date | None
    payment_date: date | None
    source: str
    source_url: str
    raw_snapshot_hash: str


class AkshareHongKongIssuerProfileProvider:
    provider_name = "akshare_hk_profile"

    def __init__(self, gateway: AkshareHongKongGateway | None = None) -> None:
        self.gateway = gateway

    def fetch_profile(self, context: MarketContext) -> FetchedCompanyProfile:
        symbol = _hk_symbol(context)
        gateway = self.gateway or _load_akshare()
        try:
            security_rows = _records(gateway.stock_hk_security_profile_em(symbol=symbol))
            company_rows = _records(gateway.stock_hk_company_profile_em(symbol=symbol))
        except MarketDataNotConfiguredError:
            raise
        except Exception as exc:
            raise MarketDataUpstreamError(f"AKShare 港股档案请求失败：{exc}") from exc
        if not security_rows and not company_rows:
            raise MarketDataParseError("AKShare 港股档案没有返回记录。")
        security = security_rows[0] if security_rows else {}
        company = company_rows[0] if company_rows else {}
        chinese_name = _text(company.get("公司名称")) or _text(security.get("证券简称"))
        english_name = _text(company.get("英文名称"))
        aliases = _unique_text((context.issuer_name, chinese_name, english_name))
        fiscal_year_end = _fiscal_year_end(
            company.get("年结日") or security.get("年结日") or context.fiscal_year_end
        )
        isin = _text(
            security.get("ISIN（国际证券识别编码）")
            or security.get("ISIN(国际证券识别编码)")
            or security.get("ISIN")
        )
        external_ids = {"isin": isin} if isin else {}
        return FetchedCompanyProfile(
            listed_date=_date_value(security.get("上市日期")),
            description=_text(company.get("公司介绍")),
            source_url=f"{AKSHARE_HK_PROFILE_URL}?code={symbol}&type=web",
            legal_name=english_name or chinese_name,
            aliases=tuple(aliases),
            domicile_country=_domicile_code(company.get("注册地")),
            reporting_currency=context.reporting_currency,
            fiscal_year_end=fiscal_year_end,
            external_ids=external_ids,
        )


class AkshareHongKongFinancialProvider:
    provider_name = "akshare_hk_financials"

    def __init__(self, gateway: AkshareHongKongGateway | None = None) -> None:
        self.gateway = gateway

    def fetch_financials(
        self, context: MarketContext, *, limit: int
    ) -> list[FetchedFinancialStatement]:
        symbol = _hk_symbol(context)
        currency = (context.reporting_currency or "").strip().upper()
        if not currency or currency not in {"CNY", "HKD", "USD"}:
            raise MarketDataValidationError("港股财务同步缺少支持的发行人 reporting currency。")
        gateway = self.gateway or _load_akshare()
        try:
            statement_frames = {
                "balance_sheet": gateway.stock_financial_hk_report_em(
                    stock=symbol, symbol="资产负债表", indicator="报告期"
                ),
                "income_statement": gateway.stock_financial_hk_report_em(
                    stock=symbol, symbol="利润表", indicator="报告期"
                ),
                "cash_flow_statement": gateway.stock_financial_hk_report_em(
                    stock=symbol, symbol="现金流量表", indicator="报告期"
                ),
            }
            indicator_frame = gateway.stock_financial_hk_analysis_indicator_em(
                symbol=symbol, indicator="报告期"
            )
        except MarketDataNotConfiguredError:
            raise
        except Exception as exc:
            raise MarketDataUpstreamError(f"AKShare 港股财务请求失败：{exc}") from exc

        statements: list[FetchedFinancialStatement] = []
        for statement_type, frame in statement_frames.items():
            statements.extend(
                map_akshare_hk_statement_rows(
                    _records(frame),
                    statement_type=statement_type,
                    currency=currency,
                    symbol=symbol,
                )
            )
        statements.extend(
            map_akshare_hk_indicator_rows(
                _records(indicator_frame), currency=currency, symbol=symbol
            )
        )
        if not statements:
            raise MarketDataParseError("AKShare 港股财务没有映射出可用报表。")
        periods = sorted(
            {item.period for item in statements},
            key=_period_sort_key,
            reverse=True,
        )[: max(limit, 1)]
        selected = set(periods)
        return [item for item in statements if item.period in selected]


class AkshareHongKongDividendProvider:
    provider_name = "akshare_hk_dividend"

    def __init__(self, gateway: AkshareHongKongGateway | None = None) -> None:
        self.gateway = gateway

    def fetch_dividends(self, context: MarketContext) -> list[FetchedDividendRecord]:
        symbol = _hk_symbol(context)
        gateway = self.gateway or _load_akshare()
        try:
            rows = _records(gateway.stock_hk_dividend_payout_em(symbol=symbol))
        except MarketDataNotConfiguredError:
            raise
        except Exception as exc:
            raise MarketDataUpstreamError(f"AKShare 港股分红请求失败：{exc}") from exc
        records: list[FetchedDividendRecord] = []
        for row in rows:
            plan = _text(row.get("分红方案"))
            if not plan:
                continue
            records.append(
                FetchedDividendRecord(
                    fiscal_year=_text(row.get("财政年度")),
                    announcement_date=_date_value(row.get("最新公告日期")),
                    plan=plan,
                    ex_date=_date_value(row.get("除净日")),
                    payment_date=_date_value(row.get("发放日")),
                    source=self.provider_name,
                    source_url=f"{AKSHARE_HK_PROFILE_URL}?code={symbol}&type=web",
                    raw_snapshot_hash=_hash(row),
                )
            )
        return records


_STATEMENT_FIELD_CANDIDATES: dict[str, dict[str, tuple[str, ...]]] = {
    "income_statement": {
        "revenue": ("收入", "营业收入", "营业总收入"),
        "gross_profit": ("毛利", "毛利润"),
        "net_profit": (
            "本公司拥有人应占盈利",
            "本公司拥有人应占溢利",
            "本公司权益持有人应占盈利",
            "本公司权益持有人应占溢利",
            "母公司拥有人应占利润",
            "股东应占溢利",
            "净利润",
        ),
        "operating_profit": ("经营盈利", "营业利润", "经营利润"),
        "income_tax_expense": ("所得税开支", "所得税费用"),
        "r_and_d_expense": ("研发开支", "研发费用"),
    },
    "cash_flow_statement": {
        "operating_cash_flow": (
            "经营活动产生的现金流量净额",
            "经营业务所得现金净额",
            "经营业务产生的现金净额",
            "经营业务现金净额",
        ),
        "capital_expenditure": (
            "购买物业厂房及设备",
            "购买物业、厂房及设备",
            "购建固定资产无形资产和其他长期资产支付的现金",
        ),
        "dividend": ("已付股息", "已付股息(融资)", "分派股息", "支付股息"),
        "depreciation_and_amortization": (
            "折旧及摊销",
            "折旧与摊销",
            "加:折旧及摊销",
        ),
    },
    "balance_sheet": {
        "cash_and_equivalents": ("现金及现金等价物", "现金和现金等价物", "现金及等价物"),
        "total_assets": ("资产总额", "总资产"),
        "total_liabilities": ("负债总额", "总负债"),
        "shareholders_equity": (
            "本公司权益持有人应占权益",
            "本公司拥有人应占权益",
            "股东权益",
            "权益总额",
        ),
        "short_term_interest_bearing_debt": ("短期借款", "短期计息借款"),
        "long_term_interest_bearing_debt": ("长期借款", "长期计息借款"),
    },
}

_HK_CAPITAL_EXPENDITURE_COMPONENTS = (
    "购建固定资产",
    "购建无形资产及其他资产",
)


def map_akshare_hk_statement_rows(
    rows: list[dict[str, object]],
    *,
    statement_type: str,
    currency: str,
    symbol: str,
) -> list[FetchedFinancialStatement]:
    candidates = _STATEMENT_FIELD_CANDIDATES.get(statement_type)
    if candidates is None:
        raise MarketDataValidationError(f"未知港股报表类型：{statement_type}")
    grouped: dict[str, dict[str, object]] = {}
    for row in rows:
        period_end = _date_value(row.get("REPORT_DATE") or row.get("STD_REPORT_DATE"))
        if period_end is None:
            continue
        period_start = _date_value(row.get("START_DATE"))
        fiscal_year = _integer(row.get("FISCAL_YEAR")) or period_end.year
        period_type = _hk_period_type(
            date_type_code=row.get("DATE_TYPE_CODE"),
            period_start=period_start,
            period_end=period_end,
        )
        period = _hk_period_label(fiscal_year, period_end, period_type)
        group = grouped.setdefault(
            period,
            {
                "fields": {},
                "period_start": period_start,
                "period_end": period_end,
                "period_type": period_type,
                "fiscal_year": fiscal_year,
                "fiscal_period": _fiscal_period(period_type, period_end),
                "source_tags": {},
                "diagnostics": [],
                "capital_expenditure_components": [],
            },
        )
        name = _normalized_item_name(row.get("STD_ITEM_NAME"))
        code = _text(row.get("STD_ITEM_CODE"))
        amount = _number(row.get("AMOUNT"))
        if not name or amount is None:
            continue
        if statement_type == "cash_flow_statement" and _matches_item(
            name, _HK_CAPITAL_EXPENDITURE_COMPONENTS
        ):
            components = group["capital_expenditure_components"]
            if isinstance(components, list):
                components.append({"amount": abs(amount), "code": code, "name": name})
            continue
        for field_name, field_candidates in candidates.items():
            if not _matches_item(name, field_candidates):
                continue
            fields = group["fields"]
            if not isinstance(fields, dict):
                continue
            if field_name in fields:
                diagnostics = group["diagnostics"]
                if isinstance(diagnostics, list):
                    diagnostics.append(
                        {
                            "field": field_name,
                            "code": "duplicate_hk_item_ignored",
                            "source_tag": code or name,
                        }
                    )
                break
            fields[field_name] = (
                abs(amount)
                if field_name in {"capital_expenditure", "dividend"}
                else amount
            )
            source_tags = group["source_tags"]
            if isinstance(source_tags, dict):
                source_tags[field_name] = {"code": code, "name": name}
            break

    statements: list[FetchedFinancialStatement] = []
    for period, group in grouped.items():
        fields = dict(group["fields"]) if isinstance(group["fields"], dict) else {}
        capex_components = group.get("capital_expenditure_components")
        if (
            "capital_expenditure" not in fields
            and isinstance(capex_components, list)
            and capex_components
        ):
            fields["capital_expenditure"] = sum(
                float(component["amount"])
                for component in capex_components
                if isinstance(component, dict) and component.get("amount") is not None
            )
            source_tags = group["source_tags"]
            if isinstance(source_tags, dict):
                source_tags["capital_expenditure"] = {
                    "components": [
                        {
                            "code": component.get("code"),
                            "name": component.get("name"),
                        }
                        for component in capex_components
                        if isinstance(component, dict)
                    ]
                }
        if statement_type == "balance_sheet":
            short_debt = _number(fields.get("short_term_interest_bearing_debt"))
            long_debt = _number(fields.get("long_term_interest_bearing_debt"))
            if short_debt is not None or long_debt is not None:
                fields["interest_bearing_debt"] = (short_debt or 0.0) + (long_debt or 0.0)
        if not fields:
            continue
        period_end = group["period_end"]
        fields.update(
            {
                "report_date": period_end.isoformat() if isinstance(period_end, date) else None,
                "report_type": group["period_type"],
                "source_tags": group["source_tags"],
            }
        )
        diagnostics = tuple(group["diagnostics"]) if isinstance(group["diagnostics"], list) else ()
        if diagnostics:
            fields["mapping_diagnostics"] = list(diagnostics)
        row_snapshot = {"period": period, "statement_type": statement_type, **group}
        statements.append(
            FetchedFinancialStatement(
                period=period,
                statement_type=statement_type,
                currency=currency,
                fields=fields,
                source="akshare_hk_financial_report_em",
                source_url=f"{AKSHARE_HK_FINANCIAL_URL}?type=web&code={symbol}",
                source_record_id=f"{symbol}:{period}:{statement_type}",
                filing_type=_hk_filing_type(str(group["period_type"])),
                taxonomy="eastmoney_hk_standard_items",
                period_start=(
                    group["period_start"]
                    if isinstance(group["period_start"], date)
                    else None
                ),
                period_end=period_end if isinstance(period_end, date) else None,
                period_type=str(group["period_type"]),
                fiscal_year=int(group["fiscal_year"]),
                fiscal_period=str(group["fiscal_period"]),
                filed_at=None,
                raw_snapshot_hash=_hash(row_snapshot),
                mapping_diagnostics=diagnostics,
            )
        )
    return statements


_INDICATOR_FIELDS = {
    "OPERATE_INCOME": "revenue",
    "HOLDER_PROFIT": "net_profit",
    "BASIC_EPS": "eps",
    "ISSUED_COMMON_SHARES": "shares_outstanding",
    "HK_COMMON_SHARES": "hk_shares_outstanding",
    "ROE_AVG": "roe",
    "NET_PROFIT_RATIO": "net_margin",
    "DIVI_RATIO": "dividend_payout_ratio",
    "DIVIDEND_TTM": "dividend_per_share_ttm",
}


def map_akshare_hk_indicator_rows(
    rows: list[dict[str, object]], *, currency: str, symbol: str
) -> list[FetchedFinancialStatement]:
    statements: list[FetchedFinancialStatement] = []
    for row in rows:
        period_end = _date_value(row.get("STD_REPORT_DATE") or row.get("REPORT_DATE"))
        if period_end is None:
            continue
        period_start = _date_value(row.get("START_DATE"))
        period_type = _hk_period_type(
            date_type_code=row.get("DATE_TYPE_CODE"),
            period_start=period_start,
            period_end=period_end,
        )
        fiscal_year = _integer(row.get("FISCAL_YEAR")) or period_end.year
        period = _hk_period_label(fiscal_year, period_end, period_type)
        fields: dict[str, object] = {
            "report_date": period_end.isoformat(),
            "report_type": period_type,
        }
        source_tags: dict[str, str] = {}
        for source_field, target_field in _INDICATOR_FIELDS.items():
            value = _number(row.get(source_field))
            if value is None:
                continue
            if source_field in {"ROE_AVG", "NET_PROFIT_RATIO", "DIVI_RATIO"}:
                value = value / 100.0 if abs(value) > 1 else value
            fields[target_field] = value
            source_tags[target_field] = source_field
        if len(fields) == 2:
            continue
        fields["source_tags"] = source_tags
        statements.append(
            FetchedFinancialStatement(
                period=period,
                statement_type="main_financial_indicators",
                currency=currency,
                fields=fields,
                source="akshare_hk_analysis_indicator_em",
                source_url=f"{AKSHARE_HK_FINANCIAL_URL}?type=web&code={symbol}",
                source_record_id=f"{symbol}:{period}:main_financial_indicators",
                filing_type=_hk_filing_type(period_type),
                taxonomy="eastmoney_hk_main_indicator",
                period_start=period_start,
                period_end=period_end,
                period_type=period_type,
                fiscal_year=fiscal_year,
                fiscal_period=_fiscal_period(period_type, period_end),
                raw_snapshot_hash=_hash(row),
            )
        )
    return statements


def _load_akshare() -> ModuleType:
    try:
        return importlib.import_module("akshare")
    except ImportError as exc:
        raise MarketDataNotConfiguredError(
            "未安装固定版本 akshare==1.18.81；请重新运行 scripts/setup.ps1。"
        ) from exc


def _records(frame: object) -> list[dict[str, object]]:
    if frame is None:
        return []
    if isinstance(frame, list):
        return [dict(item) for item in frame if isinstance(item, dict)]
    to_dict = getattr(frame, "to_dict", None)
    if not callable(to_dict):
        raise MarketDataParseError("AKShare 返回值不是可转换的 DataFrame。")
    records = to_dict(orient="records")
    if not isinstance(records, list):
        raise MarketDataParseError("AKShare DataFrame 无法转换为 records。")
    return [dict(item) for item in records if isinstance(item, dict)]


def _hk_symbol(context: MarketContext) -> str:
    if context.market != "HK" or context.exchange != "HKEX":
        raise MarketDataValidationError("港股 Provider 只接受 HKEX Listing。")
    digits = "".join(character for character in context.symbol if character.isdigit())
    if not digits or len(digits) > 5:
        raise MarketDataValidationError(f"非法港股代码：{context.symbol}")
    return digits.zfill(5)


def _hk_period_type(
    *, date_type_code: object, period_start: date | None, period_end: date
) -> str:
    code = (_text(date_type_code) or "").upper()
    if code == "001":
        return "annual"
    if code == "002":
        return "half_year_ytd"
    if code in {"003", "004"}:
        return "quarterly_ytd"
    if period_start is not None:
        days = (period_end - period_start).days
        if days >= 300:
            return "annual"
        if days >= 150:
            return "half_year_ytd"
    if period_end.month == 6:
        return "half_year_ytd"
    return "quarterly_ytd"


def _hk_period_label(fiscal_year: int, period_end: date, period_type: str) -> str:
    if period_type == "annual":
        return f"{fiscal_year}FY"
    if period_type == "half_year_ytd":
        return f"{fiscal_year}H1"
    quarter = max(1, min(4, (period_end.month + 2) // 3))
    return f"{fiscal_year}Q{quarter}"


def _fiscal_period(period_type: str, period_end: date) -> str:
    if period_type == "annual":
        return "FY"
    if period_type == "half_year_ytd":
        return "H1"
    return f"Q{max(1, min(4, (period_end.month + 2) // 3))}"


def _hk_filing_type(period_type: str) -> str:
    return {
        "annual": "annual_report",
        "half_year_ytd": "interim_report",
        "quarterly_ytd": "quarterly_results",
    }.get(period_type, "financial_results")


def _matches_item(name: str, candidates: tuple[str, ...]) -> bool:
    return any(name == _normalized_item_name(candidate) for candidate in candidates)


def _normalized_item_name(value: object) -> str:
    text = _text(value) or ""
    return re.sub(r"[\s（）()，,、：:－-]", "", text)


def _fiscal_year_end(value: object) -> str | None:
    text = _text(value)
    if not text:
        return None
    match = re.search(r"(\d{1,2})\D+(\d{1,2})", text)
    if match:
        return f"{int(match.group(1)):02d}-{int(match.group(2)):02d}"
    compact = "".join(character for character in text if character.isdigit())
    if len(compact) == 4:
        return f"{compact[:2]}-{compact[2:]}"
    return None


def _domicile_code(value: object) -> str | None:
    normalized = (_text(value) or "").lower()
    for marker, code in (
        ("开曼", "KY"),
        ("cayman", "KY"),
        ("百慕大", "BM"),
        ("bermuda", "BM"),
        ("香港", "HK"),
        ("hong kong", "HK"),
        ("中国", "CN"),
        ("china", "CN"),
    ):
        if marker in normalized:
            return code
    return None


def _unique_text(values: tuple[str | None, ...]) -> list[str]:
    items: list[str] = []
    for value in values:
        normalized = _text(value)
        if normalized and normalized not in items:
            items.append(normalized)
    return items


def _period_sort_key(period: str) -> tuple[int, int]:
    year = _integer(period[:4]) or 0
    suffix = period[4:].upper()
    rank = {"FY": 4, "Q4": 4, "Q3": 3, "H1": 2, "Q2": 2, "Q1": 1}.get(suffix, 0)
    return year, rank


def _date_value(value: object) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = _text(value)
    if not text:
        return None
    normalized = text[:10].replace("/", "-")
    try:
        return date.fromisoformat(normalized)
    except ValueError:
        for pattern in ("%d-%m-%Y", "%d %B %Y"):
            try:
                return datetime.strptime(normalized, pattern).replace(tzinfo=UTC).date()
            except ValueError:
                continue
    return None


def _number(value: object) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        number = float(value)
        return None if math.isnan(number) or math.isinf(number) else number
    text = str(value).strip().replace(",", "")
    if not text or text in {"-", "--", "nan", "None"}:
        return None
    try:
        number = float(text)
    except ValueError:
        return None
    return None if math.isnan(number) or math.isinf(number) else number


def _integer(value: object) -> int | None:
    number = _number(value)
    return int(number) if number is not None else None


def _text(value: object) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    if not normalized or normalized.lower() in {"nan", "none"}:
        return None
    return normalized


def _hash(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()
