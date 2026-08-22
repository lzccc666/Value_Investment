from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import httpx


class EastmoneySecurityCatalogError(RuntimeError):
    """Raised when the Eastmoney security directory cannot return usable data."""


@dataclass(frozen=True)
class FetchedSecurityCatalogItem:
    quote_id: str
    company_name: str
    symbol: str
    ticker: str
    exchange: Literal["SSE", "SZSE", "BSE", "HKEX", "NASDAQ", "NYSE"]
    market: Literal["A_SHARE", "HK", "US"]
    trading_currency: Literal["CNY", "HKD", "USD"]
    security_type: Literal["common_stock", "ads"]
    pinyin: str | None = None


class EastmoneySecurityCatalogClient:
    api_url = "https://searchapi.eastmoney.com/api/suggest/get"
    source_name = "Eastmoney security suggest directory"

    def __init__(self, timeout: float = 12.0) -> None:
        self._timeout = timeout

    def search(
        self,
        query: str,
        *,
        limit: int = 20,
    ) -> list[FetchedSecurityCatalogItem]:
        try:
            response = httpx.get(
                self.api_url,
                params={"input": query.strip(), "type": "14", "count": str(limit)},
                timeout=self._timeout,
                headers={
                    "User-Agent": "Mozilla/5.0",
                    "Referer": "https://quote.eastmoney.com/",
                },
            )
            response.raise_for_status()
            payload = response.json()
        except httpx.HTTPError as exc:
            raise EastmoneySecurityCatalogError(
                f"东方财富证券目录请求失败：{exc}"
            ) from exc
        except ValueError as exc:
            raise EastmoneySecurityCatalogError(
                "东方财富证券目录返回非 JSON 数据。"
            ) from exc
        return parse_security_catalog_payload(payload)

    def find_us_listing(
        self,
        symbol: str,
        exchange: str,
    ) -> FetchedSecurityCatalogItem | None:
        normalized_symbol = _normalize_us_symbol(symbol)
        normalized_exchange = exchange.strip().upper()
        return next(
            (
                item
                for item in self.search(symbol, limit=50)
                if item.market == "US"
                and _normalize_us_symbol(item.symbol) == normalized_symbol
                and item.exchange == normalized_exchange
            ),
            None,
        )


def parse_security_catalog_payload(payload: object) -> list[FetchedSecurityCatalogItem]:
    if not isinstance(payload, dict):
        raise EastmoneySecurityCatalogError("东方财富证券目录数据结构异常。")
    table = payload.get("QuotationCodeTable")
    rows = table.get("Data") if isinstance(table, dict) else None
    if rows is None:
        return []
    if not isinstance(rows, list):
        raise EastmoneySecurityCatalogError("东方财富证券目录候选列表结构异常。")

    items: list[FetchedSecurityCatalogItem] = []
    seen: set[str] = set()
    for row in rows:
        item = _parse_security_catalog_row(row)
        if item is None or item.quote_id in seen:
            continue
        seen.add(item.quote_id)
        items.append(item)
    return items


def _parse_security_catalog_row(row: object) -> FetchedSecurityCatalogItem | None:
    if not isinstance(row, dict):
        return None
    code = str(row.get("Code") or "").strip().upper()
    name = str(row.get("Name") or "").strip()
    quote_id = str(row.get("QuoteID") or "").strip()
    classify = str(row.get("Classify") or "").strip()
    exchange_code = str(row.get("JYS") or "").strip().upper()
    security_type_name = str(row.get("SecurityTypeName") or "").strip()
    security_type_code = str(row.get("SecurityType") or "").strip()
    type_us = str(row.get("TypeUS") or "").strip()
    pinyin = str(row.get("PinYin") or "").strip().upper() or None
    if not code or not name or not quote_id:
        return None

    a_share = {
        ("沪A", "1"): ("SSE", "SH"),
        ("深A", "2"): ("SZSE", "SZ"),
        ("京A", "27"): ("BSE", "BJ"),
    }.get((security_type_name, security_type_code))
    if a_share is not None:
        exchange, suffix = a_share
        return FetchedSecurityCatalogItem(
            quote_id=quote_id,
            company_name=name,
            symbol=code,
            ticker=f"{code}.{suffix}",
            exchange=exchange,
            market="A_SHARE",
            trading_currency="CNY",
            security_type="common_stock",
            pinyin=pinyin,
        )

    # TypeUS=3 is Eastmoney's ordinary-equity class for HK listings. Codes
    # beginning with 8 are RMB counters, whose currency cannot be inferred here.
    if classify == "HK" and exchange_code == "HK" and type_us == "3" and not code.startswith("8"):
        return FetchedSecurityCatalogItem(
            quote_id=quote_id,
            company_name=name,
            symbol=code,
            ticker=f"{code}.HK",
            exchange="HKEX",
            market="HK",
            trading_currency="HKD",
            security_type="common_stock",
            pinyin=pinyin,
        )

    us_exchange = {"NASDAQ": "NASDAQ", "NYSE": "NYSE"}.get(exchange_code)
    us_security_type = {"1": "common_stock", "10": "common_stock", "3": "ads"}.get(type_us)
    if classify == "UsStock" and us_exchange and us_security_type:
        return FetchedSecurityCatalogItem(
            quote_id=quote_id,
            company_name=name,
            symbol=code,
            ticker=f"{code}.US",
            exchange=us_exchange,
            market="US",
            trading_currency="USD",
            security_type=us_security_type,
            pinyin=pinyin,
        )
    return None


def _normalize_us_symbol(value: str) -> str:
    return value.strip().upper().replace(".", "_").replace("-", "_")
