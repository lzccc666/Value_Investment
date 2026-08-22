from datetime import date
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app.data_sources.ecb_fx import EcbReferenceRateProvider
from app.db.init_db import init_db
from app.db.session import create_sqlalchemy_engine, get_db
from app.main import create_app
from app.market_data.contracts import (
    MarketDataRateLimitedError,
    MarketDataValidationError,
)
from app.services.fx_rate_service import get_latest_fx_rate, refresh_fx_rate

FIXTURE_DIRECTORY = Path(__file__).parent / "fixtures" / "ecb"


def _csv_fixture() -> str:
    return (FIXTURE_DIRECTORY / "cny_hkd_usd.csv").read_text(encoding="utf-8")


def _make_provider(tmp_path: Path, handler) -> EcbReferenceRateProvider:
    return EcbReferenceRateProvider(
        cache_directory=tmp_path / "ecb-cache",
        cache_ttl_seconds=3600,
        transport=httpx.MockTransport(handler),
    )


def test_ecb_cross_rate_uses_same_date_and_persists_calculation_audit(
    tmp_path: Path,
) -> None:
    request_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal request_count
        request_count += 1
        assert "/EXR/D.CNY+HKD.EUR.SP00.A" in str(request.url)
        assert request.url.params["endPeriod"] == "2026-08-14"
        return httpx.Response(200, text=_csv_fixture(), request=request)

    provider = _make_provider(tmp_path, handler)
    rate = provider.fetch_rate("CNY", "HKD", rate_date=date(2026, 8, 14))
    cached = provider.fetch_rate("CNY", "HKD", rate_date=date(2026, 8, 14))

    assert rate.rate == pytest.approx(9.0 / 7.8)
    assert rate.rate_date == date(2026, 8, 14)
    assert rate.source == "ecb_reference_cross"
    assert rate.raw_snapshot_hash
    assert rate.calculation_audit == {
        "formula": "quote_per_eur / base_per_eur",
        "base_currency": "CNY",
        "quote_currency": "HKD",
        "base_per_eur": 7.8,
        "quote_per_eur": 9.0,
        "common_rate_date": "2026-08-14",
        "series_key": "D.CNY+HKD.EUR.SP00.A",
        "purpose": "information_only_reference_rate",
    }
    assert cached.raw_snapshot_hash == rate.raw_snapshot_hash
    assert request_count == 1


def test_ecb_service_is_immutable_idempotent_and_rejects_identity_snapshot(
    tmp_path: Path,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=_csv_fixture(), request=request)

    provider = _make_provider(tmp_path, handler)
    engine = create_sqlalchemy_engine(f"sqlite:///{(tmp_path / 'fx.db').as_posix()}")
    init_db(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    with session_factory() as session:
        first = refresh_fx_rate(
            session,
            base_currency="CNY",
            quote_currency="HKD",
            rate_date=date(2026, 8, 14),
            provider=provider,
        )
        second = refresh_fx_rate(
            session,
            base_currency="CNY",
            quote_currency="HKD",
            rate_date=date(2026, 8, 14),
            provider=provider,
        )
        latest = get_latest_fx_rate(
            session, base_currency="CNY", quote_currency="HKD"
        )
        with pytest.raises(MarketDataValidationError, match="不创建或伪造"):
            refresh_fx_rate(
                session,
                base_currency="USD",
                quote_currency="USD",
                provider=provider,
            )

    assert first.id == second.id
    assert latest is not None
    assert latest.id == first.id
    assert latest.calculation_audit["common_rate_date"] == "2026-08-14"


def test_ecb_rate_limit_is_structured_and_offline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("app.data_sources.ecb_fx.time.sleep", lambda _: None)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, request=request)

    provider = _make_provider(tmp_path, handler)
    with pytest.raises(MarketDataRateLimitedError, match="429"):
        provider.fetch_rate("CNY", "HKD")


def test_ecb_rejects_currency_outside_first_release_scope(tmp_path: Path) -> None:
    provider = _make_provider(
        tmp_path,
        lambda request: httpx.Response(500, request=request),
    )
    with pytest.raises(MarketDataValidationError, match="GBP"):
        provider.fetch_rate("GBP", "USD")


def test_fx_rate_api_reads_latest_and_rejects_identity_snapshot(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=_csv_fixture(), request=request)

    engine = create_sqlalchemy_engine(f"sqlite:///{(tmp_path / 'fx-api.db').as_posix()}")
    init_db(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    with session_factory() as session:
        refresh_fx_rate(
            session,
            base_currency="CNY",
            quote_currency="HKD",
            rate_date=date(2026, 8, 14),
            provider=_make_provider(tmp_path, handler),
        )

    app = create_app(initialize_database=False)

    def override_get_db():
        with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as client:
        latest = client.get(
            "/api/fx-rates/latest",
            params={"base_currency": "CNY", "quote_currency": "HKD"},
        )
        identity = client.post(
            "/api/fx-rates/refresh",
            params={"base_currency": "USD", "quote_currency": "USD"},
        )

    assert latest.status_code == 200
    assert latest.json()["item"]["calculation_audit"]["formula"] == (
        "quote_per_eur / base_per_eur"
    )
    assert identity.status_code == 400
    assert identity.json()["detail"]["code"] == "validation_failed"
