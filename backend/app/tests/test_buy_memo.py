from datetime import UTC, date, datetime
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.db.init_db import init_db
from app.db.models import (
    AnalysisRun,
    BuyMemoEntry,
    Company,
    InvestmentMemo,
    PriceDecisionRun,
    SecurityListing,
    ValuationRun,
)
from app.db.session import create_sqlalchemy_engine, get_db
from app.main import create_app


def test_buy_memo_imports_frozen_011_fields_and_survives_source_deletion(
    tmp_path: Path,
) -> None:
    factory, app = _make_environment(tmp_path)
    with factory() as session:
        company = session.scalar(select(Company).where(Company.ticker == "GOOGL.US"))
        assert company is not None
        listing = session.scalar(
            select(SecurityListing).where(SecurityListing.ticker == "GOOGL.US")
        )
        assert listing is not None
        memo = _seed_memo(session, company)
        valuation = _seed_valuation(session, company, memo)
        older = _seed_price_decision(
            session,
            company,
            listing,
            valuation,
            memo,
            version_no=1,
            intrinsic_value=120.0,
            buy_price=90.0,
        )
        latest = _seed_price_decision(
            session,
            company,
            listing,
            valuation,
            memo,
            version_no=2,
            intrinsic_value=125.5,
            buy_price=94.125,
        )

    with TestClient(app) as client:
        companies = client.get(
            "/api/investment-tools/buy-memo-companies",
            params={"q": "谷歌"},
        )
        assert companies.status_code == 200
        assert companies.json()["items"] == [
            {
                "company_id": company.id,
                "company_name": company.name,
                "primary_ticker": "GOOGL.US",
                "decision_count": 2,
            }
        ]

        decisions = client.get(
            f"/api/investment-tools/buy-memo-companies/{company.id}/price-decisions"
        )
        assert decisions.status_code == 200
        decision_items = decisions.json()["items"]
        assert [item["price_decision_run_id"] for item in decision_items] == [
            latest.id,
            older.id,
        ]
        assert decision_items[0]["base_intrinsic_value"] == "125.5"
        assert decision_items[0]["suggested_buy_price"] == "94.125"
        assert decision_items[0]["designed_safety_margin"] == "0.25"
        assert decision_items[0]["latest_report_period"] == "2026Q2"
        assert decision_items[0]["already_imported"] is False

        created = client.post(
            "/api/investment-tools/buy-memo-entries",
            json={"price_decision_run_id": latest.id},
        )
        assert created.status_code == 201
        entry_id = created.json()["id"]
        assert created.json()["price_decision_version_no"] == 2
        assert created.json()["listing_ticker"] == "GOOGL.US"
        assert created.json()["trading_currency"] == "USD"

        duplicate = client.post(
            "/api/investment-tools/buy-memo-entries",
            json={"price_decision_run_id": latest.id},
        )
        assert duplicate.status_code == 409

        decisions_after = client.get(
            f"/api/investment-tools/buy-memo-companies/{company.id}/price-decisions"
        ).json()["items"]
        assert decisions_after[0]["already_imported"] is True

    with factory() as session:
        source = session.get(PriceDecisionRun, latest.id)
        assert source is not None
        session.delete(source)
        session.commit()

    with TestClient(app) as client:
        entries = client.get("/api/investment-tools/buy-memo-entries")
        assert entries.status_code == 200
        item = entries.json()["items"][0]
        assert item["id"] == entry_id
        assert item["source_price_decision_run_id"] is None
        assert item["base_intrinsic_value"] == "125.50000000"
        assert item["suggested_buy_price"] == "94.12500000"
        assert item["latest_report_period"] == "2026Q2"

        deleted = client.delete(f"/api/investment-tools/buy-memo-entries/{entry_id}")
        assert deleted.status_code == 200
        assert deleted.json() == {"id": entry_id, "deleted": True}

    with factory() as session:
        assert session.get(BuyMemoEntry, entry_id) is None


def _make_environment(tmp_path: Path):
    engine = create_sqlalchemy_engine(
        f"sqlite:///{(tmp_path / 'buy-memo.db').as_posix()}"
    )
    init_db(engine)
    factory = sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
    )
    app = create_app(initialize_database=False)

    def override_get_db():
        with factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    return factory, app


def _seed_memo(session, company: Company) -> InvestmentMemo:
    run = AnalysisRun(
        company_id=company.id,
        run_type="investment_memo",
        run_version="009_v1",
        input_snapshot={},
        result={},
        status="success",
    )
    session.add(run)
    session.flush()
    memo = InvestmentMemo(
        company_id=company.id,
        generation_run_id=run.id,
        version_no=1,
        title="综合投资备忘录",
        conclusion="观察",
        sections={},
        source_analyst_run_ids=[],
        source_snapshot_hash="buy-memo-fixture",
        status="draft",
        is_latest=True,
    )
    session.add(memo)
    session.commit()
    return memo


def _seed_valuation(
    session,
    company: Company,
    memo: InvestmentMemo,
) -> ValuationRun:
    valuation = ValuationRun(
        company_id=company.id,
        memo_id=memo.id,
        input_snapshot={},
        input_snapshot_hash="valuation-buy-memo-fixture",
        valuation_inputs={"latest_period": "2026Q2"},
        results={"status": "calculated_after_user_confirmation"},
    )
    session.add(valuation)
    session.commit()
    return valuation


def _seed_price_decision(
    session,
    company: Company,
    listing: SecurityListing,
    valuation: ValuationRun,
    memo: InvestmentMemo,
    *,
    version_no: int,
    intrinsic_value: float,
    buy_price: float,
) -> PriceDecisionRun:
    run = PriceDecisionRun(
        company_id=company.id,
        valuation_run_id=valuation.id,
        memo_id=memo.id,
        listing_id=listing.id,
        version_no=version_no,
        input_snapshot={},
        input_snapshot_hash=f"decision-{version_no}",
        intrinsic_values_per_share={
            "conservative": intrinsic_value * 0.8,
            "base": intrinsic_value,
            "optimistic": intrinsic_value * 1.2,
        },
        valuation_currency="USD",
        trading_currency="USD",
        underlying_shares_per_listing_unit=1.0,
        fx_rate=1.0,
        current_price=100.0,
        market_data_updated_at=datetime.combine(date.today(), datetime.min.time(), UTC),
        suggested_safety_margin=0.25,
        effective_safety_margin=0.25,
        scenario_buy_prices={"base": buy_price},
        suggested_buy_price=buy_price,
        current_margin=0.2,
        price_status="低于内在价值但安全边际不足",
    )
    session.add(run)
    session.commit()
    return run
