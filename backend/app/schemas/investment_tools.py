from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

OwnerType = Literal["self", "investor"]
PortfolioCurrency = Literal["CNY", "HKD", "USD"]
HoldingDataStatus = Literal[
    "priced",
    "missing_price",
    "missing_fx",
    "currency_mismatch",
    "inactive_listing",
]
ReadingStatus = Literal["finished", "reading", "planned"]


def _strip_required(value: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError("字段不能为空")
    return normalized


def _strip_optional(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


class PortfolioOwnerCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    owner_type: OwnerType
    notes: str | None = Field(default=None, max_length=4000)

    _normalize_name = field_validator("name")(_strip_required)
    _normalize_notes = field_validator("notes")(_strip_optional)


class PortfolioOwnerUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    owner_type: OwnerType | None = None
    notes: str | None = Field(default=None, max_length=4000)

    _normalize_name = field_validator("name")(_strip_optional)
    _normalize_notes = field_validator("notes")(_strip_optional)

    @model_validator(mode="after")
    def reject_null_required_fields(self):
        for field_name in {"name", "owner_type"} & self.model_fields_set:
            if getattr(self, field_name) is None:
                raise ValueError(f"{field_name} 不能为 null")
        return self


class PortfolioOwnerRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    owner_type: OwnerType
    notes: str | None = None
    display_order: int
    created_at: datetime
    updated_at: datetime


class PortfolioOwnerListResponse(BaseModel):
    items: list[PortfolioOwnerRead]
    total: int


class PortfolioSnapshotCreate(BaseModel):
    title: str = Field(min_length=1, max_length=160)
    as_of_date: date
    base_currency: PortfolioCurrency
    notes: str | None = Field(default=None, max_length=4000)
    copy_from_snapshot_id: int | None = Field(default=None, ge=1)

    _normalize_title = field_validator("title")(_strip_required)
    _normalize_notes = field_validator("notes")(_strip_optional)

    @field_validator("as_of_date")
    @classmethod
    def reject_future_date(cls, value: date) -> date:
        if value > date.today():
            raise ValueError("统计日期不能晚于今天")
        return value


class PortfolioSnapshotUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=160)
    as_of_date: date | None = None
    base_currency: PortfolioCurrency | None = None
    notes: str | None = Field(default=None, max_length=4000)

    _normalize_title = field_validator("title")(_strip_optional)
    _normalize_notes = field_validator("notes")(_strip_optional)

    @field_validator("as_of_date")
    @classmethod
    def reject_future_date(cls, value: date | None) -> date | None:
        if value is not None and value > date.today():
            raise ValueError("统计日期不能晚于今天")
        return value

    @model_validator(mode="after")
    def reject_null_required_fields(self):
        for field_name in {"title", "as_of_date", "base_currency"} & self.model_fields_set:
            if getattr(self, field_name) is None:
                raise ValueError(f"{field_name} 不能为 null")
        return self


class PortfolioSnapshotRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    owner_id: int
    title: str
    as_of_date: date
    base_currency: PortfolioCurrency
    notes: str | None = None
    display_order: int
    created_at: datetime
    updated_at: datetime


class PortfolioSnapshotListResponse(BaseModel):
    owner_id: int
    items: list[PortfolioSnapshotRead]
    total: int


class PortfolioHoldingCreate(BaseModel):
    listing_id: int = Field(ge=1)
    quantity: Decimal = Field(gt=0, max_digits=28, decimal_places=8)
    notes: str | None = Field(default=None, max_length=4000)
    display_order: int = Field(default=0, ge=0)

    _normalize_notes = field_validator("notes")(_strip_optional)


class PortfolioHoldingUpdate(BaseModel):
    listing_id: int | None = Field(default=None, ge=1)
    quantity: Decimal | None = Field(
        default=None,
        gt=0,
        max_digits=28,
        decimal_places=8,
    )
    notes: str | None = Field(default=None, max_length=4000)
    display_order: int | None = Field(default=None, ge=0)

    _normalize_notes = field_validator("notes")(_strip_optional)

    @model_validator(mode="after")
    def reject_null_required_fields(self):
        for field_name in {"listing_id", "quantity", "display_order"} & self.model_fields_set:
            if getattr(self, field_name) is None:
                raise ValueError(f"{field_name} 不能为 null")
        return self


class PortfolioHoldingRead(BaseModel):
    id: int
    snapshot_id: int
    listing_id: int
    company_id: int
    company_name: str
    ticker: str
    exchange: str
    market: str
    trading_currency: str
    security_type: str
    quantity: Decimal
    notes: str | None = None
    display_order: int
    created_at: datetime
    updated_at: datetime


class PortfolioHoldingListResponse(BaseModel):
    snapshot_id: int
    items: list[PortfolioHoldingRead]
    total: int


class PortfolioReorderRequest(BaseModel):
    ordered_ids: list[int] = Field(min_length=1, max_length=500)

    @field_validator("ordered_ids")
    @classmethod
    def validate_ordered_ids(cls, value: list[int]) -> list[int]:
        if any(item_id < 1 for item_id in value):
            raise ValueError("排序 ID 必须为正整数")
        if len(value) != len(set(value)):
            raise ValueError("排序 ID 不能重复")
        return value


class PortfolioListingSearchItem(BaseModel):
    id: int
    company_id: int
    company_name: str
    ticker: str
    symbol: str
    exchange: str
    market: str
    trading_currency: str
    security_type: str
    is_primary: bool


class PortfolioListingSearchResponse(BaseModel):
    items: list[PortfolioListingSearchItem]
    total: int


class SecUsListingCatalogItem(BaseModel):
    cik: str
    company_name: str
    symbol: str
    ticker: str
    exchange: Literal["NASDAQ", "NYSE"]


class SecUsListingCatalogResponse(BaseModel):
    items: list[SecUsListingCatalogItem]
    total: int
    source: str = "SEC company_tickers_exchange.json"


class SecUsListingImportRequest(BaseModel):
    cik: str = Field(min_length=1, max_length=10, pattern=r"^\d+$")
    symbol: str = Field(min_length=1, max_length=12, pattern=r"^[A-Za-z0-9.-]+$")

    @field_validator("cik", "symbol")
    @classmethod
    def normalize_sec_identity(cls, value: str) -> str:
        return value.strip().upper()


class AhListingCatalogItem(BaseModel):
    quote_id: str
    company_name: str
    symbol: str
    ticker: str
    exchange: Literal["SSE", "SZSE", "BSE", "HKEX"]
    market: Literal["A_SHARE", "HK"]
    trading_currency: Literal["CNY", "HKD"]
    security_type: Literal["common_stock"] = "common_stock"


class AhListingCatalogResponse(BaseModel):
    items: list[AhListingCatalogItem]
    total: int
    source: str = "Eastmoney security suggest directory"


class AhListingImportRequest(BaseModel):
    quote_id: str = Field(
        min_length=3,
        max_length=32,
        pattern=r"^\d{1,3}\.[A-Za-z0-9_-]+$",
    )

    @field_validator("quote_id")
    @classmethod
    def normalize_quote_id(cls, value: str) -> str:
        return value.strip().upper()


class BuyMemoCompanyCandidate(BaseModel):
    company_id: int
    company_name: str
    primary_ticker: str
    decision_count: int


class BuyMemoCompanyCandidateResponse(BaseModel):
    items: list[BuyMemoCompanyCandidate]
    total: int


class BuyMemoDecisionCandidate(BaseModel):
    price_decision_run_id: int
    version_no: int
    run_version: str
    listing_ticker: str
    exchange: str | None = None
    trading_currency: str | None = None
    base_intrinsic_value: Decimal
    suggested_buy_price: Decimal
    designed_safety_margin: Decimal
    latest_report_period: str | None = None
    created_at: datetime
    already_imported: bool


class BuyMemoDecisionCandidateResponse(BaseModel):
    company_id: int
    items: list[BuyMemoDecisionCandidate]
    total: int


class BuyMemoEntryCreate(BaseModel):
    price_decision_run_id: int = Field(ge=1)


class BuyMemoEntryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    company_id: int
    source_price_decision_run_id: int | None = None
    company_name: str
    listing_ticker: str
    exchange: str | None = None
    trading_currency: str | None = None
    base_intrinsic_value: Decimal
    suggested_buy_price: Decimal
    designed_safety_margin: Decimal
    latest_report_period: str | None = None
    price_decision_version_no: int
    price_decision_run_version: str
    price_decision_created_at: datetime
    created_at: datetime
    updated_at: datetime


class BuyMemoEntryListResponse(BaseModel):
    items: list[BuyMemoEntryRead]
    total: int


class ReadingProgressCreate(BaseModel):
    progress_percent: int = Field(default=0, ge=0, le=100)


class ReadingProgressUpdate(BaseModel):
    progress_percent: int = Field(ge=0, le=100)


class ReadingProgressRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    book_id: int
    round_number: int
    progress_percent: int
    created_at: datetime
    updated_at: datetime


class ReadingBookCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    author: str | None = Field(default=None, max_length=160)
    status: ReadingStatus = "planned"
    notes: str | None = Field(default=None, max_length=8000)
    initial_progress: int = Field(default=0, ge=0, le=100)

    _normalize_title = field_validator("title")(_strip_required)
    _normalize_author = field_validator("author")(_strip_optional)
    _normalize_notes = field_validator("notes")(_strip_optional)


class ReadingBookUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    author: str | None = Field(default=None, max_length=160)
    status: ReadingStatus | None = None
    notes: str | None = Field(default=None, max_length=8000)

    _normalize_title = field_validator("title")(_strip_optional)
    _normalize_author = field_validator("author")(_strip_optional)
    _normalize_notes = field_validator("notes")(_strip_optional)

    @model_validator(mode="after")
    def reject_null_required_fields(self):
        for field_name in {"title", "status"} & self.model_fields_set:
            if getattr(self, field_name) is None:
                raise ValueError(f"{field_name} 不能为 null")
        return self


class ReadingBookRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    author: str | None = None
    status: ReadingStatus
    notes: str | None = None
    created_at: datetime
    updated_at: datetime
    progress_entries: list[ReadingProgressRead]


class ReadingBookListResponse(BaseModel):
    items: list[ReadingBookRead]
    total: int


class PortfolioValuationItem(BaseModel):
    holding_id: int
    listing_id: int
    company_id: int
    company_name: str
    ticker: str
    exchange: str
    market: str
    trading_currency: str
    security_type: str
    quantity: Decimal
    latest_price: Decimal | None = None
    quote_currency: str | None = None
    quote_as_of: datetime | None = None
    quote_source: str | None = None
    quote_source_url: str | None = None
    local_market_value: Decimal | None = None
    fx_rate: Decimal | None = None
    fx_rate_date: date | None = None
    fx_source: str | None = None
    base_market_value: Decimal | None = None
    weight: Decimal | None = None
    data_status: HoldingDataStatus
    status_reason: str


class PortfolioValuationResponse(BaseModel):
    snapshot: PortfolioSnapshotRead
    owner: PortfolioOwnerRead
    priced_total: Decimal | None = None
    base_currency: PortfolioCurrency
    holding_count: int
    priced_count: int
    unpriced_count: int
    valuation_status: Literal["empty", "complete", "incomplete"]
    items: list[PortfolioValuationItem]


class PortfolioQuoteRefreshItem(BaseModel):
    listing_id: int
    ticker: str
    status: Literal["success", "failed"]
    market_snapshot_id: int | None = None
    error: str | None = None


class PortfolioFxRefreshItem(BaseModel):
    base_currency: str
    quote_currency: str
    status: Literal["identity", "success", "failed"]
    fx_rate_snapshot_id: int | None = None
    error: str | None = None


class PortfolioRefreshResponse(BaseModel):
    snapshot_id: int
    status: Literal["success", "partial", "failed"]
    succeeded: int
    failed: int
    quote_results: list[PortfolioQuoteRefreshItem]
    fx_results: list[PortfolioFxRefreshItem]
    valuation: PortfolioValuationResponse


class MarketFearIndicatorRead(BaseModel):
    market: Literal["A_SHARE", "HK", "US"]
    indicator_code: str
    indicator_name: str
    value: Decimal | None = None
    data_date: date | None = None
    daily_change: Decimal | None = None
    moving_average_20: Decimal | None = None
    percentile_3y: Decimal | None = None
    temperature_score: Decimal | None = None
    temperature_level: str | None = None
    source: str | None = None
    source_url: str | None = None
    fetched_at: datetime | None = None
    observation_count: int | None = None
    freshness: Literal["fresh", "stale", "unavailable"]
    refresh_error: str | None = None
    is_proxy: bool = False
    proxy_notice: str | None = None


class MarketFearListResponse(BaseModel):
    status: Literal["success", "partial", "failed"]
    items: list[MarketFearIndicatorRead]
    notice: str = (
        "波动率指标反映市场预期波动程度，不代表价格方向，也不是买卖建议。"
    )


class DeleteResponse(BaseModel):
    id: int
    deleted: bool
