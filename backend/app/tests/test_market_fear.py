import json
from pathlib import Path

import httpx
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from app.data_sources.market_fear import (
    AkshareQvixProvider,
    CboeVixProvider,
    HangSengVhsiProvider,
)
from app.db.init_db import init_db
from app.db.models import MarketFearSnapshot
from app.db.session import create_sqlalchemy_engine, get_db
from app.main import create_app
from app.services import market_fear_service
from app.services.market_fear_service import get_market_fear, refresh_market_fear

FIXTURE_DIRECTORY = Path(__file__).parent / "fixtures" / "market_fear"


def _text(name: str) -> str:
    return (FIXTURE_DIRECTORY / name).read_text(encoding="utf-8")


def _http_provider(provider_class, fixture_name: str):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=_text(fixture_name), request=request)

    return provider_class(transport=httpx.MockTransport(handler))


def _providers():
    qvix_rows = json.loads(_text("qvix_records.json"))
    return {
        "A_SHARE": AkshareQvixProvider(fetcher=lambda: qvix_rows),
        "HK": _http_provider(HangSengVhsiProvider, "vhsi_chart.json"),
        "US": _http_provider(CboeVixProvider, "vix_history.csv"),
    }


def _make_environment(tmp_path: Path):
    engine = create_sqlalchemy_engine(
        f"sqlite:///{(tmp_path / 'market-fear.db').as_posix()}"
    )
    init_db(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    app = create_app(initialize_database=False)

    def override_get_db():
        with factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    return factory, app


def test_all_market_fear_providers_parse_fixed_fixtures() -> None:
    providers = _providers()
    qvix = providers["A_SHARE"].fetch_history()
    vhsi = providers["HK"].fetch_history()
    vix = providers["US"].fetch_history()

    assert qvix.indicator_code == "50ETF_QVIX"
    assert qvix.observations[-1].data_date.isoformat() == "2026-08-21"
    assert str(qvix.observations[-1].close) == "16.0"
    assert vhsi.indicator_code == "VHSI"
    assert str(vhsi.observations[-1].close) == "18.34"
    assert len(vhsi.observations) == 24
    assert vix.indicator_code == "VIX"
    assert str(vix.observations[-1].close) == "18"
    assert len(vix.raw_snapshot_hash) == 64


def test_market_fear_computes_metrics_and_preserves_stale_cache_on_failure(
    tmp_path: Path,
) -> None:
    factory, _ = _make_environment(tmp_path)
    with factory() as session:
        refreshed = refresh_market_fear(session, providers=_providers())
        assert refreshed.status == "success"
        assert [item.market for item in refreshed.items] == ["A_SHARE", "HK", "US"]
        assert all(item.freshness == "fresh" for item in refreshed.items)
        us = next(item for item in refreshed.items if item.market == "US")
        assert str(us.value) == "18.000000"
        assert str(us.daily_change) == "-1.000000"
        assert str(us.moving_average_20) == "21.550000"
        assert us.percentile_3y is not None
        assert us.temperature_score == us.percentile_3y
        a_share = next(item for item in refreshed.items if item.market == "A_SHARE")
        assert a_share.is_proxy is True
        assert a_share.proxy_notice == "第三方代理指标，非官方统一恐慌指数"
        cached = get_market_fear(session)
        assert cached.status == "success"

        class FailingProvider:
            def fetch_history(self):
                raise RuntimeError("fixture upstream unavailable")

        failed_refresh = refresh_market_fear(
            session,
            market="US",
            providers={"US": FailingProvider()},
        )
        assert failed_refresh.status == "partial"
        assert failed_refresh.items[0].freshness == "stale"
        assert failed_refresh.items[0].value == us.value
        assert "fixture upstream unavailable" in failed_refresh.items[0].refresh_error
        assert session.scalar(select(func.count()).select_from(MarketFearSnapshot)) == 3


def test_market_fear_api_reports_unavailable_and_refreshes_fixed_sources(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _, app = _make_environment(tmp_path)
    monkeypatch.setattr(market_fear_service, "DEFAULT_PROVIDERS", _providers())
    with TestClient(app) as client:
        empty = client.get("/api/investment-tools/market-fear")
        refreshed = client.post("/api/investment-tools/market-fear/refresh")
        cached = client.get("/api/investment-tools/market-fear")

    assert empty.status_code == 200
    assert empty.json()["status"] == "failed"
    assert all(item["freshness"] == "unavailable" for item in empty.json()["items"])
    assert refreshed.status_code == 200
    assert refreshed.json()["status"] == "success"
    assert all(
        item["fetched_at"].endswith(("Z", "+00:00"))
        for item in refreshed.json()["items"]
    )
    assert cached.json()["status"] == "success"
    assert "不代表价格方向" in cached.json()["notice"]
