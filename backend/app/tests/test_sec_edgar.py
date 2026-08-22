import json
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.analysis.analyst_profiles import list_analyst_profiles
from app.data_sources.announcement_content import AnnouncementContentFetcher
from app.data_sources.eastmoney_market_snapshot import FetchedMarketSnapshot
from app.data_sources.sec_edgar import (
    SecDisclosureProvider,
    SecEdgarClient,
    SecFinancialStatementProvider,
    SecIssuerProfileProvider,
    map_sec_companyfacts,
    map_sec_submissions,
)
from app.db.init_db import init_db
from app.db.models import (
    AnalysisRun,
    Announcement,
    Company,
    FinancialStatement,
    InvestmentMemo,
    SecurityListing,
)
from app.db.session import create_sqlalchemy_engine
from app.market_data.contracts import (
    MarketContext,
    MarketDataNotConfiguredError,
    MarketDataRateLimitedError,
)
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

FIXTURE_DIRECTORY = Path(__file__).parent / "fixtures" / "sec"


def _fixture(name: str) -> dict[str, object]:
    payload = json.loads((FIXTURE_DIRECTORY / name).read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


class FixtureSecClient:
    def fetch_submissions(self, cik: str) -> dict[str, object]:
        assert cik == "0000320193"
        return _fixture("apple_submissions.json")

    def fetch_companyfacts(self, cik: str) -> dict[str, object]:
        assert cik == "0000320193"
        return _fixture("apple_companyfacts.json")


class FixtureForeignIssuerSecClient:
    def fetch_submissions(self, cik: str) -> dict[str, object]:
        assert cik == "0001577552"
        return {
            "name": "Alibaba Group Holding Ltd",
            "formerNames": [],
            "fiscalYearEnd": None,
            "sicDescription": "Services-Business Services, NEC",
        }

    def fetch_companyfacts(self, cik: str) -> dict[str, object]:
        assert cik == "0001577552"
        return {
            "facts": {
                "us-gaap": {
                    "Assets": {
                        "units": {
                            "CNY": [
                                {
                                    "end": "2026-03-31",
                                    "val": 1_909_570_000_000,
                                    "accn": "0001577552-26-000012",
                                    "fy": 2026,
                                    "fp": "FY",
                                    "form": "20-F",
                                    "filed": "2026-05-20",
                                }
                            ]
                        }
                    }
                }
            }
        }


class FixtureSecArchiveClient:
    def fetch_text(self, url: str) -> str:
        assert url.startswith("https://www.sec.gov/Archives/")
        return """
        <html><body>
          <ix:hidden>hidden taxonomy value</ix:hidden>
          <main><h1>Apple quarterly report</h1><p>Visible filing content.</p></main>
          <script>not readable</script>
        </body></html>
        """


class FixtureAnnouncementGateway:
    model_name = "fixture-model"

    def generate_structured(self, **_: object) -> AnnouncementSummaryOutput:
        return AnnouncementSummaryOutput(
            summary="Apple filed its quarterly report.",
            key_facts=["Visible filing content."],
            category="quarterly_report",
            impact_direction="neutral",
            confidence=0.9,
            neutral_impacts=["Quarterly disclosure was filed."],
            tags=["SEC", "10-Q"],
            requires_review=False,
        )


class FixtureQuoteProvider:
    provider_name = "fixture_us_quote"

    def fetch_market_snapshot(self, context) -> FetchedMarketSnapshot:
        assert context.ticker == "AAPL.US"
        return FetchedMarketSnapshot(
            market_cap=3_400_000_000_000,
            current_price=230.0,
            pe_ttm=34.0,
            pe_dynamic=None,
            pe_static=None,
            pb_ratio=52.0,
            ps_ratio=8.5,
            dividend_yield_ttm=0.004,
            dividend_yield_static=None,
            source=self.provider_name,
            source_url="https://fixture.invalid/aapl-quote",
            fetched_at=datetime.now(UTC),
        )


def _make_test_db(tmp_path: Path):
    database_url = f"sqlite:///{(tmp_path / 'sec.db').as_posix()}"
    engine = create_sqlalchemy_engine(database_url)
    init_db(engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def test_sec_profile_maps_issuer_identity_and_requires_cik(tmp_path: Path) -> None:
    session_factory = _make_test_db(tmp_path)
    provider = SecIssuerProfileProvider(FixtureSecClient())
    with session_factory() as session:
        company = session.scalar(select(Company).where(Company.ticker == "AAPL.US"))
        assert company is not None
        listing = session.scalar(
            select(SecurityListing).where(SecurityListing.company_id == company.id)
        )
        assert listing is not None
        profile = provider.fetch_profile(build_market_context(company, listing))

    assert profile.legal_name == "Apple Inc."
    assert profile.aliases == (
        "Apple Inc. 苹果公司",
        "Apple Inc.",
        "Apple Computer, Inc.",
    )
    assert profile.reporting_currency == "USD"
    assert profile.fiscal_year_end == "09-27"
    assert profile.external_ids == {"sec_cik": "0000320193"}


def test_sec_profile_infers_missing_fiscal_year_end_from_annual_facts() -> None:
    context = MarketContext(
        company_id=15,
        canonical_key="alibaba-group",
        issuer_name="阿里巴巴-W",
        aliases=("Alibaba Group Holding Limited",),
        reporting_currency="CNY",
        fiscal_year_end="12-31",
        listing_id=64,
        ticker="BABA.US",
        symbol="BABA",
        exchange="NYSE",
        market="US",
        trading_currency="USD",
        security_type="ads",
        provider_identifiers={"sec_cik": "0001577552"},
    )

    profile = SecIssuerProfileProvider(FixtureForeignIssuerSecClient()).fetch_profile(context)

    assert profile.reporting_currency == "CNY"
    assert profile.fiscal_year_end == "03-31"


def test_sec_companyfacts_maps_explicit_periods_amendments_and_fallbacks() -> None:
    statements = map_sec_companyfacts(
        _fixture("apple_companyfacts.json"), cik="0000320193", limit=60
    )
    annual_income = next(
        item
        for item in statements
        if item.period == "2025FY" and item.statement_type == "income_statement"
    )
    fallback_income = next(
        item
        for item in statements
        if item.period == "2024FY" and item.statement_type == "income_statement"
    )
    main = next(
        item
        for item in statements
        if item.period == "2025FY" and item.statement_type == "main_financial_indicators"
    )

    assert annual_income.currency == "USD"
    assert annual_income.fields["revenue"] == 410_000_000_000
    assert annual_income.filing_type == "10-K/A"
    assert annual_income.is_amendment is True
    assert annual_income.source_record_id == "0000320193-26-000098"
    assert annual_income.period_start is not None
    assert annual_income.period_start.isoformat() == "2024-09-29"
    assert annual_income.period_end is not None
    assert annual_income.period_end.isoformat() == "2025-09-27"
    assert annual_income.period_type == "annual"
    assert annual_income.raw_snapshot_hash
    assert fallback_income.fields["revenue"] == 391_035_000_000
    assert any(
        item["code"] == "fallback_tag_used"
        for item in fallback_income.fields["mapping_diagnostics"]
    )
    assert main.fields["shares_outstanding"] == 14_800_000_000
    assert {item.statement_type for item in statements} >= {
        "main_financial_indicators",
        "income_statement",
        "cash_flow_statement",
        "balance_sheet",
    }


def test_sec_companyfacts_prefers_current_ytd_over_comparative_and_quarter() -> None:
    entries = [
        {
            "start": "2024-09-29",
            "end": "2025-06-28",
            "val": 313_695_000_000,
            "accn": "0000320193-26-000020",
            "fy": 2026,
            "fp": "Q3",
            "form": "10-Q",
            "filed": "2026-07-31",
        },
        {
            "start": "2025-03-30",
            "end": "2025-06-28",
            "val": 94_036_000_000,
            "accn": "0000320193-26-000020",
            "fy": 2026,
            "fp": "Q3",
            "form": "10-Q",
            "filed": "2026-07-31",
            "frame": "CY2025Q2",
        },
        {
            "start": "2025-09-28",
            "end": "2026-06-27",
            "val": 364_357_000_000,
            "accn": "0000320193-26-000020",
            "fy": 2026,
            "fp": "Q3",
            "form": "10-Q",
            "filed": "2026-07-31",
        },
        {
            "start": "2026-03-29",
            "end": "2026-06-27",
            "val": 109_417_000_000,
            "accn": "0000320193-26-000020",
            "fy": 2026,
            "fp": "Q3",
            "form": "10-Q",
            "filed": "2026-07-31",
            "frame": "CY2026Q2",
        },
    ]
    payload = {
        "facts": {
            "us-gaap": {
                "RevenueFromContractWithCustomerExcludingAssessedTax": {"units": {"USD": entries}}
            }
        }
    }

    statements = map_sec_companyfacts(payload, cik="0000320193", limit=4)
    income = next(
        item
        for item in statements
        if item.period == "2026Q3" and item.statement_type == "income_statement"
    )

    assert income.fields["revenue"] == 364_357_000_000
    assert income.period_start is not None
    assert income.period_start.isoformat() == "2025-09-28"
    assert income.period_end is not None
    assert income.period_end.isoformat() == "2026-06-27"


def test_sec_companyfacts_uses_requested_reporting_currency() -> None:
    entry = {
        "start": "2025-04-01",
        "end": "2026-03-31",
        "accn": "0001577552-26-000012",
        "fy": 2026,
        "fp": "FY",
        "form": "20-F",
        "filed": "2026-06-25",
    }
    payload = {
        "facts": {
            "us-gaap": {
                "Revenues": {
                    "units": {
                        "CNY": [{**entry, "val": 996_347_000_000}],
                        "USD": [{**entry, "val": 137_366_000_000}],
                    }
                }
            }
        }
    }

    statements = map_sec_companyfacts(
        payload,
        cik="0001577552",
        limit=4,
        currency="CNY",
    )
    income = next(item for item in statements if item.statement_type == "income_statement")

    assert income.currency == "CNY"
    assert income.fields["revenue"] == 996_347_000_000


def test_sec_companyfacts_maps_cost_buyback_and_profit_quality_items() -> None:
    entry = {
        "start": "2024-09-29",
        "end": "2025-09-27",
        "accn": "0000320193-25-000079",
        "fy": 2025,
        "fp": "FY",
        "form": "10-K",
        "filed": "2025-10-31",
    }
    payload = {
        "facts": {
            "us-gaap": {
                "CostOfGoodsAndServicesSold": {
                    "units": {"USD": [{**entry, "val": 210_000_000_000}]}
                },
                "PaymentsForRepurchaseOfCommonStock": {
                    "units": {"USD": [{**entry, "val": 90_000_000_000}]}
                },
                "GoodwillAndIntangibleAssetImpairment": {
                    "units": {"USD": [{**entry, "val": 250_000_000}]}
                },
                "NonoperatingIncomeExpense": {"units": {"USD": [{**entry, "val": 1_100_000_000}]}},
            }
        }
    }

    statements = map_sec_companyfacts(payload, cik="0000320193", limit=4)
    by_type = {item.statement_type: item for item in statements}

    assert by_type["income_statement"].fields["operating_cost"] == 210_000_000_000
    assert by_type["income_statement"].fields["asset_impairment_loss"] == 250_000_000
    assert by_type["income_statement"].fields["non_operating_income"] == 1_100_000_000
    assert by_type["cash_flow_statement"].fields["buyback_amount"] == 90_000_000_000


def test_sec_submissions_filters_forms_and_preserves_document_provenance() -> None:
    announcements = map_sec_submissions(
        _fixture("apple_submissions.json"), cik="0000320193", years=2, limit=50
    )

    assert [item.filing_form for item in announcements] == [
        "10-Q",
        "8-K",
        "10-K/A",
        "DEF 14A",
    ]
    assert announcements[0].source_document_id == "0000320193-26-000100"
    assert announcements[0].document_type == "quarterly_report"
    assert announcements[0].language == "en-US"
    assert announcements[0].content_type == "text/html"
    assert announcements[0].source_url.endswith("/aapl-20260627.htm")
    assert announcements[0].title == "季度报告（10-Q） · 报告期截至 2026-06-27"
    assert announcements[1].title == "重大事项报告（8-K） · 报告期截至 2026-07-29"
    assert announcements[2].title == "年度报告修订版（10-K/A） · 报告期截至 2025-09-27"
    assert announcements[3].title == "股东大会委托书（DEF 14A） · 报告期截至 2025-09-27"


def test_sec_client_requires_declared_user_agent_and_uses_json_cache(tmp_path: Path) -> None:
    with pytest.raises(MarketDataNotConfiguredError, match="SEC_USER_AGENT"):
        SecEdgarClient(user_agent="missing-contact", cache_directory=tmp_path)

    request_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal request_count
        request_count += 1
        assert request.headers["User-Agent"] == "ValueInvestment test@example.com"
        return httpx.Response(200, json={"name": "Apple Inc."})

    client = SecEdgarClient(
        user_agent="ValueInvestment test@example.com",
        cache_directory=tmp_path,
        cache_ttl_seconds=3600,
        requests_per_second=10,
        transport=httpx.MockTransport(handler),
    )
    assert client.fetch_submissions("320193")["name"] == "Apple Inc."
    assert client.fetch_submissions("0000320193")["name"] == "Apple Inc."
    assert request_count == 1
    archive_url = (
        "https://www.sec.gov/Archives/edgar/data/320193/000032019326000100/aapl-20260627.htm"
    )
    assert "Apple Inc." in client.fetch_text(archive_url)
    assert "Apple Inc." in client.fetch_text(archive_url)
    assert request_count == 2


def test_sec_archive_content_uses_sec_client_and_excludes_inline_xbrl_hidden_data() -> None:
    archive_url = (
        "https://www.sec.gov/Archives/edgar/data/320193/000032019326000100/aapl-20260627.htm"
    )
    content, source_url = AnnouncementContentFetcher(
        sec_client=FixtureSecArchiveClient()
    ).fetch_text(source_url=archive_url, raw_url=None)

    assert source_url == archive_url
    assert "Apple quarterly report" in content
    assert "Visible filing content" in content
    assert "hidden taxonomy value" not in content
    assert "not readable" not in content


def test_sec_client_surfaces_rate_limit_without_network(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("app.data_sources.sec_edgar.time.sleep", lambda _: None)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, request=request)

    client = SecEdgarClient(
        user_agent="ValueInvestment test@example.com",
        cache_directory=tmp_path,
        cache_ttl_seconds=0,
        requests_per_second=10,
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(MarketDataRateLimitedError, match="403/429"):
        client.fetch_companyfacts("0000320193")


def test_apple_vertical_chain_refreshes_profile_financials_and_disclosures(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    session_factory = _make_test_db(tmp_path)
    fixture_client = FixtureSecClient()
    original_bundle = default_registry.resolve("US")
    monkeypatch.setitem(
        default_registry._bundles,
        "US",
        MarketProviderBundle(
            capabilities=original_bundle.capabilities,
            profile=SecIssuerProfileProvider(fixture_client),
            quote=FixtureQuoteProvider(),
            financials=SecFinancialStatementProvider(fixture_client),
            disclosures=SecDisclosureProvider(fixture_client),
            fx=original_bundle.fx,
        ),
    )

    with session_factory() as session:
        company = session.scalar(select(Company).where(Company.ticker == "AAPL.US"))
        assert company is not None
        listing = session.scalar(
            select(SecurityListing).where(SecurityListing.company_id == company.id)
        )
        assert listing is not None

        refreshed, updated = refresh_company_profile(session, company)
        financials, fetched_count, created_count, updated_count = sync_company_financials(
            session, company, listing_id=listing.id
        )
        (
            announcements,
            announcement_count,
            announcement_created,
            announcement_updated,
            announcement_skipped,
            announcement_pruned,
            errors,
        ) = sync_company_announcements(session, company, years=2, listing_id=listing.id)
        evidence_pack = build_financial_evidence_pack(financials)

        assert updated is True
        assert refreshed.legal_name == "Apple Inc."
        assert fetched_count == created_count
        assert updated_count == 0
        assert (
            session.scalar(
                select(FinancialStatement).where(
                    FinancialStatement.company_id == company.id,
                    FinancialStatement.period == "2025FY",
                    FinancialStatement.statement_type == "income_statement",
                )
            )
            is not None
        )
        assert announcement_count == announcement_created == len(announcements) == 4
        assert announcement_updated == announcement_skipped == announcement_pruned == 0
        assert errors == []
        assert all(item.listing_id == listing.id for item in announcements)
        assert (
            session.scalar(
                select(Announcement).where(
                    Announcement.source_document_id == "0000320193-26-000100"
                )
            )
            is not None
        )
        assert evidence_pack["reporting_currency"] == "USD"
        assert evidence_pack["accounting_standard"] == "us-gaap"
        assert evidence_pack["source_coverage"]["currency_consistent"] is True

        announcement = session.scalar(
            select(Announcement).where(Announcement.source_document_id == "0000320193-26-000100")
        )
        assert announcement is not None
        announcement.title = "10-Q 2026-06-27"
        announcement.summary = "已有摘要应在标题刷新时保留。"
        session.commit()
        (
            _,
            second_count,
            second_created,
            second_updated,
            second_skipped,
            second_pruned,
            second_errors,
        ) = sync_company_announcements(session, company, years=2, listing_id=listing.id)
        session.refresh(announcement)
        assert second_count == 4
        assert second_created == second_pruned == 0
        assert second_updated == 1
        assert second_skipped == 3
        assert second_errors == []
        assert announcement.title == "季度报告（10-Q） · 报告期截至 2026-06-27"
        assert announcement.summary == "已有摘要应在标题刷新时保留。"
        summarized, _ = summarize_company_announcement(
            session,
            company,
            announcement,
            gateway=FixtureAnnouncementGateway(),
            content_fetcher=AnnouncementContentFetcher(sec_client=FixtureSecArchiveClient()),
        )
        assert summarized.content_source == announcement.source_url
        assert summarized.content_fetched_at is not None
        assert summarized.raw_content_hash
        assert "hidden taxonomy value" not in (summarized.raw_content or "")

        _seed_apple_research_contract(session, company)
        market_snapshot = refresh_listing_market_snapshot(session, listing)
        draft = create_draft_valuation_run(session, company)
        valuation = recalculate_valuation_run(
            session,
            draft,
            user_assumptions={"scenarios": draft.model_suggested_assumptions["scenarios"]},
        )
        per_share_values = valuation.results["intrinsic_value_range"]["per_share_value"]
        assert all(
            isinstance(per_share_values.get(scenario), int | float)
            and per_share_values[scenario] > 0
            for scenario in ("conservative", "base", "optimistic")
        ), json.dumps(
            {
                "per_share": per_share_values,
                "methods": [
                    {
                        "method": item["method"],
                        "status": item["status"],
                        "reason": item.get("reason"),
                    }
                    for item in valuation.results["method_results"]
                ],
                "gap_fields": [item["field"] for item in valuation.results["valuation_input_gaps"]],
            },
            ensure_ascii=True,
        )
        decision = create_price_decision_run(
            session,
            company,
            valuation_run_id=valuation.id,
            listing_id=listing.id,
        )

        assert market_snapshot.currency == "USD"
        assert valuation.valuation_currency == "USD"
        assert valuation.share_basis_snapshot["basis"] == "issuer_common_share"
        assert valuation.share_basis_snapshot["status"] == "confirmed"
        assert valuation.results["intrinsic_value_range"]["currency"] == "USD"
        assert "market_snapshot" not in valuation.input_snapshot
        assert "fx_rate" not in valuation.input_snapshot
        assert "current_price" not in valuation.input_snapshot["company"]
        assert "market_cap" not in valuation.input_snapshot["company"]
        assert decision.listing_id == listing.id
        assert decision.market_snapshot_id == market_snapshot.id
        assert decision.fx_rate_snapshot_id is None
        assert decision.valuation_currency == decision.trading_currency == "USD"
        assert decision.underlying_shares_per_listing_unit == 1.0
        assert decision.fx_rate == 1.0


def _seed_apple_research_contract(session, company: Company) -> None:
    analyst_run_ids: list[int] = []
    for profile in list_analyst_profiles():
        run = AnalysisRun(
            company_id=company.id,
            run_type="analyst_view",
            analyst_profile=profile.id,
            run_version="008_v1",
            model_name="fixture-model",
            prompt_version="analyst_view_v1",
            data_snapshot_hash=f"aapl-{profile.id}",
            input_snapshot={"reporting_currency": "USD"},
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
                        "financial_periods": ["2025FY"],
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
        data_snapshot_hash="aapl-memo",
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
            title="Apple 综合投资备忘录",
            conclusion="继续研究",
            sections={
                "valuation_assumption_queue": [
                    {
                        "assumption_type": "free_cash_flow_growth",
                        "reason": "以 SEC 现金流事实为估值基准并保持保守。",
                    }
                ],
                "key_risks": ["硬件周期和服务监管风险"],
                "counter_evidence": [],
                "data_gaps": [],
                "source_map": {
                    "financial_periods": ["2025FY"],
                    "filing_accessions": ["0000320193-26-000098"],
                },
            },
            markdown="Apple 离线固定样本研究备忘录。",
            source_analyst_run_ids=analyst_run_ids,
            source_snapshot_hash="aapl-memo",
            status="draft",
            is_latest=True,
        )
    )
    session.commit()
