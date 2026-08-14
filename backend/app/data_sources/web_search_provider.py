from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from html.parser import HTMLParser
from urllib.parse import parse_qs, unquote, urlparse

import httpx

from app.data_sources.eastmoney_announcements import (
    AnnouncementDataSourceError,
    EastmoneyAnnouncementClient,
    FetchedAnnouncement,
    UnsupportedAnnouncementSourceError,
)


class WebSearchError(RuntimeError):
    pass


@dataclass(frozen=True)
class SearchResult:
    query: str
    title: str
    url: str
    source: str | None
    snippet: str | None
    published_at: str | None = None

    def to_snapshot(self) -> dict[str, object]:
        return {
            "query": self.query,
            "title": self.title,
            "url": self.url,
            "source": self.source,
            "snippet": self.snippet,
            "published_at": self.published_at,
        }


@dataclass(frozen=True)
class PageSnapshot:
    url: str
    page_title: str | None
    page_description: str | None
    content_excerpt: str | None
    fetched_at: str

    def to_snapshot(self) -> dict[str, object]:
        return {
            "url": self.url,
            "page_title": self.page_title,
            "page_description": self.page_description,
            "content_excerpt": self.content_excerpt,
            "content_fetched_at": self.fetched_at,
        }


class WebSearchProvider:
    def search(self, query: str, limit: int = 5) -> list[SearchResult]:
        raise NotImplementedError


class WebPageSnapshotFetcher:
    def fetch(self, url: str) -> PageSnapshot | None:
        raise NotImplementedError


class HttpWebPageSnapshotFetcher(WebPageSnapshotFetcher):
    def __init__(
        self,
        *,
        timeout: float = 8,
        max_bytes: int = 900_000,
        max_excerpt_chars: int = 1800,
    ) -> None:
        self.timeout = timeout
        self.max_bytes = max_bytes
        self.max_excerpt_chars = max_excerpt_chars

    def fetch(self, url: str) -> PageSnapshot | None:
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"}:
            return None

        try:
            with httpx.Client(timeout=self.timeout, follow_redirects=True) as client:
                response = client.get(url, headers={"User-Agent": _user_agent()})
                response.raise_for_status()
        except httpx.HTTPError:
            return None

        content_type = response.headers.get("content-type", "").lower()
        if content_type and not (
            "text/html" in content_type
            or "application/xhtml+xml" in content_type
            or "text/plain" in content_type
        ):
            return None

        encoding = response.encoding or "utf-8"
        raw_text = response.content[: self.max_bytes].decode(encoding, errors="ignore")
        if "text/plain" in content_type:
            title = None
            description = None
            excerpt = _compact_text(raw_text, max_length=self.max_excerpt_chars)
        else:
            parsed_content = _extract_readable_html(raw_text, max_chars=self.max_excerpt_chars)
            title = parsed_content["title"]
            description = parsed_content["description"]
            excerpt = parsed_content["content_excerpt"]

        if not any([title, description, excerpt]):
            return None

        return PageSnapshot(
            url=str(response.url),
            page_title=title,
            page_description=description,
            content_excerpt=excerpt,
            fetched_at=datetime.now(UTC).isoformat(),
        )


class DuckDuckGoHtmlSearchProvider(WebSearchProvider):
    def __init__(self, *, timeout: float = 15) -> None:
        self.timeout = timeout

    def search(self, query: str, limit: int = 5) -> list[SearchResult]:
        try:
            with httpx.Client(timeout=self.timeout, follow_redirects=True) as client:
                response = client.get(
                    "https://duckduckgo.com/html/",
                    params={"q": query},
                    headers={"User-Agent": _user_agent()},
                )
                response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise WebSearchError(f"搜索接口返回错误：HTTP {exc.response.status_code}") from exc
        except httpx.HTTPError as exc:
            raise WebSearchError(f"搜索请求失败：{exc}") from exc

        parser = _DuckDuckGoHtmlParser(query=query)
        parser.feed(response.text)
        parser.close()
        return parser.results[:limit]


class BingHtmlSearchProvider(WebSearchProvider):
    def __init__(self, *, timeout: float = 15) -> None:
        self.timeout = timeout

    def search(self, query: str, limit: int = 5) -> list[SearchResult]:
        try:
            with httpx.Client(timeout=self.timeout, follow_redirects=True) as client:
                response = client.get(
                    "https://www.bing.com/search",
                    params={"q": query},
                    headers={"User-Agent": _user_agent()},
                )
                response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise WebSearchError(f"Bing 搜索接口返回错误：HTTP {exc.response.status_code}") from exc
        except httpx.HTTPError as exc:
            raise WebSearchError(f"Bing 搜索请求失败：{exc}") from exc

        parser = _BingHtmlParser(query=query)
        parser.feed(response.text)
        parser.close()
        return parser.results[:limit]


class CompositeWebSearchProvider(WebSearchProvider):
    def __init__(self, providers: list[WebSearchProvider] | None = None) -> None:
        self.providers = providers or [
            DuckDuckGoHtmlSearchProvider(),
            BingHtmlSearchProvider(),
        ]
        self.last_provider_stats: list[dict[str, object]] = []

    def search(self, query: str, limit: int = 5) -> list[SearchResult]:
        errors: list[str] = []
        results: list[SearchResult] = []
        seen_keys: set[str] = set()
        self.last_provider_stats = []

        for provider in self.providers:
            provider_name = provider.__class__.__name__
            try:
                provider_results = provider.search(query, limit=limit)
            except WebSearchError as exc:
                errors.append(str(exc))
                self.last_provider_stats.append(
                    {
                        "provider": provider_name,
                        "status": "failed",
                        "result_count": 0,
                        "error": str(exc),
                    }
                )
                continue

            self.last_provider_stats.append(
                {
                    "provider": provider_name,
                    "status": "success",
                    "result_count": len(provider_results),
                }
            )
            for result in provider_results:
                dedupe_key = result.url or result.title
                if dedupe_key in seen_keys:
                    continue
                seen_keys.add(dedupe_key)
                results.append(result)

        if results:
            return results
        if errors:
            raise WebSearchError("；".join(errors))
        return []


class KnownOfficialDisclosureSearchProvider(WebSearchProvider):
    def search(self, query: str, limit: int = 5) -> list[SearchResult]:
        stock_code = _extract_a_share_stock_code(query)
        hk_code = _extract_hk_stock_code(query)
        us_ticker = _extract_us_ticker(query)
        if stock_code is not None:
            return _a_share_official_results(query, stock_code)[:limit]
        if hk_code is not None:
            return _hk_official_results(query, hk_code)[:limit]
        if us_ticker is not None:
            return _us_official_results(query, us_ticker)[:limit]
        return []


def _a_share_official_results(query: str, stock_code: str) -> list[SearchResult]:
    market = "SH" if stock_code.startswith("6") else "SZ"
    secucode = f"{stock_code}.{market}"
    company_hint = _extract_company_hint(query, stock_code)
    display_name = f"{company_hint} {secucode}".strip()
    if market == "SZ":
        disclosure_title = f"{display_name} 深交所上市公司公告检索入口"
        disclosure_url = "https://www.szse.cn/disclosure/listed/notice/index.html"
        disclosure_source = "www.szse.cn"
        disclosure_snippet = (
            "深圳证券交易所上市公司公告检索入口，"
            "用于复核公司公告、定期报告和重大事项披露原文。"
        )
    else:
        disclosure_title = f"{display_name} 上交所上市公司公告检索入口"
        disclosure_url = "https://www.sse.com.cn/disclosure/listedinfo/announcement/"
        disclosure_source = "www.sse.com.cn"
        disclosure_snippet = (
            "上海证券交易所上市公司公告检索入口，"
            "用于复核公司公告、定期报告和重大事项披露原文。"
        )

    return [
        SearchResult(
            query=query,
            title=disclosure_title,
            url=disclosure_url,
            source=disclosure_source,
            snippet=disclosure_snippet,
        ),
        SearchResult(
            query=query,
            title=f"{display_name} 证监会上市公司监管信息检索",
            url="https://www.csrc.gov.cn/",
            source="www.csrc.gov.cn",
            snippet="中国证监会官网入口，可检索监管政策、行政许可、监管措施、处罚和上市公司相关公开信息。",
        ),
        SearchResult(
            query=query,
            title=f"{display_name} 巨潮资讯上市公司公告检索",
            url="https://www.cninfo.com.cn/new/index",
            source="www.cninfo.com.cn",
            snippet="巨潮资讯上市公司公告检索入口，可按证券代码复核年度报告、临时公告和公开披露文件。",
        ),
        SearchResult(
            query=query,
            title=f"{display_name} 国家统计局行业公开数据入口",
            url="https://data.stats.gov.cn/",
            source="data.stats.gov.cn",
            snippet="国家统计局公开数据入口，可复核行业产量、消费、价格、宏观和区域经济数据。",
        ),
    ]


def _hk_official_results(query: str, hk_code: str) -> list[SearchResult]:
    display_code = hk_code.zfill(5)
    company_hint = _extract_company_hint(query, hk_code)
    display_name = f"{company_hint} {display_code}.HK".strip()
    return [
        SearchResult(
            query=query,
            title=f"{display_name} 港交所披露易公告检索",
            url="https://www1.hkexnews.hk/search/titlesearch.xhtml",
            source="www1.hkexnews.hk",
            snippet="港交所披露易公告检索入口，可按股份代号复核公告、年报、中期报告和监管披露。",
        ),
        SearchResult(
            query=query,
            title=f"{display_name} 香港证监会监管公开信息入口",
            url="https://www.sfc.hk/",
            source="www.sfc.hk",
            snippet="香港证监会官网入口，可检索监管政策、处罚、市场纪律和公开披露资料。",
        ),
    ]


def _us_official_results(query: str, ticker: str) -> list[SearchResult]:
    return [
        SearchResult(
            query=query,
            title=f"{ticker} SEC EDGAR company filings",
            url=f"https://www.sec.gov/edgar/search/#/q={ticker}",
            source="www.sec.gov",
            snippet=(
                "SEC EDGAR 公司披露检索入口，可复核 10-K、10-Q、8-K、"
                "proxy statement 等公开披露文件。"
            ),
        ),
        SearchResult(
            query=query,
            title=f"{ticker} US macro and industry public data",
            url="https://www.bea.gov/data",
            source="www.bea.gov",
            snippet="美国经济分析局公开数据入口，可复核宏观、行业和消费相关公开数据。",
        ),
    ]


def _announcement_to_search_result(
    query: str, announcement: FetchedAnnouncement
) -> SearchResult:
    published_at = announcement.published_at.isoformat()
    snippet = (
        f"{announcement.category}，发布时间 {published_at}。"
        f"公司公开披露文件：{announcement.title}。"
    )
    return SearchResult(
        query=query,
        title=announcement.title,
        url=announcement.source_url,
        source=announcement.source,
        snippet=snippet,
        published_at=published_at,
    )


def _is_substantive_disclosure_title(title: str) -> bool:
    normalized = title.lower()
    blocked_patterns = (
        "股票交易异常波动",
        "交易异常波动",
        "回购股份价格上限",
        "回购价格上限",
        "会议决议公告",
        "行情",
    )
    if any(pattern in normalized for pattern in blocked_patterns):
        return False

    substantive_patterns = (
        "年度报告",
        "年报",
        "半年度报告",
        "季度报告",
        "定期报告",
        "问询函",
        "监管函",
        "关注函",
        "处罚",
        "行政监管",
        "信息披露",
        "业绩预告",
        "业绩快报",
        "利润分配",
        "分红",
        "审计",
        "会计",
        "减值",
        "诉讼",
        "仲裁",
        "担保",
        "关联交易",
        "重大",
        "收购",
        "出售",
        "投资",
        "合同",
        "经营",
        "董事会秘书",
        "高管",
        "管理层",
        "变更",
        "产能",
        "环保",
        "安全",
        "整改",
    )
    return any(pattern in normalized for pattern in substantive_patterns)


def _disclosure_query_title_terms(query: str) -> tuple[str, ...]:
    normalized = query.lower()
    terms: list[str] = []
    if any(pattern in normalized for pattern in ("年报", "年度报告", "定期报告", "annual")):
        terms.extend(("年度报告", "年报", "半年度报告", "季度报告", "定期报告"))
    if any(pattern in normalized for pattern in ("监管函", "问询函", "处罚", "监管")):
        terms.extend(("监管函", "问询函", "关注函", "处罚", "行政监管", "整改"))
    if any(pattern in normalized for pattern in ("业绩", "经营", "收入", "利润")):
        terms.extend(("业绩预告", "业绩快报", "年度报告", "半年度报告", "经营"))
    if any(pattern in normalized for pattern in ("分红", "利润分配", "回购")):
        terms.extend(("利润分配", "分红", "回购"))
    if any(pattern in normalized for pattern in ("审计", "会计", "重述")):
        terms.extend(("审计", "会计", "重述", "更正"))

    unique_terms: list[str] = []
    for term in terms:
        if term not in unique_terms:
            unique_terms.append(term)
    return tuple(unique_terms)


def _title_matches_terms(title: str, terms: tuple[str, ...]) -> bool:
    normalized = title.lower()
    return any(term.lower() in normalized for term in terms)


class KnownPublicPageSearchProvider(KnownOfficialDisclosureSearchProvider):
    pass


class AShareCompanyDisclosureSearchProvider(WebSearchProvider):
    def __init__(
        self,
        *,
        client: EastmoneyAnnouncementClient | None = None,
        years: int = 1,
        page_size: int = 40,
    ) -> None:
        self.client = client or EastmoneyAnnouncementClient(timeout=10)
        self.years = years
        self.page_size = page_size
        self._cache: dict[str, list[FetchedAnnouncement]] = {}

    def search(self, query: str, limit: int = 5) -> list[SearchResult]:
        stock_code = _extract_a_share_stock_code(query)
        if stock_code is None:
            return []

        try:
            announcements = self._fetch_announcements(stock_code)
        except UnsupportedAnnouncementSourceError:
            return []
        except AnnouncementDataSourceError as exc:
            raise WebSearchError(f"A 股公司公开披露读取失败：{exc}") from exc

        preferred_title_terms = _disclosure_query_title_terms(query)
        preferred_results: list[SearchResult] = []
        secondary_results: list[SearchResult] = []
        for announcement in announcements:
            if not _is_substantive_disclosure_title(announcement.title):
                continue
            result = _announcement_to_search_result(query, announcement)
            if preferred_title_terms and _title_matches_terms(
                announcement.title, preferred_title_terms
            ):
                preferred_results.append(result)
            else:
                secondary_results.append(result)

        return [*preferred_results, *secondary_results][:limit]

    def _fetch_announcements(self, stock_code: str) -> list[FetchedAnnouncement]:
        if stock_code not in self._cache:
            self._cache[stock_code] = self.client.fetch_announcements(
                ticker=stock_code,
                years=self.years,
                page_size=self.page_size,
                limit=50,
            )
        return self._cache[stock_code]


def _extract_hk_stock_code(query: str) -> str | None:
    match = re.search(r"\b(0?\d{4,5})(?:\.HK|\.HKG)?\b", query.upper())
    if match is None:
        return None
    code = match.group(1).lstrip("0")
    return code if code else None


def _extract_us_ticker(query: str) -> str | None:
    match = re.search(r"\b([A-Z]{1,5}(?:\.[A-Z])?)\.US\b", query.upper())
    if match:
        return match.group(1)
    return None


class _DuckDuckGoHtmlParser(HTMLParser):
    def __init__(self, *, query: str) -> None:
        super().__init__()
        self.query = query
        self.results: list[SearchResult] = []
        self._current_url: str | None = None
        self._current_title_parts: list[str] = []
        self._current_snippet_parts: list[str] = []
        self._in_title = False
        self._in_snippet = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = {key: value or "" for key, value in attrs}
        class_name = attr_map.get("class", "")

        if tag == "a" and "result__a" in class_name:
            self._flush_current()
            self._current_url = _normalize_result_url(attr_map.get("href", ""))
            self._current_title_parts = []
            self._current_snippet_parts = []
            self._in_title = True
            return

        if "result__snippet" in class_name:
            self._in_snippet = True

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._in_title:
            self._in_title = False
        if tag in {"a", "div"} and self._in_snippet:
            self._in_snippet = False

    def handle_data(self, data: str) -> None:
        text = " ".join(data.split())
        if not text:
            return
        if self._in_title:
            self._current_title_parts.append(text)
        elif self._in_snippet:
            self._current_snippet_parts.append(text)

    def close(self) -> None:
        self._flush_current()
        super().close()

    def _flush_current(self) -> None:
        title = " ".join(self._current_title_parts).strip()
        url = self._current_url
        if title and url:
            snippet = " ".join(self._current_snippet_parts).strip() or None
            self.results.append(
                SearchResult(
                    query=self.query,
                    title=title,
                    url=url,
                    source=_extract_domain(url),
                    snippet=snippet,
                )
            )

        self._current_url = None
        self._current_title_parts = []
        self._current_snippet_parts = []
        self._in_title = False
        self._in_snippet = False


class _BingHtmlParser(HTMLParser):
    def __init__(self, *, query: str) -> None:
        super().__init__()
        self.query = query
        self.results: list[SearchResult] = []
        self._in_result = False
        self._in_title = False
        self._in_snippet = False
        self._current_url: str | None = None
        self._current_title_parts: list[str] = []
        self._current_snippet_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = {key: value or "" for key, value in attrs}
        class_name = attr_map.get("class", "")

        if tag == "li" and "b_algo" in class_name:
            self._flush_current()
            self._in_result = True
            return

        if self._in_result and tag == "a" and not self._current_url:
            href = attr_map.get("href", "")
            if href.startswith("http"):
                self._current_url = href
                self._in_title = True
            return

        if self._in_result and tag == "p":
            self._in_snippet = True

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._in_title:
            self._in_title = False
        if tag == "p" and self._in_snippet:
            self._in_snippet = False
        if tag == "li" and self._in_result:
            self._flush_current()
            self._in_result = False

    def handle_data(self, data: str) -> None:
        text = " ".join(data.split())
        if not text:
            return
        if self._in_title:
            self._current_title_parts.append(text)
        elif self._in_snippet:
            self._current_snippet_parts.append(text)

    def close(self) -> None:
        self._flush_current()
        super().close()

    def _flush_current(self) -> None:
        title = " ".join(self._current_title_parts).strip()
        url = self._current_url
        if title and url:
            snippet = " ".join(self._current_snippet_parts).strip() or None
            self.results.append(
                SearchResult(
                    query=self.query,
                    title=title,
                    url=url,
                    source=_extract_domain(url),
                    snippet=snippet,
                )
            )

        self._current_url = None
        self._current_title_parts = []
        self._current_snippet_parts = []
        self._in_title = False
        self._in_snippet = False


class _ReadableHtmlParser(HTMLParser):
    SKIP_TAGS = {"script", "style", "noscript", "svg", "canvas", "nav", "footer"}

    def __init__(self, *, max_chars: int) -> None:
        super().__init__()
        self.max_chars = max_chars
        self.title: str | None = None
        self.description: str | None = None
        self._title_parts: list[str] = []
        self._content_parts: list[str] = []
        self._in_title = False
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in self.SKIP_TAGS:
            self._skip_depth += 1
            return
        if tag == "title":
            self._in_title = True
            return
        if tag != "meta":
            return

        attr_map = {key.lower(): value or "" for key, value in attrs}
        name = attr_map.get("name", "").lower()
        property_name = attr_map.get("property", "").lower()
        if name == "description" or property_name == "og:description":
            description = _compact_text(attr_map.get("content", ""), max_length=320)
            if description and not self.description:
                self.description = description

    def handle_endtag(self, tag: str) -> None:
        if tag in self.SKIP_TAGS and self._skip_depth > 0:
            self._skip_depth -= 1
            return
        if tag == "title":
            self._in_title = False
            title = _compact_text(" ".join(self._title_parts), max_length=240)
            if title and not self.title:
                self.title = title

    def handle_data(self, data: str) -> None:
        text = " ".join(data.split())
        if not text:
            return
        if self._in_title:
            self._title_parts.append(text)
            return
        if self._skip_depth > 0:
            return
        if len(text) < 12:
            return
        current_length = sum(len(part) for part in self._content_parts)
        if current_length >= self.max_chars:
            return
        self._content_parts.append(text)

    @property
    def content_excerpt(self) -> str | None:
        return _compact_text(" ".join(self._content_parts), max_length=self.max_chars)


def _normalize_result_url(raw_url: str) -> str:
    if not raw_url:
        return raw_url

    parsed = urlparse(raw_url)
    if "duckduckgo.com" in parsed.netloc and parsed.path.startswith("/l/"):
        query = parse_qs(parsed.query)
        uddg = query.get("uddg", [])
        if uddg:
            return unquote(uddg[0])

    return raw_url


def _extract_domain(url: str) -> str | None:
    hostname = urlparse(url).hostname
    return hostname.lower() if hostname else None


def _extract_a_share_stock_code(query: str) -> str | None:
    match = re.search(r"\b([036]\d{5})(?:\.(?:SH|SZ|SS))?\b", query.upper())
    return match.group(1) if match else None


def _eastmoney_market_prefix(stock_code: str) -> str:
    return "sh" if stock_code.startswith("6") else "sz"


def _extract_company_hint(query: str, stock_code: str) -> str:
    before_code = query.split(stock_code, 1)[0].strip()
    if not before_code:
        return ""
    return before_code.split()[-1]


def _user_agent() -> str:
    return (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36"
    )


def _extract_readable_html(raw_html: str, *, max_chars: int) -> dict[str, str | None]:
    parser = _ReadableHtmlParser(max_chars=max_chars)
    parser.feed(raw_html)
    parser.close()
    return {
        "title": parser.title,
        "description": parser.description,
        "content_excerpt": parser.content_excerpt,
    }


def _compact_text(value: str, *, max_length: int) -> str | None:
    text = " ".join(value.split())
    if not text:
        return None
    if len(text) <= max_length:
        return text
    return f"{text[:max_length]}..."
