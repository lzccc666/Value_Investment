from __future__ import annotations

import hashlib
import re
import time
from datetime import UTC, date, datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlencode, urljoin

import httpx

from app.core.config import settings
from app.data_sources.eastmoney_announcements import FetchedAnnouncement
from app.market_data.contracts import (
    MarketContext,
    MarketDataParseError,
    MarketDataRateLimitedError,
    MarketDataUpstreamError,
    MarketDataValidationError,
)

HKEX_NEWS_BASE_URL = "https://www1.hkexnews.hk"
HKEX_TITLE_SEARCH_URL = f"{HKEX_NEWS_BASE_URL}/search/titlesearch.xhtml"
HONG_KONG_TZ = timezone(timedelta(hours=8), "Asia/Hong_Kong")


class HkexNewsClient:
    def __init__(
        self,
        *,
        timeout: float | None = None,
        cache_directory: Path | None = None,
        cache_ttl_seconds: int | None = None,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.timeout = timeout or settings.provider_timeout_seconds
        self.cache_directory = cache_directory or settings.provider_cache_directory / "hkex"
        self.cache_ttl_seconds = (
            settings.hkex_cache_ttl_seconds
            if cache_ttl_seconds is None
            else max(cache_ttl_seconds, 0)
        )
        self.client = httpx.Client(
            timeout=self.timeout,
            transport=transport,
            follow_redirects=True,
            headers={
                "User-Agent": "ValueInvestmentResearch/1.0 HKEXnews reader",
                "Accept": "text/html,application/xhtml+xml",
            },
        )

    def search(self, *, stock_id: str, language: str) -> str:
        normalized_language = language.upper()
        if normalized_language not in {"EN", "ZH"}:
            raise MarketDataValidationError(f"不支持的 HKEXnews 语言：{language}")
        today = date.today()
        query = {
            "category": "0",
            "lang": normalized_language,
            "market": "SEHK",
            "searchType": "0",
            "stockId": stock_id,
            "from": f"{today.year - 2}0101",
            "to": today.strftime("%Y%m%d"),
        }
        url = f"{HKEX_TITLE_SEARCH_URL}?{urlencode(query)}"
        cache_path = self._cache_path(url)
        cached = self._read_cache(cache_path)
        if cached is not None:
            return cached
        errors: list[str] = []
        for attempt in range(3):
            try:
                response = self.client.get(url)
            except httpx.HTTPError as exc:
                errors.append(str(exc))
                if attempt < 2:
                    time.sleep(0.25 * (2**attempt))
                    continue
                raise MarketDataUpstreamError(f"HKEXnews 请求失败：{exc}") from exc
            if response.status_code == 429:
                errors.append("HTTP 429")
                if attempt < 2:
                    time.sleep(0.5 * (2**attempt))
                    continue
                raise MarketDataRateLimitedError("HKEXnews 返回 429，请稍后重试。")
            if response.status_code >= 500 and attempt < 2:
                errors.append(f"HTTP {response.status_code}")
                time.sleep(0.25 * (2**attempt))
                continue
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                raise MarketDataUpstreamError(
                    f"HKEXnews 请求失败：HTTP {response.status_code}"
                ) from exc
            content = response.text
            self._write_cache(cache_path, content)
            return content
        raise MarketDataUpstreamError("HKEXnews 请求失败：" + "；".join(errors))

    def _cache_path(self, url: str) -> Path:
        digest = hashlib.sha256(url.encode("utf-8")).hexdigest()
        return self.cache_directory / f"{digest}.html"

    def _read_cache(self, path: Path) -> str | None:
        if self.cache_ttl_seconds <= 0 or not path.exists():
            return None
        if time.time() - path.stat().st_mtime > self.cache_ttl_seconds:
            return None
        try:
            return path.read_text(encoding="utf-8")
        except OSError:
            return None

    def _write_cache(self, path: Path, content: str) -> None:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_suffix(".tmp")
            temporary.write_text(content, encoding="utf-8")
            temporary.replace(path)
        except OSError:
            return


class HkexDisclosureProvider:
    provider_name = "hkexnews_title_search"

    def __init__(self, client: HkexNewsClient | None = None) -> None:
        self.client = client

    def fetch_disclosures(
        self, context: MarketContext, *, years: int, limit: int
    ) -> list[FetchedAnnouncement]:
        if context.market != "HK" or context.exchange != "HKEX":
            raise MarketDataValidationError("HKEXnews Provider 只接受 HKEX Listing。")
        stock_id = context.provider_identifiers.get("hkex_stock_id")
        if not stock_id:
            raise MarketDataValidationError("港股 Listing 缺少 hkex_stock_id provider identifier。")
        client = self.client or HkexNewsClient()
        announcements: list[FetchedAnnouncement] = []
        for language in ("ZH", "EN"):
            html = client.search(stock_id=str(stock_id), language=language)
            announcements.extend(
                parse_hkex_title_search_html(
                    html,
                    language="zh-HK" if language == "ZH" else "en-GB",
                )
            )
        cutoff = _subtract_years(date.today(), max(years, 1))
        selected: dict[str, FetchedAnnouncement] = {}
        for item in sorted(announcements, key=lambda value: value.published_at, reverse=True):
            if item.published_at.date() < cutoff:
                continue
            document_id = item.source_document_id or item.source_url
            if document_id not in selected:
                selected[document_id] = item
            if len(selected) >= max(limit, 1):
                break
        return list(selected.values())


def parse_hkex_title_search_html(
    html: str, *, language: str
) -> list[FetchedAnnouncement]:
    parser = _HkexResultTableParser()
    try:
        parser.feed(html)
    except Exception as exc:
        raise MarketDataParseError(f"HKEXnews HTML 解析失败：{exc}") from exc
    results: list[FetchedAnnouncement] = []
    for row in parser.rows:
        href = row.get("href")
        text = row.get("text")
        title = row.get("title")
        if not href or not text or not title:
            continue
        published_at = _published_at(text)
        if published_at is None:
            continue
        source_url = urljoin(HKEX_NEWS_BASE_URL, href)
        document_id = _document_id(source_url)
        results.append(
            FetchedAnnouncement(
                title=title,
                published_at=published_at,
                category=_document_type(text, title),
                source="hkexnews",
                source_url=source_url,
                raw_url=source_url,
                source_document_id=document_id,
                document_type=_document_type(text, title),
                filing_form=None,
                language=language,
                period_end=_period_end(title),
                content_type=(
                    "application/pdf"
                    if source_url.lower().endswith(".pdf")
                    else "text/html"
                ),
            )
        )
    return results


class _HkexResultTableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.rows: list[dict[str, str]] = []
        self._in_row = False
        self._row_text: list[str] = []
        self._href: str | None = None
        self._anchor_text: list[str] = []
        self._in_anchor = False

    def handle_starttag(self, tag: str, attrs) -> None:
        lower_tag = tag.lower()
        if lower_tag == "tr":
            self._in_row = True
            self._row_text = []
            self._href = None
            self._anchor_text = []
        if not self._in_row or lower_tag != "a":
            return
        attributes = {name.lower(): value or "" for name, value in attrs}
        href = attributes.get("href")
        if href and ("listconews" in href.lower() or href.lower().endswith(".pdf")):
            self._href = href
            self._in_anchor = True

    def handle_endtag(self, tag: str) -> None:
        lower_tag = tag.lower()
        if lower_tag == "a":
            self._in_anchor = False
        if lower_tag == "tr" and self._in_row:
            text = " ".join(self._row_text)
            title = " ".join(self._anchor_text).strip()
            if self._href and title:
                self.rows.append({"href": self._href, "text": text, "title": title})
            self._in_row = False

    def handle_data(self, data: str) -> None:
        if not self._in_row:
            return
        normalized = " ".join(data.split())
        if not normalized:
            return
        self._row_text.append(normalized)
        if self._in_anchor:
            self._anchor_text.append(normalized)


def _published_at(text: str) -> datetime | None:
    match = re.search(r"(\d{2}/\d{2}/\d{4})\s+(\d{2}:\d{2})", text)
    if not match:
        return None
    try:
        local_time = datetime.strptime(
            f"{match.group(1)} {match.group(2)}", "%d/%m/%Y %H:%M"
        ).replace(tzinfo=HONG_KONG_TZ)
    except ValueError:
        return None
    return local_time.astimezone(UTC)


def _document_id(url: str) -> str:
    filename = url.rsplit("/", 1)[-1].split("?", 1)[0]
    stem = filename.rsplit(".", 1)[0]
    return stem.removesuffix("_c")


def _document_type(row_text: str, title: str) -> str:
    normalized = f"{row_text} {title}".lower()
    for markers, document_type in (
        (("annual results", "annual report", "全年业绩", "年度报告", "年度業績"), "annual_report"),
        (
            ("interim results", "interim report", "中期业绩", "中期報告", "中期業績"),
            "interim_report",
        ),
        (("quarterly results", "季度业绩", "季度業績"), "quarterly_report"),
        (("profit warning", "盈利警告", "盈警"), "profit_warning"),
        (("dividend", "股息", "分红", "分紅"), "dividend"),
        (("next day disclosure", "翌日披露"), "share_capital_change"),
        (("monthly return", "月报表", "月報表"), "monthly_return"),
        (("circular", "通函"), "circular"),
        (("governance", "董事", "委员会", "委員會"), "governance"),
    ):
        if any(marker in normalized for marker in markers):
            return document_type
    return "material_event"


def _period_end(title: str) -> date | None:
    english = re.search(
        r"ended\s+(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})",
        title,
        flags=re.IGNORECASE,
    )
    if english:
        try:
            return datetime.strptime(
                f"{english.group(1)} {english.group(2)} {english.group(3)}", "%d %B %Y"
            ).date()
        except ValueError:
            pass
    chinese = re.search(r"截至?(\d{4})年(\d{1,2})月(\d{1,2})日", title)
    if chinese:
        try:
            return date(int(chinese.group(1)), int(chinese.group(2)), int(chinese.group(3)))
        except ValueError:
            return None
    return None


def _subtract_years(value: date, years: int) -> date:
    try:
        return value.replace(year=value.year - years)
    except ValueError:
        return value.replace(year=value.year - years, month=2, day=28)
