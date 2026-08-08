from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.db.models import Company


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
            )
        )

    base_stmt = select(Company)
    if filters:
        base_stmt = base_stmt.where(*filters)

    total_stmt = select(func.count()).select_from(Company)
    if filters:
        total_stmt = total_stmt.where(*filters)

    items = session.scalars(
        base_stmt.order_by(Company.name).offset(offset).limit(limit)
    ).all()
    total = session.scalar(total_stmt) or 0
    return items, total


def get_company(session: Session, company_id: int) -> Company | None:
    return session.get(Company, company_id)
