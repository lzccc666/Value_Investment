from collections.abc import Callable
from typing import Annotated, Literal, TypeVar

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.investment_tools import (
    AhListingCatalogResponse,
    AhListingImportRequest,
    BuyMemoCompanyCandidateResponse,
    BuyMemoDecisionCandidateResponse,
    BuyMemoEntryCreate,
    BuyMemoEntryListResponse,
    BuyMemoEntryRead,
    DeleteResponse,
    MarketFearListResponse,
    PortfolioHoldingCreate,
    PortfolioHoldingListResponse,
    PortfolioHoldingRead,
    PortfolioHoldingUpdate,
    PortfolioListingSearchItem,
    PortfolioListingSearchResponse,
    PortfolioOwnerCreate,
    PortfolioOwnerListResponse,
    PortfolioOwnerRead,
    PortfolioOwnerUpdate,
    PortfolioRefreshResponse,
    PortfolioReorderRequest,
    PortfolioSnapshotCreate,
    PortfolioSnapshotListResponse,
    PortfolioSnapshotRead,
    PortfolioSnapshotUpdate,
    PortfolioValuationResponse,
    SecUsListingCatalogResponse,
    SecUsListingImportRequest,
)
from app.services.buy_memo_service import (
    create_buy_memo_entry,
    delete_buy_memo_entry,
    list_buy_memo_decisions,
    list_buy_memo_entries,
    search_buy_memo_companies,
)
from app.services.market_fear_service import get_market_fear, refresh_market_fear
from app.services.portfolio_service import (
    PortfolioConflictError,
    PortfolioError,
    PortfolioNotFoundError,
    PortfolioUpstreamError,
    PortfolioValidationError,
    create_holding,
    create_owner,
    create_snapshot,
    delete_holding,
    delete_owner,
    delete_snapshot,
    get_holding,
    get_owner,
    get_snapshot,
    holding_to_read,
    import_ah_listing,
    import_sec_us_listing,
    list_holdings,
    list_owners,
    list_snapshots,
    refresh_portfolio_market_data,
    reorder_owners,
    reorder_snapshots,
    search_ah_listing_catalog,
    search_portfolio_listings,
    search_sec_us_listing_catalog,
    update_holding,
    update_owner,
    update_snapshot,
    value_portfolio,
)

router = APIRouter(prefix="/investment-tools")
T = TypeVar("T")


@router.get("/portfolio-owners", response_model=PortfolioOwnerListResponse)
def get_portfolio_owners(
    db: Annotated[Session, Depends(get_db)],
) -> PortfolioOwnerListResponse:
    items = list_owners(db)
    return PortfolioOwnerListResponse(items=items, total=len(items))


@router.post(
    "/portfolio-owners",
    response_model=PortfolioOwnerRead,
    status_code=status.HTTP_201_CREATED,
)
def post_portfolio_owner(
    payload: PortfolioOwnerCreate,
    db: Annotated[Session, Depends(get_db)],
) -> PortfolioOwnerRead:
    return _handle(lambda: create_owner(db, payload))


@router.put("/portfolio-owners/reorder", response_model=PortfolioOwnerListResponse)
def put_portfolio_owner_order(
    payload: PortfolioReorderRequest,
    db: Annotated[Session, Depends(get_db)],
) -> PortfolioOwnerListResponse:
    items = _handle(lambda: reorder_owners(db, payload.ordered_ids))
    return PortfolioOwnerListResponse(items=items, total=len(items))


@router.get("/portfolio-owners/{owner_id}", response_model=PortfolioOwnerRead)
def get_portfolio_owner(
    owner_id: int,
    db: Annotated[Session, Depends(get_db)],
) -> PortfolioOwnerRead:
    return _handle(lambda: get_owner(db, owner_id))


@router.patch("/portfolio-owners/{owner_id}", response_model=PortfolioOwnerRead)
def patch_portfolio_owner(
    owner_id: int,
    payload: PortfolioOwnerUpdate,
    db: Annotated[Session, Depends(get_db)],
) -> PortfolioOwnerRead:
    return _handle(lambda: update_owner(db, owner_id, payload))


@router.delete("/portfolio-owners/{owner_id}", response_model=DeleteResponse)
def remove_portfolio_owner(
    owner_id: int,
    db: Annotated[Session, Depends(get_db)],
) -> DeleteResponse:
    _handle(lambda: delete_owner(db, owner_id))
    return DeleteResponse(id=owner_id, deleted=True)


@router.get(
    "/portfolio-owners/{owner_id}/snapshots",
    response_model=PortfolioSnapshotListResponse,
)
def get_portfolio_snapshots(
    owner_id: int,
    db: Annotated[Session, Depends(get_db)],
) -> PortfolioSnapshotListResponse:
    items = _handle(lambda: list_snapshots(db, owner_id))
    return PortfolioSnapshotListResponse(owner_id=owner_id, items=items, total=len(items))


@router.post(
    "/portfolio-owners/{owner_id}/snapshots",
    response_model=PortfolioSnapshotRead,
    status_code=status.HTTP_201_CREATED,
)
def post_portfolio_snapshot(
    owner_id: int,
    payload: PortfolioSnapshotCreate,
    db: Annotated[Session, Depends(get_db)],
) -> PortfolioSnapshotRead:
    return _handle(lambda: create_snapshot(db, owner_id, payload))


@router.put(
    "/portfolio-owners/{owner_id}/snapshots/reorder",
    response_model=PortfolioSnapshotListResponse,
)
def put_portfolio_snapshot_order(
    owner_id: int,
    payload: PortfolioReorderRequest,
    db: Annotated[Session, Depends(get_db)],
) -> PortfolioSnapshotListResponse:
    items = _handle(lambda: reorder_snapshots(db, owner_id, payload.ordered_ids))
    return PortfolioSnapshotListResponse(owner_id=owner_id, items=items, total=len(items))


@router.get(
    "/portfolio-listings/search",
    response_model=PortfolioListingSearchResponse,
)
def get_portfolio_listing_search(
    q: Annotated[str, Query(min_length=1, max_length=120)],
    db: Annotated[Session, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
) -> PortfolioListingSearchResponse:
    items = search_portfolio_listings(db, q, limit)
    return PortfolioListingSearchResponse(items=items, total=len(items))


@router.get(
    "/portfolio-listings/ah-catalog/search",
    response_model=AhListingCatalogResponse,
)
def get_ah_listing_catalog_search(
    q: Annotated[str, Query(min_length=1, max_length=120)],
    db: Annotated[Session, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
) -> AhListingCatalogResponse:
    items = _handle(lambda: search_ah_listing_catalog(db, q, limit))
    return AhListingCatalogResponse(items=items, total=len(items))


@router.post(
    "/portfolio-listings/ah-catalog/import",
    response_model=PortfolioListingSearchItem,
    status_code=status.HTTP_201_CREATED,
)
def post_ah_listing_catalog_import(
    payload: AhListingImportRequest,
    db: Annotated[Session, Depends(get_db)],
) -> PortfolioListingSearchItem:
    return _handle(lambda: import_ah_listing(db, payload))


@router.get(
    "/portfolio-listings/us-catalog/search",
    response_model=SecUsListingCatalogResponse,
)
def get_sec_us_listing_catalog_search(
    q: Annotated[str, Query(min_length=1, max_length=120)],
    db: Annotated[Session, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
) -> SecUsListingCatalogResponse:
    items = _handle(lambda: search_sec_us_listing_catalog(db, q, limit))
    return SecUsListingCatalogResponse(items=items, total=len(items))


@router.post(
    "/portfolio-listings/us-catalog/import",
    response_model=PortfolioListingSearchItem,
    status_code=status.HTTP_201_CREATED,
)
def post_sec_us_listing_catalog_import(
    payload: SecUsListingImportRequest,
    db: Annotated[Session, Depends(get_db)],
) -> PortfolioListingSearchItem:
    return _handle(lambda: import_sec_us_listing(db, payload))


@router.get("/portfolio-snapshots/{snapshot_id}", response_model=PortfolioSnapshotRead)
def get_portfolio_snapshot(
    snapshot_id: int,
    db: Annotated[Session, Depends(get_db)],
) -> PortfolioSnapshotRead:
    return _handle(lambda: get_snapshot(db, snapshot_id))


@router.patch("/portfolio-snapshots/{snapshot_id}", response_model=PortfolioSnapshotRead)
def patch_portfolio_snapshot(
    snapshot_id: int,
    payload: PortfolioSnapshotUpdate,
    db: Annotated[Session, Depends(get_db)],
) -> PortfolioSnapshotRead:
    return _handle(lambda: update_snapshot(db, snapshot_id, payload))


@router.delete("/portfolio-snapshots/{snapshot_id}", response_model=DeleteResponse)
def remove_portfolio_snapshot(
    snapshot_id: int,
    db: Annotated[Session, Depends(get_db)],
) -> DeleteResponse:
    _handle(lambda: delete_snapshot(db, snapshot_id))
    return DeleteResponse(id=snapshot_id, deleted=True)


@router.get(
    "/portfolio-snapshots/{snapshot_id}/holdings",
    response_model=PortfolioHoldingListResponse,
)
def get_portfolio_holdings(
    snapshot_id: int,
    db: Annotated[Session, Depends(get_db)],
) -> PortfolioHoldingListResponse:
    holdings = _handle(lambda: list_holdings(db, snapshot_id))
    items = [holding_to_read(holding) for holding in holdings]
    return PortfolioHoldingListResponse(snapshot_id=snapshot_id, items=items, total=len(items))


@router.post(
    "/portfolio-snapshots/{snapshot_id}/holdings",
    response_model=PortfolioHoldingRead,
    status_code=status.HTTP_201_CREATED,
)
def post_portfolio_holding(
    snapshot_id: int,
    payload: PortfolioHoldingCreate,
    db: Annotated[Session, Depends(get_db)],
) -> PortfolioHoldingRead:
    holding = _handle(lambda: create_holding(db, snapshot_id, payload))
    return holding_to_read(holding)


@router.get("/portfolio-holdings/{holding_id}", response_model=PortfolioHoldingRead)
def get_portfolio_holding(
    holding_id: int,
    db: Annotated[Session, Depends(get_db)],
) -> PortfolioHoldingRead:
    return holding_to_read(_handle(lambda: get_holding(db, holding_id)))


@router.patch("/portfolio-holdings/{holding_id}", response_model=PortfolioHoldingRead)
def patch_portfolio_holding(
    holding_id: int,
    payload: PortfolioHoldingUpdate,
    db: Annotated[Session, Depends(get_db)],
) -> PortfolioHoldingRead:
    holding = _handle(lambda: update_holding(db, holding_id, payload))
    return holding_to_read(holding)


@router.delete("/portfolio-holdings/{holding_id}", response_model=DeleteResponse)
def remove_portfolio_holding(
    holding_id: int,
    db: Annotated[Session, Depends(get_db)],
) -> DeleteResponse:
    _handle(lambda: delete_holding(db, holding_id))
    return DeleteResponse(id=holding_id, deleted=True)


@router.get(
    "/portfolio-snapshots/{snapshot_id}/valuation",
    response_model=PortfolioValuationResponse,
)
def get_portfolio_valuation(
    snapshot_id: int,
    db: Annotated[Session, Depends(get_db)],
) -> PortfolioValuationResponse:
    return _handle(lambda: value_portfolio(db, snapshot_id))


@router.post(
    "/portfolio-snapshots/{snapshot_id}/refresh-quotes",
    response_model=PortfolioRefreshResponse,
)
def refresh_portfolio_quotes(
    snapshot_id: int,
    db: Annotated[Session, Depends(get_db)],
) -> PortfolioRefreshResponse:
    return _handle(lambda: refresh_portfolio_market_data(db, snapshot_id))


@router.get("/buy-memo-entries", response_model=BuyMemoEntryListResponse)
def get_buy_memo_entries(
    db: Annotated[Session, Depends(get_db)],
) -> BuyMemoEntryListResponse:
    items = list_buy_memo_entries(db)
    return BuyMemoEntryListResponse(items=items, total=len(items))


@router.post(
    "/buy-memo-entries",
    response_model=BuyMemoEntryRead,
    status_code=status.HTTP_201_CREATED,
)
def post_buy_memo_entry(
    payload: BuyMemoEntryCreate,
    db: Annotated[Session, Depends(get_db)],
) -> BuyMemoEntryRead:
    return _handle(lambda: create_buy_memo_entry(db, payload))


@router.delete("/buy-memo-entries/{entry_id}", response_model=DeleteResponse)
def remove_buy_memo_entry(
    entry_id: int,
    db: Annotated[Session, Depends(get_db)],
) -> DeleteResponse:
    _handle(lambda: delete_buy_memo_entry(db, entry_id))
    return DeleteResponse(id=entry_id, deleted=True)


@router.get(
    "/buy-memo-companies",
    response_model=BuyMemoCompanyCandidateResponse,
)
def get_buy_memo_company_candidates(
    db: Annotated[Session, Depends(get_db)],
    q: Annotated[str, Query(max_length=120)] = "",
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> BuyMemoCompanyCandidateResponse:
    items = search_buy_memo_companies(db, q, limit)
    return BuyMemoCompanyCandidateResponse(items=items, total=len(items))


@router.get(
    "/buy-memo-companies/{company_id}/price-decisions",
    response_model=BuyMemoDecisionCandidateResponse,
)
def get_buy_memo_decision_candidates(
    company_id: int,
    db: Annotated[Session, Depends(get_db)],
) -> BuyMemoDecisionCandidateResponse:
    items = _handle(lambda: list_buy_memo_decisions(db, company_id))
    return BuyMemoDecisionCandidateResponse(
        company_id=company_id,
        items=items,
        total=len(items),
    )


@router.get("/market-fear", response_model=MarketFearListResponse)
def get_market_fear_indicators(
    db: Annotated[Session, Depends(get_db)],
) -> MarketFearListResponse:
    return get_market_fear(db)


@router.post("/market-fear/refresh", response_model=MarketFearListResponse)
def refresh_market_fear_indicators(
    db: Annotated[Session, Depends(get_db)],
    market: Literal["A_SHARE", "HK", "US"] | None = None,
) -> MarketFearListResponse:
    return refresh_market_fear(db, market=market)


def _handle(operation: Callable[[], T]) -> T:
    try:
        return operation()
    except PortfolioNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except PortfolioConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except PortfolioValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except PortfolioUpstreamError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    except PortfolioError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
