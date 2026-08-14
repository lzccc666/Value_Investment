from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.schemas.company import AnnouncementRead

ImpactDirection = Literal["positive", "neutral", "negative", "mixed", "unknown"]


class AnnouncementSummaryOutput(BaseModel):
    summary: str = Field(min_length=1, max_length=2000)
    key_facts: list[str] = Field(default_factory=list, max_length=12)
    category: str = Field(min_length=1, max_length=80)
    impact_direction: ImpactDirection = "unknown"
    confidence: float = Field(ge=0, le=1)
    positive_impacts: list[str] = Field(default_factory=list, max_length=8)
    negative_impacts: list[str] = Field(default_factory=list, max_length=8)
    neutral_impacts: list[str] = Field(default_factory=list, max_length=8)
    risk_tips: list[str] = Field(default_factory=list, max_length=8)
    review_questions: list[str] = Field(default_factory=list, max_length=8)
    tags: list[str] = Field(default_factory=list, max_length=12)
    requires_review: bool = True
    source_url: str | None = None

    @field_validator("summary", "category")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("字段不能为空")
        return normalized

    @field_validator("source_url")
    @classmethod
    def strip_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @field_validator(
        "key_facts",
        "positive_impacts",
        "negative_impacts",
        "neutral_impacts",
        "risk_tips",
        "review_questions",
        "tags",
    )
    @classmethod
    def normalize_text_list(cls, value: list[str]) -> list[str]:
        items: list[str] = []
        for item in value:
            normalized = " ".join(str(item).strip().split())
            if normalized and normalized not in items:
                items.append(normalized)
        return items


class AnnouncementSummaryResponse(BaseModel):
    company_id: int
    announcement_id: int
    run_id: int | None = None
    status: Literal["success", "failed"]
    summary_status: str
    announcement: AnnouncementRead


class AnnouncementSummaryBatchItem(BaseModel):
    announcement_id: int
    status: Literal["success", "failed", "skipped"]
    summary_status: str
    run_id: int | None = None
    announcement: AnnouncementRead | None = None
    error: str | None = None
    error_type: str | None = None


class AnnouncementSummaryBatchResponse(BaseModel):
    company_id: int
    requested: int
    processed: int
    remaining: int
    succeeded: int
    failed: int
    status: Literal["success", "partial", "failed"]
    items: list[AnnouncementSummaryBatchItem]


class AnnouncementContentFetchResult(BaseModel):
    source_url: str
    content: str
    fetched_at: datetime
