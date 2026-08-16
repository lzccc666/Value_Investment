from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app.db.init_db import init_db
from app.db.models import AnalysisRun, Company, InvestmentMemo, PriceDecisionRun, ValuationRun
from app.db.session import create_sqlalchemy_engine, get_db
from app.main import create_app
from app.services.price_decision_service import determine_price_status


def _make_test_db(tmp_path: Path):
    database_url = f"sqlite:///{(tmp_path / 'price-decisions.db').as_posix()}"
    engine = create_sqlalchemy_engine(database_url)
    init_db(engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def _make_client(session_factory) -> TestClient:
    app = create_app(initialize_database=False)

    def override_get_db():
        with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app)


def test_create_uses_latest_calculated_valuation_and_deterministic_formula(
    tmp_path: Path,
) -> None:
    session_factory = _make_test_db(tmp_path)
    with session_factory() as session:
        company = _seed_company(session, price=80.0)
        memo = _seed_memo(session, company, score=0.2, margin=0.2)
        calculated = _seed_valuation(session, company, memo, calculated=True)
        _seed_valuation(session, company, memo, calculated=False)

    response = _make_client(session_factory).post(
        f"/api/companies/{company.id}/price-decision-runs",
        json={},
    )

    assert response.status_code == 200
    item = response.json()["item"]
    assert item["valuation_run_id"] == calculated.id
    assert item["memo_id"] == memo.id
    assert item["run_version"] == "011_v1"
    assert item["formula_version"] == "011_v1"
    assert item["intrinsic_values_per_share"] == {
        "conservative": 70.0,
        "base": 100.0,
        "optimistic": 130.0,
    }
    assert item["suggested_safety_margin"] == pytest.approx(0.2)
    assert item["safety_margin_override"] is None
    assert item["effective_safety_margin"] == pytest.approx(0.2)
    assert item["scenario_buy_prices"] == pytest.approx(
        {"conservative": 56.0, "base": 80.0, "optimistic": 104.0}
    )
    assert item["suggested_buy_price"] == pytest.approx(80.0)
    assert item["current_margin"] == pytest.approx(0.2)
    assert item["price_status"] == "达到目标安全边际"
    assert len(item["input_snapshot_hash"]) == 64


def test_override_margin_is_saved_separately_and_changes_price_status(tmp_path: Path) -> None:
    session_factory = _make_test_db(tmp_path)
    with session_factory() as session:
        company = _seed_company(session, price=95.0)
        memo = _seed_memo(session, company, score=-0.2, margin=0.25)
        valuation = _seed_valuation(session, company, memo, calculated=True)

    response = _make_client(session_factory).post(
        f"/api/companies/{company.id}/price-decision-runs",
        json={"valuation_run_id": valuation.id, "safety_margin_override": 0.1},
    )

    assert response.status_code == 200
    item = response.json()["item"]
    assert item["suggested_safety_margin"] == pytest.approx(0.25)
    assert item["safety_margin_override"] == pytest.approx(0.1)
    assert item["effective_safety_margin"] == pytest.approx(0.1)
    assert item["suggested_buy_price"] == pytest.approx(90.0)
    assert item["current_margin"] == pytest.approx(0.05)
    assert item["price_status"] == "低于内在价值但安全边际不足"

    invalid = _make_client(session_factory).post(
        f"/api/companies/{company.id}/price-decision-runs",
        json={"safety_margin_override": 0.51},
    )
    assert invalid.status_code == 422
    assert "0%-50%" in invalid.text


@pytest.mark.parametrize(
    ("current_price", "expected"),
    [
        (80.0, "达到目标安全边际"),
        (99.0, "低于内在价值但安全边际不足"),
        (100.0, "处于估值区间上半部"),
        (130.0, "处于估值区间上半部"),
        (131.0, "高于乐观内在价值"),
    ],
)
def test_price_status_boundaries(current_price: float, expected: str) -> None:
    assert determine_price_status(
        current_price=current_price,
        suggested_buy_price=80.0,
        base_intrinsic_value=100.0,
        optimistic_intrinsic_value=130.0,
    ) == expected


def test_rejects_cross_company_valuation_and_memo_relationships(tmp_path: Path) -> None:
    session_factory = _make_test_db(tmp_path)
    with session_factory() as session:
        company = _seed_company(session, ticker="ONE.US")
        other_company = _seed_company(session, ticker="TWO.US")
        other_memo = _seed_memo(session, other_company)
        other_valuation = _seed_valuation(session, other_company, other_memo, calculated=True)
        own_memo = _seed_memo(session, company)
        broken_valuation = _seed_valuation(session, company, own_memo, calculated=True)
        broken_valuation.memo_id = other_memo.id
        session.commit()

    client = _make_client(session_factory)
    wrong_valuation = client.post(
        f"/api/companies/{company.id}/price-decision-runs",
        json={"valuation_run_id": other_valuation.id},
    )
    assert wrong_valuation.status_code == 400
    assert wrong_valuation.json()["detail"] == "指定的 010 估值版本不属于当前公司。"

    wrong_memo = client.post(
        f"/api/companies/{company.id}/price-decision-runs",
        json={"valuation_run_id": broken_valuation.id},
    )
    assert wrong_memo.status_code == 400
    assert "归属关系不一致" in wrong_memo.json()["detail"]


@pytest.mark.parametrize(
    ("price", "has_time", "expected"),
    [
        (None, True, "缺少有效的当前价格"),
        (100.0, False, "缺少当前价格的更新时间"),
    ],
)
def test_missing_market_input_stops_creation(
    tmp_path: Path, price: float | None, has_time: bool, expected: str
) -> None:
    session_factory = _make_test_db(tmp_path)
    with session_factory() as session:
        company = _seed_company(session, price=price, has_market_time=has_time)
        memo = _seed_memo(session, company)
        _seed_valuation(session, company, memo, calculated=True)

    response = _make_client(session_factory).post(
        f"/api/companies/{company.id}/price-decision-runs", json={}
    )
    assert response.status_code == 400
    assert expected in response.json()["detail"]
    with session_factory() as session:
        assert session.query(PriceDecisionRun).count() == 0


def test_uncalculated_valuation_is_rejected_even_when_run_status_is_draft(tmp_path: Path) -> None:
    session_factory = _make_test_db(tmp_path)
    with session_factory() as session:
        company = _seed_company(session)
        memo = _seed_memo(session, company)
        valuation = _seed_valuation(session, company, memo, calculated=False)

    response = _make_client(session_factory).post(
        f"/api/companies/{company.id}/price-decision-runs",
        json={"valuation_run_id": valuation.id},
    )
    assert response.status_code == 400
    assert "估值记录本身可以保持 draft" in response.json()["detail"]


def test_old_bound_memo_without_margin_does_not_fall_back_to_latest_memo(tmp_path: Path) -> None:
    session_factory = _make_test_db(tmp_path)
    with session_factory() as session:
        company = _seed_company(session)
        old_memo = _seed_memo(session, company, margin=None)
        valuation = _seed_valuation(session, company, old_memo, calculated=True)
        _seed_memo(session, company, margin=0.2)

    response = _make_client(session_factory).post(
        f"/api/companies/{company.id}/price-decision-runs",
        json={"valuation_run_id": valuation.id},
    )
    assert response.status_code == 400
    assert "旧 Memo 没有动态安全边际" in response.json()["detail"]


def test_versions_latest_list_detail_and_soft_delete(tmp_path: Path) -> None:
    session_factory = _make_test_db(tmp_path)
    with session_factory() as session:
        company = _seed_company(session, price=80.0)
        memo = _seed_memo(session, company)
        valuation = _seed_valuation(session, company, memo, calculated=True)

    client = _make_client(session_factory)
    first = client.post(
        f"/api/companies/{company.id}/price-decision-runs",
        json={"valuation_run_id": valuation.id},
    ).json()["item"]
    second = client.post(
        f"/api/companies/{company.id}/price-decision-runs",
        json={"valuation_run_id": valuation.id, "safety_margin_override": 0.1},
    ).json()["item"]
    assert (first["version_no"], second["version_no"]) == (1, 2)

    listed = client.get(f"/api/companies/{company.id}/price-decision-runs").json()
    assert listed["total"] == 2
    assert [item["id"] for item in listed["items"]] == [second["id"], first["id"]]
    assert client.get(f"/api/price-decision-runs/{first['id']}").status_code == 200

    deleted = client.delete(f"/api/price-decision-runs/{second['id']}")
    assert deleted.status_code == 200
    assert deleted.json()["latest_price_decision_run_id"] == first["id"]
    assert client.get(
        f"/api/companies/{company.id}/price-decision-runs/latest"
    ).json()["item"]["id"] == first["id"]
    assert client.get(f"/api/companies/{company.id}/price-decision-runs").json()["total"] == 1
    deleted_detail = client.get(f"/api/price-decision-runs/{second['id']}").json()
    assert deleted_detail["status"] == "deleted"
    assert deleted_detail["deleted_at"] is not None


def test_creation_does_not_modify_bound_valuation_or_memo(tmp_path: Path) -> None:
    session_factory = _make_test_db(tmp_path)
    with session_factory() as session:
        company = _seed_company(session)
        memo = _seed_memo(session, company)
        valuation = _seed_valuation(session, company, memo, calculated=True)
        memo_before = _memo_snapshot(memo)
        valuation_before = _valuation_snapshot(valuation)

    response = _make_client(session_factory).post(
        f"/api/companies/{company.id}/price-decision-runs",
        json={"valuation_run_id": valuation.id},
    )
    assert response.status_code == 200

    with session_factory() as session:
        stored_memo = session.get(InvestmentMemo, memo.id)
        stored_valuation = session.get(ValuationRun, valuation.id)
        assert stored_memo is not None
        assert stored_valuation is not None
        assert _memo_snapshot(stored_memo) == memo_before
        assert _valuation_snapshot(stored_valuation) == valuation_before


def _seed_company(
    session,
    *,
    ticker: str = "DECISION.US",
    price: float | None = 80.0,
    has_market_time: bool = True,
) -> Company:
    company = Company(
        ticker=ticker,
        exchange="NYSE",
        name=ticker,
        current_price=price,
        market_data_updated_at=datetime(2026, 8, 16, 3, 0, tzinfo=UTC)
        if has_market_time
        else None,
    )
    session.add(company)
    session.commit()
    session.refresh(company)
    return company


def _seed_memo(
    session,
    company: Company,
    *,
    score: float = 0.1,
    margin: float | None = 0.2,
) -> InvestmentMemo:
    generation_run = AnalysisRun(
        company_id=company.id,
        run_type="investment_memo",
        run_version="009_v1",
        input_snapshot={},
        result={},
        status="success",
    )
    session.add(generation_run)
    session.flush()
    scorecard: dict[str, object] = {"total_score": score, "coverage": {"total_rules": 40}}
    if margin is not None:
        scorecard["suggested_safety_margin"] = margin
    memo = InvestmentMemo(
        company_id=company.id,
        generation_run_id=generation_run.id,
        version_no=1,
        title="综合投资备忘录",
        conclusion="需复核",
        sections={"analyst_scorecard": scorecard},
        source_analyst_run_ids=[],
        source_snapshot_hash=f"memo-{company.id}-{generation_run.id}",
        status="draft",
        is_latest=True,
    )
    session.add(memo)
    session.commit()
    session.refresh(memo)
    return memo


def _seed_valuation(
    session,
    company: Company,
    memo: InvestmentMemo,
    *,
    calculated: bool,
) -> ValuationRun:
    run = ValuationRun(
        company_id=company.id,
        memo_id=memo.id,
        run_version="010_v1",
        status="draft",
        price_blind=True,
        forbidden_price_inputs={"price_blind": True},
        input_snapshot={"memo_id": memo.id},
        input_snapshot_hash=f"valuation-{company.id}-{memo.id}-{calculated}",
        valuation_inputs={},
        model_suggested_assumptions={},
        user_adjusted_assumptions={},
        assumptions={},
        methods={},
        results={
            "status": "calculated_after_user_confirmation"
            if calculated
            else "needs_user_confirmation",
            "intrinsic_value_range": {
                "per_share_value": {
                    "conservative": 70.0,
                    "base": 100.0,
                    "optimistic": 130.0,
                }
            },
        },
        sensitivity={},
        confidence_summary={},
        source_map={"memo_id": memo.id},
    )
    session.add(run)
    session.commit()
    session.refresh(run)
    return run


def _memo_snapshot(memo: InvestmentMemo) -> dict[str, object]:
    return {
        "company_id": memo.company_id,
        "version_no": memo.version_no,
        "sections": deepcopy(memo.sections),
        "status": memo.status,
        "is_latest": memo.is_latest,
        "updated_at": memo.updated_at,
    }


def _valuation_snapshot(run: ValuationRun) -> dict[str, object]:
    return {
        "company_id": run.company_id,
        "memo_id": run.memo_id,
        "status": run.status,
        "results": deepcopy(run.results),
        "input_snapshot_hash": run.input_snapshot_hash,
        "updated_at": run.updated_at,
    }
