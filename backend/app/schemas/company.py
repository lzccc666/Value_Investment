from datetime import UTC, date, datetime, timedelta, timezone

from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator

DISPLAY_TIME_ZONE = timezone(timedelta(hours=8), "Asia/Shanghai")


class CompanyCreate(BaseModel):
    ticker: str = Field(
        min_length=1,
        max_length=32,
        description="证券代码，必填。建议使用 600519.SH、00700.HK、AAPL.US 这类带市场后缀的格式。",
    )
    exchange: str = Field(
        min_length=1,
        max_length=32,
        description="交易所，必填。例如 SSE、SZSE、HKEX、NASDAQ、NYSE。",
    )
    name: str = Field(min_length=1, max_length=255, description="公司名称，必填。")
    industry: str | None = Field(default=None, max_length=120, description="所属行业，可选。")
    description: str | None = Field(default=None, description="公司简介，可选。")
    listed_date: date | None = Field(default=None, description="上市日期，可选，格式 YYYY-MM-DD。")
    status: str = Field(default="未研究", max_length=40, description="研究状态，可选。")
    tags: list[str] = Field(default_factory=list, description="标签，可选。用于搜索和研究分类。")

    @field_validator("ticker", "exchange", "name", "status")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("字段不能为空")
        return normalized

    @field_validator("industry", "description")
    @classmethod
    def strip_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None

        normalized = value.strip()
        return normalized or None

    @field_validator("tags")
    @classmethod
    def normalize_tags(cls, value: list[str]) -> list[str]:
        tags: list[str] = []
        for item in value:
            tag = item.strip()
            if tag and tag not in tags:
                tags.append(tag)
        return tags


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
    market_cap: float | None = None
    current_price: float | None = None
    pe_ttm: float | None = None
    pe_dynamic: float | None = None
    pe_static: float | None = None
    pb_ratio: float | None = None
    ps_ratio: float | None = None
    dividend_yield_ttm: float | None = None
    dividend_yield_static: float | None = None
    market_data_source: str | None = None
    market_data_source_url: str | None = None
    market_data_updated_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    @field_serializer("market_data_updated_at", "created_at", "updated_at")
    def serialize_company_time(self, value: datetime | None) -> str | None:
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=DISPLAY_TIME_ZONE)
        return value.astimezone(DISPLAY_TIME_ZONE).isoformat()


class CompanyListResponse(BaseModel):
    items: list[CompanyRead]
    total: int
    limit: int
    offset: int


class FinancialStatementRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    company_id: int
    period: str
    statement_type: str
    currency: str
    fields: dict[str, object] = Field(default_factory=dict)
    source: str | None = None
    source_url: str | None = None
    created_at: datetime

    @field_serializer("created_at")
    def serialize_financial_statement_time(self, value: datetime) -> str:
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value.astimezone(DISPLAY_TIME_ZONE).isoformat()


class FinancialStatementListResponse(BaseModel):
    items: list[FinancialStatementRead]
    total: int
    limit: int
    offset: int


class FinancialEvidencePackRead(BaseModel):
    latest_period: str | None = None
    periods: list[str] = Field(default_factory=list)
    financial_facts: dict[str, object] = Field(default_factory=dict)
    financial_metrics: dict[str, object] = Field(default_factory=dict)
    cash_flow_coverage: dict[str, object] = Field(default_factory=dict)
    financial_trends: dict[str, object] = Field(default_factory=dict)
    financial_flags: list[dict[str, object]] = Field(default_factory=list)
    financial_data_gaps: list[dict[str, object]] = Field(default_factory=list)
    financial_data_gap_messages: list[str] = Field(default_factory=list)
    cash_flow_quality: dict[str, object] = Field(default_factory=dict)
    balance_sheet_adjustment: dict[str, object] = Field(default_factory=dict)
    capital_allocation: dict[str, object] = Field(default_factory=dict)
    valuation_readiness: dict[str, object] = Field(default_factory=dict)
    quality_matrix: dict[str, object] = Field(default_factory=dict)
    analyst_summary: dict[str, object] = Field(default_factory=dict)
    data_quality: dict[str, object] = Field(default_factory=dict)


class FinancialStatementSyncResponse(BaseModel):
    company_id: int
    source: str
    fetched: int
    created: int
    updated: int
    items: list[FinancialStatementRead]


class FinancialStatementDeleteResponse(BaseModel):
    id: int
    deleted: bool


class AnnouncementRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    company_id: int
    title: str
    published_at: datetime
    category: str
    content: str | None = None
    raw_content: str | None = None
    summary: str | None = None
    key_facts: list[str] = Field(default_factory=list)
    source: str | None = None
    source_url: str | None = None
    raw_url: str | None = None
    impact_direction: str | None = None
    sentiment: str | None = None
    positive_impacts: list[str] = Field(default_factory=list)
    negative_impacts: list[str] = Field(default_factory=list)
    neutral_impacts: list[str] = Field(default_factory=list)
    risk_tips: list[str] = Field(default_factory=list)
    review_questions: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    summary_status: str = "unprocessed"
    summary_model_name: str | None = None
    summary_prompt_version: str | None = None
    summarized_at: datetime | None = None
    created_at: datetime


class AnnouncementListResponse(BaseModel):
    items: list[AnnouncementRead]
    total: int
    limit: int
    offset: int


class AnnouncementSyncResponse(BaseModel):
    company_id: int
    source: str
    fetched: int
    created: int
    updated: int
    skipped: int
    pruned: int = 0
    errors: list[str] = Field(default_factory=list)
    items: list[AnnouncementRead]


class AnnouncementSummaryBatchProgressResponse(BaseModel):
    company_id: int
    requested: int
    processed: int
    remaining: int
    succeeded: int
    failed: int
    status: str
    items: list[AnnouncementRead | dict[str, object]]


class AnnouncementDeleteResponse(BaseModel):
    id: int
    deleted: bool
