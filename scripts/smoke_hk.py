from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
sys.path.insert(0, str(BACKEND_ROOT))

from app.data_sources.announcement_content import AnnouncementContentFetcher
from app.data_sources.hkex_news import HkexDisclosureProvider
from app.data_sources.hong_kong import (
    AkshareHongKongDividendProvider,
    AkshareHongKongFinancialProvider,
    AkshareHongKongIssuerProfileProvider,
)
from app.market_data.contracts import MarketContext


def main() -> int:
    parser = argparse.ArgumentParser(
        description="显式访问 AKShare/HKEXnews，检查港股档案、财务、分红和披露链路。"
    )
    parser.add_argument("--symbol", default="00700", help="五位港股代码，默认腾讯。")
    parser.add_argument(
        "--hkex-stock-id",
        default="7609",
        help="HKEXnews stockId，默认腾讯 7609。",
    )
    parser.add_argument("--issuer", default="腾讯控股", help="发行人显示名称。")
    parser.add_argument("--currency", default="CNY", help="发行人财务报告币种。")
    parser.add_argument("--limit", type=int, default=8, help="最多映射多少个报告期。")
    parser.add_argument(
        "--fetch-first-document",
        action="store_true",
        help="额外下载第一份 HKEXnews PDF 并提取正文。",
    )
    args = parser.parse_args()

    symbol = "".join(character for character in args.symbol if character.isdigit()).zfill(5)
    context = MarketContext(
        company_id=0,
        canonical_key="hk-smoke",
        issuer_name=args.issuer,
        aliases=(args.issuer,),
        reporting_currency=args.currency.upper(),
        fiscal_year_end="12-31",
        listing_id=0,
        ticker=f"{symbol}.HK",
        symbol=symbol,
        exchange="HKEX",
        market="HK",
        trading_currency="HKD",
        security_type="common_stock",
        provider_identifiers={"hkex_stock_id": str(args.hkex_stock_id)},
    )
    profile = AkshareHongKongIssuerProfileProvider().fetch_profile(context)
    statements = AkshareHongKongFinancialProvider().fetch_financials(
        context, limit=max(args.limit, 1)
    )
    dividends = AkshareHongKongDividendProvider().fetch_dividends(context)
    disclosures = HkexDisclosureProvider().fetch_disclosures(context, years=2, limit=20)
    result: dict[str, object] = {
        "ticker": context.ticker,
        "legal_name": profile.legal_name,
        "domicile_country": profile.domicile_country,
        "reporting_currency": context.reporting_currency,
        "statement_count": len(statements),
        "statement_periods": sorted({item.period for item in statements}, reverse=True),
        "statement_types": sorted({item.statement_type for item in statements}),
        "dividend_count": len(dividends),
        "disclosure_count": len(disclosures),
        "disclosure_languages": sorted(
            {item.language for item in disclosures if item.language}
        ),
        "disclosure_types": sorted({item.document_type for item in disclosures}),
    }
    if args.fetch_first_document:
        if not disclosures:
            result["document"] = {"status": "unavailable", "reason": "没有近期披露"}
        else:
            document = disclosures[0]
            content, source_url = AnnouncementContentFetcher().fetch_text(
                source_url=document.source_url,
                raw_url=document.raw_url,
            )
            result["document"] = {
                "status": "available" if content else "needs_ocr_or_review",
                "source_url": source_url,
                "content_characters": len(content),
                "preview": content[:240],
            }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
