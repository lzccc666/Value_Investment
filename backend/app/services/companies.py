import hashlib
import json
from datetime import UTC, datetime

from sqlalchemy import String, and_, case, cast, delete, func, or_, select
from sqlalchemy.orm import Session

from app.configuration.runtime import parameter_value
from app.data_sources.announcement_content import (
    EASTMONEY_PAGE_SHELL_MARKERS,
    looks_like_eastmoney_page_shell,
)
from app.data_sources.eastmoney_announcements import (
    EastmoneyAnnouncementClient,
    FetchedAnnouncement,
)
from app.data_sources.eastmoney_company_profile import (
    EastmoneyCompanyProfileClient,
)
from app.data_sources.eastmoney_financials import (
    EastmoneyFinancialClient,
    FetchedFinancialStatement,
)
from app.data_sources.eastmoney_market_snapshot import (
    EastmoneyMarketSnapshotClient,
)
from app.db.models import Announcement, Company, FinancialStatement, MarketSnapshot, SecurityListing
from app.market_data.contracts import MarketContext, MarketDataValidationError
from app.market_data.registry import default_registry
from app.schemas.company import CompanyCreate, SecurityListingCreate
from app.services.financial_metrics import order_financial_statement_query

ANNOUNCEMENT_RETENTION_LIMIT = 50

COMPANY_MARKET_ORDER = case(
    (Company.exchange.in_(["SSE", "SZSE", "BSE"]), 0),
    (Company.exchange == "HKEX", 1),
    (Company.exchange.in_(["NASDAQ", "NYSE", "AMEX"]), 2),
    else_=3,
)


def list_companies(
    session: Session, query: str | None = None, limit: int = 20, offset: int = 0
) -> tuple[list[Company], int]:
    filters = []
    normalized_query = query.strip() if query else None
    if normalized_query:
        like = f"%{normalized_query}%"
        filters.append(
            or_(
                Company.ticker.ilike(like),
                Company.name.ilike(like),
                Company.legal_name.ilike(like),
                Company.exchange.ilike(like),
                Company.industry.ilike(like),
                Company.description.ilike(like),
                cast(Company.tags, String).ilike(like),
                cast(Company.aliases, String).ilike(like),
                select(SecurityListing.id)
                .where(
                    SecurityListing.company_id == Company.id,
                    or_(
                        SecurityListing.ticker.ilike(like),
                        SecurityListing.symbol.ilike(like),
                        SecurityListing.exchange.ilike(like),
                        SecurityListing.market.ilike(like),
                    ),
                )
                .exists(),
            )
        )

    base_stmt = select(Company)
    if filters:
        base_stmt = base_stmt.where(*filters)

    total_stmt = select(func.count()).select_from(Company)
    if filters:
        total_stmt = total_stmt.where(*filters)

    items = session.scalars(
        base_stmt.order_by(Company.name, COMPANY_MARKET_ORDER, Company.ticker)
        .offset(offset)
        .limit(limit)
    ).all()
    total = session.scalar(total_stmt) or 0
    return items, total


def get_company(session: Session, company_id: int) -> Company | None:
    return session.get(Company, company_id)


def refresh_company_profile(
    session: Session,
    company: Company,
    data_client: EastmoneyCompanyProfileClient | None = None,
) -> tuple[Company, bool]:
    listing = get_primary_listing(session, company.id)
    if listing is None:
        raise MarketDataValidationError("公司没有可用的主 Listing。")
    if data_client is not None:
        fetched_profile = data_client.fetch_company_profile(listing.ticker)
    else:
        provider = default_registry.resolve(listing.market).profile
        if provider is None:
            raise MarketDataValidationError("当前市场没有可用的发行人档案 Provider。")
        fetched_profile = provider.fetch_profile(build_market_context(company, listing))
    updated = False

    if company.listed_date is None and fetched_profile.listed_date is not None:
        company.listed_date = fetched_profile.listed_date
        listing.listed_date = fetched_profile.listed_date
        updated = True

    if fetched_profile.description is not None and _should_replace_company_description(company):
        company.description = fetched_profile.description
        updated = True

    updated = _apply_issuer_profile_fields(company, fetched_profile) or updated

    if not updated:
        return company, False

    session.commit()
    session.refresh(company)
    return company, True


def refresh_listing_profile(
    session: Session,
    listing: SecurityListing,
    data_client: EastmoneyCompanyProfileClient | None = None,
) -> tuple[Company, bool]:
    company = session.get(Company, listing.company_id)
    if company is None:
        raise MarketDataValidationError("Listing 对应的发行人不存在。")
    if data_client is not None:
        fetched_profile = data_client.fetch_company_profile(listing.ticker)
    else:
        provider = default_registry.resolve(listing.market).profile
        if provider is None:
            raise MarketDataValidationError("当前市场没有可用的发行人档案 Provider。")
        fetched_profile = provider.fetch_profile(build_market_context(company, listing))
    updated = False
    if listing.listed_date is None and fetched_profile.listed_date is not None:
        listing.listed_date = fetched_profile.listed_date
        if listing.is_primary:
            company.listed_date = fetched_profile.listed_date
        updated = True
    if fetched_profile.description is not None and _should_replace_company_description(company):
        company.description = fetched_profile.description
        updated = True
    updated = _apply_issuer_profile_fields(company, fetched_profile) or updated
    if updated:
        session.commit()
        session.refresh(company)
    return company, updated


def _apply_issuer_profile_fields(company: Company, fetched_profile: object) -> bool:
    updated = False
    for field_name in (
        "legal_name",
        "domicile_country",
        "reporting_currency",
        "fiscal_year_end",
    ):
        value = getattr(fetched_profile, field_name, None)
        if value and getattr(company, field_name) != value:
            setattr(company, field_name, value)
            updated = True
    aliases = list(getattr(fetched_profile, "aliases", ()) or ())
    if aliases and company.aliases != aliases:
        company.aliases = aliases
        updated = True
    external_ids = getattr(fetched_profile, "external_ids", None)
    if isinstance(external_ids, dict) and external_ids and company.external_ids != external_ids:
        company.external_ids = external_ids
        updated = True
    return updated


def refresh_company_market_snapshot(
    session: Session,
    company: Company,
    data_client: EastmoneyMarketSnapshotClient | None = None,
) -> Company:
    listing = get_primary_listing(session, company.id)
    if listing is None:
        raise MarketDataValidationError("公司没有可用的主 Listing。")
    refresh_listing_market_snapshot(session, listing, data_client=data_client)
    session.refresh(company)
    return company


def _should_replace_company_description(company: Company) -> bool:
    description = (company.description or "").strip()
    if not description:
        return True
    if "真实公司主数据种子" in description:
        return True
    if "不包含实时行情或投资建议" in description:
        return True
    return False


def get_company_financial_statement(
    session: Session, company_id: int, statement_id: int
) -> FinancialStatement | None:
    return session.scalar(
        select(FinancialStatement).where(
            FinancialStatement.id == statement_id,
            FinancialStatement.company_id == company_id,
        )
    )


def get_company_by_identity(session: Session, ticker: str, exchange: str) -> Company | None:
    return session.scalar(
        select(Company).where(
            Company.ticker == ticker.strip().upper(),
            Company.exchange == exchange.strip().upper(),
        )
    )


def create_company(session: Session, payload: CompanyCreate) -> Company:
    ticker = payload.ticker.upper()
    exchange = payload.exchange.upper()
    market, trading_currency, domicile_country = listing_defaults(exchange)
    canonical_key = f"issuer-{exchange.lower()}-{ticker.lower().replace('.', '-')}"
    company = Company(
        ticker=ticker,
        exchange=exchange,
        name=payload.name,
        canonical_key=canonical_key,
        legal_name=payload.legal_name or payload.name,
        aliases=payload.aliases or [payload.name],
        domicile_country=payload.domicile_country or domicile_country,
        reporting_currency=payload.reporting_currency or trading_currency,
        fiscal_year_end=payload.fiscal_year_end or "12-31",
        external_ids={},
        industry=payload.industry,
        description=payload.description,
        listed_date=payload.listed_date,
        status=payload.status,
        tags=payload.tags,
    )
    session.add(company)
    session.flush()
    session.add(
        SecurityListing(
            company_id=company.id,
            ticker=ticker,
            symbol=ticker.rsplit(".", 1)[0],
            exchange=exchange,
            market=market,
            trading_currency=trading_currency,
            security_type="common_stock",
            listed_date=payload.listed_date,
            is_primary=True,
            is_active=True,
            underlying_shares_per_listing_unit=1.0,
            provider_identifiers={},
        )
    )
    session.commit()
    session.refresh(company)
    return company


def list_company_listings(session: Session, company_id: int) -> list[SecurityListing]:
    return list(
        session.scalars(
            select(SecurityListing)
            .where(SecurityListing.company_id == company_id)
            .order_by(
                SecurityListing.is_primary.desc(),
                SecurityListing.is_active.desc(),
                SecurityListing.exchange,
                SecurityListing.ticker,
            )
        )
    )


def get_listing(session: Session, listing_id: int) -> SecurityListing | None:
    return session.get(SecurityListing, listing_id)


def get_primary_listing(session: Session, company_id: int) -> SecurityListing | None:
    return session.scalar(
        select(SecurityListing)
        .where(
            SecurityListing.company_id == company_id,
            SecurityListing.is_primary.is_(True),
            SecurityListing.is_active.is_(True),
        )
        .limit(1)
    )


def _resolve_company_listing(
    session: Session, company: Company, listing_id: int | None
) -> SecurityListing:
    listing = (
        get_listing(session, listing_id)
        if listing_id is not None
        else get_primary_listing(session, company.id)
    )
    if listing is None:
        raise MarketDataValidationError("公司没有可用的 Listing。")
    if listing.company_id != company.id:
        raise MarketDataValidationError("Listing 不属于当前公司。")
    if not listing.is_active:
        raise MarketDataValidationError("Listing 已停用。")
    if listing.security_type not in {"common_stock", "ads"}:
        raise MarketDataValidationError("当前证券类型不在 014 首轮完整链路范围内。")
    return listing


def create_company_listing(
    session: Session, company: Company, payload: SecurityListingCreate
) -> SecurityListing:
    if payload.security_type not in {"COMMON_STOCK", "ADS"}:
        raise ValueError("首轮只允许 common_stock 或 ads Listing。")
    market, currency, _ = listing_defaults(payload.exchange)
    resolved_market = payload.market or market
    resolved_currency = payload.trading_currency or currency
    ratio = payload.underlying_shares_per_listing_unit
    if payload.security_type == "COMMON_STOCK" and ratio is None:
        ratio = 1.0
    listing = SecurityListing(
        company_id=company.id,
        ticker=payload.ticker,
        symbol=payload.symbol or payload.ticker.rsplit(".", 1)[0],
        exchange=payload.exchange,
        market=resolved_market,
        trading_currency=resolved_currency,
        security_type=payload.security_type.lower(),
        listed_date=payload.listed_date,
        is_primary=False,
        is_active=True,
        underlying_shares_per_listing_unit=ratio,
        provider_identifiers=payload.provider_identifiers,
    )
    session.add(listing)
    session.flush()
    if payload.is_primary:
        set_primary_listing(session, company, listing)
    session.commit()
    session.refresh(listing)
    return listing


def set_primary_listing(
    session: Session, company: Company, listing: SecurityListing
) -> SecurityListing:
    if listing.company_id != company.id or not listing.is_active:
        raise ValueError("主 Listing 必须属于当前公司且处于启用状态。")
    for item in list_company_listings(session, company.id):
        if item.is_primary and item.id != listing.id:
            item.is_primary = False
    session.flush()
    listing.is_primary = True
    latest_snapshot = get_latest_market_snapshot(session, listing.id)
    _sync_company_market_mirror(session, company, listing, latest_snapshot)
    session.commit()
    session.refresh(listing)
    return listing


def build_market_context(company: Company, listing: SecurityListing) -> MarketContext:
    return MarketContext(
        company_id=company.id,
        canonical_key=company.canonical_key,
        issuer_name=company.name,
        aliases=tuple(company.aliases or []),
        reporting_currency=company.reporting_currency,
        fiscal_year_end=company.fiscal_year_end,
        listing_id=listing.id,
        ticker=listing.ticker,
        symbol=listing.symbol,
        exchange=listing.exchange,
        market=listing.market,
        trading_currency=listing.trading_currency,
        security_type=listing.security_type,
        provider_identifiers=dict(listing.provider_identifiers or {}),
    )


def get_latest_market_snapshot(session: Session, listing_id: int) -> MarketSnapshot | None:
    return session.scalar(
        select(MarketSnapshot)
        .where(MarketSnapshot.listing_id == listing_id)
        .order_by(MarketSnapshot.fetched_at.desc(), MarketSnapshot.id.desc())
        .limit(1)
    )


def refresh_listing_market_snapshot(
    session: Session,
    listing: SecurityListing,
    *,
    data_client: EastmoneyMarketSnapshotClient | None = None,
) -> MarketSnapshot:
    company = session.get(Company, listing.company_id)
    if company is None:
        raise MarketDataValidationError("Listing 对应的发行人不存在。")
    context = build_market_context(company, listing)
    if data_client is not None:
        fetched = data_client.fetch_market_snapshot(listing.ticker)
    else:
        provider = default_registry.resolve(listing.market).quote
        if provider is None:
            raise MarketDataValidationError("当前市场没有可用的行情 Provider。")
        fetched = provider.fetch_market_snapshot(context)
    if fetched.current_price is None or fetched.current_price <= 0:
        raise MarketDataValidationError("行情 Provider 没有返回有效的正数价格。")
    snapshot_payload = {
        "listing_id": listing.id,
        "price": fetched.current_price,
        "currency": listing.trading_currency,
        "fetched_at": fetched.fetched_at.isoformat(),
        "source": fetched.source,
    }
    raw_hash = hashlib.sha256(
        json.dumps(snapshot_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    snapshot = MarketSnapshot(
        listing_id=listing.id,
        price=fetched.current_price,
        currency=listing.trading_currency,
        market_cap=fetched.market_cap,
        pe_ttm=fetched.pe_ttm,
        pe_dynamic=fetched.pe_dynamic,
        pe_static=fetched.pe_static,
        pb_ratio=fetched.pb_ratio,
        ps_ratio=fetched.ps_ratio,
        dividend_yield_ttm=fetched.dividend_yield_ttm,
        dividend_yield_static=fetched.dividend_yield_static,
        price_as_of=fetched.fetched_at,
        fetched_at=fetched.fetched_at,
        source=fetched.source,
        source_url=fetched.source_url,
        raw_snapshot_hash=raw_hash,
    )
    session.add(snapshot)
    session.flush()
    if listing.is_primary:
        _sync_company_market_mirror(session, company, listing, snapshot)
    session.commit()
    session.refresh(snapshot)
    return snapshot


def _sync_company_market_mirror(
    session: Session,
    company: Company,
    listing: SecurityListing,
    snapshot: MarketSnapshot | None,
) -> None:
    company.ticker = listing.ticker
    company.exchange = listing.exchange
    company.listed_date = listing.listed_date
    if snapshot is None:
        for field in (
            "market_cap",
            "current_price",
            "pe_ttm",
            "pe_dynamic",
            "pe_static",
            "pb_ratio",
            "ps_ratio",
            "dividend_yield_ttm",
            "dividend_yield_static",
            "market_data_source",
            "market_data_source_url",
            "market_data_updated_at",
        ):
            setattr(company, field, None)
        return
    company.market_cap = snapshot.market_cap
    company.current_price = snapshot.price
    company.pe_ttm = snapshot.pe_ttm
    company.pe_dynamic = snapshot.pe_dynamic
    company.pe_static = snapshot.pe_static
    company.pb_ratio = snapshot.pb_ratio
    company.ps_ratio = snapshot.ps_ratio
    company.dividend_yield_ttm = snapshot.dividend_yield_ttm
    company.dividend_yield_static = snapshot.dividend_yield_static
    company.market_data_source = snapshot.source
    company.market_data_source_url = snapshot.source_url
    company.market_data_updated_at = snapshot.fetched_at


def listing_defaults(exchange: str) -> tuple[str, str, str]:
    normalized = exchange.strip().upper()
    if normalized in {"SSE", "SZSE", "BSE"}:
        return "A_SHARE", "CNY", "CN"
    if normalized == "HKEX":
        return "HK", "HKD", "HK"
    if normalized in {"NASDAQ", "NYSE", "AMEX"}:
        return "US", "USD", "US"
    return "OTHER", "XXX", "ZZ"


def list_company_financials(
    session: Session, company_id: int, limit: int = 60, offset: int = 0
) -> tuple[list[FinancialStatement], int]:
    base_stmt = select(FinancialStatement).where(FinancialStatement.company_id == company_id)
    total_stmt = (
        select(func.count())
        .select_from(FinancialStatement)
        .where(FinancialStatement.company_id == company_id)
    )
    items = session.scalars(
        order_financial_statement_query(base_stmt).offset(offset).limit(limit)
    ).all()
    total = session.scalar(total_stmt) or 0
    return items, total


def list_company_financials_by_periods(
    session: Session, company_id: int, period_limit: int = 60, period_offset: int = 0
) -> tuple[list[FinancialStatement], int]:
    statements = session.scalars(
        order_financial_statement_query(
            select(FinancialStatement).where(FinancialStatement.company_id == company_id)
        )
    ).all()
    selected_periods: list[str] = []

    for statement in statements:
        if statement.period in selected_periods:
            continue
        if len(selected_periods) < period_offset:
            selected_periods.append(statement.period)
            continue
        if len(selected_periods) >= period_offset + period_limit:
            break
        selected_periods.append(statement.period)

    visible_periods = set(selected_periods[period_offset : period_offset + period_limit])
    items = [statement for statement in statements if statement.period in visible_periods]
    return items, len(statements)


def delete_company_financial_statement(session: Session, statement: FinancialStatement) -> None:
    session.delete(statement)
    session.commit()


def sync_company_financials(
    session: Session,
    company: Company,
    data_client: EastmoneyFinancialClient | None = None,
    limit: int = 60,
    listing_id: int | None = None,
) -> tuple[list[FinancialStatement], int, int, int]:
    if data_client is not None:
        fetch_financials = getattr(data_client, "fetch_financials", None)
        if callable(fetch_financials):
            fetched_statements = fetch_financials(company.ticker, limit=limit)
        else:
            fetched_statements = data_client.fetch_main_financials(company.ticker, limit=limit)
    else:
        listing = _resolve_company_listing(session, company, listing_id)
        provider = default_registry.resolve(listing.market).financials
        if provider is None:
            raise MarketDataValidationError("当前市场没有可用的结构化财务 Provider。")
        fetched_statements = provider.fetch_financials(
            build_market_context(company, listing), limit=limit
        )

    currencies = {item.currency.strip().upper() for item in fetched_statements if item.currency}
    if len(currencies) > 1:
        raise MarketDataValidationError("同一次财务同步返回了混合币种，已阻止写入。")
    if currencies and company.reporting_currency and currencies != {company.reporting_currency}:
        raise MarketDataValidationError(
            "财务币种与发行人 reporting_currency 不一致，已阻止混合口径写入。"
        )

    changed_items: list[FinancialStatement] = []
    created = 0
    updated = 0

    for fetched_statement in fetched_statements:
        statement, was_created = _upsert_financial_statement(session, company.id, fetched_statement)
        changed_items.append(statement)
        if was_created:
            created += 1
        else:
            updated += 1

    session.commit()
    for item in changed_items:
        session.refresh(item)

    return changed_items, len(fetched_statements), created, updated


def _upsert_financial_statement(
    session: Session, company_id: int, fetched_statement: FetchedFinancialStatement
) -> tuple[FinancialStatement, bool]:
    statement = session.scalar(
        select(FinancialStatement).where(
            FinancialStatement.company_id == company_id,
            FinancialStatement.period == fetched_statement.period,
            FinancialStatement.statement_type == fetched_statement.statement_type,
        )
    )

    if statement is None:
        statement = FinancialStatement(
            company_id=company_id,
            period=fetched_statement.period,
            statement_type=fetched_statement.statement_type,
            currency=fetched_statement.currency,
            fields=fetched_statement.fields,
            source=fetched_statement.source,
            source_url=fetched_statement.source_url,
            source_record_id=getattr(fetched_statement, "source_record_id", None),
            filing_type=getattr(fetched_statement, "filing_type", None),
            taxonomy=getattr(fetched_statement, "taxonomy", None),
            period_start=getattr(fetched_statement, "period_start", None),
            period_end=getattr(fetched_statement, "period_end", None),
            period_type=getattr(fetched_statement, "period_type", None),
            fiscal_year=getattr(fetched_statement, "fiscal_year", None),
            fiscal_period=getattr(fetched_statement, "fiscal_period", None),
            filed_at=getattr(fetched_statement, "filed_at", None),
            unit_scale=getattr(fetched_statement, "unit_scale", 1.0),
            is_amendment=getattr(fetched_statement, "is_amendment", False),
            raw_snapshot_hash=getattr(fetched_statement, "raw_snapshot_hash", None),
        )
        session.add(statement)
        return statement, True

    statement.currency = fetched_statement.currency
    statement.fields = fetched_statement.fields
    statement.source = fetched_statement.source
    statement.source_url = fetched_statement.source_url
    statement.source_record_id = getattr(fetched_statement, "source_record_id", None)
    statement.filing_type = getattr(fetched_statement, "filing_type", None)
    statement.taxonomy = getattr(fetched_statement, "taxonomy", None)
    statement.period_start = getattr(fetched_statement, "period_start", None)
    statement.period_end = getattr(fetched_statement, "period_end", None)
    statement.period_type = getattr(fetched_statement, "period_type", None)
    statement.fiscal_year = getattr(fetched_statement, "fiscal_year", None)
    statement.fiscal_period = getattr(fetched_statement, "fiscal_period", None)
    statement.filed_at = getattr(fetched_statement, "filed_at", None)
    statement.unit_scale = getattr(fetched_statement, "unit_scale", 1.0)
    statement.is_amendment = getattr(fetched_statement, "is_amendment", False)
    statement.raw_snapshot_hash = getattr(fetched_statement, "raw_snapshot_hash", None)
    return statement, False


def list_company_announcements(
    session: Session, company_id: int, limit: int | None = 20, offset: int = 0
) -> tuple[list[Announcement], int]:
    base_stmt = select(Announcement).where(Announcement.company_id == company_id)
    total_stmt = (
        select(func.count()).select_from(Announcement).where(Announcement.company_id == company_id)
    )

    items_stmt = base_stmt.order_by(Announcement.published_at.desc()).offset(offset)
    if limit is not None:
        items_stmt = items_stmt.limit(limit)

    items = session.scalars(items_stmt).all()
    total = session.scalar(total_stmt) or 0
    return items, total


def list_company_announcements_for_summary(
    session: Session,
    *,
    company_id: int,
    limit: int,
    only_missing: bool = True,
    include_failed: bool = True,
    exclude_deep_summarized: bool = False,
) -> tuple[list[Announcement], int]:
    filters = [Announcement.company_id == company_id]
    if exclude_deep_summarized:
        filters.append(
            or_(
                Announcement.summary_model_name.is_(None),
                Announcement.summary_model_name == "metadata_keyword",
            )
        )
    if only_missing:
        eligible_statuses = ["unprocessed", "processing"]
        if include_failed:
            eligible_statuses.append("failed")
        filters.append(
            or_(
                Announcement.summary.is_(None),
                Announcement.summary_status.in_(eligible_statuses),
            )
        )

    base_stmt = select(Announcement).where(*filters)
    total_stmt = select(func.count()).select_from(Announcement).where(*filters)

    items = session.scalars(
        base_stmt.order_by(Announcement.published_at.desc(), Announcement.id.desc()).limit(limit)
    ).all()
    total = session.scalar(total_stmt) or 0
    return items, total


def list_company_announcements_for_deep_summary(
    session: Session,
    *,
    company_id: int,
    limit: int,
) -> tuple[list[Announcement], int]:
    stale_page_shell_filter = or_(
        *[Announcement.raw_content.ilike(f"%{marker}%") for marker in EASTMONEY_PAGE_SHELL_MARKERS],
        *[Announcement.content.ilike(f"%{marker}%") for marker in EASTMONEY_PAGE_SHELL_MARKERS],
    )
    filters = [
        Announcement.company_id == company_id,
        or_(
            Announcement.summary_model_name.is_(None),
            Announcement.summary_model_name == "metadata_keyword",
            and_(
                Announcement.summary_model_name.is_not(None),
                Announcement.summary_model_name != "metadata_keyword",
                stale_page_shell_filter,
            ),
        ),
    ]
    base_stmt = select(Announcement).where(*filters)
    total_stmt = select(func.count()).select_from(Announcement).where(*filters)

    items = session.scalars(
        base_stmt.order_by(Announcement.published_at.desc(), Announcement.id.desc()).limit(limit)
    ).all()
    total = session.scalar(total_stmt) or 0
    return items, total


def get_company_announcement(
    session: Session, company_id: int, announcement_id: int
) -> Announcement | None:
    return session.scalar(
        select(Announcement).where(
            Announcement.company_id == company_id,
            Announcement.id == announcement_id,
        )
    )


def delete_company_announcement(session: Session, announcement: Announcement) -> None:
    session.delete(announcement)
    session.commit()


def sync_company_announcements(
    session: Session,
    company: Company,
    data_client: EastmoneyAnnouncementClient | None = None,
    years: int = 1,
    listing_id: int | None = None,
) -> tuple[list[Announcement], int, int, int, int, int, list[str]]:
    listing = _resolve_company_listing(session, company, listing_id)
    retention_limit = int(parameter_value("data_sampling.announcement_retention_limit", 50))
    if data_client is not None:
        fetched_announcements = data_client.fetch_announcements(
            listing.ticker,
            years=years,
            limit=retention_limit,
        )
    else:
        bundle = default_registry.resolve(listing.market)
        provider = bundle.disclosures
        if provider is None:
            raise MarketDataValidationError("当前市场没有可用的官方披露 Provider。")
        fetched_announcements = provider.fetch_disclosures(
            build_market_context(company, listing), years=years, limit=retention_limit
        )
    published_since = _announcement_window_start(years)

    changed_items: list[Announcement] = []
    created = 0
    updated = 0
    skipped = 0
    errors: list[str] = []

    for fetched_announcement in fetched_announcements:
        try:
            announcement, action = _upsert_announcement(
                session,
                company.id,
                fetched_announcement,
                listing_id=listing.id,
            )
        except ValueError as exc:
            skipped += 1
            errors.append(str(exc))
            continue

        if action == "created":
            created += 1
            changed_items.append(announcement)
        elif action == "updated":
            updated += 1
            changed_items.append(announcement)
        else:
            skipped += 1

    session.flush()
    source = fetched_announcements[0].source if fetched_announcements else None
    use_partitioned_retention = data_client is None or listing_id is not None
    pruned = _prune_company_announcements_before(
        session,
        company.id,
        published_since,
        listing_id=listing.id if use_partitioned_retention else None,
        source=source if use_partitioned_retention else None,
    )
    pruned += _prune_company_announcements_over_limit(
        session,
        company.id,
        limit=retention_limit,
        listing_id=listing.id if use_partitioned_retention else None,
        source=source if use_partitioned_retention else None,
    )
    session.commit()
    changed_item_ids = [item.id for item in changed_items if item.id is not None]
    changed_items = []
    if changed_item_ids:
        changed_items = session.scalars(
            select(Announcement)
            .where(Announcement.id.in_(changed_item_ids))
            .order_by(Announcement.published_at.desc(), Announcement.id.desc())
        ).all()

    return changed_items, len(fetched_announcements), created, updated, skipped, pruned, errors


def _announcement_window_start(years: int, *, as_of: datetime | None = None) -> datetime:
    reference_time = as_of or datetime.now(UTC)
    if reference_time.tzinfo is None:
        reference_time = reference_time.replace(tzinfo=UTC)
    else:
        reference_time = reference_time.astimezone(UTC)
    try:
        start = reference_time.replace(year=reference_time.year - years)
    except ValueError:
        start = reference_time.replace(year=reference_time.year - years, month=2, day=28)
    return start.replace(hour=0, minute=0, second=0, microsecond=0)


def _prune_company_announcements_before(
    session: Session,
    company_id: int,
    published_since: datetime,
    *,
    listing_id: int | None = None,
    source: str | None = None,
) -> int:
    filters = [
        Announcement.company_id == company_id,
        Announcement.published_at < published_since,
    ]
    if listing_id is not None:
        filters.append(Announcement.listing_id == listing_id)
    if source is not None:
        filters.append(Announcement.source == source)
    result = session.execute(
        delete(Announcement).where(*filters).execution_options(synchronize_session=False)
    )
    return result.rowcount or 0


def _prune_company_announcements_over_limit(
    session: Session,
    company_id: int,
    *,
    limit: int,
    listing_id: int | None = None,
    source: str | None = None,
) -> int:
    if limit < 1:
        return 0

    filters = [Announcement.company_id == company_id]
    if listing_id is not None:
        filters.append(Announcement.listing_id == listing_id)
    if source is not None:
        filters.append(Announcement.source == source)
    keep_ids = session.scalars(
        select(Announcement.id)
        .where(*filters)
        .order_by(Announcement.published_at.desc(), Announcement.id.desc())
        .limit(limit)
    ).all()
    total = session.scalar(select(func.count()).select_from(Announcement).where(*filters)) or 0
    if total <= len(keep_ids):
        return 0

    result = session.execute(
        delete(Announcement)
        .where(*filters, Announcement.id.not_in(keep_ids))
        .execution_options(synchronize_session=False)
    )
    return result.rowcount or 0


def _upsert_announcement(
    session: Session,
    company_id: int,
    fetched_announcement: FetchedAnnouncement,
    *,
    listing_id: int | None = None,
) -> tuple[Announcement, str]:
    announcement = _find_existing_announcement(session, company_id, fetched_announcement)
    if announcement is None:
        announcement = Announcement(
            company_id=company_id,
            listing_id=listing_id,
            title=fetched_announcement.title,
            published_at=fetched_announcement.published_at,
            category=fetched_announcement.category,
            source=fetched_announcement.source,
            source_url=fetched_announcement.source_url,
            raw_url=fetched_announcement.raw_url,
            source_document_id=getattr(fetched_announcement, "source_document_id", None),
            document_type=getattr(fetched_announcement, "document_type", None),
            filing_form=getattr(fetched_announcement, "filing_form", None),
            language=getattr(fetched_announcement, "language", None),
            period_end=getattr(fetched_announcement, "period_end", None),
            content_type=getattr(fetched_announcement, "content_type", None),
        )
        session.add(announcement)
        return announcement, "created"

    if announcement.listing_id is None and listing_id is not None:
        announcement.listing_id = listing_id
    if _reset_stale_eastmoney_page_shell_announcement(announcement, fetched_announcement):
        return announcement, "updated"

    source_document_id = getattr(fetched_announcement, "source_document_id", None)
    if announcement.source == fetched_announcement.source and source_document_id:
        changed = False
        metadata = {
            "title": fetched_announcement.title,
            "published_at": fetched_announcement.published_at,
            "category": fetched_announcement.category,
            "source_url": fetched_announcement.source_url,
            "raw_url": fetched_announcement.raw_url,
            "source_document_id": source_document_id,
            "document_type": getattr(fetched_announcement, "document_type", None),
            "filing_form": getattr(fetched_announcement, "filing_form", None),
            "language": getattr(fetched_announcement, "language", None),
            "period_end": getattr(fetched_announcement, "period_end", None),
            "content_type": getattr(fetched_announcement, "content_type", None),
        }
        for field_name, next_value in metadata.items():
            if not _values_equal(getattr(announcement, field_name), next_value):
                setattr(announcement, field_name, next_value)
                changed = True
        if changed:
            return announcement, "updated"

    return announcement, "skipped"


def _reset_stale_eastmoney_page_shell_announcement(
    announcement: Announcement,
    fetched_announcement: FetchedAnnouncement,
) -> bool:
    if not (
        looks_like_eastmoney_page_shell(announcement.raw_content)
        or (not announcement.raw_content and looks_like_eastmoney_page_shell(announcement.content))
    ):
        return False

    announcement.title = fetched_announcement.title
    announcement.published_at = fetched_announcement.published_at
    announcement.category = fetched_announcement.category
    announcement.source = fetched_announcement.source
    announcement.source_url = fetched_announcement.source_url
    announcement.raw_url = fetched_announcement.raw_url
    announcement.source_document_id = getattr(fetched_announcement, "source_document_id", None)
    announcement.document_type = getattr(fetched_announcement, "document_type", None)
    announcement.filing_form = getattr(fetched_announcement, "filing_form", None)
    announcement.language = getattr(fetched_announcement, "language", None)
    announcement.period_end = getattr(fetched_announcement, "period_end", None)
    announcement.content_type = getattr(fetched_announcement, "content_type", None)
    announcement.content = None
    announcement.raw_content = None
    announcement.summary = None
    announcement.key_facts = []
    announcement.importance_score = None
    announcement.impact_direction = None
    announcement.sentiment = None
    announcement.positive_impacts = []
    announcement.negative_impacts = []
    announcement.neutral_impacts = []
    announcement.risk_tips = []
    announcement.review_questions = []
    announcement.tags = []
    announcement.summary_status = "unprocessed"
    announcement.summary_model_name = None
    announcement.summary_prompt_version = None
    announcement.summarized_at = None
    return True


def _values_equal(current_value: object, next_value: object) -> bool:
    if isinstance(current_value, datetime) and isinstance(next_value, datetime):
        return current_value.replace(tzinfo=None) == next_value.replace(tzinfo=None)
    return current_value == next_value


def _find_existing_announcement(
    session: Session, company_id: int, fetched_announcement: FetchedAnnouncement
) -> Announcement | None:
    source_document_id = getattr(fetched_announcement, "source_document_id", None)
    if source_document_id:
        announcement = session.scalar(
            select(Announcement).where(
                Announcement.company_id == company_id,
                Announcement.source == fetched_announcement.source,
                Announcement.source_document_id == source_document_id,
            )
        )
        if announcement is not None:
            return announcement
    if fetched_announcement.source_url:
        announcement = session.scalar(
            select(Announcement).where(
                Announcement.company_id == company_id,
                Announcement.source_url == fetched_announcement.source_url,
            )
        )
        if announcement is not None:
            return announcement

    return session.scalar(
        select(Announcement).where(
            Announcement.company_id == company_id,
            Announcement.title == fetched_announcement.title,
            Announcement.published_at == fetched_announcement.published_at,
        )
    )
