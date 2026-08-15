from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

EvidenceSourceType = Literal[
    "policy",
    "industry_news",
    "company_news",
    "public_data",
    "regulatory",
    "web",
]
ImpactDirection = Literal["positive", "neutral", "negative", "mixed", "unknown"]
EvidenceAnalysisStatus = Literal["model_analyzed", "search_lead"]
EvidenceUseScope = Literal[
    "fundamental_analysis",
    "analyst_view",
    "intrinsic_valuation",
]


class EvidenceModelOutput(BaseModel):
    source_type: EvidenceSourceType
    title: str = Field(min_length=1, max_length=255)
    source: str | None = Field(default=None, max_length=160)
    source_url: str | None = None
    published_at: datetime | None = None
    summary: str = Field(min_length=1)
    key_facts: list[str] = Field(default_factory=list)
    impact_direction: ImpactDirection = "unknown"
    importance_score: float = Field(ge=0, le=1)
    credibility_score: float = Field(ge=0, le=1)
    tags: list[str] = Field(default_factory=list)
    requires_review: bool = True
    price_sensitive: bool = False
    use_scope: list[EvidenceUseScope] = Field(
        default_factory=lambda: [
            "fundamental_analysis",
            "analyst_view",
            "intrinsic_valuation",
        ]
    )
    analysis_status: EvidenceAnalysisStatus = "model_analyzed"
    analysis_note: str | None = None
    raw_snapshot: dict[str, object] = Field(default_factory=dict)

    @field_validator("title", "summary")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("字段不能为空")
        return normalized

    @field_validator("source", "source_url", "analysis_note")
    @classmethod
    def strip_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @field_validator("key_facts", "tags")
    @classmethod
    def normalize_text_list(cls, value: list[str]) -> list[str]:
        items: list[str] = []
        for item in value:
            normalized = item.strip()
            if normalized and normalized not in items:
                items.append(normalized)
        return items

    @field_validator("use_scope")
    @classmethod
    def normalize_use_scope(cls, value: list[EvidenceUseScope]) -> list[EvidenceUseScope]:
        items: list[EvidenceUseScope] = []
        for item in value:
            if item not in items:
                items.append(item)
        return items


class EvidenceExtractionOutput(BaseModel):
    evidences: list[EvidenceModelOutput] = Field(default_factory=list)


class SearchQueryPlan(BaseModel):
    queries: list[str] = Field(min_length=1, max_length=8)

    @field_validator("queries")
    @classmethod
    def normalize_queries(cls, value: list[str]) -> list[str]:
        queries: list[str] = []
        for item in value:
            normalized = " ".join(item.strip().split())
            if normalized and normalized not in queries:
                queries.append(normalized)
        if not queries:
            raise ValueError("至少需要一个搜索 query")
        return queries[:8]


class EvidenceCreate(EvidenceModelOutput):
    pass


class EvidenceRead(EvidenceModelOutput):
    model_config = ConfigDict(from_attributes=True)

    id: int
    company_id: int
    created_at: datetime


class EvidenceListResponse(BaseModel):
    items: list[EvidenceRead]
    total: int
    limit: int
    offset: int


class EvidenceSearchRequest(BaseModel):
    keywords: list[str] = Field(default_factory=list, max_length=10)
    max_results: int = Field(default=5, ge=1, le=10)

    @field_validator("keywords")
    @classmethod
    def normalize_keywords(cls, value: list[str]) -> list[str]:
        keywords: list[str] = []
        for item in value:
            normalized = " ".join(item.strip().split())
            if normalized and normalized not in keywords:
                keywords.append(normalized)
        return keywords


class EvidenceSearchResponse(BaseModel):
    company_id: int
    run_id: int
    status: Literal["success", "partial", "failed"]
    created: int
    items: list[EvidenceRead]
    diagnostics: dict[str, object] | None = None


class EvidenceReviewResponse(BaseModel):
    evidence: EvidenceRead


class EvidenceDeleteResponse(BaseModel):
    id: int
    deleted: bool


class ModelConfigStatus(BaseModel):
    provider: str
    base_url: str | None = None
    model_name: str | None
    wire_api: str | None = None
    api_key_configured: bool


class ModelSmokeTestOutput(BaseModel):
    ok: bool
    message: str


class ModelSmokeTestResponse(BaseModel):
    provider: str
    base_url: str | None = None
    model_name: str | None
    wire_api: str | None = None
    api_key_configured: bool
    ok: bool
    message: str
