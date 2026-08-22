from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.models import Company, PriceDecisionRun
from app.db.session import get_db
from app.schemas.price_decision import (
    PriceDecisionCreateRequest,
    PriceDecisionDeleteResponse,
    PriceDecisionLatestResponse,
    PriceDecisionListResponse,
    PriceDecisionMutationResponse,
    PriceDecisionRunRead,
)
from app.services.companies import get_company
from app.services.parameter_config_service import get_runtime_parameter_config
from app.services.price_decision_service import (
    PriceDecisionInputError,
    create_price_decision_run,
    delete_price_decision_run,
    get_latest_company_price_decision_run,
    get_price_decision_run,
    list_company_price_decision_runs,
)

router = APIRouter()


@router.post(
    "/companies/{company_id}/price-decision-runs",
    response_model=PriceDecisionMutationResponse,
)
def create_company_price_decision_run(
    company_id: int,
    payload: PriceDecisionCreateRequest,
    db: Annotated[Session, Depends(get_db)],
) -> PriceDecisionMutationResponse:
    company = _get_company_or_404(db, company_id)
    try:
        item = create_price_decision_run(
            db,
            company,
            valuation_run_id=payload.valuation_run_id,
            safety_margin_override=payload.safety_margin_override,
            listing_id=payload.listing_id,
        )
    except PriceDecisionInputError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return PriceDecisionMutationResponse(company_id=company_id, item=item)


@router.get(
    "/companies/{company_id}/price-decision-runs/latest",
    response_model=PriceDecisionLatestResponse,
)
def get_latest_company_price_decision_run_item(
    company_id: int,
    db: Annotated[Session, Depends(get_db)],
) -> PriceDecisionLatestResponse:
    _get_company_or_404(db, company_id)
    item = get_latest_company_price_decision_run(db, company_id=company_id)
    return PriceDecisionLatestResponse(company_id=company_id, item=item)


@router.get(
    "/companies/{company_id}/price-decision-runs",
    response_model=PriceDecisionListResponse,
)
def get_company_price_decision_runs(
    company_id: int,
    db: Annotated[Session, Depends(get_db)],
    limit: Annotated[int | None, Query(ge=1, le=100)] = None,
    offset: Annotated[int, Query(ge=0)] = 0,
    include_deleted: bool = False,
) -> PriceDecisionListResponse:
    _get_company_or_404(db, company_id)
    runtime = get_runtime_parameter_config(db)
    effective_limit = limit or int(
        runtime.snapshot["data_sampling"]["price_decision_history_limit"]
    )
    items, total = list_company_price_decision_runs(
        db,
        company_id=company_id,
        limit=effective_limit,
        offset=offset,
        include_deleted=include_deleted,
    )
    return PriceDecisionListResponse(
        items=items,
        total=total,
        limit=effective_limit,
        offset=offset,
    )


@router.get("/price-decision-runs/{run_id}", response_model=PriceDecisionRunRead)
def get_price_decision_run_item(
    run_id: int,
    db: Annotated[Session, Depends(get_db)],
) -> PriceDecisionRunRead:
    return _get_price_decision_run_or_404(db, run_id)


@router.delete(
    "/price-decision-runs/{run_id}",
    response_model=PriceDecisionDeleteResponse,
)
def delete_price_decision_run_item(
    run_id: int,
    db: Annotated[Session, Depends(get_db)],
) -> PriceDecisionDeleteResponse:
    run = _get_price_decision_run_or_404(db, run_id)
    delete_price_decision_run(db, run)
    latest = get_latest_company_price_decision_run(db, company_id=run.company_id)
    return PriceDecisionDeleteResponse(
        id=run.id,
        deleted=True,
        latest_price_decision_run_id=latest.id if latest else None,
    )


def _get_company_or_404(db: Session, company_id: int) -> Company:
    company = get_company(db, company_id)
    if company is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found")
    return company


def _get_price_decision_run_or_404(db: Session, run_id: int) -> PriceDecisionRun:
    run = get_price_decision_run(db, run_id)
    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="价格决策版本不存在。",
        )
    return run
