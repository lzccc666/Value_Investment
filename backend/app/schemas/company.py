from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class CompanyRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    ticker: str
    exchange: str
    name: str
    industry: str | None = None
    description: str | None = None
    listed_date: date | None = None
    status: str
    tags: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class CompanyListResponse(BaseModel):
    items: list[CompanyRead]
    total: int
    limit: int
    offset: int
