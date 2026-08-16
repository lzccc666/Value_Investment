from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.data_management import (
    AutomaticBackupSettings,
    BackupCreateRequest,
    BackupDeleteRequest,
    BackupListResponse,
    BackupManifest,
    BackupVerifyResponse,
    DataManagementSummary,
    DataOperationExecuteRequest,
    DataOperationParameters,
    DataOperationPreview,
    DataOperationPreviewRequest,
    DataOperationResult,
    DataOperationType,
)
from app.services.backup_service import BackupError, BackupService, engine_from_session
from app.services.data_management_service import (
    DataManagementError,
    InvalidOperationTokenError,
    execute_operation,
    get_summary,
    preview_operation,
)
from app.services.maintenance_gate import MaintenanceBusyError, maintenance_gate

router = APIRouter(prefix="/data-management")


@router.get("/summary", response_model=DataManagementSummary)
def read_summary(db: Annotated[Session, Depends(get_db)]) -> DataManagementSummary:
    return _handle(lambda: get_summary(db))


@router.post("/operations/preview", response_model=DataOperationPreview)
def preview_data_operation(
    payload: DataOperationPreviewRequest,
    db: Annotated[Session, Depends(get_db)],
) -> DataOperationPreview:
    return _handle(lambda: preview_operation(db, payload))


@router.post("/operations/execute", response_model=DataOperationResult)
def execute_data_operation(
    payload: DataOperationExecuteRequest,
    db: Annotated[Session, Depends(get_db)],
) -> DataOperationResult:
    return _handle(
        lambda: execute_operation(
            db,
            operation_token=payload.operation_token,
            confirmation_phrase=payload.confirmation_phrase,
        )
    )


@router.get("/backups", response_model=BackupListResponse)
def list_backups(db: Annotated[Session, Depends(get_db)]) -> BackupListResponse:
    service = BackupService(engine_from_session(db))
    items = _handle(service.list_backups)
    return BackupListResponse(items=items, total=len(items))


@router.post("/backups", response_model=BackupManifest)
def create_backup(
    payload: BackupCreateRequest,
    db: Annotated[Session, Depends(get_db)],
) -> BackupManifest:
    service = BackupService(engine_from_session(db))

    def action() -> BackupManifest:
        with maintenance_gate.maintenance("manual_backup"):
            db.commit()
            manifest = service.create_backup(reason=payload.reason)
            backup_settings = service.get_settings()
            service.prune_backups(backup_settings.max_backups)
            return manifest

    return _handle(action)


@router.post("/backups/{backup_id}/verify", response_model=BackupVerifyResponse)
def verify_backup(
    backup_id: str,
    db: Annotated[Session, Depends(get_db)],
) -> BackupVerifyResponse:
    return _handle(lambda: BackupService(engine_from_session(db)).verify_backup(backup_id))


@router.post("/backups/{backup_id}/restore/preview", response_model=DataOperationPreview)
def preview_backup_restore(
    backup_id: str,
    db: Annotated[Session, Depends(get_db)],
) -> DataOperationPreview:
    request = DataOperationPreviewRequest(
        operation_type=DataOperationType.RESTORE_BACKUP,
        parameters=DataOperationParameters(backup_id=backup_id),
    )
    return _handle(lambda: preview_operation(db, request))


@router.delete("/backups/{backup_id}", response_model=DataOperationResult)
def delete_backup(
    backup_id: str,
    payload: BackupDeleteRequest,
    db: Annotated[Session, Depends(get_db)],
) -> DataOperationResult:
    result = _handle(
        lambda: execute_operation(
            db,
            operation_token=payload.operation_token,
            confirmation_phrase=payload.confirmation_phrase,
            expected_operation=DataOperationType.DELETE_BACKUP,
            expected_backup_id=backup_id,
        )
    )
    return result


@router.get("/settings", response_model=AutomaticBackupSettings)
def read_backup_settings(
    db: Annotated[Session, Depends(get_db)],
) -> AutomaticBackupSettings:
    return _handle(lambda: BackupService(engine_from_session(db)).get_settings())


@router.put("/settings", response_model=AutomaticBackupSettings)
def update_backup_settings(
    payload: AutomaticBackupSettings,
    db: Annotated[Session, Depends(get_db)],
) -> AutomaticBackupSettings:
    current = BackupService(engine_from_session(db)).get_settings()
    payload.last_auto_backup_at = current.last_auto_backup_at
    return _handle(lambda: BackupService(engine_from_session(db)).update_settings(payload))


def _handle(action):
    try:
        return action()
    except InvalidOperationTokenError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except MaintenanceBusyError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except (DataManagementError, BackupError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
