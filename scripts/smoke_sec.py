from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
sys.path.insert(0, str(BACKEND_ROOT))

from app.data_sources.announcement_content import AnnouncementContentFetcher  # noqa: E402
from app.data_sources.sec_edgar import (  # noqa: E402
    SecEdgarClient,
    map_sec_companyfacts,
    map_sec_submissions,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="显式访问 SEC EDGAR，检查 submissions/companyfacts/Archives 链路。"
    )
    parser.add_argument("--cik", default="0000320193", help="SEC CIK，默认 Apple。")
    parser.add_argument(
        "--currency",
        default="USD",
        help="报告币种，默认 USD；例如阿里巴巴使用 CNY。",
    )
    parser.add_argument("--limit", type=int, default=8, help="最多映射多少个报告期。")
    parser.add_argument(
        "--fetch-first-document",
        action="store_true",
        help="额外读取第一份支持表单的 Archives HTML 正文。",
    )
    args = parser.parse_args()

    client = SecEdgarClient()
    submissions = client.fetch_submissions(args.cik)
    companyfacts = client.fetch_companyfacts(args.cik)
    statements = map_sec_companyfacts(
        companyfacts,
        cik=args.cik,
        limit=max(args.limit, 1),
        currency=args.currency,
    )
    disclosures = map_sec_submissions(submissions, cik=args.cik, years=2, limit=20)
    result: dict[str, object] = {
        "cik": str(args.cik),
        "issuer_name": submissions.get("name"),
        "fiscal_year_end": submissions.get("fiscalYearEnd"),
        "reporting_currency": args.currency.strip().upper(),
        "statement_count": len(statements),
        "statement_periods": sorted({item.period for item in statements}, reverse=True),
        "statement_types": sorted({item.statement_type for item in statements}),
        "filing_forms": sorted(
            {item.filing_form for item in disclosures if item.filing_form}
        ),
        "disclosure_count": len(disclosures),
    }
    if args.fetch_first_document:
        if not disclosures:
            result["document"] = {"status": "unavailable", "reason": "没有支持的近期表单"}
        else:
            document = disclosures[0]
            content, source_url = AnnouncementContentFetcher(sec_client=client).fetch_text(
                source_url=document.source_url,
                raw_url=document.raw_url,
            )
            result["document"] = {
                "status": "available",
                "form": document.filing_form,
                "source_url": source_url,
                "content_characters": len(content),
                "preview": content[:240],
            }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
