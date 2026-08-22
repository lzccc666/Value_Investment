from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class FxRateSnapshotRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    base_currency: str
    quote_currency: str
    rate: float
    rate_date: date
    fetched_at: datetime
    source: str
    source_url: str | None = None
    raw_snapshot_hash: str | None = None
    calculation_audit: dict[str, object] | None = None


class FxRateLatestResponse(BaseModel):
    base_currency: str
    quote_currency: str
    item: FxRateSnapshotRead | None = Field(default=None)
