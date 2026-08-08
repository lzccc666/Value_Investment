from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.company import CompanyListResponse, CompanyRead
from app.services.companies import get_company, list_companies

router = APIRouter(prefix="/companies")


@router.get("", response_model=CompanyListResponse)
def get_companies(
    db: Annotated[Session, Depends(get_db)],
    q: Annotated[str | None, Query(description="按代码、名称、交易所或行业筛选")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> CompanyListResponse:
    items, total = list_companies(db, query=q, limit=limit, offset=offset)
    return CompanyListResponse(items=items, total=total, limit=limit, offset=offset)


@router.get("/{company_id}", response_model=CompanyRead)
def get_company_detail(
    company_id: int, db: Annotated[Session, Depends(get_db)]
) -> CompanyRead:
    company = get_company(db, company_id)
    if company is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found")
    return company
