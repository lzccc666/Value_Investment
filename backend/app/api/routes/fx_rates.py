from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.errors import market_data_http_exception
from app.db.session import get_db
from app.market_data.contracts import MarketDataError
from app.schemas.fx_rate import FxRateLatestResponse, FxRateSnapshotRead
from app.services.fx_rate_service import get_latest_fx_rate, refresh_fx_rate

router = APIRouter(prefix="/fx-rates")


@router.post("/refresh", response_model=FxRateSnapshotRead)
def refresh_reference_fx_rate(
    db: Annotated[Session, Depends(get_db)],
    base_currency: Annotated[str, Query(min_length=3, max_length=3)],
    quote_currency: Annotated[str, Query(min_length=3, max_length=3)],
    rate_date: Annotated[date | None, Query()] = None,
) -> FxRateSnapshotRead:
    try:
        return refresh_fx_rate(
            db,
            base_currency=base_currency,
            quote_currency=quote_currency,
            rate_date=rate_date,
        )
    except MarketDataError as exc:
        raise market_data_http_exception(exc) from exc


@router.get("/latest", response_model=FxRateLatestResponse)
def read_latest_reference_fx_rate(
    db: Annotated[Session, Depends(get_db)],
    base_currency: Annotated[str, Query(min_length=3, max_length=3)],
    quote_currency: Annotated[str, Query(min_length=3, max_length=3)],
) -> FxRateLatestResponse:
    base = base_currency.strip().upper()
    quote = quote_currency.strip().upper()
    return FxRateLatestResponse(
        base_currency=base,
        quote_currency=quote,
        item=get_latest_fx_rate(db, base_currency=base, quote_currency=quote),
    )
