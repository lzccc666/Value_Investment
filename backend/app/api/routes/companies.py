from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.analysis.model_gateway import (
    ModelGatewayError,
    ModelNotConfiguredError,
    ModelOutputValidationError,
)
from app.api.errors import market_data_http_exception
from app.configuration.runtime import parameter_config_context
from app.data_sources.announcement_content import AnnouncementContentFetchError
from app.data_sources.eastmoney_announcements import (
    AnnouncementDataSourceError,
    UnsupportedAnnouncementSourceError,
)
from app.data_sources.eastmoney_company_profile import CompanyProfileDataSourceError
from app.data_sources.eastmoney_financials import FinancialDataSourceError
from app.data_sources.eastmoney_market_snapshot import (
    MarketSnapshotDataSourceError,
    UnsupportedMarketSnapshotSourceError,
)
from app.db.models import Company
from app.db.session import get_db
from app.market_data.contracts import MarketDataError, MarketDataValidationError
from app.market_data.registry import default_registry
from app.schemas.announcement_summary import (
    AnnouncementSummaryBatchResponse,
    AnnouncementSummaryResponse,
)
from app.schemas.company import (
    AnnouncementDeleteResponse,
    AnnouncementListResponse,
    AnnouncementSyncResponse,
    CompanyCreate,
    CompanyListResponse,
    CompanyRead,
    FinancialEvidencePackRead,
    FinancialStatementDeleteResponse,
    FinancialStatementListResponse,
    FinancialStatementSyncResponse,
    MarketCapabilitiesResponse,
    SecurityListingCreate,
    SecurityListingListResponse,
    SecurityListingRead,
)
from app.services.announcement_summary_service import (
    summarize_company_announcement,
    summarize_company_announcements,
    summarize_company_announcements_deep,
)
from app.services.companies import (
    ANNOUNCEMENT_RETENTION_LIMIT,
    create_company,
    create_company_listing,
    delete_company_announcement,
    delete_company_financial_statement,
    get_company,
    get_company_announcement,
    get_company_by_identity,
    get_company_financial_statement,
    get_primary_listing,
    list_companies,
    list_company_announcements,
    list_company_announcements_for_deep_summary,
    list_company_announcements_for_summary,
    list_company_financials,
    list_company_financials_by_periods,
    list_company_listings,
    refresh_company_market_snapshot,
    refresh_company_profile,
    sync_company_announcements,
    sync_company_financials,
)
from app.services.financial_metrics import build_financial_evidence_pack
from app.services.parameter_config_service import get_runtime_parameter_config

router = APIRouter(prefix="/companies")


@router.get("", response_model=CompanyListResponse)
def get_companies(
    db: Annotated[Session, Depends(get_db)],
    q: Annotated[str | None, Query(description="按代码、名称、交易所或行业筛选")] = None,
    limit: Annotated[int | None, Query(ge=1)] = None,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> CompanyListResponse:
    runtime = get_runtime_parameter_config(db)
    sampling = runtime.snapshot["data_sampling"]
    maximum = int(sampling["company_list_limit_max"])
    effective_limit = int(sampling["company_list_limit"]) if limit is None else limit
    if effective_limit > maximum:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"公司列表单次请求数量不能超过当前配置上限 {maximum}",
        )
    items, total = list_companies(db, query=q, limit=effective_limit, offset=offset)
    return CompanyListResponse(items=items, total=total, limit=effective_limit, offset=offset)


@router.post("", response_model=CompanyRead, status_code=status.HTTP_201_CREATED)
def create_company_record(
    payload: CompanyCreate,
    db: Annotated[Session, Depends(get_db)],
) -> CompanyRead:
    existing_company = get_company_by_identity(db, payload.ticker, payload.exchange)
    if existing_company is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Company with this ticker and exchange already exists",
        )

    return create_company(db, payload)


@router.get("/{company_id}", response_model=CompanyRead)
def get_company_detail(company_id: int, db: Annotated[Session, Depends(get_db)]) -> CompanyRead:
    company = _get_company_or_404(db, company_id)
    if company.listed_date is None or _should_refresh_company_description(company):
        try:
            company, _ = refresh_company_profile(db, company)
        except (CompanyProfileDataSourceError, MarketDataError):
            pass
    return company


@router.post("/{company_id}/profile/refresh", response_model=CompanyRead)
def refresh_company_profile_data(
    company_id: int, db: Annotated[Session, Depends(get_db)]
) -> CompanyRead:
    company = _get_company_or_404(db, company_id)
    if company.listed_date is None or _should_refresh_company_description(company):
        try:
            company, _ = refresh_company_profile(db, company)
        except (CompanyProfileDataSourceError, MarketDataError):
            pass

    try:
        return refresh_company_market_snapshot(db, company)
    except UnsupportedMarketSnapshotSourceError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except MarketSnapshotDataSourceError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc
    except MarketDataValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("/{company_id}/listings", response_model=SecurityListingListResponse)
def get_company_listings(
    company_id: int, db: Annotated[Session, Depends(get_db)]
) -> SecurityListingListResponse:
    _get_company_or_404(db, company_id)
    return SecurityListingListResponse(
        company_id=company_id,
        items=list_company_listings(db, company_id),
    )


@router.post(
    "/{company_id}/listings",
    response_model=SecurityListingRead,
    status_code=status.HTTP_201_CREATED,
)
def create_company_listing_record(
    company_id: int,
    payload: SecurityListingCreate,
    db: Annotated[Session, Depends(get_db)],
) -> SecurityListingRead:
    company = _get_company_or_404(db, company_id)
    try:
        return create_company_listing(db, company, payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("/{company_id}/market-capabilities", response_model=MarketCapabilitiesResponse)
def get_company_market_capabilities(
    company_id: int,
    db: Annotated[Session, Depends(get_db)],
    listing_id: Annotated[int | None, Query(ge=1)] = None,
) -> MarketCapabilitiesResponse:
    company = _get_company_or_404(db, company_id)
    listings = list_company_listings(db, company.id)
    listing = next((item for item in listings if item.id == listing_id), None)
    if listing_id is None:
        listing = get_primary_listing(db, company.id)
    if listing is None or listing.company_id != company.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Listing not found")
    try:
        capabilities = default_registry.capabilities(listing.market)
    except MarketDataError as exc:
        raise market_data_http_exception(exc) from exc
    capability_payload = capabilities.as_dict()
    if listing.market == "US":
        recent_financials, _ = list_company_financials_by_periods(
            db,
            company_id=company.id,
            period_limit=60,
        )
        has_sec_dividend = any(
            isinstance(item.fields, dict)
            and isinstance(item.fields.get("dividend"), int | float)
            and not isinstance(item.fields.get("dividend"), bool)
            for item in recent_financials
        )
        if has_sec_dividend:
            capability_payload["dividend"] = {
                "status": "available",
                "provider": "sec_companyfacts",
                "reason": "已读取该发行人的 SEC 标准 XBRL 现金分红事实",
            }
    return MarketCapabilitiesResponse(
        company_id=company.id,
        listing_id=listing.id,
        market=listing.market,
        capabilities=capability_payload,
    )


@router.get("/{company_id}/financials", response_model=FinancialStatementListResponse)
def get_company_financials(
    company_id: int,
    db: Annotated[Session, Depends(get_db)],
    limit: Annotated[int | None, Query(ge=1, le=100)] = None,
    offset: Annotated[int, Query(ge=0)] = 0,
    period_limit: Annotated[int | None, Query(ge=1)] = None,
    period_offset: Annotated[int, Query(ge=0)] = 0,
) -> FinancialStatementListResponse:
    _get_company_or_404(db, company_id)
    if period_limit is not None or limit is None:
        runtime = get_runtime_parameter_config(db)
        effective_period_limit = period_limit or int(
            runtime.snapshot["data_sampling"]["financial_display_periods"]
        )
        items, total = list_company_financials_by_periods(
            db,
            company_id=company_id,
            period_limit=effective_period_limit,
            period_offset=period_offset,
        )
        return FinancialStatementListResponse(
            items=items, total=total, limit=len(items), offset=period_offset
        )

    items, total = list_company_financials(db, company_id=company_id, limit=limit, offset=offset)
    return FinancialStatementListResponse(items=items, total=total, limit=limit, offset=offset)


@router.get(
    "/{company_id}/financials/evidence-pack",
    response_model=FinancialEvidencePackRead,
)
def get_company_financial_evidence_pack(
    company_id: int,
    db: Annotated[Session, Depends(get_db)],
) -> FinancialEvidencePackRead:
    _get_company_or_404(db, company_id)
    runtime = get_runtime_parameter_config(db)
    with parameter_config_context(runtime.snapshot):
        items, _ = list_company_financials_by_periods(
            db,
            company_id=company_id,
            period_limit=int(runtime.snapshot["data_sampling"]["financial_display_periods"]),
            period_offset=0,
        )
        return FinancialEvidencePackRead(**build_financial_evidence_pack(items))


@router.delete(
    "/{company_id}/financials/{statement_id:int}",
    response_model=FinancialStatementDeleteResponse,
)
def delete_company_financial_data(
    company_id: int,
    statement_id: int,
    db: Annotated[Session, Depends(get_db)],
) -> FinancialStatementDeleteResponse:
    _get_company_or_404(db, company_id)
    statement = get_company_financial_statement(db, company_id, statement_id)
    if statement is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Financial statement not found",
        )

    delete_company_financial_statement(db, statement)
    return FinancialStatementDeleteResponse(id=statement_id, deleted=True)


@router.post("/{company_id}/financials/sync", response_model=FinancialStatementSyncResponse)
def sync_company_financial_data(
    company_id: int,
    db: Annotated[Session, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=60)] = 60,
    listing_id: Annotated[int | None, Query(ge=1)] = None,
) -> FinancialStatementSyncResponse:
    company = _get_company_or_404(db, company_id)
    try:
        if listing_id is None:
            items, fetched, created, updated = sync_company_financials(db, company, limit=limit)
        else:
            items, fetched, created, updated = sync_company_financials(
                db, company, limit=limit, listing_id=listing_id
            )
    except MarketDataError as exc:
        raise market_data_http_exception(exc) from exc
    except FinancialDataSourceError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc

    return FinancialStatementSyncResponse(
        company_id=company.id,
        source=_provider_source(items, "eastmoney_f10_main_finance"),
        fetched=fetched,
        created=created,
        updated=updated,
        items=items,
    )


@router.get("/{company_id}/announcements", response_model=AnnouncementListResponse)
def get_company_announcements(
    company_id: int,
    db: Annotated[Session, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=ANNOUNCEMENT_RETENTION_LIMIT)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> AnnouncementListResponse:
    _get_company_or_404(db, company_id)
    items, total = list_company_announcements(db, company_id=company_id, limit=limit, offset=offset)
    return AnnouncementListResponse(items=items, total=total, limit=limit, offset=offset)


@router.delete(
    "/{company_id}/announcements/{announcement_id}",
    response_model=AnnouncementDeleteResponse,
)
def delete_company_announcement_data(
    company_id: int,
    announcement_id: int,
    db: Annotated[Session, Depends(get_db)],
) -> AnnouncementDeleteResponse:
    _get_company_or_404(db, company_id)
    announcement = get_company_announcement(db, company_id, announcement_id)
    if announcement is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Announcement not found",
        )

    delete_company_announcement(db, announcement)
    return AnnouncementDeleteResponse(id=announcement_id, deleted=True)


@router.post(
    "/{company_id}/announcements/{announcement_id}/summarize",
    response_model=AnnouncementSummaryResponse,
)
def summarize_company_announcement_data(
    company_id: int,
    announcement_id: int,
    db: Annotated[Session, Depends(get_db)],
) -> AnnouncementSummaryResponse:
    company = _get_company_or_404(db, company_id)
    announcement = get_company_announcement(db, company_id, announcement_id)
    if announcement is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Announcement not found",
        )

    try:
        runtime = get_runtime_parameter_config(db)
        with parameter_config_context(runtime.snapshot):
            summarized, run_id = summarize_company_announcement(db, company, announcement)
    except ModelNotConfiguredError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except (
        AnnouncementContentFetchError,
        ModelOutputValidationError,
        ModelGatewayError,
    ) as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    return AnnouncementSummaryResponse(
        company_id=company_id,
        announcement_id=announcement_id,
        run_id=run_id,
        status="success",
        summary_status=summarized.summary_status,
        announcement=summarized,
    )


@router.post(
    "/{company_id}/announcements/summarize-all",
    response_model=AnnouncementSummaryBatchResponse,
)
def summarize_all_company_announcements_data(
    company_id: int,
    db: Annotated[Session, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=ANNOUNCEMENT_RETENTION_LIMIT)] = (
        ANNOUNCEMENT_RETENTION_LIMIT
    ),
    only_missing: Annotated[bool, Query()] = False,
    include_failed: Annotated[bool, Query()] = True,
) -> AnnouncementSummaryBatchResponse:
    company = _get_company_or_404(db, company_id)
    announcements, pending_before = list_company_announcements_for_summary(
        db,
        company_id=company_id,
        limit=limit,
        only_missing=only_missing,
        include_failed=include_failed,
        exclude_deep_summarized=True,
    )
    if not announcements:
        return AnnouncementSummaryBatchResponse(
            company_id=company_id,
            requested=pending_before,
            processed=0,
            remaining=0,
            succeeded=0,
            failed=0,
            status="success",
            items=[],
        )

    runtime = get_runtime_parameter_config(db)
    with parameter_config_context(runtime.snapshot):
        items = summarize_company_announcements(db, company, announcements)
    succeeded = sum(1 for item in items if item.status == "success")
    failed = sum(1 for item in items if item.status == "failed")

    return AnnouncementSummaryBatchResponse(
        company_id=company_id,
        requested=pending_before,
        processed=len(items),
        remaining=max(0, pending_before - len(items)),
        succeeded=succeeded,
        failed=failed,
        status=_batch_summary_status(len(items), succeeded, failed),
        items=items,
    )


@router.post(
    "/{company_id}/announcements/summarize-all-deep",
    response_model=AnnouncementSummaryBatchResponse,
)
def summarize_all_company_announcements_deep_data(
    company_id: int,
    db: Annotated[Session, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=ANNOUNCEMENT_RETENTION_LIMIT)] = (
        ANNOUNCEMENT_RETENTION_LIMIT
    ),
) -> AnnouncementSummaryBatchResponse:
    company = _get_company_or_404(db, company_id)
    announcements, pending_before = list_company_announcements_for_deep_summary(
        db,
        company_id=company_id,
        limit=limit,
    )
    if not announcements:
        return AnnouncementSummaryBatchResponse(
            company_id=company_id,
            requested=pending_before,
            processed=0,
            remaining=0,
            succeeded=0,
            failed=0,
            status="success",
            items=[],
        )

    runtime = get_runtime_parameter_config(db)
    with parameter_config_context(runtime.snapshot):
        items = summarize_company_announcements_deep(db, company, announcements)
    succeeded = sum(1 for item in items if item.status == "success")
    failed = sum(1 for item in items if item.status == "failed")

    return AnnouncementSummaryBatchResponse(
        company_id=company_id,
        requested=pending_before,
        processed=len(items),
        remaining=max(0, pending_before - len(items)),
        succeeded=succeeded,
        failed=failed,
        status=_batch_summary_status(len(items), succeeded, failed),
        items=items,
    )


@router.post("/{company_id}/announcements/sync", response_model=AnnouncementSyncResponse)
def sync_company_announcement_data(
    company_id: int,
    db: Annotated[Session, Depends(get_db)],
    years: Annotated[int | None, Query(ge=1, le=10, description="同步最近多少年的公告")] = None,
    listing_id: Annotated[int | None, Query(ge=1)] = None,
) -> AnnouncementSyncResponse:
    company = _get_company_or_404(db, company_id)
    try:
        runtime = get_runtime_parameter_config(db)
        with parameter_config_context(runtime.snapshot):
            effective_years = years or int(
                runtime.snapshot["data_sampling"]["announcement_lookback_years"]
            )
            if listing_id is None:
                result = sync_company_announcements(db, company, years=effective_years)
            else:
                result = sync_company_announcements(
                    db, company, years=effective_years, listing_id=listing_id
                )
            items, fetched, created, updated, skipped, pruned, errors = result
    except UnsupportedAnnouncementSourceError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except MarketDataError as exc:
        raise market_data_http_exception(exc) from exc
    except AnnouncementDataSourceError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc

    return AnnouncementSyncResponse(
        company_id=company.id,
        source=_provider_source(items, "eastmoney_announcements"),
        fetched=fetched,
        created=created,
        updated=updated,
        skipped=skipped,
        pruned=pruned,
        errors=errors,
        items=items,
    )


def _batch_summary_status(total: int, succeeded: int, failed: int) -> str:
    if total == 0 or failed == 0:
        return "success"
    if failed == total:
        return "failed"
    return "partial"


def _provider_source(items: list[object], fallback: str) -> str:
    sources = sorted({str(source) for item in items if (source := getattr(item, "source", None))})
    return sources[0] if len(sources) == 1 else fallback


def _get_company_or_404(db: Session, company_id: int) -> Company:
    company = get_company(db, company_id)
    if company is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found")
    return company


def _should_refresh_company_description(company: Company) -> bool:
    description = (company.description or "").strip()
    if not description:
        return True
    if "真实公司主数据种子" in description:
        return True
    if "不包含实时行情或投资建议" in description:
        return True
    return False
