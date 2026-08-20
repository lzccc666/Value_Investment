from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.analysis.analyst_profiles import get_analyst_profile, list_analyst_profiles
from app.analysis.model_gateway import ModelNotConfiguredError
from app.analysis.prompts.analyst import ANALYST_SYSTEM_PROMPT, build_analyst_prompt
from app.analysis.providers.openai_compatible import _compact_error_response
from app.analysis.valuation_parameter_matrix import (
    RULE_VALUATION_MAPPINGS,
    STATUS_SCORES,
    PriceAnchorOutputError,
    derive_valuation_parameter_matrix,
)
from app.db.init_db import init_db
from app.db.models import AnalysisRun, Announcement, Company, Evidence, FinancialStatement
from app.db.session import create_sqlalchemy_engine, get_db
from app.main import create_app
from app.schemas.analysis import AnalystAnalysisOutput, AnalystRunRequest
from app.services.analyst_service import (
    build_company_analysis_snapshot,
    list_latest_company_analysis_runs,
    run_company_analyst_view,
)


def _make_test_db(tmp_path: Path):
    database_url = f"sqlite:///{(tmp_path / 'analysis.db').as_posix()}"
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


def test_analyst_profiles_list_includes_all_profiles_from_architecture_note(
    tmp_path: Path,
) -> None:
    session_factory = _make_test_db(tmp_path)
    app = create_app(initialize_database=False)
    _override_db(app, session_factory)

    with TestClient(app) as client:
        response = client.get("/api/analyst-profiles")

    assert response.status_code == 200
    payload = response.json()
    profile_ids = [item["id"] for item in payload["items"]]
    assert profile_ids == [
        "buffett",
        "peter_lynch",
        "munger",
        "duan_yongping",
        "graham",
        "fisher",
        "lin_yuan",
        "li_lu",
    ]
    buffett = next(item for item in payload["items"] if item["id"] == "buffett")
    assert {rule["id"] for rule in buffett["rules"]} == {
        "durable_moat",
        "owner_earnings_quality",
        "capital_allocation",
        "management_candor",
    }
    assert all(
        buffett[field]
        for field in (
            "core_logic",
            "decision_sequence",
            "preferred_evidence",
            "failure_modes",
            "prompt_focus",
        )
    )
    assert all(
        set(rule["status_rubric"]) == {"pass", "neutral", "unknown", "warn", "fail"}
        for rule in buffett["rules"]
    )


def test_valuation_rule_mapping_covers_all_32_profile_rules() -> None:
    expected = {
        (profile.id, rule.id) for profile in list_analyst_profiles() for rule in profile.rules
    }
    assert len(expected) == 32
    assert set(RULE_VALUATION_MAPPINGS) == expected
    assert all(
        mapping.calculation_role == "compute" for mapping in RULE_VALUATION_MAPPINGS.values()
    )
    assert sum(len(mapping.dimensions) for mapping in RULE_VALUATION_MAPPINGS.values()) == 117


def test_each_profile_derives_four_rule_impacts_and_status_scores() -> None:
    assert STATUS_SCORES == {
        "pass": 1.0,
        "neutral": 0.0,
        "unknown": -0.1,
        "warn": -0.5,
        "fail": -2.0,
    }
    statuses = ("pass", "neutral", "unknown", "fail")
    for profile in list_analyst_profiles():
        result = {
            "profile_fit_score": 0.8,
            "confidence": 0.7,
            "rule_checks": [
                {"rule_id": rule.id, "status": statuses[index], "summary": rule.label}
                for index, rule in enumerate(profile.rules)
            ],
        }
        matrix = derive_valuation_parameter_matrix(
            source_run_id=100,
            profile=profile,
            result=result,
        )
        impacts = matrix["analyst_items"][0]["rule_impacts"]
        assert len(impacts) == 4
        assert [item["status_score"] for item in impacts] == [1.0, 0.0, -0.1, -2.0]


def test_price_blind_gate_does_not_confuse_esg_rating_or_per_share_value() -> None:
    cases = (
        ("buffett", "durable_moat", "ESG评级改善，但护城河仍需按经营证据判断。"),
        ("munger", "incentive_alignment", "激励考核与长期每股价值增长一致。"),
    )
    for profile_id, rule_id, summary in cases:
        profile = get_analyst_profile(profile_id)
        assert profile is not None
        matrix = derive_valuation_parameter_matrix(
            source_run_id=101,
            profile=profile,
            result={
                "profile_fit_score": 0.8,
                "confidence": 0.7,
                "rule_checks": [
                    {"rule_id": rule.id, "status": "pass", "summary": summary}
                    for rule in profile.rules
                ],
            },
        )
        impact = next(
            item
            for item in matrix["analyst_items"][0]["rule_impacts"]
            if item["rule_id"] == rule_id
        )
        assert impact["calculation_role"] == "compute"
        assert impact["price_blind_compatible"] is True
        assert impact["exclusion_reason"] is None


def test_price_blind_gate_still_excludes_explicit_price_anchors() -> None:
    profile = get_analyst_profile("buffett")
    assert profile is not None
    with pytest.raises(PriceAnchorOutputError):
        derive_valuation_parameter_matrix(
            source_run_id=102,
            profile=profile,
            result={
                "profile_fit_score": 0.8,
                "confidence": 0.7,
                "rule_checks": [
                    {
                        "rule_id": rule.id,
                        "status": "warn",
                        "summary": "引用 pe_ttm。"
                        if rule.id == "durable_moat"
                        else "仅使用基本面证据。",
                    }
                    for rule in profile.rules
                ],
            },
        )


def test_analyst_prompt_enforces_price_blind_deep_profile_contract() -> None:
    profile = get_analyst_profile("li_lu")
    assert profile is not None
    prompt = build_analyst_prompt(
        profile=profile,
        data_snapshot={
            "source_boundary": {},
            "company": {"name": "测试公司"},
            "financial_statements": [],
            "announcements": [],
            "external_evidence": [],
        },
    )
    combined_prompt = ANALYST_SYSTEM_PROMPT + prompt

    for expected in (
        "当前价格",
        "历史价格",
        "目标价",
        "市值",
        "持仓成本",
        "安全边际",
        "008 必须彻底 price-blind",
        "core_logic",
        "decision_sequence",
        "preferred_evidence",
        "failure_modes",
        "pass、neutral、unknown、warn、fail",
        "financial_metrics.profit_structure",
        "financial_metrics.expense_control",
        "quality_matrix.accounting_quality",
        "analyst_summary.income_statement_quality",
        "analyst_summary.profit_composition",
        "不要从原始 income_statement JSON 现场猜公式",
        "rule_checks[].financial_periods",
        "source_refs.financial_periods",
        "不要把利润表或财务记录写入 evidence_ids",
        "不要计算内在价值",
        "不要输出买入、卖出、持有、减仓",
        "financial_evidence_pack.model_display",
        "raw_decimal=0.77936",
        "绝不能写成 0.78%",
        "1亿元等于100,000,000元",
    ):
        assert expected in combined_prompt

    assert "最终 JSON 不得复述禁止概念或其英文技术字段名" in combined_prompt
    assert "不得把它们写成未评估项、无法判断项或数据缺口" in combined_prompt


def test_analyst_view_uses_existing_data_snapshot_and_creates_latest_run(
    tmp_path: Path,
    monkeypatch,
) -> None:
    session_factory = _make_test_db(tmp_path)
    _seed_analysis_snapshot_fixture(session_factory)
    app = create_app(initialize_database=False)

    def fake_run_company_analyst_view(db, company, analyst_profile, user_note=None):
        return run_company_analyst_view(
            db,
            company,
            analyst_profile,
            user_note=user_note,
            gateway=FakeAnalystGateway(),
        )

    from app.api.routes import analysis as analysis_routes

    monkeypatch.setattr(analysis_routes, "run_company_analyst_view", fake_run_company_analyst_view)
    _override_db(app, session_factory)

    with TestClient(app) as client:
        company_id = _get_company_id(client, "贵州茅台")
        response = client.post(
            f"/api/companies/{company_id}/analysis/runs",
            json={"analyst_profile": "buffett", "user_note": "重点看现金流"},
        )
        list_response = client.get(
            f"/api/companies/{company_id}/analysis/runs",
            params={"run_type": "analyst_view", "analyst_profile": "buffett"},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "success"
    assert payload["run_type"] == "analyst_view"
    assert payload["analyst_profile"] == "buffett"
    assert payload["run_version"] == "008_v1"
    assert payload["prompt_version"] == "analyst_view_v5"
    assert payload["is_latest"] is True
    assert payload["confidence"] == payload["result"]["confidence"]
    assert payload["result"]["overview"] == "现金流质量较好，但证据仍需补充。"
    assert 0 <= payload["result"]["profile_fit_score"] <= 1
    assert 0 <= payload["result"]["confidence"] <= 1
    assert payload["result"]["score_explanations"]["profile_relevance"]["method"] == (
        "rule_based_company_profile_fit_v2"
    )
    assert payload["result"]["score_explanations"]["data_confidence"]["method"] == (
        "snapshot_quality_v2"
    )
    assert "components" in payload["result"]["score_explanations"]["profile_relevance"]
    assert "components" in payload["result"]["score_explanations"]["data_confidence"]
    assert payload["result"]["analysis_basis"]["external_evidence_ids"] == [1]
    assert payload["result"]["rule_checks"][0]["rule_id"] == "durable_moat"
    assert payload["user_note"] == "重点看现金流"

    assert list_response.status_code == 200
    list_payload = list_response.json()
    assert list_payload["total"] >= 1
    assert list_payload["items"][0]["id"] == payload["id"]

    with session_factory() as session:
        run = session.get(AnalysisRun, payload["id"])

    assert run is not None
    assert run.input_snapshot["source_boundary"]["allowed_actions"] == ["web_search"]
    assert run.input_snapshot["source_boundary"]["disallowed_actions"] == [
        "persistent_web_collection"
    ]
    assert "live_web_search" in run.input_snapshot["source_boundary"]["allowed_sources"]
    assert run.input_snapshot["source_boundary"]["source_aliases"]["evidence"] == (
        "external_evidence"
    )
    assert run.input_snapshot["data_counts"]["financial_statements"] == 1
    assert "financial_evidence_pack" in run.input_snapshot
    assert run.input_snapshot["financial_evidence_pack"]["latest_period"] == "2025A"
    assert (
        run.input_snapshot["financial_evidence_pack"]["financial_facts"]["latest"]["revenue"]
        == 100.0
    )
    model_display = run.input_snapshot["financial_evidence_pack"]["model_display"]
    assert model_display["unit_contract"]["raw_ratio_unit"] == "0-1小数"
    assert model_display["latest_percentages"]["operating_cash_flow_to_revenue"] == {
        "source_path": "financial_metrics.cash_quality.operating_cash_flow_to_revenue",
        "raw_decimal": 0.28,
        "percent_value": 28.0,
        "display": "28.00%",
    }
    assert "cash_flow_quality" in run.input_snapshot["financial_evidence_pack"]
    assert "balance_sheet_adjustment" in run.input_snapshot["financial_evidence_pack"]
    assert "capital_allocation" in run.input_snapshot["financial_evidence_pack"]
    assert "valuation_readiness" in run.input_snapshot["financial_evidence_pack"]
    assert "analyst_summary" in run.input_snapshot["financial_evidence_pack"]
    assert run.input_snapshot["fact_ledger"]["financial_quality"]["latest_period"] == "2025A"
    assert run.input_snapshot["fact_ledger"]["financial_quality"]["flags_count"] == 0
    assert run.input_snapshot["fact_ledger"]["financial_quality"]["structured_gaps_count"] >= 1
    assert "valuation_readiness" in run.input_snapshot["fact_ledger"]["financial_quality"]
    assert "source_coverage_matrix" in run.input_snapshot
    assert "pre_model_observations" in run.input_snapshot
    assert run.input_snapshot["data_counts"]["announcements"] == 1
    assert run.input_snapshot["data_counts"]["evidence"] == 1
    assert set(run.input_snapshot["evidence"][0]) == {
        "id",
        "title",
        "published_at",
        "source_type",
        "summary",
    }
    assert (
        run.input_snapshot["fact_ledger"]["profile_relevance"]["score"]
        == (payload["result"]["profile_fit_score"])
    )
    assert run.data_snapshot_hash is not None
    assert run.parent_run_id is None
    assert "analysis_runs" not in run.input_snapshot["source_boundary"]["allowed_sources"]
    assert "history_runs" not in run.input_snapshot
    assert (
        run.input_snapshot["source_boundary"]["run_isolation_policy"]
        == "每次 analyst_view 生成完全独立，不读取历史 run，不把历史结论作为输入。"
    )


def test_analyst_output_corrects_raw_cash_flow_ratio_written_as_percent(
    tmp_path: Path,
) -> None:
    session_factory = _make_test_db(tmp_path)
    _seed_analysis_snapshot_fixture(session_factory)

    with session_factory() as session:
        company = session.scalar(select(Company).where(Company.ticker == "600519.SH"))
        assert company is not None
        run = run_company_analyst_view(
            session,
            company,
            "buffett",
            gateway=FakeRatioUnitMistakeGateway(),
        )

    assert run.result["overview"] == "经营现金流/收入为28.00%，需要继续观察。"
    assert run.result["financial_observations"] == ["经营现金流占收入为28.00%。"]


def test_analyst_snapshot_does_not_read_history_runs(tmp_path: Path) -> None:
    session_factory = _make_test_db(tmp_path)
    _seed_analysis_snapshot_fixture(session_factory)

    with session_factory() as session:
        company = session.scalar(select(Company).where(Company.ticker == "600519.SH"))
        assert company is not None
        session.add_all(
            [
                AnalysisRun(
                    company_id=company.id,
                    run_type="analyst_view",
                    analyst_profile="buffett",
                    result={"overview": "成功视角可作为历史上下文。"},
                    confidence=0.7,
                    is_latest=True,
                    status="success",
                ),
                AnalysisRun(
                    company_id=company.id,
                    run_type="evidence_search",
                    analyst_profile="evidence_search",
                    result={
                        "created_evidence_count": 3,
                        "fallback_reason": "模型接口返回错误：HTTP 502；<html>bad gateway</html>",
                    },
                    is_latest=True,
                    status="success",
                ),
            ]
        )
        session.commit()
        profile = get_analyst_profile("buffett")
        assert profile is not None

        snapshot = build_company_analysis_snapshot(session, company, profile=profile)

    assert "history_runs" not in snapshot
    assert snapshot["data_counts"].get("history_runs") is None
    assert "成功视角可作为历史上下文" not in str(snapshot)
    assert "bad gateway" not in str(snapshot)


def test_analyst_fact_ledger_detects_accounting_events_and_profile_relevance(
    tmp_path: Path,
) -> None:
    session_factory = _make_test_db(tmp_path)
    _seed_analysis_snapshot_fixture(session_factory)

    with session_factory() as session:
        company = session.scalar(select(Company).where(Company.ticker == "600519.SH"))
        assert company is not None
        session.add(
            Announcement(
                company_id=company.id,
                title="年度报告会计政策变更和收入确认核算调整",
                published_at=datetime(2026, 4, 28, tzinfo=UTC),
                category="annual_report",
                source="test_fixture",
                summary=(
                    "公司对部分业务收入确认相关核算方式进行调整，并对上年同期进行"
                    "追溯调整。利润和收入同比需要按可比口径复核。"
                ),
                importance_score=0.92,
            )
        )
        session.commit()

        lin_yuan = get_analyst_profile("lin_yuan")
        graham = get_analyst_profile("graham")
        assert lin_yuan is not None
        assert graham is not None

        lin_snapshot = build_company_analysis_snapshot(session, company, profile=lin_yuan)
        graham_snapshot = build_company_analysis_snapshot(session, company, profile=graham)

    lin_ledger = lin_snapshot["fact_ledger"]
    graham_ledger = graham_snapshot["fact_ledger"]
    assert isinstance(lin_ledger, dict)
    assert isinstance(graham_ledger, dict)

    assert lin_ledger["profile_relevance"]["score"] > graham_ledger["profile_relevance"]["score"]
    assert lin_ledger["profile_relevance"]["method"] == "rule_based_company_profile_fit_v2"
    assert "components" in lin_ledger["profile_relevance"]
    assert lin_ledger["profile_relevance"]["components"]["industry_framework_fit"] >= 0.8
    assert (
        graham_ledger["profile_relevance"]["components"]["industry_framework_fit"]
        < (lin_ledger["profile_relevance"]["components"]["industry_framework_fit"])
    )

    accounting_events = lin_ledger["accounting_events"]
    assert any(item["event_type"] == "revenue_recognition_change" for item in accounting_events)
    assert any(item["event_type"] == "retrospective_adjustment" for item in accounting_events)
    assert lin_ledger["financial_quality"]["has_accounting_event"] is True
    assert "同比变化需区分经营变化和口径变化" in str(
        lin_ledger["financial_quality"]["comparability_notes"]
    )


def test_analyst_snapshot_uses_isolated_ranked_source_limits(tmp_path: Path) -> None:
    session_factory = _make_test_db(tmp_path)
    _seed_analysis_snapshot_fixture(session_factory)

    with session_factory() as session:
        company = session.scalar(select(Company).where(Company.ticker == "600519.SH"))
        assert company is not None
        session.add_all(
            [
                FinancialStatement(
                    company_id=company.id,
                    period=f"2025Q{index:02d}",
                    statement_type="main_financial_indicators",
                    currency="CNY",
                    fields={"revenue": float(index)},
                    source="test_fixture",
                )
                for index in range(1, 50)
            ]
        )
        session.add_all(
            [
                Announcement(
                    company_id=company.id,
                    title=f"普通公告 {index}",
                    published_at=datetime(2026, 1, min(index, 28), tzinfo=UTC),
                    category="other",
                    source="test_fixture",
                    summary="一般事项。",
                    importance_score=0.1,
                )
                for index in range(1, 35)
            ]
        )
        priority_announcement = Announcement(
            company_id=company.id,
            title="年度报告会计政策变更和收入确认调整",
            published_at=datetime(2025, 1, 1, tzinfo=UTC),
            category="annual_report",
            source="test_fixture",
            summary="公司发生会计政策变更、收入确认和追溯调整事项。",
            key_facts=["收入确认政策发生调整。", "会计政策变更需要追溯复核。"],
            importance_score=0.95,
            tags=["会计政策", "收入确认"],
        )
        session.add(priority_announcement)
        session.add_all(
            [
                Evidence(
                    company_id=company.id,
                    source_type="industry_news",
                    title=f"普通外部信息 {index}",
                    source="test_fixture",
                    source_url=f"https://example.test/evidence/{index}",
                    published_at=datetime(2026, 2, min(index, 28), tzinfo=UTC),
                    summary="一般行业信息。",
                    key_facts=[],
                    impact_direction="neutral",
                    importance_score=0.2,
                    credibility_score=0.2,
                    tags=["普通"],
                    requires_review=True,
                    price_sensitive=False,
                    use_scope=["fundamental_analysis", "analyst_view"],
                    analysis_status="search_lead",
                    raw_snapshot={},
                )
                for index in range(1, 71)
            ]
        )
        priority_evidence = Evidence(
            company_id=company.id,
            source_type="regulatory",
            title="监管公开信息提到渠道合规整改",
            source="test_fixture",
            source_url="https://example.test/regulatory",
            published_at=datetime(2025, 1, 1, tzinfo=UTC),
            summary="监管公开信息要求公司整改渠道合规。",
            key_facts=["渠道合规整改需要跟踪。"],
            impact_direction="negative",
            importance_score=0.95,
            credibility_score=0.95,
            tags=["监管", "渠道"],
            requires_review=False,
            price_sensitive=False,
            use_scope=["fundamental_analysis", "analyst_view", "intrinsic_valuation"],
            analysis_status="model_analyzed",
            raw_snapshot={},
        )
        session.add(priority_evidence)
        session.commit()

        profile = get_analyst_profile("buffett")
        assert profile is not None
        snapshot = build_company_analysis_snapshot(session, company, profile=profile)

    assert len(snapshot["financial_statements"]) == 40
    assert len(snapshot["announcements"]) == 20
    assert len(snapshot["external_evidence"]) == 10
    assert "history_runs" not in snapshot
    assert snapshot["data_counts"]["financial_statements"] == 40
    assert snapshot["data_counts"]["financial_statement_periods"] == 40
    assert "financial_evidence_pack" in snapshot
    assert "financial_flags" in snapshot["financial_evidence_pack"]
    assert snapshot["data_counts"]["announcements"] == 20
    assert snapshot["data_counts"]["external_evidence"] == 10
    assert priority_announcement.id in {item["id"] for item in snapshot["announcements"]}
    assert set(snapshot["announcements"][0]) == {
        "id",
        "title",
        "published_at",
        "category",
        "summary",
        "key_facts",
        "tags",
    }
    priority_snapshot = next(
        item for item in snapshot["announcements"] if item["id"] == priority_announcement.id
    )
    assert priority_snapshot["key_facts"] == [
        "收入确认政策发生调整。",
        "会计政策变更需要追溯复核。",
    ]
    assert priority_snapshot["tags"] == ["会计政策", "收入确认"]
    assert priority_evidence.id in {item["id"] for item in snapshot["external_evidence"]}
    assert set(snapshot["external_evidence"][0]) == {
        "id",
        "title",
        "published_at",
        "source_type",
        "summary",
    }
    assert set(snapshot["intrinsic_valuation_input"]["external_evidence"][0]) == {
        "id",
        "title",
        "published_at",
        "source_type",
        "summary",
    }
    assert snapshot["external_evidence"][0]["id"] == priority_evidence.id
    assert snapshot["source_boundary"]["snapshot_limits"] == {
        "financial_statement_periods": 40,
        "announcements": 20,
        "evidence": 10,
    }
    assert snapshot["data_counts"]["external_evidence_candidates"] > 60
    assert len(snapshot["intrinsic_valuation_input"]["external_evidence"]) <= 10


def test_analyst_snapshot_prioritizes_deep_summarized_announcements(
    tmp_path: Path,
) -> None:
    session_factory = _make_test_db(tmp_path)
    with session_factory() as session:
        company = session.scalar(select(Company).where(Company.ticker == "600519.SH"))
        assert company is not None
        quick_announcements = [
            Announcement(
                company_id=company.id,
                title=f"近期快速摘要公告 {index}",
                published_at=datetime(2026, 2, index, tzinfo=UTC),
                category="other",
                source="test_fixture",
                summary="仅有标题和元数据生成的快速摘要。",
                summary_model_name="metadata_keyword",
            )
            for index in range(1, 21)
        ]
        deep_announcement = Announcement(
            company_id=company.id,
            title="较早但已深度摘要的增持进展公告",
            published_at=datetime(2025, 1, 1, tzinfo=UTC),
            category="控制权变化",
            source="test_fixture",
            summary="控股股东增持进展明确，后续仍需跟踪完成情况。",
            key_facts=["累计增持金额已披露。"],
            tags=["股东增持"],
            summary_model_name="deepseek-v4-pro",
        )
        session.add_all([*quick_announcements, deep_announcement])
        session.commit()
        profile = get_analyst_profile("buffett")
        assert profile is not None
        snapshot = build_company_analysis_snapshot(session, company, profile=profile)

    announcement_ids = [item["id"] for item in snapshot["announcements"]]
    quick_ids = {item.id for item in quick_announcements}
    deep_snapshot = next(
        item for item in snapshot["announcements"] if item["id"] == deep_announcement.id
    )
    assert announcement_ids[0] == deep_announcement.id
    assert len(quick_ids & set(announcement_ids)) < len(quick_ids)
    assert deep_snapshot["key_facts"] == ["累计增持金额已披露。"]
    assert deep_snapshot["tags"] == ["股东增持"]
    assert "summary_model_name" not in deep_snapshot


def test_analyst_snapshot_orders_financials_by_report_date(tmp_path: Path) -> None:
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
        profile = get_analyst_profile("buffett")
        assert profile is not None
        snapshot = build_company_analysis_snapshot(session, company, profile=profile)

    assert [item["period"] for item in snapshot["financial_statements"][:3]] == [
        "2025三季报",
        "2025中报",
        "2025一季报",
    ]
    assert snapshot["financial_evidence_pack"]["latest_period"] == "2025三季报"


def test_analyst_snapshot_keeps_forty_periods_when_financials_have_split_tables(
    tmp_path: Path,
) -> None:
    session_factory = _make_test_db(tmp_path)
    with session_factory() as session:
        company = session.scalar(select(Company).where(Company.ticker == "600519.SH"))
        assert company is not None
        statements = []
        for index in range(45):
            year = 2025 - index // 4
            quarter = index % 4
            period = f"{year}Q{4 - quarter}"
            report_month_day = ("12-31", "09-30", "06-30", "03-31")[quarter]
            report_date = f"{year}-{report_month_day}"
            statements.extend(
                [
                    FinancialStatement(
                        company_id=company.id,
                        period=period,
                        statement_type="main_financial_indicators",
                        currency="CNY",
                        fields={"report_date": report_date, "revenue": 100.0 + index},
                        source="test_fixture",
                    ),
                    FinancialStatement(
                        company_id=company.id,
                        period=period,
                        statement_type="income_statement",
                        currency="CNY",
                        fields={
                            "report_date": report_date,
                            "revenue": 100.0 + index,
                            "operating_profit": 25.0,
                            "net_profit": 20.0,
                        },
                        source="test_fixture",
                    ),
                    FinancialStatement(
                        company_id=company.id,
                        period=period,
                        statement_type="cash_flow_statement",
                        currency="CNY",
                        fields={"report_date": report_date, "operating_cash_flow": 30.0},
                        source="test_fixture",
                    ),
                    FinancialStatement(
                        company_id=company.id,
                        period=period,
                        statement_type="balance_sheet",
                        currency="CNY",
                        fields={"report_date": report_date, "cash_and_equivalents": 50.0},
                        source="test_fixture",
                    ),
                ]
            )
        session.add_all(statements)
        session.commit()
        profile = get_analyst_profile("buffett")
        assert profile is not None
        snapshot = build_company_analysis_snapshot(session, company, profile=profile)

    periods = {item["period"] for item in snapshot["financial_statements"]}

    assert len(periods) == 40
    assert len(snapshot["financial_statements"]) == 160
    assert snapshot["data_counts"]["financial_statement_periods"] == 40
    assert snapshot["data_counts"]["financial_statements"] == 160
    assert "2014Q4" not in periods
    assert "2025Q4" in periods
    financial_selection_policy = snapshot["source_boundary"]["selection_policy"][
        "financial_statements"
    ]
    assert "利润表" in financial_selection_policy
    assert "income_statement" in financial_selection_policy
    assert "income_statement" in {
        item["statement_type"] for item in snapshot["financial_statements"]
    }
    assert {
        item["statement_type"]
        for item in snapshot["financial_statements"]
        if item["period"] == "2025Q4"
    } == {
        "main_financial_indicators",
        "income_statement",
        "cash_flow_statement",
        "balance_sheet",
    }


def test_analyst_snapshot_uses_income_statement_structured_pack(tmp_path: Path) -> None:
    session_factory = _make_test_db(tmp_path)
    with session_factory() as session:
        company = session.scalar(select(Company).where(Company.ticker == "600519.SH"))
        assert company is not None
        session.add_all(
            [
                FinancialStatement(
                    company_id=company.id,
                    period="2025A",
                    statement_type="main_financial_indicators",
                    currency="CNY",
                    fields={
                        "report_date": "2025-12-31",
                        "revenue": 100.0,
                        "net_profit": 20.0,
                        "deducted_net_profit": 10.0,
                    },
                    source="test_fixture",
                ),
                FinancialStatement(
                    company_id=company.id,
                    period="2025A",
                    statement_type="income_statement",
                    currency="CNY",
                    fields={
                        "report_date": "2025-12-31",
                        "revenue": 100.0,
                        "operating_cost": 50.0,
                        "gross_profit": 50.0,
                        "selling_expense": 8.0,
                        "admin_expense": 7.0,
                        "r_and_d_expense": 2.0,
                        "finance_expense": 5.0,
                        "investment_income": 8.0,
                        "credit_impairment_loss": -3.0,
                        "asset_impairment_loss": -2.0,
                        "operating_profit": 30.0,
                        "non_operating_income": 1.0,
                        "non_operating_expense": 0.0,
                        "total_profit": 26.0,
                        "income_tax_expense": 6.0,
                        "net_profit": 20.0,
                        "parent_net_profit": 20.0,
                        "deducted_net_profit": 10.0,
                    },
                    source="test_fixture",
                ),
                FinancialStatement(
                    company_id=company.id,
                    period="2025A",
                    statement_type="cash_flow_statement",
                    currency="CNY",
                    fields={
                        "report_date": "2025-12-31",
                        "operating_cash_flow": 25.0,
                        "capital_expenditure": 3.0,
                        "free_cash_flow": 22.0,
                    },
                    source="test_fixture",
                ),
                FinancialStatement(
                    company_id=company.id,
                    period="2025A",
                    statement_type="balance_sheet",
                    currency="CNY",
                    fields={
                        "report_date": "2025-12-31",
                        "cash_and_equivalents": 40.0,
                        "interest_bearing_debt": 10.0,
                        "shareholders_equity": 90.0,
                    },
                    source="test_fixture",
                ),
                FinancialStatement(
                    company_id=company.id,
                    period="2024A",
                    statement_type="income_statement",
                    currency="CNY",
                    fields={
                        "report_date": "2024-12-31",
                        "revenue": 100.0,
                        "selling_expense": 5.0,
                        "admin_expense": 4.0,
                        "r_and_d_expense": 2.0,
                        "finance_expense": 1.0,
                        "operating_profit": 35.0,
                        "net_profit": 30.0,
                        "parent_net_profit": 30.0,
                        "deducted_net_profit": 28.0,
                    },
                    source="test_fixture",
                ),
            ]
        )
        session.commit()
        profile = get_analyst_profile("buffett")
        assert profile is not None
        snapshot = build_company_analysis_snapshot(session, company, profile=profile)

    financial_topics = snapshot["source_coverage_matrix"]["financial"]
    assert financial_topics["profit_structure"]["covered"] is True
    assert financial_topics["expense_control"]["covered"] is True
    assert financial_topics["accounting_quality"]["covered"] is True

    financial_quality = snapshot["fact_ledger"]["financial_quality"]
    income_coverage = financial_quality["income_statement_coverage"]
    assert income_coverage["has_income_statement"] is True
    assert income_coverage["has_expense_breakdown"] is True
    assert income_coverage["has_operating_profit"] is True
    assert income_coverage["has_impairment_items"] is True
    assert income_coverage["has_non_operating_items"] is True
    assert income_coverage["has_tax_expense"] is True
    assert "evidence_pack" in income_coverage["note"]

    observations_text = "\n".join(snapshot["pre_model_observations"])
    assert "投资收益占净利润较高" in observations_text
    assert "期间费用率连续上升" in observations_text
    assert "财务费用率上升" in observations_text
    assert "减值损失占净利润较高" in observations_text
    assert "扣非净利润显著弱于归母净利润" in observations_text
    assert "不要从原始 JSON 现场猜公式" in observations_text


def test_analyst_snapshot_excludes_price_sensitive_inputs(tmp_path: Path) -> None:
    session_factory = _make_test_db(tmp_path)
    _seed_analysis_snapshot_fixture(session_factory)

    with session_factory() as session:
        company = session.scalar(select(Company).where(Company.ticker == "600519.SH"))
        assert company is not None
        company.market_cap = 1694223093019.29
        company.current_price = 1355.29
        company.pe_ttm = 20.48
        company.pe_dynamic = 18.6
        company.pe_static = 21.1
        company.pb_ratio = 7.8
        company.ps_ratio = 11.2
        company.dividend_yield_ttm = 0.039
        company.dividend_yield_static = 0.035
        company.market_data_source = "eastmoney_quote"
        company.market_data_source_url = "https://example.test/quote/600519"
        company.market_data_updated_at = datetime(2026, 8, 15, 12, 30, tzinfo=UTC)
        price_sensitive_evidence = Evidence(
            company_id=company.id,
            source_type="web",
            title="当前价格和历史价格线索",
            source="test_fixture",
            source_url="https://example.test/price",
            published_at=datetime(2026, 5, 2, tzinfo=UTC),
            summary="内容包含当前价格、历史价格、目标价、市值和持仓成本。",
            key_facts=["当前价格 100", "历史价格 90", "目标价 120"],
            impact_direction="neutral",
            importance_score=0.5,
            credibility_score=0.5,
            tags=["价格", "市值", "持仓成本"],
            requires_review=True,
            price_sensitive=True,
            use_scope=[],
            analysis_status="model_analyzed",
            analysis_note="价格敏感内容测试。",
            raw_snapshot={"current_price": 100, "target_price": 120},
        )
        session.add_all(
            [
                FinancialStatement(
                    company_id=company.id,
                    period="2026Q1",
                    statement_type="main_financial_indicators",
                    currency="CNY",
                    fields={
                        "revenue": 120.0,
                        "current_price": 100.0,
                        "target_price": 120.0,
                        "market_cap": 9000.0,
                        "holding_cost": 88.0,
                    },
                    source="test_fixture",
                ),
                Announcement(
                    company_id=company.id,
                    title="目标价与持仓成本相关披露",
                    published_at=datetime(2026, 5, 1, tzinfo=UTC),
                    category="other",
                    source="test_fixture",
                    summary="这里提到目标价、当前价格、市值和持仓成本都不应进入 008 快照。",
                    importance_score=0.8,
                ),
                price_sensitive_evidence,
            ]
        )
        session.commit()
        profile = get_analyst_profile("buffett")
        assert profile is not None

        snapshot = build_company_analysis_snapshot(session, company, profile=profile)

    snapshot_text = str(snapshot)
    assert "目标价" not in snapshot_text
    assert "持仓成本" not in snapshot_text
    assert "当前价格" not in snapshot_text
    assert "历史价格" not in snapshot_text
    assert "市值" not in snapshot_text
    assert not any(
        item["title"] == "目标价与持仓成本相关披露" for item in snapshot["announcements"]
    )
    assert snapshot["data_counts"]["price_sensitive_external_evidence"] == 0
    assert not any(
        item["title"] == "当前价格和历史价格线索" for item in snapshot["external_evidence"]
    )
    latest_financial = next(
        item for item in snapshot["financial_statements"] if item["period"] == "2026Q1"
    )
    assert "current_price" not in latest_financial["fields"]
    assert "target_price" not in latest_financial["fields"]
    assert "market_cap" not in latest_financial["fields"]
    assert "holding_cost" not in latest_financial["fields"]
    assert (
        snapshot["source_boundary"]["price_sensitive_policy"]["analyst_view_allows_price_sensitive"]
        is False
    )
    assert set(snapshot["company"]) == {
        "id",
        "ticker",
        "exchange",
        "name",
        "industry",
        "description",
        "listed_date",
        "status",
        "tags",
    }


def test_analyst_view_failed_model_configuration_is_recorded(tmp_path: Path) -> None:
    session_factory = _make_test_db(tmp_path)

    with session_factory() as session:
        company = session.scalar(select(Company).where(Company.ticker == "600519.SH"))
        assert company is not None

        with pytest.raises(ModelNotConfiguredError, match="MODEL_API_KEY"):
            run_company_analyst_view(
                session,
                company,
                "buffett",
                gateway=FakeUnconfiguredGateway(),
            )

        run = session.scalar(
            select(AnalysisRun)
            .where(
                AnalysisRun.company_id == company.id,
                AnalysisRun.run_type == "analyst_view",
                AnalysisRun.analyst_profile == "buffett",
            )
            .order_by(AnalysisRun.id.desc())
        )

    assert run is not None
    assert run.status == "failed"
    assert run.result["error_type"] == "ModelNotConfiguredError"
    assert run.is_latest is True


def test_analyst_view_preserves_previous_profile_runs(tmp_path: Path) -> None:
    session_factory = _make_test_db(tmp_path)
    _seed_analysis_snapshot_fixture(session_factory)

    with session_factory() as session:
        company = session.scalar(select(Company).where(Company.ticker == "600519.SH"))
        assert company is not None
        old_run = AnalysisRun(
            company_id=company.id,
            run_type="analyst_view",
            analyst_profile="buffett",
            result={"overview": "旧结论"},
            confidence=0.4,
            is_latest=True,
            status="success",
            created_at=datetime(2026, 8, 14, 8, 0, tzinfo=UTC),
        )
        stale_failed_run = AnalysisRun(
            company_id=company.id,
            run_type="analyst_view",
            analyst_profile="buffett",
            result={"error": "旧失败"},
            confidence=None,
            is_latest=False,
            status="failed",
            created_at=datetime(2026, 8, 13, 8, 0, tzinfo=UTC),
        )
        other_profile_run = AnalysisRun(
            company_id=company.id,
            run_type="analyst_view",
            analyst_profile="munger",
            result={"overview": "芒格旧结论"},
            confidence=0.5,
            is_latest=True,
            status="success",
        )
        session.add_all([old_run, stale_failed_run, other_profile_run])
        session.commit()
        old_run_id = old_run.id
        stale_failed_run_id = stale_failed_run.id
        other_profile_run_id = other_profile_run.id

        created = run_company_analyst_view(
            session,
            company,
            "buffett",
            gateway=FakeAnalystGateway(),
        )

        buffett_runs = session.scalars(
            select(AnalysisRun)
            .where(
                AnalysisRun.company_id == company.id,
                AnalysisRun.run_type == "analyst_view",
                AnalysisRun.analyst_profile == "buffett",
            )
            .order_by(AnalysisRun.id.asc())
        ).all()
        other_run = session.get(AnalysisRun, other_profile_run_id)
        stale_failed = session.get(AnalysisRun, stale_failed_run_id)

    assert created.id != old_run_id
    assert stale_failed is not None
    assert len(buffett_runs) == 3
    assert buffett_runs[0].is_latest is False
    assert buffett_runs[-1].status == "success"
    assert buffett_runs[-1].result["overview"] == "现金流质量较好，但证据仍需补充。"
    assert buffett_runs[-1].is_latest is True
    assert other_run is not None
    assert other_run.result["overview"] == "芒格旧结论"


def test_latest_analysis_runs_return_one_latest_success_per_profile(tmp_path: Path) -> None:
    session_factory = _make_test_db(tmp_path)

    with session_factory() as session:
        company = session.scalar(select(Company).where(Company.ticker == "600519.SH"))
        assert company is not None
        first_run = AnalysisRun(
            company_id=company.id,
            run_type="analyst_view",
            analyst_profile="buffett",
            result={"overview": "旧结论"},
            confidence=0.4,
            is_latest=False,
            status="success",
        )
        second_run = AnalysisRun(
            company_id=company.id,
            run_type="analyst_view",
            analyst_profile="buffett",
            result={"overview": "新结论"},
            confidence=0.7,
            is_latest=True,
            status="success",
        )
        failed_run = AnalysisRun(
            company_id=company.id,
            run_type="analyst_view",
            analyst_profile="munger",
            result={"error": "模型未配置"},
            is_latest=False,
            status="failed",
        )
        fisher_run = AnalysisRun(
            company_id=company.id,
            run_type="analyst_view",
            analyst_profile="fisher",
            result={"overview": "费雪视角"},
            confidence=0.6,
            is_latest=True,
            status="success",
        )
        session.add_all([first_run, second_run, failed_run, fisher_run])
        session.commit()
        company_id = company.id

    with session_factory() as session:
        latest_runs = list_latest_company_analysis_runs(
            session,
            company_id=company_id,
            run_type="analyst_view",
            status="success",
        )

    assert {run.analyst_profile for run in latest_runs} == {"buffett", "fisher"}
    buffett_run = next(run for run in latest_runs if run.analyst_profile == "buffett")
    assert buffett_run.result["overview"] == "新结论"


def test_latest_successful_analysis_runs_remain_visible_during_newer_attempts(
    tmp_path: Path,
) -> None:
    session_factory = _make_test_db(tmp_path)

    with session_factory() as session:
        company = session.scalar(select(Company).where(Company.ticker == "600519.SH"))
        assert company is not None
        successful_run = AnalysisRun(
            company_id=company.id,
            run_type="analyst_view",
            analyst_profile="buffett",
            result={"overview": "最近一次成功结论"},
            confidence=0.7,
            is_latest=False,
            status="success",
            created_at=datetime(2026, 8, 14, 8, 0, tzinfo=UTC),
        )
        newer_failed_run = AnalysisRun(
            company_id=company.id,
            run_type="analyst_view",
            analyst_profile="buffett",
            result={"error": "本次生成失败"},
            confidence=None,
            is_latest=False,
            status="failed",
            created_at=datetime(2026, 8, 14, 9, 0, tzinfo=UTC),
        )
        latest_running_run = AnalysisRun(
            company_id=company.id,
            run_type="analyst_view",
            analyst_profile="buffett",
            result={},
            confidence=None,
            is_latest=True,
            status="running",
            created_at=datetime(2026, 8, 14, 10, 0, tzinfo=UTC),
        )
        session.add_all([successful_run, newer_failed_run, latest_running_run])
        session.commit()
        company_id = company.id

    with session_factory() as session:
        latest_successful_runs = list_latest_company_analysis_runs(
            session,
            company_id=company_id,
            run_type="analyst_view",
            status="success",
        )
        latest_runs = list_latest_company_analysis_runs(
            session,
            company_id=company_id,
            run_type="analyst_view",
            status=None,
        )

    assert len(latest_successful_runs) == 1
    assert latest_successful_runs[0].id == successful_run.id
    assert latest_successful_runs[0].result["overview"] == "最近一次成功结论"
    assert len(latest_runs) == 1
    assert latest_runs[0].id == latest_running_run.id
    assert latest_runs[0].status == "running"


def test_latest_failed_analysis_runs_ignore_profiles_with_newer_success(tmp_path: Path) -> None:
    session_factory = _make_test_db(tmp_path)

    with session_factory() as session:
        company = session.scalar(select(Company).where(Company.ticker == "600519.SH"))
        assert company is not None
        stale_failed_run = AnalysisRun(
            company_id=company.id,
            run_type="analyst_view",
            analyst_profile="duan_yongping",
            result={"error": "previous failure"},
            confidence=None,
            is_latest=False,
            status="failed",
            created_at=datetime(2026, 8, 14, 8, 0, tzinfo=UTC),
        )
        latest_success_run = AnalysisRun(
            company_id=company.id,
            run_type="analyst_view",
            analyst_profile="duan_yongping",
            result={"overview": "new success"},
            confidence=0.72,
            is_latest=True,
            status="success",
            created_at=datetime(2026, 8, 14, 9, 0, tzinfo=UTC),
        )
        session.add_all([stale_failed_run, latest_success_run])
        session.commit()
        company_id = company.id

    with session_factory() as session:
        latest_failed_runs = list_latest_company_analysis_runs(
            session,
            company_id=company_id,
            run_type="analyst_view",
            status="failed",
        )

    assert latest_failed_runs == []


def test_latest_analysis_runs_endpoint(tmp_path: Path) -> None:
    session_factory = _make_test_db(tmp_path)
    app = create_app(initialize_database=False)
    _override_db(app, session_factory)

    with session_factory() as session:
        company = session.scalar(select(Company).where(Company.ticker == "600519.SH"))
        assert company is not None
        session.add(
            AnalysisRun(
                company_id=company.id,
                run_type="analyst_view",
                analyst_profile="buffett",
                result={"overview": "最新结论"},
                confidence=0.8,
                is_latest=True,
                status="success",
            )
        )
        session.commit()
        company_id = company.id

    with TestClient(app) as client:
        response = client.get(
            f"/api/companies/{company_id}/analysis/runs/latest",
            params={"run_type": "analyst_view"},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["company_id"] == company_id
    assert payload["items"][0]["analyst_profile"] == "buffett"
    assert payload["items"][0]["result"]["overview"] == "最新结论"


def test_latest_failed_analysis_runs_response_sanitizes_html_error(tmp_path: Path) -> None:
    session_factory = _make_test_db(tmp_path)
    app = create_app(initialize_database=False)
    _override_db(app, session_factory)

    raw_error = """
    模型接口返回错误：HTTP 502；<!DOCTYPE html>
    <html><head><title>pumpkinai.vip | 502: Bad gateway</title></head></html>
    """
    with session_factory() as session:
        company = session.scalar(select(Company).where(Company.ticker == "600519.SH"))
        assert company is not None
        failed_run = AnalysisRun(
            company_id=company.id,
            run_type="analyst_view",
            analyst_profile="buffett",
            result={"error": raw_error, "error_type": "ModelGatewayError"},
            is_latest=False,
            status="failed",
        )
        session.add(failed_run)
        session.commit()
        company_id = company.id
        run_id = failed_run.id

    with TestClient(app) as client:
        response = client.get(
            f"/api/companies/{company_id}/analysis/runs/latest",
            params={"run_type": "analyst_view", "status": "failed"},
        )

    assert response.status_code == 200
    payload = response.json()
    error = payload["items"][0]["result"]["error"]
    assert error == "模型接口返回错误：HTTP 502；pumpkinai.vip | 502: Bad gateway"
    assert "<html" not in error

    with session_factory() as session:
        stored_run = session.get(AnalysisRun, run_id)
        assert stored_run is not None
        assert "<html" in stored_run.result["error"]


def test_delete_company_analysis_run_removes_record(tmp_path: Path) -> None:
    session_factory = _make_test_db(tmp_path)
    app = create_app(initialize_database=False)
    _override_db(app, session_factory)

    with session_factory() as session:
        company = session.scalar(select(Company).where(Company.ticker == "600519.SH"))
        assert company is not None
        run = AnalysisRun(
            company_id=company.id,
            run_type="analyst_view",
            analyst_profile="buffett",
            result={"overview": "用户不想保留的记录"},
            is_latest=True,
            status="success",
        )
        session.add(run)
        session.commit()
        company_id = company.id
        run_id = run.id

    with TestClient(app) as client:
        delete_response = client.delete(f"/api/companies/{company_id}/analysis/runs/{run_id}")
        list_response = client.get(
            f"/api/companies/{company_id}/analysis/runs",
            params={"run_type": "analyst_view"},
        )

    assert delete_response.status_code == 200
    assert delete_response.json() == {"id": run_id, "deleted": True}
    assert list_response.status_code == 200
    assert list_response.json()["total"] == 0


def test_delete_company_analysis_run_is_scoped_to_company(tmp_path: Path) -> None:
    session_factory = _make_test_db(tmp_path)
    app = create_app(initialize_database=False)
    _override_db(app, session_factory)

    with session_factory() as session:
        companies = session.scalars(select(Company).order_by(Company.id.asc()).limit(2)).all()
        assert len(companies) == 2
        run = AnalysisRun(
            company_id=companies[0].id,
            run_type="analyst_view",
            analyst_profile="buffett",
            result={"overview": "不能被其他公司删除"},
            is_latest=True,
            status="success",
        )
        session.add(run)
        session.commit()
        wrong_company_id = companies[1].id
        run_id = run.id

    with TestClient(app) as client:
        response = client.delete(f"/api/companies/{wrong_company_id}/analysis/runs/{run_id}")

    assert response.status_code == 404

    with session_factory() as session:
        assert session.get(AnalysisRun, run_id) is not None


def test_update_analysis_run_rule_status_overwrites_result(tmp_path: Path) -> None:
    session_factory = _make_test_db(tmp_path)
    app = create_app(initialize_database=False)
    _override_db(app, session_factory)

    with session_factory() as session:
        company = session.scalar(select(Company).where(Company.ticker == "600519.SH"))
        assert company is not None
        run = AnalysisRun(
            company_id=company.id,
            run_type="analyst_view",
            analyst_profile="buffett",
            result={
                "overview": "Existing analyst output",
                "rule_checks": [
                    {"rule_id": "durable_moat", "status": "warn", "summary": "Needs review"},
                    {
                        "rule_id": "owner_earnings_quality",
                        "status": "pass",
                        "summary": "Cash backed",
                    },
                ],
            },
            is_latest=True,
            status="success",
        )
        session.add(run)
        session.commit()
        company_id = company.id
        run_id = run.id

    with TestClient(app) as client:
        response = client.patch(
            f"/api/companies/{company_id}/analysis/runs/{run_id}/rule-checks/durable_moat",
            json={"status": "fail"},
        )

    assert response.status_code == 200
    payload = response.json()
    rule_checks = payload["result"]["rule_checks"]
    assert rule_checks[0]["status"] == "fail"
    assert rule_checks[1]["status"] == "pass"
    matrix_rules = payload["result"]["valuation_parameter_matrix"]["analyst_items"][0][
        "rule_impacts"
    ]
    moat_impact = next(item for item in matrix_rules if item["rule_id"] == "durable_moat")
    assert moat_impact["status"] == "fail"
    assert moat_impact["status_score"] == -2.0

    with session_factory() as session:
        stored_run = session.get(AnalysisRun, run_id)
        assert stored_run is not None
        assert stored_run.result["rule_checks"][0]["status"] == "fail"
        assert (
            stored_run.result["valuation_parameter_matrix"]
            == payload["result"]["valuation_parameter_matrix"]
        )


def test_update_analysis_run_rule_status_returns_404_for_missing_rule(tmp_path: Path) -> None:
    session_factory = _make_test_db(tmp_path)
    app = create_app(initialize_database=False)
    _override_db(app, session_factory)

    with session_factory() as session:
        company = session.scalar(select(Company).where(Company.ticker == "600519.SH"))
        assert company is not None
        run = AnalysisRun(
            company_id=company.id,
            run_type="analyst_view",
            analyst_profile="buffett",
            result={"overview": "Existing analyst output", "rule_checks": []},
            is_latest=True,
            status="success",
        )
        session.add(run)
        session.commit()
        company_id = company.id
        run_id = run.id

    with TestClient(app) as client:
        response = client.patch(
            f"/api/companies/{company_id}/analysis/runs/{run_id}/rule-checks/durable_moat",
            json={"status": "pass"},
        )

    assert response.status_code == 404


def test_batch_analysis_runs_continue_after_profile_failure(
    tmp_path: Path,
    monkeypatch,
) -> None:
    session_factory = _make_test_db(tmp_path)
    _seed_analysis_snapshot_fixture(session_factory)
    app = create_app(initialize_database=False)

    def fake_run_company_analyst_views_batch(db, company, analyst_profiles, user_note=None):
        from app.services.analyst_service import run_company_analyst_views_batch

        return run_company_analyst_views_batch(
            db,
            company,
            analyst_profiles,
            user_note=user_note,
            gateway=FakeBatchGateway(fail_profile="munger"),
        )

    from app.api.routes import analysis as analysis_routes

    monkeypatch.setattr(
        analysis_routes,
        "run_company_analyst_views_batch",
        fake_run_company_analyst_views_batch,
    )
    _override_db(app, session_factory)

    with TestClient(app) as client:
        company_id = _get_company_id(client, "贵州茅台")
        response = client.post(
            f"/api/companies/{company_id}/analysis/runs/batch",
            json={"analyst_profiles": ["buffett", "munger"]},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["requested"] == 2
    assert payload["succeeded"] == 1
    assert payload["failed"] == 1
    by_profile = {item["analyst_profile"]: item for item in payload["items"]}
    assert by_profile["buffett"]["status"] == "success"
    assert by_profile["munger"]["status"] == "failed"
    assert by_profile["munger"]["error_type"] == "ModelNotConfiguredError"


def test_model_http_error_body_is_compacted() -> None:
    body = """
    <!DOCTYPE html>
    <html><head><title>pumpkinai.vip | 502: Bad gateway</title></head>
    <body>very long html body should not be persisted in full</body></html>
    """

    assert _compact_error_response(body) == "pumpkinai.vip | 502: Bad gateway"


def test_analyst_output_references_are_validated(tmp_path: Path) -> None:
    session_factory = _make_test_db(tmp_path)
    _seed_analysis_snapshot_fixture(session_factory)

    with session_factory() as session:
        company = session.scalar(select(Company).where(Company.ticker == "600519.SH"))
        assert company is not None

        with pytest.raises(Exception, match="不存在的 Evidence"):
            run_company_analyst_view(
                session,
                company,
                "buffett",
                gateway=FakeInvalidReferenceGateway(),
            )

        run = session.scalar(
            select(AnalysisRun)
            .where(
                AnalysisRun.company_id == company.id,
                AnalysisRun.run_type == "analyst_view",
                AnalysisRun.analyst_profile == "buffett",
            )
            .order_by(AnalysisRun.id.desc())
        )

    assert run is not None
    assert run.status == "failed"
    assert run.result["error_type"] == "ModelOutputValidationError"


def test_analyst_output_rejects_price_sensitive_analysis(tmp_path: Path) -> None:
    session_factory = _make_test_db(tmp_path)
    _seed_analysis_snapshot_fixture(session_factory)

    with session_factory() as session:
        company = session.scalar(select(Company).where(Company.ticker == "600519.SH"))
        assert company is not None

        with pytest.raises(PriceAnchorOutputError):
            run_company_analyst_view(
                session,
                company,
                "buffett",
                gateway=FakePriceAwareAnalysisGateway(),
            )

        run = session.scalar(
            select(AnalysisRun)
            .where(
                AnalysisRun.company_id == company.id,
                AnalysisRun.run_type == "analyst_view",
                AnalysisRun.analyst_profile == "buffett",
            )
            .order_by(AnalysisRun.id.desc())
        )

    assert run is not None
    assert run.status == "failed"
    assert run.result["error_type"] == "PriceAnchorOutputError"


def test_analyst_snapshot_only_exposes_minimal_external_evidence_fields(
    tmp_path: Path,
) -> None:
    session_factory = _make_test_db(tmp_path)
    _seed_analysis_snapshot_fixture(session_factory)

    with session_factory() as session:
        company = session.scalar(select(Company).where(Company.ticker == "600519.SH"))
        assert company is not None
        session.add(
            Evidence(
                company_id=company.id,
                source_type="regulatory",
                title="高重要性监管信息",
                source="test_fixture",
                source_url="https://example.test/regulatory-high",
                published_at=datetime(2026, 6, 1, tzinfo=UTC),
                summary="只验证分析师输入字段收敛。",
                key_facts=["原始材料"],
                impact_direction="neutral",
                importance_score=0.99,
                credibility_score=0.98,
                tags=["监管"],
                requires_review=False,
                price_sensitive=False,
                use_scope=["fundamental_analysis", "analyst_view", "intrinsic_valuation"],
                analysis_status="model_analyzed",
                analysis_note="不应传给分析师。",
                raw_snapshot={"source_url": "https://example.test/regulatory-high"},
            )
        )
        session.commit()

        profile = get_analyst_profile("buffett")
        assert profile is not None
        snapshot = build_company_analysis_snapshot(session, company, profile=profile)

    fields = set(snapshot["external_evidence"][0])
    assert fields == {"id", "title", "published_at", "source_type", "summary"}
    assert set(snapshot["intrinsic_valuation_input"]["external_evidence"][0]) == fields


def test_analyst_output_normalizes_deepseek_schema_drift() -> None:
    output = AnalystAnalysisOutput.model_validate(
        {
            "analyst_profile": "buffett",
            "rule_checks": [
                {
                    "rule_id": "durable_moat",
                    "status": "stable",
                    "reasoning": "品牌和毛利率支持护城河判断。",
                    "supporting_evidence_ids": [],
                },
                {
                    "rule_id": "owner_earnings_quality",
                    "status": "acceptable",
                    "reasoning": "现金流质量尚可。",
                },
                {
                    "rule_id": "capital_allocation",
                    "status": "uncertain",
                    "reasoning": "管理层变动需要跟踪。",
                    "supporting_evidence_ids": [1],
                },
                {
                    "rule_id": "management_candor",
                    "status": "inconclusive",
                    "reasoning": "缺少估值数据。",
                },
            ],
            "data_gaps": ["缺少估值数据。"],
            "bear_case": ["若毛利率趋势反转，品牌优势需要重估。"],
            "valuation_assumptions": [
                "后续估值模块应验证利润率中枢。",
                {
                    "assumption_type": "利润率中枢",
                    "reason": "当前快照只能看到有限期间毛利率。",
                    "needed_inputs": ["5 年毛利率", "费用率"],
                    "source_refs": {"financial_periods": ["2025A"]},
                },
            ],
            "follow_up_questions": ["回购是否能持续？"],
        }
    )

    assert output.overview == "品牌和毛利率支持护城河判断；现金流质量尚可"
    assert output.profile_fit_score == 0.63
    assert output.confidence == 0.51
    assert output.key_observations[0] == "品牌和毛利率支持护城河判断。"
    assert output.counter_evidence == ["若毛利率趋势反转，品牌优势需要重估。"]
    assert output.valuation_assumption_suggestions == [
        "后续估值模块应验证利润率中枢。",
        "利润率中枢：当前快照只能看到有限期间毛利率；需补充 5 年毛利率、费用率",
    ]
    assert output.valuation_assumption_details[0].assumption_type == "利润率中枢"
    assert output.valuation_assumption_details[0].needed_inputs == ["5 年毛利率", "费用率"]
    assert output.supporting_evidence_ids == [1]
    assert output.rule_checks[0].status == "pass"
    assert output.rule_checks[0].summary == "品牌和毛利率支持护城河判断。"
    assert output.rule_checks[2].status == "unknown"


def test_analyst_output_fallback_overview_normalizes_punctuation() -> None:
    output = AnalystAnalysisOutput.model_validate(
        {
            "analyst_profile": "buffett",
            "rule_checks": [
                {
                    "rule_id": "durable_moat",
                    "status": "warn",
                    "reasoning": "品牌证据仍需复核。",
                },
                {
                    "rule_id": "owner_earnings_quality",
                    "status": "warn",
                    "reasoning": "现金流证据不足。",
                },
            ],
        }
    )

    assert output.overview == "品牌证据仍需复核；现金流证据不足"
    assert "。；" not in output.overview


def test_unknown_analyst_profile_returns_404(tmp_path: Path) -> None:
    session_factory = _make_test_db(tmp_path)
    app = create_app(initialize_database=False)
    _override_db(app, session_factory)

    with TestClient(app) as client:
        company_id = _get_company_id(client, "贵州茅台")
        response = client.post(
            f"/api/companies/{company_id}/analysis/runs",
            json={"analyst_profile": "unknown"},
        )

    assert response.status_code == 404
    assert "未知分析师 Profile" in response.json()["detail"]


def test_analysis_run_request_normalizes_user_note() -> None:
    payload = AnalystRunRequest(analyst_profile=" buffett ", user_note="  ")
    assert payload.analyst_profile == "buffett"
    assert payload.user_note is None


def _seed_analysis_snapshot_fixture(session_factory) -> None:
    with session_factory() as session:
        company = session.scalar(select(Company).where(Company.ticker == "600519.SH"))
        assert company is not None
        session.add_all(
            [
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
                        "operating_cash_flow_to_revenue": 0.28,
                    },
                    source="test_fixture",
                ),
                Announcement(
                    company_id=company.id,
                    title="年度经营摘要已导入",
                    published_at=datetime(2026, 1, 15, tzinfo=UTC),
                    category="annual_report",
                    source="test_fixture",
                    summary="测试公告用于验证分析快照。",
                    importance_score=0.7,
                ),
                Evidence(
                    company_id=company.id,
                    source_type="industry_news",
                    title="测试行业证据已入库",
                    source="test_fixture",
                    source_url="https://example.test/evidence",
                    published_at=datetime(2026, 2, 1, tzinfo=UTC),
                    summary="测试外部信息用于验证分析快照。",
                    key_facts=["行业需求变化需要结合公告和财务数据继续复核"],
                    impact_direction="mixed",
                    importance_score=0.62,
                    credibility_score=0.55,
                    tags=["测试", "行业"],
                    requires_review=True,
                    analysis_status="model_analyzed",
                    analysis_note="测试外部信息用于验证分析快照。",
                    raw_snapshot={"title": "测试行业证据已入库"},
                ),
            ]
        )
        session.commit()


class FakeAnalystGateway:
    model_name = "fake-analyst-model"

    def generate_structured(self, **kwargs):
        schema = kwargs["schema"]
        return schema.model_validate(
            {
                "analyst_profile": "buffett",
                "overview": "现金流质量较好，但证据仍需补充。",
                "profile_fit_score": 0.68,
                "confidence": 0.73,
                "key_observations": ["种子财务显示利润和现金流匹配。"],
                "rule_checks": [
                    {
                        "rule_id": "durable_moat",
                        "status": "warn",
                        "summary": "有消费品标签和行业证据，但护城河证据还不足。",
                        "evidence_ids": [1],
                        "financial_periods": ["2025A"],
                        "announcement_ids": [1],
                    },
                    {
                        "rule_id": "owner_earnings_quality",
                        "status": "pass",
                        "summary": "净利润和经营现金流匹配度较好。",
                        "evidence_ids": [],
                        "financial_periods": ["2025A"],
                        "announcement_ids": [],
                    },
                    {
                        "rule_id": "capital_allocation",
                        "status": "unknown",
                        "summary": "管理层证据不足。",
                        "evidence_ids": [],
                        "financial_periods": [],
                        "announcement_ids": [],
                    },
                    {
                        "rule_id": "management_candor",
                        "status": "unknown",
                        "summary": "当前快照没有估值数据。",
                        "evidence_ids": [],
                        "financial_periods": [],
                        "announcement_ids": [],
                    },
                ],
                "supporting_evidence_ids": [1],
                "financial_observations": ["2025A 毛利率 58%。"],
                "announcement_observations": ["年度经营摘要已导入。"],
                "risk_flags": ["估值数据缺失。"],
                "counter_evidence": ["如果渠道库存恶化，护城河判断需要下调。"],
                "valuation_assumption_suggestions": ["后续估值模块应验证自由现金流可持续性。"],
                "data_gaps": ["缺少估值和更长周期财务数据。"],
                "follow_up_questions": ["现金流是否能连续多年覆盖利润？"],
            }
        )


class FakeRatioUnitMistakeGateway(FakeAnalystGateway):
    def generate_structured(self, **kwargs):
        output = super().generate_structured(**kwargs)
        return output.model_copy(
            update={
                "overview": "经营现金流/收入为0.28%，需要继续观察。",
                "financial_observations": ["经营现金流占收入为0.28%。"],
            }
        )


class FakeBatchGateway:
    model_name = "fake-batch-model"

    def __init__(self, fail_profile: str | None = None) -> None:
        self.fail_profile = fail_profile

    def generate_structured(self, **kwargs):
        user_prompt = str(kwargs["user_prompt"])
        if self.fail_profile and f'"id": "{self.fail_profile}"' in user_prompt:
            raise ModelNotConfiguredError("模型未配置，请先在 .env 中设置：MODEL_API_KEY")

        schema = kwargs["schema"]
        profile_id = _extract_profile_id_from_prompt(user_prompt)
        rule_ids = _extract_rule_ids_from_prompt(user_prompt)
        return schema.model_validate(
            {
                "analyst_profile": profile_id,
                "overview": f"{profile_id} 视角已生成。",
                "profile_fit_score": 0.6,
                "confidence": 0.7,
                "key_observations": [],
                "rule_checks": [
                    {
                        "rule_id": rule_id,
                        "status": "unknown",
                        "summary": f"{rule_id} 待继续验证。",
                        "evidence_ids": [],
                        "financial_periods": [],
                        "announcement_ids": [],
                    }
                    for rule_id in rule_ids
                ],
                "supporting_evidence_ids": [],
                "financial_observations": [],
                "announcement_observations": [],
                "risk_flags": [],
                "data_gaps": [],
                "follow_up_questions": [],
            }
        )


class FakeInvalidReferenceGateway:
    model_name = "fake-invalid-reference-model"

    def generate_structured(self, **kwargs):
        schema = kwargs["schema"]
        return schema.model_validate(
            {
                "analyst_profile": "buffett",
                "overview": "引用了不存在的证据。",
                "profile_fit_score": 0.5,
                "confidence": 0.5,
                "key_observations": [],
                "rule_checks": [
                    {
                        "rule_id": "durable_moat",
                        "status": "warn",
                        "summary": "测试无效 evidence 引用。",
                        "evidence_ids": [999999],
                        "financial_periods": ["2025A"],
                        "announcement_ids": [],
                    },
                    {
                        "rule_id": "owner_earnings_quality",
                        "status": "unknown",
                        "summary": "待验证。",
                        "evidence_ids": [],
                        "financial_periods": [],
                        "announcement_ids": [],
                    },
                    {
                        "rule_id": "capital_allocation",
                        "status": "unknown",
                        "summary": "待验证。",
                        "evidence_ids": [],
                        "financial_periods": [],
                        "announcement_ids": [],
                    },
                    {
                        "rule_id": "management_candor",
                        "status": "unknown",
                        "summary": "待验证。",
                        "evidence_ids": [],
                        "financial_periods": [],
                        "announcement_ids": [],
                    },
                ],
                "supporting_evidence_ids": [999999],
                "financial_observations": [],
                "announcement_observations": [],
                "risk_flags": [],
                "data_gaps": [],
                "follow_up_questions": [],
            }
        )


class FakePriceAwareAnalysisGateway:
    model_name = "fake-price-aware-analysis-model"

    def generate_structured(self, **kwargs):
        schema = kwargs["schema"]
        return schema.model_validate(
            {
                "analyst_profile": "buffett",
                "overview": (
                    "商业质量尚可，但当前市值、目标价线索和持仓成本会压缩安全边际，"
                    "需要把价格相关证据与长期现金流质量一起看。"
                ),
                "profile_fit_score": 0.5,
                "confidence": 0.5,
                "key_observations": ["目标价线索不能单独替代内在价值判断。"],
                "rule_checks": [
                    {
                        "rule_id": "durable_moat",
                        "status": "warn",
                        "summary": "护城河证据待复核。",
                        "evidence_ids": [],
                        "financial_periods": ["2025A"],
                        "announcement_ids": [],
                    },
                    {
                        "rule_id": "owner_earnings_quality",
                        "status": "unknown",
                        "summary": "待验证。",
                        "evidence_ids": [],
                        "financial_periods": [],
                        "announcement_ids": [],
                    },
                    {
                        "rule_id": "capital_allocation",
                        "status": "unknown",
                        "summary": "待验证。",
                        "evidence_ids": [],
                        "financial_periods": [],
                        "announcement_ids": [],
                    },
                    {
                        "rule_id": "management_candor",
                        "status": "warn",
                        "summary": "市值和持仓成本相关线索提示安全边际需要谨慎复核。",
                        "evidence_ids": [],
                        "financial_periods": [],
                        "announcement_ids": [],
                    },
                ],
                "supporting_evidence_ids": [],
                "financial_observations": ["财务快照可包含当前价格、目标价和市值字段。"],
                "announcement_observations": ["公告可包含目标价与持仓成本相关披露。"],
                "risk_flags": ["若估值证据过度依赖目标价，安全边际判断会失真。"],
                "data_gaps": ["需要进一步核验价格、市值和现金流假设之间的关系。"],
                "follow_up_questions": [],
            }
        )


class FakeUnconfiguredGateway:
    model_name = None

    def generate_structured(self, **kwargs):
        raise ModelNotConfiguredError(
            "模型未配置，请先在 .env 中设置：MODEL_BASE_URL, MODEL_API_KEY, MODEL_NAME"
        )


def _extract_profile_id_from_prompt(user_prompt: str) -> str:
    marker = '"id": "'
    marker_index = user_prompt.index(marker)
    start = marker_index + len(marker)
    end = user_prompt.index('"', start)
    return user_prompt[start:end]


def _extract_rule_ids_from_prompt(user_prompt: str) -> list[str]:
    rule_ids: list[str] = []
    rules_marker = '"rules": ['
    prompt_until_snapshot = user_prompt.split("数据快照:", maxsplit=1)[0]
    section_start = prompt_until_snapshot.index(rules_marker)
    rules_section = prompt_until_snapshot[section_start:]
    for line in rules_section.splitlines():
        stripped = line.strip()
        if not stripped.startswith('"id": "'):
            continue
        rule_id = stripped.split('"id": "', maxsplit=1)[1].split('"', maxsplit=1)[0]
        if rule_id not in rule_ids:
            rule_ids.append(rule_id)
    return rule_ids
