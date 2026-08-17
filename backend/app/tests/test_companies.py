import json
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.analysis.model_gateway import ModelNotConfiguredError
from app.api.routes import companies as company_routes
from app.data_sources.announcement_content import (
    AnnouncementContentFetcher,
    AnnouncementContentFetchError,
)
from app.data_sources.eastmoney_announcements import (
    AnnouncementDataSourceError,
    EastmoneyAnnouncementClient,
    FetchedAnnouncement,
    UnsupportedAnnouncementSourceError,
)
from app.data_sources.eastmoney_company_profile import FetchedCompanyProfile
from app.data_sources.eastmoney_financials import (
    EastmoneyFinancialClient,
    FetchedFinancialStatement,
    _map_eastmoney_balance_sheet_row,
    _map_eastmoney_cash_flow_row,
    _map_eastmoney_income_statement_row,
)
from app.data_sources.eastmoney_market_snapshot import (
    EastmoneyMarketSnapshotClient,
    UnsupportedMarketSnapshotSourceError,
)
from app.db.base import Base
from app.db.init_db import init_db
from app.db.models import AnalysisRun, Announcement, Company, FinancialStatement
from app.db.session import create_sqlalchemy_engine, get_db
from app.main import create_app
from app.schemas.announcement_summary import AnnouncementSummaryBatchItem
from app.services.announcement_summary_service import (
    summarize_company_announcement,
    summarize_company_announcements,
    summarize_company_announcements_deep,
)
from app.services.companies import (
    ANNOUNCEMENT_RETENTION_LIMIT,
    _announcement_window_start,
    list_company_announcements_for_deep_summary,
    list_company_announcements_for_summary,
    sync_company_announcements,
    sync_company_financials,
)
from app.services.financial_metrics import build_financial_evidence_pack


def _make_test_db(tmp_path: Path):
    database_url = f"sqlite:///{(tmp_path / 'companies.db').as_posix()}"
    engine = create_sqlalchemy_engine(database_url)
    init_db(engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def _get_company_id(client: TestClient, query: str) -> int:
    response = client.get("/api/companies", params={"q": query, "limit": 100})
    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] >= 1
    return int(payload["items"][0]["id"])


def test_company_list_returns_seed_companies(tmp_path: Path) -> None:
    session_factory = _make_test_db(tmp_path)
    app = create_app(initialize_database=False)

    def override_get_db():
        with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as client:
        response = client.get("/api/companies", params={"limit": 100})

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] >= 61
    assert payload["limit"] == 100
    assert payload["offset"] == 0
    tickers = {item["ticker"] for item in payload["items"]}
    assert {"600519.SH", "600941.SH", "688981.SH", "00700.HK", "AAPL.US"}.issubset(tickers)
    assert "00941.HK" not in tickers
    assert not {"VI0001", "VI0002", "VI0003"} & tickers


def test_company_list_filters_by_query(tmp_path: Path) -> None:
    session_factory = _make_test_db(tmp_path)
    app = create_app(initialize_database=False)

    def override_get_db():
        with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as client:
        response = client.get("/api/companies", params={"q": "贵州茅台"})
        code_response = client.get("/api/companies", params={"q": "600519"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["items"][0]["ticker"] == "600519.SH"

    assert code_response.status_code == 200
    code_payload = code_response.json()
    assert code_payload["total"] == 1
    assert code_payload["items"][0]["name"] == "贵州茅台"


def test_company_list_prefers_a_share_then_hk_then_us_for_same_name(tmp_path: Path) -> None:
    session_factory = _make_test_db(tmp_path)
    with session_factory() as session:
        session.add_all(
            [
                Company(
                    ticker="PREF.US",
                    exchange="NYSE",
                    name="多地上市测试公司",
                    status="未研究",
                    tags=["美股"],
                ),
                Company(
                    ticker="09999.HK",
                    exchange="HKEX",
                    name="多地上市测试公司",
                    status="未研究",
                    tags=["港股"],
                ),
                Company(
                    ticker="600999.SH",
                    exchange="SSE",
                    name="多地上市测试公司",
                    status="未研究",
                    tags=["A股"],
                ),
            ]
        )
        session.commit()

    app = create_app(initialize_database=False)

    def override_get_db():
        with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as client:
        response = client.get("/api/companies", params={"q": "多地上市测试公司"})

    assert response.status_code == 200
    assert [item["exchange"] for item in response.json()["items"]] == [
        "SSE",
        "HKEX",
        "NYSE",
    ]


def test_company_detail_returns_seed_company(tmp_path: Path) -> None:
    session_factory = _make_test_db(tmp_path)
    app = create_app(initialize_database=False)

    def override_get_db():
        with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as client:
        company_id = _get_company_id(client, "贵州茅台")
        response = client.get(f"/api/companies/{company_id}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["ticker"] == "600519.SH"
    assert payload["name"] == "贵州茅台"
    assert payload["listed_date"] == "2001-08-27"
    assert "market_cap" in payload
    assert "current_price" in payload
    assert "pe_ttm" in payload
    assert "dividend_yield_ttm" in payload


def test_company_detail_refreshes_missing_listed_date(
    tmp_path: Path,
    monkeypatch,
) -> None:
    session_factory = _make_test_db(tmp_path)
    with session_factory() as session:
        company = session.scalar(select(Company).where(Company.ticker == "000858.SZ"))
        assert company is not None
        company.listed_date = None
        session.commit()

    app = create_app(initialize_database=False)

    def override_get_db():
        with session_factory() as session:
            yield session

    def fake_refresh_company_profile(db: Session, company: Company):
        company.listed_date = datetime(1998, 4, 27).date()
        db.commit()
        db.refresh(company)
        return company, True

    monkeypatch.setattr(company_routes, "refresh_company_profile", fake_refresh_company_profile)
    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as client:
        company_id = _get_company_id(client, "五粮液")
        response = client.get(f"/api/companies/{company_id}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["ticker"] == "000858.SZ"
    assert payload["listed_date"] == "1998-04-27"


def test_company_detail_refreshes_seed_description(
    tmp_path: Path,
    monkeypatch,
) -> None:
    session_factory = _make_test_db(tmp_path)
    app = create_app(initialize_database=False)

    def override_get_db():
        with session_factory() as session:
            yield session

    def fake_refresh_company_profile(db: Session, company: Company):
        company.description = "宜宾五粮液股份有限公司真实简介。"
        db.commit()
        db.refresh(company)
        return company, True

    monkeypatch.setattr(company_routes, "refresh_company_profile", fake_refresh_company_profile)
    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as client:
        company_id = _get_company_id(client, "五粮液")
        response = client.get(f"/api/companies/{company_id}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["ticker"] == "000858.SZ"
    assert payload["description"] == "宜宾五粮液股份有限公司真实简介。"


def test_company_profile_refresh_updates_market_snapshot(
    tmp_path: Path,
    monkeypatch,
) -> None:
    session_factory = _make_test_db(tmp_path)
    app = create_app(initialize_database=False)

    def override_get_db():
        with session_factory() as session:
            yield session

    def fake_refresh_company_market_snapshot(db: Session, company: Company):
        company.market_cap = 1694223093019.29
        company.current_price = 1355.29
        company.pe_ttm = 20.48
        company.pe_dynamic = 15.55
        company.pe_static = 20.58
        company.pb_ratio = 7.18
        company.ps_ratio = 10.57
        company.dividend_yield_ttm = 0.03838277861071787
        company.dividend_yield_static = 0.03838527303964923
        company.market_data_source = "fake_market_snapshot"
        company.market_data_source_url = "https://example.test/quote"
        company.market_data_updated_at = datetime(2026, 8, 13, 20, 0, tzinfo=UTC)
        db.commit()
        db.refresh(company)
        return company

    monkeypatch.setattr(
        company_routes,
        "refresh_company_market_snapshot",
        fake_refresh_company_market_snapshot,
    )
    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as client:
        company_id = _get_company_id(client, "贵州茅台")
        response = client.post(f"/api/companies/{company_id}/profile/refresh")

    assert response.status_code == 200
    payload = response.json()
    assert payload["ticker"] == "600519.SH"
    assert payload["market_cap"] == 1694223093019.29
    assert payload["current_price"] == 1355.29
    assert payload["pe_ttm"] == 20.48
    assert payload["pe_dynamic"] == 15.55
    assert payload["pe_static"] == 20.58
    assert payload["pb_ratio"] == 7.18
    assert payload["ps_ratio"] == 10.57
    assert payload["dividend_yield_ttm"] == 0.03838277861071787
    assert payload["dividend_yield_static"] == 0.03838527303964923
    assert payload["market_data_source"] == "fake_market_snapshot"
    assert payload["market_data_updated_at"] == "2026-08-13T20:00:00+08:00"


def test_company_profile_refresh_updates_seed_description(
    tmp_path: Path,
    monkeypatch,
) -> None:
    session_factory = _make_test_db(tmp_path)
    app = create_app(initialize_database=False)

    def override_get_db():
        with session_factory() as session:
            yield session

    def fake_refresh_company_profile(db: Session, company: Company):
        company.description = "宜宾五粮液股份有限公司真实简介。"
        db.commit()
        db.refresh(company)
        return company, True

    def fake_refresh_company_market_snapshot(db: Session, company: Company):
        db.refresh(company)
        return company

    monkeypatch.setattr(company_routes, "refresh_company_profile", fake_refresh_company_profile)
    monkeypatch.setattr(
        company_routes,
        "refresh_company_market_snapshot",
        fake_refresh_company_market_snapshot,
    )
    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as client:
        company_id = _get_company_id(client, "五粮液")
        response = client.post(f"/api/companies/{company_id}/profile/refresh")

    assert response.status_code == 200
    payload = response.json()
    assert payload["ticker"] == "000858.SZ"
    assert payload["description"] == "宜宾五粮液股份有限公司真实简介。"


def test_company_profile_refresh_returns_clear_unsupported_error(
    tmp_path: Path,
    monkeypatch,
) -> None:
    session_factory = _make_test_db(tmp_path)
    app = create_app(initialize_database=False)

    def override_get_db():
        with session_factory() as session:
            yield session

    def fake_refresh_company_market_snapshot(db: Session, company: Company):
        raise UnsupportedMarketSnapshotSourceError("东方财富行情快照暂不支持证券代码：PRIVATE")

    monkeypatch.setattr(
        company_routes,
        "refresh_company_market_snapshot",
        fake_refresh_company_market_snapshot,
    )
    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as client:
        response = client.post(
            "/api/companies",
            json={
                "ticker": "PRIVATE",
                "exchange": "MANUAL",
                "name": "Private Company",
            },
        )
        company_id = response.json()["id"]
        refresh_response = client.post(f"/api/companies/{company_id}/profile/refresh")

    assert refresh_response.status_code == 400
    assert refresh_response.json()["detail"] == "东方财富行情快照暂不支持证券代码：PRIVATE"


def test_refresh_company_profile_replaces_seed_description(tmp_path: Path) -> None:
    session_factory = _make_test_db(tmp_path)

    class FakeCompanyProfileClient:
        def fetch_company_profile(self, secucode: str) -> FetchedCompanyProfile:
            assert secucode == "000858.SZ"
            return FetchedCompanyProfile(
                listed_date=datetime(1998, 4, 27).date(),
                description="宜宾五粮液股份有限公司真实简介。",
                source_url="https://example.test/company-profile",
            )

    with session_factory() as session:
        company = session.scalar(select(Company).where(Company.ticker == "000858.SZ"))
        assert company is not None

        from app.services.companies import refresh_company_profile

        refreshed_company, updated = refresh_company_profile(
            session,
            company,
            data_client=FakeCompanyProfileClient(),
        )

    assert updated is True
    assert refreshed_company.description == "宜宾五粮液股份有限公司真实简介。"


def test_eastmoney_market_snapshot_client_falls_back_to_delay_endpoint(
    monkeypatch,
) -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        if "push2.eastmoney.com" in str(request.url):
            raise httpx.RemoteProtocolError("Server disconnected without sending a response.")
        if "BonusFinancing" in str(request.url):
            return httpx.Response(
                200,
                json={
                    "fhyx": [
                        {
                            "NOTICE_DATE": "2026-06-22 00:00:00",
                            "IMPL_PLAN_PROFILE": "10派280.2423元",
                            "ASSIGN_PROGRESS": "实施方案",
                            "PAY_CASH_DATE": "2026-06-26 00:00:00",
                        },
                        {
                            "NOTICE_DATE": "2025-12-11 00:00:00",
                            "IMPL_PLAN_PROFILE": "10派239.57元",
                            "ASSIGN_PROGRESS": "实施方案",
                            "PAY_CASH_DATE": "2025-12-19 00:00:00",
                        },
                    ],
                    "lnfhrz": [
                        {"STATISTICS_YEAR": "2025", "TOTAL_DIVIDEND": 65033211845.95},
                        {"STATISTICS_YEAR": "2024", "TOTAL_DIVIDEND": 64671677596.8},
                    ],
                },
                request=request,
            )

        return httpx.Response(
            200,
            json={
                "rc": 0,
                "data": {
                    "f43": 1355.29,
                    "f116": 1694223093019.29,
                    "f162": 15.55,
                    "f163": 20.58,
                    "f164": 20.48,
                    "f167": 7.18,
                    "f173": 10.57,
                },
            },
            request=request,
        )

    transport = httpx.MockTransport(handler)

    def fake_get(url: str, **kwargs):
        with httpx.Client(transport=transport) as client:
            return client.get(url, **kwargs)

    monkeypatch.setattr(httpx, "get", fake_get)

    snapshot = EastmoneyMarketSnapshotClient(
        now_factory=lambda: datetime(2026, 8, 13, 23, 0, tzinfo=UTC)
    ).fetch_market_snapshot("600519.SH")

    assert len(calls) == 3
    assert "push2.eastmoney.com" in calls[0]
    assert "push2delay.eastmoney.com" in calls[1]
    assert "BonusFinancing" in calls[2]
    assert snapshot.market_cap == 1694223093019.29
    assert snapshot.current_price == 1355.29
    assert snapshot.pe_ttm == 20.48
    assert snapshot.pe_dynamic == 15.55
    assert snapshot.pe_static == 20.58
    assert snapshot.pb_ratio == 7.18
    assert snapshot.ps_ratio == 10.57
    assert snapshot.dividend_yield_ttm == (280.2423 + 239.57) / 10 / 1355.29
    assert snapshot.dividend_yield_static == 65033211845.95 / 1694223093019.29
    assert snapshot.fetched_at.isoformat() == "2026-08-14T07:00:00+08:00"
    assert "push2delay.eastmoney.com" in snapshot.source_url


def test_eastmoney_market_snapshot_uses_announced_dividend_when_latest_total_is_partial(
    monkeypatch,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if "BonusFinancing" in str(request.url):
            return httpx.Response(
                200,
                json={
                    "fhyx": [
                        {
                            "NOTICE_DATE": "2026-04-29 00:00:00",
                            "IMPL_PLAN_PROFILE": "10派44.17元",
                            "ASSIGN_PROGRESS": "股东大会预案",
                        },
                        {
                            "NOTICE_DATE": "2026-01-24 00:00:00",
                            "IMPL_PLAN_PROFILE": "10派13.58元",
                            "ASSIGN_PROGRESS": "实施方案",
                            "PAY_CASH_DATE": "2026-01-30 00:00:00",
                        },
                        {
                            "NOTICE_DATE": "2025-08-02 00:00:00",
                            "IMPL_PLAN_PROFILE": "10派45.92元",
                            "ASSIGN_PROGRESS": "实施方案",
                            "PAY_CASH_DATE": "2025-08-08 00:00:00",
                        },
                    ],
                    "lnfhrz": [
                        {"STATISTICS_YEAR": "2025", "TOTAL_DIVIDEND": 1998897185.75},
                        {"STATISTICS_YEAR": "2024", "TOTAL_DIVIDEND": 8759000000.0},
                    ],
                },
                request=request,
            )

        return httpx.Response(
            200,
            json={
                "rc": 0,
                "data": {
                    "f43": 89.42,
                    "f116": 131617428821.46,
                    "f162": 8.87,
                    "f163": 12.15,
                    "f164": 13.23,
                    "f167": 2.55,
                    "f173": 7.32,
                },
            },
            request=request,
        )

    transport = httpx.MockTransport(handler)

    def fake_get(url: str, **kwargs):
        with httpx.Client(transport=transport) as client:
            return client.get(url, **kwargs)

    monkeypatch.setattr(httpx, "get", fake_get)

    snapshot = EastmoneyMarketSnapshotClient(
        now_factory=lambda: datetime(2026, 8, 16, 12, 0, tzinfo=UTC)
    ).fetch_market_snapshot("000568.SZ")

    total_shares = 131617428821.46 / 89.42
    announced_annual_yield = (1998897185.75 + (44.17 / 10) * total_shares) / 131617428821.46
    strict_implemented_ttm_yield = (13.58 / 10) / 89.42
    assert snapshot.dividend_yield_ttm == announced_annual_yield
    assert snapshot.dividend_yield_static == announced_annual_yield
    assert snapshot.dividend_yield_ttm > strict_implemented_ttm_yield


def test_eastmoney_market_snapshot_keeps_latest_lower_dividend_without_pending_plan(
    monkeypatch,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if "BonusFinancing" in str(request.url):
            return httpx.Response(
                200,
                json={
                    "fhyx": [
                        {
                            "NOTICE_DATE": "2026-06-01 00:00:00",
                            "IMPL_PLAN_PROFILE": "10派2元",
                            "ASSIGN_PROGRESS": "实施方案",
                            "PAY_CASH_DATE": "2026-06-10 00:00:00",
                        }
                    ],
                    "lnfhrz": [
                        {"STATISTICS_YEAR": "2025", "TOTAL_DIVIDEND": 2000000000.0},
                        {"STATISTICS_YEAR": "2024", "TOTAL_DIVIDEND": 6000000000.0},
                    ],
                },
                request=request,
            )

        return httpx.Response(
            200,
            json={
                "rc": 0,
                "data": {
                    "f43": 20.0,
                    "f116": 100000000000.0,
                    "f162": 10.0,
                    "f163": 11.0,
                    "f164": 12.0,
                    "f167": 1.5,
                    "f173": 3.0,
                },
            },
            request=request,
        )

    transport = httpx.MockTransport(handler)

    def fake_get(url: str, **kwargs):
        with httpx.Client(transport=transport) as client:
            return client.get(url, **kwargs)

    monkeypatch.setattr(httpx, "get", fake_get)

    snapshot = EastmoneyMarketSnapshotClient(
        now_factory=lambda: datetime(2026, 8, 16, 12, 0, tzinfo=UTC)
    ).fetch_market_snapshot("000001.SZ")

    assert snapshot.dividend_yield_ttm == (2 / 10) / 20
    assert snapshot.dividend_yield_static == 2000000000.0 / 100000000000.0


def test_eastmoney_financial_client_normalizes_main_indicator_fields(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert "RPT_F10_FINANCE_MAINFINADATA" in str(request.url)
        return httpx.Response(
            200,
            json={
                "success": True,
                "result": {
                    "data": [
                        {
                            "SECUCODE": "600519.SH",
                            "SECURITY_NAME_ABBR": "贵州茅台",
                            "REPORT_DATE_NAME": "2025年报",
                            "REPORT_DATE": "2025-12-31 00:00:00",
                            "NOTICE_DATE": "2026-03-29 00:00:00",
                            "TOTALOPERATEREVE": "172,054,171,890.91",
                            "PARENTNETPROFIT": "82320067101.68",
                            "ROEJQ": "32.53",
                            "XSMLL": "91.18",
                            "JYXJLYYSR": "48.62",
                        }
                    ]
                },
            },
            request=request,
        )

    transport = httpx.MockTransport(handler)

    def fake_get(url: str, **kwargs):
        with httpx.Client(transport=transport) as client:
            return client.get(url, **kwargs)

    monkeypatch.setattr(httpx, "get", fake_get)

    statements = EastmoneyFinancialClient().fetch_main_financials("600519.SH", limit=60)

    assert len(statements) == 1
    assert statements[0].period == "2025年报"
    assert statements[0].fields["revenue"] == 172054171890.91
    assert statements[0].fields["net_profit"] == 82320067101.68
    assert statements[0].fields["roe"] == pytest.approx(0.3253)
    assert statements[0].fields["gross_margin"] == pytest.approx(0.9118)
    assert statements[0].fields["operating_cash_flow_to_revenue"] == pytest.approx(0.4862)


def test_eastmoney_financial_client_keeps_cash_flow_to_revenue_ratio_input(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert "RPT_F10_FINANCE_MAINFINADATA" in str(request.url)
        return httpx.Response(
            200,
            json={
                "success": True,
                "result": {
                    "data": [
                        {
                            "SECUCODE": "600519.SH",
                            "SECURITY_NAME_ABBR": "贵州茅台",
                            "REPORT_DATE_NAME": "2025年报",
                            "REPORT_DATE": "2025-12-31 00:00:00",
                            "TOTALOPERATEREVE": "172054171890.91",
                            "PARENTNETPROFIT": "82320067101.68",
                            "JYXJLYYSR": "0.4862",
                        }
                    ]
                },
            },
            request=request,
        )

    transport = httpx.MockTransport(handler)

    def fake_get(url: str, **kwargs):
        with httpx.Client(transport=transport) as client:
            return client.get(url, **kwargs)

    monkeypatch.setattr(httpx, "get", fake_get)

    statements = EastmoneyFinancialClient().fetch_main_financials("600519.SH", limit=60)

    assert statements[0].fields["operating_cash_flow_to_revenue"] == pytest.approx(0.4862)


def test_eastmoney_cash_flow_mapper_derives_free_cash_flow() -> None:
    statement = _map_eastmoney_cash_flow_row(
        {
            "SECUCODE": "600519.SH",
            "SECURITY_NAME_ABBR": "贵州茅台",
            "REPORT_DATE_NAME": "2025年报",
            "REPORT_DATE": "2025-12-31",
            "NETCASH_OPERATE": "1000",
            "CONSTRUCT_LONG_ASSET": "-260",
            "LPE_AMORTIZE": "12",
            "IA_AMORTIZE": "3",
            "OPERATE_RECE_REDUCE": "5",
            "INVENTORY_REDUCE": "-2",
            "OPERATE_PAYABLE_ADD": "7",
            "ASSIGN_DIVIDEND_PORFIT": "600",
        },
        "eastmoney_f10_cash_flow",
        "https://example.test/cash-flow",
    )

    assert statement.period == "2025年报"
    assert statement.statement_type == "cash_flow_statement"
    assert statement.fields["operating_cash_flow"] == 1000.0
    assert statement.fields["purchase_fixed_assets_cash_paid"] == -260.0
    assert statement.fields["capital_expenditure"] == 260.0
    assert statement.fields["free_cash_flow"] == 740.0
    assert statement.fields["depreciation_and_amortization"] == 15.0
    assert statement.fields["working_capital_change"] == 10.0
    assert statement.fields["dividend"] == 600.0


def test_eastmoney_income_statement_mapper_standardizes_profit_fields() -> None:
    statement = _map_eastmoney_income_statement_row(
        {
            "SECUCODE": "600519.SH",
            "SECURITY_NAME_ABBR": "贵州茅台",
            "REPORT_DATE_NAME": "2025年报",
            "REPORT_DATE": "2025-12-31",
            "REPORT_TYPE": "年报",
            "NOTICE_DATE": "2026-03-29",
            "CURRENCY": "CNY",
            "TOTAL_OPERATE_INCOME": "1720",
            "OPERATE_COST": "150",
            "OPERATE_TAX_ADD": "280",
            "SALE_EXPENSE": "60",
            "MANAGE_EXPENSE": "70",
            "RESEARCH_EXPENSE": "8",
            "FINANCE_EXPENSE": "-5",
            "OTHER_INCOME": "2",
            "INVEST_INCOME": "3",
            "FAIRVALUE_CHANGE_INCOME": "1",
            "CREDIT_IMPAIRMENT_LOSS": "-4",
            "ASSET_IMPAIRMENT_LOSS": "-6",
            "OPERATE_PROFIT": "1100",
            "NONBUSINESS_INCOME": "9",
            "NONBUSINESS_EXPENSE": "4",
            "TOTAL_PROFIT": "1105",
            "INCOME_TAX": "275",
            "NETPROFIT": "830",
            "PARENT_NETPROFIT": "823",
            "MINORITY_INTEREST": "7",
            "DEDUCT_PARENT_NETPROFIT": "810",
            "BASIC_EPS": "65.5",
        },
        "eastmoney_f10_income_statement",
        "https://example.test/income",
    )

    assert statement.period == "2025年报"
    assert statement.statement_type == "income_statement"
    assert statement.currency == "CNY"
    assert statement.fields["revenue"] == 1720.0
    assert statement.fields["operating_cost"] == 150.0
    assert statement.fields["gross_profit"] == 1570.0
    assert statement.fields["taxes_and_surcharges"] == 280.0
    assert statement.fields["selling_expense"] == 60.0
    assert statement.fields["admin_expense"] == 70.0
    assert statement.fields["r_and_d_expense"] == 8.0
    assert statement.fields["finance_expense"] == -5.0
    assert statement.fields["operating_profit"] == 1100.0
    assert statement.fields["parent_net_profit"] == 823.0
    assert statement.fields["deducted_net_profit"] == 810.0


def test_eastmoney_balance_sheet_mapper_sums_debt_and_net_cash() -> None:
    statement = _map_eastmoney_balance_sheet_row(
        {
            "SECUCODE": "600519.SH",
            "SECURITY_NAME_ABBR": "贵州茅台",
            "REPORT_DATE_NAME": "2025年报",
            "REPORT_DATE": "2025-12-31",
            "MONETARYFUNDS": "1000",
            "SHORT_LOAN": "100",
            "NONCURRENT_LIAB_1YEAR": "20",
            "LONG_LOAN": "200",
            "BOND_PAYABLE": "30",
            "LEASE_LIAB": "10",
            "TOTAL_ASSETS": "5000",
            "TOTAL_LIABILITIES": "1500",
            "TOTAL_PARENT_EQUITY": "3300",
            "GOODWILL": "50",
            "ACCOUNTS_RECE": "70",
            "NOTE_RECE": "20",
            "OTHER_RECE": "10",
            "INVENTORY": "120",
            "SHARE_CAPITAL": "1256",
            "TREASURY_SHARES": "8",
        },
        "eastmoney_f10_balance_sheet",
        "https://example.test/balance-sheet",
    )

    assert statement.statement_type == "balance_sheet"
    assert statement.fields["cash_and_equivalents"] == 1000.0
    assert statement.fields["short_term_interest_bearing_debt"] == 120.0
    assert statement.fields["long_term_interest_bearing_debt"] == 240.0
    assert statement.fields["interest_bearing_debt"] == 360.0
    assert statement.fields["net_cash"] == 640.0
    assert statement.fields["receivables"] == 100.0
    assert statement.fields["shares_outstanding"] == 1256.0
    assert statement.fields["buyback_amount_proxy"] == 8.0


def test_create_company_adds_new_company(tmp_path: Path) -> None:
    session_factory = _make_test_db(tmp_path)
    app = create_app(initialize_database=False)

    def override_get_db():
        with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as client:
        response = client.post(
            "/api/companies",
            json={
                "ticker": "sony.us",
                "exchange": "nyse",
                "name": "Sony Group Corporation 索尼集团",
                "industry": "消费电子",
                "description": "手动新增的研究对象。",
                "listed_date": "1970-09-17",
                "status": "观察中",
                "tags": ["美股", "消费电子"],
            },
        )
        search_response = client.get("/api/companies", params={"q": "索尼集团"})

    assert response.status_code == 201
    payload = response.json()
    assert payload["ticker"] == "SONY.US"
    assert payload["exchange"] == "NYSE"
    assert payload["name"] == "Sony Group Corporation 索尼集团"
    assert payload["tags"] == ["美股", "消费电子"]

    assert search_response.status_code == 200
    search_payload = search_response.json()
    assert search_payload["total"] == 1
    assert search_payload["items"][0]["ticker"] == "SONY.US"


def test_create_company_rejects_duplicate_ticker_exchange(tmp_path: Path) -> None:
    session_factory = _make_test_db(tmp_path)
    app = create_app(initialize_database=False)

    def override_get_db():
        with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as client:
        response = client.post(
            "/api/companies",
            json={
                "ticker": "600519.SH",
                "exchange": "SSE",
                "name": "重复贵州茅台",
            },
        )

    assert response.status_code == 409


def test_company_financials_return_seed_statement(tmp_path: Path) -> None:
    session_factory = _make_test_db(tmp_path)
    with session_factory() as session:
        company = session.scalar(select(Company).where(Company.ticker == "600519.SH"))
        assert company is not None
        session.add(
            FinancialStatement(
                company_id=company.id,
                period="2025A",
                statement_type="income_statement",
                currency="CNY",
                fields={
                    "revenue": 100.0,
                    "gross_margin": 0.58,
                    "net_profit": 24.0,
                    "operating_cash_flow": 28.0,
                },
                source="test_fixture",
                created_at=datetime(2026, 8, 9, 0, 0, tzinfo=UTC),
            )
        )
        session.commit()

    app = create_app(initialize_database=False)

    def override_get_db():
        with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as client:
        company_id = _get_company_id(client, "贵州茅台")
        response = client.get(f"/api/companies/{company_id}/financials")

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["limit"] == 1
    assert payload["items"][0]["period"] == "2025A"
    assert payload["items"][0]["fields"]["revenue"] == 100.0
    assert payload["items"][0]["fields"]["gross_margin"] == 0.58
    assert payload["items"][0]["created_at"] == "2026-08-09T08:00:00+08:00"


def test_company_financials_are_ordered_by_report_date(tmp_path: Path) -> None:
    session_factory = _make_test_db(tmp_path)
    with session_factory() as session:
        company = session.scalar(select(Company).where(Company.ticker == "600519.SH"))
        assert company is not None
        session.add_all(
            [
                FinancialStatement(
                    company_id=company.id,
                    period="2025中报",
                    statement_type="main_financial_indicators",
                    currency="CNY",
                    fields={"report_date": "2025-06-30", "revenue": 100.0},
                    source="test_fixture",
                ),
                FinancialStatement(
                    company_id=company.id,
                    period="2025三季报",
                    statement_type="main_financial_indicators",
                    currency="CNY",
                    fields={"report_date": "2025-09-30", "revenue": 150.0},
                    source="test_fixture",
                ),
                FinancialStatement(
                    company_id=company.id,
                    period="2025一季报",
                    statement_type="main_financial_indicators",
                    currency="CNY",
                    fields={"report_date": "2025-03-31", "revenue": 50.0},
                    source="test_fixture",
                ),
            ]
        )
        session.commit()

    app = create_app(initialize_database=False)

    def override_get_db():
        with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as client:
        company_id = _get_company_id(client, "贵州茅台")
        response = client.get(f"/api/companies/{company_id}/financials")

    assert response.status_code == 200
    payload = response.json()
    assert [item["period"] for item in payload["items"]] == [
        "2025三季报",
        "2025中报",
        "2025一季报",
    ]


def test_company_financial_evidence_pack_summarizes_facts_metrics_and_trends(
    tmp_path: Path,
) -> None:
    session_factory = _make_test_db(tmp_path)
    with session_factory() as session:
        company = session.scalar(select(Company).where(Company.ticker == "600519.SH"))
        assert company is not None
        session.add_all(
            [
                FinancialStatement(
                    company_id=company.id,
                    period="2025年报",
                    statement_type="main_financial_indicators",
                    currency="CNY",
                    fields={
                        "report_date": "2025-12-31",
                        "report_type": "年度报告",
                        "revenue": 172.0,
                        "gross_profit": 150.0,
                        "net_profit": 82.0,
                        "deducted_net_profit": 80.0,
                        "roe": 0.32,
                        "gross_margin": 0.91,
                        "net_margin": 0.48,
                        "revenue_yoy": 0.12,
                        "net_profit_yoy": 0.10,
                        "operating_cash_flow_to_revenue": 0.42,
                        "asset_liability_ratio": 0.18,
                        "total_assets_turnover": 0.5,
                        "inventory_turnover_days": 12.0,
                        "eps": 6.5,
                        "bps": 20.0,
                        "operating_cash_flow_per_share": 7.2,
                    },
                    source="test_fixture",
                ),
                FinancialStatement(
                    company_id=company.id,
                    period="2025年报",
                    statement_type="income_statement",
                    currency="CNY",
                    fields={
                        "report_date": "2025-12-31",
                        "report_type": "年度报告",
                        "revenue": 172.0,
                        "operating_cost": 20.0,
                        "gross_profit": 152.0,
                        "taxes_and_surcharges": 12.0,
                        "selling_expense": 6.0,
                        "admin_expense": 5.0,
                        "r_and_d_expense": 2.0,
                        "finance_expense": -1.0,
                        "other_income": 0.6,
                        "investment_income": 1.0,
                        "fair_value_change_income": 0.4,
                        "credit_impairment_loss": 0.2,
                        "asset_impairment_loss": 0.3,
                        "operating_profit": 108.0,
                        "non_operating_income": 0.5,
                        "non_operating_expense": 0.2,
                        "total_profit": 108.3,
                        "income_tax_expense": 26.3,
                        "net_profit": 82.0,
                        "parent_net_profit": 82.0,
                        "minority_interest": 0.0,
                        "deducted_net_profit": 80.0,
                        "eps": 6.5,
                    },
                    source="test_fixture",
                ),
                FinancialStatement(
                    company_id=company.id,
                    period="2025年报",
                    statement_type="cash_flow_statement",
                    currency="CNY",
                    fields={
                        "report_date": "2025-12-31",
                        "report_type": "年度报告",
                        "operating_cash_flow": 92.0,
                        "capital_expenditure": 18.0,
                        "free_cash_flow": 74.0,
                        "depreciation_and_amortization": 5.0,
                        "working_capital_change": -2.0,
                        "dividend": 58.0,
                    },
                    source="test_fixture",
                ),
                FinancialStatement(
                    company_id=company.id,
                    period="2025年报",
                    statement_type="balance_sheet",
                    currency="CNY",
                    fields={
                        "report_date": "2025-12-31",
                        "report_type": "年度报告",
                        "cash_and_equivalents": 120.0,
                        "short_term_interest_bearing_debt": 8.0,
                        "long_term_interest_bearing_debt": 12.0,
                        "interest_bearing_debt": 20.0,
                        "total_assets": 420.0,
                        "total_liabilities": 76.0,
                        "shareholders_equity": 300.0,
                        "goodwill": 0.0,
                        "receivables": 6.0,
                        "inventory": 12.0,
                        "shares_outstanding": 12.56,
                        "treasury_shares": 1.0,
                        "buyback_amount_proxy": 1.0,
                    },
                    source="test_fixture",
                ),
                FinancialStatement(
                    company_id=company.id,
                    period="2024年报",
                    statement_type="main_financial_indicators",
                    currency="CNY",
                    fields={
                        "report_date": "2024-12-31",
                        "report_type": "年度报告",
                        "revenue": 150.0,
                        "net_profit": 75.0,
                        "roe": 0.31,
                        "gross_margin": 0.90,
                        "net_margin": 0.47,
                    },
                    source="test_fixture",
                ),
                FinancialStatement(
                    company_id=company.id,
                    period="2023年报",
                    statement_type="main_financial_indicators",
                    currency="CNY",
                    fields={
                        "report_date": "2023-12-31",
                        "report_type": "年度报告",
                        "revenue": 120.0,
                        "net_profit": 60.0,
                        "roe": 0.30,
                        "gross_margin": 0.89,
                        "net_margin": 0.46,
                    },
                    source="test_fixture",
                ),
                FinancialStatement(
                    company_id=company.id,
                    period="2022年报",
                    statement_type="main_financial_indicators",
                    currency="CNY",
                    fields={
                        "report_date": "2022-12-31",
                        "report_type": "年度报告",
                        "revenue": 100.0,
                        "net_profit": 50.0,
                        "roe": 0.29,
                        "gross_margin": 0.88,
                        "net_margin": 0.45,
                    },
                    source="test_fixture",
                ),
            ]
        )
        session.commit()
        statements = session.scalars(
            select(FinancialStatement)
            .where(FinancialStatement.company_id == company.id)
            .order_by(FinancialStatement.fields["report_date"].as_string().desc())
        ).all()

    pack = build_financial_evidence_pack(statements)

    assert pack["latest_period"] == "2025年报"
    assert pack["financial_facts"]["latest"]["revenue"] == 172.0
    assert pack["financial_facts"]["series"]["net_profit"][0] == {
        "period": "2025年报",
        "value": 82.0,
    }
    assert pack["financial_facts"]["latest"]["free_cash_flow"] == 74.0
    assert pack["financial_facts"]["latest"]["cash_and_equivalents"] == 120.0
    assert pack["financial_facts"]["latest"]["interest_bearing_debt"] == 20.0
    assert pack["financial_facts"]["latest"]["net_cash"] == 100.0
    assert pack["financial_facts"]["latest"]["dividend"] == 58.0
    assert pack["financial_facts"]["latest"]["shares_outstanding"] == 12.56
    assert pack["financial_facts"]["latest"]["operating_cost"] == 20.0
    assert pack["financial_facts"]["latest"]["selling_expense"] == 6.0
    assert pack["financial_facts"]["latest"]["operating_profit"] == 108.0
    assert pack["financial_facts"]["latest"]["income_tax_expense"] == 26.3
    assert pack["financial_metrics"]["profitability"]["roe"] == 0.32
    assert pack["financial_metrics"]["profit_structure"]["operating_margin"] == pytest.approx(
        108.0 / 172.0
    )
    assert pack["financial_metrics"]["profit_structure"][
        "deducted_net_profit_to_net_profit"
    ] == pytest.approx(80.0 / 82.0)
    assert pack["financial_metrics"]["expense_control"]["period_expense_ratio"] == pytest.approx(
        (6.0 + 5.0 + 2.0 - 1.0) / 172.0
    )
    assert pack["financial_metrics"]["cash_quality"]["operating_cash_flow_to_revenue"] == 0.42
    assert pack["financial_metrics"]["cash_quality"][
        "free_cash_flow_to_net_profit"
    ] == pytest.approx(74.0 / 82.0)
    assert pack["financial_metrics"]["balance_sheet_safety"][
        "cash_to_interest_bearing_debt"
    ] == pytest.approx(6.0)
    assert pack["financial_metrics"]["shareholder_return"][
        "dividend_payout_ratio"
    ] == pytest.approx(58.0 / 82.0)
    assert pack["cash_flow_coverage"] == {
        "has_operating_cash_flow": True,
        "has_cash_flow_proxy": True,
        "proxy_fields": [
            "operating_cash_flow_per_share",
            "operating_cash_flow_to_revenue",
        ],
        "note": None,
    }
    assert pack["cash_flow_quality"]["free_cash_flow"] == 74.0
    assert pack["balance_sheet_adjustment"]["net_cash"] == 100.0
    assert pack["capital_allocation"]["dividend"] == 58.0
    assert pack["income_statement_quality"]["operating_profit"] == 108.0
    assert pack["quality_matrix"]["profit_structure"]["metrics"][
        "operating_margin"
    ] == pytest.approx(108.0 / 172.0)
    assert pack["quality_matrix"]["expense_control"]["metrics"][
        "period_expense_ratio"
    ] == pytest.approx((6.0 + 5.0 + 2.0 - 1.0) / 172.0)
    assert "accounting_quality" in pack["quality_matrix"]
    assert "profit_composition" in pack["analyst_summary"]
    assert pack["valuation_readiness"]["dcf_ready"] is True
    assert pack["valuation_readiness"]["asset_value_ready"] is True
    assert "analyst_summary" in pack
    assert "quality_matrix" in pack
    assert "data_quality" in pack
    assert pack["financial_trends"]["revenue_cagr_3y"] == pytest.approx(
        (172.0 / 100.0) ** (1 / 3) - 1
    )
    assert pack["financial_trends"]["roe_stability"] == "stable"
    gap_fields = {item["field"] for item in pack["financial_data_gaps"]}
    assert "operating_cash_flow" not in gap_fields
    assert "capital_expenditure" not in gap_fields
    assert "free_cash_flow" not in gap_fields
    assert "interest_bearing_debt" not in gap_fields
    assert "cash_and_equivalents" not in gap_fields
    assert "income_statement" not in gap_fields
    assert "expense_breakdown" not in gap_fields
    assert "operating_profit" not in gap_fields
    assert "impairment_losses" not in gap_fields
    assert "non_operating_items" not in gap_fields
    assert "income_tax_expense" not in gap_fields
    assert "buyback_amount" in gap_fields
    buyback_gap = next(
        item for item in pack["financial_data_gaps"] if item["field"] == "buyback_amount"
    )
    assert buyback_gap["replacement_available"] is True
    assert buyback_gap["proxy_fields"] == ["buyback_amount_proxy", "treasury_shares"]


def test_company_financial_evidence_pack_reports_flags_and_missing_data(
    tmp_path: Path,
) -> None:
    session_factory = _make_test_db(tmp_path)
    with session_factory() as session:
        company = session.scalar(select(Company).where(Company.ticker == "600519.SH"))
        assert company is not None
        statement = FinancialStatement(
            company_id=company.id,
            period="2025年报",
            statement_type="main_financial_indicators",
            currency="CNY",
            fields={
                "report_date": "2025-12-31",
                "revenue": 100.0,
                "net_profit": 10.0,
                "revenue_yoy": 0.08,
                "net_profit_yoy": -0.08,
                "asset_liability_ratio": 0.75,
                "operating_cash_flow_to_revenue": 0.03,
            },
            source="test_fixture",
        )
        session.add(statement)
        session.commit()
        statements = [statement]

    pack = build_financial_evidence_pack(statements)
    flag_codes = {item["code"] for item in pack["financial_flags"]}

    assert "profit_growth_negative" in flag_codes
    assert "profit_growth_lags_revenue" in flag_codes
    assert "high_asset_liability_ratio" in flag_codes
    assert "low_operating_cash_flow_to_revenue" in flag_codes
    operating_cash_flow_gap = next(
        item for item in pack["financial_data_gaps"] if item["field"] == "operating_cash_flow"
    )
    assert operating_cash_flow_gap["replacement_available"] is True
    assert "代理口径" in operating_cash_flow_gap["reason"]
    income_statement_gap = next(
        item for item in pack["financial_data_gaps"] if item["field"] == "income_statement"
    )
    assert income_statement_gap["replacement_available"] is True
    assert "利润构成明细" in income_statement_gap["reason"]


def test_company_financial_evidence_pack_reports_income_statement_quality_flags(
    tmp_path: Path,
) -> None:
    session_factory = _make_test_db(tmp_path)
    with session_factory() as session:
        company = session.scalar(select(Company).where(Company.ticker == "600519.SH"))
        assert company is not None
        session.add_all(
            [
                FinancialStatement(
                    company_id=company.id,
                    period="2025年报",
                    statement_type="income_statement",
                    currency="CNY",
                    fields={
                        "report_date": "2025-12-31",
                        "report_type": "年度报告",
                        "revenue": 100.0,
                        "operating_cost": 40.0,
                        "selling_expense": 8.0,
                        "admin_expense": 6.0,
                        "r_and_d_expense": 2.0,
                        "finance_expense": 5.0,
                        "operating_profit": 30.0,
                        "investment_income": 12.0,
                        "fair_value_change_income": 7.0,
                        "credit_impairment_loss": -4.0,
                        "asset_impairment_loss": -3.0,
                        "non_operating_income": 6.0,
                        "non_operating_expense": 1.0,
                        "total_profit": 35.0,
                        "income_tax_expense": 14.0,
                        "net_profit": 20.0,
                        "deducted_net_profit": 12.0,
                    },
                    source="test_fixture",
                ),
                FinancialStatement(
                    company_id=company.id,
                    period="2024年报",
                    statement_type="income_statement",
                    currency="CNY",
                    fields={
                        "report_date": "2024-12-31",
                        "report_type": "年度报告",
                        "revenue": 100.0,
                        "operating_cost": 25.0,
                        "selling_expense": 4.0,
                        "admin_expense": 4.0,
                        "r_and_d_expense": 1.0,
                        "finance_expense": 1.0,
                        "operating_profit": 40.0,
                        "total_profit": 40.0,
                        "income_tax_expense": 8.0,
                        "net_profit": 32.0,
                        "deducted_net_profit": 31.0,
                    },
                    source="test_fixture",
                ),
            ]
        )
        session.commit()
        statements = session.scalars(
            select(FinancialStatement)
            .where(FinancialStatement.company_id == company.id)
            .order_by(FinancialStatement.fields["report_date"].as_string().desc())
        ).all()

    pack = build_financial_evidence_pack(statements)
    flag_codes = {item["code"] for item in pack["financial_flags"]}

    assert "high_investment_income_to_profit" in flag_codes
    assert "high_fair_value_change_to_profit" in flag_codes
    assert "high_impairment_loss_to_profit" in flag_codes
    assert "high_non_operating_profit_to_profit" in flag_codes
    assert "abnormal_effective_tax_rate" in flag_codes
    assert "deducted_profit_lags_parent_profit" in flag_codes
    assert "operating_margin_decline" in flag_codes
    assert "period_expense_ratio_rise" in flag_codes
    assert "finance_expense_ratio_rise" in flag_codes


def test_company_financial_evidence_pack_api_returns_local_pack(tmp_path: Path) -> None:
    session_factory = _make_test_db(tmp_path)
    with session_factory() as session:
        company = session.scalar(select(Company).where(Company.ticker == "600519.SH"))
        assert company is not None
        session.add(
            FinancialStatement(
                company_id=company.id,
                period="2025年报",
                statement_type="main_financial_indicators",
                currency="CNY",
                fields={
                    "report_date": "2025-12-31",
                    "revenue": 172.0,
                    "net_profit": 82.0,
                    "roe": 0.32,
                },
                source="test_fixture",
            )
        )
        session.commit()

    app = create_app(initialize_database=False)

    def override_get_db():
        with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as client:
        company_id = _get_company_id(client, "贵州茅台")
        response = client.get(f"/api/companies/{company_id}/financials/evidence-pack")

    assert response.status_code == 200
    payload = response.json()
    assert payload["latest_period"] == "2025年报"
    assert payload["financial_facts"]["latest"]["revenue"] == 172.0
    assert payload["financial_metrics"]["profitability"]["roe"] == 0.32


def test_company_financials_can_list_sixty_periods_with_all_statement_types(
    tmp_path: Path,
) -> None:
    session_factory = _make_test_db(tmp_path)
    statement_types = (
        "main_financial_indicators",
        "income_statement",
        "cash_flow_statement",
        "balance_sheet",
    )
    with session_factory() as session:
        company = session.scalar(select(Company).where(Company.ticker == "600519.SH"))
        assert company is not None
        for index in range(60):
            period = f"P{index:02d}"
            report_date = f"{2060 - index}-12-31"
            for statement_type in statement_types:
                session.add(
                    FinancialStatement(
                        company_id=company.id,
                        period=period,
                        statement_type=statement_type,
                        currency="CNY",
                        fields={"report_date": report_date, "revenue": 1000 - index},
                        source="test_fixture",
                    )
                )
        session.commit()

    app = create_app(initialize_database=False)

    def override_get_db():
        with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as client:
        company_id = _get_company_id(client, "贵州茅台")
        response = client.get(
            f"/api/companies/{company_id}/financials?period_limit=60&period_offset=0"
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 240
    assert payload["limit"] == 240
    assert len(payload["items"]) == 240
    assert len({item["period"] for item in payload["items"]}) == 60
    assert {item["statement_type"] for item in payload["items"][:4]} == set(statement_types)


def test_delete_company_financial_statement_removes_record(tmp_path: Path) -> None:
    session_factory = _make_test_db(tmp_path)
    with session_factory() as session:
        company = session.scalar(select(Company).where(Company.ticker == "600519.SH"))
        assert company is not None
        statement = FinancialStatement(
            company_id=company.id,
            period="2025年报",
            statement_type="main_financial_indicators",
            currency="CNY",
            fields={"revenue": 172054171890.91},
            source="test_fixture",
        )
        session.add(statement)
        session.commit()
        statement_id = statement.id

    app = create_app(initialize_database=False)

    def override_get_db():
        with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as client:
        company_id = _get_company_id(client, "贵州茅台")
        delete_response = client.delete(f"/api/companies/{company_id}/financials/{statement_id}")
        list_response = client.get(f"/api/companies/{company_id}/financials")

    assert delete_response.status_code == 200
    assert delete_response.json() == {"id": statement_id, "deleted": True}
    assert list_response.status_code == 200
    assert list_response.json()["total"] == 0


def test_delete_company_financial_statement_rejects_wrong_company(
    tmp_path: Path,
) -> None:
    session_factory = _make_test_db(tmp_path)
    with session_factory() as session:
        maotai = session.scalar(select(Company).where(Company.ticker == "600519.SH"))
        apple = session.scalar(select(Company).where(Company.ticker == "AAPL.US"))
        assert maotai is not None
        assert apple is not None
        statement = FinancialStatement(
            company_id=maotai.id,
            period="2025年报",
            statement_type="main_financial_indicators",
            currency="CNY",
            fields={"revenue": 172054171890.91},
            source="test_fixture",
        )
        session.add(statement)
        session.commit()
        statement_id = statement.id
        apple_id = apple.id

    app = create_app(initialize_database=False)

    def override_get_db():
        with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as client:
        response = client.delete(f"/api/companies/{apple_id}/financials/{statement_id}")

    assert response.status_code == 404
    assert response.json()["detail"] == "Financial statement not found"


def test_company_financial_sync_creates_and_updates_statements(
    tmp_path: Path,
    monkeypatch,
) -> None:
    session_factory = _make_test_db(tmp_path)
    app = create_app(initialize_database=False)

    def override_get_db():
        with session_factory() as session:
            yield session

    def fake_sync_company_financials(db, company, limit=60):
        return sync_company_financials(
            db,
            company,
            data_client=FakeFinancialClient(),
            limit=limit,
        )

    monkeypatch.setattr(company_routes, "sync_company_financials", fake_sync_company_financials)
    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as client:
        company_id = _get_company_id(client, "贵州茅台")
        first_response = client.post(f"/api/companies/{company_id}/financials/sync")
        second_response = client.post(f"/api/companies/{company_id}/financials/sync")
        list_response = client.get(f"/api/companies/{company_id}/financials")

    assert first_response.status_code == 200
    first_payload = first_response.json()
    assert first_payload["fetched"] == 2
    assert first_payload["created"] == 2
    assert first_payload["updated"] == 0
    assert first_payload["items"][0]["period"] == "2025年报"
    assert first_payload["items"][0]["fields"]["revenue"] == 172054171890.91
    assert first_payload["items"][0]["fields"]["roe"] == 0.3253

    assert second_response.status_code == 200
    second_payload = second_response.json()
    assert second_payload["created"] == 0
    assert second_payload["updated"] == 2

    assert list_response.status_code == 200
    list_payload = list_response.json()
    assert list_payload["total"] == 2
    assert list_payload["items"][0]["source"] == "fake_financial_source"


def test_company_financial_sync_uses_expanded_statement_fetcher(tmp_path: Path) -> None:
    session_factory = _make_test_db(tmp_path)
    with session_factory() as session:
        company = session.scalar(select(Company).where(Company.ticker == "600519.SH"))
        assert company is not None

        items, fetched, created, updated = sync_company_financials(
            session,
            company,
            data_client=FakeExpandedFinancialClient(),
            limit=60,
        )

    assert fetched == 4
    assert created == 4
    assert updated == 0
    assert {item.statement_type for item in items} == {
        "main_financial_indicators",
        "income_statement",
        "cash_flow_statement",
        "balance_sheet",
    }


def test_company_announcements_return_seed_announcement(tmp_path: Path) -> None:
    session_factory = _make_test_db(tmp_path)
    with session_factory() as session:
        company = session.scalar(select(Company).where(Company.ticker == "600519.SH"))
        assert company is not None
        session.add(
            Announcement(
                company_id=company.id,
                title="年度经营摘要已导入",
                published_at=datetime(2026, 1, 15, tzinfo=UTC),
                category="annual_report",
                source="test_fixture",
                summary="测试公告用于验证公告列表读取。",
                importance_score=0.7,
            )
        )
        session.commit()

    app = create_app(initialize_database=False)

    def override_get_db():
        with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as client:
        company_id = _get_company_id(client, "贵州茅台")
        response = client.get(f"/api/companies/{company_id}/announcements")

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["items"][0]["title"] == "年度经营摘要已导入"
    assert payload["items"][0]["category"] == "annual_report"
    assert payload["items"][0]["source"] == "test_fixture"
    assert "importance_score" not in payload["items"][0]


def test_company_announcement_delete_removes_item(tmp_path: Path) -> None:
    session_factory = _make_test_db(tmp_path)
    with session_factory() as session:
        company = session.scalar(select(Company).where(Company.ticker == "600519.SH"))
        assert company is not None
        announcement = Announcement(
            company_id=company.id,
            title="可删除公告",
            published_at=datetime(2026, 3, 1, tzinfo=UTC),
            category="其他",
            source="test_fixture",
        )
        session.add(announcement)
        session.commit()
        announcement_id = announcement.id

    app = create_app(initialize_database=False)

    def override_get_db():
        with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as client:
        company_id = _get_company_id(client, "贵州茅台")
        delete_response = client.delete(
            f"/api/companies/{company_id}/announcements/{announcement_id}"
        )
        list_response = client.get(f"/api/companies/{company_id}/announcements")

    assert delete_response.status_code == 200
    assert delete_response.json() == {"id": announcement_id, "deleted": True}
    assert list_response.status_code == 200
    assert list_response.json()["total"] == 0


def test_company_announcement_delete_is_scoped_to_company(tmp_path: Path) -> None:
    session_factory = _make_test_db(tmp_path)
    with session_factory() as session:
        first_company = session.scalar(select(Company).where(Company.ticker == "600519.SH"))
        second_company = session.scalar(select(Company).where(Company.ticker == "000858.SZ"))
        assert first_company is not None
        assert second_company is not None
        announcement = Announcement(
            company_id=second_company.id,
            title="其他公司公告",
            published_at=datetime(2026, 3, 1, tzinfo=UTC),
            category="其他",
            source="test_fixture",
        )
        session.add(announcement)
        session.commit()
        announcement_id = announcement.id

    app = create_app(initialize_database=False)

    def override_get_db():
        with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as client:
        company_id = _get_company_id(client, "贵州茅台")
        response = client.delete(f"/api/companies/{company_id}/announcements/{announcement_id}")

    assert response.status_code == 404
    assert response.json()["detail"] == "Announcement not found"


def test_company_announcement_sync_creates_and_skips_duplicates(
    tmp_path: Path,
    monkeypatch,
) -> None:
    session_factory = _make_test_db(tmp_path)
    app = create_app(initialize_database=False)

    def override_get_db():
        with session_factory() as session:
            yield session

    def fake_sync_company_announcements(db, company, years=1):
        return sync_company_announcements(
            db,
            company,
            data_client=FakeAnnouncementClient(),
            years=years,
        )

    monkeypatch.setattr(
        company_routes,
        "sync_company_announcements",
        fake_sync_company_announcements,
    )
    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as client:
        company_id = _get_company_id(client, "贵州茅台")
        first_response = client.post(f"/api/companies/{company_id}/announcements/sync")
        second_response = client.post(f"/api/companies/{company_id}/announcements/sync")
        list_response = client.get(f"/api/companies/{company_id}/announcements")

    assert first_response.status_code == 200
    first_payload = first_response.json()
    assert first_payload["fetched"] == 1
    assert first_payload["created"] == 1
    assert first_payload["updated"] == 0
    assert first_payload["skipped"] == 0
    assert first_payload["pruned"] == 0
    assert first_payload["errors"] == []
    assert first_payload["items"][0]["title"] == "贵州茅台:重大事项公告"
    assert first_payload["items"][0]["source"] == "fake_announcements"
    assert first_payload["items"][0]["raw_url"] == "https://example.test/pdf/AN1.pdf"

    assert second_response.status_code == 200
    second_payload = second_response.json()
    assert second_payload["fetched"] == 1
    assert second_payload["created"] == 0
    assert second_payload["updated"] == 0
    assert second_payload["skipped"] == 1
    assert second_payload["pruned"] == 0

    assert list_response.status_code == 200
    list_payload = list_response.json()
    assert list_payload["total"] == 1
    assert list_payload["items"][0]["source_url"] == (
        "https://example.test/notices/detail/600519/AN1.html"
    )


def test_company_announcement_sync_does_not_overwrite_existing_summary(
    tmp_path: Path,
) -> None:
    session_factory = _make_test_db(tmp_path)
    with session_factory() as session:
        company = session.scalar(select(Company).where(Company.ticker == "600519.SH"))
        assert company is not None
        announcement = Announcement(
            company_id=company.id,
            title="贵州茅台:重大事项公告",
            published_at=datetime(2026, 7, 18, tzinfo=UTC),
            category="深度分类",
            source="manual",
            source_url="https://example.test/notices/detail/600519/AN1.html",
            raw_url="https://example.test/original.pdf",
            summary="已经生成的深度摘要不能被公告同步覆盖。",
            summary_status="summarized",
            summary_model_name="fake-summary-model",
        )
        session.add(announcement)
        session.commit()

        _, fetched, created, updated, skipped, pruned, errors = sync_company_announcements(
            session,
            company,
            data_client=FakeAnnouncementClient(),
            years=1,
        )
        session.refresh(announcement)

    assert fetched == 1
    assert created == 0
    assert updated == 0
    assert skipped == 1
    assert pruned == 0
    assert errors == []
    assert announcement.category == "深度分类"
    assert announcement.source == "manual"
    assert announcement.raw_url == "https://example.test/original.pdf"
    assert announcement.summary == "已经生成的深度摘要不能被公告同步覆盖。"
    assert announcement.summary_model_name == "fake-summary-model"


def test_company_announcement_sync_resets_stale_eastmoney_page_shell_summary(
    tmp_path: Path,
) -> None:
    session_factory = _make_test_db(tmp_path)
    with session_factory() as session:
        company = session.scalar(select(Company).where(Company.ticker == "600519.SH"))
        assert company is not None
        announcement = Announcement(
            company_id=company.id,
            title="贵州茅台:重大事项公告",
            published_at=datetime(2026, 7, 18, tzinfo=UTC),
            category="其他事项",
            source="eastmoney_announcements",
            source_url="https://example.test/notices/detail/600519/AN1.html",
            raw_url="https://example.test/original.pdf",
            raw_content=(
                "贵州茅台（600519）公告正文 _ 数据中心 _ 东方财富网 "
                "数据中心 全球财经快讯 行情中心 Choice数据"
            ),
            summary="类别：其他事项；性质：重大事项公告；影响：未知。",
            key_facts=["正文未含具体重大事项内容"],
            summary_status="summarized",
            summary_model_name="fake-summary-model",
            summary_prompt_version="announcement_summary_keywords_v3",
            tags=["重大事项"],
        )
        session.add(announcement)
        session.commit()

        _, fetched, created, updated, skipped, pruned, errors = sync_company_announcements(
            session,
            company,
            data_client=FakeAnnouncementClient(),
            years=1,
        )
        session.refresh(announcement)

    assert fetched == 1
    assert created == 0
    assert updated == 1
    assert skipped == 0
    assert pruned == 0
    assert errors == []
    assert announcement.raw_content is None
    assert announcement.summary is None
    assert announcement.key_facts == []
    assert announcement.tags == []
    assert announcement.summary_status == "unprocessed"
    assert announcement.summary_model_name is None
    assert announcement.summary_prompt_version is None
    assert announcement.raw_url == "https://example.test/pdf/AN1.pdf"


def test_company_announcement_sync_prunes_announcements_outside_one_year(
    tmp_path: Path,
) -> None:
    session_factory = _make_test_db(tmp_path)
    with session_factory() as session:
        company = session.scalar(select(Company).where(Company.ticker == "600519.SH"))
        assert company is not None
        cutoff = _announcement_window_start(1)
        old_announcement = Announcement(
            company_id=company.id,
            title="贵州茅台:一年外旧公告",
            published_at=cutoff.replace(year=cutoff.year - 1),
            category="其他",
            source="test_fixture",
            source_url="https://example.test/old-announcement",
        )
        recent_announcement = Announcement(
            company_id=company.id,
            title="贵州茅台:一年内保留公告",
            published_at=cutoff,
            category="其他",
            source="test_fixture",
            source_url="https://example.test/recent-announcement",
        )
        session.add_all([old_announcement, recent_announcement])
        session.commit()

        _, fetched, created, updated, skipped, pruned, errors = sync_company_announcements(
            session,
            company,
            data_client=FakeAnnouncementClient(),
            years=1,
        )

        remaining_titles = {
            item.title
            for item in session.scalars(
                select(Announcement).where(Announcement.company_id == company.id)
            ).all()
        }

    assert fetched == 1
    assert created == 1
    assert updated == 0
    assert skipped == 0
    assert pruned == 1
    assert errors == []
    assert "贵州茅台:一年外旧公告" not in remaining_titles
    assert "贵州茅台:一年内保留公告" in remaining_titles
    assert "贵州茅台:重大事项公告" in remaining_titles


def test_company_announcement_sync_prunes_announcements_over_retention_limit(
    tmp_path: Path,
) -> None:
    session_factory = _make_test_db(tmp_path)
    with session_factory() as session:
        company = session.scalar(select(Company).where(Company.ticker == "600519.SH"))
        assert company is not None
        existing_announcements = [
            Announcement(
                company_id=company.id,
                title=f"贵州茅台:保留窗口公告{i:02d}",
                published_at=datetime(2026, 7, 1, tzinfo=UTC),
                category="其他",
                source="test_fixture",
                source_url=f"https://example.test/retention/{i:02d}",
            )
            for i in range(55)
        ]
        session.add_all(existing_announcements)
        session.commit()

        _, fetched, created, updated, skipped, pruned, errors = sync_company_announcements(
            session,
            company,
            data_client=FakeAnnouncementClient(),
            years=1,
        )

        remaining = session.scalars(
            select(Announcement)
            .where(Announcement.company_id == company.id)
            .order_by(Announcement.published_at.desc(), Announcement.id.desc())
        ).all()

    assert fetched == 1
    assert created == 1
    assert updated == 0
    assert skipped == 0
    assert pruned == 6
    assert errors == []
    assert len(remaining) == ANNOUNCEMENT_RETENTION_LIMIT
    assert "贵州茅台:重大事项公告" == remaining[0].title


def test_company_announcement_sync_unsupported_source_returns_clear_error(
    tmp_path: Path,
    monkeypatch,
) -> None:
    session_factory = _make_test_db(tmp_path)
    app = create_app(initialize_database=False)

    def override_get_db():
        with session_factory() as session:
            yield session

    def fake_sync_company_announcements(db, company, years=1):
        raise UnsupportedAnnouncementSourceError("当前公告同步第一版仅支持 A 股证券代码")

    monkeypatch.setattr(
        company_routes,
        "sync_company_announcements",
        fake_sync_company_announcements,
    )
    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as client:
        company_id = _get_company_id(client, "AAPL")
        response = client.post(f"/api/companies/{company_id}/announcements/sync")

    assert response.status_code == 400
    assert "仅支持 A 股" in response.json()["detail"]


def test_company_announcement_sync_data_source_failure_returns_clear_error(
    tmp_path: Path,
    monkeypatch,
) -> None:
    session_factory = _make_test_db(tmp_path)
    app = create_app(initialize_database=False)

    def override_get_db():
        with session_factory() as session:
            yield session

    def fake_sync_company_announcements(db, company, years=1):
        raise AnnouncementDataSourceError("东方财富公告请求失败")

    monkeypatch.setattr(
        company_routes,
        "sync_company_announcements",
        fake_sync_company_announcements,
    )
    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as client:
        company_id = _get_company_id(client, "贵州茅台")
        response = client.post(f"/api/companies/{company_id}/announcements/sync")

    assert response.status_code == 502
    assert response.json()["detail"] == "东方财富公告请求失败"


def test_eastmoney_announcement_client_fetches_announcements_in_last_year(
    monkeypatch,
) -> None:
    calls: list[tuple[int, int]] = []

    def fake_fetch_announcement_page(
        self,
        stock_code: str,
        page_index: int,
        page_size: int,
    ) -> tuple[list[object], int | None]:
        assert stock_code == "600519"
        calls.append((page_index, page_size))
        pages: dict[int, list[object]] = {
            1: [
                _eastmoney_announcement_row("AN1", "贵州茅台:一年内公告一", "2026-07-18 00:00:00"),
                _eastmoney_announcement_row("AN2", "贵州茅台:一年内公告二", "2025-08-10 00:00:00"),
            ],
            2: [
                _eastmoney_announcement_row("AN3", "贵州茅台:边界内公告", "2025-08-09 00:00:00"),
                _eastmoney_announcement_row(
                    "AN4", "贵州茅台:一年前更早公告", "2025-08-08 00:00:00"
                ),
            ],
        }
        return pages[page_index], 4

    monkeypatch.setattr(
        EastmoneyAnnouncementClient,
        "_fetch_announcement_page",
        fake_fetch_announcement_page,
    )

    client = EastmoneyAnnouncementClient()
    announcements = client.fetch_announcements(
        "600519.SH",
        years=1,
        page_size=2,
        as_of=datetime(2026, 8, 9, 12, 0, tzinfo=UTC),
    )

    assert calls == [(1, 2), (2, 2)]
    assert [announcement.title for announcement in announcements] == [
        "贵州茅台:一年内公告一",
        "贵州茅台:一年内公告二",
        "贵州茅台:边界内公告",
    ]
    assert all(
        announcement.published_at >= datetime(2025, 8, 9, tzinfo=UTC)
        for announcement in announcements
    )


def test_eastmoney_announcement_client_caps_results_at_retention_limit(
    monkeypatch,
) -> None:
    calls: list[tuple[int, int]] = []

    def fake_fetch_announcement_page(
        self,
        stock_code: str,
        page_index: int,
        page_size: int,
    ) -> tuple[list[object], int | None]:
        assert stock_code == "600519"
        calls.append((page_index, page_size))
        start = (page_index - 1) * page_size
        return [
            _eastmoney_announcement_row(
                f"AN{index:03d}",
                f"贵州茅台:一年内公告{index:03d}",
                "2026-07-18 00:00:00",
            )
            for index in range(start, start + page_size)
        ], 80

    monkeypatch.setattr(
        EastmoneyAnnouncementClient,
        "_fetch_announcement_page",
        fake_fetch_announcement_page,
    )

    client = EastmoneyAnnouncementClient()
    announcements = client.fetch_announcements(
        "600519.SH",
        years=1,
        page_size=30,
        limit=ANNOUNCEMENT_RETENTION_LIMIT,
        as_of=datetime(2026, 8, 9, 12, 0, tzinfo=UTC),
    )

    assert calls == [(1, 30), (2, 30)]
    assert len(announcements) == ANNOUNCEMENT_RETENTION_LIMIT
    assert announcements[-1].title == "贵州茅台:一年内公告049"


def test_announcement_content_fetcher_reads_eastmoney_notice_api(monkeypatch) -> None:
    calls: list[tuple[str, int]] = []

    def fake_get(url: str, **kwargs):
        request = httpx.Request("GET", url)
        assert url == "https://np-cnotice-stock.eastmoney.com/api/content/ann"
        params = kwargs["params"]
        calls.append((params["art_code"], params["page_index"]))
        return httpx.Response(
            200,
            json={
                "success": 1,
                "data": {
                    "notice_title": "贵州茅台:现金分红公告",
                    "notice_content": "\n第一页正文\n",
                    "page_size": 1,
                },
            },
            request=request,
        )

    monkeypatch.setattr(httpx, "get", fake_get)

    content, source = AnnouncementContentFetcher().fetch_text(
        source_url="https://data.eastmoney.com/notices/detail/600519/AN202608010001.html",
        raw_url="https://pdf.dfcfw.com/pdf/H2_AN202608010001_1.pdf",
    )

    assert calls == [("AN202608010001", 1)]
    assert content == "第一页正文"
    assert source == "https://data.eastmoney.com/notices/detail/600519/AN202608010001.html"


def test_announcement_content_fetcher_falls_back_to_html_when_api_fails(
    monkeypatch,
) -> None:
    calls: list[str] = []

    def fake_get(url: str, **kwargs):
        calls.append(url)
        request = httpx.Request("GET", url)
        if url == "https://np-cnotice-stock.eastmoney.com/api/content/ann":
            return httpx.Response(
                200,
                json={"success": 0, "message": "not found"},
                request=request,
            )
        return httpx.Response(
            200,
            text=(
                "<html><body><nav>导航</nav>"
                '<div id="notice_content">公告正文来自 HTML 容器。</div>'
                "</body></html>"
            ),
            headers={"content-type": "text/html; charset=utf-8"},
            request=request,
        )

    monkeypatch.setattr(httpx, "get", fake_get)

    content, source = AnnouncementContentFetcher().fetch_text(
        source_url="https://data.eastmoney.com/notices/detail/600519/AN202608010002.html",
        raw_url=None,
    )

    assert calls == [
        "https://np-cnotice-stock.eastmoney.com/api/content/ann",
        "https://data.eastmoney.com/notices/detail/600519/AN202608010002.html",
    ]
    assert content == "公告正文来自 HTML 容器。"
    assert source == "https://data.eastmoney.com/notices/detail/600519/AN202608010002.html"


def test_announcement_summary_refetches_stored_eastmoney_page_shell(
    tmp_path: Path,
) -> None:
    session_factory = _make_test_db(tmp_path)
    with session_factory() as session:
        company = session.scalar(select(Company).where(Company.ticker == "600519.SH"))
        assert company is not None
        announcement = Announcement(
            company_id=company.id,
            title="贵州茅台:关于控股股东增持公司股票的进展公告",
            published_at=datetime(2026, 8, 7, tzinfo=UTC),
            category="股东增持",
            source="eastmoney_announcements",
            source_url="https://data.eastmoney.com/notices/detail/600519/AN202608010003.html",
            raw_url="https://pdf.dfcfw.com/pdf/H2_AN202608010003_1.pdf",
            raw_content=(
                "贵州茅台（600519）公告正文 _ 数据中心 _ 东方财富网 "
                "数据中心 全球财经快讯 行情中心 Choice数据"
            ),
            summary="旧摘要误把页面壳当正文。",
            summary_status="summarized",
            summary_model_name="deepseek-v4-pro",
        )
        session.add(announcement)
        session.commit()

        fetcher = FakeRecoveredContentFetcher("证券代码：600519\n本次增持金额为 1.23 亿元。")
        gateway = CapturingAnnouncementSummaryGateway()

        summarized, run_id = summarize_company_announcement(
            session,
            company,
            announcement,
            gateway=gateway,
            content_fetcher=fetcher,
        )

    assert run_id is None
    assert fetcher.calls == [
        (
            "https://data.eastmoney.com/notices/detail/600519/AN202608010003.html",
            "https://pdf.dfcfw.com/pdf/H2_AN202608010003_1.pdf",
        )
    ]
    assert gateway.received_content == "证券代码：600519\n本次增持金额为 1.23 亿元。"
    assert summarized.raw_content == "证券代码：600519\n本次增持金额为 1.23 亿元。"
    assert summarized.summary_model_name == "fake-summary-model"


def test_announcement_summary_updates_announcement_without_history(
    tmp_path: Path,
) -> None:
    session_factory = _make_test_db(tmp_path)
    with session_factory() as session:
        company = session.scalar(select(Company).where(Company.ticker == "600519.SH"))
        assert company is not None
        announcement = Announcement(
            company_id=company.id,
            title="贵州茅台:年度报告摘要",
            published_at=datetime(2026, 4, 1, tzinfo=UTC),
            category="定期报告",
            source="test_fixture",
            source_url="https://example.test/ann",
            raw_content="公司披露年度报告，营业收入增长，现金流保持稳定。",
        )
        old_run = AnalysisRun(
            company_id=company.id,
            run_type="announcement_summary",
            analyst_profile="announcement_summary",
            input_snapshot={"stale": True},
            result={"summary": "旧摘要"},
            status="success",
        )
        session.add_all([announcement, old_run])
        session.commit()
        announcement_id = announcement.id

        summarized, run_id = summarize_company_announcement(
            session,
            company,
            announcement,
            gateway=FakeAnnouncementSummaryGateway(),
        )

        assert run_id is None
        assert summarized.id == announcement_id
        assert summarized.summary_status == "summarized"
        assert summarized.summary == "年度报告显示经营保持稳定。"
        assert summarized.key_facts == ["营业收入增长", "现金流保持稳定"]
        assert summarized.tags == ["财报", "现金流"]
        assert summarized.summary_prompt_version == "announcement_summary_keywords_v3"
        assert summarized.importance_score is None

        summary_runs = session.scalars(
            select(AnalysisRun).where(
                AnalysisRun.company_id == company.id,
                AnalysisRun.run_type == "announcement_summary",
            )
        ).all()
        assert summary_runs == []


def test_announcement_summary_failure_does_not_create_history(
    tmp_path: Path,
) -> None:
    session_factory = _make_test_db(tmp_path)
    with session_factory() as session:
        company = session.scalar(select(Company).where(Company.ticker == "600519.SH"))
        assert company is not None
        announcement = Announcement(
            company_id=company.id,
            title="贵州茅台:年度报告摘要",
            published_at=datetime(2026, 4, 1, tzinfo=UTC),
            category="定期报告",
            source="test_fixture",
            raw_content="公司披露年度报告。",
        )
        old_run = AnalysisRun(
            company_id=company.id,
            run_type="announcement_summary",
            analyst_profile="announcement_summary",
            input_snapshot={"stale": True},
            result={"summary": "旧摘要"},
            status="success",
        )
        session.add_all([announcement, old_run])
        session.commit()

        try:
            summarize_company_announcement(
                session,
                company,
                announcement,
                gateway=FakeUnconfiguredAnnouncementGateway(),
            )
        except ModelNotConfiguredError:
            pass
        else:
            raise AssertionError("expected ModelNotConfiguredError")

        summary_runs = session.scalars(
            select(AnalysisRun).where(
                AnalysisRun.company_id == company.id,
                AnalysisRun.run_type == "announcement_summary",
            )
        ).all()
        assert summary_runs == []
        assert announcement.summary_status == "failed"


def test_announcement_summary_metadata_fallback_creates_summary_without_raw_content(
    tmp_path: Path,
) -> None:
    session_factory = _make_test_db(tmp_path)
    with session_factory() as session:
        company = session.scalar(select(Company).where(Company.ticker == "600519.SH"))
        assert company is not None
        announcement = Announcement(
            company_id=company.id,
            title="贵州茅台:董事会决议公告",
            published_at=datetime(2026, 6, 1, tzinfo=UTC),
            category="治理事项",
            source="test_fixture",
            source_url="https://example.test/announcement",
        )
        session.add(announcement)
        session.commit()

        summarized, run_id = summarize_company_announcement(
            session,
            company,
            announcement,
            gateway=FakeAnnouncementSummaryGateway(),
            content_fetcher=FakeMissingContentFetcher(),
        )

        assert run_id is None
        assert summarized.summary_status == "summarized"
        assert summarized.summary.startswith("类别：")
        assert "重要性" not in summarized.summary
        assert "待复核" not in summarized.tags
        assert summarized.review_questions
        assert summarized.importance_score is None


def test_announcement_batch_summary_updates_announcements_without_history(
    tmp_path: Path,
) -> None:
    session_factory = _make_test_db(tmp_path)
    with session_factory() as session:
        company = session.scalar(select(Company).where(Company.ticker == "600519.SH"))
        assert company is not None
        announcements = [
            Announcement(
                company_id=company.id,
                title="贵州茅台:年度报告摘要",
                published_at=datetime(2026, 4, 1, tzinfo=UTC),
                category="定期报告",
                source="test_fixture",
                source_url="https://example.test/ann-1",
            ),
            Announcement(
                company_id=company.id,
                title="贵州茅台:现金分红公告",
                published_at=datetime(2026, 5, 1, tzinfo=UTC),
                category="分红",
                source="test_fixture",
                source_url="https://example.test/ann-2",
            ),
        ]
        session.add_all(announcements)
        session.commit()
        announcement_ids = [announcement.id for announcement in announcements]

        results = summarize_company_announcements(
            session,
            company,
            announcements,
            gateway=FakeUnconfiguredAnnouncementGateway(),
            content_fetcher=FakeUnexpectedContentFetcher(),
        )

        assert [item.status for item in results] == ["success", "success"]
        assert [item.announcement_id for item in results] == announcement_ids
        assert [item.run_id for item in results] == [None, None]
        assert all(item.announcement is not None for item in results)
        assert [item.announcement.summary_status for item in results if item.announcement] == [
            "summarized",
            "summarized",
        ]
        assert all(
            item.announcement.summary.startswith("类别：")
            for item in results
            if item.announcement is not None
        )
        assert all(
            item.announcement.raw_content is None
            for item in results
            if item.announcement is not None
        )
        assert all(
            item.announcement.summary_model_name == "metadata_keyword"
            for item in results
            if item.announcement is not None
        )
        summary_runs = session.scalars(
            select(AnalysisRun)
            .where(
                AnalysisRun.company_id == company.id,
                AnalysisRun.run_type == "announcement_summary",
            )
            .order_by(AnalysisRun.id)
        ).all()
        assert summary_runs == []


def test_announcement_batch_summary_skips_deep_summarized_announcements(
    tmp_path: Path,
) -> None:
    session_factory = _make_test_db(tmp_path)
    with session_factory() as session:
        company = session.scalar(select(Company).where(Company.ticker == "600519.SH"))
        assert company is not None
        quick_candidate = Announcement(
            company_id=company.id,
            title="贵州茅台:现金分红公告",
            published_at=datetime(2026, 5, 1, tzinfo=UTC),
            category="分红",
            source="test_fixture",
            summary="旧快速摘要",
            summary_status="summarized",
            summary_model_name="metadata_keyword",
        )
        deep_summary = Announcement(
            company_id=company.id,
            title="贵州茅台:年度报告摘要",
            published_at=datetime(2026, 4, 1, tzinfo=UTC),
            category="定期报告",
            source="test_fixture",
            summary="深度摘要不能被快速摘要覆盖",
            summary_status="summarized",
            summary_model_name="fake-summary-model",
        )
        session.add_all([quick_candidate, deep_summary])
        session.commit()

        announcements, pending = list_company_announcements_for_summary(
            session,
            company_id=company.id,
            limit=50,
            only_missing=False,
            include_failed=True,
            exclude_deep_summarized=True,
        )
        results = summarize_company_announcements(session, company, announcements)
        session.refresh(deep_summary)

    assert pending == 1
    assert [item.announcement_id for item in results] == [quick_candidate.id]
    assert deep_summary.summary == "深度摘要不能被快速摘要覆盖"
    assert deep_summary.summary_model_name == "fake-summary-model"


def test_announcement_deep_batch_summary_skips_existing_deep_summary(
    tmp_path: Path,
) -> None:
    session_factory = _make_test_db(tmp_path)
    with session_factory() as session:
        company = session.scalar(select(Company).where(Company.ticker == "600519.SH"))
        assert company is not None
        quick_candidate = Announcement(
            company_id=company.id,
            title="贵州茅台:年度报告摘要",
            published_at=datetime(2026, 4, 1, tzinfo=UTC),
            category="定期报告",
            source="test_fixture",
            raw_content="公司披露年度报告，营业收入增长，现金流保持稳定。",
            summary_model_name="metadata_keyword",
        )
        deep_summary = Announcement(
            company_id=company.id,
            title="贵州茅台:现金分红公告",
            published_at=datetime(2026, 5, 1, tzinfo=UTC),
            category="分红",
            source="test_fixture",
            raw_content="公司披露现金分红。",
            summary="已有深度摘要",
            summary_status="summarized",
            summary_model_name="fake-summary-model",
        )
        session.add_all([quick_candidate, deep_summary])
        session.commit()

        announcements, pending = list_company_announcements_for_deep_summary(
            session,
            company_id=company.id,
            limit=50,
        )
        results = summarize_company_announcements_deep(
            session,
            company,
            announcements,
            gateway=FakeAnnouncementSummaryGateway(),
        )
        session.refresh(quick_candidate)
        session.refresh(deep_summary)

    assert pending == 1
    assert [item.status for item in results] == ["success"]
    assert quick_candidate.summary_model_name == "fake-summary-model"
    assert deep_summary.summary == "已有深度摘要"


def test_deep_summary_list_includes_stale_eastmoney_page_shell_content(
    tmp_path: Path,
) -> None:
    session_factory = _make_test_db(tmp_path)
    with session_factory() as session:
        company = session.scalar(select(Company).where(Company.ticker == "600519.SH"))
        assert company is not None
        stale_deep_summary = Announcement(
            company_id=company.id,
            title="贵州茅台:关于控股股东增持公司股票的进展公告",
            published_at=datetime(2026, 8, 7, tzinfo=UTC),
            category="股东增持",
            source="eastmoney_announcements",
            raw_content=(
                "贵州茅台（600519）公告正文 _ 数据中心 _ 东方财富网 "
                "数据中心 全球财经快讯 行情中心 Choice数据"
            ),
            summary="已有但错误的深度摘要",
            summary_status="summarized",
            summary_model_name="fake-summary-model",
        )
        valid_deep_summary = Announcement(
            company_id=company.id,
            title="贵州茅台:现金分红公告",
            published_at=datetime(2026, 5, 1, tzinfo=UTC),
            category="分红",
            source="test_fixture",
            raw_content="证券代码：600519\n本公司披露现金分红。",
            summary="已有深度摘要",
            summary_status="summarized",
            summary_model_name="fake-summary-model",
        )
        session.add_all([stale_deep_summary, valid_deep_summary])
        session.commit()

        announcements, pending = list_company_announcements_for_deep_summary(
            session,
            company_id=company.id,
            limit=50,
        )

    assert pending == 1
    assert [item.id for item in announcements] == [stale_deep_summary.id]


def test_announcement_batch_summary_api_returns_progress_fields(
    tmp_path: Path,
    monkeypatch,
) -> None:
    session_factory = _make_test_db(tmp_path)
    with session_factory() as session:
        company = session.scalar(select(Company).where(Company.ticker == "600519.SH"))
        assert company is not None
        announcements = [
            Announcement(
                company_id=company.id,
                title=f"贵州茅台:公告{i}",
                published_at=datetime(2026, 5, i, tzinfo=UTC),
                category="其他",
                source="test_fixture",
                raw_content="公司披露公告内容。",
            )
            for i in range(1, 4)
        ]
        session.add_all(announcements)
        session.commit()

    app = create_app(initialize_database=False)

    def override_get_db():
        with session_factory() as session:
            yield session

    def fake_summarize_company_announcements(db, company, announcements):
        assert len(announcements) == 2
        return [
            AnnouncementSummaryBatchItem(
                announcement_id=announcements[0].id,
                status="success",
                summary_status="summarized",
                run_id=None,
                announcement=announcements[0],
            ),
            AnnouncementSummaryBatchItem(
                announcement_id=announcements[1].id,
                status="success",
                summary_status="summarized",
                run_id=None,
                announcement=announcements[1],
            ),
        ]

    monkeypatch.setattr(
        company_routes,
        "summarize_company_announcements",
        fake_summarize_company_announcements,
    )
    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as client:
        company_id = _get_company_id(client, "贵州茅台")
        response = client.post(
            f"/api/companies/{company_id}/announcements/summarize-all",
            params={"limit": 2, "only_missing": True, "include_failed": False},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["requested"] == 3
    assert payload["processed"] == 2
    assert payload["remaining"] == 1
    assert payload["succeeded"] == 2
    assert payload["failed"] == 0
    assert payload["items"][0]["run_id"] is None


def test_announcement_deep_batch_summary_api_returns_per_announcement_results(
    tmp_path: Path,
    monkeypatch,
) -> None:
    session_factory = _make_test_db(tmp_path)
    with session_factory() as session:
        company = session.scalar(select(Company).where(Company.ticker == "600519.SH"))
        assert company is not None
        announcements = [
            Announcement(
                company_id=company.id,
                title="贵州茅台:年度报告摘要",
                published_at=datetime(2026, 4, 1, tzinfo=UTC),
                category="定期报告",
                source="test_fixture",
                raw_content="公司披露年度报告。",
                summary_model_name="metadata_keyword",
            ),
            Announcement(
                company_id=company.id,
                title="贵州茅台:现金分红公告",
                published_at=datetime(2026, 5, 1, tzinfo=UTC),
                category="分红",
                source="test_fixture",
                raw_content="公司披露现金分红。",
                summary_model_name="fake-summary-model",
            ),
        ]
        session.add_all(announcements)
        session.commit()
        candidate_id = announcements[0].id

    app = create_app(initialize_database=False)

    def override_get_db():
        with session_factory() as session:
            yield session

    def fake_summarize_company_announcements_deep(db, company, announcements):
        assert [announcement.id for announcement in announcements] == [candidate_id]
        first = announcements[0]
        first.summary = "深度批量摘要结果写回候选公告。"
        first.summary_status = "summarized"
        first.summary_model_name = "fake-summary-model"
        return [
            AnnouncementSummaryBatchItem(
                announcement_id=first.id,
                status="success",
                summary_status="summarized",
                run_id=None,
                announcement=first,
            )
        ]

    monkeypatch.setattr(
        company_routes,
        "summarize_company_announcements_deep",
        fake_summarize_company_announcements_deep,
    )
    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as client:
        company_id = _get_company_id(client, "贵州茅台")
        response = client.post(f"/api/companies/{company_id}/announcements/summarize-all-deep")

    assert response.status_code == 200
    payload = response.json()
    assert payload["requested"] == 1
    assert payload["processed"] == 1
    assert payload["succeeded"] == 1
    assert payload["failed"] == 0
    assert payload["items"][0]["announcement_id"] == candidate_id
    assert payload["items"][0]["announcement"]["summary"] == "深度批量摘要结果写回候选公告。"


def test_announcement_summary_api_returns_clear_model_config_error(
    tmp_path: Path,
    monkeypatch,
) -> None:
    session_factory = _make_test_db(tmp_path)
    with session_factory() as session:
        company = session.scalar(select(Company).where(Company.ticker == "600519.SH"))
        assert company is not None
        announcement = Announcement(
            company_id=company.id,
            title="贵州茅台:年度报告摘要",
            published_at=datetime(2026, 4, 1, tzinfo=UTC),
            category="定期报告",
            source="test_fixture",
            raw_content="公司披露年度报告。",
        )
        session.add(announcement)
        session.commit()
        announcement_id = announcement.id

    app = create_app(initialize_database=False)

    def override_get_db():
        with session_factory() as session:
            yield session

    def fake_summarize_company_announcement(db, company, announcement):
        raise ModelNotConfiguredError("模型未配置，请先在 .env 中设置：MODEL_API_KEY")

    monkeypatch.setattr(
        company_routes,
        "summarize_company_announcement",
        fake_summarize_company_announcement,
    )
    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as client:
        company_id = _get_company_id(client, "贵州茅台")
        response = client.post(
            f"/api/companies/{company_id}/announcements/{announcement_id}/summarize"
        )

    assert response.status_code == 400
    assert response.json()["detail"] == "模型未配置，请先在 .env 中设置：MODEL_API_KEY"


def test_announcement_batch_summary_api_returns_per_announcement_results(
    tmp_path: Path,
    monkeypatch,
) -> None:
    session_factory = _make_test_db(tmp_path)
    with session_factory() as session:
        company = session.scalar(select(Company).where(Company.ticker == "600519.SH"))
        assert company is not None
        announcements = [
            Announcement(
                company_id=company.id,
                title="贵州茅台:年度报告摘要",
                published_at=datetime(2026, 4, 1, tzinfo=UTC),
                category="定期报告",
                source="test_fixture",
                raw_content="公司披露年度报告。",
            ),
            Announcement(
                company_id=company.id,
                title="贵州茅台:现金分红公告",
                published_at=datetime(2026, 5, 1, tzinfo=UTC),
                category="分红",
                source="test_fixture",
                raw_content="公司披露现金分红。",
            ),
        ]
        session.add_all(announcements)
        session.commit()
        announcement_ids = [announcement.id for announcement in announcements]

    app = create_app(initialize_database=False)
    expected_order = [announcement_ids[1], announcement_ids[0]]

    def override_get_db():
        with session_factory() as session:
            yield session

    def fake_summarize_company_announcements(db, company, announcements):
        assert [announcement.id for announcement in announcements] == expected_order
        first = announcements[0]
        first.summary = "批量摘要结果仍写回第一条公告。"
        first.summary_status = "summarized"
        return [
            AnnouncementSummaryBatchItem(
                announcement_id=first.id,
                status="success",
                summary_status="summarized",
                run_id=None,
                announcement=first,
            ),
            AnnouncementSummaryBatchItem(
                announcement_id=announcements[1].id,
                status="failed",
                summary_status="failed",
                run_id=None,
                announcement=announcements[1],
                error="模型输出未通过结构校验",
                error_type="ModelOutputValidationError",
            ),
        ]

    monkeypatch.setattr(
        company_routes,
        "summarize_company_announcements",
        fake_summarize_company_announcements,
    )
    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as client:
        company_id = _get_company_id(client, "贵州茅台")
        response = client.post(f"/api/companies/{company_id}/announcements/summarize-all")

    assert response.status_code == 200
    payload = response.json()
    assert payload["requested"] == 2
    assert payload["processed"] == 2
    assert payload["remaining"] == 0
    assert payload["succeeded"] == 1
    assert payload["failed"] == 1
    assert payload["status"] == "partial"
    assert payload["items"][0]["announcement_id"] == expected_order[0]
    assert payload["items"][0]["announcement"]["summary"] == "批量摘要结果仍写回第一条公告。"
    assert payload["items"][1]["announcement_id"] == expected_order[1]
    assert payload["items"][1]["error_type"] == "ModelOutputValidationError"


def test_seed_db_adds_real_companies_when_database_already_has_existing_data(
    tmp_path: Path,
) -> None:
    database_url = f"sqlite:///{(tmp_path / 'existing.db').as_posix()}"
    engine = create_sqlalchemy_engine(database_url)
    Base.metadata.create_all(bind=engine)

    with Session(engine) as session:
        session.add(
            Company(
                ticker="LEGACY.US",
                exchange="NYSE",
                name="Legacy Manual Company",
                status="观察中",
                tags=["manual"],
            )
        )
        session.commit()

    init_db(engine)

    with Session(engine) as session:
        company = session.scalar(select(Company).where(Company.ticker == "600519.SH"))

    assert company is not None
    assert company.name == "贵州茅台"


def test_seed_db_promotes_existing_hk_listing_to_a_share_without_changing_id(
    tmp_path: Path,
) -> None:
    database_url = f"sqlite:///{(tmp_path / 'existing-china-mobile.db').as_posix()}"
    engine = create_sqlalchemy_engine(database_url)
    Base.metadata.create_all(bind=engine)

    with Session(engine) as session:
        company = Company(
            ticker="00941.HK",
            exchange="HKEX",
            name="中国移动",
            industry="电信运营",
            description="港股电信运营商，真实公司主数据种子；不包含实时行情或投资建议。",
            listed_date=datetime(1997, 10, 23).date(),
            status="观察中",
            tags=["港股", "通信"],
            current_price=80.0,
            market_cap=1_600_000_000_000.0,
            market_data_source="old_hk_snapshot",
        )
        session.add(company)
        session.commit()
        company_id = company.id

    init_db(engine)

    with Session(engine) as session:
        companies = session.scalars(select(Company).where(Company.name == "中国移动")).all()

    assert len(companies) == 1
    assert companies[0].id == company_id
    assert companies[0].ticker == "600941.SH"
    assert companies[0].exchange == "SSE"
    assert companies[0].status == "观察中"
    assert companies[0].tags == ["A股", "通信", "运营商"]
    assert companies[0].description is not None
    assert companies[0].description.startswith("A股")
    assert companies[0].listed_date is None
    assert companies[0].current_price is None
    assert companies[0].market_cap is None
    assert companies[0].market_data_source is None


class FakeFinancialClient:
    def fetch_main_financials(
        self, secucode: str, limit: int = 60
    ) -> list[FetchedFinancialStatement]:
        assert secucode == "600519.SH"
        assert limit == 60
        return [
            FetchedFinancialStatement(
                period="2025年报",
                statement_type="main_financial_indicators",
                currency="CNY",
                fields={
                    "revenue": 172054171890.91,
                    "net_profit": 82320067101.68,
                    "roe": 0.3253,
                    "gross_margin": 0.9118,
                },
                source="fake_financial_source",
                source_url="https://example.test/financials",
            ),
            FetchedFinancialStatement(
                period="2016年报",
                statement_type="main_financial_indicators",
                currency="CNY",
                fields={
                    "revenue": 40155000000.0,
                    "net_profit": 16718000000.0,
                    "roe": 0.246,
                    "gross_margin": 0.913,
                },
                source="fake_financial_source",
                source_url="https://example.test/financials",
            ),
        ]


class FakeExpandedFinancialClient:
    def fetch_financials(self, secucode: str, limit: int = 60) -> list[FetchedFinancialStatement]:
        assert secucode == "600519.SH"
        assert limit == 60
        return [
            FetchedFinancialStatement(
                period="2025年报",
                statement_type="main_financial_indicators",
                currency="CNY",
                fields={"revenue": 100.0, "net_profit": 24.0},
                source="fake_financial_source",
                source_url="https://example.test/main",
            ),
            FetchedFinancialStatement(
                period="2025年报",
                statement_type="income_statement",
                currency="CNY",
                fields={"operating_cost": 30.0, "operating_profit": 40.0},
                source="fake_income_statement_source",
                source_url="https://example.test/income",
            ),
            FetchedFinancialStatement(
                period="2025年报",
                statement_type="cash_flow_statement",
                currency="CNY",
                fields={"operating_cash_flow": 28.0, "capital_expenditure": 6.0},
                source="fake_cash_flow_source",
                source_url="https://example.test/cash-flow",
            ),
            FetchedFinancialStatement(
                period="2025年报",
                statement_type="balance_sheet",
                currency="CNY",
                fields={"cash_and_equivalents": 50.0, "interest_bearing_debt": 10.0},
                source="fake_balance_sheet_source",
                source_url="https://example.test/balance-sheet",
            ),
        ]


class FakeAnnouncementClient:
    def fetch_announcements(
        self,
        ticker: str,
        years: int = 1,
        limit: int | None = None,
    ) -> list[FetchedAnnouncement]:
        assert ticker == "600519.SH"
        assert years == 1
        assert limit == ANNOUNCEMENT_RETENTION_LIMIT
        return [
            FetchedAnnouncement(
                title="贵州茅台:重大事项公告",
                published_at=datetime(2026, 7, 18, tzinfo=UTC),
                category="其他",
                source="fake_announcements",
                source_url="https://example.test/notices/detail/600519/AN1.html",
                raw_url="https://example.test/pdf/AN1.pdf",
            )
        ]


class FakeAnnouncementSummaryGateway:
    model_name = "fake-summary-model"

    def generate_structured(self, *, system_prompt, user_prompt, schema, temperature):
        assert "历史" in system_prompt or "history" in user_prompt
        return schema(
            summary="年度报告显示经营保持稳定。",
            key_facts=["营业收入增长", "现金流保持稳定"],
            category="定期报告",
            impact_direction="neutral",
            confidence=0.82,
            positive_impacts=["经营收入增长"],
            negative_impacts=[],
            neutral_impacts=["仍需结合财务报表复核"],
            risk_tips=["关注现金流持续性"],
            review_questions=["复核年度报告完整原文"],
            tags=["财报", "现金流"],
            requires_review=True,
            source_url="https://example.test/ann",
        )


class FakeMissingContentFetcher:
    def fetch_text(self, *, source_url: str | None, raw_url: str | None) -> tuple[str, str]:
        raise AnnouncementContentFetchError("测试环境未能读取公告正文")


class FakeUnexpectedContentFetcher:
    def fetch_text(self, *, source_url: str | None, raw_url: str | None) -> tuple[str, str]:
        raise AssertionError("批量快速摘要不应读取公告正文")


class FakeRecoveredContentFetcher:
    def __init__(self, content: str) -> None:
        self._content = content
        self.calls: list[tuple[str | None, str | None]] = []

    def fetch_text(self, *, source_url: str | None, raw_url: str | None) -> tuple[str, str]:
        self.calls.append((source_url, raw_url))
        return self._content, source_url or raw_url or "https://example.test/ann"


class CapturingAnnouncementSummaryGateway:
    model_name = "fake-summary-model"

    def __init__(self) -> None:
        self.received_content: str | None = None

    def generate_structured(self, *, system_prompt, user_prompt, schema, temperature):
        payload = json.loads(user_prompt)
        self.received_content = payload["content"]
        return schema(
            summary="公告正文显示股东已增持。",
            key_facts=["本次增持金额为 1.23 亿元"],
            category="股东增持",
            impact_direction="neutral",
            confidence=0.78,
            positive_impacts=[],
            negative_impacts=[],
            neutral_impacts=["增持进展需结合后续完成情况复核"],
            risk_tips=[],
            review_questions=["复核后续增持计划完成情况"],
            tags=["股东增持"],
            requires_review=True,
            source_url="https://example.test/ann",
        )


class FakeUnconfiguredAnnouncementGateway:
    model_name = None

    def generate_structured(self, *, system_prompt, user_prompt, schema, temperature):
        raise ModelNotConfiguredError("模型未配置，请先在 .env 中设置：MODEL_API_KEY")


def _eastmoney_announcement_row(art_code: str, title: str, notice_date: str) -> dict[str, object]:
    return {
        "art_code": art_code,
        "title_ch": title,
        "notice_date": notice_date,
        "columns": [{"column_name": "其他"}],
    }
