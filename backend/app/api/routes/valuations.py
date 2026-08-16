from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.models import Company, ValuationRun
from app.db.session import get_db
from app.schemas.valuation import (
    ValuationDraftRequest,
    ValuationRecalculateRequest,
    ValuationRunLatestResponse,
    ValuationRunListResponse,
    ValuationRunMutationResponse,
    ValuationRunRead,
)
from app.services.companies import get_company
from app.services.valuation_service import (
    ValuationInputError,
    create_draft_valuation_run,
    get_latest_company_valuation_run,
    get_valuation_run,
    list_company_valuation_runs,
    recalculate_valuation_run,
)

router = APIRouter()


@router.get(
    "/companies/{company_id}/valuation-runs/latest",
    response_model=ValuationRunLatestResponse,
)
def get_latest_company_valuation_run_item(
    company_id: int,
    db: Annotated[Session, Depends(get_db)],
) -> ValuationRunLatestResponse:
    _get_company_or_404(db, company_id)
    item = get_latest_company_valuation_run(db, company_id=company_id)
    return ValuationRunLatestResponse(company_id=company_id, item=item)


@router.get(
    "/companies/{company_id}/valuation-runs",
    response_model=ValuationRunListResponse,
)
def get_company_valuation_runs(
    company_id: int,
    db: Annotated[Session, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ValuationRunListResponse:
    _get_company_or_404(db, company_id)
    items, total = list_company_valuation_runs(
        db,
        company_id=company_id,
        limit=limit,
        offset=offset,
    )
    return ValuationRunListResponse(items=items, total=total, limit=limit, offset=offset)


@router.post(
    "/companies/{company_id}/valuation-runs/draft",
    response_model=ValuationRunMutationResponse,
)
def create_company_valuation_draft(
    company_id: int,
    payload: ValuationDraftRequest,
    db: Annotated[Session, Depends(get_db)],
) -> ValuationRunMutationResponse:
    company = _get_company_or_404(db, company_id)
    try:
        item = create_draft_valuation_run(
            db,
            company,
            user_assumptions=payload.assumptions,
            user_note=payload.user_note,
        )
    except ValuationInputError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return ValuationRunMutationResponse(company_id=company_id, item=item)


@router.post(
    "/valuation-runs/{run_id}/recalculate",
    response_model=ValuationRunMutationResponse,
)
def recalculate_valuation_run_item(
    run_id: int,
    payload: ValuationRecalculateRequest,
    db: Annotated[Session, Depends(get_db)],
) -> ValuationRunMutationResponse:
    run = _get_valuation_run_or_404(db, run_id)
    try:
        item = recalculate_valuation_run(
            db,
            run,
            user_assumptions=payload.assumptions,
            user_note=payload.user_note,
        )
    except ValuationInputError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return ValuationRunMutationResponse(company_id=item.company_id, item=item)


@router.get("/valuation-runs/{run_id}", response_model=ValuationRunRead)
def get_valuation_run_item(
    run_id: int,
    db: Annotated[Session, Depends(get_db)],
) -> ValuationRunRead:
    return _get_valuation_run_or_404(db, run_id)


def _get_company_or_404(db: Session, company_id: int) -> Company:
    company = get_company(db, company_id)
    if company is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found")
    return company


def _get_valuation_run_or_404(db: Session, run_id: int) -> ValuationRun:
    run = get_valuation_run(db, run_id)
    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Valuation run not found",
        )
    return run
