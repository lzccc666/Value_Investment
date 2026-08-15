from __future__ import annotations

import re
from datetime import UTC, datetime
from html.parser import HTMLParser
from io import BytesIO

import httpx


class AnnouncementContentFetchError(RuntimeError):
    pass


_EASTMONEY_ART_CODE_RE = re.compile(r"\b(AN\d+)\b", re.IGNORECASE)
_EASTMONEY_NOTICE_API = "https://np-cnotice-stock.eastmoney.com/api/content/ann"
EASTMONEY_PAGE_SHELL_MARKERS = (
    "公告正文 _ 数据中心 _ 东方财富网",
    "数据中心 全球财经快讯 行情中心 Choice数据",
    "东方财富网研报中心提供沪深两市最全面的上市公司公告信息",
)
_NOTICE_BODY_MARKERS = (
    "证券代码",
    "公告编号",
    "本公司及董事会",
    "重要内容提示",
    "特此公告",
)


class AnnouncementContentFetcher:
    def __init__(self, timeout: float = 20.0, max_bytes: int = 8_000_000) -> None:
        self._timeout = timeout
        self._max_bytes = max_bytes

    def fetch_text(self, *, source_url: str | None, raw_url: str | None) -> tuple[str, str]:
        urls = [url for url in (raw_url, source_url) if url]
        if not urls:
            raise AnnouncementContentFetchError("公告缺少 source_url/raw_url，无法读取原文")

        errors: list[str] = []

        art_code = _extract_eastmoney_art_code(*urls)
        if art_code:
            try:
                content = self._fetch_eastmoney_notice_text(art_code)
            except AnnouncementContentFetchError as exc:
                errors.append(str(exc))
            else:
                if content.strip():
                    return content, _preferred_trace_url(source_url, raw_url) or urls[0]

        for url in urls:
            try:
                content = self._fetch_one(url)
            except AnnouncementContentFetchError as exc:
                errors.append(str(exc))
                continue
            if content.strip():
                return content, url

        joined = "；".join(errors) if errors else "未能读取到公告正文"
        raise AnnouncementContentFetchError(joined)

    def _fetch_eastmoney_notice_text(self, art_code: str) -> str:
        pages: list[str] = []
        page_count = 1

        for page_index in range(1, self._max_notice_pages() + 1):
            payload = self._fetch_eastmoney_notice_page(art_code, page_index)
            if page_index == 1:
                page_count = _positive_int_or_none(payload.get("page_size")) or 1

            page_content = _normalize_text(_string_or_empty(payload.get("notice_content")))
            if page_content and (not pages or page_content != pages[-1]):
                pages.append(page_content)

            if page_index >= page_count:
                break

        if not pages:
            raise AnnouncementContentFetchError("东方财富公告正文接口未返回可用正文")

        return "\n".join(pages)

    def _fetch_eastmoney_notice_page(self, art_code: str, page_index: int) -> dict[str, object]:
        try:
            response = httpx.get(
                _EASTMONEY_NOTICE_API,
                params={
                    "art_code": art_code,
                    "client_source": "web",
                    "page_index": page_index,
                },
                timeout=self._timeout,
                follow_redirects=True,
                headers={
                    "user-agent": "Mozilla/5.0",
                    "referer": f"https://data.eastmoney.com/notices/detail/{art_code}.html",
                },
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise AnnouncementContentFetchError(f"东方财富公告正文接口请求失败：{exc}") from exc

        try:
            payload = response.json()
        except ValueError as exc:
            raise AnnouncementContentFetchError("东方财富公告正文接口返回非 JSON 内容") from exc

        if payload.get("success") not in (1, True):
            message = payload.get("message") or payload.get("error") or "未返回有效正文"
            raise AnnouncementContentFetchError(f"东方财富公告正文接口返回失败：{message}")

        data = payload.get("data")
        if not isinstance(data, dict):
            raise AnnouncementContentFetchError("东方财富公告正文接口返回结构异常")

        return data

    def _max_notice_pages(self) -> int:
        # 留出余量，避免无意间拉过多分页。
        return max(1, min(80, self._max_bytes // 100_000))

    def _fetch_one(self, url: str) -> str:
        try:
            response = httpx.get(url, timeout=self._timeout, follow_redirects=True)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise AnnouncementContentFetchError(f"公告原文请求失败：{exc}") from exc

        content = response.content[: self._max_bytes]
        content_type = response.headers.get("content-type", "").lower()
        if "pdf" in content_type or url.lower().endswith(".pdf"):
            return _extract_pdf_text(content)

        response.encoding = response.encoding or "utf-8"
        return _extract_html_text(response.text)


def _extract_pdf_text(content: bytes) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise AnnouncementContentFetchError("当前环境未安装 pypdf，无法解析 PDF 公告原文") from exc

    try:
        reader = PdfReader(BytesIO(content))
        text_parts = [page.extract_text() or "" for page in reader.pages[:80]]
    except Exception as exc:
        raise AnnouncementContentFetchError(f"PDF 公告原文解析失败：{exc}") from exc

    return _normalize_text("\n".join(text_parts))


def _extract_html_text(content: str) -> str:
    targeted_parser = _TargetedHTMLTextParser(target_ids={"notice_content"})
    targeted_parser.feed(content)
    if targeted_parser.target_found:
        return _normalize_text(" ".join(targeted_parser.text_parts))

    parser = _ReadableHTMLParser()
    parser.feed(content)
    return _normalize_text(" ".join(parser.text_parts))


def _normalize_text(value: str) -> str:
    lines = [" ".join(line.split()) for line in value.splitlines()]
    return "\n".join(line for line in lines if line)


def looks_like_eastmoney_page_shell(value: str | None) -> bool:
    normalized = _normalize_text(value or "")
    if not normalized:
        return False

    compact_text = " ".join(normalized.split())
    if not any(marker in compact_text for marker in EASTMONEY_PAGE_SHELL_MARKERS):
        return False

    return not any(marker in compact_text for marker in _NOTICE_BODY_MARKERS)


class _ReadableHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.text_parts: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag.lower() in {"script", "style", "noscript"}:
            self._skip_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in {"script", "style", "noscript"} and self._skip_depth > 0:
            self._skip_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        normalized = " ".join(data.split())
        if normalized:
            self.text_parts.append(normalized)


class _TargetedHTMLTextParser(HTMLParser):
    def __init__(self, *, target_ids: set[str]) -> None:
        super().__init__()
        self.text_parts: list[str] = []
        self._skip_depth = 0
        self._capture_depth = 0
        self.target_found = False
        self._target_ids = {
            target_id.strip().lower() for target_id in target_ids if target_id.strip()
        }

    def handle_starttag(self, tag: str, attrs) -> None:
        lower_tag = tag.lower()
        attrs_map = {name.lower(): (value or "") for name, value in attrs}
        if lower_tag in {"script", "style", "noscript"}:
            self._skip_depth += 1
            return

        if attrs_map.get("id", "").lower() in self._target_ids:
            self.target_found = True
            self._capture_depth = 1
            return

        if self._capture_depth > 0:
            self._capture_depth += 1

    def handle_endtag(self, tag: str) -> None:
        lower_tag = tag.lower()
        if lower_tag in {"script", "style", "noscript"} and self._skip_depth > 0:
            self._skip_depth -= 1
            return

        if self._capture_depth > 0:
            self._capture_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._skip_depth or self._capture_depth <= 0:
            return
        normalized = " ".join(data.split())
        if normalized:
            self.text_parts.append(normalized)


def _extract_eastmoney_art_code(*urls: str | None) -> str | None:
    for url in urls:
        if not url:
            continue
        match = _EASTMONEY_ART_CODE_RE.search(url)
        if match:
            return match.group(1).upper()
    return None


def _preferred_trace_url(source_url: str | None, raw_url: str | None) -> str | None:
    for url in (source_url, raw_url):
        if url and _extract_eastmoney_art_code(url):
            return url
    return source_url or raw_url


def _string_or_empty(value: object) -> str:
    if value is None:
        return ""
    return str(value)


def _positive_int_or_none(value: object) -> int | None:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()
