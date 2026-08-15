from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.analysis.model_gateway import (
    ModelGatewayError,
    ModelNotConfiguredError,
    ModelOutputValidationError,
)
from app.db.models import Company, InvestmentMemo
from app.db.session import get_db
from app.schemas.memo import (
    InvestmentMemoArchiveResponse,
    InvestmentMemoDeleteResponse,
    InvestmentMemoGenerateRequest,
    InvestmentMemoGenerateResponse,
    InvestmentMemoLatestResponse,
    InvestmentMemoListResponse,
    InvestmentMemoRead,
)
from app.services.companies import get_company
from app.services.memo_service import (
    InvestmentMemoInsufficientSourcesError,
    archive_investment_memo,
    delete_investment_memo,
    get_investment_memo,
    get_latest_company_investment_memo,
    list_company_investment_memos,
    run_company_investment_memo,
)

router = APIRouter()


@router.post(
    "/companies/{company_id}/investment-memos/generate",
    response_model=InvestmentMemoGenerateResponse,
)
def generate_company_investment_memo(
    company_id: int,
    payload: InvestmentMemoGenerateRequest,
    db: Annotated[Session, Depends(get_db)],
) -> InvestmentMemoGenerateResponse:
    company = _get_company_or_404(db, company_id)
    try:
        run, memo = run_company_investment_memo(
            db,
            company,
            user_note=payload.user_note,
        )
    except InvestmentMemoInsufficientSourcesError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except ModelNotConfiguredError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except ModelOutputValidationError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    except ModelGatewayError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    return InvestmentMemoGenerateResponse(company_id=company_id, run_id=run.id, memo=memo)


@router.get(
    "/companies/{company_id}/investment-memos/latest",
    response_model=InvestmentMemoLatestResponse,
)
def get_latest_company_investment_memo_item(
    company_id: int,
    db: Annotated[Session, Depends(get_db)],
) -> InvestmentMemoLatestResponse:
    _get_company_or_404(db, company_id)
    item = get_latest_company_investment_memo(db, company_id=company_id)
    return InvestmentMemoLatestResponse(company_id=company_id, item=item)


@router.get(
    "/companies/{company_id}/investment-memos",
    response_model=InvestmentMemoListResponse,
)
def get_company_investment_memos(
    company_id: int,
    db: Annotated[Session, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
    include_deleted: Annotated[bool, Query()] = False,
) -> InvestmentMemoListResponse:
    _get_company_or_404(db, company_id)
    items, total = list_company_investment_memos(
        db,
        company_id=company_id,
        limit=limit,
        offset=offset,
        include_deleted=include_deleted,
    )
    return InvestmentMemoListResponse(items=items, total=total, limit=limit, offset=offset)


@router.get("/investment-memos/{memo_id}", response_model=InvestmentMemoRead)
def get_investment_memo_item(
    memo_id: int,
    db: Annotated[Session, Depends(get_db)],
) -> InvestmentMemoRead:
    memo = _get_memo_or_404(db, memo_id)
    return memo


@router.post(
    "/investment-memos/{memo_id}/archive",
    response_model=InvestmentMemoArchiveResponse,
)
def archive_investment_memo_item(
    memo_id: int,
    db: Annotated[Session, Depends(get_db)],
) -> InvestmentMemoArchiveResponse:
    memo = _get_memo_or_404(db, memo_id)
    latest = archive_investment_memo(db, memo)
    return InvestmentMemoArchiveResponse(
        id=memo_id,
        archived=True,
        latest_memo_id=latest.id if latest else None,
    )


@router.delete(
    "/investment-memos/{memo_id}",
    response_model=InvestmentMemoDeleteResponse,
)
def delete_investment_memo_item(
    memo_id: int,
    db: Annotated[Session, Depends(get_db)],
) -> InvestmentMemoDeleteResponse:
    memo = _get_memo_or_404(db, memo_id)
    latest = delete_investment_memo(db, memo)
    return InvestmentMemoDeleteResponse(
        id=memo_id,
        deleted=True,
        latest_memo_id=latest.id if latest else None,
    )


def _get_company_or_404(db: Session, company_id: int) -> Company:
    company = get_company(db, company_id)
    if company is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found")
    return company


def _get_memo_or_404(db: Session, memo_id: int) -> InvestmentMemo:
    memo = get_investment_memo(db, memo_id)
    if memo is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Investment memo not found",
        )
    return memo
