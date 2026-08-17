from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, model_validator


class DataOperationType(StrEnum):
    RESET_COMPANY_RESEARCH_DATA = "reset_company_research_data"
    CLEAR_ANALYSIS_HISTORY = "clear_analysis_history"
    INITIALIZE_DATABASE = "initialize_database"
    PRUNE_VERSIONS = "prune_versions"
    PURGE_DELETED_AND_VACUUM = "purge_deleted_and_vacuum"
    RESTORE_BACKUP = "restore_backup"
    DELETE_BACKUP = "delete_backup"


class DataOperationParameters(BaseModel):
    company_id: int | None = Field(default=None, ge=1)
    keep_count: int | None = Field(default=None, ge=1, le=100)
    backup_id: str | None = Field(default=None, min_length=1, max_length=120)


class DataOperationPreviewRequest(BaseModel):
    operation_type: DataOperationType
    parameters: DataOperationParameters = Field(default_factory=DataOperationParameters)

    @model_validator(mode="after")
    def validate_parameters(self) -> DataOperationPreviewRequest:
        if (
            self.operation_type == DataOperationType.RESET_COMPANY_RESEARCH_DATA
            and self.parameters.company_id is None
        ):
            raise ValueError("清空单家公司研究数据时必须指定 company_id。")
        if (
            self.operation_type == DataOperationType.PRUNE_VERSIONS
            and self.parameters.keep_count is None
        ):
            raise ValueError("版本保留操作必须指定 keep_count。")
        if (
            self.operation_type
            in {
                DataOperationType.RESTORE_BACKUP,
                DataOperationType.DELETE_BACKUP,
            }
            and not self.parameters.backup_id
        ):
            raise ValueError("该操作必须指定 backup_id。")
        return self


class ProtectedRecord(BaseModel):
    table: str
    record_id: int
    reason: str


class DataOperationPreview(BaseModel):
    operation_token: str
    operation_type: DataOperationType
    parameters: DataOperationParameters
    affected_counts: dict[str, int]
    protected_records: list[ProtectedRecord] = Field(default_factory=list)
    estimated_reclaim_bytes: int = 0
    requires_backup: bool = True
    confirmation_phrase: str
    expires_at: datetime


class DataOperationExecuteRequest(BaseModel):
    operation_token: str = Field(min_length=20, max_length=200)
    confirmation_phrase: str = Field(min_length=1, max_length=120)


class DataOperationResult(BaseModel):
    operation_type: DataOperationType
    affected_counts: dict[str, int]
    backup_id: str | None = None
    protected_records: list[ProtectedRecord] = Field(default_factory=list)
    database_size_before: int | None = None
    database_size_after: int | None = None
    reclaimed_bytes: int | None = None
    integrity_check: str | None = None
    restart_required: bool = False
    message: str


class BackupManifest(BaseModel):
    backup_id: str
    created_at: datetime
    database_filename: str
    file_size: int
    sha256: str
    schema_version: int
    record_counts: dict[str, int]
    reason: str
    application_version: str
    verified: bool | None = None
    integrity_check: str | None = None


class BackupListResponse(BaseModel):
    items: list[BackupManifest]
    total: int


class BackupCreateRequest(BaseModel):
    reason: str = Field(default="manual", min_length=1, max_length=160)


class BackupVerifyResponse(BaseModel):
    backup_id: str
    valid: bool
    sha256_matches: bool
    integrity_check: str


class BackupDeleteRequest(BaseModel):
    operation_token: str = Field(min_length=20, max_length=200)
    confirmation_phrase: str = Field(min_length=1, max_length=120)


class AutomaticBackupSettings(BaseModel):
    enabled: bool = False
    interval_hours: int = Field(default=24, ge=1, le=720)
    max_backups: int = Field(default=10, ge=1, le=200)
    last_auto_backup_at: datetime | None = None


class DataManagementSummary(BaseModel):
    database_path: str
    database_size: int
    record_counts: dict[str, int]
    soft_deleted_counts: dict[str, int]
    latest_backup: BackupManifest | None = None
    automatic_backup: AutomaticBackupSettings
    maintenance_active: bool
    maintenance_operation: str | None = None
    schema_version: int
    integrity_check: str


class ErrorDetail(BaseModel):
    detail: str
    context: dict[str, Any] = Field(default_factory=dict)
