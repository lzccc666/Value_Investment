from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.analysis.model_gateway import (
    ModelGatewayError,
    ModelNotConfiguredError,
    ModelOutputValidationError,
)
from app.db.models import Company
from app.db.session import get_db
from app.schemas.analysis import (
    AnalysisBatchRunItem,
    AnalysisBatchRunResponse,
    AnalysisLatestRunsResponse,
    AnalysisRuleStatusUpdateRequest,
    AnalysisRunDeleteResponse,
    AnalysisRunListResponse,
    AnalysisRunRead,
    AnalystBatchRunRequest,
    AnalystProfileListResponse,
    AnalystProfileRead,
    AnalystRunRequest,
)
from app.services.analyst_service import (
    AnalysisRuleCheckNotFoundError,
    AnalysisRunNotFoundError,
    AnalystProfileNotFoundError,
    delete_company_analysis_run,
    list_company_analysis_runs,
    list_latest_company_analysis_runs,
    list_profiles,
    run_company_analyst_view,
    run_company_analyst_views_batch,
    update_analysis_run_rule_status,
)
from app.services.companies import get_company

router = APIRouter()


@router.get("/analyst-profiles", response_model=AnalystProfileListResponse)
def get_analyst_profiles() -> AnalystProfileListResponse:
    return AnalystProfileListResponse(
        items=[AnalystProfileRead.model_validate(item) for item in list_profiles()]
    )


@router.get(
    "/companies/{company_id}/analysis/runs/latest",
    response_model=AnalysisLatestRunsResponse,
)
def get_latest_company_analysis_runs(
    company_id: int,
    db: Annotated[Session, Depends(get_db)],
    run_type: Annotated[str | None, Query(max_length=80)] = "analyst_view",
    analyst_profile: Annotated[str | None, Query(max_length=80)] = None,
    status_filter: Annotated[str | None, Query(alias="status", max_length=40)] = "success",
) -> AnalysisLatestRunsResponse:
    _get_company_or_404(db, company_id)
    items = list_latest_company_analysis_runs(
        db,
        company_id=company_id,
        run_type=run_type,
        analyst_profile=analyst_profile,
        status=status_filter,
    )
    return AnalysisLatestRunsResponse(
        company_id=company_id,
        run_type=run_type,
        analyst_profile=analyst_profile,
        status=status_filter,
        items=items,
    )


@router.get("/companies/{company_id}/analysis/runs", response_model=AnalysisRunListResponse)
def get_company_analysis_runs(
    company_id: int,
    db: Annotated[Session, Depends(get_db)],
    run_type: Annotated[str | None, Query(max_length=80)] = None,
    analyst_profile: Annotated[str | None, Query(max_length=80)] = None,
    status_filter: Annotated[str | None, Query(alias="status", max_length=40)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> AnalysisRunListResponse:
    _get_company_or_404(db, company_id)
    items, total = list_company_analysis_runs(
        db,
        company_id=company_id,
        run_type=run_type,
        analyst_profile=analyst_profile,
        status=status_filter,
        limit=limit,
        offset=offset,
    )
    return AnalysisRunListResponse(items=items, total=total, limit=limit, offset=offset)


@router.patch(
    "/companies/{company_id}/analysis/runs/{run_id}/rule-checks/{rule_id}",
    response_model=AnalysisRunRead,
)
def update_company_analysis_run_rule_status(
    company_id: int,
    run_id: int,
    rule_id: str,
    payload: AnalysisRuleStatusUpdateRequest,
    db: Annotated[Session, Depends(get_db)],
) -> AnalysisRunRead:
    _get_company_or_404(db, company_id)
    try:
        return update_analysis_run_rule_status(
            db,
            company_id=company_id,
            run_id=run_id,
            rule_id=rule_id,
            status=payload.status,
        )
    except (AnalysisRunNotFoundError, AnalysisRuleCheckNotFoundError) as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.delete(
    "/companies/{company_id}/analysis/runs/{run_id}",
    response_model=AnalysisRunDeleteResponse,
)
def delete_company_analysis_run_item(
    company_id: int,
    run_id: int,
    db: Annotated[Session, Depends(get_db)],
) -> AnalysisRunDeleteResponse:
    _get_company_or_404(db, company_id)
    try:
        deleted_id = delete_company_analysis_run(db, company_id=company_id, run_id=run_id)
    except AnalysisRunNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return AnalysisRunDeleteResponse(id=deleted_id, deleted=True)


@router.post(
    "/companies/{company_id}/analysis/runs/batch",
    response_model=AnalysisBatchRunResponse,
)
def run_company_analysis_batch(
    company_id: int,
    payload: AnalystBatchRunRequest,
    db: Annotated[Session, Depends(get_db)],
) -> AnalysisBatchRunResponse:
    company = _get_company_or_404(db, company_id)
    try:
        results = run_company_analyst_views_batch(
            db,
            company,
            payload.analyst_profiles,
            user_note=payload.user_note,
        )
    except AnalystProfileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    items = [
        AnalysisBatchRunItem(
            analyst_profile=result.analyst_profile,
            status=result.status,
            run=result.run,
            error=result.error,
            error_type=result.error_type,
        )
        for result in results
    ]
    succeeded = sum(1 for item in items if item.status == "success")
    failed = len(items) - succeeded
    return AnalysisBatchRunResponse(
        company_id=company_id,
        requested=len(items),
        succeeded=succeeded,
        failed=failed,
        items=items,
    )


@router.post("/companies/{company_id}/analysis/runs", response_model=AnalysisRunRead)
def run_company_analysis(
    company_id: int,
    payload: AnalystRunRequest,
    db: Annotated[Session, Depends(get_db)],
) -> AnalysisRunRead:
    company = _get_company_or_404(db, company_id)
    try:
        return run_company_analyst_view(
            db,
            company,
            payload.analyst_profile,
            user_note=payload.user_note,
        )
    except AnalystProfileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ModelNotConfiguredError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except ModelOutputValidationError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    except ModelGatewayError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc


def _get_company_or_404(db: Session, company_id: int) -> Company:
    company = get_company(db, company_id)
    if company is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found")
    return company
