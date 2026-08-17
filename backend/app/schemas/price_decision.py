from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator

DISPLAY_TIME_ZONE = timezone(timedelta(hours=8), "Asia/Shanghai")
PriceDecisionRunStatus = Literal["active", "deleted"]


class PriceDecisionCreateRequest(BaseModel):
    valuation_run_id: int | None = Field(default=None, ge=1)
    safety_margin_override: float | None = None

    @field_validator("safety_margin_override")
    @classmethod
    def validate_safety_margin_override(cls, value: float | None) -> float | None:
        if value is not None and not 0.0 <= value <= 1.0:
            raise ValueError("用户覆盖安全边际必须位于 0%-100%。")
        return value


class PriceDecisionRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    company_id: int
    valuation_run_id: int
    memo_id: int
    version_no: int
    run_version: str
    formula_version: str
    status: PriceDecisionRunStatus
    input_snapshot: dict[str, object] = Field(default_factory=dict)
    input_snapshot_hash: str
    config_version: int | None = None
    config_hash: str | None = None
    config_snapshot: dict[str, object] = Field(default_factory=dict)
    intrinsic_values_per_share: dict[str, float] = Field(default_factory=dict)
    current_price: float
    market_data_updated_at: datetime
    suggested_safety_margin: float
    safety_margin_override: float | None = None
    effective_safety_margin: float
    scenario_buy_prices: dict[str, float] = Field(default_factory=dict)
    suggested_buy_price: float
    current_margin: float
    price_status: str
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None = None

    @field_serializer("market_data_updated_at", "created_at", "updated_at", "deleted_at")
    def serialize_time(self, value: datetime | None) -> str | None:
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value.astimezone(DISPLAY_TIME_ZONE).isoformat()


class PriceDecisionLatestResponse(BaseModel):
    company_id: int
    item: PriceDecisionRunRead | None = None


class PriceDecisionListResponse(BaseModel):
    items: list[PriceDecisionRunRead]
    total: int
    limit: int
    offset: int


class PriceDecisionMutationResponse(BaseModel):
    company_id: int
    item: PriceDecisionRunRead


class PriceDecisionDeleteResponse(BaseModel):
    id: int
    deleted: bool
    latest_price_decision_run_id: int | None = None
