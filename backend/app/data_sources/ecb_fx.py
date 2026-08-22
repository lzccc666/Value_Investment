from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import time
from datetime import date, timedelta
from pathlib import Path

import httpx

from app.core.config import settings
from app.market_data.contracts import (
    FetchedFxRate,
    MarketDataParseError,
    MarketDataRateLimitedError,
    MarketDataUpstreamError,
    MarketDataValidationError,
)

ECB_DATA_API_URL = "https://data-api.ecb.europa.eu/service/data/EXR"
ECB_REFERENCE_RATES_URL = (
    "https://www.ecb.europa.eu/stats/policy_and_exchange_rates/"
    "euro_reference_exchange_rates/html/index.en.html"
)
SUPPORTED_REFERENCE_CURRENCIES = frozenset({"CNY", "EUR", "HKD", "USD"})


class EcbReferenceRateProvider:
    provider_name = "ecb_reference_rates"

    def __init__(
        self,
        *,
        timeout: float | None = None,
        cache_directory: Path | None = None,
        cache_ttl_seconds: int | None = None,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.timeout = timeout or settings.provider_timeout_seconds
        self.cache_directory = cache_directory or settings.provider_cache_directory / "ecb"
        self.cache_ttl_seconds = (
            settings.ecb_cache_ttl_seconds
            if cache_ttl_seconds is None
            else max(cache_ttl_seconds, 0)
        )
        self.client = httpx.Client(
            timeout=self.timeout,
            transport=transport,
            follow_redirects=True,
            headers={"Accept": "text/csv", "User-Agent": "ValueInvestmentResearch/1.0"},
        )

    def fetch_rate(
        self,
        base_currency: str,
        quote_currency: str,
        *,
        rate_date: date | None = None,
    ) -> FetchedFxRate:
        base = _currency(base_currency)
        quote = _currency(quote_currency)
        unsupported = {base, quote}.difference(SUPPORTED_REFERENCE_CURRENCIES)
        if unsupported:
            raise MarketDataValidationError(
                f"ECB 首轮汇率不支持币种：{', '.join(sorted(unsupported))}。"
            )
        if base == quote:
            return FetchedFxRate(
                base_currency=base,
                quote_currency=quote,
                rate=1.0,
                rate_date=rate_date or date.today(),
                source="identity",
                source_url=None,
                raw_snapshot_hash=None,
                calculation_audit={"formula": "identity", "rate": 1.0},
            )

        requested = sorted({currency for currency in (base, quote) if currency != "EUR"})
        series_key = f"D.{'+'.join(requested)}.EUR.SP00.A"
        params: dict[str, str | int] = {
            "format": "csvdata",
            "detail": "dataonly",
        }
        if rate_date is None:
            params["lastNObservations"] = 10
        else:
            params["startPeriod"] = (rate_date - timedelta(days=10)).isoformat()
            params["endPeriod"] = rate_date.isoformat()
        url = f"{ECB_DATA_API_URL}/{series_key}"
        source_url = str(httpx.URL(url, params=params))
        raw_csv = self._get_csv(source_url)
        observations = _parse_observations(raw_csv, requested)
        common_date = _latest_common_date(observations, requested, on_or_before=rate_date)
        values = {
            currency: 1.0 if currency == "EUR" else observations[currency][common_date]
            for currency in (base, quote)
        }
        rate = values[quote] / values[base]
        if not math.isfinite(rate) or rate <= 0:
            raise MarketDataParseError("ECB 交叉汇率不是有效正数。")
        audit: dict[str, object] = {
            "formula": "quote_per_eur / base_per_eur",
            "base_currency": base,
            "quote_currency": quote,
            "base_per_eur": values[base],
            "quote_per_eur": values[quote],
            "common_rate_date": common_date.isoformat(),
            "series_key": series_key,
            "purpose": "information_only_reference_rate",
        }
        raw_hash = hashlib.sha256(
            (raw_csv + json.dumps(audit, sort_keys=True)).encode("utf-8")
        ).hexdigest()
        return FetchedFxRate(
            base_currency=base,
            quote_currency=quote,
            rate=rate,
            rate_date=common_date,
            source="ecb_reference_cross",
            source_url=source_url,
            raw_snapshot_hash=raw_hash,
            calculation_audit=audit,
        )

    def _get_csv(self, url: str) -> str:
        cache_path = self._cache_path(url)
        cached = self._read_cache(cache_path)
        if cached is not None:
            return cached
        errors: list[str] = []
        for attempt in range(3):
            try:
                response = self.client.get(url)
            except httpx.HTTPError as exc:
                errors.append(str(exc))
                if attempt < 2:
                    time.sleep(0.25 * (2**attempt))
                    continue
                raise MarketDataUpstreamError(f"ECB 汇率请求失败：{exc}") from exc
            if response.status_code == 429:
                errors.append("HTTP 429")
                if attempt < 2:
                    time.sleep(0.5 * (2**attempt))
                    continue
                raise MarketDataRateLimitedError("ECB 汇率接口返回 429，请稍后重试。")
            if response.status_code >= 500 and attempt < 2:
                errors.append(f"HTTP {response.status_code}")
                time.sleep(0.25 * (2**attempt))
                continue
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                raise MarketDataUpstreamError(
                    f"ECB 汇率请求失败：HTTP {response.status_code}"
                ) from exc
            content = response.text
            self._write_cache(cache_path, content)
            return content
        raise MarketDataUpstreamError("ECB 汇率请求失败：" + "；".join(errors))

    def _cache_path(self, url: str) -> Path:
        digest = hashlib.sha256(url.encode("utf-8")).hexdigest()
        return self.cache_directory / f"{digest}.csv"

    def _read_cache(self, path: Path) -> str | None:
        if self.cache_ttl_seconds <= 0 or not path.exists():
            return None
        if time.time() - path.stat().st_mtime > self.cache_ttl_seconds:
            return None
        try:
            return path.read_text(encoding="utf-8")
        except OSError:
            return None

    def _write_cache(self, path: Path, content: str) -> None:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_suffix(".tmp")
            temporary.write_text(content, encoding="utf-8")
            temporary.replace(path)
        except OSError:
            return


def _parse_observations(
    raw_csv: str, currencies: list[str]
) -> dict[str, dict[date, float]]:
    observations: dict[str, dict[date, float]] = {currency: {} for currency in currencies}
    try:
        reader = csv.DictReader(io.StringIO(raw_csv.lstrip("\ufeff")))
        for row in reader:
            currency = str(row.get("CURRENCY") or "").strip().upper()
            if currency not in observations:
                continue
            raw_period = str(row.get("TIME_PERIOD") or "").strip()
            raw_value = str(row.get("OBS_VALUE") or "").strip()
            try:
                period = date.fromisoformat(raw_period)
                value = float(raw_value)
            except ValueError:
                continue
            if math.isfinite(value) and value > 0:
                observations[currency][period] = value
    except csv.Error as exc:
        raise MarketDataParseError(f"ECB CSV 解析失败：{exc}") from exc
    missing = [currency for currency, values in observations.items() if not values]
    if missing:
        raise MarketDataParseError(f"ECB CSV 缺少币种观测：{', '.join(missing)}。")
    return observations


def _latest_common_date(
    observations: dict[str, dict[date, float]],
    currencies: list[str],
    *,
    on_or_before: date | None,
) -> date:
    common_dates: set[date] | None = None
    for currency in currencies:
        dates = set(observations[currency])
        common_dates = dates if common_dates is None else common_dates & dates
    eligible = [
        item
        for item in (common_dates or set())
        if on_or_before is None or item <= on_or_before
    ]
    if not eligible:
        raise MarketDataParseError("ECB 返回中没有两个币种的共同参考日期。")
    return max(eligible)


def _currency(value: str) -> str:
    normalized = value.strip().upper()
    if len(normalized) != 3 or not normalized.isalpha():
        raise MarketDataValidationError(f"非法 ISO 4217 币种代码：{value}")
    return normalized
