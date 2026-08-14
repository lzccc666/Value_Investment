from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any

import httpx

SHANGHAI_TZ = timezone(timedelta(hours=8), "Asia/Shanghai")


class MarketSnapshotDataSourceError(RuntimeError):
    """Raised when a market snapshot source cannot return usable data."""


class UnsupportedMarketSnapshotSourceError(MarketSnapshotDataSourceError):
    """Raised when the current ticker cannot be queried by this source."""


@dataclass(frozen=True)
class FetchedMarketSnapshot:
    market_cap: float | None
    current_price: float | None
    pe_ttm: float | None
    pe_dynamic: float | None
    pe_static: float | None
    pb_ratio: float | None
    ps_ratio: float | None
    dividend_yield_ttm: float | None
    dividend_yield_static: float | None
    source: str
    source_url: str
    fetched_at: datetime


class EastmoneyMarketSnapshotClient:
    api_urls = (
        "https://push2.eastmoney.com/api/qt/stock/get",
        "https://push2delay.eastmoney.com/api/qt/stock/get",
    )
    bonus_api_url = "https://emweb.securities.eastmoney.com/PC_HSF10/BonusFinancing/PageAjax"
    source_name = "eastmoney_quote_snapshot"
    bonus_source_name = "eastmoney_bonus_financing"

    _fields = ",".join(
        [
            "f43",
            "f57",
            "f58",
            "f116",
            "f117",
            "f162",
            "f163",
            "f164",
            "f167",
            "f173",
        ]
    )

    def __init__(
        self,
        timeout: float = 12.0,
        api_urls: tuple[str, ...] | None = None,
        now_factory: Callable[[], datetime] | None = None,
    ) -> None:
        self._timeout = timeout
        self._api_urls = api_urls or self.api_urls
        self._now_factory = now_factory or shanghai_now

    def fetch_market_snapshot(self, secucode: str) -> FetchedMarketSnapshot:
        eastmoney_secid = _to_eastmoney_secid(secucode)
        if eastmoney_secid is None:
            raise UnsupportedMarketSnapshotSourceError(
                f"东方财富行情快照暂不支持证券代码：{secucode}"
            )

        params = {
            "secid": eastmoney_secid,
            "fields": self._fields,
            "fltt": "2",
            "invt": "2",
            "ut": "fa5fd1943c7b386f172d6893dbfba10b",
        }
        response, data = self._fetch_snapshot_data(params)
        fetched_at = _as_shanghai(self._now_factory())
        market_cap = _number_or_none(data.get("f116"))
        current_price = _number_or_none(data.get("f43"))
        bonus_payload, bonus_source_url = self._fetch_bonus_data(secucode)
        dividend_yield_ttm, dividend_yield_static = _calculate_dividend_yields(
            bonus_payload,
            market_cap=market_cap,
            current_price=current_price,
            as_of=fetched_at.date(),
        )
        source = self.source_name
        source_url = str(response.url)
        if bonus_source_url and (
            dividend_yield_ttm is not None or dividend_yield_static is not None
        ):
            source = f"{self.source_name},{self.bonus_source_name}"
            source_url = f"{response.url}; {bonus_source_url}"

        return FetchedMarketSnapshot(
            market_cap=market_cap,
            current_price=current_price,
            pe_ttm=_number_or_none(data.get("f164")),
            pe_dynamic=_number_or_none(data.get("f162")),
            pe_static=_number_or_none(data.get("f163")),
            pb_ratio=_number_or_none(data.get("f167")),
            ps_ratio=_number_or_none(data.get("f173")),
            dividend_yield_ttm=dividend_yield_ttm,
            dividend_yield_static=dividend_yield_static,
            source=source,
            source_url=source_url,
            fetched_at=fetched_at,
        )

    def _fetch_snapshot_data(self, params: dict[str, str]) -> tuple[httpx.Response, dict[str, Any]]:
        errors: list[str] = []
        for api_url in self._api_urls:
            try:
                response = httpx.get(
                    api_url,
                    params=params,
                    timeout=self._timeout,
                    headers={
                        "User-Agent": "Mozilla/5.0",
                        "Referer": "https://quote.eastmoney.com/",
                    },
                )
                response.raise_for_status()
                payload = response.json()
                data = _read_payload_data(payload)
                return response, data
            except httpx.HTTPError as exc:
                errors.append(f"{api_url}: {exc}")
            except ValueError:
                errors.append(f"{api_url}: 返回非 JSON 数据")
            except MarketSnapshotDataSourceError as exc:
                errors.append(f"{api_url}: {exc}")

        detail = "；".join(errors) if errors else "没有可用行情源"
        raise MarketSnapshotDataSourceError(f"东方财富行情快照请求失败：{detail}")

    def _fetch_bonus_data(self, secucode: str) -> tuple[dict[str, Any] | None, str | None]:
        eastmoney_company_code = _to_eastmoney_company_code(secucode)
        if eastmoney_company_code is None:
            return None, None

        try:
            response = httpx.get(
                self.bonus_api_url,
                params={"code": eastmoney_company_code},
                timeout=self._timeout,
                headers={"User-Agent": "Mozilla/5.0"},
            )
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError):
            return None, None

        if not isinstance(payload, dict):
            return None, None
        return payload, str(response.url)


def shanghai_now() -> datetime:
    return datetime.now(SHANGHAI_TZ)


def _as_shanghai(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=SHANGHAI_TZ)
    return value.astimezone(SHANGHAI_TZ)


def _read_payload_data(payload: object) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise MarketSnapshotDataSourceError("东方财富行情快照数据结构异常")
    if payload.get("rc") not in (0, None):
        message = payload.get("rt") or payload.get("message") or "未知错误"
        raise MarketSnapshotDataSourceError(f"东方财富行情快照返回失败：{message}")

    data = payload.get("data")
    if not isinstance(data, dict):
        raise MarketSnapshotDataSourceError("东方财富行情快照未返回公司数据")
    return data


def _to_eastmoney_secid(secucode: str) -> str | None:
    normalized = secucode.strip().upper()
    if normalized.endswith(".SH"):
        return f"1.{normalized[:-3]}"
    if normalized.endswith(".SZ"):
        return f"0.{normalized[:-3]}"
    if normalized.endswith(".HK"):
        return f"116.{normalized[:-3]}"
    if normalized.endswith(".US"):
        return f"105.{normalized[:-3]}"
    return None


def _to_eastmoney_company_code(secucode: str) -> str | None:
    normalized = secucode.strip().upper()
    if normalized.endswith(".SH"):
        return f"SH{normalized[:-3]}"
    if normalized.endswith(".SZ"):
        return f"SZ{normalized[:-3]}"
    return None


def _calculate_dividend_yields(
    payload: dict[str, Any] | None,
    *,
    market_cap: float | None,
    current_price: float | None,
    as_of: date,
) -> tuple[float | None, float | None]:
    if payload is None:
        return None, None

    dynamic_yield = _calculate_ttm_dividend_yield(
        payload.get("fhyx"),
        current_price=current_price,
        as_of=as_of,
    )
    static_yield = _calculate_static_dividend_yield(
        payload.get("lnfhrz"),
        market_cap=market_cap,
    )
    return dynamic_yield, static_yield


def _calculate_ttm_dividend_yield(
    rows: object,
    *,
    current_price: float | None,
    as_of: date,
) -> float | None:
    if not isinstance(rows, list) or current_price is None or current_price <= 0:
        return None

    window_start = as_of - timedelta(days=365)
    cash_per_10_shares = 0.0
    for row in rows:
        if not isinstance(row, dict):
            continue
        progress = str(row.get("ASSIGN_PROGRESS") or "")
        if "实施" not in progress:
            continue
        dividend_date = (
            _date_or_none(row.get("PAY_CASH_DATE"))
            or _date_or_none(row.get("EX_DIVIDEND_DATE"))
            or _date_or_none(row.get("EQUITY_RECORD_DATE"))
            or _date_or_none(row.get("NOTICE_DATE"))
        )
        if dividend_date is None or not window_start <= dividend_date <= as_of:
            continue
        cash_per_10 = _cash_per_10_shares_or_none(row.get("IMPL_PLAN_PROFILE"))
        if cash_per_10 is not None:
            cash_per_10_shares += cash_per_10

    if cash_per_10_shares <= 0:
        return None
    return (cash_per_10_shares / 10) / current_price


def _calculate_static_dividend_yield(
    rows: object,
    *,
    market_cap: float | None,
) -> float | None:
    if not isinstance(rows, list) or market_cap is None or market_cap <= 0:
        return None

    candidates: list[tuple[int, float]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        year = _int_or_none(row.get("STATISTICS_YEAR"))
        total_dividend = _number_or_none(row.get("TOTAL_DIVIDEND"))
        if year is not None and total_dividend is not None and total_dividend > 0:
            candidates.append((year, total_dividend))

    if not candidates:
        return None
    _, total_dividend = max(candidates, key=lambda item: item[0])
    return total_dividend / market_cap


def _cash_per_10_shares_or_none(value: object) -> float | None:
    if value is None:
        return None
    text = str(value)
    if "派" not in text:
        return None
    match = re.search(r"派\s*([0-9]+(?:\.[0-9]+)?)\s*元", text)
    if match is None:
        return None
    return _number_or_none(match.group(1))


def _date_or_none(value: object) -> date | None:
    if value is None:
        return None

    text = str(value).strip()
    if not text:
        return None

    for candidate in (text[:10], text):
        try:
            return date.fromisoformat(candidate)
        except ValueError:
            pass
    return None


def _int_or_none(value: object) -> int | None:
    if value is None:
        return None
    try:
        return int(str(value).strip())
    except ValueError:
        return None


def _number_or_none(value: object) -> float | None:
    if value is None:
        return None

    if isinstance(value, str):
        normalized = value.strip()
        if normalized in {"", "-", "--"}:
            return None
        value = normalized

    try:
        number = float(value)
    except (TypeError, ValueError):
        return None

    return number
