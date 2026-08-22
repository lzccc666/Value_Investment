from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Literal, Protocol

from app.data_sources.eastmoney_announcements import FetchedAnnouncement
from app.data_sources.eastmoney_company_profile import FetchedCompanyProfile
from app.data_sources.eastmoney_financials import FetchedFinancialStatement
from app.data_sources.eastmoney_market_snapshot import FetchedMarketSnapshot

CapabilityStatus = Literal["available", "partial", "unavailable", "stale", "blocked"]


class MarketDataError(RuntimeError):
    code = "upstream_failed"


class UnsupportedMarketDataError(MarketDataError):
    code = "unsupported"


class MarketDataNotConfiguredError(MarketDataError):
    code = "not_configured"


class MarketDataRateLimitedError(MarketDataError):
    code = "rate_limited"


class MarketDataUpstreamError(MarketDataError):
    code = "upstream_failed"


class MarketDataParseError(MarketDataError):
    code = "parse_failed"


class MarketDataValidationError(MarketDataError):
    code = "validation_failed"


@dataclass(frozen=True)
class MarketContext:
    company_id: int
    canonical_key: str | None
    issuer_name: str
    aliases: tuple[str, ...]
    reporting_currency: str | None
    fiscal_year_end: str | None
    listing_id: int
    ticker: str
    symbol: str
    exchange: str
    market: str
    trading_currency: str
    security_type: str
    provider_identifiers: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class CapabilityState:
    status: CapabilityStatus
    provider: str | None = None
    reason: str | None = None
    remediation: str | None = None

    def as_dict(self) -> dict[str, object]:
        return {key: value for key, value in asdict(self).items() if value is not None}


@dataclass(frozen=True)
class ProviderCapabilities:
    profile: CapabilityState
    quote: CapabilityState
    financials: CapabilityState
    disclosures: CapabilityState
    dividend: CapabilityState
    fx: CapabilityState

    def as_dict(self) -> dict[str, dict[str, object]]:
        return {
            "profile": self.profile.as_dict(),
            "quote": self.quote.as_dict(),
            "financials": self.financials.as_dict(),
            "disclosures": self.disclosures.as_dict(),
            "dividend": self.dividend.as_dict(),
            "fx": self.fx.as_dict(),
        }


@dataclass(frozen=True)
class FetchedFxRate:
    base_currency: str
    quote_currency: str
    rate: float
    rate_date: date
    source: str
    source_url: str | None
    raw_snapshot_hash: str | None = None
    calculation_audit: dict[str, object] | None = None


class IssuerProfileProvider(Protocol):
    provider_name: str

    def fetch_profile(self, context: MarketContext) -> FetchedCompanyProfile: ...


class MarketSnapshotProvider(Protocol):
    provider_name: str

    def fetch_market_snapshot(self, context: MarketContext) -> FetchedMarketSnapshot: ...


class FinancialStatementProvider(Protocol):
    provider_name: str

    def fetch_financials(
        self, context: MarketContext, *, limit: int
    ) -> list[FetchedFinancialStatement]: ...


class DisclosureProvider(Protocol):
    provider_name: str

    def fetch_disclosures(
        self, context: MarketContext, *, years: int, limit: int
    ) -> list[FetchedAnnouncement]: ...


class DividendProvider(Protocol):
    provider_name: str

    def fetch_dividends(self, context: MarketContext) -> list[object]: ...


class FxRateProvider(Protocol):
    provider_name: str

    def fetch_rate(
        self, base_currency: str, quote_currency: str, *, rate_date: date | None = None
    ) -> FetchedFxRate: ...
