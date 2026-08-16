from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.analysis.model_gateway import (
    ModelGatewayError,
    ModelNotConfiguredError,
    ModelOutputValidationError,
)
from app.configuration.runtime import parameter_config_context
from app.db.models import Company
from app.db.session import get_db
from app.schemas.evidence import (
    EvidenceDeleteResponse,
    EvidenceImportTextRequest,
    EvidenceImportTextResponse,
    EvidenceListResponse,
    EvidenceRead,
    EvidenceReviewResponse,
    EvidenceSearchRequest,
    EvidenceSearchResponse,
    ModelConfigStatus,
    ModelSmokeTestResponse,
)
from app.services.companies import get_company
from app.services.evidence_service import (
    EvidenceImportTextError,
    EvidenceSearchError,
    delete_evidence,
    get_evidence,
    get_model_config_status,
    import_text_evidence,
    list_company_evidence,
    mark_evidence_reviewed,
    run_model_smoke_test,
    search_company_evidence,
)
from app.services.parameter_config_service import get_runtime_parameter_config

router = APIRouter()


@router.get("/evidence/model-config", response_model=ModelConfigStatus)
def get_evidence_model_config() -> ModelConfigStatus:
    return ModelConfigStatus.model_validate(get_model_config_status())


@router.post("/evidence/model-smoke-test", response_model=ModelSmokeTestResponse)
def smoke_test_evidence_model() -> ModelSmokeTestResponse:
    try:
        return ModelSmokeTestResponse.model_validate(run_model_smoke_test())
    except ModelNotConfiguredError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except ModelOutputValidationError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    except ModelGatewayError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc


@router.post(
    "/companies/{company_id}/evidence/search",
    response_model=EvidenceSearchResponse,
)
def search_external_evidence(
    company_id: int,
    payload: EvidenceSearchRequest,
    db: Annotated[Session, Depends(get_db)],
) -> EvidenceSearchResponse:
    company = _get_company_or_404(db, company_id)
    try:
        runtime = get_runtime_parameter_config(db)
        with parameter_config_context(runtime.snapshot):
            effective_payload = payload.model_copy(
                update={
                    "max_results": payload.max_results
                    or int(runtime.snapshot["data_sampling"]["external_search_default_results"])
                }
            )
            items, run = search_company_evidence(db, company, effective_payload)
    except ModelNotConfiguredError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except ModelOutputValidationError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    except ModelGatewayError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    except EvidenceSearchError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    return EvidenceSearchResponse(
        company_id=company_id,
        run_id=run.id,
        status=run.status if run.status in {"success", "partial", "failed"} else "failed",
        created=len(items),
        items=items,
        diagnostics=run.result.get("search_stats") if isinstance(run.result, dict) else None,
    )


@router.post(
    "/companies/{company_id}/evidence/import-text",
    response_model=EvidenceImportTextResponse,
)
def import_external_evidence_text(
    company_id: int,
    payload: EvidenceImportTextRequest,
    db: Annotated[Session, Depends(get_db)],
) -> EvidenceImportTextResponse:
    company = _get_company_or_404(db, company_id)
    try:
        runtime = get_runtime_parameter_config(db)
        with parameter_config_context(runtime.snapshot):
            items, run = import_text_evidence(db, company, payload)
    except ModelNotConfiguredError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except ModelOutputValidationError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    except ModelGatewayError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    except EvidenceImportTextError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    return EvidenceImportTextResponse(
        company_id=company_id,
        run_id=run.id,
        status=run.status if run.status in {"success", "partial", "failed"} else "failed",
        created=len(items),
        items=items,
        diagnostics=run.result.get("diagnostics") if isinstance(run.result, dict) else None,
    )


@router.get("/companies/{company_id}/evidence", response_model=EvidenceListResponse)
def get_company_evidence_list(
    company_id: int,
    db: Annotated[Session, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=10)] = 10,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> EvidenceListResponse:
    _get_company_or_404(db, company_id)
    items, total = list_company_evidence(db, company_id=company_id, limit=limit, offset=offset)
    return EvidenceListResponse(items=items, total=total, limit=limit, offset=offset)


@router.get("/evidence/{evidence_id}", response_model=EvidenceRead)
def get_evidence_detail(
    evidence_id: int,
    db: Annotated[Session, Depends(get_db)],
) -> EvidenceRead:
    evidence = get_evidence(db, evidence_id)
    if evidence is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Evidence not found")
    return evidence


@router.post("/evidence/{evidence_id}/review", response_model=EvidenceReviewResponse)
def review_evidence(
    evidence_id: int,
    db: Annotated[Session, Depends(get_db)],
) -> EvidenceReviewResponse:
    evidence = get_evidence(db, evidence_id)
    if evidence is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Evidence not found")

    reviewed = mark_evidence_reviewed(db, evidence)
    return EvidenceReviewResponse(evidence=reviewed)


@router.delete("/evidence/{evidence_id}", response_model=EvidenceDeleteResponse)
def delete_evidence_item(
    evidence_id: int,
    db: Annotated[Session, Depends(get_db)],
) -> EvidenceDeleteResponse:
    evidence = get_evidence(db, evidence_id)
    if evidence is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Evidence not found")

    deleted_id = delete_evidence(db, evidence)
    return EvidenceDeleteResponse(id=deleted_id, deleted=True)


def _get_company_or_404(db: Session, company_id: int) -> Company:
    company = get_company(db, company_id)
    if company is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found")
    return company
