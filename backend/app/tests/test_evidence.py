from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from app.analysis.model_gateway import ModelNotConfiguredError, ModelOutputValidationError
from app.data_sources.eastmoney_announcements import FetchedAnnouncement
from app.data_sources.web_search_provider import (
    AShareCompanyDisclosureSearchProvider,
    CompositeWebSearchProvider,
    SearchResult,
    WebSearchError,
)
from app.db.init_db import init_db
from app.db.models import AnalysisRun, Announcement, Company, Evidence
from app.db.session import create_sqlalchemy_engine, get_db
from app.main import create_app
from app.schemas.evidence import EvidenceImportTextRequest, EvidenceSearchRequest
from app.services.evidence_service import (
    _build_fallback_queries,
    _build_official_fallback_leads,
    _build_seed_source_leads,
    _default_fallback_search_provider,
    import_text_evidence,
    search_company_evidence,
)


def _make_test_db(tmp_path: Path):
    database_url = f"sqlite:///{(tmp_path / 'evidence.db').as_posix()}"
    engine = create_sqlalchemy_engine(database_url)
    init_db(engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def _override_db(app, session_factory) -> None:
    def override_get_db():
        with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db


def _get_company_id(client: TestClient, query: str) -> int:
    response = client.get("/api/companies", params={"q": query, "limit": 100})
    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] >= 1
    return int(payload["items"][0]["id"])


def test_import_text_evidence_creates_model_analyzed_evidence_and_history_run(
    tmp_path: Path,
) -> None:
    session_factory = _make_test_db(tmp_path)
    gateway = FakeManualImportGateway()

    with session_factory() as session:
        company = session.scalar(select(Company).where(Company.ticker == "600519.SH"))
        assert company is not None

        items, run = import_text_evidence(
            session,
            company,
            EvidenceImportTextRequest(
                title="白酒渠道监管访谈纪要",
                content=(
                    "市场监管公开材料显示，白酒渠道治理重点包括经销商价格秩序、"
                    "食品安全追溯和区域库存监测，这些事项会影响高端白酒企业的渠道管理。"
                ),
                source="manual_source",
                source_url="https://example.test/manual-evidence",
                published_at=datetime(2026, 8, 15, tzinfo=UTC),
                source_type="regulatory",
                notes="用户手动导入的外部公开材料摘录。",
            ),
            gateway=gateway,
        )

    assert run.status == "success"
    assert run.run_type == "evidence_import_text"
    assert run.input_snapshot["mode"] == "manual_text_import"
    assert run.result["created_evidence_count"] == 1
    assert run.result["diagnostics"]["mode"] == "manual_text_import"
    assert len(items) == 1
    assert items[0].analysis_status == "model_analyzed"
    assert items[0].requires_review is True
    assert items[0].source_url == "https://example.test/manual-evidence"
    assert items[0].raw_snapshot["import_mode"] == "manual_text_import"
    assert "用户手动导入文本生成" in (items[0].analysis_note or "")
    assert gateway.saw_manual_text is True


def test_import_text_evidence_without_source_url_caps_credibility_and_notes(
    tmp_path: Path,
) -> None:
    session_factory = _make_test_db(tmp_path)

    with session_factory() as session:
        company = session.scalar(select(Company).where(Company.ticker == "600519.SH"))
        assert company is not None

        items, _run = import_text_evidence(
            session,
            company,
            EvidenceImportTextRequest(
                title="白酒库存调研摘要",
                content="调研摘要显示部分区域渠道库存上升，经销商回款节奏放缓，需要继续复核来源。",
                source="manual_note",
            ),
            gateway=FakeManualImportGateway(),
        )

    assert len(items) == 1
    assert items[0].requires_review is True
    assert items[0].credibility_score == 0.6
    assert "缺少可复核来源链接" in (items[0].analysis_note or "")


def test_import_text_evidence_allows_shareholder_fact_from_report_quote(
    tmp_path: Path,
) -> None:
    session_factory = _make_test_db(tmp_path)
    gateway = FakeManualShareholderFactGateway()

    with session_factory() as session:
        company = session.scalar(select(Company).where(Company.ticker == "600519.SH"))
        assert company is not None

        items, run = import_text_evidence(
            session,
            company,
            EvidenceImportTextRequest(
                title="香港中央结算退出贵州茅台十大股东名单",
                content=(
                    "8月14日，贵州茅台披露2026年半年报。报告显示，截至期末，"
                    "香港中央结算有限公司已退出贵州茅台前十大股东名单；上一期末，"
                    "香港中央结算有限公司分别持有贵州茅台0.83%和0.32%股份，"
                    "为公司的第九和第十股东。"
                ),
                source="东方财富",
                source_url="https://finance.eastmoney.com/a/202608143842073818.html",
                published_at=datetime(2026, 8, 14, tzinfo=UTC),
                source_type="web",
            ),
            gateway=gateway,
        )

    assert run.status == "success"
    assert len(items) == 1
    assert items[0].analysis_status == "model_analyzed"
    assert items[0].requires_review is True
    assert items[0].price_sensitive is False
    assert "十大股东" in items[0].summary
    assert gateway.saw_shareholder_rule is True


def test_import_text_evidence_records_failed_run_when_model_is_not_configured(
    tmp_path: Path,
) -> None:
    session_factory = _make_test_db(tmp_path)

    with session_factory() as session:
        company = session.scalar(select(Company).where(Company.ticker == "600519.SH"))
        assert company is not None

        with pytest.raises(ModelNotConfiguredError):
            import_text_evidence(
                session,
                company,
                EvidenceImportTextRequest(
                    content="外部公开资料显示白酒行业监管政策持续关注食品安全和渠道秩序。"
                ),
                gateway=FakeUnconfiguredGateway(),
            )

        evidence_count = session.scalar(
            select(func.count()).select_from(Evidence).where(Evidence.company_id == company.id)
        )
        run = session.scalar(
            select(AnalysisRun)
            .where(
                AnalysisRun.company_id == company.id,
                AnalysisRun.run_type == "evidence_import_text",
            )
            .order_by(AnalysisRun.id.desc())
        )

    assert evidence_count == 0
    assert run is not None
    assert run.status == "failed"
    assert run.result["created_evidence_count"] == 0
    assert run.result["error_type"] == "ModelNotConfiguredError"


def test_import_text_evidence_does_not_store_price_sensitive_output(
    tmp_path: Path,
) -> None:
    session_factory = _make_test_db(tmp_path)

    with session_factory() as session:
        company = session.scalar(select(Company).where(Company.ticker == "600519.SH"))
        assert company is not None

        with pytest.raises(Exception, match="未入库"):
            import_text_evidence(
                session,
                company,
                EvidenceImportTextRequest(
                    content="文本主要讨论贵州茅台当前股价、目标价和短线交易评级。"
                ),
                gateway=FakeManualPriceSensitiveGateway(),
            )

        evidence_count = session.scalar(
            select(func.count()).select_from(Evidence).where(Evidence.company_id == company.id)
        )
        run = session.scalar(
            select(AnalysisRun)
            .where(
                AnalysisRun.company_id == company.id,
                AnalysisRun.run_type == "evidence_import_text",
            )
            .order_by(AnalysisRun.id.desc())
        )

    assert evidence_count == 0
    assert run is not None
    assert run.status == "failed"


def test_import_text_evidence_api_validates_required_content(tmp_path: Path) -> None:
    session_factory = _make_test_db(tmp_path)
    app = create_app(initialize_database=False)
    _override_db(app, session_factory)

    with TestClient(app) as client:
        company_id = _get_company_id(client, "贵州茅台")
        response = client.post(
            f"/api/companies/{company_id}/evidence/import-text",
            json={"title": "缺少正文"},
        )

    assert response.status_code == 422


def test_import_text_evidence_api_creates_evidence_and_refresh_payload(
    tmp_path: Path,
    monkeypatch,
) -> None:
    session_factory = _make_test_db(tmp_path)
    app = create_app(initialize_database=False)
    _override_db(app, session_factory)

    from app.api.routes import evidence as evidence_routes

    def fake_import_text_evidence(db, company, payload):
        return import_text_evidence(
            db,
            company,
            payload,
            gateway=FakeManualImportGateway(),
        )

    monkeypatch.setattr(evidence_routes, "import_text_evidence", fake_import_text_evidence)

    with TestClient(app) as client:
        company_id = _get_company_id(client, "贵州茅台")
        response = client.post(
            f"/api/companies/{company_id}/evidence/import-text",
            json={
                "title": "白酒渠道监管访谈纪要",
                "content": "公开材料显示白酒渠道监管关注食品安全追溯和经销商库存监测。",
                "source": "manual_source",
                "source_url": "https://example.test/manual-evidence",
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "success"
    assert payload["created"] == 1
    assert payload["items"][0]["analysis_status"] == "model_analyzed"
    assert payload["items"][0]["raw_snapshot"]["import_mode"] == "manual_text_import"
    assert payload["diagnostics"]["mode"] == "manual_text_import"


def test_evidence_search_returns_clear_error_when_model_is_not_configured(tmp_path: Path) -> None:
    session_factory = _make_test_db(tmp_path)

    with session_factory() as session:
        company = session.scalar(select(Company).where(Company.ticker == "600519.SH"))
        assert company is not None

        with pytest.raises(ModelNotConfiguredError, match="MODEL_BASE_URL"):
            search_company_evidence(
                session,
                company,
                EvidenceSearchRequest(keywords=["政策"], max_results=1),
                gateway=FakeUnconfiguredGateway(),
                search_provider=FakeSearchProvider(),
            )

        run = session.scalar(
            select(AnalysisRun)
            .where(AnalysisRun.company_id == company.id, AnalysisRun.run_type == "evidence_search")
            .order_by(AnalysisRun.id.desc())
        )

    assert run is not None
    assert run.status == "failed"
    assert run.result["error_type"] == "ModelNotConfiguredError"


def test_evidence_search_creates_evidence_and_history_run(tmp_path: Path) -> None:
    session_factory = _make_test_db(tmp_path)
    app = create_app(initialize_database=False)
    _override_db(app, session_factory)

    with TestClient(app) as client:
        company_id = _get_company_id(client, "贵州茅台")
        search_response = client.post(
            f"/api/companies/{company_id}/evidence/search",
            json={"keywords": ["白酒政策"], "max_results": 2},
        )
        list_response = client.get(f"/api/companies/{company_id}/evidence")

    assert search_response.status_code == 200
    payload = search_response.json()
    assert payload["status"] == "success"
    assert payload["created"] == 1
    assert payload["items"][0]["title"] == "白酒行业监管政策变化"
    assert payload["items"][0]["source_type"] == "policy"
    assert payload["items"][0]["impact_direction"] == "mixed"
    assert payload["items"][0]["importance_score"] == 0.82
    assert payload["items"][0]["requires_review"] is True
    assert payload["items"][0]["analysis_status"] == "model_analyzed"
    assert payload["items"][0]["analysis_note"] == "来源为政策页面，重要性较高。"
    assert payload["diagnostics"]["sent_to_model_count"] == 1
    assert payload["diagnostics"]["filtered_out_count"] == 0

    assert list_response.status_code == 200
    list_payload = list_response.json()
    assert list_payload["total"] == 1
    assert (
        list_payload["items"][0]["summary"]
        == "政策信息可能影响高端白酒渠道监管，需要后续复核原文。"
    )

    with session_factory() as session:
        run = session.get(AnalysisRun, payload["run_id"])
        evidence = session.get(Evidence, payload["items"][0]["id"])

    assert run is not None
    assert run.status == "success"
    assert run.model_name == "fake-model"
    assert run.prompt_version == "evidence_search_v1"
    assert run.result["created_evidence_count"] == 1
    assert "贵州茅台 白酒政策" in run.result["queries"]
    assert "贵州茅台 政策 监管 公开数据" in run.result["queries"]
    assert evidence is not None
    assert evidence.raw_snapshot["query"] == "贵州茅台 白酒政策"


def test_evidence_review_marks_item_as_reviewed(tmp_path: Path) -> None:
    session_factory = _make_test_db(tmp_path)
    app = create_app(initialize_database=False)
    _override_db(app, session_factory)

    with session_factory() as session:
        company = session.scalar(select(Company).where(Company.ticker == "600519.SH"))
        assert company is not None
        evidence = Evidence(
            company_id=company.id,
            source_type="web",
            title="待复核证据",
            summary="需要人工确认。",
            key_facts=[],
            impact_direction="unknown",
            importance_score=0.4,
            credibility_score=0.4,
            tags=[],
            requires_review=True,
            analysis_status="search_lead",
            analysis_note="手动创建的待复核搜索线索。",
            raw_snapshot={},
        )
        session.add(evidence)
        session.commit()
        evidence_id = evidence.id

    with TestClient(app) as client:
        response = client.post(f"/api/evidence/{evidence_id}/review")

    assert response.status_code == 200
    payload = response.json()
    assert payload["evidence"]["requires_review"] is False


def test_evidence_delete_removes_item(tmp_path: Path) -> None:
    session_factory = _make_test_db(tmp_path)
    app = create_app(initialize_database=False)
    _override_db(app, session_factory)

    with session_factory() as session:
        company = session.scalar(select(Company).where(Company.ticker == "600519.SH"))
        assert company is not None
        evidence = Evidence(
            company_id=company.id,
            source_type="web",
            title="无关搜索线索",
            summary="用户决定删除的外部信息。",
            key_facts=[],
            impact_direction="unknown",
            importance_score=0.2,
            credibility_score=0.2,
            tags=["无关"],
            requires_review=True,
            analysis_status="search_lead",
            analysis_note="与当前公司基本面无关。",
            raw_snapshot={},
        )
        session.add(evidence)
        session.commit()
        evidence_id = evidence.id
        company_id = company.id

    with TestClient(app) as client:
        delete_response = client.delete(f"/api/evidence/{evidence_id}")
        detail_response = client.get(f"/api/evidence/{evidence_id}")
        list_response = client.get(f"/api/companies/{company_id}/evidence")

    assert delete_response.status_code == 200
    assert delete_response.json() == {"id": evidence_id, "deleted": True}
    assert detail_response.status_code == 404
    assert list_response.status_code == 200
    assert list_response.json()["total"] == 0


def test_evidence_delete_returns_404_for_missing_item(tmp_path: Path) -> None:
    session_factory = _make_test_db(tmp_path)
    app = create_app(initialize_database=False)
    _override_db(app, session_factory)

    with TestClient(app) as client:
        response = client.delete("/api/evidence/999999")

    assert response.status_code == 404
    assert response.json()["detail"] == "Evidence not found"


def test_model_json_validation_failure_is_recorded(tmp_path: Path) -> None:
    session_factory = _make_test_db(tmp_path)

    with session_factory() as session:
        company = session.scalar(select(Company).where(Company.ticker == "600519.SH"))
        assert company is not None

        items, run = search_company_evidence(
            session,
            company,
            EvidenceSearchRequest(keywords=[], max_results=1),
            gateway=FakeInvalidJsonGateway(),
            search_provider=FakeSearchProvider(),
        )

        assert len(items) == 1

    assert run is not None
    assert run.status == "partial"
    assert "fallback_reason" in run.result
    assert items[0].requires_review is True
    assert items[0].analysis_status == "search_lead"
    assert items[0].analysis_note is not None
    assert items[0].raw_snapshot["title"] == "白酒行业监管政策变化"


def test_evidence_search_passes_page_snapshot_to_model(tmp_path: Path) -> None:
    session_factory = _make_test_db(tmp_path)
    gateway = FakePageAwareGateway()

    with session_factory() as session:
        company = session.scalar(select(Company).where(Company.ticker == "600519.SH"))
        assert company is not None

        items, run = search_company_evidence(
            session,
            company,
            EvidenceSearchRequest(keywords=["渠道监管"], max_results=1),
            gateway=gateway,
            search_provider=FakeSearchProvider(),
            page_fetcher=FakePageSnapshotFetcher(),
        )

    assert run.status == "success"
    assert len(items) == 1
    assert items[0].raw_snapshot["page_snapshot"]["content_excerpt"] == "网页正文显示渠道监管要求。"
    assert gateway.saw_page_snapshot is True


def test_evidence_search_filters_market_and_technical_results(tmp_path: Path) -> None:
    session_factory = _make_test_db(tmp_path)
    gateway = FakeFilterAwareGateway()

    with session_factory() as session:
        company = session.scalar(select(Company).where(Company.ticker == "600519.SH"))
        assert company is not None

        items, run = search_company_evidence(
            session,
            company,
            EvidenceSearchRequest(keywords=["政策"], max_results=3),
            gateway=gateway,
            search_provider=FakeMixedSearchProvider(),
        )

    assert run.status == "success"
    assert run.result["filtered_out_count"] == 2
    assert len(items) == 1
    assert gateway.seen_titles == ["贵州茅台 食品安全监管公开信息"]


def test_evidence_search_filters_generic_entries_and_keeps_substantive_results(
    tmp_path: Path,
) -> None:
    session_factory = _make_test_db(tmp_path)
    gateway = FakeSubstantiveCandidateGateway()
    search_provider = FakeManySearchProvider()

    with session_factory() as session:
        company = session.scalar(select(Company).where(Company.ticker == "600519.SH"))
        assert company is not None

        items, run = search_company_evidence(
            session,
            company,
            EvidenceSearchRequest(keywords=["政策"], max_results=2),
            gateway=gateway,
            search_provider=search_provider,
        )

    assert run.status == "success"
    assert len(items) == 4
    assert gateway.seen_titles == [
        "白酒行业政策解读 1",
        "白酒行业政策解读 2",
        "白酒行业政策解读 3",
        "白酒行业政策解读 4",
    ]
    assert "000858.SZ 深交所上市公司公告检索入口" not in gateway.seen_titles
    assert search_provider.search_calls > 1


def test_evidence_search_drops_model_price_sensitive_evidence(tmp_path: Path) -> None:
    session_factory = _make_test_db(tmp_path)

    with session_factory() as session:
        company = session.scalar(select(Company).where(Company.ticker == "600519.SH"))
        assert company is not None

        items, run = search_company_evidence(
            session,
            company,
            EvidenceSearchRequest(keywords=["政策"], max_results=1),
            gateway=FakePriceSensitiveEvidenceGateway(),
            search_provider=FakeSearchProvider(),
        )
        evidence_count = session.scalar(
            select(func.count()).select_from(Evidence).where(Evidence.company_id == company.id)
        )

    assert run.status == "success"
    assert items == []
    assert run.result["created_evidence_count"] == 0
    assert evidence_count == 0


def test_evidence_search_limits_created_evidence_to_ten(tmp_path: Path) -> None:
    session_factory = _make_test_db(tmp_path)

    with session_factory() as session:
        company = session.scalar(select(Company).where(Company.ticker == "600519.SH"))
        assert company is not None

        items, run = search_company_evidence(
            session,
            company,
            EvidenceSearchRequest(keywords=["政策"], max_results=10),
            gateway=FakeManyEvidenceGateway(),
            search_provider=FakeSearchProvider(),
        )

    assert run.status == "success"
    assert len(items) == 10
    assert run.result["created_evidence_count"] == 10


def test_evidence_search_drops_company_disclosure_duplicate_outputs(tmp_path: Path) -> None:
    session_factory = _make_test_db(tmp_path)

    with session_factory() as session:
        company = session.scalar(select(Company).where(Company.ticker == "600519.SH"))
        assert company is not None

        items, run = search_company_evidence(
            session,
            company,
            EvidenceSearchRequest(keywords=["政策"], max_results=1),
            gateway=FakeCompanyDisclosureDuplicateGateway(),
            search_provider=FakeSearchProvider(),
        )
        evidence_count = session.scalar(
            select(func.count()).select_from(Evidence).where(Evidence.company_id == company.id)
        )

    assert run.status == "success"
    assert items == []
    assert run.result["created_evidence_count"] == 0
    assert evidence_count == 0


def test_composite_search_provider_merges_multiple_sources() -> None:
    provider = CompositeWebSearchProvider(
        providers=[
            FakeStaticSearchProvider(
                [
                    SearchResult(
                        query="",
                        title="第一来源低价值首页",
                        url="https://example.test/home",
                        source="example.test",
                        snippet="公司首页。",
                    )
                ]
            ),
            FakeStaticSearchProvider(
                [
                    SearchResult(
                        query="",
                        title="第二来源白酒行业供需公开数据",
                        url="https://news.example.test/liquor-supply",
                        source="news.example.test",
                        snippet="统计数据显示白酒行业产量和渠道库存变化。",
                    )
                ]
            ),
        ]
    )

    results = provider.search("白酒 行业 供需", limit=5)

    assert [result.title for result in results] == [
        "第一来源低价值首页",
        "第二来源白酒行业供需公开数据",
    ]
    assert provider.last_provider_stats == [
        {
            "provider": "FakeStaticSearchProvider",
            "status": "success",
            "result_count": 1,
        },
        {
            "provider": "FakeStaticSearchProvider",
            "status": "success",
            "result_count": 1,
        },
    ]


def test_a_share_company_disclosure_provider_returns_specific_filings() -> None:
    provider = AShareCompanyDisclosureSearchProvider(client=FakeDisclosureClient())

    results = provider.search("五粮液 000858 年报 公告 公开披露", limit=5)

    assert [result.title for result in results] == [
        "五粮液股份有限公司2025年年度报告",
        "关于收到深圳证券交易所监管函的公告",
    ]
    assert results[0].url == "https://data.eastmoney.com/notices/detail/000858/1.html"
    assert "公司公开披露文件" in (results[0].snippet or "")


def test_evidence_search_keeps_substantive_non_official_fundamental_news(
    tmp_path: Path,
) -> None:
    session_factory = _make_test_db(tmp_path)
    gateway = FakeSubstantiveCandidateGateway()

    with session_factory() as session:
        company = session.scalar(select(Company).where(Company.ticker == "600519.SH"))
        assert company is not None

        items, run = search_company_evidence(
            session,
            company,
            EvidenceSearchRequest(keywords=["白酒"], max_results=3),
            gateway=gateway,
            search_provider=FakeNonOfficialFundamentalSearchProvider(),
        )

    assert run.status == "success"
    assert len(items) == 1
    assert gateway.seen_titles == ["白酒行业供需公开数据跟踪"]
    assert run.result["search_stats"]["filtered_out_by_reason"]["price_sensitive"] == 1
    assert run.result["search_stats"]["sent_to_model_count"] == 1


def test_evidence_search_filters_financial_report_content_even_from_secondary_sources(
    tmp_path: Path,
) -> None:
    session_factory = _make_test_db(tmp_path)
    gateway = FakeSubstantiveCandidateGateway()

    with session_factory() as session:
        company = session.scalar(select(Company).where(Company.ticker == "600519.SH"))
        assert company is not None

        with pytest.raises(Exception, match="搜索源返回了结果，但均被过滤"):
            search_company_evidence(
                session,
                company,
                EvidenceSearchRequest(keywords=["年报"], max_results=3),
                gateway=gateway,
                search_provider=FakeSecondarySourceFundamentalSearchProvider(),
            )

        run = session.scalar(
            select(AnalysisRun)
            .where(AnalysisRun.company_id == company.id, AnalysisRun.run_type == "evidence_search")
            .order_by(AnalysisRun.id.desc())
        )

    assert run is not None
    assert run.status == "failed"
    assert run.result["search_stats"]["sent_to_model_count"] == 0
    assert run.result["search_stats"]["filtered_out_by_reason"]["company_disclosure_duplicate"] == 1


def test_evidence_search_triggers_a_share_fallback_when_primary_results_are_filtered(
    tmp_path: Path,
) -> None:
    session_factory = _make_test_db(tmp_path)
    gateway = FakeSubstantiveCandidateGateway()

    with session_factory() as session:
        company = session.scalar(select(Company).where(Company.ticker == "600519.SH"))
        assert company is not None

        items, run = search_company_evidence(
            session,
            company,
            EvidenceSearchRequest(keywords=["政策"], max_results=5),
            gateway=gateway,
            search_provider=FakeOnlyPriceSearchProvider(),
            fallback_search_provider=AShareCompanyDisclosureSearchProvider(
                client=FakeMoutaiDisclosureClient()
            ),
        )

    assert run.status == "success"
    assert len(items) == 1
    assert gateway.seen_titles == ["贵州茅台关于收到上海证券交易所监管函的公告"]
    assert run.result["search_stats"]["fallback_triggered"] is True
    assert run.result["search_stats"]["fallback_stage"] == "a_share_disclosure"
    assert run.result["search_stats"]["fallback_candidate_count"] == 1
    assert run.result["search_stats"]["filtered_out_by_reason"]["price_sensitive"] > 0
    assert run.result["search_stats"]["filtered_out_by_reason"]["company_disclosure_duplicate"] >= 2
    assert not any("年度报告" in title for title in gateway.seen_titles)
    assert not any("利润分配" in title for title in gateway.seen_titles)


def test_evidence_search_uses_fallback_when_primary_provider_fails_for_a_share(
    tmp_path: Path,
) -> None:
    session_factory = _make_test_db(tmp_path)
    gateway = FakeSubstantiveCandidateGateway()

    with session_factory() as session:
        company = session.scalar(select(Company).where(Company.ticker == "600519.SH"))
        assert company is not None

        items, run = search_company_evidence(
            session,
            company,
            EvidenceSearchRequest(keywords=["监管"], max_results=5),
            gateway=gateway,
            search_provider=FakeFailingSearchProvider(),
            fallback_search_provider=AShareCompanyDisclosureSearchProvider(
                client=FakeMoutaiDisclosureClient()
            ),
        )

    assert run.status == "success"
    assert len(items) == 1
    assert run.result["search_stats"]["fallback_triggered"] is True
    assert run.result["search_stats"]["fallback_stage"] == "a_share_disclosure"
    assert run.result["search_stats"]["query_errors"]
    assert "贵州茅台 600519 监管函 问询函 site:sse.com.cn" in run.result["queries"]


@pytest.mark.parametrize(
    ("ticker", "expected_domains"),
    [
        ("00700.HK", {"hkexnews.hk", "sfc.hk", "censtatd.gov.hk"}),
        ("AAPL.US", {"sec.gov", "bea.gov", "bls.gov", "census.gov"}),
    ],
)
def test_non_a_share_evidence_fallback_uses_market_official_sources_only(
    tmp_path: Path, ticker: str, expected_domains: set[str]
) -> None:
    session_factory = _make_test_db(tmp_path)
    with session_factory() as session:
        company = session.scalar(select(Company).where(Company.ticker == ticker))
        assert company is not None
        queries = _build_fallback_queries(company, ["监管"])
        leads = _build_official_fallback_leads(company, ["监管"])
        seed_leads = _build_seed_source_leads(company, ["监管"])
        provider = _default_fallback_search_provider(
            company=company,
            provider=FakeEmptySearchProvider(),
            search_provider_was_injected=False,
        )

    combined = " ".join(
        [*queries]
        + [str(item.get("url") or "") for item in leads]
        + [str(item.get("url") or "") for item in seed_leads]
    ).lower()
    assert any(domain in combined for domain in expected_domains)
    assert "sse.com.cn" not in combined
    assert "cninfo.com.cn" not in combined
    assert provider is not None
    assert isinstance(provider, CompositeWebSearchProvider)
    assert not any(
        isinstance(item, AShareCompanyDisclosureSearchProvider)
        for item in provider.providers
    )


def test_evidence_search_creates_official_search_leads_when_fallback_has_no_candidates(
    tmp_path: Path,
) -> None:
    session_factory = _make_test_db(tmp_path)

    with session_factory() as session:
        company = session.scalar(select(Company).where(Company.ticker == "600519.SH"))
        assert company is not None

        items, run = search_company_evidence(
            session,
            company,
            EvidenceSearchRequest(keywords=["监管"], max_results=5),
            gateway=FakeQueryOnlyGateway(),
            search_provider=FakeOnlyPriceSearchProvider(),
            fallback_search_provider=FakeEmptySearchProvider(),
        )

    assert run.status == "partial"
    assert len(items) >= 3
    assert all(item.analysis_status == "search_lead" for item in items)
    assert all(item.requires_review is True for item in items)
    assert run.result["created_evidence_count"] == len(items)
    assert run.result["search_stats"]["fallback_triggered"] is True
    assert run.result["search_stats"]["fallback_stage"] == "seed_source"
    assert run.result["search_stats"]["fallback_candidate_count"] >= len(items)
    assert run.result["search_stats"]["seed_source_lead_count"] >= len(items)
    assert run.result["search_stats"]["local_announcement_lead_count"] == 0
    assert run.result["search_stats"]["final_search_lead_count"] == 0
    assert run.result["search_stats"]["fallback_queries"]
    assert "官方种子源" in (items[0].analysis_note or "")


def test_evidence_search_creates_wuliangye_local_announcement_search_leads(
    tmp_path: Path,
) -> None:
    session_factory = _make_test_db(tmp_path)

    with session_factory() as session:
        company = session.scalar(select(Company).where(Company.ticker == "000858.SZ"))
        assert company is not None
        session.add_all(
            [
                Announcement(
                    company_id=company.id,
                    title="五粮液2025年年度报告",
                    published_at=datetime(2026, 7, 1, tzinfo=UTC),
                    category="定期报告",
                    content=None,
                    raw_content=None,
                    summary="公司年度报告，属于 005/006 已覆盖的常规公告。",
                    key_facts=["年度报告"],
                    source="巨潮资讯",
                    source_url="https://example.test/wly-annual-report",
                    raw_url="https://example.test/wly-annual-report/raw",
                    risk_tips=[],
                    review_questions=[],
                    tags=["年报"],
                ),
                Announcement(
                    company_id=company.id,
                    title="关于召开2026年第一次临时股东大会的通知",
                    published_at=datetime(2026, 7, 2, tzinfo=UTC),
                    category="临时公告",
                    content=None,
                    raw_content=None,
                    summary="股东大会通知，属于公告区重复内容。",
                    key_facts=["股东大会"],
                    source="巨潮资讯",
                    source_url="https://example.test/wly-shareholder-meeting",
                    raw_url="https://example.test/wly-shareholder-meeting/raw",
                    risk_tips=[],
                    review_questions=[],
                    tags=["股东大会"],
                ),
                Announcement(
                    company_id=company.id,
                    title=(
                        "北京中伦(成都)律师事务所关于宜宾五粮液股份有限公司"
                        "2025年度股东会的法律意见书"
                    ),
                    published_at=datetime(2026, 7, 2, 12, tzinfo=UTC),
                    category="临时公告",
                    content=None,
                    raw_content=None,
                    summary="律师事务所就股东会召集、召开程序和表决程序发表法律意见。",
                    key_facts=["股东会", "法律意见书"],
                    source="eastmoney_announcements",
                    source_url="https://example.test/wly-legal-opinion",
                    raw_url="https://example.test/wly-legal-opinion/raw",
                    risk_tips=[],
                    review_questions=[],
                    tags=["股东会", "法律意见书"],
                ),
                Announcement(
                    company_id=company.id,
                    title="关于收到监管工作函并完成整改的公告",
                    published_at=datetime(2026, 7, 3, tzinfo=UTC),
                    category="临时公告",
                    content=None,
                    raw_content=None,
                    summary="公司收到监管工作函并披露整改措施，需要追溯原文复核。",
                    key_facts=["监管工作函", "整改措施"],
                    source="巨潮资讯",
                    source_url="https://example.test/wly-regulatory-letter",
                    raw_url="https://example.test/wly-regulatory-letter/raw",
                    risk_tips=["监管要求落实风险"],
                    review_questions=["整改是否影响渠道和合规成本"],
                    tags=["监管", "整改"],
                ),
            ]
        )
        session.flush()

        items, run = search_company_evidence(
            session,
            company,
            EvidenceSearchRequest(keywords=["食品安全"], max_results=5),
            gateway=FakeQueryOnlyGateway(),
            search_provider=FakeWuliangyeOnlyPriceSearchProvider(),
            fallback_search_provider=FakeEmptySearchProvider(),
        )

    titles = [item.title for item in items]
    assert run.status == "partial"
    assert len(items) >= 1
    assert any("监管工作函" in title for title in titles)
    assert not any("本地公告追溯线索" in title for title in titles)
    assert not any("年度报告" in title for title in titles)
    assert not any("股东大会" in title for title in titles)
    assert not any("法律意见书" in title for title in titles)
    assert all(item.analysis_status == "search_lead" for item in items)
    assert all(item.requires_review is True for item in items)
    assert all(item.impact_direction == "unknown" for item in items)
    assert run.result["search_stats"]["fallback_triggered"] is True
    assert run.result["search_stats"]["fallback_stage"] == "local_announcement"
    assert run.result["search_stats"]["local_announcement_lead_count"] == 1
    assert run.result["search_stats"]["seed_source_lead_count"] > 0
    assert run.result["search_stats"]["fallback_candidate_count"] >= len(items)
    assert run.result["search_stats"]["no_candidate_reason"] == "all_filtered"


def test_evidence_search_analyzes_local_announcement_lead_when_body_is_read(
    tmp_path: Path,
) -> None:
    session_factory = _make_test_db(tmp_path)
    gateway = FakeAnnouncementBodyAwareGateway()
    content_fetcher = FakeAnnouncementContentFetcher(
        "监管正文显示公司收到监管工作函，并承诺在三十日内完成渠道整改和信息披露整改。"
    )

    with session_factory() as session:
        company = session.scalar(select(Company).where(Company.ticker == "000858.SZ"))
        assert company is not None
        session.add(
            Announcement(
                company_id=company.id,
                title="关于收到监管工作函并完成整改的公告",
                published_at=datetime(2026, 7, 3, tzinfo=UTC),
                category="临时公告",
                content=None,
                raw_content=None,
                summary="公司收到监管工作函并披露整改措施，需要追溯原文复核。",
                key_facts=["监管工作函", "整改措施"],
                source="eastmoney_announcements",
                source_url="https://data.eastmoney.com/notices/detail/000858/ANBODY.html",
                raw_url="https://pdf.dfcfw.com/pdf/H2_ANBODY_1.pdf",
                risk_tips=["监管要求落实风险"],
                review_questions=["整改是否影响渠道和合规成本"],
                tags=["监管", "整改"],
            )
        )
        session.flush()

        items, run = search_company_evidence(
            session,
            company,
            EvidenceSearchRequest(keywords=["食品安全"], max_results=5),
            gateway=gateway,
            search_provider=FakeWuliangyeOnlyPriceSearchProvider(),
            fallback_search_provider=FakeEmptySearchProvider(),
            announcement_content_fetcher=content_fetcher,
        )

    assert run.status == "success"
    assert len(items) == 1
    assert items[0].analysis_status == "model_analyzed"
    assert items[0].source_type == "regulatory"
    assert gateway.saw_announcement_body is True
    assert content_fetcher.calls == [
        (
            "https://data.eastmoney.com/notices/detail/000858/ANBODY.html",
            "https://pdf.dfcfw.com/pdf/H2_ANBODY_1.pdf",
        )
    ]
    assert run.result["search_stats"]["fallback_stage"] == "local_announcement"
    assert run.result["search_stats"]["sent_to_model_count"] == 1
    assert run.result["search_stats"]["deterministic_model_candidate_count"] == 1


def test_evidence_search_creates_wuliangye_seed_source_leads_without_local_announcements(
    tmp_path: Path,
) -> None:
    session_factory = _make_test_db(tmp_path)

    with session_factory() as session:
        company = session.scalar(select(Company).where(Company.ticker == "000858.SZ"))
        assert company is not None

        items, run = search_company_evidence(
            session,
            company,
            EvidenceSearchRequest(keywords=["渠道库存"], max_results=5),
            gateway=FakeQueryOnlyGateway(),
            search_provider=FakeWuliangyeOnlyPriceSearchProvider(),
            fallback_search_provider=FakeEmptySearchProvider(),
        )

    assert run.status == "partial"
    assert len(items) >= 3
    assert all(item.analysis_status == "search_lead" for item in items)
    assert all(item.requires_review is True for item in items)
    assert any(
        term in item.title
        for item in items
        for term in ("五粮液集团", "宜宾五粮液", "浓香型白酒", "白酒")
    )
    assert run.result["search_stats"]["fallback_triggered"] is True
    assert run.result["search_stats"]["fallback_stage"] == "seed_source"
    assert run.result["search_stats"]["seed_source_lead_count"] >= len(items)
    assert run.result["search_stats"]["local_announcement_lead_count"] == 0
    assert run.result["search_stats"]["fallback_candidate_count"] >= len(items)
    assert run.result["search_stats"]["fallback_queries"]


def test_evidence_search_error_distinguishes_provider_no_result(
    tmp_path: Path,
) -> None:
    session_factory = _make_test_db(tmp_path)

    with session_factory() as session:
        company = session.scalar(select(Company).where(Company.ticker == "600519.SH"))
        assert company is not None

        with pytest.raises(Exception, match="外部搜索源暂未返回可用结果"):
            search_company_evidence(
                session,
                company,
                EvidenceSearchRequest(keywords=["政策"], max_results=3),
                gateway=FakeQueryOnlyGateway(),
                search_provider=FakeEmptySearchProvider(),
            )

        run = session.scalar(
            select(AnalysisRun)
            .where(AnalysisRun.company_id == company.id, AnalysisRun.run_type == "evidence_search")
            .order_by(AnalysisRun.id.desc())
        )

    assert run is not None
    assert run.status == "failed"
    assert run.result["search_stats"]["provider_result_count"] == 0
    assert run.result["search_stats"]["no_candidate_reason"] == "provider_no_result"
    assert run.result["search_stats"]["fallback_triggered"] is False


def test_evidence_search_records_filter_diagnostics_when_no_candidates(
    tmp_path: Path,
) -> None:
    session_factory = _make_test_db(tmp_path)

    with session_factory() as session:
        company = session.scalar(select(Company).where(Company.ticker == "600519.SH"))
        assert company is not None

        with pytest.raises(Exception, match="搜索源返回了结果，但均被过滤"):
            search_company_evidence(
                session,
                company,
                EvidenceSearchRequest(keywords=["政策"], max_results=3),
                gateway=FakeQueryOnlyGateway(),
                search_provider=FakeOnlyFilteredSearchProvider(),
            )

        run = session.scalar(
            select(AnalysisRun)
            .where(AnalysisRun.company_id == company.id, AnalysisRun.run_type == "evidence_search")
            .order_by(AnalysisRun.id.desc())
        )

    assert run is not None
    assert run.status == "failed"
    assert run.result["error_type"] == "EvidenceSearchError"
    assert run.result["search_stats"]["deduped_result_count"] == 3
    assert run.result["search_stats"]["filtered_out_by_reason"]["generic_entry"] == 1
    assert run.result["search_stats"]["filtered_out_by_reason"]["price_sensitive"] == 1
    assert run.result["search_stats"]["filtered_out_by_reason"]["not_fundamental"] == 1
    assert run.result["search_stats"]["no_candidate_reason"] == "all_filtered"
    assert run.result["search_stats"]["fallback_stage"] is None
    assert run.result["search_stats"]["fallback_queries"] == []
    assert run.result["search_stats"]["local_announcement_lead_count"] == 0
    assert run.result["search_stats"]["seed_source_lead_count"] == 0
    assert run.result["search_stats"]["final_search_lead_count"] == 0


def test_model_config_status_does_not_expose_api_key(tmp_path: Path, monkeypatch) -> None:
    session_factory = _make_test_db(tmp_path)
    app = create_app(initialize_database=False)
    _override_db(app, session_factory)

    from app.api.routes import evidence as evidence_routes

    monkeypatch.setattr(
        evidence_routes,
        "get_model_config_status",
        lambda: {
            "provider": "openai_compatible",
            "base_url": "https://api.deepseek.com",
            "model_name": "fake-model",
            "wire_api": "chat_completions",
            "api_key_configured": True,
        },
    )

    with TestClient(app) as client:
        response = client.get("/api/evidence/model-config")

    assert response.status_code == 200
    payload = response.json()
    assert payload["provider"] == "openai_compatible"
    assert payload["base_url"] == "https://api.deepseek.com"
    assert payload["model_name"] == "fake-model"
    assert payload["wire_api"] == "chat_completions"
    assert payload["api_key_configured"] is True
    assert "api_key" not in payload


def test_model_smoke_test_returns_gateway_status(tmp_path: Path, monkeypatch) -> None:
    session_factory = _make_test_db(tmp_path)
    app = create_app(initialize_database=False)
    _override_db(app, session_factory)

    from app.api.routes import evidence as evidence_routes

    monkeypatch.setattr(
        evidence_routes,
        "run_model_smoke_test",
        lambda: {
            "provider": "openai_compatible",
            "base_url": "https://api.deepseek.com",
            "model_name": "deepseek-v4-pro",
            "wire_api": "chat_completions",
            "api_key_configured": True,
            "ok": True,
            "message": "model gateway ok",
        },
    )

    with TestClient(app) as client:
        response = client.post("/api/evidence/model-smoke-test")

    assert response.status_code == 200
    payload = response.json()
    assert payload["provider"] == "openai_compatible"
    assert payload["base_url"] == "https://api.deepseek.com"
    assert payload["model_name"] == "deepseek-v4-pro"
    assert payload["wire_api"] == "chat_completions"
    assert payload["api_key_configured"] is True
    assert payload["ok"] is True
    assert payload["message"] == "model gateway ok"
    assert "api_key" not in payload


def test_model_smoke_test_returns_clear_error_when_not_configured(
    tmp_path: Path, monkeypatch
) -> None:
    session_factory = _make_test_db(tmp_path)
    app = create_app(initialize_database=False)
    _override_db(app, session_factory)

    from app.api.routes import evidence as evidence_routes

    def fake_smoke_test():
        raise ModelNotConfiguredError("模型未配置，请先在 .env 中设置：MODEL_API_KEY")

    monkeypatch.setattr(evidence_routes, "run_model_smoke_test", fake_smoke_test)

    with TestClient(app) as client:
        response = client.post("/api/evidence/model-smoke-test")

    assert response.status_code == 400
    assert response.json()["detail"] == "模型未配置，请先在 .env 中设置：MODEL_API_KEY"


class FakeUnconfiguredGateway:
    model_name = None

    def generate_structured(self, **kwargs):
        raise ModelNotConfiguredError(
            "模型未配置，请先在 .env 中设置：MODEL_BASE_URL, MODEL_API_KEY, MODEL_NAME"
        )


class FakeInvalidJsonGateway:
    model_name = "fake-model"

    def __init__(self) -> None:
        self.calls = 0

    def generate_structured(self, **kwargs):
        self.calls += 1
        if self.calls == 1:
            schema = kwargs["schema"]
            return schema.model_validate({"queries": ["贵州茅台 白酒政策"]})
        raise ModelOutputValidationError("模型返回内容不是合法 JSON")


class FakeSearchProvider:
    def search(self, query: str, limit: int = 5) -> list[SearchResult]:
        return [
            SearchResult(
                query=query,
                title="白酒行业监管政策变化",
                url="https://example.test/policy",
                source="example.test",
                snippet="政策信息可能影响高端白酒渠道监管。",
                published_at="2026-08-01T00:00:00Z",
            )
        ]


class FakeStaticSearchProvider:
    def __init__(self, results: list[SearchResult]) -> None:
        self.results = results

    def search(self, query: str, limit: int = 5) -> list[SearchResult]:
        return [
            SearchResult(
                query=query,
                title=result.title,
                url=result.url,
                source=result.source,
                snippet=result.snippet,
                published_at=result.published_at,
            )
            for result in self.results[:limit]
        ]


class FakeMixedSearchProvider:
    def search(self, query: str, limit: int = 5) -> list[SearchResult]:
        return [
            SearchResult(
                query=query,
                title="贵州茅台 K线技术分析 MACD",
                url="https://quote.eastmoney.com/sh600519.html",
                source="quote.eastmoney.com",
                snippet="股票行情走势和技术指标。",
            ),
            SearchResult(
                query=query,
                title="贵州茅台 股吧 短线资金流向",
                url="https://guba.eastmoney.com/list,600519.html",
                source="guba.eastmoney.com",
                snippet="股吧讨论和主力资金流向。",
            ),
            SearchResult(
                query=query,
                title="贵州茅台 食品安全监管公开信息",
                url="https://www.cninfo.com.cn/new/disclosure/detail",
                source="www.cninfo.com.cn",
                snippet="监管公开信息涉及食品安全与合规要求，可用于复核原始监管文件。",
            ),
        ]


class FakeManySearchProvider:
    def __init__(self) -> None:
        self.search_calls = 0

    def search(self, query: str, limit: int = 5) -> list[SearchResult]:
        self.search_calls += 1
        entry_result = SearchResult(
            query=query,
            title="000858.SZ 深交所上市公司公告检索入口",
            url="https://www.szse.cn/disclosure/listed/notice/index.html",
            source="www.szse.cn",
            snippet="深圳证券交易所上市公司公告检索入口，用于复核公司公告、定期报告和重大事项披露原文。",
        )
        substantive_results = [
            SearchResult(
                query=query,
                title=f"白酒行业政策解读 {index}",
                url=f"https://example.test/liquor-policy-{index}",
                source="example.test",
                snippet="政策信息和行业供需数据可能影响高端白酒企业经营，需要复核原文。",
            )
            for index in range(1, 5)
        ]
        return [entry_result, *substantive_results]


class FakeNonOfficialFundamentalSearchProvider:
    def search(self, query: str, limit: int = 5) -> list[SearchResult]:
        return [
            SearchResult(
                query=query,
                title="白酒行业供需公开数据跟踪",
                url="https://news.example.test/liquor-supply-data",
                source="news.example.test",
                snippet="公开统计数据显示白酒行业产量、渠道库存和消费需求变化。",
            ),
            SearchResult(
                query=query,
                title="贵州茅台 目标价和投资评级更新",
                url="https://news.example.test/price-target",
                source="news.example.test",
                snippet="内容主要讨论目标价、投资评级和短期市场情绪。",
            ),
        ]


class FakeOnlyPriceSearchProvider:
    def search(self, query: str, limit: int = 5) -> list[SearchResult]:
        return [
            SearchResult(
                query=query,
                title="贵州茅台 当前股价和目标价",
                url="https://quote.eastmoney.com/sh600519.html",
                source="quote.eastmoney.com",
                snippet="股票行情、实时股价、五档盘口和目标价。",
            ),
            SearchResult(
                query=query,
                title="贵州茅台 股吧 短线资金流向",
                url="https://guba.eastmoney.com/list,600519.html",
                source="guba.eastmoney.com",
                snippet="股吧讨论、主力资金流向和短线市场情绪。",
            ),
        ][:limit]


class FakeWuliangyeOnlyPriceSearchProvider:
    def search(self, query: str, limit: int = 5) -> list[SearchResult]:
        return [
            SearchResult(
                query=query,
                title="五粮液 当前股价和目标价",
                url="https://quote.eastmoney.com/sz000858.html",
                source="quote.eastmoney.com",
                snippet="股票行情、实时股价、五档盘口和目标价。",
            ),
            SearchResult(
                query=query,
                title="五粮液 股吧 短线资金流向",
                url="https://guba.eastmoney.com/list,000858.html",
                source="guba.eastmoney.com",
                snippet="股吧讨论、主力资金流向和短线市场情绪。",
            ),
        ][:limit]


class FakeFailingSearchProvider:
    def search(self, query: str, limit: int = 5) -> list[SearchResult]:
        raise WebSearchError("搜索源连接被重置")


class FakeEmptySearchProvider:
    def search(self, query: str, limit: int = 5) -> list[SearchResult]:
        return []


class FakeSecondarySourceFundamentalSearchProvider:
    def search(self, query: str, limit: int = 5) -> list[SearchResult]:
        return [
            SearchResult(
                query=query,
                title="雪球长文整理：贵州茅台年报披露经营数据",
                url="https://xueqiu.com/example/fundamental-article",
                source="xueqiu.com",
                snippet="文章引用公司年度报告，整理收入、利润、渠道和经营风险等公开披露事实，需要追到年报原文复核。",
            )
        ]


class FakeOnlyFilteredSearchProvider:
    def search(self, query: str, limit: int = 5) -> list[SearchResult]:
        return [
            SearchResult(
                query=query,
                title="000858.SZ 深交所上市公司公告检索入口",
                url="https://www.szse.cn/disclosure/listed/notice/index.html",
                source="www.szse.cn",
                snippet="深圳证券交易所上市公司公告检索入口。",
            ),
            SearchResult(
                query=query,
                title="贵州茅台 当前股价和目标价",
                url="https://quote.eastmoney.com/sh600519.html",
                source="quote.eastmoney.com",
                snippet="股票行情和目标价。",
            ),
            SearchResult(
                query=query,
                title="贵州茅台 百度百科",
                url="https://baike.baidu.com/item/贵州茅台",
                source="baike.baidu.com",
                snippet="百科词条。",
            ),
        ]


class FakeDisclosureClient:
    def fetch_announcements(
        self,
        ticker: str,
        years: int = 2,
        page_size: int = 40,
        limit: int | None = None,
    ) -> list[FetchedAnnouncement]:
        assert ticker == "000858"
        assert limit == 50
        return [
            FetchedAnnouncement(
                title="五粮液股份有限公司2025年年度报告",
                published_at=datetime(2026, 4, 30, tzinfo=UTC),
                category="定期报告",
                source="eastmoney_announcements",
                source_url="https://data.eastmoney.com/notices/detail/000858/1.html",
                raw_url="https://pdf.dfcfw.com/pdf/H2_1_1.pdf",
            ),
            FetchedAnnouncement(
                title="股票交易异常波动公告",
                published_at=datetime(2026, 4, 28, tzinfo=UTC),
                category="临时公告",
                source="eastmoney_announcements",
                source_url="https://data.eastmoney.com/notices/detail/000858/2.html",
                raw_url="https://pdf.dfcfw.com/pdf/H2_2_1.pdf",
            ),
            FetchedAnnouncement(
                title="关于收到深圳证券交易所监管函的公告",
                published_at=datetime(2026, 4, 20, tzinfo=UTC),
                category="临时公告",
                source="eastmoney_announcements",
                source_url="https://data.eastmoney.com/notices/detail/000858/3.html",
                raw_url="https://pdf.dfcfw.com/pdf/H2_3_1.pdf",
            ),
        ]


class FakeMoutaiDisclosureClient:
    def fetch_announcements(
        self,
        ticker: str,
        years: int = 2,
        page_size: int = 40,
        limit: int | None = None,
    ) -> list[FetchedAnnouncement]:
        assert ticker == "600519"
        assert limit == 50
        return [
            FetchedAnnouncement(
                title="贵州茅台2025年年度报告",
                published_at=datetime(2026, 4, 30, tzinfo=UTC),
                category="定期报告",
                source="eastmoney_announcements",
                source_url="https://data.eastmoney.com/notices/detail/600519/1.html",
                raw_url="https://pdf.dfcfw.com/pdf/H2_1_1.pdf",
            ),
            FetchedAnnouncement(
                title="贵州茅台关于2025年度利润分配方案的公告",
                published_at=datetime(2026, 4, 25, tzinfo=UTC),
                category="临时公告",
                source="eastmoney_announcements",
                source_url="https://data.eastmoney.com/notices/detail/600519/2.html",
                raw_url="https://pdf.dfcfw.com/pdf/H2_2_1.pdf",
            ),
            FetchedAnnouncement(
                title="贵州茅台关于收到上海证券交易所监管函的公告",
                published_at=datetime(2026, 4, 20, tzinfo=UTC),
                category="临时公告",
                source="eastmoney_announcements",
                source_url="https://data.eastmoney.com/notices/detail/600519/3.html",
                raw_url="https://pdf.dfcfw.com/pdf/H2_3_1.pdf",
            ),
        ]


class FakeManualImportGateway:
    model_name = "fake-model"

    def __init__(self) -> None:
        self.saw_manual_text = False

    def generate_structured(self, **kwargs):
        schema = kwargs["schema"]
        user_prompt = str(kwargs["user_prompt"])
        self.saw_manual_text = "manual_text_import" in user_prompt and "只能基于" in user_prompt
        return schema.model_validate(
            {
                "evidences": [
                    {
                        "source_type": "regulatory",
                        "title": "白酒渠道监管访谈纪要",
                        "source": "manual_source",
                        "source_url": "https://example.test/manual-evidence",
                        "published_at": "2026-08-15T00:00:00+00:00",
                        "summary": "用户导入文本显示白酒渠道治理关注食品安全追溯和库存监测。",
                        "key_facts": ["白酒渠道治理关注食品安全追溯", "监管关注库存监测"],
                        "impact_direction": "mixed",
                        "importance_score": 0.7,
                        "credibility_score": 0.9,
                        "tags": ["监管", "渠道"],
                        "requires_review": False,
                        "price_sensitive": False,
                        "use_scope": [
                            "fundamental_analysis",
                            "analyst_view",
                            "intrinsic_valuation",
                        ],
                        "analysis_status": "model_analyzed",
                        "analysis_note": "模型基于用户导入文本完成结构化。",
                        "raw_snapshot": {"title": "白酒渠道监管访谈纪要"},
                    }
                ]
            }
        )


class FakeManualShareholderFactGateway:
    model_name = "fake-model"

    def __init__(self) -> None:
        self.saw_shareholder_rule = False

    def generate_structured(self, **kwargs):
        schema = kwargs["schema"]
        user_prompt = str(kwargs["user_prompt"])
        self.saw_shareholder_rule = (
            "前十大股东变化" in user_prompt and "机构持股变化" in user_prompt
        )
        return schema.model_validate(
            {
                "evidences": [
                    {
                        "source_type": "web",
                        "title": "香港中央结算退出贵州茅台十大股东名单",
                        "source": "东方财富",
                        "source_url": "https://finance.eastmoney.com/a/202608143842073818.html",
                        "published_at": "2026-08-14T00:00:00+00:00",
                        "summary": (
                            "手动导入文本显示香港中央结算已退出贵州茅台前十大股东名单，"
                            "需追到半年报原文复核。"
                        ),
                        "key_facts": [
                            "香港中央结算已退出贵州茅台前十大股东名单",
                            "上一期末香港中央结算曾为公司第九和第十股东",
                        ],
                        "impact_direction": "unknown",
                        "importance_score": 0.58,
                        "credibility_score": 0.65,
                        "tags": ["股东结构", "手动导入"],
                        "requires_review": True,
                        "price_sensitive": False,
                        "use_scope": [
                            "fundamental_analysis",
                            "analyst_view",
                            "intrinsic_valuation",
                        ],
                        "analysis_status": "model_analyzed",
                        "analysis_note": "模型基于用户导入文本完成结构化，需追到半年报原文复核。",
                        "raw_snapshot": {"title": "香港中央结算退出贵州茅台十大股东名单"},
                    }
                ]
            }
        )


class FakeManualPriceSensitiveGateway:
    model_name = "fake-model"

    def generate_structured(self, **kwargs):
        schema = kwargs["schema"]
        return schema.model_validate(
            {
                "evidences": [
                    {
                        "source_type": "web",
                        "title": "贵州茅台当前股价与目标价摘要",
                        "source": "manual_source",
                        "source_url": None,
                        "published_at": None,
                        "summary": "文本主要讨论当前股价、目标价、短线评级和交易观点。",
                        "key_facts": ["当前股价和目标价属于价格敏感信息"],
                        "impact_direction": "unknown",
                        "importance_score": 0.4,
                        "credibility_score": 0.4,
                        "tags": ["股价", "目标价"],
                        "requires_review": True,
                        "price_sensitive": True,
                        "use_scope": [],
                        "analysis_status": "model_analyzed",
                        "analysis_note": "价格敏感文本不应进入默认基本面证据库。",
                        "raw_snapshot": {"title": "贵州茅台当前股价与目标价摘要"},
                    }
                ]
            }
        )


class FakeConfiguredGateway:
    model_name = "fake-model"

    def __init__(self) -> None:
        self.calls = 0

    def generate_structured(self, **kwargs):
        self.calls += 1
        schema = kwargs["schema"]
        if self.calls == 1:
            return schema.model_validate({"queries": ["贵州茅台 白酒政策"]})
        return schema.model_validate(
            {
                "evidences": [
                    {
                        "source_type": "policy",
                        "title": "白酒行业监管政策变化",
                        "source": "example.test",
                        "source_url": "https://example.test/policy",
                        "published_at": datetime(2026, 8, 1, tzinfo=UTC).isoformat(),
                        "summary": "政策信息可能影响高端白酒渠道监管，需要后续复核原文。",
                        "key_facts": ["监管政策提到渠道合规要求"],
                        "impact_direction": "mixed",
                        "importance_score": 0.82,
                        "credibility_score": 0.76,
                        "tags": ["政策", "白酒"],
                        "requires_review": True,
                        "analysis_status": "model_analyzed",
                        "analysis_note": "来源为政策页面，重要性较高。",
                        "raw_snapshot": {
                            "query": "贵州茅台 白酒政策",
                            "title": "白酒行业监管政策变化",
                            "url": "https://example.test/policy",
                        },
                    }
                ]
            }
        )


class FakeFilterAwareGateway:
    model_name = "fake-model"

    def __init__(self) -> None:
        self.calls = 0
        self.seen_titles: list[str] = []

    def generate_structured(self, **kwargs):
        self.calls += 1
        schema = kwargs["schema"]
        if self.calls == 1:
            return schema.model_validate({"queries": ["贵州茅台 政策 监管 披露"]})

        user_prompt = str(kwargs["user_prompt"])
        search_results_section = user_prompt.split('"schema"', maxsplit=1)[0]
        assert "K线技术分析" not in search_results_section
        assert "贵州茅台 股吧 短线资金流向" not in search_results_section
        self.seen_titles = ["贵州茅台 食品安全监管公开信息"]
        return schema.model_validate(
            {
                "evidences": [
                    {
                        "source_type": "regulatory",
                        "title": "贵州茅台 食品安全监管公开信息",
                        "source": "www.cninfo.com.cn",
                        "source_url": "https://www.cninfo.com.cn/new/disclosure/detail",
                        "published_at": None,
                        "summary": "监管公开信息涉及食品安全与合规要求。",
                        "key_facts": ["监管公开信息涉及食品安全与合规要求"],
                        "impact_direction": "unknown",
                        "importance_score": 0.55,
                        "credibility_score": 0.85,
                        "tags": ["监管", "合规"],
                        "requires_review": True,
                        "analysis_status": "model_analyzed",
                        "analysis_note": "公开监管信息，仍需打开原文复核。",
                        "raw_snapshot": {
                            "query": "贵州茅台 政策 监管 披露",
                            "title": "贵州茅台 食品安全监管公开信息",
                            "url": "https://www.cninfo.com.cn/new/disclosure/detail",
                        },
                    }
                ]
            }
        )


class FakeSubstantiveCandidateGateway:
    model_name = "fake-model"

    def __init__(self) -> None:
        self.calls = 0
        self.seen_titles: list[str] = []

    def generate_structured(self, **kwargs):
        self.calls += 1
        schema = kwargs["schema"]
        if self.calls == 1:
            return schema.model_validate({"queries": ["贵州茅台 政策 监管 披露"]})

        import json

        payload = json.loads(str(kwargs["user_prompt"]))
        self.seen_titles = [item["title"] for item in payload["search_results"]]
        return schema.model_validate(
            {
                "evidences": [
                    {
                        "source_type": "regulatory",
                        "title": title,
                        "source": "example.test",
                        "source_url": f"https://example.test/liquor-policy-{index}",
                        "published_at": None,
                        "summary": "政策信息和行业供需数据可能影响高端白酒企业经营，需要复核原文。",
                        "key_facts": ["政策信息和行业供需数据可能影响高端白酒企业经营"],
                        "impact_direction": "unknown",
                        "importance_score": 0.55,
                        "credibility_score": 0.85,
                        "tags": ["交易所", "披露"],
                        "requires_review": True,
                        "analysis_status": "model_analyzed",
                        "analysis_note": "官方交易所来源，仍需按证券代码打开原文复核。",
                        "raw_snapshot": {
                            "query": "贵州茅台 政策 监管 披露",
                            "title": title,
                            "url": f"https://example.test/liquor-policy-{index}",
                        },
                    }
                    for index, title in enumerate(self.seen_titles, start=1)
                ]
            }
        )


class FakePriceSensitiveEvidenceGateway:
    model_name = "fake-model"

    def __init__(self) -> None:
        self.calls = 0

    def generate_structured(self, **kwargs):
        self.calls += 1
        schema = kwargs["schema"]
        if self.calls == 1:
            return schema.model_validate({"queries": ["贵州茅台 政策 监管"]})

        return schema.model_validate(
            {
                "evidences": [
                    {
                        "source_type": "web",
                        "title": "贵州茅台 当前股价与目标价摘要",
                        "source": "example.test",
                        "source_url": "https://example.test/price",
                        "published_at": None,
                        "summary": "内容主要涉及当前股价、历史股价、涨跌幅和目标价。",
                        "key_facts": ["当前股价和目标价属于价格敏感信息"],
                        "impact_direction": "unknown",
                        "importance_score": 0.4,
                        "credibility_score": 0.4,
                        "tags": ["股价", "目标价"],
                        "requires_review": True,
                        "price_sensitive": True,
                        "use_scope": [],
                        "analysis_status": "model_analyzed",
                        "analysis_note": "价格敏感信息不应进入外部基本面证据库。",
                        "raw_snapshot": {
                            "title": "贵州茅台 当前股价与目标价摘要",
                            "url": "https://example.test/price",
                        },
                    }
                ]
            }
        )


class FakeManyEvidenceGateway:
    model_name = "fake-model"

    def __init__(self) -> None:
        self.calls = 0

    def generate_structured(self, **kwargs):
        self.calls += 1
        schema = kwargs["schema"]
        if self.calls == 1:
            return schema.model_validate({"queries": ["贵州茅台 政策 监管 公开数据"]})

        evidences = []
        for index in range(12):
            evidences.append(
                {
                    "source_type": "policy",
                    "title": f"白酒行业政策线索 {index + 1}",
                    "source": "example.test",
                    "source_url": f"https://example.test/policy-{index + 1}",
                    "published_at": None,
                    "summary": "政策或监管公开信息。",
                    "key_facts": ["政策或监管公开信息"],
                    "impact_direction": "neutral",
                    "importance_score": 0.5,
                    "credibility_score": 0.6,
                    "tags": ["政策"],
                    "requires_review": True,
                    "price_sensitive": False,
                    "use_scope": [
                        "fundamental_analysis",
                        "analyst_view",
                        "intrinsic_valuation",
                    ],
                    "analysis_status": "model_analyzed",
                    "analysis_note": "政策公开信息。",
                    "raw_snapshot": {
                        "title": f"白酒行业政策线索 {index + 1}",
                        "url": f"https://example.test/policy-{index + 1}",
                    },
                }
            )
        return schema.model_validate({"evidences": evidences})


class FakeCompanyDisclosureDuplicateGateway:
    model_name = "fake-model"

    def __init__(self) -> None:
        self.calls = 0

    def generate_structured(self, **kwargs):
        self.calls += 1
        schema = kwargs["schema"]
        if self.calls == 1:
            return schema.model_validate({"queries": ["贵州茅台 政策 监管 公开数据"]})

        return schema.model_validate(
            {
                "evidences": [
                    {
                        "source_type": "web",
                        "title": "贵州茅台 2025年年度报告",
                        "source": "example.test",
                        "source_url": "https://example.test/annual-report",
                        "published_at": None,
                        "summary": "年报摘要，属于公告区已有内容。",
                        "key_facts": ["年报摘要"],
                        "impact_direction": "neutral",
                        "importance_score": 0.5,
                        "credibility_score": 0.6,
                        "tags": ["年报"],
                        "requires_review": True,
                        "price_sensitive": False,
                        "use_scope": [
                            "fundamental_analysis",
                            "analyst_view",
                            "intrinsic_valuation",
                        ],
                        "analysis_status": "model_analyzed",
                        "analysis_note": "与公告区重复。",
                        "raw_snapshot": {
                            "title": "贵州茅台 2025年年度报告",
                            "url": "https://example.test/annual-report",
                        },
                    }
                ]
            }
        )


class FakeQueryOnlyGateway:
    model_name = "fake-model"

    def generate_structured(self, **kwargs):
        schema = kwargs["schema"]
        return schema.model_validate({"queries": ["贵州茅台 政策 监管 披露"]})


class FakePageSnapshot:
    def to_snapshot(self):
        return {
            "url": "https://example.test/policy",
            "page_title": "白酒渠道监管政策",
            "page_description": "政策正文摘要",
            "content_excerpt": "网页正文显示渠道监管要求。",
            "content_fetched_at": "2026-08-09T00:00:00+00:00",
        }


class FakePageSnapshotFetcher:
    def fetch(self, url: str):
        assert url == "https://example.test/policy"
        return FakePageSnapshot()


class FakeAnnouncementContentFetcher:
    def __init__(self, content: str) -> None:
        self.content = content
        self.calls: list[tuple[str | None, str | None]] = []

    def fetch_text(self, *, source_url: str | None, raw_url: str | None):
        self.calls.append((source_url, raw_url))
        return self.content, raw_url or source_url or "https://example.test/announcement"


class FakeAnnouncementBodyAwareGateway:
    model_name = "fake-model"

    def __init__(self) -> None:
        self.calls = 0
        self.saw_announcement_body = False

    def generate_structured(self, **kwargs):
        self.calls += 1
        schema = kwargs["schema"]
        if self.calls == 1:
            return schema.model_validate({"queries": ["五粮液 食品安全 监管"]})

        user_prompt = str(kwargs["user_prompt"])
        self.saw_announcement_body = "三十日内完成渠道整改" in user_prompt
        return schema.model_validate(
            {
                "evidences": [
                    {
                        "source_type": "regulatory",
                        "title": "关于收到监管工作函并完成整改的公告",
                        "source": "eastmoney_announcements",
                        "source_url": (
                            "https://data.eastmoney.com/notices/detail/000858/ANBODY.html"
                        ),
                        "published_at": "2026-07-03T00:00:00+00:00",
                        "summary": "公告正文显示公司收到监管工作函并承诺完成渠道和信息披露整改。",
                        "key_facts": ["公司收到监管工作函", "公司承诺在三十日内完成整改"],
                        "impact_direction": "mixed",
                        "importance_score": 0.62,
                        "credibility_score": 0.78,
                        "tags": ["监管", "整改"],
                        "requires_review": True,
                        "analysis_status": "model_analyzed",
                        "analysis_note": "基于 006 公告正文读取结果完成结构化，仍需核对原文。",
                        "raw_snapshot": {
                            "title": "关于收到监管工作函并完成整改的公告",
                            "page_snapshot": {"content_excerpt": "三十日内完成渠道整改"},
                        },
                    }
                ]
            }
        )


class FakePageAwareGateway:
    model_name = "fake-model"

    def __init__(self) -> None:
        self.calls = 0
        self.saw_page_snapshot = False

    def generate_structured(self, **kwargs):
        self.calls += 1
        schema = kwargs["schema"]
        if self.calls == 1:
            return schema.model_validate({"queries": ["贵州茅台 渠道监管"]})

        user_prompt = str(kwargs["user_prompt"])
        self.saw_page_snapshot = "网页正文显示渠道监管要求。" in user_prompt
        return schema.model_validate(
            {
                "evidences": [
                    {
                        "source_type": "policy",
                        "title": "白酒行业监管政策变化",
                        "source": "example.test",
                        "source_url": "https://example.test/policy",
                        "published_at": None,
                        "summary": "网页正文显示渠道监管要求，需要继续复核原文。",
                        "key_facts": ["网页正文显示渠道监管要求"],
                        "impact_direction": "mixed",
                        "importance_score": 0.68,
                        "credibility_score": 0.7,
                        "tags": ["政策", "渠道"],
                        "requires_review": True,
                        "analysis_status": "model_analyzed",
                        "analysis_note": "基于网页正文摘录评分。",
                        "raw_snapshot": {
                            "query": "贵州茅台 渠道监管",
                            "title": "白酒行业监管政策变化",
                            "url": "https://example.test/policy",
                            "page_snapshot": {"content_excerpt": "网页正文显示渠道监管要求。"},
                        },
                    }
                ]
            }
        )


@pytest.fixture(autouse=True)
def patch_search_service_dependencies(monkeypatch) -> None:
    from app.api.routes import evidence as evidence_routes

    def fake_search_company_evidence(db, company, payload):
        return search_company_evidence(
            db,
            company,
            payload,
            gateway=FakeConfiguredGateway(),
            search_provider=FakeSearchProvider(),
        )

    monkeypatch.setattr(evidence_routes, "search_company_evidence", fake_search_company_evidence)
