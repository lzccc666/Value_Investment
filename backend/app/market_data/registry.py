from __future__ import annotations

import importlib.util
from dataclasses import dataclass

from app.core.config import settings
from app.data_sources.eastmoney_announcements import EastmoneyAnnouncementClient
from app.data_sources.eastmoney_company_profile import EastmoneyCompanyProfileClient
from app.data_sources.eastmoney_financials import EastmoneyFinancialClient
from app.data_sources.eastmoney_market_snapshot import EastmoneyMarketSnapshotClient
from app.data_sources.ecb_fx import EcbReferenceRateProvider
from app.data_sources.hkex_news import HkexDisclosureProvider
from app.data_sources.hong_kong import (
    AkshareHongKongDividendProvider,
    AkshareHongKongFinancialProvider,
    AkshareHongKongIssuerProfileProvider,
)
from app.data_sources.sec_edgar import (
    SecDisclosureProvider,
    SecFinancialStatementProvider,
    SecIssuerProfileProvider,
)
from app.market_data.contracts import (
    CapabilityState,
    CapabilityStatus,
    DisclosureProvider,
    DividendProvider,
    FinancialStatementProvider,
    FxRateProvider,
    IssuerProfileProvider,
    MarketContext,
    MarketSnapshotProvider,
    ProviderCapabilities,
    UnsupportedMarketDataError,
)


class EastmoneyIssuerProfileProvider:
    provider_name = "eastmoney_company_profile"

    def __init__(self, client: EastmoneyCompanyProfileClient | None = None) -> None:
        self.client = client or EastmoneyCompanyProfileClient()

    def fetch_profile(self, context: MarketContext):
        return self.client.fetch_company_profile(context.ticker)


class EastmoneyQuoteProvider:
    provider_name = "eastmoney_quote_snapshot"

    def __init__(self, client: EastmoneyMarketSnapshotClient | None = None) -> None:
        self.client = client or EastmoneyMarketSnapshotClient()

    def fetch_market_snapshot(self, context: MarketContext):
        return self.client.fetch_market_snapshot(
            context.ticker,
            exchange=context.exchange,
        )


class EastmoneyFinancialProvider:
    provider_name = "eastmoney_f10"

    def __init__(self, client: EastmoneyFinancialClient | None = None) -> None:
        self.client = client or EastmoneyFinancialClient()

    def fetch_financials(self, context: MarketContext, *, limit: int):
        return self.client.fetch_financials(context.ticker, limit=limit)


class EastmoneyDisclosureProvider:
    provider_name = "eastmoney_announcements"

    def __init__(self, client: EastmoneyAnnouncementClient | None = None) -> None:
        self.client = client or EastmoneyAnnouncementClient()

    def fetch_disclosures(self, context: MarketContext, *, years: int, limit: int):
        return self.client.fetch_announcements(context.ticker, years=years, limit=limit)


@dataclass(frozen=True)
class MarketProviderBundle:
    capabilities: ProviderCapabilities
    profile: IssuerProfileProvider | None = None
    quote: MarketSnapshotProvider | None = None
    financials: FinancialStatementProvider | None = None
    disclosures: DisclosureProvider | None = None
    dividends: DividendProvider | None = None
    fx: FxRateProvider | None = None


class MarketProviderRegistry:
    def __init__(self) -> None:
        self._bundles: dict[str, MarketProviderBundle] = {}

    def register(self, market: str, bundle: MarketProviderBundle) -> None:
        self._bundles[market.strip().upper()] = bundle

    def resolve(self, market: str) -> MarketProviderBundle:
        normalized = market.strip().upper()
        bundle = self._bundles.get(normalized)
        if bundle is None:
            raise UnsupportedMarketDataError(f"当前市场没有已注册的数据源：{market}")
        return bundle

    def capabilities(self, market: str) -> ProviderCapabilities:
        return self.resolve(market).capabilities


def _capability(
    status: CapabilityStatus,
    provider: str | None = None,
    reason: str | None = None,
    remediation: str | None = None,
) -> CapabilityState:
    return CapabilityState(
        status=status,
        provider=provider,
        reason=reason,
        remediation=remediation,
    )


def _build_default_registry() -> MarketProviderRegistry:
    registry = MarketProviderRegistry()
    quote = EastmoneyQuoteProvider()
    fx = EcbReferenceRateProvider()
    akshare_ready = importlib.util.find_spec("akshare") is not None
    akshare_status: CapabilityStatus = "available" if akshare_ready else "blocked"
    akshare_reason = None if akshare_ready else "未安装固定版本 akshare==1.18.81"
    akshare_remediation = None if akshare_ready else "重新运行 scripts/setup.ps1"
    sec_ready = bool(settings.sec_user_agent and "@" in settings.sec_user_agent)
    sec_status = "available" if sec_ready else "blocked"
    sec_reason = None if sec_ready else "未配置包含联系邮箱的 SEC_USER_AGENT"
    sec_remediation = None if sec_ready else "在 backend/.env 配置 SEC_USER_AGENT"
    registry.register(
        "A_SHARE",
        MarketProviderBundle(
            profile=EastmoneyIssuerProfileProvider(),
            quote=quote,
            financials=EastmoneyFinancialProvider(),
            disclosures=EastmoneyDisclosureProvider(),
            fx=fx,
            capabilities=ProviderCapabilities(
                profile=_capability("available", "eastmoney_company_profile"),
                quote=_capability("available", "eastmoney_quote_snapshot"),
                financials=_capability("available", "eastmoney_f10"),
                disclosures=_capability("available", "eastmoney_announcements"),
                dividend=_capability("available", "eastmoney_bonus_financing"),
                fx=_capability("available", "identity_or_ecb"),
            ),
        ),
    )
    registry.register(
        "US",
        MarketProviderBundle(
            profile=SecIssuerProfileProvider(),
            quote=quote,
            financials=SecFinancialStatementProvider(),
            disclosures=SecDisclosureProvider(),
            fx=fx,
            capabilities=ProviderCapabilities(
                profile=_capability(
                    sec_status,
                    "sec_submissions",
                    reason=sec_reason,
                    remediation=sec_remediation,
                ),
                quote=_capability("available", "eastmoney_quote_snapshot"),
                financials=_capability(
                    sec_status,
                    "sec_companyfacts",
                    reason=sec_reason,
                    remediation=sec_remediation,
                ),
                disclosures=_capability(
                    sec_status,
                    "sec_submissions_archives",
                    reason=sec_reason,
                    remediation=sec_remediation,
                ),
                dividend=_capability(
                    "partial",
                    "sec_companyfacts",
                    reason="仅在 SEC 标准 XBRL 现金分红事实可用时提供",
                ),
                fx=_capability("available", "identity_or_ecb"),
            ),
        ),
    )
    registry.register(
        "HK",
        MarketProviderBundle(
            profile=AkshareHongKongIssuerProfileProvider(),
            quote=quote,
            financials=AkshareHongKongFinancialProvider(),
            disclosures=HkexDisclosureProvider(),
            dividends=AkshareHongKongDividendProvider(),
            fx=fx,
            capabilities=ProviderCapabilities(
                profile=_capability(
                    akshare_status,
                    "akshare_hk_profile",
                    reason=akshare_reason,
                    remediation=akshare_remediation,
                ),
                quote=_capability("available", "eastmoney_quote_snapshot"),
                financials=_capability(
                    akshare_status,
                    "akshare_hk_financials",
                    reason=akshare_reason,
                    remediation=akshare_remediation,
                ),
                disclosures=_capability(
                    "available", "hkexnews_title_search"
                ),
                dividend=_capability(
                    akshare_status,
                    "akshare_hk_dividend",
                    reason=akshare_reason,
                    remediation=akshare_remediation,
                ),
                fx=_capability("available", "identity_or_ecb"),
            ),
        ),
    )
    return registry


default_registry = _build_default_registry()
