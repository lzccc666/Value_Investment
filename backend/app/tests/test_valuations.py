from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app.analysis.analyst_profiles import get_analyst_profile, list_analyst_profiles
from app.db.init_db import init_db
from app.db.models import AnalysisRun, Company, FinancialStatement, InvestmentMemo, ValuationRun
from app.db.session import create_sqlalchemy_engine, get_db
from app.main import create_app
from app.services.valuation_service import (
    ValuationInputError,
    _calculate_owner_earnings,
    _derive_assumptions,
    _derive_normalized_financial_bases,
    build_valuation_snapshot,
    create_draft_valuation_run,
    recalculate_valuation_run,
)


def _make_test_db(tmp_path: Path):
    database_url = f"sqlite:///{(tmp_path / 'valuations.db').as_posix()}"
    engine = create_sqlalchemy_engine(database_url)
    init_db(engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def _override_db(app, session_factory) -> None:
    def override_get_db():
        with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db


def test_valuation_snapshot_is_price_blind_and_scrubs_memo_text(tmp_path: Path) -> None:
    session_factory = _make_test_db(tmp_path)
    with session_factory() as session:
        company = _seed_company(session)
        _seed_financials(session, company)
        _seed_memo(
            session,
            company,
            sections={
                "valuation_assumption_queue": [
                    {
                        "assumption_type": "growth",
                        "reason": "当前价格和市值不应进入 010。",
                        "current_price": 100,
                    },
                    {
                        "assumption_type": "free_cash_flow",
                        "reason": "自由现金流可作为估值基准。",
                    },
                ],
                "key_risks": ["竞争导致利润率下行"],
                "source_map": {"financial_periods": ["2025A"]},
            },
        )

        snapshot = build_valuation_snapshot(session, company)

    assert snapshot["price_blind_boundary"]["price_blind"] is True
    assert "current_price" not in snapshot["company"]
    assert "market_cap" not in snapshot["company"]
    assert "当前价格" not in str(snapshot["memo_inputs"])
    assert "市值" not in str(snapshot["memo_inputs"])
    assert "自由现金流可作为估值基准。" in str(snapshot["memo_inputs"])


def test_create_draft_waits_for_user_confirmation_before_calculation(
    tmp_path: Path,
) -> None:
    session_factory = _make_test_db(tmp_path)
    with session_factory() as session:
        company = _seed_ready_company(session)

        run = create_draft_valuation_run(session, company)

    assert run.status == "draft"
    assert run.price_blind is True
    assert run.memo_id is not None
    assert run.valuation_inputs["base_free_cash_flow"] == 80_000_000.0
    assert run.results["price_blind"] is True
    assert run.results["status"] == "needs_user_confirmation"
    assert run.results["method_results"] == []
    assert run.assumptions == {}
    assert run.model_suggested_assumptions["scenarios"]["base"]["discount_rate"] > 0
    assert run.model_suggested_assumptions["model_weights"] == {
        "owner_earnings": 0.35,
        "dcf": 0.35,
        "residual_income": 0.15,
        "dividend_discount": 0.10,
        "asset_value": 0.05,
    }

    with session_factory() as session:
        stored = session.get(ValuationRun, run.id)
        assert stored is not None
        confirmed = _confirm_run(session, stored)

    assert confirmed.results["status"] == "calculated_after_user_confirmation"
    method_statuses = {
        item["method"]: item["status"] for item in confirmed.results["method_results"]
    }
    assert method_statuses == {
        "dcf": "success",
        "owner_earnings": "success",
        "residual_income": "success",
        "dividend_discount": "success",
        "asset_value": "success",
    }
    method_applicability = {
        item["method"]: item["applicability"] for item in confirmed.results["method_results"]
    }
    assert method_applicability == {
        "dcf": 0.35,
        "owner_earnings": 0.35,
        "residual_income": 0.15,
        "dividend_discount": 0.10,
        "asset_value": 0.05,
    }
    assert confirmed.methods["base_weights"] == {
        "owner_earnings": 0.35,
        "dcf": 0.35,
        "residual_income": 0.15,
        "dividend_discount": 0.10,
        "asset_value": 0.05,
    }
    intrinsic_value_range = confirmed.results["intrinsic_value_range"]
    assert intrinsic_value_range["total_equity_value"]["base"] > 0
    first_weight = confirmed.results["model_weighting"][0]
    assert "components" in first_weight
    assert first_weight["components"]["applicability"] > 0
    assert first_weight["components"]["baseline_weight"] > 0
    assert first_weight["components"]["available_baseline_weight"] == pytest.approx(
        first_weight["components"]["baseline_weight"]
    )
    assert first_weight["components"]["weighting_policy"] == "configured_available_baseline"
    assert {
        item["method"]: item["weight"] for item in confirmed.results["model_weighting"]
    } == pytest.approx(
        {
            "dcf": 0.35,
            "owner_earnings": 0.35,
            "residual_income": 0.15,
            "dividend_discount": 0.10,
            "asset_value": 0.05,
        }
    )
    assert all(
        set(item["components"])
        == {
            "applicability",
            "baseline_weight",
            "available_baseline_weight",
            "weighting_policy",
        }
        for item in confirmed.results["model_weighting"]
    )
    assert confirmed.confidence is not None


def test_user_can_adjust_model_weights_before_valuation(tmp_path: Path) -> None:
    session_factory = _make_test_db(tmp_path)
    configured_weights = {
        "owner_earnings": 0.25,
        "dcf": 0.55,
        "residual_income": 0.10,
        "dividend_discount": 0.05,
        "asset_value": 0.05,
    }
    with session_factory() as session:
        company = _seed_ready_company(session)
        draft = create_draft_valuation_run(session, company)
        confirmed = recalculate_valuation_run(
            session,
            draft,
            user_assumptions={
                "scenarios": draft.model_suggested_assumptions["scenarios"],
                "model_weights": configured_weights,
            },
        )

    assert confirmed.assumptions["model_weights"] == configured_weights
    assert confirmed.methods["base_weights"] == configured_weights
    assert confirmed.methods["default_base_weights"] == {
        "owner_earnings": 0.35,
        "dcf": 0.35,
        "residual_income": 0.15,
        "dividend_discount": 0.10,
        "asset_value": 0.05,
    }
    assert {
        item["method"]: item["weight"] for item in confirmed.results["model_weighting"]
    } == pytest.approx(configured_weights)


def test_residual_income_dividend_discount_and_asset_value_are_calculated(
    tmp_path: Path,
) -> None:
    session_factory = _make_test_db(tmp_path)
    with session_factory() as session:
        company = _seed_ready_company(session)
        draft = create_draft_valuation_run(session, company)
        confirmed = _confirm_run(session, draft)

    assert confirmed.methods["selected_methods"] == [
        "dcf",
        "owner_earnings",
        "residual_income",
        "dividend_discount",
        "asset_value",
    ]
    assert confirmed.methods["reserved_methods"] == []
    methods = {item["method"]: item for item in confirmed.results["method_results"]}
    for method in ("residual_income", "dividend_discount", "asset_value"):
        assert methods[method]["status"] == "success"
        assert methods[method]["scenario_values"]["base"] > 0
        assert methods[method]["per_share_values"]["base"] > 0
        assert methods[method]["calculation_basis"]["formula"]

    residual_basis = methods["residual_income"]["calculation_basis"]
    assert residual_basis["components"]["shareholders_equity"] == 1_000_000_000
    assert residual_basis["components"]["base_net_profit"] == 100_000_000

    dividend_basis = methods["dividend_discount"]["calculation_basis"]
    assert dividend_basis["components"]["base_dividend"] == 30_000_000

    asset_basis = methods["asset_value"]["calculation_basis"]["scenario_basis"]["base"]
    assert asset_basis["total_assets"] == 1_500_000_000
    assert asset_basis["total_liabilities"] == 500_000_000
    assert methods["asset_value"]["key_assumptions"] == {
        "conservative": {"non_cash_asset_haircut": 0.60},
        "base": {"non_cash_asset_haircut": 0.80},
        "optimistic": {"non_cash_asset_haircut": 1.00},
    }
    assert methods["asset_value"]["scenario_values"]["conservative"] == pytest.approx(480_000_000)
    assert methods["asset_value"]["scenario_values"]["base"] == pytest.approx(740_000_000)
    assert methods["asset_value"]["scenario_values"]["optimistic"] == pytest.approx(1_000_000_000)


def test_model_weights_require_100_percent_and_positive_available_weight(
    tmp_path: Path,
) -> None:
    session_factory = _make_test_db(tmp_path)
    with session_factory() as session:
        company = _seed_ready_company(session)
        draft = create_draft_valuation_run(session, company)
        scenarios = draft.model_suggested_assumptions["scenarios"]

        with pytest.raises(ValuationInputError, match="合计必须等于 100%"):
            recalculate_valuation_run(
                session,
                draft,
                user_assumptions={
                    "scenarios": scenarios,
                    "model_weights": {
                        "owner_earnings": 0.35,
                        "dcf": 0.45,
                        "residual_income": 0.15,
                        "dividend_discount": 0.10,
                        "asset_value": 0.05,
                    },
                },
            )

        sparse_company = _seed_company(session, ticker="SPARSE.US", name="Sparse Co")
        _seed_financials(session, sparse_company, include_balance_sheet=False)
        _seed_memo(session, sparse_company)
        sparse_draft = create_draft_valuation_run(session, sparse_company)
        sparse_scenarios = sparse_draft.model_suggested_assumptions["scenarios"]

        with pytest.raises(ValuationInputError, match="可计算模型的配置权重合计"):
            recalculate_valuation_run(
                session,
                sparse_draft,
                user_assumptions={
                    "scenarios": sparse_scenarios,
                    "model_weights": {
                        "owner_earnings": 0.0,
                        "dcf": 0.0,
                        "residual_income": 0.50,
                        "dividend_discount": 0.0,
                        "asset_value": 0.50,
                    },
                },
            )


def test_dcf_uses_annual_fcf_when_latest_period_is_interim(tmp_path: Path) -> None:
    session_factory = _make_test_db(tmp_path)
    with session_factory() as session:
        company = _seed_company(session, ticker="INTERIM.US", name="Interim Cash Flow")
        _seed_financials(session, company)
        session.add(
            FinancialStatement(
                company_id=company.id,
                period="2026H1",
                statement_type="main_financial_indicators",
                currency="CNY",
                fields={
                    "report_date": "2026-06-30",
                    "revenue": 600_000_000,
                    "net_profit": 70_000_000,
                    "gross_margin": 0.6,
                    "net_margin": 0.12,
                },
            )
        )
        session.add(
            FinancialStatement(
                company_id=company.id,
                period="2026H1",
                statement_type="cash_flow_statement",
                currency="CNY",
                fields={
                    "report_date": "2026-06-30",
                    "operating_cash_flow": 360_000_000,
                    "capital_expenditure": 60_000_000,
                    "free_cash_flow": 300_000_000,
                },
            )
        )
        session.commit()
        _seed_memo(session, company)

        run = create_draft_valuation_run(session, company)

    assert run.valuation_inputs["latest_period"] == "2026H1"
    assert run.valuation_inputs["latest_period_type"] == "half_year"
    assert run.valuation_inputs["latest_period_used_as_dcf_base"] is False
    assert run.valuation_inputs["base_free_cash_flow"] == 80_000_000.0
    assert run.valuation_inputs["normalization_method"] == "latest_annual_adjusted"
    gap_fields = {item["field"] for item in run.results["valuation_input_gaps"]}
    assert "ttm_free_cash_flow" in gap_fields


def test_interim_valuation_inputs_use_ttm_base_for_profit_and_owner_earnings(
    tmp_path: Path,
) -> None:
    session_factory = _make_test_db(tmp_path)
    with session_factory() as session:
        company = _seed_company(session, ticker="TTM.US", name="TTM Co")
        _seed_financials(session, company)
        session.add(
            FinancialStatement(
                company_id=company.id,
                period="2025H1",
                statement_type="main_financial_indicators",
                currency="CNY",
                fields={
                    "report_date": "2025-06-30",
                    "revenue": 400_000_000,
                    "net_profit": 30_000_000,
                    "deducted_net_profit": 29_000_000,
                },
            )
        )
        session.add(
            FinancialStatement(
                company_id=company.id,
                period="2025H1",
                statement_type="cash_flow_statement",
                currency="CNY",
                fields={
                    "report_date": "2025-06-30",
                    "operating_cash_flow": 30_000_000,
                    "capital_expenditure": 10_000_000,
                    "free_cash_flow": 20_000_000,
                    "depreciation_and_amortization": 2_000_000,
                    "working_capital_change": 3_000_000,
                    "dividend": 12_000_000,
                },
            )
        )
        session.add(
            FinancialStatement(
                company_id=company.id,
                period="2026H1",
                statement_type="main_financial_indicators",
                currency="CNY",
                fields={
                    "report_date": "2026-06-30",
                    "revenue": 700_000_000,
                    "net_profit": 80_000_000,
                    "deducted_net_profit": 79_000_000,
                },
            )
        )
        session.add(
            FinancialStatement(
                company_id=company.id,
                period="2026H1",
                statement_type="cash_flow_statement",
                currency="CNY",
                fields={
                    "report_date": "2026-06-30",
                    "operating_cash_flow": 120_000_000,
                    "capital_expenditure": 20_000_000,
                    "free_cash_flow": 100_000_000,
                    "depreciation_and_amortization": 3_000_000,
                    "working_capital_change": 4_000_000,
                    "dividend": 14_000_000,
                },
            )
        )
        session.commit()
        _seed_memo(session, company)

        run = create_draft_valuation_run(session, company)
        run = _confirm_run(session, run)

    assert run.valuation_inputs["base_period_method"] == "ttm_adjusted"
    assert run.valuation_inputs["base_revenue"] == 1_300_000_000.0
    assert run.valuation_inputs["base_net_profit"] == 150_000_000.0
    assert run.valuation_inputs["capital_expenditure"] == 50_000_000.0
    assert run.valuation_inputs["depreciation_and_amortization"] == 11_000_000.0
    assert run.valuation_inputs["working_capital_change"] == 6_000_000.0
    assert run.valuation_inputs["dividend"] == 32_000_000.0

    owner_method = next(
        item for item in run.results["method_results"] if item["method"] == "owner_earnings"
    )
    dividend_method = next(
        item for item in run.results["method_results"] if item["method"] == "dividend_discount"
    )
    expected_owner_base = 150_000_000 + 11_000_000 - 50_000_000
    expected_value = _manual_discount_cash_flow(
        base_cash_flow=expected_owner_base,
        growth_rate=run.assumptions["scenarios"]["base"]["owner_earnings_growth_rate"],
        discount_rate=run.assumptions["scenarios"]["base"]["discount_rate"],
        terminal_growth_rate=run.assumptions["scenarios"]["base"]["terminal_growth_rate"],
        cash=run.valuation_inputs["cash_and_equivalents"] or 0,
        debt=run.valuation_inputs["interest_bearing_debt"] or 0,
    )
    assert owner_method["scenario_values"]["base"] == pytest.approx(expected_value)
    assert owner_method["calculation_basis"]["base_cash_flow"] == expected_owner_base
    assert owner_method["calculation_basis"]["period_method"] == "ttm_adjusted"
    assert owner_method["calculation_basis"]["period_type"] == "ttm"
    assert (
        owner_method["calculation_basis"]["components"]["working_capital_cash_effect"] == 6_000_000
    )
    assert (
        owner_method["calculation_basis"]["components"]["working_capital_investment_deducted"]
        == 0.0
    )
    assert dividend_method["calculation_basis"]["components"]["base_dividend"] == 32_000_000.0
    assert dividend_method["calculation_basis"]["components"]["period_method"] == "ttm_adjusted"


def test_owner_earnings_rejects_unannualized_interim_base() -> None:
    result = _calculate_owner_earnings(
        {
            "base_net_profit": 50_000_000.0,
            "capital_expenditure": 8_000_000.0,
            "base_period_method": "latest_period",
            "base_period_type": "half_year",
        },
        {},
        [],
    )

    assert result["status"] == "needs_input"
    assert "TTM 或完整年度" in result["reason"]


def test_short_history_uses_available_annual_fcf_average(tmp_path: Path) -> None:
    session_factory = _make_test_db(tmp_path)
    with session_factory() as session:
        company = _seed_company(session, ticker="SHORT.US", name="Short History")
        _seed_financials(session, company)
        session.add(
            FinancialStatement(
                company_id=company.id,
                period="2024A",
                statement_type="main_financial_indicators",
                currency="CNY",
                fields={
                    "report_date": "2024-12-31",
                    "revenue": 900_000_000,
                    "net_profit": 90_000_000,
                },
            )
        )
        session.add(
            FinancialStatement(
                company_id=company.id,
                period="2024A",
                statement_type="cash_flow_statement",
                currency="CNY",
                fields={
                    "report_date": "2024-12-31",
                    "operating_cash_flow": 80_000_000,
                    "capital_expenditure": 40_000_000,
                    "free_cash_flow": 40_000_000,
                },
            )
        )
        session.commit()
        _seed_memo(session, company)

        run = create_draft_valuation_run(session, company)

    expected = ((0.50 * 80_000_000) + (0.30 * 40_000_000)) / 0.80
    assert run.valuation_inputs["base_free_cash_flow"] == pytest.approx(expected)
    assert run.valuation_inputs["normalization_method"] == "weighted_annual_available"
    assert run.valuation_inputs["normalization_confidence"] == "medium"
    gap_fields = {item["field"] for item in run.results["valuation_input_gaps"]}
    assert "normalized_free_cash_flow_history" in gap_fields


def test_shared_annual_normalization_calculates_owner_earnings_per_period() -> None:
    result = _derive_normalized_financial_bases(
        _financial_pack_from_series(
            latest_period="2025A",
            series={
                "net_profit": {"2025A": 100.0, "2024A": 80.0, "2023A": 60.0},
                "free_cash_flow": {"2025A": 80.0, "2024A": 60.0, "2023A": 50.0},
                "capital_expenditure": {"2025A": 20.0, "2024A": 15.0, "2023A": 10.0},
                "depreciation_and_amortization": {"2025A": 5.0, "2024A": 4.0, "2023A": 3.0},
                "working_capital_change": {"2025A": 3.0, "2024A": -2.0, "2023A": 1.0},
            },
        )
    )

    assert result["method"] == "weighted_annual_3y"
    assert result["year_weights"] == pytest.approx([0.50, 0.30, 0.20])
    assert result["metrics"]["net_profit"]["value"] == pytest.approx(86.0)
    assert result["metrics"]["free_cash_flow"]["value"] == pytest.approx(68.0)
    assert result["metrics"]["owner_earnings"]["value"] == pytest.approx(73.2)
    period_owners = [
        item["owner_earnings"]["value"] for item in result["audit"]["periods"]
    ]
    assert period_owners == pytest.approx([85.0, 67.0, 53.0])


def test_shared_annual_normalization_renormalizes_two_year_history() -> None:
    result = _derive_normalized_financial_bases(
        _financial_pack_from_series(
            latest_period="2025A",
            series={
                "net_profit": {"2025A": 100.0, "2024A": 80.0},
                "free_cash_flow": {"2025A": 80.0, "2024A": 60.0},
                "capital_expenditure": {"2025A": 20.0, "2024A": 15.0},
            },
        )
    )

    assert result["method"] == "weighted_annual_available"
    assert result["year_weights"] == pytest.approx([0.625, 0.375])
    assert result["metrics"]["net_profit"]["value"] == pytest.approx(92.5)
    assert "62.5%/37.5%" in result["warnings"][-1]


def test_shared_annual_normalization_one_year_is_low_confidence() -> None:
    result = _derive_normalized_financial_bases(
        _financial_pack_from_series(
            latest_period="2025A",
            series={
                "net_profit": {"2025A": 100.0},
                "free_cash_flow": {"2025A": 80.0},
                "capital_expenditure": {"2025A": 20.0},
            },
        )
    )

    assert result["method"] == "latest_annual_adjusted"
    assert result["confidence"] == "low"
    assert result["metrics"]["owner_earnings"]["value"] == pytest.approx(80.0)


def test_shared_normalization_refuses_unannualized_interim_without_ttm() -> None:
    result = _derive_normalized_financial_bases(
        _financial_pack_from_series(
            latest_period="2026H1",
            series={
                "net_profit": {"2026H1": 100.0},
                "free_cash_flow": {"2026H1": 80.0},
            },
        )
    )

    assert result["method"] is None
    assert result["values"]["net_profit"] is None
    assert result["values"]["free_cash_flow"] is None
    assert "不使用未年度化中报或季报" in result["warnings"][-1]


def test_fcf_cap_audits_same_normalized_profit_before_and_after_cap() -> None:
    result = _derive_normalized_financial_bases(
        _financial_pack_from_series(
            latest_period="2025A",
            series={
                "net_profit": {"2025A": 100.0, "2024A": 100.0, "2023A": 100.0},
                "free_cash_flow": {"2025A": 200.0, "2024A": 200.0, "2023A": 200.0},
                "capital_expenditure": {"2025A": 20.0, "2024A": 20.0, "2023A": 20.0},
            },
        )
    )

    fcf_metric = result["metrics"]["free_cash_flow"]
    assert fcf_metric["value"] == pytest.approx(130.0)
    assert fcf_metric["fcf_to_net_profit_before_cap"] == pytest.approx(2.0)
    assert fcf_metric["fcf_to_net_profit"] == pytest.approx(1.3)
    conversion = result["audit"]["fcf_conversion"]
    assert conversion["matched_normalized_net_profit"] == pytest.approx(100.0)
    assert conversion["normalized_fcf_before_cap"] == pytest.approx(200.0)
    assert conversion["normalized_fcf_after_cap"] == pytest.approx(130.0)
    assert conversion["fcf_to_net_profit_after_cap"] == pytest.approx(1.3)


def test_growth_basis_exposes_source_clamp_and_analyst_delta() -> None:
    assumptions = _derive_assumptions(
        {"financial_trends": {"revenue_cagr_3y": 0.04}},
        {},
        [],
        [],
    )

    growth_basis = assumptions["growth_basis"]
    assert growth_basis["raw_growth_rate"] == pytest.approx(0.04)
    assert growth_basis["growth_source"] == "revenue_cagr_3y"
    assert growth_basis["clamped_financial_base_growth_rate"] == pytest.approx(0.04)
    assert growth_basis["final_base_cash_flow_growth_rate"] == pytest.approx(
        growth_basis["clamped_financial_base_growth_rate"]
        + growth_basis["analyst_delta_cash_flow_growth_rate"]
    )


def test_010_uses_008_rule_matrix_and_ignores_009_signal_pack(tmp_path: Path) -> None:
    session_factory = _make_test_db(tmp_path)
    with session_factory() as session:
        company = _seed_company(session, ticker="SIGNAL.US", name="Signal Co")
        _seed_financials(session, company)
        _seed_analyst_run(
            session,
            company,
            profile_id="li_lu",
            statuses={
                "economic_knowability": "pass",
                "moat_growth_coexistence": "pass",
                "owner_governance": "pass",
                "permanent_loss_resilience": "fail",
            },
        )
        _seed_memo(
            session,
            company,
            sections={
                "valuation_assumption_queue": [],
                "key_risks": [],
                "counter_evidence": [],
                "data_gaps": [],
                "source_map": {"financial_periods": ["2025A"]},
                "valuation_signal_pack": {"analyst_signals": [{"all": "positive"}]},
            },
        )

        run = create_draft_valuation_run(session, company)
        confirmed = _confirm_run(session, run)

    assert "valuation_signal_pack" not in run.input_snapshot["memo_inputs"]
    adjustment = run.model_suggested_assumptions["analyst_parameter_matrix_snapshot"]
    assert adjustment["status_score_policy"]["fail"] == -2.0
    assert adjustment["source"] == "latest_successful_008_analyst_view_runs"
    assert adjustment["dimension_scores"]["permanent_loss_risk"] < 0
    assert adjustment["risk_score"] > 0
    assert adjustment["analyst_parameter_impact_scale"] == 2.0
    assert "analyst_method_weight_impact_scale" not in adjustment
    assert "method_multipliers" not in adjustment
    unscaled_delta_discount = (
        -0.018 * adjustment["quality_score"]
        + 0.030 * adjustment["risk_score"]
        + 0.012 * adjustment["dimension_disagreement_avg"]
    )
    assert adjustment["delta_discount"] == pytest.approx(
        adjustment["analyst_parameter_impact_scale"] * unscaled_delta_discount
    )
    assert any(
        item["rule_id"] == "permanent_loss_resilience" and item["status_score"] == -2.0
        for item in adjustment["rule_impacts"]
    )

    scenarios = confirmed.assumptions["scenarios"]
    spread = adjustment["scenario_spread"]
    assert scenarios["conservative"]["discount_rate"] == pytest.approx(
        scenarios["base"]["discount_rate"] + spread * 0.60
    )
    assert (
        scenarios["optimistic"]["terminal_growth_rate"] > scenarios["base"]["terminal_growth_rate"]
    )

    weighting = {item["method"]: item["weight"] for item in confirmed.results["model_weighting"]}
    assert weighting == pytest.approx(
        {
            "dcf": 0.35,
            "owner_earnings": 0.35,
            "residual_income": 0.15,
            "dividend_discount": 0.10,
            "asset_value": 0.05,
        }
    )


def test_analyst_weight_uses_confidence_and_profile_fit_only(tmp_path: Path) -> None:
    session_factory = _make_test_db(tmp_path)
    with session_factory() as session:
        company = _seed_ready_company(session, ticker="WEIGHT.US", name="Weight Co")
        _seed_analyst_run(
            session,
            company,
            profile_id="buffett",
            statuses={},
            profile_fit_score=0.8,
            data_confidence=0.6,
        )
        li_lu = get_analyst_profile("li_lu")
        assert li_lu is not None
        _seed_analyst_run(
            session,
            company,
            profile_id="li_lu",
            statuses={rule.id: "pass" for rule in li_lu.rules},
            profile_fit_score=0.4,
            data_confidence=0.2,
        )

        run = create_draft_valuation_run(session, company)

    snapshot = run.model_suggested_assumptions["analyst_parameter_matrix_snapshot"]
    weights = {item["profile_id"]: item for item in snapshot["analyst_weights"]}
    assert weights["buffett"]["known_rule_completeness"] == 0.0
    assert weights["buffett"]["price_blind_completeness"] == 1.0
    assert weights["buffett"]["raw_weight"] == pytest.approx(0.7)
    assert weights["li_lu"]["raw_weight"] == pytest.approx(0.3)
    assert weights["buffett"]["base_weight"] == pytest.approx(0.7 / 7.0)
    assert weights["li_lu"]["base_weight"] == pytest.approx(0.3 / 7.0)
    denominator = 0.7**2 + 0.3**2 + 6 * 1.0**2
    assert weights["buffett"]["weight"] == pytest.approx(0.7**2 / denominator)
    assert weights["li_lu"]["weight"] == pytest.approx(0.3**2 / denominator)


@pytest.mark.parametrize(
    ("status", "expected_margin"),
    [
        ("pass", 0.1),
        ("neutral", 0.22),
        ("unknown", 0.26),
        ("warn", 0.1 + (0.512 / 0.96) * 0.4),
        ("fail", 0.5),
    ],
)
def test_all_32_rules_compute_and_dynamic_margin_hits_policy_endpoints(
    tmp_path: Path, status: str, expected_margin: float
) -> None:
    session_factory = _make_test_db(tmp_path)
    with session_factory() as session:
        company = _seed_company(
            session,
            ticker=f"{status.upper()}.US",
            name=f"{status} policy",
            seed_analysts=False,
        )
        _seed_all_analyst_runs(session, company, status=status)
        _seed_financials(session, company)
        _seed_memo(session, company)
        run = create_draft_valuation_run(session, company)

    snapshot = run.model_suggested_assumptions["analyst_parameter_matrix_snapshot"]
    assert len(snapshot["rule_impacts"]) == 32
    assert all(item["calculation_role"] == "compute" for item in snapshot["rule_impacts"])
    assert all(item["price_blind_compatible"] is True for item in snapshot["rule_impacts"])
    assert len(snapshot["dynamic_safety_margin_contributions"]) == 32
    assert snapshot["dynamic_safety_margin"] == pytest.approx(expected_margin)
    assert run.results["dynamic_safety_margin"] == pytest.approx(expected_margin)
    policy = snapshot["dynamic_safety_margin_policy"]
    assert policy["raw_minimum"] == pytest.approx(0.0)
    assert policy["raw_maximum"] == pytest.approx(0.96)
    assert policy["minimum"] == pytest.approx(0.1)
    assert policy["maximum"] == pytest.approx(0.5)


def test_010_requires_all_eight_latest_successful_complete_analyst_runs(tmp_path: Path) -> None:
    session_factory = _make_test_db(tmp_path)
    with session_factory() as session:
        company = _seed_company(session, seed_analysts=False)
        for profile in list_analyst_profiles()[:-1]:
            _seed_analyst_run(
                session,
                company,
                profile_id=profile.id,
                statuses={rule.id: "neutral" for rule in profile.rules},
            )
        _seed_financials(session, company)
        _seed_memo(session, company)

        with pytest.raises(ValuationInputError, match="李录"):
            create_draft_valuation_run(session, company)

        li_lu = list_analyst_profiles()[-1]
        _seed_analyst_run(
            session,
            company,
            profile_id=li_lu.id,
            statuses={rule.id: "neutral" for rule in li_lu.rules},
        )
        latest_munger = _seed_analyst_run(
            session,
            company,
            profile_id="munger",
            statuses={},
        )
        latest_munger.status = "failed"
        session.commit()
        with pytest.raises(ValuationInputError, match="failed"):
            create_draft_valuation_run(session, company)

        latest_munger.status = "success"
        latest_munger.result = {
            **latest_munger.result,
            "rule_checks": latest_munger.result["rule_checks"][:3],
        }
        session.commit()
        with pytest.raises(ValuationInputError, match="=3"):
            create_draft_valuation_run(session, company)


def test_new_draft_rederives_latest_008_matrix_instead_of_using_stale_snapshot(
    tmp_path: Path,
) -> None:
    session_factory = _make_test_db(tmp_path)
    with session_factory() as session:
        company = _seed_ready_company(session, ticker="STALE.US", name="Stale Matrix")
        analyst_run = _seed_analyst_run(
            session,
            company,
            profile_id="buffett",
            statuses={"durable_moat": "pass"},
        )
        stale_result = dict(analyst_run.result)
        stale_result["valuation_parameter_matrix"] = {
            "source": "stale_buggy_snapshot",
            "analyst_items": [],
        }
        analyst_run.result = stale_result
        session.commit()

        run = create_draft_valuation_run(session, company)

    snapshot = run.model_suggested_assumptions["analyst_parameter_matrix_snapshot"]
    assert snapshot["has_signals"] is True
    moat = next(item for item in snapshot["rule_impacts"] if item["rule_id"] == "durable_moat")
    assert moat["calculation_role"] == "compute"
    assert moat["price_blind_compatible"] is True


def test_high_severity_gaps_reduce_confidence_and_remain_reviewable(tmp_path: Path) -> None:
    session_factory = _make_test_db(tmp_path)
    with session_factory() as session:
        incomplete_company = _seed_company(session, ticker="MISS.US", name="Missing Cash Flow")
        _seed_financials(
            session,
            incomplete_company,
            include_cash_flow=False,
            include_balance_sheet=True,
        )
        _seed_memo(session, incomplete_company)
        incomplete_run = create_draft_valuation_run(session, incomplete_company)
        incomplete_run = _confirm_run(session, incomplete_run)

        ready_company = _seed_ready_company(session, ticker="READY.US", name="Ready Co")
        ready_run = create_draft_valuation_run(session, ready_company)
        ready_run = _confirm_run(session, ready_run)

    assert incomplete_run.status == "draft"
    assert incomplete_run.confidence is not None
    assert ready_run.confidence is not None
    assert incomplete_run.confidence < ready_run.confidence
    assert any(
        "高严重度输入缺口" in reason for reason in incomplete_run.confidence_summary["reasons"]
    )


def test_recalculate_creates_new_draft_without_overwriting_source_run(
    tmp_path: Path,
) -> None:
    session_factory = _make_test_db(tmp_path)
    with session_factory() as session:
        company = _seed_ready_company(session)
        draft = create_draft_valuation_run(session, company)
        original = _confirm_run(session, draft)
        original_base_value = original.results["intrinsic_value_range"]["total_equity_value"][
            "base"
        ]

        recalculated = recalculate_valuation_run(
            session,
            original,
            user_assumptions={
                "scenarios": {
                    "base": {
                        "discount_rate": 0.14,
                        "terminal_growth_rate": 0.01,
                    }
                }
            },
            user_note="提高折现率复核",
        )
        refreshed_original = session.get(ValuationRun, original.id)

    assert refreshed_original is not None
    assert refreshed_original.status == "draft"
    assert recalculated.id != original.id
    assert recalculated.status == "draft"
    assert recalculated.user_adjusted_assumptions["scenarios"]["base"]["discount_rate"] == 0.14
    assert recalculated.assumptions["parameter_sources"]["user_adjusted"] == ["scenarios"]
    assert (
        recalculated.results["intrinsic_value_range"]["total_equity_value"]["base"]
        < original_base_value
    )


def test_valuation_api_creates_lists_and_recalculates(tmp_path: Path) -> None:
    session_factory = _make_test_db(tmp_path)
    app = create_app(initialize_database=False)
    _override_db(app, session_factory)
    with session_factory() as session:
        company = _seed_ready_company(session)
        company_id = company.id

    client = TestClient(app)
    draft_response = client.post(f"/api/companies/{company_id}/valuation-runs/draft", json={})
    assert draft_response.status_code == 200
    draft = draft_response.json()["item"]
    assert draft["price_blind"] is True
    assert draft["results"]["status"] == "needs_user_confirmation"
    assert draft["results"]["method_results"] == []

    latest_response = client.get(f"/api/companies/{company_id}/valuation-runs/latest")
    assert latest_response.status_code == 200
    assert latest_response.json()["item"]["id"] == draft["id"]

    recalc_response = client.post(
        f"/api/valuation-runs/{draft['id']}/recalculate",
        json={
            "assumptions": {
                "scenarios": draft["model_suggested_assumptions"]["scenarios"],
            }
        },
    )
    assert recalc_response.status_code == 200
    recalculated = recalc_response.json()["item"]
    assert recalculated["id"] != draft["id"]
    assert recalculated["results"]["status"] == "calculated_after_user_confirmation"

    removed_lock_response = client.post(f"/api/valuation-runs/{recalculated['id']}/lock")
    assert removed_lock_response.status_code == 404

    list_response = client.get(f"/api/companies/{company_id}/valuation-runs")
    assert list_response.status_code == 200
    assert list_response.json()["total"] == 2


def _manual_discount_cash_flow(
    *,
    base_cash_flow: float,
    growth_rate: float,
    discount_rate: float,
    terminal_growth_rate: float,
    cash: float,
    debt: float,
) -> float:
    discount_rate = max(discount_rate, terminal_growth_rate + 0.01)
    present_value = 0.0
    cash_flow = base_cash_flow
    for year in range(1, 6):
        cash_flow *= 1 + growth_rate
        present_value += cash_flow / ((1 + discount_rate) ** year)
    terminal_cash_flow = cash_flow * (1 + terminal_growth_rate)
    terminal_value = terminal_cash_flow / (discount_rate - terminal_growth_rate)
    present_value += terminal_value / ((1 + discount_rate) ** 5)
    return present_value + cash - debt


def _confirm_run(session, run: ValuationRun) -> ValuationRun:
    return recalculate_valuation_run(
        session,
        run,
        user_assumptions={
            "scenarios": run.model_suggested_assumptions["scenarios"],
        },
    )


def _seed_analyst_run(
    session,
    company: Company,
    *,
    profile_id: str,
    statuses: dict[str, str],
    profile_fit_score: float = 1.0,
    data_confidence: float = 1.0,
) -> AnalysisRun:
    profile = get_analyst_profile(profile_id)
    assert profile is not None
    run = AnalysisRun(
        company_id=company.id,
        run_type="analyst_view",
        analyst_profile=profile_id,
        run_version="008_v1",
        model_name="fake",
        prompt_version="analyst_view_v1",
        data_snapshot_hash=f"{profile_id}-hash",
        input_snapshot={},
        result={
            "profile_fit_score": profile_fit_score,
            "confidence": data_confidence,
            "rule_checks": [
                {
                    "rule_id": rule.id,
                    "status": statuses.get(rule.id, "unknown"),
                    "summary": rule.label,
                    "evidence_ids": [],
                    "announcement_ids": [],
                    "financial_periods": ["2025A"],
                }
                for rule in profile.rules
            ],
        },
        confidence=data_confidence,
        is_latest=True,
        status="success",
        created_at=datetime(2026, 8, 16, tzinfo=UTC),
    )
    session.add(run)
    session.commit()
    session.refresh(run)
    return run


def _seed_ready_company(
    session,
    *,
    ticker: str = "VALUE.US",
    name: str = "Value Co",
) -> Company:
    company = _seed_company(session, ticker=ticker, name=name)
    _seed_financials(session, company)
    _seed_memo(session, company)
    return company


def _seed_company(
    session,
    *,
    ticker: str = "TEST010.US",
    name: str = "测试公司",
    seed_analysts: bool = True,
) -> Company:
    company = Company(
        ticker=ticker,
        exchange="SSE",
        name=name,
        industry="消费",
        status="观察中",
        tags=["测试"],
        current_price=100.0,
        market_cap=100_000_000_000.0,
        pe_ttm=25.0,
    )
    session.add(company)
    session.commit()
    session.refresh(company)
    if seed_analysts:
        _seed_all_analyst_runs(session, company)
    return company


def _seed_all_analyst_runs(session, company: Company, *, status: str = "neutral") -> None:
    for profile in list_analyst_profiles():
        _seed_analyst_run(
            session,
            company,
            profile_id=profile.id,
            statuses={rule.id: status for rule in profile.rules},
        )


def _seed_financials(
    session,
    company: Company,
    *,
    include_cash_flow: bool = True,
    include_balance_sheet: bool = True,
) -> None:
    session.add(
        FinancialStatement(
            company_id=company.id,
            period="2025A",
            statement_type="main_financial_indicators",
            currency="CNY",
            fields={
                "report_date": "2025-12-31",
                "revenue": 1_000_000_000,
                "gross_profit": 600_000_000,
                "net_profit": 100_000_000,
                "deducted_net_profit": 95_000_000,
                "roe": 0.2,
                "gross_margin": 0.6,
                "net_margin": 0.1,
                "revenue_yoy": 0.05,
                "net_profit_yoy": 0.06,
            },
        )
    )
    if include_cash_flow:
        session.add(
            FinancialStatement(
                company_id=company.id,
                period="2025A",
                statement_type="cash_flow_statement",
                currency="CNY",
                fields={
                    "report_date": "2025-12-31",
                    "operating_cash_flow": 120_000_000,
                    "capital_expenditure": 40_000_000,
                    "free_cash_flow": 80_000_000,
                    "depreciation_and_amortization": 10_000_000,
                    "working_capital_change": 5_000_000,
                    "dividend": 30_000_000,
                },
            )
        )
    if include_balance_sheet:
        session.add(
            FinancialStatement(
                company_id=company.id,
                period="2025A",
                statement_type="balance_sheet",
                currency="CNY",
                fields={
                    "report_date": "2025-12-31",
                    "cash_and_equivalents": 200_000_000,
                    "interest_bearing_debt": 50_000_000,
                    "total_assets": 1_500_000_000,
                    "total_liabilities": 500_000_000,
                    "shareholders_equity": 1_000_000_000,
                    "shares_outstanding": 100_000_000,
                },
            )
        )
    session.commit()


def _financial_pack_from_series(*, latest_period: str, series: dict[str, dict[str, float]]) -> dict:
    return {
        "latest_period": latest_period,
        "financial_facts": {
            "series": {
                field: [
                    {"period": period, "value": value}
                    for period, value in values.items()
                ]
                for field, values in series.items()
            }
        },
    }


def _seed_memo(
    session,
    company: Company,
    *,
    sections: dict[str, object] | None = None,
) -> InvestmentMemo:
    run = AnalysisRun(
        company_id=company.id,
        run_type="investment_memo",
        analyst_profile="investment_committee",
        run_version="009_v1",
        model_name="fake",
        prompt_version="investment_memo_v1",
        data_snapshot_hash="memo-hash",
        input_snapshot={},
        result={},
        confidence=0.7,
        is_latest=True,
        status="success",
        created_at=datetime(2026, 8, 15, tzinfo=UTC),
    )
    session.add(run)
    session.flush()
    memo = InvestmentMemo(
        company_id=company.id,
        generation_run_id=run.id,
        version_no=1,
        editor_type="model",
        title="综合投资备忘录",
        conclusion="优质",
        sections=sections
        or {
            "valuation_assumption_queue": [
                {
                    "assumption_type": "free_cash_flow_growth",
                    "reason": "自由现金流增长应保持保守。",
                }
            ],
            "key_risks": ["增长放缓"],
            "counter_evidence": ["资本开支上升"],
            "data_gaps": [],
            "source_map": {"financial_periods": ["2025A"]},
        },
        markdown="不应读取 markdown 来计算估值。",
        source_analyst_run_ids=[],
        source_snapshot_hash="memo-hash",
        status="draft",
        is_latest=True,
        created_at=datetime(2026, 8, 15, tzinfo=UTC),
        updated_at=datetime(2026, 8, 15, tzinfo=UTC),
    )
    session.add(memo)
    session.commit()
    session.refresh(memo)
    return memo
