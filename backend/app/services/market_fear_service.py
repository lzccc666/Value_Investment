from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.data_sources.market_fear import (
    AkshareQvixProvider,
    CboeVixProvider,
    FetchedFearSeries,
    HangSengVhsiProvider,
)
from app.db.models import MarketFearSnapshot
from app.schemas.investment_tools import MarketFearIndicatorRead, MarketFearListResponse

MARKET_ORDER = ("A_SHARE", "HK", "US")
MARKET_METADATA = {
    "A_SHARE": {
        "indicator_code": "50ETF_QVIX",
        "indicator_name": "50ETF QVIX",
        "is_proxy": True,
        "proxy_notice": "第三方代理指标，非官方统一恐慌指数",
    },
    "HK": {
        "indicator_code": "VHSI",
        "indicator_name": "恒生波幅指数 VHSI",
        "is_proxy": False,
        "proxy_notice": None,
    },
    "US": {
        "indicator_code": "VIX",
        "indicator_name": "Cboe VIX",
        "is_proxy": False,
        "proxy_notice": None,
    },
}
DEFAULT_PROVIDERS: dict[str, FearHistoryProvider] = {
    "A_SHARE": AkshareQvixProvider(),
    "HK": HangSengVhsiProvider(),
    "US": CboeVixProvider(),
}


class FearHistoryProvider(Protocol):
    def fetch_history(self) -> FetchedFearSeries: ...


def get_market_fear(session: Session) -> MarketFearListResponse:
    items = [
        _snapshot_to_read(get_latest_market_fear_snapshot(session, market), market)
        for market in MARKET_ORDER
    ]
    return _list_response(items)


def refresh_market_fear(
    session: Session,
    *,
    market: str | None = None,
    providers: dict[str, FearHistoryProvider] | None = None,
) -> MarketFearListResponse:
    selected = MARKET_ORDER if market is None else (_normalize_market(market),)
    registry = providers or DEFAULT_PROVIDERS
    items: list[MarketFearIndicatorRead] = []
    for market_name in selected:
        provider = registry.get(market_name)
        if provider is None:
            items.append(
                _snapshot_to_read(
                    get_latest_market_fear_snapshot(session, market_name),
                    market_name,
                    refresh_error="当前市场没有已注册的恐慌指标 Provider。",
                    force_stale=True,
                )
            )
            continue
        try:
            fetched = provider.fetch_history()
            if fetched.market != market_name:
                raise ValueError("Provider 返回的市场与请求市场不一致。")
            snapshot = _persist_fear_snapshot(session, fetched)
            items.append(_snapshot_to_read(snapshot, market_name))
        except Exception as exc:
            session.rollback()
            items.append(
                _snapshot_to_read(
                    get_latest_market_fear_snapshot(session, market_name),
                    market_name,
                    refresh_error=str(exc),
                    force_stale=True,
                )
            )
    return _list_response(items)


def get_latest_market_fear_snapshot(
    session: Session,
    market: str,
) -> MarketFearSnapshot | None:
    return session.scalar(
        select(MarketFearSnapshot)
        .where(MarketFearSnapshot.market == _normalize_market(market))
        .order_by(
            MarketFearSnapshot.data_date.desc(),
            MarketFearSnapshot.fetched_at.desc(),
            MarketFearSnapshot.id.desc(),
        )
        .limit(1)
    )


def _persist_fear_snapshot(
    session: Session,
    fetched: FetchedFearSeries,
) -> MarketFearSnapshot:
    observations = list(fetched.observations)
    latest = observations[-1]
    previous = observations[-2]
    recent_20 = observations[-20:]
    cutoff = _three_year_cutoff(latest.data_date)
    three_year = [item for item in observations if item.data_date >= cutoff]
    if len(three_year) < 20:
        raise ValueError("过去 3 年有效观测不足 20 条。")
    daily_change = latest.close - previous.close
    moving_average = sum(
        (item.close for item in recent_20),
        start=Decimal("0"),
    ) / Decimal(len(recent_20))
    percentile = (
        Decimal(sum(item.close <= latest.close for item in three_year))
        / Decimal(len(three_year))
        * Decimal("100")
    )
    now = datetime.now(UTC)
    values = {
        "indicator_code": fetched.indicator_code,
        "indicator_name": fetched.indicator_name,
        "value": _quantize(latest.close, "0.000001"),
        "daily_change": _quantize(daily_change, "0.000001"),
        "moving_average_20": _quantize(moving_average, "0.000001"),
        "percentile_3y": _quantize(percentile, "0.0001"),
        "temperature_score": _quantize(percentile, "0.0001"),
        "temperature_level": _temperature_level(percentile),
        "observation_count": len(three_year),
        "fetched_at": now,
        "source_url": fetched.source_url,
        "raw_snapshot_hash": fetched.raw_snapshot_hash,
    }
    snapshot = session.scalar(
        select(MarketFearSnapshot).where(
            MarketFearSnapshot.market == fetched.market,
            MarketFearSnapshot.data_date == latest.data_date,
            MarketFearSnapshot.source == fetched.source,
        )
    )
    if snapshot is None:
        snapshot = MarketFearSnapshot(
            market=fetched.market,
            data_date=latest.data_date,
            source=fetched.source,
            **values,
        )
        session.add(snapshot)
    else:
        for field_name, value in values.items():
            setattr(snapshot, field_name, value)
    session.commit()
    session.refresh(snapshot)
    return snapshot


def _snapshot_to_read(
    snapshot: MarketFearSnapshot | None,
    market: str,
    *,
    refresh_error: str | None = None,
    force_stale: bool = False,
) -> MarketFearIndicatorRead:
    normalized = _normalize_market(market)
    metadata = MARKET_METADATA[normalized]
    if snapshot is None:
        return MarketFearIndicatorRead(
            market=normalized,
            indicator_code=str(metadata["indicator_code"]),
            indicator_name=str(metadata["indicator_name"]),
            freshness="unavailable",
            refresh_error=refresh_error,
            is_proxy=bool(metadata["is_proxy"]),
            proxy_notice=metadata["proxy_notice"],
        )
    stale = force_stale or _is_stale(snapshot)
    return MarketFearIndicatorRead(
        market=normalized,
        indicator_code=snapshot.indicator_code,
        indicator_name=snapshot.indicator_name,
        value=snapshot.value,
        data_date=snapshot.data_date,
        daily_change=snapshot.daily_change,
        moving_average_20=snapshot.moving_average_20,
        percentile_3y=snapshot.percentile_3y,
        temperature_score=snapshot.temperature_score,
        temperature_level=snapshot.temperature_level,
        source=snapshot.source,
        source_url=snapshot.source_url,
        fetched_at=_as_utc(snapshot.fetched_at),
        observation_count=snapshot.observation_count,
        freshness="stale" if stale else "fresh",
        refresh_error=refresh_error,
        is_proxy=bool(metadata["is_proxy"]),
        proxy_notice=metadata["proxy_notice"],
    )


def _list_response(items: list[MarketFearIndicatorRead]) -> MarketFearListResponse:
    available = sum(item.freshness != "unavailable" for item in items)
    fresh = sum(item.freshness == "fresh" for item in items)
    status = "success" if fresh == len(items) else "failed" if available == 0 else "partial"
    return MarketFearListResponse(status=status, items=items)


def _is_stale(snapshot: MarketFearSnapshot) -> bool:
    fetched_at = _as_utc(snapshot.fetched_at)
    return (
        datetime.now(UTC) - fetched_at > timedelta(hours=36)
        or date.today() - snapshot.data_date > timedelta(days=7)
    )


def _temperature_level(percentile: Decimal) -> str:
    if percentile < 20:
        return "平静"
    if percentile < 40:
        return "稳定"
    if percentile < 60:
        return "升温"
    if percentile < 80:
        return "恐慌"
    return "极度恐慌"


def _three_year_cutoff(value: date) -> date:
    try:
        return value.replace(year=value.year - 3)
    except ValueError:
        return value.replace(year=value.year - 3, day=28)


def _quantize(value: Decimal, quantum: str) -> Decimal:
    return value.quantize(Decimal(quantum), rounding=ROUND_HALF_UP)


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _normalize_market(market: str) -> str:
    normalized = market.strip().upper()
    if normalized not in MARKET_METADATA:
        raise ValueError("市场必须是 A_SHARE、HK 或 US。")
    return normalized
