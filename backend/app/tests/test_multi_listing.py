from copy import deepcopy
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.db.init_db import init_db
from app.db.models import (
    AnalysisRun,
    Company,
    FxRateSnapshot,
    InvestmentMemo,
    MarketSnapshot,
    SecurityListing,
    ValuationRun,
)
from app.db.session import create_sqlalchemy_engine
from app.services.companies import list_company_listings, set_primary_listing
from app.services.price_decision_service import (
    PriceDecisionInputError,
    create_price_decision_run,
)


def _make_test_db(tmp_path: Path):
    engine = create_sqlalchemy_engine(
        f"sqlite:///{(tmp_path / 'multi-listing.db').as_posix()}"
    )
    init_db(engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def test_alibaba_hk_ordinary_and_us_ads_freeze_independent_011_history(
    tmp_path: Path,
) -> None:
    session_factory = _make_test_db(tmp_path)
    with session_factory() as session:
        company, hk_listing, ads_listing, valuation = _seed_alibaba_context(session)
        hk_snapshot = _add_market_snapshot(session, hk_listing, price=140.0)
        ads_snapshot = _add_market_snapshot(session, ads_listing, price=145.0)
        hkd_fx = _add_fx(session, "CNY", "HKD", 1.1)
        usd_fx = _add_fx(session, "CNY", "USD", 0.14)

        hk_decision = create_price_decision_run(
            session,
            company,
            valuation_run_id=valuation.id,
            listing_id=hk_listing.id,
        )
        ads_decision = create_price_decision_run(
            session,
            company,
            valuation_run_id=valuation.id,
            listing_id=ads_listing.id,
        )
        frozen_hk = _decision_snapshot(hk_decision)
        frozen_ads = _decision_snapshot(ads_decision)

        assert hk_decision.market_snapshot_id == hk_snapshot.id
        assert hk_decision.fx_rate_snapshot_id == hkd_fx.id
        assert hk_decision.input_snapshot["fx_conversion"]["calculation_audit"] == {
            "formula": "quote_per_eur / base_per_eur"
        }
        assert hk_decision.underlying_shares_per_listing_unit == 1.0
        assert hk_decision.intrinsic_values_per_share["base"] == pytest.approx(110.0)
        assert ads_decision.market_snapshot_id == ads_snapshot.id
        assert ads_decision.fx_rate_snapshot_id == usd_fx.id
        assert ads_decision.input_snapshot["fx_conversion"]["calculation_audit"] == {
            "formula": "quote_per_eur / base_per_eur"
        }
        assert ads_decision.underlying_shares_per_listing_unit == 8.0
        assert ads_decision.intrinsic_values_per_share["base"] == pytest.approx(112.0)
        assert hk_decision.version_no == ads_decision.version_no == 1

        set_primary_listing(session, company, ads_listing)
        session.refresh(company)
        session.refresh(hk_decision)
        session.refresh(ads_decision)

        assert company.id == valuation.company_id == hk_decision.company_id
        assert company.ticker == "BABA.US"
        assert company.exchange == "NYSE"
        assert _decision_snapshot(hk_decision) == frozen_hk
        assert _decision_snapshot(ads_decision) == frozen_ads

        ads_listing.underlying_shares_per_listing_unit = None
        session.commit()
        with pytest.raises(PriceDecisionInputError, match="证券单位换算比例"):
            create_price_decision_run(
                session,
                company,
                valuation_run_id=valuation.id,
                listing_id=ads_listing.id,
            )
        session.refresh(ads_decision)
        assert _decision_snapshot(ads_decision) == frozen_ads


def test_011_blocks_missing_and_stale_fx_without_guessing(tmp_path: Path) -> None:
    session_factory = _make_test_db(tmp_path)
    with session_factory() as session:
        company, _hk_listing, ads_listing, valuation = _seed_alibaba_context(session)
        _add_market_snapshot(session, ads_listing, price=145.0)

        with pytest.raises(PriceDecisionInputError, match="缺少 CNY->USD 汇率快照"):
            create_price_decision_run(
                session,
                company,
                valuation_run_id=valuation.id,
                listing_id=ads_listing.id,
            )

        _add_fx(
            session,
            "CNY",
            "USD",
            0.14,
            rate_date=date.today() - timedelta(days=30),
        )
        with pytest.raises(PriceDecisionInputError, match="汇率快照已过期"):
            create_price_decision_run(
                session,
                company,
                valuation_run_id=valuation.id,
                listing_id=ads_listing.id,
            )


def test_011_blocks_stale_listing_quote(tmp_path: Path) -> None:
    session_factory = _make_test_db(tmp_path)
    with session_factory() as session:
        company, _hk_listing, ads_listing, valuation = _seed_alibaba_context(session)
        _add_market_snapshot(
            session,
            ads_listing,
            price=145.0,
            fetched_at=datetime.now(UTC) - timedelta(days=30),
        )
        _add_fx(session, "CNY", "USD", 0.14)

        with pytest.raises(PriceDecisionInputError, match="行情快照已过期"):
            create_price_decision_run(
                session,
                company,
                valuation_run_id=valuation.id,
                listing_id=ads_listing.id,
            )


def _seed_alibaba_context(
    session,
) -> tuple[Company, SecurityListing, SecurityListing, ValuationRun]:
    company = session.scalar(select(Company).where(Company.canonical_key == "alibaba-group"))
    assert company is not None
    listings = list_company_listings(session, company.id)
    hk_listing = next(item for item in listings if item.ticker == "09988.HK")
    ads_listing = next(item for item in listings if item.ticker == "BABA.US")
    assert hk_listing.is_primary is True
    assert hk_listing.security_type == "common_stock"
    assert ads_listing.is_primary is False
    assert ads_listing.security_type == "ads"
    assert ads_listing.underlying_shares_per_listing_unit == 8.0

    generation_run = AnalysisRun(
        company_id=company.id,
        run_type="investment_memo",
        analyst_profile="investment_committee",
        run_version="009_v1",
        input_snapshot={"company_id": company.id},
        result={"narrative_only": True},
        status="success",
        is_latest=True,
    )
    session.add(generation_run)
    session.flush()
    memo = InvestmentMemo(
        company_id=company.id,
        generation_run_id=generation_run.id,
        version_no=1,
        editor_type="model",
        title="阿里巴巴多 Listing 固定样本",
        conclusion="继续研究",
        sections={"source_map": {"financial_periods": ["2026FY"]}},
        source_analyst_run_ids=[],
        source_snapshot_hash="alibaba-memo-fixture",
        status="draft",
        is_latest=True,
    )
    session.add(memo)
    session.flush()
    valuation = ValuationRun(
        company_id=company.id,
        memo_id=memo.id,
        run_version="010_v1",
        status="draft",
        price_blind=True,
        forbidden_price_inputs={"price_blind": True},
        input_snapshot={
            "company": {
                "id": company.id,
                "reporting_currency": "CNY",
            }
        },
        input_snapshot_hash="alibaba-valuation-fixture",
        valuation_inputs={"valuation_currency": "CNY"},
        model_suggested_assumptions={},
        user_adjusted_assumptions={},
        assumptions={},
        methods={},
        results={
            "status": "calculated_after_user_confirmation",
            "intrinsic_value_range": {
                "currency": "CNY",
                "per_share_value": {
                    "conservative": 70.0,
                    "base": 100.0,
                    "optimistic": 130.0,
                },
            },
            "dynamic_safety_margin": 0.25,
            "dynamic_safety_margin_formula_version": "010_dynamic_safety_margin_v2",
        },
        sensitivity={},
        confidence_summary={},
        source_map={"memo_id": memo.id},
        valuation_currency="CNY",
        share_basis_snapshot={
            "basis": "issuer_common_share",
            "status": "confirmed",
            "shares_outstanding": 18_000_000_000,
        },
    )
    session.add(valuation)
    session.commit()
    session.refresh(company)
    session.refresh(hk_listing)
    session.refresh(ads_listing)
    session.refresh(valuation)
    return company, hk_listing, ads_listing, valuation


def _add_market_snapshot(
    session,
    listing: SecurityListing,
    *,
    price: float,
    fetched_at: datetime | None = None,
) -> MarketSnapshot:
    observed_at = fetched_at or datetime.now(UTC)
    snapshot = MarketSnapshot(
        listing_id=listing.id,
        price=price,
        currency=listing.trading_currency,
        price_as_of=observed_at,
        fetched_at=observed_at,
        source="fixture_quote",
        source_url=f"https://fixture.invalid/{listing.ticker}",
        raw_snapshot_hash=f"quote-{listing.id}-{observed_at.isoformat()}",
    )
    session.add(snapshot)
    session.commit()
    session.refresh(snapshot)
    return snapshot


def _add_fx(
    session,
    base: str,
    quote: str,
    rate: float,
    *,
    rate_date: date | None = None,
) -> FxRateSnapshot:
    snapshot = FxRateSnapshot(
        base_currency=base,
        quote_currency=quote,
        rate=rate,
        rate_date=rate_date or date.today(),
        fetched_at=datetime.now(UTC),
        source="fixture_ecb_cross",
        source_url="https://fixture.invalid/ecb",
        raw_snapshot_hash=f"fx-{base}-{quote}-{rate_date or date.today()}",
        calculation_audit={"formula": "quote_per_eur / base_per_eur"},
    )
    session.add(snapshot)
    session.commit()
    session.refresh(snapshot)
    return snapshot


def _decision_snapshot(run) -> dict[str, object]:
    return {
        "listing_id": run.listing_id,
        "market_snapshot_id": run.market_snapshot_id,
        "fx_rate_snapshot_id": run.fx_rate_snapshot_id,
        "version_no": run.version_no,
        "input_snapshot": deepcopy(run.input_snapshot),
        "issuer_values": deepcopy(run.issuer_intrinsic_values_per_share),
        "listing_values": deepcopy(run.intrinsic_values_per_share),
        "valuation_currency": run.valuation_currency,
        "trading_currency": run.trading_currency,
        "ratio": run.underlying_shares_per_listing_unit,
        "fx_rate": run.fx_rate,
        "current_price": run.current_price,
        "suggested_buy_price": run.suggested_buy_price,
        "price_status": run.price_status,
        "created_at": run.created_at,
    }
