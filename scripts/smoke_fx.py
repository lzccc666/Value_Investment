from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
sys.path.insert(0, str(BACKEND_ROOT))

from app.data_sources.ecb_fx import EcbReferenceRateProvider


def main() -> int:
    parser = argparse.ArgumentParser(
        description="显式访问 ECB Data API，检查日参考率和交叉汇率计算。"
    )
    parser.add_argument("--base", default="CNY", help="基础币种，默认 CNY。")
    parser.add_argument("--quote", default="HKD", help="报价币种，默认 HKD。")
    parser.add_argument("--date", type=date.fromisoformat, help="可选 YYYY-MM-DD 截止日。")
    args = parser.parse_args()

    fetched = EcbReferenceRateProvider().fetch_rate(
        args.base,
        args.quote,
        rate_date=args.date,
    )
    print(
        json.dumps(
            {
                "base_currency": fetched.base_currency,
                "quote_currency": fetched.quote_currency,
                "rate": fetched.rate,
                "rate_date": fetched.rate_date.isoformat(),
                "source": fetched.source,
                "source_url": fetched.source_url,
                "calculation_audit": fetched.calculation_audit,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
