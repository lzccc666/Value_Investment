from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

import httpx


class CompanyProfileDataSourceError(RuntimeError):
    """Raised when a company profile data source cannot return usable data."""


class UnsupportedCompanyProfileSourceError(CompanyProfileDataSourceError):
    """Raised when the current ticker cannot be queried by this source."""


@dataclass(frozen=True)
class FetchedCompanyProfile:
    listed_date: date | None
    description: str | None
    source_url: str


class EastmoneyCompanyProfileClient:
    api_url = "https://emweb.securities.eastmoney.com/PC_HSF10/CompanySurvey/PageAjax"

    def __init__(self, timeout: float = 12.0) -> None:
        self._timeout = timeout

    def fetch_company_profile(self, secucode: str) -> FetchedCompanyProfile:
        eastmoney_code = _to_eastmoney_company_code(secucode)
        if eastmoney_code is None:
            raise UnsupportedCompanyProfileSourceError(
                f"东方财富公司概况暂不支持证券代码：{secucode}"
            )

        try:
            response = httpx.get(
                self.api_url,
                params={"code": eastmoney_code},
                timeout=self._timeout,
                headers={"User-Agent": "Mozilla/5.0"},
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise CompanyProfileDataSourceError(f"东方财富公司概况请求失败：{exc}") from exc

        try:
            payload = response.json()
        except ValueError as exc:
            raise CompanyProfileDataSourceError("东方财富公司概况返回非 JSON 数据") from exc

        if not isinstance(payload, dict):
            raise CompanyProfileDataSourceError("东方财富公司概况数据结构异常")

        if payload.get("status") == -1:
            message = payload.get("message") or "股票代码不合法"
            raise UnsupportedCompanyProfileSourceError(str(message))

        issue_rows = payload.get("fxxg", [])
        profile_rows = payload.get("jbzl", [])
        if not isinstance(issue_rows, list) or not issue_rows:
            return FetchedCompanyProfile(
                listed_date=None,
                description=_org_profile_or_none(profile_rows),
                source_url=str(response.url),
            )

        first_row = issue_rows[0]
        if not isinstance(first_row, dict):
            return FetchedCompanyProfile(
                listed_date=None,
                description=_org_profile_or_none(profile_rows),
                source_url=str(response.url),
            )

        return FetchedCompanyProfile(
            listed_date=_date_or_none(first_row.get("LISTING_DATE")),
            description=_org_profile_or_none(profile_rows),
            source_url=str(response.url),
        )


def _to_eastmoney_company_code(secucode: str) -> str | None:
    normalized = secucode.strip().upper()
    if normalized.endswith(".SH"):
        return f"SH{normalized[:-3]}"
    if normalized.endswith(".SZ"):
        return f"SZ{normalized[:-3]}"
    return None


def _date_or_none(value: object) -> date | None:
    if value is None:
        return None

    text = str(value).strip()
    if not text:
        return None

    for candidate in (text[:10], text):
        try:
            return date.fromisoformat(candidate)
        except ValueError:
            pass

    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y/%m/%d", "%Y/%m/%d %H:%M:%S"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            pass

    return None


def _org_profile_or_none(profile_rows: object) -> str | None:
    if not isinstance(profile_rows, list) or not profile_rows:
        return None

    first_row = profile_rows[0]
    if not isinstance(first_row, dict):
        return None

    for key in ("ORG_PROFILE", "BUSINESS_SCOPE"):
        value = first_row.get(key)
        if isinstance(value, str):
            normalized = value.strip()
            if normalized:
                return normalized

    return None
