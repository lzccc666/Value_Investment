from __future__ import annotations

import hashlib
import json
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Protocol

import httpx

from app.core.config import settings
from app.data_sources.eastmoney_announcements import FetchedAnnouncement
from app.data_sources.eastmoney_company_profile import FetchedCompanyProfile
from app.data_sources.eastmoney_financials import FetchedFinancialStatement
from app.market_data.contracts import (
    MarketContext,
    MarketDataNotConfiguredError,
    MarketDataParseError,
    MarketDataRateLimitedError,
    MarketDataUpstreamError,
    MarketDataValidationError,
)

SEC_DATA_BASE_URL = "https://data.sec.gov"
SEC_ARCHIVES_BASE_URL = "https://www.sec.gov/Archives/edgar/data"
SEC_COMPANY_TICKERS_EXCHANGE_URL = (
    "https://www.sec.gov/files/company_tickers_exchange.json"
)
SUPPORTED_FILING_FORMS = {
    "10-K",
    "10-Q",
    "8-K",
    "20-F",
    "6-K",
    "DEF 14A",
}


class SecDataClient(Protocol):
    def fetch_submissions(self, cik: str) -> dict[str, object]: ...

    def fetch_companyfacts(self, cik: str) -> dict[str, object]: ...


class _SecRateLimiter:
    def __init__(self, requests_per_second: float) -> None:
        self._minimum_interval = 1.0 / min(max(requests_per_second, 0.1), 10.0)
        self._lock = threading.Lock()
        self._last_request_at = 0.0

    def wait(self) -> None:
        with self._lock:
            now = time.monotonic()
            remaining = self._minimum_interval - (now - self._last_request_at)
            if remaining > 0:
                time.sleep(remaining)
            self._last_request_at = time.monotonic()


class SecEdgarClient:
    def __init__(
        self,
        *,
        user_agent: str | None = None,
        timeout: float | None = None,
        cache_directory: Path | None = None,
        cache_ttl_seconds: int | None = None,
        requests_per_second: float | None = None,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.user_agent = (user_agent or settings.sec_user_agent or "").strip()
        if not self.user_agent or "@" not in self.user_agent:
            raise MarketDataNotConfiguredError(
                "SEC_USER_AGENT 必须包含应用名和联系邮箱，例如 "
                "ValueInvestmentResearch contact@example.com。"
            )
        self.timeout = timeout or settings.provider_timeout_seconds
        self.cache_directory = cache_directory or settings.provider_cache_directory / "sec"
        self.cache_ttl_seconds = (
            settings.sec_cache_ttl_seconds
            if cache_ttl_seconds is None
            else max(cache_ttl_seconds, 0)
        )
        self._limiter = _SecRateLimiter(requests_per_second or settings.sec_max_requests_per_second)
        self._client = httpx.Client(
            timeout=self.timeout,
            transport=transport,
            headers={
                "User-Agent": self.user_agent,
                "Accept-Encoding": "gzip, deflate",
                "Accept": "application/json, text/html;q=0.9, */*;q=0.8",
            },
        )

    def fetch_submissions(self, cik: str) -> dict[str, object]:
        return self._get_json(f"{SEC_DATA_BASE_URL}/submissions/CIK{_normalize_cik(cik)}.json")

    def fetch_companyfacts(self, cik: str) -> dict[str, object]:
        return self._get_json(
            f"{SEC_DATA_BASE_URL}/api/xbrl/companyfacts/CIK{_normalize_cik(cik)}.json"
        )

    def fetch_company_ticker_directory(self) -> dict[str, object]:
        return self._get_json(SEC_COMPANY_TICKERS_EXCHANGE_URL)

    def fetch_text(self, url: str) -> str:
        cache_path = self._cache_path(url, suffix=".txt")
        cached = self._read_text_cache(cache_path)
        if cached is not None:
            return cached
        content = self._request(url).text
        self._write_text_cache(cache_path, content)
        return content

    def _get_json(self, url: str) -> dict[str, object]:
        cache_path = self._cache_path(url)
        cached = self._read_cache(cache_path)
        if cached is not None:
            return cached
        response = self._request(url)
        try:
            payload = response.json()
        except ValueError as exc:
            raise MarketDataParseError("SEC 返回了非 JSON 数据。") from exc
        if not isinstance(payload, dict):
            raise MarketDataParseError("SEC JSON 顶层不是对象。")
        self._write_cache(cache_path, payload)
        return payload

    def _request(self, url: str) -> httpx.Response:
        errors: list[str] = []
        for attempt in range(3):
            self._limiter.wait()
            try:
                response = self._client.get(url)
            except httpx.HTTPError as exc:
                errors.append(str(exc))
                if attempt < 2:
                    time.sleep(0.25 * (2**attempt))
                    continue
                raise MarketDataUpstreamError(f"SEC 请求失败：{exc}") from exc
            if response.status_code in {403, 429}:
                errors.append(f"HTTP {response.status_code}")
                if attempt < 2:
                    time.sleep(0.5 * (2**attempt))
                    continue
                raise MarketDataRateLimitedError(
                    "SEC 返回 403/429；请核对声明 User-Agent、限速和稍后重试。"
                )
            if response.status_code >= 500 and attempt < 2:
                errors.append(f"HTTP {response.status_code}")
                time.sleep(0.25 * (2**attempt))
                continue
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                raise MarketDataUpstreamError(f"SEC 请求失败：HTTP {response.status_code}") from exc
            return response
        raise MarketDataUpstreamError("SEC 请求失败：" + "；".join(errors))

    def _cache_path(self, url: str, *, suffix: str = ".json") -> Path:
        digest = hashlib.sha256(url.encode("utf-8")).hexdigest()
        return self.cache_directory / f"{digest}{suffix}"

    def _read_cache(self, path: Path) -> dict[str, object] | None:
        if self.cache_ttl_seconds <= 0 or not path.exists():
            return None
        if time.time() - path.stat().st_mtime > self.cache_ttl_seconds:
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        return payload if isinstance(payload, dict) else None

    def _write_cache(self, path: Path, payload: dict[str, object]) -> None:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_suffix(".tmp")
            temporary.write_text(
                json.dumps(payload, ensure_ascii=False, sort_keys=True),
                encoding="utf-8",
            )
            temporary.replace(path)
        except OSError:
            return

    def _read_text_cache(self, path: Path) -> str | None:
        if self.cache_ttl_seconds <= 0 or not path.exists():
            return None
        if time.time() - path.stat().st_mtime > self.cache_ttl_seconds:
            return None
        try:
            return path.read_text(encoding="utf-8")
        except OSError:
            return None

    def _write_text_cache(self, path: Path, content: str) -> None:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_suffix(".tmp")
            temporary.write_text(content, encoding="utf-8")
            temporary.replace(path)
        except OSError:
            return


class SecIssuerProfileProvider:
    provider_name = "sec_submissions"

    def __init__(self, client: SecDataClient | None = None) -> None:
        self.client = client

    def fetch_profile(self, context: MarketContext) -> FetchedCompanyProfile:
        cik = _context_cik(context)
        client = self.client or SecEdgarClient()
        payload = client.fetch_submissions(cik)
        legal_name = _string(payload.get("name"))
        former_names = payload.get("formerNames")
        aliases = [context.issuer_name]
        if legal_name and legal_name not in aliases:
            aliases.append(legal_name)
        if isinstance(former_names, list):
            for item in former_names:
                if isinstance(item, dict):
                    name = _string(item.get("name"))
                    if name and name not in aliases:
                        aliases.append(name)
        fiscal_year_end = _format_fiscal_year_end(payload.get("fiscalYearEnd"))
        if fiscal_year_end is None:
            fiscal_year_end = _infer_fiscal_year_end(client.fetch_companyfacts(cik))
        sic_description = _string(payload.get("sicDescription"))
        description = f"SEC filer；SIC：{sic_description}" if sic_description else "SEC filer"
        return FetchedCompanyProfile(
            listed_date=None,
            description=description,
            source_url=f"{SEC_DATA_BASE_URL}/submissions/CIK{_normalize_cik(cik)}.json",
            legal_name=legal_name,
            aliases=tuple(aliases),
            domicile_country=None,
            reporting_currency=context.reporting_currency,
            fiscal_year_end=fiscal_year_end,
            external_ids={"sec_cik": _normalize_cik(cik)},
        )


class SecFinancialStatementProvider:
    provider_name = "sec_companyfacts"

    def __init__(self, client: SecDataClient | None = None) -> None:
        self.client = client

    def fetch_financials(
        self, context: MarketContext, *, limit: int
    ) -> list[FetchedFinancialStatement]:
        cik = _context_cik(context)
        if not context.reporting_currency:
            raise MarketDataValidationError("美股发行人缺少 reporting_currency。")
        payload = (self.client or SecEdgarClient()).fetch_companyfacts(cik)
        return map_sec_companyfacts(
            payload,
            cik=cik,
            limit=limit,
            currency=context.reporting_currency,
        )


class SecDisclosureProvider:
    provider_name = "sec_submissions"

    def __init__(self, client: SecDataClient | None = None) -> None:
        self.client = client

    def fetch_disclosures(
        self, context: MarketContext, *, years: int, limit: int
    ) -> list[FetchedAnnouncement]:
        cik = _context_cik(context)
        payload = (self.client or SecEdgarClient()).fetch_submissions(cik)
        return map_sec_submissions(payload, cik=cik, years=years, limit=limit)


@dataclass(frozen=True)
class _ConceptMapping:
    statement_type: str
    candidates: tuple[str, ...]
    units: tuple[str, ...]
    transform: Callable[[float], float] = float


_CONCEPT_MAPPINGS: dict[str, _ConceptMapping] = {
    "revenue": _ConceptMapping(
        "income_statement",
        (
            "RevenueFromContractWithCustomerExcludingAssessedTax",
            "SalesRevenueNet",
            "Revenues",
        ),
        ("USD",),
    ),
    "gross_profit": _ConceptMapping("income_statement", ("GrossProfit",), ("USD",)),
    "operating_cost": _ConceptMapping(
        "income_statement",
        (
            "CostOfGoodsAndServicesSold",
            "CostOfRevenue",
            "CostOfGoodsSold",
        ),
        ("USD",),
        abs,
    ),
    "net_profit": _ConceptMapping("income_statement", ("NetIncomeLoss", "ProfitLoss"), ("USD",)),
    "operating_profit": _ConceptMapping("income_statement", ("OperatingIncomeLoss",), ("USD",)),
    "income_tax_expense": _ConceptMapping(
        "income_statement", ("IncomeTaxExpenseBenefit",), ("USD",)
    ),
    "asset_impairment_loss": _ConceptMapping(
        "income_statement",
        (
            "GoodwillAndIntangibleAssetImpairment",
            "AssetImpairmentCharges",
            "GoodwillImpairmentLoss",
            "ImpairmentOfIntangibleAssetsExcludingGoodwill",
        ),
        ("USD",),
        abs,
    ),
    "non_operating_income": _ConceptMapping(
        "income_statement",
        ("NonoperatingIncomeExpense", "OtherNonoperatingIncomeExpense"),
        ("USD",),
    ),
    "r_and_d_expense": _ConceptMapping(
        "income_statement", ("ResearchAndDevelopmentExpense",), ("USD",)
    ),
    "eps": _ConceptMapping(
        "income_statement", ("EarningsPerShareDiluted", "EarningsPerShareBasic"), ("USD/shares",)
    ),
    "operating_cash_flow": _ConceptMapping(
        "cash_flow_statement", ("NetCashProvidedByUsedInOperatingActivities",), ("USD",)
    ),
    "capital_expenditure": _ConceptMapping(
        "cash_flow_statement",
        ("PaymentsToAcquirePropertyPlantAndEquipment",),
        ("USD",),
        abs,
    ),
    "dividend": _ConceptMapping(
        "cash_flow_statement",
        ("PaymentsOfDividends", "PaymentsOfDividendsCommonStock"),
        ("USD",),
        abs,
    ),
    "buyback_amount": _ConceptMapping(
        "cash_flow_statement",
        (
            "PaymentsForRepurchaseOfCommonStock",
            "PaymentsForRepurchaseOfCommonAndPreferredStock",
        ),
        ("USD",),
        abs,
    ),
    "depreciation_and_amortization": _ConceptMapping(
        "cash_flow_statement",
        (
            "DepreciationDepletionAndAmortization",
            "DepreciationDepletionAndAmortizationPropertyPlantAndEquipment",
        ),
        ("USD",),
    ),
    "cash_and_equivalents": _ConceptMapping(
        "balance_sheet",
        (
            "CashAndCashEquivalentsAtCarryingValue",
            "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
        ),
        ("USD",),
    ),
    "total_assets": _ConceptMapping("balance_sheet", ("Assets",), ("USD",)),
    "total_liabilities": _ConceptMapping("balance_sheet", ("Liabilities",), ("USD",)),
    "shareholders_equity": _ConceptMapping(
        "balance_sheet",
        (
            "StockholdersEquity",
            "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
        ),
        ("USD",),
    ),
    "short_term_interest_bearing_debt": _ConceptMapping(
        "balance_sheet", ("ShortTermBorrowings", "LongTermDebtCurrent"), ("USD",)
    ),
    "long_term_interest_bearing_debt": _ConceptMapping(
        "balance_sheet", ("LongTermDebtNoncurrent",), ("USD",)
    ),
    "shares_outstanding": _ConceptMapping(
        "balance_sheet",
        ("EntityCommonStockSharesOutstanding", "CommonStockSharesOutstanding"),
        ("shares",),
    ),
}


def map_sec_companyfacts(
    payload: dict[str, object], *, cik: str, limit: int = 60, currency: str = "USD"
) -> list[FetchedFinancialStatement]:
    reporting_currency = currency.strip().upper()
    if not reporting_currency:
        raise MarketDataValidationError("SEC companyfacts 缺少报告币种。")
    facts = payload.get("facts")
    if not isinstance(facts, dict):
        raise MarketDataParseError("SEC companyfacts 缺少 facts 对象。")
    taxonomies = [name for name in ("us-gaap", "ifrs-full") if isinstance(facts.get(name), dict)]
    if not taxonomies:
        raise MarketDataValidationError("SEC companyfacts 没有 us-gaap 或 ifrs-full 标准事实。")

    grouped: dict[tuple[str, str], dict[str, object]] = {}
    diagnostics: dict[tuple[str, str], list[dict[str, object]]] = {}
    for standard_field, mapping in _CONCEPT_MAPPINGS.items():
        selected_periods: set[str] = set()
        for taxonomy in taxonomies:
            taxonomy_facts = facts[taxonomy]
            if not isinstance(taxonomy_facts, dict):
                continue
            for priority, tag in enumerate(mapping.candidates):
                concept = taxonomy_facts.get(tag)
                if not isinstance(concept, dict):
                    continue
                units = concept.get("units")
                if not isinstance(units, dict):
                    continue
                entries = _concept_entries(
                    units,
                    _reporting_currency_units(mapping.units, reporting_currency),
                )
                latest_by_period = _latest_entries_by_period(entries)
                for period, entry in latest_by_period.items():
                    if period in selected_periods:
                        diagnostics.setdefault((period, mapping.statement_type), []).append(
                            {
                                "field": standard_field,
                                "code": "lower_priority_tag_ignored",
                                "tag": tag,
                                "priority": priority,
                            }
                        )
                        continue
                    value = _number(entry.get("val"))
                    if value is None:
                        continue
                    selected_periods.add(period)
                    key = (period, mapping.statement_type)
                    row = grouped.setdefault(key, _statement_seed(period, mapping.statement_type))
                    row_fields = row["fields"]
                    if isinstance(row_fields, dict):
                        row_fields[standard_field] = mapping.transform(value)
                    _apply_entry_metadata(row, entry, taxonomy=taxonomy, tag=tag)
                    if priority > 0:
                        diagnostics.setdefault(key, []).append(
                            {
                                "field": standard_field,
                                "code": "fallback_tag_used",
                                "tag": tag,
                                "priority": priority,
                            }
                        )

    _add_main_financial_indicator_rows(grouped)
    rows = sorted(
        grouped.values(),
        key=lambda item: (
            str(item.get("period_end") or ""),
            str(item.get("filed_at") or ""),
            str(item.get("statement_type") or ""),
        ),
        reverse=True,
    )
    statements: list[FetchedFinancialStatement] = []
    for row in rows[: max(limit, 1) * 4]:
        period = str(row["period"])
        statement_type = str(row["statement_type"])
        accession = str(row.get("source_record_id") or "")
        source_url = _filing_directory_url(cik, accession) if accession else SEC_DATA_BASE_URL
        statement_diagnostics = tuple(diagnostics.get((period, statement_type), []))
        fields = dict(row["fields"]) if isinstance(row.get("fields"), dict) else {}
        if statement_diagnostics:
            fields["mapping_diagnostics"] = list(statement_diagnostics)
        statements.append(
            FetchedFinancialStatement(
                period=period,
                statement_type=statement_type,
                currency=reporting_currency,
                fields=fields,
                source="sec_companyfacts",
                source_url=source_url,
                source_record_id=accession or None,
                filing_type=_string(row.get("filing_type")),
                taxonomy=_string(row.get("taxonomy")),
                period_start=_date(row.get("period_start")),
                period_end=_date(row.get("period_end")),
                period_type=_string(row.get("period_type")),
                fiscal_year=_integer(row.get("fiscal_year")),
                fiscal_period=_string(row.get("fiscal_period")),
                filed_at=_datetime(row.get("filed_at")),
                is_amendment=bool(row.get("is_amendment")),
                raw_snapshot_hash=_row_hash(row),
                mapping_diagnostics=statement_diagnostics,
            )
        )
    return statements


def _add_main_financial_indicator_rows(
    grouped: dict[tuple[str, str], dict[str, object]],
) -> None:
    periods = sorted({period for period, _ in grouped})
    for period in periods:
        source_rows = [row for (row_period, _), row in grouped.items() if row_period == period]
        if not source_rows:
            continue
        fields: dict[str, object] = {}
        for row in source_rows:
            row_fields = row.get("fields")
            if not isinstance(row_fields, dict):
                continue
            for field_name in (
                "revenue",
                "gross_profit",
                "net_profit",
                "eps",
                "operating_cash_flow",
                "shares_outstanding",
            ):
                if row_fields.get(field_name) is not None:
                    fields[field_name] = row_fields[field_name]
        if not fields:
            continue
        metadata_source = max(
            source_rows,
            key=lambda row: str(row.get("filed_at") or ""),
        )
        main_row = dict(metadata_source)
        main_row["statement_type"] = "main_financial_indicators"
        main_row["fields"] = fields
        grouped[(period, "main_financial_indicators")] = main_row


def map_sec_submissions(
    payload: dict[str, object], *, cik: str, years: int, limit: int
) -> list[FetchedAnnouncement]:
    filings = payload.get("filings")
    recent = filings.get("recent") if isinstance(filings, dict) else None
    if not isinstance(recent, dict):
        raise MarketDataParseError("SEC submissions 缺少 filings.recent。")
    accessions = recent.get("accessionNumber")
    if not isinstance(accessions, list):
        raise MarketDataParseError("SEC submissions 缺少 accessionNumber 列。")
    today = date.today()
    try:
        cutoff = today.replace(year=today.year - max(years, 1))
    except ValueError:
        cutoff = today.replace(year=today.year - max(years, 1), month=2, day=28)
    results: list[FetchedAnnouncement] = []
    for index, accession_value in enumerate(accessions):
        accession = _string(accession_value)
        form = _recent_value(recent, "form", index)
        filed = _date(_recent_value(recent, "filingDate", index))
        if not accession or not form or filed is None or filed < cutoff:
            continue
        base_form = form.removesuffix("/A")
        if base_form not in SUPPORTED_FILING_FORMS:
            continue
        primary_document = _recent_value(recent, "primaryDocument", index)
        report_date = _date(_recent_value(recent, "reportDate", index))
        source_url = _filing_document_url(cik, accession, primary_document)
        results.append(
            FetchedAnnouncement(
                title=_sec_filing_title(form, report_date=report_date, filed=filed),
                published_at=datetime.combine(filed, datetime.min.time(), tzinfo=UTC),
                category=_sec_document_type(base_form),
                source="sec_edgar",
                source_url=source_url,
                raw_url=source_url,
                source_document_id=accession,
                document_type=_sec_document_type(base_form),
                filing_form=form,
                language="en-US",
                period_end=report_date,
                content_type="text/html",
            )
        )
        if len(results) >= limit:
            break
    return results


def _concept_entries(
    units: dict[str, object], preferred_units: tuple[str, ...]
) -> list[dict[str, object]]:
    for unit in preferred_units:
        rows = units.get(unit)
        if isinstance(rows, list):
            return [
                row for row in rows if isinstance(row, dict) and _supported_form(row.get("form"))
            ]
    return []


def _reporting_currency_units(units: tuple[str, ...], reporting_currency: str) -> tuple[str, ...]:
    return tuple(
        reporting_currency + unit.removeprefix("USD") if unit.startswith("USD") else unit
        for unit in units
    )


def _infer_fiscal_year_end(payload: dict[str, object]) -> str | None:
    facts = payload.get("facts")
    if not isinstance(facts, dict):
        return None
    annual_ends: list[date] = []
    for taxonomy_name in ("us-gaap", "ifrs-full"):
        taxonomy = facts.get(taxonomy_name)
        if not isinstance(taxonomy, dict):
            continue
        for tag in ("Assets", "Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax"):
            concept = taxonomy.get(tag)
            units = concept.get("units") if isinstance(concept, dict) else None
            if not isinstance(units, dict):
                continue
            for entries in units.values():
                if not isinstance(entries, list):
                    continue
                for entry in entries:
                    if not isinstance(entry, dict):
                        continue
                    form = _string(entry.get("form")) or ""
                    if form.removesuffix("/A") not in {"10-K", "20-F"}:
                        continue
                    if _string(entry.get("fp")) != "FY":
                        continue
                    period_end = _date(entry.get("end"))
                    if period_end is not None:
                        annual_ends.append(period_end)
    if not annual_ends:
        return None
    latest = max(annual_ends)
    return f"{latest.month:02d}-{latest.day:02d}"


def _latest_entries_by_period(entries: list[dict[str, object]]) -> dict[str, dict[str, object]]:
    selected: dict[str, dict[str, object]] = {}
    for entry in entries:
        period = _period_label(entry)
        if period is None:
            continue
        existing = selected.get(period)
        if existing is None or _entry_sort_key(entry) > _entry_sort_key(existing):
            selected[period] = entry
    return selected


def _entry_sort_key(entry: dict[str, object]) -> tuple[int, int, int, str, int]:
    form = _string(entry.get("form")) or ""
    period_end = _date(entry.get("end"))
    filed_at = _date(entry.get("filed"))
    period_start = _date(entry.get("start"))
    return (
        period_end.toordinal() if period_end else 0,
        filed_at.toordinal() if filed_at else 0,
        1 if form.endswith("/A") else 0,
        _string(entry.get("accn")) or "",
        -period_start.toordinal() if period_start else 0,
    )


def _period_label(entry: dict[str, object]) -> str | None:
    fiscal_year = _integer(entry.get("fy"))
    fiscal_period = _string(entry.get("fp"))
    end = _date(entry.get("end"))
    if fiscal_year and fiscal_period:
        return f"{fiscal_year}{fiscal_period}"
    return end.isoformat() if end else None


def _statement_seed(period: str, statement_type: str) -> dict[str, object]:
    return {"period": period, "statement_type": statement_type, "fields": {}}


def _apply_entry_metadata(
    row: dict[str, object], entry: dict[str, object], *, taxonomy: str, tag: str
) -> None:
    form = _string(entry.get("form")) or ""
    end = _date(entry.get("end"))
    row.update(
        {
            "source_record_id": _string(entry.get("accn")),
            "filing_type": form,
            "taxonomy": taxonomy,
            "period_start": _date(entry.get("start")),
            "period_end": end,
            "period_type": _sec_period_type(form),
            "fiscal_year": _integer(entry.get("fy")),
            "fiscal_period": _string(entry.get("fp")),
            "filed_at": _datetime(entry.get("filed")),
            "is_amendment": form.endswith("/A"),
        }
    )
    fields = row.get("fields")
    if isinstance(fields, dict):
        fields["report_date"] = end.isoformat() if end else None
        fields["report_type"] = form
        fields["notice_date"] = _string(entry.get("filed"))
        fields.setdefault("source_tags", {})[tag] = taxonomy


def _supported_form(value: object) -> bool:
    form = _string(value)
    return bool(form and form.removesuffix("/A") in {"10-K", "10-Q", "20-F", "6-K"})


def _sec_period_type(form: str) -> str:
    base_form = form.removesuffix("/A")
    if base_form in {"10-K", "20-F"}:
        return "annual"
    if base_form in {"10-Q", "6-K"}:
        return "quarterly_ytd"
    return "event"


def _sec_document_type(form: str) -> str:
    return {
        "10-K": "annual_report",
        "10-Q": "quarterly_report",
        "20-F": "annual_report",
        "6-K": "foreign_issuer_report",
        "8-K": "material_event",
        "DEF 14A": "governance",
    }.get(form, "other")


def _sec_filing_title(form: str, *, report_date: date | None, filed: date) -> str:
    base_form = form.removesuffix("/A")
    label = {
        "10-K": "年度报告",
        "10-Q": "季度报告",
        "20-F": "境外发行人年度报告",
        "6-K": "境外发行人临时报告",
        "8-K": "重大事项报告",
        "DEF 14A": "股东大会委托书",
    }.get(base_form, "SEC 披露文件")
    amendment = "修订版" if form.endswith("/A") else ""
    date_label = "报告期截至" if report_date else "披露于"
    relevant_date = report_date or filed
    return f"{label}{amendment}（{form}） · {date_label} {relevant_date.isoformat()}"


def _context_cik(context: MarketContext) -> str:
    cik = context.provider_identifiers.get("sec_cik")
    if not cik:
        raise MarketDataValidationError("美股 Listing 缺少 SEC CIK provider identifier。")
    return _normalize_cik(str(cik))


def _normalize_cik(value: str) -> str:
    digits = "".join(character for character in value if character.isdigit())
    if not digits or len(digits) > 10:
        raise MarketDataValidationError(f"非法 SEC CIK：{value}")
    return digits.zfill(10)


def _format_fiscal_year_end(value: object) -> str | None:
    normalized = _string(value)
    if normalized and len(normalized) == 4 and normalized.isdigit():
        return f"{normalized[:2]}-{normalized[2:]}"
    return None


def _filing_directory_url(cik: str, accession: str) -> str:
    return f"{SEC_ARCHIVES_BASE_URL}/{int(_normalize_cik(cik))}/{accession.replace('-', '')}/"


def _filing_document_url(cik: str, accession: str, document: str | None) -> str:
    directory = _filing_directory_url(cik, accession)
    return f"{directory}{document}" if document else directory


def _recent_value(recent: dict[str, object], key: str, index: int) -> str | None:
    values = recent.get(key)
    if not isinstance(values, list) or index >= len(values):
        return None
    return _string(values[index])


def _row_hash(row: dict[str, object]) -> str:
    return hashlib.sha256(
        json.dumps(row, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()


def _string(value: object) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return float(value)


def _integer(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None


def _date(value: object) -> date | None:
    normalized = _string(value)
    if not normalized:
        return None
    try:
        return date.fromisoformat(normalized[:10])
    except ValueError:
        return None


def _datetime(value: object) -> datetime | None:
    parsed = _date(value)
    return datetime.combine(parsed, datetime.min.time(), tzinfo=UTC) if parsed else None
