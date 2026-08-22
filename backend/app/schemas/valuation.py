from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator

DISPLAY_TIME_ZONE = timezone(timedelta(hours=8), "Asia/Shanghai")
ValuationRunStatus = Literal["draft", "locked", "archived", "failed"]


class ValuationDraftRequest(BaseModel):
    assumptions: dict[str, object] | None = None
    user_note: str | None = Field(default=None, max_length=2000)

    @field_validator("user_note")
    @classmethod
    def normalize_user_note(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None


class ValuationRecalculateRequest(BaseModel):
    assumptions: dict[str, object] = Field(default_factory=dict)
    user_note: str | None = Field(default=None, max_length=2000)

    @field_validator("user_note")
    @classmethod
    def normalize_user_note(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None


class ValuationRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    company_id: int
    memo_id: int | None = None
    run_version: str
    status: ValuationRunStatus
    price_blind: bool
    forbidden_price_inputs: dict[str, object] = Field(default_factory=dict)
    input_snapshot: dict[str, object] = Field(default_factory=dict)
    input_snapshot_hash: str | None = None
    config_version: int | None = None
    config_hash: str | None = None
    config_snapshot: dict[str, object] = Field(default_factory=dict)
    valuation_inputs: dict[str, object] = Field(default_factory=dict)
    model_suggested_assumptions: dict[str, object] = Field(default_factory=dict)
    user_adjusted_assumptions: dict[str, object] = Field(default_factory=dict)
    assumptions: dict[str, object] = Field(default_factory=dict)
    methods: dict[str, object] = Field(default_factory=dict)
    results: dict[str, object] = Field(default_factory=dict)
    sensitivity: dict[str, object] = Field(default_factory=dict)
    confidence: float | None = None
    confidence_summary: dict[str, object] = Field(default_factory=dict)
    source_map: dict[str, object] = Field(default_factory=dict)
    valuation_currency: str | None = None
    share_basis_snapshot: dict[str, object] = Field(default_factory=dict)
    user_note: str | None = None
    created_at: datetime
    updated_at: datetime

    @field_serializer("created_at", "updated_at")
    def serialize_time(self, value: datetime) -> str:
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value.astimezone(DISPLAY_TIME_ZONE).isoformat()


class ValuationRunLatestResponse(BaseModel):
    company_id: int
    item: ValuationRunRead | None = None


class ValuationRunListResponse(BaseModel):
    items: list[ValuationRunRead]
    total: int
    limit: int
    offset: int


class ValuationRunMutationResponse(BaseModel):
    company_id: int
    item: ValuationRunRead
