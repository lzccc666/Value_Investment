from __future__ import annotations

import re
from datetime import UTC, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.data_sources.eastmoney_security_catalog import (
    EastmoneySecurityCatalogClient,
    EastmoneySecurityCatalogError,
    FetchedSecurityCatalogItem,
)
from app.data_sources.sec_edgar import SecEdgarClient
from app.db.models import (
    Company,
    PortfolioHolding,
    PortfolioOwner,
    PortfolioSnapshot,
    SecurityListing,
)
from app.market_data.contracts import MarketDataError
from app.schemas.investment_tools import (
    AhListingCatalogItem,
    AhListingImportRequest,
    PortfolioFxRefreshItem,
    PortfolioHoldingCreate,
    PortfolioHoldingRead,
    PortfolioHoldingUpdate,
    PortfolioListingSearchItem,
    PortfolioOwnerCreate,
    PortfolioOwnerUpdate,
    PortfolioQuoteRefreshItem,
    PortfolioRefreshResponse,
    PortfolioSnapshotCreate,
    PortfolioSnapshotUpdate,
    PortfolioValuationItem,
    PortfolioValuationResponse,
    SecUsListingCatalogItem,
    SecUsListingImportRequest,
)
from app.services.companies import (
    get_latest_market_snapshot,
    refresh_listing_market_snapshot,
    set_primary_listing,
)
from app.services.fx_rate_service import get_latest_fx_rate, refresh_fx_rate

SUPPORTED_CURRENCIES = {"CNY", "HKD", "USD"}
SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")
SEC_EXCHANGE_MAP = {"nasdaq": "NASDAQ", "nyse": "NYSE"}


class PortfolioError(RuntimeError):
    pass


class PortfolioNotFoundError(PortfolioError):
    pass


class PortfolioConflictError(PortfolioError):
    pass


class PortfolioValidationError(PortfolioError):
    pass


class PortfolioUpstreamError(PortfolioError):
    pass


def list_owners(session: Session) -> list[PortfolioOwner]:
    return list(
        session.scalars(
            select(PortfolioOwner).order_by(
                PortfolioOwner.display_order,
                PortfolioOwner.id,
            )
        )
    )


def get_owner(session: Session, owner_id: int) -> PortfolioOwner:
    owner = session.get(PortfolioOwner, owner_id)
    if owner is None:
        raise PortfolioNotFoundError("持仓人不存在。")
    return owner


def create_owner(session: Session, payload: PortfolioOwnerCreate) -> PortfolioOwner:
    highest_order = session.scalar(select(func.max(PortfolioOwner.display_order)))
    owner = PortfolioOwner(
        **payload.model_dump(),
        display_order=0 if highest_order is None else highest_order + 1,
    )
    session.add(owner)
    session.commit()
    session.refresh(owner)
    return owner


def update_owner(
    session: Session,
    owner_id: int,
    payload: PortfolioOwnerUpdate,
) -> PortfolioOwner:
    owner = get_owner(session, owner_id)
    for field_name, value in payload.model_dump(exclude_unset=True).items():
        setattr(owner, field_name, value)
    session.commit()
    session.refresh(owner)
    return owner


def delete_owner(session: Session, owner_id: int) -> None:
    owner = get_owner(session, owner_id)
    snapshot_count = int(
        session.scalar(
            select(func.count())
            .select_from(PortfolioSnapshot)
            .where(PortfolioSnapshot.owner_id == owner.id)
        )
        or 0
    )
    if snapshot_count:
        raise PortfolioConflictError(
            f"持仓人仍有 {snapshot_count} 个持仓快照，请先删除这些快照。"
        )
    session.delete(owner)
    session.commit()


def reorder_owners(session: Session, ordered_ids: list[int]) -> list[PortfolioOwner]:
    owners = list(session.scalars(select(PortfolioOwner)))
    if len(owners) != len(ordered_ids) or {item.id for item in owners} != set(ordered_ids):
        raise PortfolioValidationError("排序列表必须完整包含当前全部持仓人。")
    owners_by_id = {item.id: item for item in owners}
    for display_order, owner_id in enumerate(ordered_ids):
        owners_by_id[owner_id].display_order = display_order
    session.commit()
    return list_owners(session)


def list_snapshots(session: Session, owner_id: int) -> list[PortfolioSnapshot]:
    get_owner(session, owner_id)
    return list(
        session.scalars(
            select(PortfolioSnapshot)
            .where(PortfolioSnapshot.owner_id == owner_id)
            .order_by(
                PortfolioSnapshot.display_order,
                PortfolioSnapshot.id,
            )
        )
    )


def get_snapshot(session: Session, snapshot_id: int) -> PortfolioSnapshot:
    snapshot = session.get(PortfolioSnapshot, snapshot_id)
    if snapshot is None:
        raise PortfolioNotFoundError("持仓快照不存在。")
    return snapshot


def create_snapshot(
    session: Session,
    owner_id: int,
    payload: PortfolioSnapshotCreate,
) -> PortfolioSnapshot:
    get_owner(session, owner_id)
    source: PortfolioSnapshot | None = None
    if payload.copy_from_snapshot_id is not None:
        source = get_snapshot(session, payload.copy_from_snapshot_id)
        if source.owner_id != owner_id:
            raise PortfolioValidationError("只能从同一持仓人的历史快照复制持仓。")
    values = payload.model_dump(exclude={"copy_from_snapshot_id"})
    highest_order = session.scalar(
        select(func.max(PortfolioSnapshot.display_order)).where(
            PortfolioSnapshot.owner_id == owner_id
        )
    )
    snapshot = PortfolioSnapshot(
        owner_id=owner_id,
        display_order=0 if highest_order is None else highest_order + 1,
        **values,
    )
    session.add(snapshot)
    session.flush()
    if source is not None:
        for holding in list_holdings(session, source.id):
            snapshot.holdings.append(
                PortfolioHolding(
                    listing_id=holding.listing_id,
                    quantity=holding.quantity,
                    notes=holding.notes,
                    display_order=holding.display_order,
                )
            )
    session.commit()
    session.refresh(snapshot)
    return snapshot


def update_snapshot(
    session: Session,
    snapshot_id: int,
    payload: PortfolioSnapshotUpdate,
) -> PortfolioSnapshot:
    snapshot = get_snapshot(session, snapshot_id)
    for field_name, value in payload.model_dump(exclude_unset=True).items():
        setattr(snapshot, field_name, value)
    session.commit()
    session.refresh(snapshot)
    return snapshot


def delete_snapshot(session: Session, snapshot_id: int) -> None:
    snapshot = get_snapshot(session, snapshot_id)
    session.delete(snapshot)
    session.commit()


def reorder_snapshots(
    session: Session,
    owner_id: int,
    ordered_ids: list[int],
) -> list[PortfolioSnapshot]:
    get_owner(session, owner_id)
    snapshots = list(
        session.scalars(
            select(PortfolioSnapshot).where(PortfolioSnapshot.owner_id == owner_id)
        )
    )
    if len(snapshots) != len(ordered_ids) or {
        item.id for item in snapshots
    } != set(ordered_ids):
        raise PortfolioValidationError(
            "排序列表必须完整包含该持仓人的全部持仓快照。"
        )
    snapshots_by_id = {item.id: item for item in snapshots}
    for display_order, snapshot_id in enumerate(ordered_ids):
        snapshots_by_id[snapshot_id].display_order = display_order
    session.commit()
    return list_snapshots(session, owner_id)


def search_portfolio_listings(
    session: Session,
    query: str,
    limit: int = 20,
) -> list[PortfolioListingSearchItem]:
    normalized_query = _normalize_search_text(query)
    if not normalized_query:
        return []
    listings = list(
        session.scalars(
            select(SecurityListing)
            .options(joinedload(SecurityListing.company))
            .where(
                SecurityListing.is_active.is_(True),
                SecurityListing.market.in_({"A_SHARE", "HK", "US"}),
                SecurityListing.trading_currency.in_(SUPPORTED_CURRENCIES),
                SecurityListing.security_type.in_({"common_stock", "ads"}),
            )
        )
    )
    has_exact_ticker = any(
        normalized_query
        in {
            _normalize_search_text(listing.ticker),
            _normalize_search_text(listing.symbol),
        }
        for listing in listings
    )
    if has_exact_ticker:
        listings = [
            listing
            for listing in listings
            if any(
                field.startswith(normalized_query)
                for field in (
                    _normalize_search_text(listing.ticker),
                    _normalize_search_text(listing.symbol),
                )
            )
        ]
    matches = [
        (_listing_search_score(listing, normalized_query), listing)
        for listing in listings
    ]
    matches = [item for item in matches if item[0] is not None]
    matches.sort(
        key=lambda item: (
            int(item[0]),
            item[1].company.name.casefold(),
            item[1].ticker,
        )
    )
    return [
        _listing_to_search_item(listing)
        for _, listing in matches[:limit]
    ]


def search_sec_us_listing_catalog(
    session: Session,
    query: str,
    limit: int = 20,
    *,
    client: SecEdgarClient | None = None,
    catalog_client: EastmoneySecurityCatalogClient | None = None,
) -> list[SecUsListingCatalogItem]:
    normalized_query = _normalize_search_text(query)
    if not normalized_query:
        return []
    directory = _fetch_sec_directory(client)
    candidates = _parse_sec_directory(directory)
    try:
        supported_us_listings = [
            item
            for item in (catalog_client or EastmoneySecurityCatalogClient()).search(
                query,
                limit=50,
            )
            if item.market == "US"
        ]
    except EastmoneySecurityCatalogError as exc:
        raise PortfolioUpstreamError(f"美股证券类型核验失败：{exc}") from exc
    supported_identities = {
        (_normalize_catalog_us_symbol(item.symbol), item.exchange)
        for item in supported_us_listings
    }
    exact_symbol_identities = {
        (_normalize_catalog_us_symbol(item.symbol), item.exchange)
        for item in supported_us_listings
        if _normalize_search_text(item.symbol) == normalized_query
    }
    if exact_symbol_identities:
        supported_identities = exact_symbol_identities
    imported_tickers = set(
        session.scalars(
            select(SecurityListing.ticker).where(SecurityListing.market == "US")
        )
    )
    scored: list[tuple[int, SecUsListingCatalogItem]] = []
    for candidate in candidates:
        if candidate.ticker in imported_tickers:
            continue
        if (
            _normalize_catalog_us_symbol(candidate.symbol),
            candidate.exchange,
        ) not in supported_identities:
            continue
        normalized_symbol = _normalize_search_text(candidate.symbol)
        normalized_name = _normalize_search_text(candidate.company_name)
        if normalized_symbol == normalized_query:
            score = 0
        elif normalized_name == normalized_query:
            score = 1
        elif normalized_symbol.startswith(normalized_query):
            score = 2
        elif normalized_name.startswith(normalized_query):
            score = 3
        elif normalized_query in normalized_name:
            score = 4
        else:
            continue
        scored.append((score, candidate))
    scored.sort(key=lambda item: (item[0], item[1].company_name.casefold(), item[1].symbol))
    return [item for _, item in scored[:limit]]


def import_sec_us_listing(
    session: Session,
    payload: SecUsListingImportRequest,
    *,
    client: SecEdgarClient | None = None,
    catalog_client: EastmoneySecurityCatalogClient | None = None,
) -> PortfolioListingSearchItem:
    sec_client = _sec_client(client)
    cik = _normalize_cik(payload.cik)
    symbol = _normalize_sec_symbol(payload.symbol)
    directory_entries = _parse_sec_directory(_fetch_sec_directory(sec_client))
    candidate = next(
        (
            item
            for item in directory_entries
            if item.cik == cik and item.symbol == symbol
        ),
        None,
    )
    if candidate is None:
        raise PortfolioValidationError("SEC 公司目录中不存在该 ticker/CIK 组合。")

    existing = session.scalar(
        select(SecurityListing)
        .options(joinedload(SecurityListing.company))
        .where(
            SecurityListing.ticker == candidate.ticker,
            SecurityListing.exchange == candidate.exchange,
        )
    )
    if existing is not None:
        return _listing_to_search_item(existing)

    try:
        submissions = sec_client.fetch_submissions(cik)
    except MarketDataError as exc:
        raise PortfolioUpstreamError(f"SEC submissions 请求失败：{exc}") from exc
    try:
        catalog_listing = (catalog_client or EastmoneySecurityCatalogClient()).find_us_listing(
            symbol,
            candidate.exchange,
        )
    except EastmoneySecurityCatalogError as exc:
        raise PortfolioUpstreamError(f"美股证券类型核验失败：{exc}") from exc
    if catalog_listing is None:
        raise PortfolioValidationError(
            "外部证券目录未确认该 SEC 条目为普通股或 ADS。"
        )
    security_type = catalog_listing.security_type
    catalog_alias = catalog_listing.company_name
    entity_type = str(submissions.get("entityType") or "").strip().casefold()
    if entity_type != "operating":
        recent = submissions.get("filings")
        recent = recent.get("recent") if isinstance(recent, dict) else None
        forms = recent.get("form") if isinstance(recent, dict) else None
        is_foreign_private_issuer = isinstance(forms, list) and any(
            str(form).strip().upper() in {"20-F", "6-K"} for form in forms
        )
        if not is_foreign_private_issuer:
            raise PortfolioValidationError(
                "SEC 目录条目不是 operating issuer，且没有 20-F/6-K 境外发行人记录。"
            )
    ticker_exchange_pairs = {
        (_normalize_sec_symbol(str(ticker)), _normalize_sec_exchange(str(exchange)))
        for ticker, exchange in zip(
            submissions.get("tickers") or [],
            submissions.get("exchanges") or [],
            strict=False,
        )
    }
    if (symbol, candidate.exchange) not in ticker_exchange_pairs:
        raise PortfolioValidationError("SEC submissions 未确认该 ticker 与交易所组合。")

    company = _find_company_by_sec_cik(session, cik)
    if company is None:
        company_name = str(submissions.get("name") or candidate.company_name).strip()
        company_aliases = [company_name, symbol]
        if catalog_alias:
            company_aliases.append(catalog_alias)
        company = Company(
            ticker=candidate.ticker,
            exchange=candidate.exchange,
            name=company_name,
            canonical_key=f"sec-cik-{cik}",
            legal_name=company_name,
            aliases=list(dict.fromkeys(company_aliases)),
            domicile_country=None,
            reporting_currency=None,
            fiscal_year_end=None,
            external_ids={"sec_cik": cik},
            industry=None,
            description="从 SEC 官方公司目录导入；行业、报告币种和证券单位比例待后续资料核验。",
            status="未研究",
            tags=["美股", "SEC目录导入"],
        )
        session.add(company)
        session.flush()
    elif catalog_alias and catalog_alias not in (company.aliases or []):
        company.aliases = [*(company.aliases or []), catalog_alias]

    listing = SecurityListing(
        company_id=company.id,
        ticker=candidate.ticker,
        symbol=symbol,
        exchange=candidate.exchange,
        market="US",
        trading_currency="USD",
        security_type=security_type,
        is_primary=False,
        is_active=True,
        underlying_shares_per_listing_unit=None,
        provider_identifiers={
            "sec_cik": cik,
            "sec_ticker": symbol,
            "security_unit_status": "unreviewed_sec_directory_import",
        },
    )
    session.add(listing)
    session.flush()
    listing.underlying_shares_per_listing_unit = None
    session.flush()
    has_primary = session.scalar(
        select(SecurityListing.id).where(
            SecurityListing.company_id == company.id,
            SecurityListing.is_active.is_(True),
            SecurityListing.is_primary.is_(True),
            SecurityListing.id != listing.id,
        )
    )
    if has_primary is None:
        set_primary_listing(session, company, listing)
    else:
        session.commit()
        session.refresh(listing)
    listing = session.scalar(
        select(SecurityListing)
        .options(joinedload(SecurityListing.company))
        .where(SecurityListing.id == listing.id)
    )
    assert listing is not None
    return _listing_to_search_item(listing)


def search_ah_listing_catalog(
    session: Session,
    query: str,
    limit: int = 20,
    *,
    client: EastmoneySecurityCatalogClient | None = None,
) -> list[AhListingCatalogItem]:
    normalized_query = _normalize_search_text(query)
    if not normalized_query:
        return []
    try:
        fetched = (client or EastmoneySecurityCatalogClient()).search(query, limit=50)
    except EastmoneySecurityCatalogError as exc:
        raise PortfolioUpstreamError(f"A/H 证券目录请求失败：{exc}") from exc

    imported = set(
        session.execute(
            select(SecurityListing.exchange, SecurityListing.ticker).where(
                SecurityListing.market.in_({"A_SHARE", "HK"})
            )
        ).all()
    )
    scored: list[tuple[int, int, FetchedSecurityCatalogItem]] = []
    for index, item in enumerate(fetched):
        if item.market not in {"A_SHARE", "HK"}:
            continue
        if (item.exchange, item.ticker) in imported:
            continue
        score = _catalog_search_score(item, normalized_query)
        if score is not None:
            scored.append((score, index, item))
    scored.sort(key=lambda entry: (entry[0], entry[1], entry[2].ticker))
    return [_ah_catalog_item(item) for _, _, item in scored[:limit]]


def import_ah_listing(
    session: Session,
    payload: AhListingImportRequest,
    *,
    client: EastmoneySecurityCatalogClient | None = None,
) -> PortfolioListingSearchItem:
    code = payload.quote_id.partition(".")[2]
    try:
        fetched = (client or EastmoneySecurityCatalogClient()).search(code, limit=50)
    except EastmoneySecurityCatalogError as exc:
        raise PortfolioUpstreamError(f"A/H 证券目录请求失败：{exc}") from exc
    candidate = next(
        (
            item
            for item in fetched
            if item.quote_id.upper() == payload.quote_id
            and item.market in {"A_SHARE", "HK"}
        ),
        None,
    )
    if candidate is None:
        raise PortfolioValidationError(
            "A/H 证券目录未确认该标识为沪深北或港股普通股。"
        )

    existing = session.scalar(
        select(SecurityListing)
        .options(joinedload(SecurityListing.company))
        .where(
            SecurityListing.ticker == candidate.ticker,
            SecurityListing.exchange == candidate.exchange,
        )
    )
    if existing is not None:
        return _listing_to_search_item(existing)

    company = _find_company_for_catalog_listing(session, candidate)
    if company is None:
        company = Company(
            ticker=candidate.ticker,
            exchange=candidate.exchange,
            name=candidate.company_name,
            canonical_key=f"eastmoney-quote-{candidate.quote_id.replace('.', '-')}",
            legal_name=None,
            aliases=list(
                dict.fromkeys(
                    value
                    for value in (
                        candidate.company_name,
                        candidate.symbol,
                        candidate.pinyin,
                    )
                    if value
                )
            ),
            domicile_country=None,
            reporting_currency=None,
            fiscal_year_end=None,
            external_ids={"eastmoney_quote_id": candidate.quote_id},
            industry=None,
            description="从东方财富证券目录导入；发行人档案待后续官方资料核验。",
            status="未研究",
            tags=["A股" if candidate.market == "A_SHARE" else "港股", "证券目录导入"],
        )
        session.add(company)
        session.flush()
    else:
        aliases = list(company.aliases or [])
        for alias in (candidate.company_name, candidate.symbol, candidate.pinyin):
            if alias and alias not in aliases:
                aliases.append(alias)
        company.aliases = aliases

    listing = SecurityListing(
        company_id=company.id,
        ticker=candidate.ticker,
        symbol=candidate.symbol,
        exchange=candidate.exchange,
        market=candidate.market,
        trading_currency=candidate.trading_currency,
        security_type="common_stock",
        is_primary=False,
        is_active=True,
        underlying_shares_per_listing_unit=1.0,
        provider_identifiers={
            "eastmoney_quote_id": candidate.quote_id,
            "eastmoney_symbol": candidate.symbol,
            "security_unit_status": "ordinary_share_catalog_import",
        },
    )
    session.add(listing)
    session.flush()
    has_primary = session.scalar(
        select(SecurityListing.id).where(
            SecurityListing.company_id == company.id,
            SecurityListing.is_active.is_(True),
            SecurityListing.is_primary.is_(True),
            SecurityListing.id != listing.id,
        )
    )
    if has_primary is None:
        set_primary_listing(session, company, listing)
    else:
        session.commit()
        session.refresh(listing)
    listing = session.scalar(
        select(SecurityListing)
        .options(joinedload(SecurityListing.company))
        .where(SecurityListing.id == listing.id)
    )
    assert listing is not None
    return _listing_to_search_item(listing)


def list_holdings(session: Session, snapshot_id: int) -> list[PortfolioHolding]:
    get_snapshot(session, snapshot_id)
    return list(
        session.scalars(
            select(PortfolioHolding)
            .options(joinedload(PortfolioHolding.listing).joinedload(SecurityListing.company))
            .where(PortfolioHolding.snapshot_id == snapshot_id)
            .order_by(PortfolioHolding.display_order, PortfolioHolding.id)
        )
    )


def get_holding(session: Session, holding_id: int) -> PortfolioHolding:
    holding = session.scalar(
        select(PortfolioHolding)
        .options(joinedload(PortfolioHolding.listing).joinedload(SecurityListing.company))
        .where(PortfolioHolding.id == holding_id)
    )
    if holding is None:
        raise PortfolioNotFoundError("持仓明细不存在。")
    return holding


def create_holding(
    session: Session,
    snapshot_id: int,
    payload: PortfolioHoldingCreate,
) -> PortfolioHolding:
    get_snapshot(session, snapshot_id)
    listing = _get_supported_listing(session, payload.listing_id)
    _validate_quantity(listing, payload.quantity)
    duplicate = session.scalar(
        select(PortfolioHolding).where(
            PortfolioHolding.snapshot_id == snapshot_id,
            PortfolioHolding.listing_id == listing.id,
        )
    )
    if duplicate is not None:
        raise PortfolioConflictError("同一快照内已存在该 Listing，请编辑原持仓。")
    holding = PortfolioHolding(snapshot_id=snapshot_id, **payload.model_dump())
    session.add(holding)
    _commit_holding(session)
    session.refresh(holding)
    return get_holding(session, holding.id)


def update_holding(
    session: Session,
    holding_id: int,
    payload: PortfolioHoldingUpdate,
) -> PortfolioHolding:
    holding = get_holding(session, holding_id)
    values = payload.model_dump(exclude_unset=True)
    listing = holding.listing
    if "listing_id" in values:
        listing = _get_supported_listing(session, int(values["listing_id"]))
        duplicate = session.scalar(
            select(PortfolioHolding).where(
                PortfolioHolding.snapshot_id == holding.snapshot_id,
                PortfolioHolding.listing_id == listing.id,
                PortfolioHolding.id != holding.id,
            )
        )
        if duplicate is not None:
            raise PortfolioConflictError("同一快照内已存在该 Listing，不能产生重复持仓。")
    quantity = values.get("quantity", holding.quantity)
    _validate_quantity(listing, Decimal(quantity))
    for field_name, value in values.items():
        setattr(holding, field_name, value)
    _commit_holding(session)
    session.refresh(holding)
    return get_holding(session, holding.id)


def delete_holding(session: Session, holding_id: int) -> None:
    holding = get_holding(session, holding_id)
    session.delete(holding)
    session.commit()


def holding_to_read(holding: PortfolioHolding) -> PortfolioHoldingRead:
    listing = holding.listing
    return PortfolioHoldingRead(
        id=holding.id,
        snapshot_id=holding.snapshot_id,
        listing_id=listing.id,
        company_id=listing.company_id,
        company_name=listing.company.name,
        ticker=listing.ticker,
        exchange=listing.exchange,
        market=listing.market,
        trading_currency=listing.trading_currency,
        security_type=listing.security_type,
        quantity=holding.quantity,
        notes=holding.notes,
        display_order=holding.display_order,
        created_at=holding.created_at,
        updated_at=holding.updated_at,
    )


def value_portfolio(session: Session, snapshot_id: int) -> PortfolioValuationResponse:
    snapshot = get_snapshot(session, snapshot_id)
    owner = get_owner(session, snapshot.owner_id)
    holdings = list_holdings(session, snapshot.id)
    items: list[PortfolioValuationItem] = []
    priced_values: dict[int, Decimal] = {}

    for holding in holdings:
        item = _value_holding(session, holding, snapshot.base_currency)
        items.append(item)
        if item.base_market_value is not None:
            priced_values[holding.id] = item.base_market_value

    priced_total = sum(priced_values.values(), start=Decimal("0"))
    if priced_total > 0:
        for item in items:
            value = priced_values.get(item.holding_id)
            if value is not None:
                item.weight = value / priced_total

    # Priced holdings lead by comparable base-currency value; Python's stable
    # sort keeps the user's display order among unpriced rows.
    items.sort(
        key=lambda item: (
            item.base_market_value is None,
            -(item.base_market_value or Decimal("0")),
        )
    )

    priced_count = len(priced_values)
    holding_count = len(items)
    return PortfolioValuationResponse(
        snapshot=snapshot,
        owner=owner,
        priced_total=priced_total if priced_count else None,
        base_currency=snapshot.base_currency,
        holding_count=holding_count,
        priced_count=priced_count,
        unpriced_count=holding_count - priced_count,
        valuation_status=(
            "empty"
            if holding_count == 0
            else "complete"
            if priced_count == holding_count
            else "incomplete"
        ),
        items=items,
    )


def refresh_portfolio_market_data(
    session: Session,
    snapshot_id: int,
) -> PortfolioRefreshResponse:
    snapshot = get_snapshot(session, snapshot_id)
    holdings = list_holdings(session, snapshot.id)
    listings = {holding.listing_id: holding.listing for holding in holdings}
    quote_results: list[PortfolioQuoteRefreshItem] = []
    for listing in listings.values():
        try:
            market_snapshot = refresh_listing_market_snapshot(session, listing)
            quote_results.append(
                PortfolioQuoteRefreshItem(
                    listing_id=listing.id,
                    ticker=listing.ticker,
                    status="success",
                    market_snapshot_id=market_snapshot.id,
                )
            )
        except Exception as exc:
            session.rollback()
            quote_results.append(
                PortfolioQuoteRefreshItem(
                    listing_id=listing.id,
                    ticker=listing.ticker,
                    status="failed",
                    error=str(exc),
                )
            )

    currency_pairs = sorted(
        {
            (listing.trading_currency, snapshot.base_currency)
            for listing in listings.values()
        }
    )
    fx_results: list[PortfolioFxRefreshItem] = []
    for base_currency, quote_currency in currency_pairs:
        if base_currency == quote_currency:
            fx_results.append(
                PortfolioFxRefreshItem(
                    base_currency=base_currency,
                    quote_currency=quote_currency,
                    status="identity",
                )
            )
            continue
        try:
            fx_snapshot = refresh_fx_rate(
                session,
                base_currency=base_currency,
                quote_currency=quote_currency,
            )
            fx_results.append(
                PortfolioFxRefreshItem(
                    base_currency=base_currency,
                    quote_currency=quote_currency,
                    status="success",
                    fx_rate_snapshot_id=fx_snapshot.id,
                )
            )
        except Exception as exc:
            session.rollback()
            fx_results.append(
                PortfolioFxRefreshItem(
                    base_currency=base_currency,
                    quote_currency=quote_currency,
                    status="failed",
                    error=str(exc),
                )
            )

    quote_succeeded = sum(item.status == "success" for item in quote_results)
    quote_failed = sum(item.status == "failed" for item in quote_results)
    any_failed = quote_failed > 0 or any(item.status == "failed" for item in fx_results)
    any_succeeded = quote_succeeded > 0 or any(
        item.status in {"success", "identity"} for item in fx_results
    )
    status = "partial" if any_failed and any_succeeded else "failed" if any_failed else "success"
    return PortfolioRefreshResponse(
        snapshot_id=snapshot.id,
        status=status,
        succeeded=quote_succeeded,
        failed=quote_failed,
        quote_results=quote_results,
        fx_results=fx_results,
        valuation=value_portfolio(session, snapshot.id),
    )


def _value_holding(
    session: Session,
    holding: PortfolioHolding,
    base_currency: str,
) -> PortfolioValuationItem:
    listing = holding.listing
    common = {
        "holding_id": holding.id,
        "listing_id": listing.id,
        "company_id": listing.company_id,
        "company_name": listing.company.name,
        "ticker": listing.ticker,
        "exchange": listing.exchange,
        "market": listing.market,
        "trading_currency": listing.trading_currency,
        "security_type": listing.security_type,
        "quantity": holding.quantity,
    }
    if not listing.is_active:
        return PortfolioValuationItem(
            **common,
            data_status="inactive_listing",
            status_reason="Listing 已停用，未纳入估值。",
        )
    market_snapshot = get_latest_market_snapshot(session, listing.id)
    if market_snapshot is None or market_snapshot.price is None or market_snapshot.price <= 0:
        return PortfolioValuationItem(
            **common,
            data_status="missing_price",
            status_reason="缺少有效的最新行情，未纳入估值。",
        )
    if market_snapshot.currency != listing.trading_currency:
        return PortfolioValuationItem(
            **common,
            latest_price=_decimal(market_snapshot.price),
            quote_currency=market_snapshot.currency,
            quote_as_of=_quote_as_of(market_snapshot.price_as_of, market_snapshot.source),
            quote_source=market_snapshot.source,
            quote_source_url=market_snapshot.source_url,
            data_status="currency_mismatch",
            status_reason="行情币种与 Listing 交易币种不一致，未纳入估值。",
        )

    latest_price = _decimal(market_snapshot.price)
    local_value = holding.quantity * latest_price
    if listing.trading_currency == base_currency:
        return PortfolioValuationItem(
            **common,
            latest_price=latest_price,
            quote_currency=market_snapshot.currency,
            quote_as_of=_quote_as_of(market_snapshot.price_as_of, market_snapshot.source),
            quote_source=market_snapshot.source,
            quote_source_url=market_snapshot.source_url,
            local_market_value=local_value,
            fx_rate=Decimal("1"),
            fx_source="identity",
            base_market_value=local_value,
            data_status="priced",
            status_reason="已按最新可用行情计价。",
        )

    fx_snapshot = get_latest_fx_rate(
        session,
        base_currency=listing.trading_currency,
        quote_currency=base_currency,
    )
    if fx_snapshot is None or fx_snapshot.rate <= 0:
        return PortfolioValuationItem(
            **common,
            latest_price=latest_price,
            quote_currency=market_snapshot.currency,
            quote_as_of=_quote_as_of(market_snapshot.price_as_of, market_snapshot.source),
            quote_source=market_snapshot.source,
            quote_source_url=market_snapshot.source_url,
            local_market_value=local_value,
            data_status="missing_fx",
            status_reason=(
                f"缺少 {listing.trading_currency}->{base_currency} 汇率，未纳入估值。"
            ),
        )
    fx_rate = _decimal(fx_snapshot.rate)
    return PortfolioValuationItem(
        **common,
        latest_price=latest_price,
        quote_currency=market_snapshot.currency,
        quote_as_of=_quote_as_of(market_snapshot.price_as_of, market_snapshot.source),
        quote_source=market_snapshot.source,
        quote_source_url=market_snapshot.source_url,
        local_market_value=local_value,
        fx_rate=fx_rate,
        fx_rate_date=fx_snapshot.rate_date,
        fx_source=fx_snapshot.source,
        base_market_value=local_value * fx_rate,
        data_status="priced",
        status_reason="已按最新可用行情和汇率计价。",
    )


def _get_supported_listing(session: Session, listing_id: int) -> SecurityListing:
    listing = session.get(SecurityListing, listing_id)
    if listing is None:
        raise PortfolioValidationError("Listing 不存在。")
    if not listing.is_active:
        raise PortfolioValidationError("只能录入启用中的 Listing。")
    if listing.market not in {"A_SHARE", "HK", "US"}:
        raise PortfolioValidationError("首版只支持 A 股、港股和美股 Listing。")
    if listing.trading_currency not in SUPPORTED_CURRENCIES:
        raise PortfolioValidationError("Listing 交易币种不在 CNY/HKD/USD 支持范围内。")
    if listing.security_type not in {"common_stock", "ads"}:
        raise PortfolioValidationError("首版只支持普通股和 ADS Listing。")
    return listing


def _listing_search_score(
    listing: SecurityListing,
    normalized_query: str,
) -> int | None:
    market_intent = next(
        (
            market
            for token, market in (("a股", "A_SHARE"), ("港股", "HK"), ("美股", "US"))
            if token in normalized_query
        ),
        None,
    )
    if market_intent is not None and listing.market != market_intent:
        return None
    company = listing.company
    ticker_fields = [
        _normalize_search_text(listing.ticker),
        _normalize_search_text(listing.symbol),
    ]
    company_fields = [
        _normalize_search_text(company.name),
        _normalize_search_text(company.legal_name or ""),
        *(_normalize_search_text(alias) for alias in (company.aliases or [])),
    ]
    if company.name.upper().endswith("-W"):
        company_fields.append(_normalize_search_text(company.name[:-2]))
    market_label = {"A_SHARE": "A股", "HK": "港股", "US": "美股"}.get(
        listing.market, listing.market
    )
    normalized_market_label = _normalize_search_text(market_label)
    company_fields.extend(
        f"{field}{normalized_market_label}" for field in list(company_fields) if field
    )
    all_fields = [field for field in [*ticker_fields, *company_fields] if field]
    if any(field == normalized_query for field in all_fields):
        return 0
    if any(field.startswith(normalized_query) for field in ticker_fields):
        return 1
    if any(normalized_query in field for field in ticker_fields):
        return 2
    if any(field.startswith(normalized_query) for field in company_fields):
        return 3
    if any(normalized_query in field for field in company_fields):
        return 4
    return None


def _listing_to_search_item(listing: SecurityListing) -> PortfolioListingSearchItem:
    return PortfolioListingSearchItem(
        id=listing.id,
        company_id=listing.company_id,
        company_name=listing.company.name,
        ticker=listing.ticker,
        symbol=listing.symbol,
        exchange=listing.exchange,
        market=listing.market,
        trading_currency=listing.trading_currency,
        security_type=listing.security_type,
        is_primary=listing.is_primary,
    )


def _catalog_search_score(
    item: FetchedSecurityCatalogItem,
    normalized_query: str,
) -> int | None:
    market_intent = next(
        (
            market
            for token, market in (("a股", "A_SHARE"), ("港股", "HK"))
            if token in normalized_query
        ),
        None,
    )
    if market_intent is not None and item.market != market_intent:
        return None
    symbol_fields = [
        _normalize_search_text(item.symbol),
        _normalize_search_text(item.ticker),
    ]
    name_fields = [
        _normalize_search_text(item.company_name),
        _normalize_search_text(item.pinyin or ""),
    ]
    all_fields = [field for field in [*symbol_fields, *name_fields] if field]
    if any(field == normalized_query for field in all_fields):
        return 0
    if any(field.startswith(normalized_query) for field in symbol_fields):
        return 1
    if any(field.startswith(normalized_query) for field in name_fields):
        return 2
    if any(normalized_query in field for field in all_fields):
        return 3
    # The upstream directory already applies Chinese/pinyin relevance. Retain a
    # supported result even when its matching token is not returned in the row.
    return 4


def _ah_catalog_item(item: FetchedSecurityCatalogItem) -> AhListingCatalogItem:
    assert item.market in {"A_SHARE", "HK"}
    assert item.exchange in {"SSE", "SZSE", "BSE", "HKEX"}
    assert item.trading_currency in {"CNY", "HKD"}
    return AhListingCatalogItem(
        quote_id=item.quote_id,
        company_name=item.company_name,
        symbol=item.symbol,
        ticker=item.ticker,
        exchange=item.exchange,
        market=item.market,
        trading_currency=item.trading_currency,
    )


def _find_company_for_catalog_listing(
    session: Session,
    candidate: FetchedSecurityCatalogItem,
) -> Company | None:
    candidate_names = _catalog_company_name_keys(candidate.company_name)
    for company in session.scalars(select(Company)):
        company_names: set[str] = set()
        for value in (company.name, company.legal_name, *(company.aliases or [])):
            if value:
                company_names.update(_catalog_company_name_keys(str(value)))
        if candidate_names & company_names:
            return company
    return None


def _catalog_company_name_keys(value: str) -> set[str]:
    stripped = re.sub(
        r"[-－](?:SW|WR|W|S|R)$",
        "",
        value.strip(),
        flags=re.IGNORECASE,
    )
    return {
        normalized
        for normalized in (
            _normalize_search_text(value),
            _normalize_search_text(stripped),
        )
        if normalized
    }


def _sec_client(client: SecEdgarClient | None) -> SecEdgarClient:
    try:
        return client or SecEdgarClient()
    except MarketDataError as exc:
        raise PortfolioUpstreamError(f"SEC 公司目录不可用：{exc}") from exc


def _fetch_sec_directory(client: SecEdgarClient | None) -> dict[str, object]:
    sec_client = _sec_client(client)
    try:
        return sec_client.fetch_company_ticker_directory()
    except MarketDataError as exc:
        raise PortfolioUpstreamError(f"SEC 公司目录请求失败：{exc}") from exc


def _parse_sec_directory(payload: dict[str, object]) -> list[SecUsListingCatalogItem]:
    fields = payload.get("fields")
    rows = payload.get("data")
    if not isinstance(fields, list) or not isinstance(rows, list):
        raise PortfolioUpstreamError("SEC 公司目录数据结构异常。")
    required = {"cik", "name", "ticker", "exchange"}
    indexes = {
        field_name: fields.index(field_name)
        for field_name in required
        if field_name in fields
    }
    if set(indexes) != required:
        raise PortfolioUpstreamError("SEC 公司目录缺少必要字段。")

    items: list[SecUsListingCatalogItem] = []
    for row in rows:
        if not isinstance(row, list) or len(row) < len(fields):
            continue
        exchange = _normalize_sec_exchange(str(row[indexes["exchange"]] or ""))
        if exchange is None:
            continue
        symbol = _normalize_sec_symbol(str(row[indexes["ticker"]] or ""))
        company_name = str(row[indexes["name"]] or "").strip()
        try:
            cik = _normalize_cik(str(row[indexes["cik"]]))
        except (TypeError, ValueError):
            continue
        if not symbol or not company_name:
            continue
        items.append(
            SecUsListingCatalogItem(
                cik=cik,
                company_name=company_name,
                symbol=symbol,
                ticker=f"{symbol}.US",
                exchange=exchange,
            )
        )
    return items


def _find_company_by_sec_cik(session: Session, cik: str) -> Company | None:
    for company in session.scalars(select(Company)):
        company_cik = (company.external_ids or {}).get("sec_cik")
        if company_cik is not None and _normalize_cik(str(company_cik)) == cik:
            return company
    for listing in session.scalars(
        select(SecurityListing).options(joinedload(SecurityListing.company))
    ):
        listing_cik = (listing.provider_identifiers or {}).get("sec_cik")
        if listing_cik is not None and _normalize_cik(str(listing_cik)) == cik:
            return listing.company
    return None


def _normalize_cik(value: str) -> str:
    normalized = value.strip()
    if not normalized.isdigit():
        raise ValueError("CIK 必须是数字。")
    return f"{int(normalized):010d}"


def _normalize_sec_exchange(value: str) -> str | None:
    return SEC_EXCHANGE_MAP.get(value.strip().casefold())


def _normalize_sec_symbol(value: str) -> str:
    return value.strip().upper().replace("-", ".")


def _normalize_search_text(value: str) -> str:
    return "".join(character for character in value.casefold() if character.isalnum())


def _normalize_catalog_us_symbol(value: str) -> str:
    return value.strip().upper().replace(".", "_").replace("-", "_")


def _validate_quantity(listing: SecurityListing, quantity: Decimal) -> None:
    if quantity <= 0:
        raise PortfolioValidationError("持有数量必须大于 0。")
    if listing.market in {"A_SHARE", "HK"} and quantity != quantity.to_integral_value():
        raise PortfolioValidationError("A 股和港股持有数量必须为整数证券单位。")


def _commit_holding(session: Session) -> None:
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise PortfolioConflictError("同一快照内不能重复添加同一 Listing。") from exc


def _decimal(value: float | int | str | Decimal) -> Decimal:
    return value if isinstance(value, Decimal) else Decimal(str(value))


def _quote_as_of(value: datetime, source: str) -> datetime:
    if value.tzinfo is not None:
        return value
    timezone = SHANGHAI_TZ if "eastmoney" in source.lower() else UTC
    return value.replace(tzinfo=timezone)
