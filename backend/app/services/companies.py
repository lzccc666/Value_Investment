from datetime import UTC, datetime

from sqlalchemy import String, and_, cast, delete, func, or_, select
from sqlalchemy.orm import Session

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
from app.db.models import Announcement, Company, FinancialStatement
from app.schemas.company import CompanyCreate
from app.services.financial_metrics import order_financial_statement_query

ANNOUNCEMENT_RETENTION_LIMIT = 50


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
                Company.exchange.ilike(like),
                Company.industry.ilike(like),
                Company.description.ilike(like),
                cast(Company.tags, String).ilike(like),
            )
        )

    base_stmt = select(Company)
    if filters:
        base_stmt = base_stmt.where(*filters)

    total_stmt = select(func.count()).select_from(Company)
    if filters:
        total_stmt = total_stmt.where(*filters)

    items = session.scalars(base_stmt.order_by(Company.name).offset(offset).limit(limit)).all()
    total = session.scalar(total_stmt) or 0
    return items, total


def get_company(session: Session, company_id: int) -> Company | None:
    return session.get(Company, company_id)


def refresh_company_profile(
    session: Session,
    company: Company,
    data_client: EastmoneyCompanyProfileClient | None = None,
) -> tuple[Company, bool]:
    client = data_client or EastmoneyCompanyProfileClient()
    fetched_profile = client.fetch_company_profile(company.ticker)
    updated = False

    if company.listed_date is None and fetched_profile.listed_date is not None:
        company.listed_date = fetched_profile.listed_date
        updated = True

    if fetched_profile.description is not None and _should_replace_company_description(company):
        company.description = fetched_profile.description
        updated = True

    if not updated:
        return company, False

    session.commit()
    session.refresh(company)
    return company, True


def refresh_company_market_snapshot(
    session: Session,
    company: Company,
    data_client: EastmoneyMarketSnapshotClient | None = None,
) -> Company:
    client = data_client or EastmoneyMarketSnapshotClient()
    fetched_snapshot = client.fetch_market_snapshot(company.ticker)
    company.market_cap = fetched_snapshot.market_cap
    company.current_price = fetched_snapshot.current_price
    company.pe_ttm = fetched_snapshot.pe_ttm
    company.pe_dynamic = fetched_snapshot.pe_dynamic
    company.pe_static = fetched_snapshot.pe_static
    company.pb_ratio = fetched_snapshot.pb_ratio
    company.ps_ratio = fetched_snapshot.ps_ratio
    company.dividend_yield_ttm = fetched_snapshot.dividend_yield_ttm
    company.dividend_yield_static = fetched_snapshot.dividend_yield_static
    company.market_data_source = fetched_snapshot.source
    company.market_data_source_url = fetched_snapshot.source_url
    company.market_data_updated_at = fetched_snapshot.fetched_at
    session.commit()
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
    company = Company(
        ticker=payload.ticker.upper(),
        exchange=payload.exchange.upper(),
        name=payload.name,
        industry=payload.industry,
        description=payload.description,
        listed_date=payload.listed_date,
        status=payload.status,
        tags=payload.tags,
    )
    session.add(company)
    session.commit()
    session.refresh(company)
    return company


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
) -> tuple[list[FinancialStatement], int, int, int]:
    client = data_client or EastmoneyFinancialClient()
    fetch_financials = getattr(client, "fetch_financials", None)
    if callable(fetch_financials):
        fetched_statements = fetch_financials(company.ticker, limit=limit)
    else:
        fetched_statements = client.fetch_main_financials(company.ticker, limit=limit)

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
        )
        session.add(statement)
        return statement, True

    statement.currency = fetched_statement.currency
    statement.fields = fetched_statement.fields
    statement.source = fetched_statement.source
    statement.source_url = fetched_statement.source_url
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
) -> tuple[list[Announcement], int, int, int, int, int, list[str]]:
    client = data_client or EastmoneyAnnouncementClient()
    fetched_announcements = client.fetch_announcements(
        company.ticker,
        years=years,
        limit=ANNOUNCEMENT_RETENTION_LIMIT,
    )
    published_since = _announcement_window_start(years)

    changed_items: list[Announcement] = []
    created = 0
    updated = 0
    skipped = 0
    errors: list[str] = []

    for fetched_announcement in fetched_announcements:
        try:
            announcement, action = _upsert_announcement(session, company.id, fetched_announcement)
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
    pruned = _prune_company_announcements_before(session, company.id, published_since)
    pruned += _prune_company_announcements_over_limit(
        session,
        company.id,
        limit=ANNOUNCEMENT_RETENTION_LIMIT,
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
    session: Session, company_id: int, published_since: datetime
) -> int:
    result = session.execute(
        delete(Announcement)
        .where(
            Announcement.company_id == company_id,
            Announcement.published_at < published_since,
        )
        .execution_options(synchronize_session=False)
    )
    return result.rowcount or 0


def _prune_company_announcements_over_limit(
    session: Session,
    company_id: int,
    *,
    limit: int,
) -> int:
    if limit < 1:
        return 0

    keep_ids = session.scalars(
        select(Announcement.id)
        .where(Announcement.company_id == company_id)
        .order_by(Announcement.published_at.desc(), Announcement.id.desc())
        .limit(limit)
    ).all()
    total = (
        session.scalar(
            select(func.count())
            .select_from(Announcement)
            .where(Announcement.company_id == company_id)
        )
        or 0
    )
    if total <= len(keep_ids):
        return 0

    result = session.execute(
        delete(Announcement)
        .where(
            Announcement.company_id == company_id,
            Announcement.id.not_in(keep_ids),
        )
        .execution_options(synchronize_session=False)
    )
    return result.rowcount or 0


def _upsert_announcement(
    session: Session, company_id: int, fetched_announcement: FetchedAnnouncement
) -> tuple[Announcement, str]:
    announcement = _find_existing_announcement(session, company_id, fetched_announcement)
    if announcement is None:
        announcement = Announcement(
            company_id=company_id,
            title=fetched_announcement.title,
            published_at=fetched_announcement.published_at,
            category=fetched_announcement.category,
            source=fetched_announcement.source,
            source_url=fetched_announcement.source_url,
            raw_url=fetched_announcement.raw_url,
        )
        session.add(announcement)
        return announcement, "created"

    if _reset_stale_eastmoney_page_shell_announcement(announcement, fetched_announcement):
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
