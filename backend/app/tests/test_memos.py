import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from app.analysis.model_gateway import ModelOutputValidationError
from app.db.init_db import init_db
from app.db.models import AnalysisRun, Company, InvestmentMemo
from app.db.session import create_sqlalchemy_engine, get_db
from app.main import create_app
from app.schemas.memo import InvestmentMemoOutput
from app.services.memo_service import (
    InvestmentMemoInsufficientSourcesError,
    archive_investment_memo,
    build_investment_memo_snapshot,
    delete_investment_memo,
    get_latest_memo_for_valuation,
    run_company_investment_memo,
)


def _make_test_db(tmp_path: Path):
    database_url = f"sqlite:///{(tmp_path / 'memos.db').as_posix()}"
    engine = create_sqlalchemy_engine(database_url)
    init_db(engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def _override_db(app, session_factory) -> None:
    def override_get_db():
        with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db


def test_memo_generation_requires_at_least_two_successful_analyst_views(
    tmp_path: Path,
) -> None:
    session_factory = _make_test_db(tmp_path)
    with session_factory() as session:
        company = _seed_company_with_analyst_runs(session, profiles=["buffett"])

        with pytest.raises(InvestmentMemoInsufficientSourcesError):
            run_company_investment_memo(session, company, gateway=FakeMemoGateway())


def test_memo_snapshot_reads_latest_successful_analyst_views_and_failed_profiles(
    tmp_path: Path,
) -> None:
    session_factory = _make_test_db(tmp_path)
    with session_factory() as session:
        company = _seed_company_with_analyst_runs(session, profiles=["buffett", "fisher"])
        session.add(
            AnalysisRun(
                company_id=company.id,
                run_type="analyst_view",
                analyst_profile="peter_lynch",
                run_version="008_v1",
                prompt_version="analyst_view_v1",
                data_snapshot_hash="failed-hash",
                result={"error": "模型失败", "error_type": "ModelGatewayError"},
                status="failed",
                is_latest=True,
                created_at=datetime(2026, 8, 15, 2, 0, tzinfo=UTC),
            )
        )
        session.add(
            AnalysisRun(
                company_id=company.id,
                run_type="evidence_search",
                analyst_profile="evidence_search",
                result={"summary": "不应进入 009"},
                status="success",
                is_latest=True,
            )
        )
        session.commit()

        snapshot = build_investment_memo_snapshot(session, company)

    source_runs = snapshot["source_analyst_runs"]
    assert isinstance(source_runs, list)
    assert {item["analyst_profile"] for item in source_runs} == {"buffett", "fisher"}
    assert "不应进入 009" not in str(snapshot)
    assert "peter_lynch 最近失败" in snapshot["committee_ledger"]["missing_profiles"]


def test_memo_snapshot_excludes_retired_analyst_profiles(tmp_path: Path) -> None:
    session_factory = _make_test_db(tmp_path)
    with session_factory() as session:
        company = _seed_company_with_analyst_runs(
            session,
            profiles=["buffett", "fisher", "george_soros", "ray_dalio"],
        )

        snapshot = build_investment_memo_snapshot(session, company)

    source_runs = snapshot["source_analyst_runs"]
    assert isinstance(source_runs, list)
    assert [item["analyst_profile"] for item in source_runs] == ["buffett", "fisher"]
    assert "george_soros" not in str(snapshot)
    assert "ray_dalio" not in str(snapshot)


def test_memo_generation_creates_analysis_run_and_historical_versions(
    tmp_path: Path,
) -> None:
    session_factory = _make_test_db(tmp_path)
    with session_factory() as session:
        company = _seed_company_with_analyst_runs(session, profiles=["buffett", "fisher"])

        first_run, first_memo = run_company_investment_memo(
            session,
            company,
            gateway=FakeMemoGateway(summary="第一版综合备忘录。"),
        )
        second_run, second_memo = run_company_investment_memo(
            session,
            company,
            gateway=FakeMemoGateway(summary="第二版综合备忘录。"),
        )

        memos = session.scalars(
            select(InvestmentMemo)
            .where(InvestmentMemo.company_id == company.id)
            .order_by(InvestmentMemo.version_no.asc())
        ).all()

    assert first_run.run_type == "investment_memo"
    assert first_run.status == "success"
    assert first_run.prompt_version == "investment_memo_v2"
    assert first_memo.editor_type == "model"
    assert first_memo.parent_memo_id is None
    assert first_memo.change_note is None
    assert first_memo.status == "draft"
    assert first_memo.is_latest is False
    assert second_run.id != first_run.id
    assert second_memo.version_no == first_memo.version_no + 1
    assert second_memo.is_latest is True
    assert len(memos) == 2


def test_memo_generation_contains_narrative_only_without_numeric_score_layers(
    tmp_path: Path,
) -> None:
    session_factory = _make_test_db(tmp_path)
    with session_factory() as session:
        company = _seed_company_with_analyst_runs(
            session,
            profiles=["buffett", "fisher", "duan_yongping"],
        )

        _, memo = run_company_investment_memo(session, company, gateway=FakeMemoGateway())

    forbidden = {
        "valuation_signal_pack",
        "analyst_scorecard",
        "total_score",
        "weighted_score",
        "rule_score",
        "suggested_safety_margin",
    }
    serialized = json.dumps(memo.sections, ensure_ascii=False)
    assert all(name not in serialized for name in forbidden)
    assert memo.sections["executive_summary"]


def test_memo_output_with_price_anchor_is_rejected(tmp_path: Path) -> None:
    session_factory = _make_test_db(tmp_path)
    with session_factory() as session:
        company = _seed_company_with_analyst_runs(session, profiles=["buffett", "fisher"])

        with pytest.raises((ModelOutputValidationError, ValueError)):
            run_company_investment_memo(
                session,
                company,
                gateway=FakePriceAnchorMemoGateway(),
            )


def test_delete_latest_memo_recomputes_latest_for_valuation(tmp_path: Path) -> None:
    session_factory = _make_test_db(tmp_path)
    with session_factory() as session:
        company = _seed_company_with_analyst_runs(session, profiles=["buffett", "fisher"])
        _, first_memo = run_company_investment_memo(
            session,
            company,
            gateway=FakeMemoGateway(summary="第一版综合备忘录。"),
        )
        _, second_memo = run_company_investment_memo(
            session,
            company,
            gateway=FakeMemoGateway(summary="第二版综合备忘录。"),
        )

        latest_after_delete = delete_investment_memo(session, second_memo)
        latest_for_valuation = get_latest_memo_for_valuation(session, company_id=company.id)
        session.refresh(second_memo)

        delete_investment_memo(session, first_memo)
        empty_latest = get_latest_memo_for_valuation(session, company_id=company.id)

    assert latest_after_delete is not None
    assert latest_after_delete.id == first_memo.id
    assert latest_for_valuation is not None
    assert latest_for_valuation.id == first_memo.id
    assert second_memo.status == "deleted"
    assert second_memo.is_latest is False
    assert empty_latest is None


def test_archive_latest_memo_recomputes_latest_for_valuation(tmp_path: Path) -> None:
    session_factory = _make_test_db(tmp_path)
    with session_factory() as session:
        company = _seed_company_with_analyst_runs(session, profiles=["buffett", "fisher"])
        _, first_memo = run_company_investment_memo(
            session,
            company,
            gateway=FakeMemoGateway(summary="第一版综合备忘录。"),
        )
        _, second_memo = run_company_investment_memo(
            session,
            company,
            gateway=FakeMemoGateway(summary="第二版综合备忘录。"),
        )

        latest_after_archive = archive_investment_memo(session, second_memo)
        latest_for_valuation = get_latest_memo_for_valuation(session, company_id=company.id)
        session.refresh(second_memo)

    assert latest_after_archive is not None
    assert latest_after_archive.id == first_memo.id
    assert latest_for_valuation is not None
    assert latest_for_valuation.id == first_memo.id
    assert second_memo.status == "archived"
    assert second_memo.is_latest is False


def test_memo_generation_fails_when_model_references_unknown_source(
    tmp_path: Path,
) -> None:
    session_factory = _make_test_db(tmp_path)
    with session_factory() as session:
        company = _seed_company_with_analyst_runs(session, profiles=["buffett", "fisher"])

        with pytest.raises(ModelOutputValidationError):
            run_company_investment_memo(session, company, gateway=FakeInvalidMemoGateway())

        failed_run = session.scalar(
            select(AnalysisRun)
            .where(
                AnalysisRun.company_id == company.id,
                AnalysisRun.run_type == "investment_memo",
            )
            .order_by(AnalysisRun.id.desc())
        )
        memo_count = session.scalar(
            select(func.count())
            .select_from(InvestmentMemo)
            .where(InvestmentMemo.company_id == company.id)
        )

    assert failed_run is not None
    assert failed_run.status == "failed"
    assert failed_run.result["error_type"] == "ModelOutputValidationError"
    assert memo_count == 0


def test_memo_generation_fails_when_model_outputs_trade_action(tmp_path: Path) -> None:
    session_factory = _make_test_db(tmp_path)
    with session_factory() as session:
        company = _seed_company_with_analyst_runs(session, profiles=["buffett", "fisher"])

        with pytest.raises(ModelOutputValidationError):
            run_company_investment_memo(session, company, gateway=FakeTradeActionMemoGateway())


def test_memo_schema_rejects_legacy_numeric_and_signal_layers() -> None:
    for legacy_field in (
        "analyst_scorecard",
        "valuation_signal_pack",
        "total_score",
        "suggested_safety_margin",
    ):
        with pytest.raises(ValidationError):
            InvestmentMemoOutput.model_validate(
                {
                    "executive_summary": "只保留叙事综合。",
                    legacy_field: {},
                }
            )


def test_memo_api_generates_lists_and_deletes_history(tmp_path: Path, monkeypatch) -> None:
    session_factory = _make_test_db(tmp_path)
    with session_factory() as session:
        company = _seed_company_with_analyst_runs(session, profiles=["buffett", "fisher"])
        company_id = company.id

    from app.api.routes import memos as memo_routes

    def fake_run_company_investment_memo(db, company, user_note=None):
        return run_company_investment_memo(
            db,
            company,
            user_note=user_note,
            gateway=FakeMemoGateway(summary="API 生成综合备忘录。"),
        )

    monkeypatch.setattr(
        memo_routes,
        "run_company_investment_memo",
        fake_run_company_investment_memo,
    )
    app = create_app(initialize_database=False)
    _override_db(app, session_factory)

    with TestClient(app) as client:
        generate_response = client.post(
            f"/api/companies/{company_id}/investment-memos/generate",
            json={},
        )
        latest_response = client.get(f"/api/companies/{company_id}/investment-memos/latest")
        list_response = client.get(f"/api/companies/{company_id}/investment-memos")
        memo_id = generate_response.json()["memo"]["id"]
        delete_response = client.delete(f"/api/investment-memos/{memo_id}")
        latest_after_delete = client.get(f"/api/companies/{company_id}/investment-memos/latest")

    assert generate_response.status_code == 200
    assert generate_response.json()["memo"]["editor_type"] == "model"
    assert latest_response.status_code == 200
    assert latest_response.json()["item"]["id"] == memo_id
    assert list_response.status_code == 200
    assert list_response.json()["total"] == 1
    assert delete_response.status_code == 200
    assert delete_response.json()["deleted"] is True
    assert latest_after_delete.status_code == 200
    assert latest_after_delete.json()["item"] is None


def _seed_company_with_analyst_runs(
    session,
    *,
    profiles: list[str],
) -> Company:
    company = session.scalar(select(Company).where(Company.ticker == "600519.SH"))
    assert company is not None
    base_time = datetime(2026, 8, 15, 1, 0, tzinfo=UTC)
    for index, profile in enumerate(profiles, start=1):
        session.add(
            AnalysisRun(
                company_id=company.id,
                run_type="analyst_view",
                analyst_profile=profile,
                run_version="008_v1",
                prompt_version="analyst_view_v1",
                data_snapshot_hash=f"{profile}-hash",
                input_snapshot={"profile": profile},
                result=_analyst_result(profile, index),
                confidence=0.7,
                status="success",
                is_latest=True,
                created_at=base_time + timedelta(minutes=index),
            )
        )
    session.commit()
    session.refresh(company)
    return company


def _analyst_result(profile: str, index: int) -> dict[str, object]:
    return {
        "analyst_profile": profile,
        "overview": f"{profile} 认为现金流质量需要复核。",
        "profile_fit_score": 0.7,
        "confidence": 0.7,
        "key_observations": ["现金流质量需要复核。", f"{profile} 关注增长质量。"],
        "rule_checks": [
            {
                "rule_id": "quality",
                "status": "pass" if index == 1 else "warn",
                "summary": "利润与现金流匹配度仍需复核。",
                "evidence_ids": [index],
                "announcement_ids": [index],
                "financial_periods": ["2025A"],
            }
        ],
        "supporting_evidence_ids": [index],
        "financial_observations": ["2025A 毛利率较高。"],
        "announcement_observations": ["年度报告摘要已入库。"],
        "risk_flags": ["现金流恶化风险需要持续跟踪。"],
        "counter_evidence": ["若渠道库存恶化，增长质量需要下调。"],
        "valuation_assumption_suggestions": ["010 应复核自由现金流基准。"],
        "valuation_assumption_details": [
            {
                "assumption_type": "base_free_cash_flow",
                "scenario_bias": "review_only",
                "reason": "自由现金流是后续估值核心输入。",
                "needed_inputs": ["经营现金流", "资本开支"],
                "risk_adjustments": ["现金流波动时下调基准"],
                "source_refs": {
                    "evidence_ids": [index],
                    "announcement_ids": [index],
                    "financial_periods": ["2025A"],
                },
            }
        ],
        "data_gaps": ["缺少资本开支数据。"],
        "follow_up_questions": ["现金流是否能连续覆盖利润？"],
        "analysis_basis": {
            "external_evidence_ids": [index],
            "announcement_ids": [index],
            "financial_periods": ["2025A"],
        },
    }


class FakeMemoGateway:
    model_name = "fake-memo-model"

    def __init__(self, summary: str = "综合显示公司质量较高，但估值输入仍需复核。") -> None:
        self.summary = summary

    def generate_structured(self, **kwargs):
        schema = kwargs["schema"]
        snapshot = _snapshot_from_prompt(str(kwargs["user_prompt"]))
        source_run_ids = snapshot["committee_ledger"]["source_run_ids"]
        evidence_ids = snapshot["committee_ledger"]["shared_evidence_ids"]
        announcement_ids = snapshot["committee_ledger"]["shared_announcement_ids"]
        financial_periods = snapshot["committee_ledger"]["financial_periods"]
        return schema.model_validate(
            _memo_payload(
                summary=self.summary,
                source_run_ids=source_run_ids,
                evidence_ids=evidence_ids,
                announcement_ids=announcement_ids,
                financial_periods=financial_periods,
            )
        )


class FakeInvalidMemoGateway(FakeMemoGateway):
    def generate_structured(self, **kwargs):
        schema = kwargs["schema"]
        return schema.model_validate(
            _memo_payload(
                summary="引用不存在来源。",
                source_run_ids=[999999],
                evidence_ids=[],
                announcement_ids=[],
                financial_periods=[],
            )
        )


class FakeTradeActionMemoGateway(FakeMemoGateway):
    def generate_structured(self, **kwargs):
        schema = kwargs["schema"]
        payload = _memo_payload(
            summary="建议买入该公司。",
            source_run_ids=[],
            evidence_ids=[],
            announcement_ids=[],
            financial_periods=[],
        )
        return schema.model_validate(payload)


class FakePriceAnchorMemoGateway(FakeMemoGateway):
    def generate_structured(self, **kwargs):
        schema = kwargs["schema"]
        snapshot = _snapshot_from_prompt(str(kwargs["user_prompt"]))
        source_run_ids = snapshot["committee_ledger"]["source_run_ids"]
        evidence_ids = snapshot["committee_ledger"]["shared_evidence_ids"]
        announcement_ids = snapshot["committee_ledger"]["shared_announcement_ids"]
        financial_periods = snapshot["committee_ledger"]["financial_periods"]
        payload = _memo_payload(
            summary="price anchors must be removed from valuation signal pack.",
            source_run_ids=source_run_ids,
            evidence_ids=evidence_ids,
            announcement_ids=announcement_ids,
            financial_periods=financial_periods,
        )
        payload["valuation_signal_pack"] = {
            "price_blind_compatible": True,
            "source": "latest_successful_analyst_view_runs",
            "analyst_signals": [],
            "consensus_parameter_impacts": [
                {
                    "parameter": "discount_rate",
                    "direction": "up",
                    "magnitude": "low",
                    "scenario": "all",
                    "reason": "target_price and market_cap should not pass through",
                    "confidence": 0.4,
                    "requires_user_review": True,
                    "source_refs": {
                        "analyst_run_ids": source_run_ids,
                        "evidence_ids": evidence_ids,
                        "announcement_ids": announcement_ids,
                        "financial_periods": financial_periods,
                    },
                }
            ],
            "dissent_parameter_impacts": [],
            "risk_constraints": ["current_price and market_sentiment are anchors"],
            "data_gaps_for_valuation": ["目标价 and 市值 should be scrubbed"],
            "user_confirmation_required": True,
            "current_price": 1,
            "market_cap": 2,
        }
        return schema.model_validate(payload)


def _memo_payload(
    *,
    summary: str,
    source_run_ids: list[int],
    evidence_ids: list[int],
    announcement_ids: list[int],
    financial_periods: list[str],
) -> dict[str, object]:
    source_refs = {
        "analyst_run_ids": source_run_ids,
        "evidence_ids": evidence_ids,
        "announcement_ids": announcement_ids,
        "financial_periods": financial_periods,
    }
    return {
        "title": "综合投资备忘录",
        "research_conclusion": "需复核",
        "executive_summary": summary,
        "core_thesis": ["现金流质量是后续研究核心。"],
        "consensus_points": [
            {
                "topic": "现金流质量",
                "summary": "多个视角都要求复核现金流质量。",
                "supporting_profiles": ["buffett", "fisher"],
                "source_run_ids": source_run_ids,
                "evidence_ids": evidence_ids,
                "announcement_ids": announcement_ids,
                "financial_periods": financial_periods,
            }
        ],
        "dissent_points": [],
        "business_quality": ["商业质量需要结合更多证据复核。"],
        "financial_quality": ["财务质量以现金流复核为核心。"],
        "management_and_capital_allocation": [],
        "moat_and_growth": [],
        "key_risks": ["现金流恶化风险需要跟踪。"],
        "counter_evidence": ["渠道库存恶化会削弱增长判断。"],
        "data_gaps": ["缺少资本开支数据。"],
        "follow_up_questions": ["现金流是否能连续覆盖利润？"],
        "valuation_assumption_queue": [
            {
                "assumption_type": "base_free_cash_flow",
                "scenario_bias": "review_only",
                "reason": "自由现金流是后续估值核心输入。",
                "suggested_range": {},
                "needed_inputs": ["经营现金流", "资本开支"],
                "risk_adjustments": ["现金流波动时下调基准"],
                "source_refs": source_refs,
            }
        ],
        "watch_signals": ["后续财报现金流变化。"],
        "price_decision_status": "not_started",
        "prohibited_actions_note": (
            "本备忘录未生成买卖、持有、减仓、加仓或仓位建议，价格对照留给 011。"
        ),
        "source_map": source_refs,
        "confidence_summary": {"level": "medium", "reasons": ["证据仍需补充。"]},
    }


def _snapshot_from_prompt(user_prompt: str) -> dict[str, object]:
    if "Data snapshot:\n" in user_prompt:
        return json.loads(user_prompt.split("Data snapshot:\n", maxsplit=1)[1])
    if "数据快照:\n" in user_prompt:
        return json.loads(user_prompt.split("数据快照:\n", maxsplit=1)[1])
    marker = "数据快照:\n"
    return json.loads(user_prompt.split(marker, maxsplit=1)[1])
