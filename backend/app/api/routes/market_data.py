from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.errors import market_data_http_exception
from app.data_sources.eastmoney_company_profile import CompanyProfileDataSourceError
from app.data_sources.eastmoney_market_snapshot import MarketSnapshotDataSourceError
from app.db.models import SecurityListing
from app.db.session import get_db
from app.market_data.contracts import MarketDataError
from app.schemas.company import (
    CompanyRead,
    MarketSnapshotLatestResponse,
    MarketSnapshotRead,
    SecurityListingRead,
)
from app.services.companies import (
    get_latest_market_snapshot,
    get_listing,
    refresh_listing_market_snapshot,
    refresh_listing_profile,
    set_primary_listing,
)

router = APIRouter(prefix="/listings")


@router.post("/{listing_id}/profile/refresh", response_model=CompanyRead)
def refresh_listing_profile_data(
    listing_id: int, db: Annotated[Session, Depends(get_db)]
) -> CompanyRead:
    listing = _get_listing_or_404(db, listing_id)
    try:
        company, _ = refresh_listing_profile(db, listing)
        return company
    except MarketDataError as exc:
        raise market_data_http_exception(exc) from exc
    except CompanyProfileDataSourceError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc


@router.post("/{listing_id}/market-snapshots/refresh", response_model=MarketSnapshotRead)
def refresh_listing_market_snapshot_data(
    listing_id: int, db: Annotated[Session, Depends(get_db)]
) -> MarketSnapshotRead:
    listing = _get_listing_or_404(db, listing_id)
    try:
        return refresh_listing_market_snapshot(db, listing)
    except MarketDataError as exc:
        raise market_data_http_exception(exc) from exc
    except MarketSnapshotDataSourceError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc


@router.get("/{listing_id}/market-snapshots/latest", response_model=MarketSnapshotLatestResponse)
def get_listing_latest_market_snapshot(
    listing_id: int, db: Annotated[Session, Depends(get_db)]
) -> MarketSnapshotLatestResponse:
    _get_listing_or_404(db, listing_id)
    return MarketSnapshotLatestResponse(
        listing_id=listing_id,
        item=get_latest_market_snapshot(db, listing_id),
    )


@router.post("/{listing_id}/primary", response_model=SecurityListingRead)
def set_listing_as_primary(
    listing_id: int, db: Annotated[Session, Depends(get_db)]
) -> SecurityListingRead:
    listing = _get_listing_or_404(db, listing_id)
    company = listing.company
    try:
        return set_primary_listing(db, company, listing)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


def _get_listing_or_404(db: Session, listing_id: int) -> SecurityListing:
    listing = get_listing(db, listing_id)
    if listing is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Listing not found")
    return listing
