import json
from datetime import UTC, date, datetime
from io import BytesIO
from pathlib import Path

import httpx
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.analysis.analyst_profiles import list_analyst_profiles
from app.data_sources.announcement_content import AnnouncementContentFetcher
from app.data_sources.eastmoney_market_snapshot import FetchedMarketSnapshot
from app.data_sources.hkex_news import HkexDisclosureProvider, parse_hkex_title_search_html
from app.data_sources.hong_kong import (
    AkshareHongKongDividendProvider,
    AkshareHongKongFinancialProvider,
    AkshareHongKongIssuerProfileProvider,
    map_akshare_hk_indicator_rows,
    map_akshare_hk_statement_rows,
)
from app.db.init_db import init_db
from app.db.models import (
    AnalysisRun,
    Announcement,
    Company,
    FxRateSnapshot,
    InvestmentMemo,
    SecurityListing,
)
from app.db.session import create_sqlalchemy_engine
from app.market_data.registry import MarketProviderBundle, default_registry
from app.schemas.announcement_summary import AnnouncementSummaryOutput
from app.services.announcement_summary_service import summarize_company_announcement
from app.services.companies import (
    build_market_context,
    refresh_company_profile,
    refresh_listing_market_snapshot,
    sync_company_announcements,
    sync_company_financials,
)
from app.services.financial_metrics import build_financial_evidence_pack
from app.services.price_decision_service import create_price_decision_run
from app.services.valuation_service import create_draft_valuation_run, recalculate_valuation_run

FIXTURE_DIRECTORY = Path(__file__).parent / "fixtures" / "hk"


def _fixture() -> dict[str, object]:
    payload = json.loads(
        (FIXTURE_DIRECTORY / "tencent_akshare.json").read_text(encoding="utf-8")
    )
    assert isinstance(payload, dict)
    return payload


class FixtureAkshareGateway:
    def __init__(self) -> None:
        self.payload = _fixture()

    def stock_hk_security_profile_em(self, *, symbol: str):
        assert symbol == "00700"
        return self.payload["security_profile"]

    def stock_hk_company_profile_em(self, *, symbol: str):
        assert symbol == "00700"
        return self.payload["company_profile"]

    def stock_financial_hk_report_em(
        self, *, stock: str, symbol: str, indicator: str
    ):
        assert stock == "00700"
        assert indicator == "报告期"
        key = {
            "资产负债表": "balance_sheet",
            "利润表": "income_statement",
            "现金流量表": "cash_flow_statement",
        }[symbol]
        return self.payload[key]

    def stock_financial_hk_analysis_indicator_em(
        self, *, symbol: str, indicator: str
    ):
        assert symbol == "00700"
        assert indicator == "报告期"
        return self.payload["indicators"]

    def stock_hk_dividend_payout_em(self, *, symbol: str):
        assert symbol == "00700"
        return self.payload["dividends"]


class FixtureHkexClient:
    def search(self, *, stock_id: str, language: str) -> str:
        assert stock_id == "7609"
        filename = "tencent_hkex_zh.html" if language == "ZH" else "tencent_hkex_en.html"
        return (FIXTURE_DIRECTORY / filename).read_text(encoding="utf-8")


class FixtureHongKongQuoteProvider:
    provider_name = "fixture_hk_quote"

    def fetch_market_snapshot(self, context) -> FetchedMarketSnapshot:
        assert context.ticker == "00700.HK"
        return FetchedMarketSnapshot(
            market_cap=4_600_000_000_000,
            current_price=500.0,
            pe_ttm=20.0,
            pe_dynamic=18.5,
            pe_static=22.0,
            pb_ratio=4.1,
            ps_ratio=6.5,
            dividend_yield_ttm=0.009,
            dividend_yield_static=0.008,
            source=self.provider_name,
            source_url="https://fixture.invalid/00700-quote",
            fetched_at=datetime.now(UTC),
        )


class FixtureAnnouncementGateway:
    model_name = "fixture-model"

    def generate_structured(self, **_: object) -> AnnouncementSummaryOutput:
        return AnnouncementSummaryOutput(
            summary="腾讯发布中期业绩公告。",
            key_facts=["Tencent interim results PDF content."],
            category="interim_report",
            impact_direction="neutral",
            confidence=0.9,
            neutral_impacts=["中期业绩已正式披露。"],
            tags=["HKEX", "中期业绩"],
            requires_review=False,
        )


def _make_test_db(tmp_path: Path):
    database_url = f"sqlite:///{(tmp_path / 'hong-kong.db').as_posix()}"
    engine = create_sqlalchemy_engine(database_url)
    init_db(engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def _tencent_context(tmp_path: Path):
    session_factory = _make_test_db(tmp_path)
    with session_factory() as session:
        company = session.scalar(select(Company).where(Company.ticker == "00700.HK"))
        assert company is not None
        listing = session.scalar(
            select(SecurityListing).where(SecurityListing.company_id == company.id)
        )
        assert listing is not None
        return build_market_context(company, listing)


def test_akshare_hk_profile_maps_issuer_identity(tmp_path: Path) -> None:
    context = _tencent_context(tmp_path)
    profile = AkshareHongKongIssuerProfileProvider(
        FixtureAkshareGateway()
    ).fetch_profile(context)

    assert profile.legal_name == "Tencent Holdings Limited"
    assert profile.aliases == (
        "腾讯控股",
        "腾讯控股有限公司",
        "Tencent Holdings Limited",
    )
    assert profile.domicile_country == "KY"
    assert profile.reporting_currency == "CNY"
    assert profile.fiscal_year_end == "12-31"
    assert profile.external_ids == {"isin": "KYG875721634"}
    assert profile.listed_date == date(2004, 6, 16)


def test_akshare_hk_financials_map_periods_currency_ttm_components(
    tmp_path: Path,
) -> None:
    context = _tencent_context(tmp_path)
    statements = AkshareHongKongFinancialProvider(
        FixtureAkshareGateway()
    ).fetch_financials(context, limit=60)

    income = next(
        item
        for item in statements
        if item.period == "2025FY" and item.statement_type == "income_statement"
    )
    cash_flow = next(
        item
        for item in statements
        if item.period == "2026H1" and item.statement_type == "cash_flow_statement"
    )
    balance = next(
        item
        for item in statements
        if item.period == "2026H1" and item.statement_type == "balance_sheet"
    )
    main = next(
        item
        for item in statements
        if item.period == "2026H1"
        and item.statement_type == "main_financial_indicators"
    )

    assert income.currency == "CNY"
    assert income.period_type == "annual"
    assert income.fields["net_profit"] == 230_000_000_000
    assert income.taxonomy == "eastmoney_hk_standard_items"
    assert income.raw_snapshot_hash
    assert cash_flow.period_type == "half_year_ytd"
    assert cash_flow.fields["capital_expenditure"] == 25_000_000_000
    assert balance.fields["interest_bearing_debt"] == 76_000_000_000
    assert main.fields["shares_outstanding"] == 9_180_000_000
    assert {item.currency for item in statements} == {"CNY"}
    assert {item.period for item in statements} >= {
        "2024FY",
        "2025H1",
        "2025FY",
        "2026H1",
    }


def test_hk_cash_flow_maps_current_online_item_names_and_sums_capex() -> None:
    rows = [
        {
            "REPORT_DATE": "2025-12-31",
            "START_DATE": "2025-01-01",
            "FISCAL_YEAR": 2025,
            "DATE_TYPE_CODE": "001",
            "STD_ITEM_CODE": "CF_OCF",
            "STD_ITEM_NAME": "经营业务现金净额",
            "AMOUNT": 100.0,
        },
        {
            "REPORT_DATE": "2025-12-31",
            "START_DATE": "2025-01-01",
            "FISCAL_YEAR": 2025,
            "DATE_TYPE_CODE": "001",
            "STD_ITEM_CODE": "CF_FIXED",
            "STD_ITEM_NAME": "购建固定资产",
            "AMOUNT": -12.0,
        },
        {
            "REPORT_DATE": "2025-12-31",
            "START_DATE": "2025-01-01",
            "FISCAL_YEAR": 2025,
            "DATE_TYPE_CODE": "001",
            "STD_ITEM_CODE": "CF_INTANGIBLE",
            "STD_ITEM_NAME": "购建无形资产及其他资产",
            "AMOUNT": -3.0,
        },
        {
            "REPORT_DATE": "2025-12-31",
            "START_DATE": "2025-01-01",
            "FISCAL_YEAR": 2025,
            "DATE_TYPE_CODE": "001",
            "STD_ITEM_CODE": "CF_DIVIDEND",
            "STD_ITEM_NAME": "已付股息(融资)",
            "AMOUNT": -8.0,
        },
        {
            "REPORT_DATE": "2025-12-31",
            "START_DATE": "2025-01-01",
            "FISCAL_YEAR": 2025,
            "DATE_TYPE_CODE": "001",
            "STD_ITEM_CODE": "CF_DA",
            "STD_ITEM_NAME": "加:折旧及摊销",
            "AMOUNT": 6.0,
        },
    ]

    statements = map_akshare_hk_statement_rows(
        rows,
        statement_type="cash_flow_statement",
        currency="CNY",
        symbol="00700",
    )

    assert len(statements) == 1
    fields = statements[0].fields
    assert fields["operating_cash_flow"] == 100.0
    assert fields["capital_expenditure"] == 15.0
    assert fields["dividend"] == 8.0
    assert fields["depreciation_and_amortization"] == 6.0
    assert fields["source_tags"]["capital_expenditure"]["components"] == [
        {"code": "CF_FIXED", "name": "购建固定资产"},
        {"code": "CF_INTANGIBLE", "name": "购建无形资产及其他资产"},
    ]


def test_hk_indicator_period_codes_keep_h1_and_q3_distinct() -> None:
    rows = [
        {
            "REPORT_DATE": "2025-06-30",
            "START_DATE": "2025-01-01",
            "DATE_TYPE_CODE": "002",
            "OPERATE_INCOME": 50.0,
        },
        {
            "REPORT_DATE": "2025-09-30",
            "START_DATE": "2025-01-01",
            "DATE_TYPE_CODE": "004",
            "OPERATE_INCOME": 80.0,
        },
    ]

    statements = map_akshare_hk_indicator_rows(
        rows,
        currency="CNY",
        symbol="00700",
    )

    assert [(item.period, item.period_type) for item in statements] == [
        ("2025H1", "half_year_ytd"),
        ("2025Q3", "quarterly_ytd"),
    ]


def test_akshare_hk_dividend_preserves_plan_without_guessing_total(
    tmp_path: Path,
) -> None:
    context = _tencent_context(tmp_path)
    records = AkshareHongKongDividendProvider(
        FixtureAkshareGateway()
    ).fetch_dividends(context)

    assert len(records) == 1
    assert records[0].plan == "每股派末期股息4.50港元"
    assert records[0].payment_date == date(2026, 6, 5)
    assert records[0].raw_snapshot_hash
    assert not hasattr(records[0], "total_dividend")


def test_hkex_title_search_deduplicates_languages_and_prefers_chinese(
    tmp_path: Path,
) -> None:
    context = _tencent_context(tmp_path)
    zh_items = parse_hkex_title_search_html(
        (FIXTURE_DIRECTORY / "tencent_hkex_zh.html").read_text(encoding="utf-8"),
        language="zh-HK",
    )
    items = HkexDisclosureProvider(FixtureHkexClient()).fetch_disclosures(
        context, years=2, limit=50
    )

    assert len(zh_items) == 3
    assert len(items) == 3
    interim = next(item for item in items if item.document_type == "interim_report")
    assert interim.language == "zh-HK"
    assert interim.source_document_id == "202608140002"
    assert interim.period_end == date(2026, 6, 30)
    assert interim.content_type == "application/pdf"
    assert interim.source_url.endswith("202608140002_c.pdf")


def test_tencent_vertical_chain_keeps_010_price_blind_and_converts_only_in_011(
    tmp_path: Path, monkeypatch
) -> None:
    session_factory = _make_test_db(tmp_path)
    gateway = FixtureAkshareGateway()
    original_bundle = default_registry.resolve("HK")
    monkeypatch.setitem(
        default_registry._bundles,
        "HK",
        MarketProviderBundle(
            capabilities=original_bundle.capabilities,
            profile=AkshareHongKongIssuerProfileProvider(gateway),
            quote=FixtureHongKongQuoteProvider(),
            financials=AkshareHongKongFinancialProvider(gateway),
            disclosures=HkexDisclosureProvider(FixtureHkexClient()),
            dividends=AkshareHongKongDividendProvider(gateway),
            fx=original_bundle.fx,
        ),
    )

    with session_factory() as session:
        company = session.scalar(select(Company).where(Company.ticker == "00700.HK"))
        assert company is not None
        listing = session.scalar(
            select(SecurityListing).where(SecurityListing.company_id == company.id)
        )
        assert listing is not None

        refreshed, updated = refresh_company_profile(session, company)
        financials, fetched, created, changed = sync_company_financials(
            session, company, listing_id=listing.id
        )
        announcements, total, added, amended, skipped, pruned, errors = (
            sync_company_announcements(session, company, years=2, listing_id=listing.id)
        )
        evidence_pack = build_financial_evidence_pack(financials)

        assert updated is True
        assert refreshed.legal_name == "Tencent Holdings Limited"
        assert refreshed.reporting_currency == "CNY"
        assert fetched == created == len(financials)
        assert changed == 0
        assert total == added == len(announcements) == 3
        assert amended == skipped == pruned == 0
        assert errors == []
        assert all(item.listing_id == listing.id for item in announcements)
        assert evidence_pack["reporting_currency"] == "CNY"

        interim = session.scalar(
            select(Announcement).where(
                Announcement.company_id == company.id,
                Announcement.source_document_id == "202608140002",
            )
        )
        assert interim is not None
        pdf_bytes = _text_pdf_bytes("Tencent interim results PDF content.")

        def fake_get(url: str, **_: object) -> httpx.Response:
            return httpx.Response(
                200,
                content=pdf_bytes,
                headers={"content-type": "application/pdf"},
                request=httpx.Request("GET", url),
            )

        monkeypatch.setattr("app.data_sources.announcement_content.httpx.get", fake_get)
        summarized, _ = summarize_company_announcement(
            session,
            company,
            interim,
            gateway=FixtureAnnouncementGateway(),
            content_fetcher=AnnouncementContentFetcher(),
        )
        assert "Tencent interim results PDF content" in (summarized.raw_content or "")
        assert summarized.content_source == interim.source_url
        assert summarized.content_fetched_at is not None
        assert summarized.raw_content_hash

        _seed_tencent_research_contract(session, company)
        market_snapshot = refresh_listing_market_snapshot(session, listing)
        fx_snapshot = FxRateSnapshot(
            base_currency="CNY",
            quote_currency="HKD",
            rate=1.08,
            rate_date=date.today(),
            fetched_at=datetime.now(UTC),
            source="fixture_ecb_cross",
            source_url="https://fixture.invalid/ecb-cny-hkd",
            raw_snapshot_hash="fixture-cny-hkd",
        )
        session.add(fx_snapshot)
        session.commit()
        session.refresh(fx_snapshot)

        draft = create_draft_valuation_run(session, company)
        valuation = recalculate_valuation_run(
            session,
            draft,
            user_assumptions={"scenarios": draft.model_suggested_assumptions["scenarios"]},
        )
        decision = create_price_decision_run(
            session,
            company,
            valuation_run_id=valuation.id,
            listing_id=listing.id,
        )

        assert market_snapshot.currency == "HKD"
        assert valuation.valuation_currency == "CNY"
        assert valuation.valuation_inputs["base_period_method"] == "ttm_adjusted"
        assert valuation.valuation_inputs["base_source_periods"] == [
            "2025FY",
            "2026H1",
            "2025H1",
        ]
        assert valuation.share_basis_snapshot["basis"] == "issuer_common_share"
        assert valuation.share_basis_snapshot["status"] == "confirmed"
        assert "market_snapshot" not in valuation.input_snapshot
        assert "fx_rate" not in valuation.input_snapshot
        assert "current_price" not in valuation.input_snapshot["company"]
        assert "market_cap" not in valuation.input_snapshot["company"]
        assert decision.market_snapshot_id == market_snapshot.id
        assert decision.fx_rate_snapshot_id == fx_snapshot.id
        assert decision.valuation_currency == "CNY"
        assert decision.trading_currency == "HKD"
        assert decision.underlying_shares_per_listing_unit == 1.0
        assert decision.fx_rate == 1.08
        for scenario, issuer_value in decision.issuer_intrinsic_values_per_share.items():
            assert decision.intrinsic_values_per_share[scenario] == issuer_value * 1.08


def _text_pdf_bytes(text: str) -> bytes:
    from pypdf import PdfWriter
    from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

    writer = PdfWriter()
    page = writer.add_blank_page(width=612, height=792)
    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }
    )
    page[NameObject("/Resources")] = DictionaryObject(
        {
            NameObject("/Font"): DictionaryObject(
                {NameObject("/F1"): writer._add_object(font)}
            )
        }
    )
    content = DecodedStreamObject()
    safe_text = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    content.set_data(f"BT /F1 12 Tf 72 720 Td ({safe_text}) Tj ET".encode("ascii"))
    page[NameObject("/Contents")] = writer._add_object(content)
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


def _seed_tencent_research_contract(session, company: Company) -> None:
    analyst_run_ids: list[int] = []
    for profile in list_analyst_profiles():
        run = AnalysisRun(
            company_id=company.id,
            run_type="analyst_view",
            analyst_profile=profile.id,
            run_version="008_v1",
            model_name="fixture-model",
            prompt_version="analyst_view_v1",
            data_snapshot_hash=f"tencent-{profile.id}",
            input_snapshot={"reporting_currency": "CNY"},
            result={
                "profile_fit_score": 1.0,
                "confidence": 0.9,
                "rule_checks": [
                    {
                        "rule_id": rule.id,
                        "status": "neutral",
                        "summary": rule.label,
                        "evidence_ids": [],
                        "announcement_ids": [],
                        "financial_periods": ["2026H1", "2025FY", "2025H1"],
                    }
                    for rule in profile.rules
                ],
            },
            confidence=0.9,
            is_latest=True,
            status="success",
        )
        session.add(run)
        session.flush()
        analyst_run_ids.append(run.id)

    generation_run = AnalysisRun(
        company_id=company.id,
        run_type="investment_memo",
        analyst_profile="investment_committee",
        run_version="009_v1",
        model_name="fixture-model",
        prompt_version="investment_memo_v1",
        data_snapshot_hash="tencent-memo",
        input_snapshot={"source_analyst_run_ids": analyst_run_ids},
        result={"narrative_only": True},
        confidence=0.8,
        is_latest=True,
        status="success",
    )
    session.add(generation_run)
    session.flush()
    session.add(
        InvestmentMemo(
            company_id=company.id,
            generation_run_id=generation_run.id,
            version_no=1,
            editor_type="model",
            title="腾讯综合投资备忘录",
            conclusion="继续研究",
            sections={
                "valuation_assumption_queue": [
                    {
                        "assumption_type": "free_cash_flow_growth",
                        "reason": "以港股披露的人民币完整年度和中报构造 TTM。",
                    }
                ],
                "key_risks": ["游戏监管和金融科技合规风险"],
                "counter_evidence": [],
                "data_gaps": [],
                "source_map": {
                    "financial_periods": ["2026H1", "2025FY", "2025H1"],
                    "hkex_document_ids": ["202608140002", "202603180001"],
                },
            },
            markdown="腾讯离线固定样本研究备忘录。",
            source_analyst_run_ids=analyst_run_ids,
            source_snapshot_hash="tencent-memo",
            status="draft",
            is_latest=True,
        )
    )
    session.commit()
