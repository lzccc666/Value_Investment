from datetime import UTC, date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.data_sources.ecb_fx import EcbReferenceRateProvider
from app.db.models import FxRateSnapshot
from app.market_data.contracts import FxRateProvider, MarketDataValidationError


def refresh_fx_rate(
    session: Session,
    *,
    base_currency: str,
    quote_currency: str,
    rate_date: date | None = None,
    provider: FxRateProvider | None = None,
) -> FxRateSnapshot:
    base = base_currency.strip().upper()
    quote = quote_currency.strip().upper()
    if base == quote:
        raise MarketDataValidationError("同币种汇率固定为 1，不创建或伪造 FX 快照。")
    fetched = (provider or EcbReferenceRateProvider()).fetch_rate(
        base, quote, rate_date=rate_date
    )
    existing = session.scalar(
        select(FxRateSnapshot).where(
            FxRateSnapshot.base_currency == fetched.base_currency,
            FxRateSnapshot.quote_currency == fetched.quote_currency,
            FxRateSnapshot.rate_date == fetched.rate_date,
            FxRateSnapshot.source == fetched.source,
        )
    )
    if existing is not None:
        return existing
    snapshot = FxRateSnapshot(
        base_currency=fetched.base_currency,
        quote_currency=fetched.quote_currency,
        rate=fetched.rate,
        rate_date=fetched.rate_date,
        fetched_at=datetime.now(UTC),
        source=fetched.source,
        source_url=fetched.source_url,
        raw_snapshot_hash=fetched.raw_snapshot_hash,
        calculation_audit=fetched.calculation_audit,
    )
    session.add(snapshot)
    session.commit()
    session.refresh(snapshot)
    return snapshot


def get_latest_fx_rate(
    session: Session, *, base_currency: str, quote_currency: str
) -> FxRateSnapshot | None:
    return session.scalar(
        select(FxRateSnapshot)
        .where(
            FxRateSnapshot.base_currency == base_currency.strip().upper(),
            FxRateSnapshot.quote_currency == quote_currency.strip().upper(),
        )
        .order_by(FxRateSnapshot.rate_date.desc(), FxRateSnapshot.id.desc())
        .limit(1)
    )
