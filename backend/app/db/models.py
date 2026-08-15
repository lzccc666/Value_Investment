from __future__ import annotations

from datetime import UTC, date, datetime, timedelta, timezone

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.db.base import Base

SHANGHAI_TZ = timezone(timedelta(hours=8), "Asia/Shanghai")


def utc_now() -> datetime:
    return datetime.now(UTC)


def shanghai_now() -> datetime:
    return datetime.now(SHANGHAI_TZ)


class Company(Base):
    __tablename__ = "companies"
    __table_args__ = (
        UniqueConstraint("ticker", "exchange", name="uq_companies_ticker_exchange"),
        Index("ix_companies_name", "name"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    ticker: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    exchange: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
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
    user_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )

    company: Mapped[Company] = relationship(back_populates="valuation_runs")
    memo: Mapped[InvestmentMemo | None] = relationship()
