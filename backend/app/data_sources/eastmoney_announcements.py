from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import httpx


class AnnouncementDataSourceError(RuntimeError):
    """Raised when an announcement source cannot return usable data."""


class UnsupportedAnnouncementSourceError(AnnouncementDataSourceError):
    """Raised when the current provider does not support the requested security."""


@dataclass(frozen=True)
class FetchedAnnouncement:
    title: str
    published_at: datetime
    category: str
    source: str
    source_url: str
    raw_url: str | None = None


class EastmoneyAnnouncementClient:
    api_url = "https://np-anotice-stock.eastmoney.com/api/security/ann"
    detail_url_template = "https://data.eastmoney.com/notices/detail/{stock_code}/{art_code}.html"
    pdf_url_template = "https://pdf.dfcfw.com/pdf/H2_{art_code}_1.pdf"
    source_name = "eastmoney_announcements"

    def __init__(self, timeout: float = 12.0) -> None:
        self._timeout = timeout

    def fetch_announcements(
        self,
        ticker: str,
        years: int = 1,
        page_size: int = 50,
        limit: int | None = 50,
        as_of: datetime | None = None,
    ) -> list[FetchedAnnouncement]:
        stock_code = _normalize_a_share_stock_code(ticker)
        if years < 1:
            raise AnnouncementDataSourceError("公告回看年限必须大于 0")

        normalized_page_size = max(1, min(page_size, 100))
        max_items = None if limit is None else max(1, min(limit, 50))
        reference_time = _as_utc(as_of or datetime.now(UTC))
        published_since = _start_of_day(_subtract_years(reference_time, years))
        announcements: list[FetchedAnnouncement] = []
        page_index = 1

        while page_index <= 200:
            raw_items, total_hits = self._fetch_announcement_page(
                stock_code=stock_code,
                page_index=page_index,
                page_size=normalized_page_size,
            )
            if not raw_items:
                break

            reached_cutoff = False
            for row in raw_items:
                if not isinstance(row, dict):
                    continue

                announcement = _map_eastmoney_announcement(row, stock_code, self.source_name)
                if announcement.published_at < published_since:
                    reached_cutoff = True
                    continue
                announcements.append(announcement)
                if max_items is not None and len(announcements) >= max_items:
                    return announcements[:max_items]

            if reached_cutoff:
                break
            if total_hits is not None and page_index * normalized_page_size >= total_hits:
                break
            if len(raw_items) < normalized_page_size:
                break

            page_index += 1
        else:
            raise AnnouncementDataSourceError(
                "东方财富公告分页超过安全上限，可能未完整读取目标时间范围公告"
            )

        return announcements

    def _fetch_announcement_page(
        self, stock_code: str, page_index: int, page_size: int
    ) -> tuple[list[object], int | None]:
        params = {
            "sr": "-1",
            "page_size": str(page_size),
            "page_index": str(page_index),
            "ann_type": "A",
            "client_source": "web",
            "stock_list": stock_code,
        }

        try:
            response = httpx.get(self.api_url, params=params, timeout=self._timeout)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise AnnouncementDataSourceError(f"东方财富公告请求失败：{exc}") from exc

        try:
            payload = response.json()
        except ValueError as exc:
            raise AnnouncementDataSourceError("东方财富公告返回不是有效 JSON") from exc

        if payload.get("success") not in (1, True):
            message = payload.get("error") or payload.get("message") or "未知错误"
            raise AnnouncementDataSourceError(f"东方财富公告返回失败：{message}")

        data = payload.get("data", {})
        raw_items = data.get("list", [])
        if not isinstance(raw_items, list):
            raise AnnouncementDataSourceError("东方财富公告数据结构异常")

        return raw_items, _positive_int_or_none(data.get("total_hits"))


def _normalize_a_share_stock_code(ticker: str) -> str:
    normalized = ticker.strip().upper()
    stock_code = normalized.split(".", 1)[0]
    market_suffix = normalized.split(".", 1)[1] if "." in normalized else ""

    if not stock_code.isdigit() or len(stock_code) != 6:
        raise UnsupportedAnnouncementSourceError(
            "当前公告同步第一版仅支持 A 股证券代码，例如 600519.SH"
        )

    if market_suffix and market_suffix not in {"SH", "SZ", "SS"}:
        raise UnsupportedAnnouncementSourceError(
            "当前公告同步第一版仅支持 A 股证券代码，例如 600519.SH"
        )

    return stock_code


def _map_eastmoney_announcement(
    row: dict[str, Any], stock_code: str, source_name: str
) -> FetchedAnnouncement:
    title = _string_or_none(row.get("title_ch")) or _string_or_none(row.get("title"))
    art_code = _string_or_none(row.get("art_code"))
    published_at = _parse_datetime(
        _string_or_none(row.get("notice_date"))
        or _string_or_none(row.get("display_time"))
        or _string_or_none(row.get("sort_date"))
    )
    if title is None or art_code is None or published_at is None:
        raise AnnouncementDataSourceError("东方财富公告缺少标题、公告代码或发布时间")

    category = _extract_category(row)
    source_url = EastmoneyAnnouncementClient.detail_url_template.format(
        stock_code=stock_code, art_code=art_code
    )
    raw_url = EastmoneyAnnouncementClient.pdf_url_template.format(art_code=art_code)

    return FetchedAnnouncement(
        title=title,
        published_at=published_at,
        category=category,
        source=source_name,
        source_url=source_url,
        raw_url=raw_url,
    )


def _extract_category(row: dict[str, Any]) -> str:
    columns = row.get("columns")
    if isinstance(columns, list) and columns:
        first_column = columns[0]
        if isinstance(first_column, dict):
            column_name = _string_or_none(first_column.get("column_name"))
            if column_name:
                return column_name
    return "其他"


def _parse_datetime(value: str | None) -> datetime | None:
    if value is None:
        return None

    normalized = value.strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M:%S:%f", "%Y-%m-%d"):
        try:
            return datetime.strptime(normalized, fmt).replace(tzinfo=UTC)
        except ValueError:
            continue

    return None


def _subtract_years(value: datetime, years: int) -> datetime:
    try:
        return value.replace(year=value.year - years)
    except ValueError:
        return value.replace(year=value.year - years, month=2, day=28)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)

    return value.astimezone(UTC)


def _start_of_day(value: datetime) -> datetime:
    return value.replace(hour=0, minute=0, second=0, microsecond=0)


def _positive_int_or_none(value: object) -> int | None:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None

    return number if number > 0 else None


def _string_or_none(value: object) -> str | None:
    if value is None:
        return None

    text = str(value).strip()
    return text or None
