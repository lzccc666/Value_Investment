from __future__ import annotations

from datetime import UTC, date, datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.db.base import Base

SHANGHAI_TZ = timezone(timedelta(hours=8), "Asia/Shanghai")


def utc_now() -> datetime:
    return datetime.now(UTC)


def shanghai_now() -> datetime:
    return datetime.now(SHANGHAI_TZ)


class ParameterConfigVersion(Base):
    __tablename__ = "parameter_config_versions"
    __table_args__ = (
        UniqueConstraint("version_no", name="uq_parameter_config_versions_version_no"),
        Index("ix_parameter_config_versions_status", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    version_no: Mapped[int] = mapped_column(nullable=False)
    schema_version: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(40), default="draft", nullable=False)
    scope_type: Mapped[str] = mapped_column(String(40), default="global", nullable=False)
    scope_key: Mapped[str | None] = mapped_column(String(120), nullable=True)
    config_json: Mapped[dict[str, object]] = mapped_column(JSON, default=dict, nullable=False)
    config_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    change_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Company(Base):
    __tablename__ = "companies"
    __table_args__ = (
        UniqueConstraint("ticker", "exchange", name="uq_companies_ticker_exchange"),
        Index("uq_companies_canonical_key", "canonical_key", unique=True),
        Index("ix_companies_name", "name"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    ticker: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    exchange: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    canonical_key: Mapped[str | None] = mapped_column(String(160), nullable=True)
    legal_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    aliases: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    domicile_country: Mapped[str | None] = mapped_column(String(2), nullable=True)
    reporting_currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    fiscal_year_end: Mapped[str | None] = mapped_column(String(5), nullable=True)
    external_ids: Mapped[dict[str, object]] = mapped_column(JSON, default=dict, nullable=False)
    industry: Mapped[str | None] = mapped_column(String(120), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    listed_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(40), default="watchlist", nullable=False)
    tags: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    market_cap: Mapped[float | None] = mapped_column(Float, nullable=True)
    current_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    pe_ttm: Mapped[float | None] = mapped_column(Float, nullable=True)
    pe_dynamic: Mapped[float | None] = mapped_column(Float, nullable=True)
    pe_static: Mapped[float | None] = mapped_column(Float, nullable=True)
    pb_ratio: Mapped[float | None] = mapped_column(Float, nullable=True)
    ps_ratio: Mapped[float | None] = mapped_column(Float, nullable=True)
    dividend_yield_ttm: Mapped[float | None] = mapped_column(Float, nullable=True)
    dividend_yield_static: Mapped[float | None] = mapped_column(Float, nullable=True)
    market_data_source: Mapped[str | None] = mapped_column(String(120), nullable=True)
    market_data_source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    market_data_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=shanghai_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=shanghai_now, onupdate=shanghai_now, nullable=False
    )

    financial_statements: Mapped[list[FinancialStatement]] = relationship(
        back_populates="company", cascade="all, delete-orphan"
    )
    announcements: Mapped[list[Announcement]] = relationship(
        back_populates="company", cascade="all, delete-orphan"
    )
    evidence_items: Mapped[list[Evidence]] = relationship(
        back_populates="company", cascade="all, delete-orphan"
    )
    analysis_runs: Mapped[list[AnalysisRun]] = relationship(
        back_populates="company", cascade="all, delete-orphan"
    )
    investment_memos: Mapped[list[InvestmentMemo]] = relationship(
        back_populates="company", cascade="all, delete-orphan"
    )
    valuation_runs: Mapped[list[ValuationRun]] = relationship(
        back_populates="company", cascade="all, delete-orphan"
    )
    price_decision_runs: Mapped[list[PriceDecisionRun]] = relationship(
        back_populates="company", cascade="all, delete-orphan"
    )
    listings: Mapped[list[SecurityListing]] = relationship(
        back_populates="company", cascade="all, delete-orphan"
    )

    @property
    def primary_listing(self) -> SecurityListing | None:
        active = [listing for listing in self.listings if listing.is_active]
        fallback = active[0] if active else None
        return next((listing for listing in active if listing.is_primary), fallback)


class SecurityListing(Base):
    __tablename__ = "security_listings"
    __table_args__ = (
        UniqueConstraint("exchange", "ticker", name="uq_security_listings_exchange_ticker"),
        Index("ix_security_listings_company_active", "company_id", "is_active"),
        Index(
            "uq_security_listings_company_primary_active",
            "company_id",
            unique=True,
            sqlite_where=text("is_primary = 1 AND is_active = 1"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True, nullable=False)
    ticker: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    symbol: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    exchange: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    market: Mapped[str] = mapped_column(String(16), index=True, nullable=False)
    trading_currency: Mapped[str] = mapped_column(String(3), nullable=False)
    security_type: Mapped[str] = mapped_column(String(24), default="common_stock", nullable=False)
    listed_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    underlying_shares_per_listing_unit: Mapped[float | None] = mapped_column(
        Float, default=1.0, nullable=True
    )
    provider_identifiers: Mapped[dict[str, object]] = mapped_column(
        JSON, default=dict, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )

    company: Mapped[Company] = relationship(back_populates="listings")
    market_snapshots: Mapped[list[MarketSnapshot]] = relationship(
        back_populates="listing", cascade="all, delete-orphan"
    )
    portfolio_holdings: Mapped[list[PortfolioHolding]] = relationship(
        back_populates="listing"
    )


class MarketSnapshot(Base):
    __tablename__ = "market_snapshots"
    __table_args__ = (
        Index("ix_market_snapshots_listing_price_as_of", "listing_id", "price_as_of"),
        Index("ix_market_snapshots_listing_fetched", "listing_id", "fetched_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    listing_id: Mapped[int] = mapped_column(
        ForeignKey("security_listings.id"), index=True, nullable=False
    )
    price: Mapped[float] = mapped_column(Float, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    market_cap: Mapped[float | None] = mapped_column(Float, nullable=True)
    pe_ttm: Mapped[float | None] = mapped_column(Float, nullable=True)
    pe_dynamic: Mapped[float | None] = mapped_column(Float, nullable=True)
    pe_static: Mapped[float | None] = mapped_column(Float, nullable=True)
    pb_ratio: Mapped[float | None] = mapped_column(Float, nullable=True)
    ps_ratio: Mapped[float | None] = mapped_column(Float, nullable=True)
    dividend_yield_ttm: Mapped[float | None] = mapped_column(Float, nullable=True)
    dividend_yield_static: Mapped[float | None] = mapped_column(Float, nullable=True)
    price_as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source: Mapped[str] = mapped_column(String(120), nullable=False)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_snapshot_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)

    listing: Mapped[SecurityListing] = relationship(back_populates="market_snapshots")


class FxRateSnapshot(Base):
    __tablename__ = "fx_rate_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "base_currency",
            "quote_currency",
            "rate_date",
            "source",
            name="uq_fx_rate_snapshots_direction_date_source",
        ),
        Index(
            "ix_fx_rate_snapshots_direction_date",
            "base_currency",
            "quote_currency",
            "rate_date",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    base_currency: Mapped[str] = mapped_column(String(3), nullable=False)
    quote_currency: Mapped[str] = mapped_column(String(3), nullable=False)
    rate: Mapped[float] = mapped_column(Float, nullable=False)
    rate_date: Mapped[date] = mapped_column(Date, nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source: Mapped[str] = mapped_column(String(120), nullable=False)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_snapshot_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    calculation_audit: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)


class PortfolioOwner(Base):
    __tablename__ = "portfolio_owners"
    __table_args__ = (
        CheckConstraint(
            "owner_type IN ('self', 'investor')",
            name="ck_portfolio_owners_owner_type",
        ),
        Index("ix_portfolio_owners_name", "name"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    owner_type: Mapped[str] = mapped_column(String(16), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    display_order: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )

    snapshots: Mapped[list[PortfolioSnapshot]] = relationship(
        back_populates="owner", cascade="all, delete-orphan"
    )


class PortfolioSnapshot(Base):
    __tablename__ = "portfolio_snapshots"
    __table_args__ = (
        CheckConstraint(
            "base_currency IN ('CNY', 'HKD', 'USD')",
            name="ck_portfolio_snapshots_base_currency",
        ),
        Index(
            "ix_portfolio_snapshots_owner_as_of",
            "owner_id",
            "as_of_date",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(
        ForeignKey("portfolio_owners.id"), index=True, nullable=False
    )
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    as_of_date: Mapped[date] = mapped_column(Date, nullable=False)
    base_currency: Mapped[str] = mapped_column(String(3), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    display_order: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )

    owner: Mapped[PortfolioOwner] = relationship(back_populates="snapshots")
    holdings: Mapped[list[PortfolioHolding]] = relationship(
        back_populates="snapshot",
        cascade="all, delete-orphan",
        order_by="PortfolioHolding.display_order, PortfolioHolding.id",
    )


class PortfolioHolding(Base):
    __tablename__ = "portfolio_holdings"
    __table_args__ = (
        UniqueConstraint(
            "snapshot_id",
            "listing_id",
            name="uq_portfolio_holdings_snapshot_listing",
        ),
        CheckConstraint("quantity > 0", name="ck_portfolio_holdings_quantity_positive"),
        Index(
            "ix_portfolio_holdings_snapshot_order",
            "snapshot_id",
            "display_order",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    snapshot_id: Mapped[int] = mapped_column(
        ForeignKey("portfolio_snapshots.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    listing_id: Mapped[int] = mapped_column(
        ForeignKey("security_listings.id"), index=True, nullable=False
    )
    quantity: Mapped[Decimal] = mapped_column(Numeric(28, 8), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    display_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )

    snapshot: Mapped[PortfolioSnapshot] = relationship(back_populates="holdings")
    listing: Mapped[SecurityListing] = relationship(back_populates="portfolio_holdings")


class MarketFearSnapshot(Base):
    __tablename__ = "market_fear_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "market",
            "data_date",
            "source",
            name="uq_market_fear_snapshots_market_date_source",
        ),
        Index(
            "ix_market_fear_snapshots_market_fetched",
            "market",
            "fetched_at",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    market: Mapped[str] = mapped_column(String(16), nullable=False)
    indicator_code: Mapped[str] = mapped_column(String(24), nullable=False)
    indicator_name: Mapped[str] = mapped_column(String(80), nullable=False)
    value: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    daily_change: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    moving_average_20: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    percentile_3y: Mapped[Decimal] = mapped_column(Numeric(8, 4), nullable=False)
    temperature_score: Mapped[Decimal] = mapped_column(Numeric(8, 4), nullable=False)
    temperature_level: Mapped[str] = mapped_column(String(24), nullable=False)
    data_date: Mapped[date] = mapped_column(Date, nullable=False)
    observation_count: Mapped[int] = mapped_column(Integer, nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source: Mapped[str] = mapped_column(String(120), nullable=False)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_snapshot_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )


class BuyMemoEntry(Base):
    __tablename__ = "buy_memo_entries"
    __table_args__ = (
        UniqueConstraint(
            "source_price_decision_run_id",
            name="uq_buy_memo_entries_source_price_decision",
        ),
        CheckConstraint(
            "base_intrinsic_value > 0",
            name="ck_buy_memo_entries_intrinsic_value_positive",
        ),
        CheckConstraint(
            "suggested_buy_price > 0",
            name="ck_buy_memo_entries_buy_price_positive",
        ),
        CheckConstraint(
            "designed_safety_margin >= 0 AND designed_safety_margin <= 1",
            name="ck_buy_memo_entries_safety_margin_range",
        ),
        Index("ix_buy_memo_entries_company_created", "company_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id"), index=True, nullable=False
    )
    source_price_decision_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("price_decision_runs.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    company_name: Mapped[str] = mapped_column(String(255), nullable=False)
    listing_ticker: Mapped[str] = mapped_column(String(32), nullable=False)
    exchange: Mapped[str | None] = mapped_column(String(32), nullable=True)
    trading_currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    base_intrinsic_value: Mapped[Decimal] = mapped_column(Numeric(28, 8), nullable=False)
    suggested_buy_price: Mapped[Decimal] = mapped_column(Numeric(28, 8), nullable=False)
    designed_safety_margin: Mapped[Decimal] = mapped_column(Numeric(10, 8), nullable=False)
    latest_report_period: Mapped[str | None] = mapped_column(String(32), nullable=True)
    price_decision_version_no: Mapped[int] = mapped_column(nullable=False)
    price_decision_run_version: Mapped[str] = mapped_column(String(40), nullable=False)
    price_decision_created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )


class FinancialStatement(Base):
    __tablename__ = "financial_statements"
    __table_args__ = (
        UniqueConstraint(
            "company_id",
            "period",
            "statement_type",
            name="uq_financial_statements_company_period_type",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True, nullable=False)
    period: Mapped[str] = mapped_column(String(20), index=True, nullable=False)
    statement_type: Mapped[str] = mapped_column(String(40), index=True, nullable=False)
    currency: Mapped[str] = mapped_column(String(12), default="CNY", nullable=False)
    fields: Mapped[dict[str, object]] = mapped_column(JSON, default=dict, nullable=False)
    source: Mapped[str | None] = mapped_column(String(120), nullable=True)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_record_id: Mapped[str | None] = mapped_column(String(160), nullable=True)
    filing_type: Mapped[str | None] = mapped_column(String(40), nullable=True)
    taxonomy: Mapped[str | None] = mapped_column(String(40), nullable=True)
    period_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    period_end: Mapped[date | None] = mapped_column(Date, nullable=True)
    period_type: Mapped[str | None] = mapped_column(String(24), nullable=True)
    fiscal_year: Mapped[int | None] = mapped_column(nullable=True)
    fiscal_period: Mapped[str | None] = mapped_column(String(16), nullable=True)
    filed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    unit_scale: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    is_amendment: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    raw_snapshot_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    company: Mapped[Company] = relationship(back_populates="financial_statements")


class Announcement(Base):
    __tablename__ = "announcements"
    __table_args__ = (
        UniqueConstraint(
            "company_id",
            "source_url",
            name="uq_announcements_company_source_url",
        ),
        Index(
            "ix_announcements_company_title_published",
            "company_id",
            "title",
            "published_at",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True, nullable=False)
    listing_id: Mapped[int | None] = mapped_column(
        ForeignKey("security_listings.id"), index=True, nullable=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    published_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), index=True, nullable=False
    )
    category: Mapped[str] = mapped_column(String(80), index=True, nullable=False)
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    key_facts: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    source: Mapped[str | None] = mapped_column(String(120), nullable=True)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_document_id: Mapped[str | None] = mapped_column(String(160), nullable=True)
    document_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    filing_form: Mapped[str | None] = mapped_column(String(40), nullable=True)
    language: Mapped[str | None] = mapped_column(String(16), nullable=True)
    period_end: Mapped[date | None] = mapped_column(Date, nullable=True)
    content_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    content_source: Mapped[str | None] = mapped_column(String(120), nullable=True)
    content_fetched_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    raw_content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    importance_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    impact_direction: Mapped[str | None] = mapped_column(String(40), nullable=True)
    sentiment: Mapped[str | None] = mapped_column(String(40), nullable=True)
    positive_impacts: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    negative_impacts: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    neutral_impacts: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    risk_tips: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    review_questions: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    tags: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    summary_status: Mapped[str] = mapped_column(String(40), default="unprocessed", nullable=False)
    summary_model_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    summary_prompt_version: Mapped[str | None] = mapped_column(String(80), nullable=True)
    summarized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    company: Mapped[Company] = relationship(back_populates="announcements")


class Evidence(Base):
    __tablename__ = "evidence"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True, nullable=False)
    source_type: Mapped[str] = mapped_column(String(40), index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    source: Mapped[str | None] = mapped_column(String(160), nullable=True)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), index=True, nullable=True
    )
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    key_facts: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    impact_direction: Mapped[str] = mapped_column(String(40), index=True, nullable=False)
    importance_score: Mapped[float] = mapped_column(Float, nullable=False)
    credibility_score: Mapped[float] = mapped_column(Float, nullable=False)
    tags: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    requires_review: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    price_sensitive: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    use_scope: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    analysis_status: Mapped[str] = mapped_column(
        String(40), default="model_analyzed", nullable=False
    )
    analysis_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_snapshot: Mapped[dict[str, object]] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    company: Mapped[Company] = relationship(back_populates="evidence_items")


class AnalysisRun(Base):
    __tablename__ = "analysis_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True, nullable=False)
    run_type: Mapped[str] = mapped_column(String(80), index=True, nullable=False)
    analyst_profile: Mapped[str | None] = mapped_column(String(80), index=True, nullable=True)
    run_version: Mapped[str | None] = mapped_column(String(40), nullable=True)
    model_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    prompt_version: Mapped[str | None] = mapped_column(String(80), nullable=True)
    data_snapshot_hash: Mapped[str | None] = mapped_column(String(120), nullable=True)
    input_snapshot: Mapped[dict[str, object]] = mapped_column(JSON, default=dict, nullable=False)
    result: Mapped[dict[str, object]] = mapped_column(JSON, default=dict, nullable=False)
    config_version: Mapped[int | None] = mapped_column(nullable=True)
    config_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    config_snapshot: Mapped[dict[str, object]] = mapped_column(JSON, default=dict, nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    parent_run_id: Mapped[int | None] = mapped_column(nullable=True)
    is_latest: Mapped[bool] = mapped_column(default=False, nullable=False)
    user_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(40), default="success", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    company: Mapped[Company] = relationship(back_populates="analysis_runs")


class InvestmentMemo(Base):
    __tablename__ = "investment_memos"
    __table_args__ = (
        Index("ix_investment_memos_company_latest", "company_id", "is_latest"),
        Index("ix_investment_memos_company_created", "company_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True, nullable=False)
    generation_run_id: Mapped[int] = mapped_column(
        ForeignKey("analysis_runs.id"), index=True, nullable=False
    )
    parent_memo_id: Mapped[int | None] = mapped_column(
        ForeignKey("investment_memos.id"), index=True, nullable=True
    )
    version_no: Mapped[int] = mapped_column(default=1, nullable=False)
    editor_type: Mapped[str] = mapped_column(String(40), default="model", nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    conclusion: Mapped[str] = mapped_column(String(40), nullable=False)
    sections: Mapped[dict[str, object]] = mapped_column(JSON, default=dict, nullable=False)
    markdown: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_analyst_run_ids: Mapped[list[int]] = mapped_column(JSON, default=list, nullable=False)
    source_snapshot_hash: Mapped[str | None] = mapped_column(String(120), nullable=True)
    config_version: Mapped[int | None] = mapped_column(nullable=True)
    config_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    config_snapshot: Mapped[dict[str, object]] = mapped_column(JSON, default=dict, nullable=False)
    change_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(40), default="draft", nullable=False)
    is_latest: Mapped[bool] = mapped_column(default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )

    company: Mapped[Company] = relationship(back_populates="investment_memos")
    generation_run: Mapped[AnalysisRun] = relationship()


class ValuationRun(Base):
    __tablename__ = "valuation_runs"
    __table_args__ = (
        Index("ix_valuation_runs_company_created", "company_id", "created_at"),
        Index("ix_valuation_runs_company_status", "company_id", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True, nullable=False)
    memo_id: Mapped[int | None] = mapped_column(
        ForeignKey("investment_memos.id"), index=True, nullable=True
    )
    run_version: Mapped[str] = mapped_column(String(40), default="010_v1", nullable=False)
    status: Mapped[str] = mapped_column(String(40), default="draft", nullable=False)
    price_blind: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    forbidden_price_inputs: Mapped[dict[str, object]] = mapped_column(
        JSON, default=dict, nullable=False
    )
    input_snapshot: Mapped[dict[str, object]] = mapped_column(JSON, default=dict, nullable=False)
    input_snapshot_hash: Mapped[str | None] = mapped_column(String(120), nullable=True)
    config_version: Mapped[int | None] = mapped_column(nullable=True)
    config_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    config_snapshot: Mapped[dict[str, object]] = mapped_column(JSON, default=dict, nullable=False)
    valuation_inputs: Mapped[dict[str, object]] = mapped_column(JSON, default=dict, nullable=False)
    model_suggested_assumptions: Mapped[dict[str, object]] = mapped_column(
        JSON, default=dict, nullable=False
    )
    user_adjusted_assumptions: Mapped[dict[str, object]] = mapped_column(
        JSON, default=dict, nullable=False
    )
    assumptions: Mapped[dict[str, object]] = mapped_column(JSON, default=dict, nullable=False)
    methods: Mapped[dict[str, object]] = mapped_column(JSON, default=dict, nullable=False)
    results: Mapped[dict[str, object]] = mapped_column(JSON, default=dict, nullable=False)
    sensitivity: Mapped[dict[str, object]] = mapped_column(JSON, default=dict, nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    confidence_summary: Mapped[dict[str, object]] = mapped_column(
        JSON, default=dict, nullable=False
    )
    source_map: Mapped[dict[str, object]] = mapped_column(JSON, default=dict, nullable=False)
    valuation_currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    share_basis_snapshot: Mapped[dict[str, object]] = mapped_column(
        JSON, default=dict, nullable=False
    )
    user_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )

    company: Mapped[Company] = relationship(back_populates="valuation_runs")
    memo: Mapped[InvestmentMemo | None] = relationship()


class PriceDecisionRun(Base):
    __tablename__ = "price_decision_runs"
    __table_args__ = (
        Index("ix_price_decision_runs_company_created", "company_id", "created_at"),
        Index("ix_price_decision_runs_company_status", "company_id", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True, nullable=False)
    valuation_run_id: Mapped[int] = mapped_column(
        ForeignKey("valuation_runs.id"), index=True, nullable=False
    )
    memo_id: Mapped[int] = mapped_column(
        ForeignKey("investment_memos.id"), index=True, nullable=False
    )
    listing_id: Mapped[int | None] = mapped_column(
        ForeignKey("security_listings.id"), index=True, nullable=True
    )
    market_snapshot_id: Mapped[int | None] = mapped_column(
        ForeignKey("market_snapshots.id"), index=True, nullable=True
    )
    fx_rate_snapshot_id: Mapped[int | None] = mapped_column(
        ForeignKey("fx_rate_snapshots.id"), index=True, nullable=True
    )
    version_no: Mapped[int] = mapped_column(default=1, nullable=False)
    run_version: Mapped[str] = mapped_column(String(40), default="011_v1", nullable=False)
    formula_version: Mapped[str] = mapped_column(String(40), default="011_v1", nullable=False)
    status: Mapped[str] = mapped_column(String(40), default="active", nullable=False)
    input_snapshot: Mapped[dict[str, object]] = mapped_column(JSON, default=dict, nullable=False)
    input_snapshot_hash: Mapped[str] = mapped_column(String(120), nullable=False)
    config_version: Mapped[int | None] = mapped_column(nullable=True)
    config_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    config_snapshot: Mapped[dict[str, object]] = mapped_column(JSON, default=dict, nullable=False)
    intrinsic_values_per_share: Mapped[dict[str, float]] = mapped_column(
        JSON, default=dict, nullable=False
    )
    issuer_intrinsic_values_per_share: Mapped[dict[str, float]] = mapped_column(
        JSON, default=dict, nullable=False
    )
    valuation_currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    trading_currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    underlying_shares_per_listing_unit: Mapped[float | None] = mapped_column(
        Float, nullable=True
    )
    fx_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    current_price: Mapped[float] = mapped_column(Float, nullable=False)
    market_data_updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    analyst_score_total: Mapped[float | None] = mapped_column(Float, nullable=True)
    analyst_scorecard_snapshot: Mapped[dict[str, object]] = mapped_column(
        JSON, default=dict, nullable=False
    )
    suggested_safety_margin: Mapped[float] = mapped_column(Float, nullable=False)
    safety_margin_override: Mapped[float | None] = mapped_column(Float, nullable=True)
    effective_safety_margin: Mapped[float] = mapped_column(Float, nullable=False)
    scenario_buy_prices: Mapped[dict[str, float]] = mapped_column(
        JSON, default=dict, nullable=False
    )
    suggested_buy_price: Mapped[float] = mapped_column(Float, nullable=False)
    current_margin: Mapped[float] = mapped_column(Float, nullable=False)
    price_status: Mapped[str] = mapped_column(String(80), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    company: Mapped[Company] = relationship(back_populates="price_decision_runs")
    valuation_run: Mapped[ValuationRun] = relationship()
    memo: Mapped[InvestmentMemo] = relationship()
