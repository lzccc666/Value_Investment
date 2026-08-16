import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from app.analysis.analyst_profiles import list_analyst_profiles
from app.analysis.model_gateway import ModelOutputValidationError
from app.db.init_db import init_db
from app.db.models import AnalysisRun, Company, InvestmentMemo
from app.db.session import create_sqlalchemy_engine, get_db
from app.main import create_app
from app.schemas.memo import InvestmentMemoOutput
from app.services.memo_service import (
    InvestmentMemoInsufficientSourcesError,
    archive_investment_memo,
    build_analyst_scorecard,
    build_investment_memo_snapshot,
    delete_investment_memo,
    get_latest_memo_for_valuation,
    run_company_investment_memo,
)


def test_analyst_scorecard_uses_equal_rule_weights_and_safety_margin_mapping() -> None:
    profiles = list_analyst_profiles()
    statuses = ("pass", "fail", "warn", "unknown")
    source_runs = []
    for index, profile in enumerate(profiles):
        status = statuses[index % len(statuses)]
        source_runs.append(
            {
                "run_id": index + 1,
                "analyst_profile": profile.id,
                "confidence": 0.55 + (index * 0.03),
                "profile_fit_score": 0.60 + (index * 0.025),
                "result": {
                    "rule_checks": [
                        {"rule_id": rule.id, "status": status} for rule in profile.rules
                    ]
                },
            }
        )

    scorecard = build_analyst_scorecard(source_runs)

    assert scorecard["status_score_policy"] == {
        "pass": 1.0,
        "warn": -0.3,
        "fail": -2.0,
        "unknown": -0.1,
    }
    assert scorecard["independent_from_valuation"] is True
    assert scorecard["coverage"] == {
        "successful_profiles": 10,
        "total_profiles": 10,
        "known_rules": 32,
        "total_rules": 40,
    }
    items = scorecard["analyst_items"]
    assert [item["rule_score_total"] for item in items[:4]] == [4.0, -8.0, -1.2, -0.4]
    assert sum(item["analyst_weight"] for item in items) == pytest.approx(1.0)
    assert [item["analyst_weight"] for item in items] == pytest.approx([0.1] * 10)
    assert [item["weighted_score"] for item in items[:4]] == pytest.approx(
        [0.1, -0.2, -0.03, -0.01]
    )
    assert scorecard["total_score"] == pytest.approx(
        sum(item["weighted_score"] for item in items)
    )
    assert scorecard["total_score"] == pytest.approx(-0.38)
    assert scorecard["suggested_safety_margin"] == pytest.approx(0.23)
    assert scorecard["score_range"] == {"minimum": -2.0, "maximum": 1.0}
    assert scorecard["weight_policy"] == {
        "mode": "equal_weight_per_rule",
        "rule_weight": 0.025,
        "total_rules": 40,
        "formula": "sum(rule_status_score * 1/40)",
        "uses_data_confidence": False,
        "uses_profile_fit_score": False,
    }


@pytest.mark.parametrize(
    ("status", "expected_score", "expected_margin"),
    (
        ("pass", 1.0, 0.0),
        ("unknown", -0.1, 0.1833333333),
        ("warn", -0.3, 0.2166666667),
        ("fail", -2.0, 0.5),
    ),
)
def test_analyst_scorecard_maps_pure_statuses_to_safety_margin(
    status: str,
    expected_score: float,
    expected_margin: float,
) -> None:
    source_runs = [
        {
            "run_id": index + 1,
            "analyst_profile": profile.id,
            "result": {
                "rule_checks": [
                    {"rule_id": rule.id, "status": status} for rule in profile.rules
                ]
            },
        }
        for index, profile in enumerate(list_analyst_profiles())
    ]

    scorecard = build_analyst_scorecard(source_runs)

    assert scorecard["total_score"] == pytest.approx(expected_score)
    assert scorecard["suggested_safety_margin"] == pytest.approx(expected_margin)


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
    assert first_run.prompt_version == "investment_memo_v1"
    assert first_memo.editor_type == "model"
    assert first_memo.parent_memo_id is None
    assert first_memo.change_note is None
    assert first_memo.status == "draft"
    assert first_memo.is_latest is False
    assert second_run.id != first_run.id
    assert second_memo.version_no == first_memo.version_no + 1
    assert second_memo.is_latest is True
    assert len(memos) == 2


def test_memo_generation_marks_valuation_signal_pack_deprecated(
    tmp_path: Path,
) -> None:
    session_factory = _make_test_db(tmp_path)
    with session_factory() as session:
        company = _seed_company_with_analyst_runs(
            session,
            profiles=["buffett", "fisher", "duan_yongping"],
        )

        _, memo = run_company_investment_memo(session, company, gateway=FakeMemoGateway())

    pack = memo.sections["valuation_signal_pack"]
    assert pack["price_blind_compatible"] is True
    assert pack["source"] == "deprecated_009_display_compatibility_only"
    assert pack["user_confirmation_required"] is True
    assert pack["analyst_signals"] == []
    scorecard = memo.sections["analyst_scorecard"]
    assert scorecard["source"] == "latest_successful_008_rule_checks"
    assert scorecard["coverage"]["successful_profiles"] == 3
    assert len(scorecard["analyst_items"]) == 10


def test_valuation_signal_pack_scrubs_price_anchors(tmp_path: Path) -> None:
    session_factory = _make_test_db(tmp_path)
    with session_factory() as session:
        company = _seed_company_with_analyst_runs(session, profiles=["buffett", "fisher"])

        _, memo = run_company_investment_memo(
            session,
            company,
            gateway=FakePriceAnchorMemoGateway(),
        )

    serialized = json.dumps(
        memo.sections["valuation_signal_pack"],
        ensure_ascii=False,
        sort_keys=True,
    ).lower()
    for forbidden in (
        "current_price",
        "historical_price",
        "market_cap",
        "valuation_multiple",
        "position_cost",
        "target_price",
        "market_sentiment",
        "目标价",
        "市值",
        "评级",
    ):
        assert forbidden not in serialized
    assert "price_blind_compatible" in serialized
    assert "deprecated_009_display_compatibility_only" in serialized


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


def test_memo_schema_accepts_common_model_aliases_without_executive_summary() -> None:
    output = InvestmentMemoOutput.model_validate(
        {
            "summary": "The company needs a valuation-input review.",
            "consensus": [
                {
                    "topic": "cash flow quality",
                    "assessment": "Multiple analyst views require cash flow checks.",
                    "profiles": ["buffett", "duan_yongping"],
                    "source_refs": {
                        "source_run_ids": ["11"],
                        "evidence_ids": ["2"],
                        "announcement_ids": ["3"],
                        "financial_periods": ["2025A"],
                    },
                }
            ],
            "valuation_assumptions": [
                {
                    "type": "base_free_cash_flow",
                    "rationale": "010 needs normalized free cash flow inputs.",
                    "inputs": "operating cash flow",
                    "sources": {"source_run_ids": [11]},
                }
            ],
            "analyst_valuation_matrix": {
                "price_blind_compatible": False,
                "source": "latest_successful_analyst_view_runs",
                "analyst_signals": [
                    {
                        "profile": "buffett",
                        "run_id": 11,
                        "confidence": 0.6,
                        "parameter_signals": [
                            {
                                "metric": "discount_rate",
                                "direction": "up",
                                "reason": "Risk needs user review.",
                                "source_map": {"source_run_ids": [11]},
                            }
                        ],
                    }
                ],
                "user_confirmation_required": False,
            },
            "sources": {"source_run_ids": [11]},
        }
    )

    assert output.executive_summary == "The company needs a valuation-input review."
    assert output.consensus_points[0].summary == (
        "Multiple analyst views require cash flow checks."
    )
    assert output.consensus_points[0].source_run_ids == [11]
    assert output.valuation_assumption_queue[0].assumption_type == "base_free_cash_flow"
    assert output.valuation_assumption_queue[0].needed_inputs == ["operating cash flow"]
    assert output.valuation_signal_pack.price_blind_compatible is True
    assert output.valuation_signal_pack.user_confirmation_required is True
    assert output.valuation_signal_pack.analyst_signals[0].profile_id == "buffett"
    assert output.valuation_signal_pack.analyst_signals[0].source_run_id == 11
    assert output.source_map.analyst_run_ids == [11]


def test_memo_schema_normalizes_model_valuation_signal_aliases() -> None:
    output = InvestmentMemoOutput.model_validate(
        {
            "summary": "Model output contains natural-language valuation signals.",
            "valuation_signal_pack": {
                "price_blind_compatible": False,
                "source": "latest_successful_analyst_view_runs",
                "analyst_signals": [
                    {
                        "profile": "duan_yongping",
                        "display_name": "段永平",
                        "run_id": "21",
                        "profile_fit_score": "80%",
                        "confidence": "70%",
                        "business_quality_signal": "较强",
                        "moat_durability_signal": "偏正面",
                        "growth_runway_signal": "偏正面",
                        "pricing_power_signal": "高",
                        "capital_intensity_signal": "低风险",
                        "cash_flow_reliability_signal": "稳定",
                        "balance_sheet_risk_signal": "较高风险",
                        "management_capital_allocation_signal": "不确定",
                        "cyclicality_signal": "较高风险",
                        "permanent_loss_risk_signal": "证据不足",
                        "valuation_methods": [
                            "现金流折现",
                            {
                                "valuation_method": "所有者盈余",
                                "direction": "提高",
                                "confidence": "75%",
                            },
                        ],
                        "parameter_signals": [
                            "折现率上调，需要用户复核",
                            {
                                "metric": "scenario_spread",
                                "direction": "扩大",
                                "magnitude": "较高",
                                "scenario": "保守",
                                "confidence": "65%",
                                "needs_review": False,
                            },
                        ],
                    }
                ],
                "consensus_parameter_impacts": ["现金流增长率需要保守复核"],
                "user_confirmation_required": False,
            },
        }
    )

    pack = output.valuation_signal_pack
    signal = pack.analyst_signals[0]
    method = signal.valuation_method_preference[0]
    second_method = signal.valuation_method_preference[1]
    impact = signal.parameter_impacts[1]

    assert pack.price_blind_compatible is True
    assert pack.user_confirmation_required is True
    assert signal.profile_id == "duan_yongping"
    assert signal.source_run_id == 21
    assert signal.profile_fit_score == 0.8
    assert signal.data_confidence == 0.7
    assert signal.business_quality_signal == "positive"
    assert signal.moat_durability_signal == "positive"
    assert signal.growth_runway_signal == "positive"
    assert signal.pricing_power_signal == "positive"
    assert signal.capital_intensity_signal == "negative"
    assert signal.cash_flow_reliability_signal == "neutral"
    assert signal.balance_sheet_risk_signal == "negative"
    assert signal.management_capital_allocation_signal == "unknown"
    assert signal.cyclicality_signal == "negative"
    assert signal.permanent_loss_risk_signal == "unknown"
    assert method.method == "dcf"
    assert method.direction == "neutral"
    assert method.reason == "现金流折现"
    assert second_method.method == "owner_earnings"
    assert second_method.direction == "up"
    assert second_method.confidence == 0.75
    assert signal.parameter_impacts[0].parameter == "review_parameter"
    assert signal.parameter_impacts[0].requires_user_review is True
    assert impact.direction == "widen"
    assert impact.magnitude == "high"
    assert impact.scenario == "conservative"
    assert impact.confidence == 0.65
    assert impact.requires_user_review is True
    assert pack.consensus_parameter_impacts[0].parameter == "review_parameter"
    assert pack.consensus_parameter_impacts[0].requires_user_review is True


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
