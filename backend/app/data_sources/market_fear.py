from __future__ import annotations

import csv
import hashlib
import io
import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation

import httpx

CBOE_VIX_URL = "https://cdn.cboe.com/api/global/us_indices/daily_prices/VIX_History.csv"
HANG_SENG_VHSI_URL = (
    "https://www.hsi.com.hk/data/eng/indexes/01050.00/chart.json"
)
AKSHARE_QVIX_DOCS_URL = "https://akshare.akfamily.xyz/data/index/index.html"


class MarketFearDataSourceError(RuntimeError):
    pass


@dataclass(frozen=True)
class FearObservation:
    data_date: date
    close: Decimal


@dataclass(frozen=True)
class FetchedFearSeries:
    market: str
    indicator_code: str
    indicator_name: str
    source: str
    source_url: str
    observations: tuple[FearObservation, ...]
    raw_snapshot_hash: str


class CboeVixProvider:
    provider_name = "cboe_vix_history"

    def __init__(
        self,
        *,
        transport: httpx.BaseTransport | None = None,
        timeout_seconds: float = 20.0,
    ) -> None:
        self.transport = transport
        self.timeout_seconds = timeout_seconds

    def fetch_history(self) -> FetchedFearSeries:
        raw = _get_text(
            CBOE_VIX_URL,
            transport=self.transport,
            timeout_seconds=self.timeout_seconds,
        )
        try:
            reader = csv.DictReader(io.StringIO(raw.lstrip("\ufeff")))
            observations = [
                FearObservation(
                    data_date=datetime.strptime(row["DATE"].strip(), "%m/%d/%Y").date(),
                    close=_positive_decimal(row["CLOSE"]),
                )
                for row in reader
                if row.get("DATE") and row.get("CLOSE")
            ]
        except (KeyError, TypeError, ValueError) as exc:
            raise MarketFearDataSourceError("Cboe VIX 历史 CSV 结构无法解析。") from exc
        return _series(
            market="US",
            indicator_code="VIX",
            indicator_name="Cboe VIX",
            source=self.provider_name,
            source_url=CBOE_VIX_URL,
            observations=observations,
            raw_payload=raw.encode("utf-8"),
        )


class HangSengVhsiProvider:
    provider_name = "hang_seng_indexes_vhsi"

    def __init__(
        self,
        *,
        transport: httpx.BaseTransport | None = None,
        timeout_seconds: float = 20.0,
    ) -> None:
        self.transport = transport
        self.timeout_seconds = timeout_seconds

    def fetch_history(self) -> FetchedFearSeries:
        raw = _get_text(
            HANG_SENG_VHSI_URL,
            transport=self.transport,
            timeout_seconds=self.timeout_seconds,
        )
        try:
            payload = json.loads(raw)
            if str(payload.get("indexCode")) != "01050.00":
                raise ValueError("unexpected VHSI index code")
            observations = [
                FearObservation(
                    data_date=datetime.fromtimestamp(
                        int(point[0]) / 1000,
                        tz=UTC,
                    ).date(),
                    close=_positive_decimal(point[1]),
                )
                for point in payload["indexLevels-3y"]
                if isinstance(point, list) and len(point) >= 2
            ]
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise MarketFearDataSourceError("恒生指数公司 VHSI 图表数据无法解析。") from exc
        return _series(
            market="HK",
            indicator_code="VHSI",
            indicator_name="恒生波幅指数 VHSI",
            source=self.provider_name,
            source_url=HANG_SENG_VHSI_URL,
            observations=observations,
            raw_payload=raw.encode("utf-8"),
        )


class AkshareQvixProvider:
    provider_name = "akshare_50etf_qvix_third_party"

    def __init__(self, *, fetcher: Callable[[], object] | None = None) -> None:
        self.fetcher = fetcher

    def fetch_history(self) -> FetchedFearSeries:
        try:
            rows = self._fetch_rows()
            observations = [
                FearObservation(
                    data_date=_coerce_date(row["date"]),
                    close=_positive_decimal(row["close"]),
                )
                for row in rows
                if row.get("date") is not None and row.get("close") is not None
            ]
        except (KeyError, TypeError, ValueError, InvalidOperation) as exc:
            raise MarketFearDataSourceError("AKShare 50ETF QVIX 数据无法解析。") from exc
        normalized = [
            {"date": item.data_date.isoformat(), "close": str(item.close)}
            for item in observations
        ]
        return _series(
            market="A_SHARE",
            indicator_code="50ETF_QVIX",
            indicator_name="50ETF QVIX",
            source=self.provider_name,
            source_url=AKSHARE_QVIX_DOCS_URL,
            observations=observations,
            raw_payload=json.dumps(
                normalized,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8"),
        )

    def _fetch_rows(self) -> list[dict[str, object]]:
        if self.fetcher is not None:
            result = self.fetcher()
        else:
            import akshare as ak

            result = ak.index_option_50etf_qvix()
        if isinstance(result, list):
            return [dict(item) for item in result]
        if hasattr(result, "to_dict"):
            return [dict(item) for item in result.to_dict("records")]
        raise TypeError("QVIX provider did not return records")


def _get_text(
    url: str,
    *,
    transport: httpx.BaseTransport | None,
    timeout_seconds: float,
) -> str:
    try:
        with httpx.Client(
            transport=transport,
            timeout=timeout_seconds,
            follow_redirects=True,
            headers={"User-Agent": "ValueInvestmentWorkbench/0.1"},
        ) as client:
            response = client.get(url)
            response.raise_for_status()
            return response.text
    except httpx.HTTPError as exc:
        raise MarketFearDataSourceError(f"市场波动率数据源请求失败：{exc}") from exc


def _series(
    *,
    market: str,
    indicator_code: str,
    indicator_name: str,
    source: str,
    source_url: str,
    observations: list[FearObservation],
    raw_payload: bytes,
) -> FetchedFearSeries:
    deduplicated = {item.data_date: item for item in observations}
    ordered = tuple(deduplicated[key] for key in sorted(deduplicated))
    if len(ordered) < 20:
        raise MarketFearDataSourceError("波动率历史数据不足 20 个有效日频收盘值。")
    return FetchedFearSeries(
        market=market,
        indicator_code=indicator_code,
        indicator_name=indicator_name,
        source=source,
        source_url=source_url,
        observations=ordered,
        raw_snapshot_hash=hashlib.sha256(raw_payload).hexdigest(),
    )


def _positive_decimal(value: object) -> Decimal:
    decimal_value = Decimal(str(value).strip())
    if not decimal_value.is_finite() or decimal_value <= 0:
        raise ValueError("close must be a positive finite number")
    return decimal_value


def _coerce_date(value: object) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value).strip()[:10])
