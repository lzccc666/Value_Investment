from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.data_sources.eastmoney_security_catalog import FetchedSecurityCatalogItem
from app.db.init_db import init_db
from app.db.models import (
    Company,
    FxRateSnapshot,
    MarketSnapshot,
    PortfolioHolding,
    SecurityListing,
)
from app.db.session import create_sqlalchemy_engine, get_db
from app.main import create_app
from app.schemas.investment_tools import (
    AhListingImportRequest,
    PortfolioHoldingCreate,
    PortfolioOwnerCreate,
    PortfolioSnapshotCreate,
    SecUsListingImportRequest,
)
from app.services import portfolio_service
from app.services.portfolio_service import (
    create_holding,
    create_owner,
    create_snapshot,
    import_ah_listing,
    import_sec_us_listing,
    search_ah_listing_catalog,
    search_sec_us_listing_catalog,
    value_portfolio,
)


def _make_environment(tmp_path: Path):
    engine = create_sqlalchemy_engine(
        f"sqlite:///{(tmp_path / 'portfolio-tools.db').as_posix()}"
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


def test_portfolio_crud_decimal_validation_copy_and_delete_contract(
    tmp_path: Path,
) -> None:
    factory, app = _make_environment(tmp_path)
    with factory() as session:
        aapl = _listing(session, "AAPL.US")
        maotai = _listing(session, "600519.SH")

    with TestClient(app) as client:
        owner_response = client.post(
            "/api/investment-tools/portfolio-owners",
            json={"name": "本人", "owner_type": "self", "notes": "长期账户"},
        )
        assert owner_response.status_code == 201
        owner_id = owner_response.json()["id"]
        snapshot_response = client.post(
            f"/api/investment-tools/portfolio-owners/{owner_id}/snapshots",
            json={
                "title": "2026 年中持仓",
                "as_of_date": date.today().isoformat(),
                "base_currency": "CNY",
            },
        )
        assert snapshot_response.status_code == 201
        snapshot_id = snapshot_response.json()["id"]

        fractional = client.post(
            f"/api/investment-tools/portfolio-snapshots/{snapshot_id}/holdings",
            json={"listing_id": aapl.id, "quantity": "1.12345678"},
        )
        assert fractional.status_code == 201
        assert fractional.json()["quantity"] == "1.12345678"
        holding_id = fractional.json()["id"]
        assert client.post(
            f"/api/investment-tools/portfolio-snapshots/{snapshot_id}/holdings",
            json={"listing_id": aapl.id, "quantity": "2"},
        ).status_code == 409
        assert client.post(
            f"/api/investment-tools/portfolio-snapshots/{snapshot_id}/holdings",
            json={"listing_id": maotai.id, "quantity": "1.5"},
        ).status_code == 400
        assert client.post(
            f"/api/investment-tools/portfolio-snapshots/{snapshot_id}/holdings",
            json={"listing_id": maotai.id, "quantity": "100"},
        ).status_code == 201
        too_precise = client.patch(
            f"/api/investment-tools/portfolio-holdings/{holding_id}",
            json={"quantity": "1.123456789"},
        )
        assert too_precise.status_code == 422
        duplicate_edit = client.patch(
            f"/api/investment-tools/portfolio-holdings/{holding_id}",
            json={"listing_id": maotai.id},
        )
        assert duplicate_edit.status_code == 409

        copied = client.post(
            f"/api/investment-tools/portfolio-owners/{owner_id}/snapshots",
            json={
                "title": "2026 三季度持仓",
                "as_of_date": date.today().isoformat(),
                "base_currency": "USD",
                "copy_from_snapshot_id": snapshot_id,
            },
        )
        assert copied.status_code == 201
        copied_id = copied.json()["id"]
        copied_holdings = client.get(
            f"/api/investment-tools/portfolio-snapshots/{copied_id}/holdings"
        ).json()
        assert copied_holdings["total"] == 2
        assert client.delete(
            f"/api/investment-tools/portfolio-owners/{owner_id}"
        ).status_code == 409
        assert client.delete(
            f"/api/investment-tools/portfolio-snapshots/{copied_id}"
        ).status_code == 200
        assert client.delete(
            f"/api/investment-tools/portfolio-snapshots/{snapshot_id}"
        ).status_code == 200
        assert client.delete(
            f"/api/investment-tools/portfolio-owners/{owner_id}"
        ).status_code == 200

    with factory() as session:
        assert session.scalar(
            select(PortfolioHolding).where(PortfolioHolding.snapshot_id == snapshot_id)
        ) is None


def test_portfolio_listing_search_covers_common_names_tickers_and_multi_listing(
    tmp_path: Path,
) -> None:
    factory, app = _make_environment(tmp_path)
    expected = {
        "拼多多": "PDD.US",
        "阿里巴巴美股": "BABA.US",
        "circl": "CRCL.US",
        "泡泡玛特": "09992.HK",
        "BRKA": "BRK.A.US",
        "OXY": "OXY.US",
        "美国运通": "AXP.US",
        "BofA": "BAC.US",
        "雪佛龙": "CVX.US",
        "安达保险": "CB.US",
        "穆迪": "MCO.US",
        "卡夫亨氏": "KHC.US",
        "达美航空": "DAL.US",
        "天狼星XM": "SIRI.US",
        "CRDO": "CRDO.US",
    }

    with TestClient(app) as client:
        for query, ticker in expected.items():
            response = client.get(
                "/api/investment-tools/portfolio-listings/search",
                params={"q": query},
            )
            assert response.status_code == 200
            assert response.json()["items"][0]["ticker"] == ticker
            if query == "BRKA":
                assert {item["ticker"] for item in response.json()["items"]} == {
                    "BRK.A.US"
                }

    with factory() as session:
        pdd = _listing(session, "PDD.US")
        brka = _listing(session, "BRK.A.US")
        brkb = _listing(session, "BRK.B.US")
        goog = _listing(session, "GOOG.US")
        googl = _listing(session, "GOOGL.US")

    assert pdd.security_type == "ads"
    assert pdd.underlying_shares_per_listing_unit == 4.0
    assert brka.company_id == brkb.company_id
    assert goog.company_id == googl.company_id

    with TestClient(app) as client:
        google = client.get(
            "/api/investment-tools/portfolio-listings/search",
            params={"q": "GOOG"},
        ).json()["items"]
    assert google[0]["ticker"] == "GOOG.US"
    assert {item["ticker"] for item in google[:2]} == {"GOOG.US", "GOOGL.US"}


def test_sec_us_catalog_search_and_import_reuses_issuer(tmp_path: Path) -> None:
    factory, _ = _make_environment(tmp_path)

    class FakeSecClient:
        def fetch_company_ticker_directory(self):
            return {
                "fields": ["cik", "name", "ticker", "exchange"],
                "data": [
                    [1652044, "Alphabet Inc.", "GOOG", "Nasdaq"],
                    [1234567, "Example Operating Corp", "EXM", "NYSE"],
                    [1067983, "Berkshire Hathaway Inc.", "BRK-B", "NYSE"],
                    [7654321, "Ignored OTC Corp", "OTCX", "OTC"],
                ],
            }

        def fetch_submissions(self, cik: str):
            assert cik == "0001234567"
            return {
                "entityType": "operating",
                "name": "Example Operating Corp",
                "tickers": ["EXM"],
                "exchanges": ["NYSE"],
            }

    class FakeCatalogClient:
        def search(self, query: str, *, limit: int = 20):
            assert limit == 50
            if query == "EXM":
                return [self._item()]
            assert query == "BRK-B"
            return [
                FetchedSecurityCatalogItem(
                    quote_id="106.BRK_B",
                    company_name="伯克希尔哈撒韦-B",
                    symbol="BRK_B",
                    ticker="BRK_B.US",
                    exchange="NYSE",
                    market="US",
                    trading_currency="USD",
                    security_type="common_stock",
                )
            ]

        def find_us_listing(self, symbol: str, exchange: str):
            assert (symbol, exchange) == ("EXM", "NYSE")
            return self._item()

        @staticmethod
        def _item():
            return FetchedSecurityCatalogItem(
                quote_id="106.EXM",
                company_name="示例运营公司",
                symbol="EXM",
                ticker="EXM.US",
                exchange="NYSE",
                market="US",
                trading_currency="USD",
                security_type="common_stock",
                pinyin="SLYYGS",
            )

    fake = FakeSecClient()
    catalog_fake = FakeCatalogClient()
    with factory() as session:
        results = search_sec_us_listing_catalog(
            session,
            "EXM",
            client=fake,
            catalog_client=catalog_fake,
        )
        assert [(item.ticker, item.exchange) for item in results] == [
            ("EXM.US", "NYSE")
        ]
        assert search_sec_us_listing_catalog(
            session,
            "BRK-B",
            client=fake,
            catalog_client=catalog_fake,
        ) == []

        imported = import_sec_us_listing(
            session,
            SecUsListingImportRequest(cik="1234567", symbol="exm"),
            client=fake,
            catalog_client=catalog_fake,
        )
        imported_again = import_sec_us_listing(
            session,
            SecUsListingImportRequest(cik="0001234567", symbol="EXM"),
            client=fake,
            catalog_client=catalog_fake,
        )

        listing = _listing(session, "EXM.US")
        assert imported.id == imported_again.id == listing.id
        assert listing.exchange == "NYSE"
        assert listing.underlying_shares_per_listing_unit is None
        assert listing.provider_identifiers["security_unit_status"] == (
            "unreviewed_sec_directory_import"
        )
        assert session.scalar(
            select(Company).where(Company.canonical_key == "sec-cik-0001234567")
        ) is not None


def test_sec_us_catalog_import_accepts_verified_foreign_private_issuer_ads(
    tmp_path: Path,
) -> None:
    factory, _ = _make_environment(tmp_path)

    class FakeSecClient:
        def fetch_company_ticker_directory(self):
            return {
                "fields": ["cik", "name", "ticker", "exchange"],
                "data": [[1744676, "Tencent Music Entertainment Group", "TME", "NYSE"]],
            }

        def fetch_submissions(self, cik: str):
            assert cik == "0001744676"
            return {
                "entityType": "other",
                "name": "Tencent Music Entertainment Group",
                "tickers": ["TME"],
                "exchanges": ["NYSE"],
                "filings": {"recent": {"form": ["20-F", "6-K"]}},
            }

    class FakeCatalogClient:
        def find_us_listing(self, symbol: str, exchange: str):
            assert (symbol, exchange) == ("TME", "NYSE")
            return FetchedSecurityCatalogItem(
                quote_id="106.TME",
                company_name="腾讯音乐",
                symbol="TME",
                ticker="TME.US",
                exchange="NYSE",
                market="US",
                trading_currency="USD",
                security_type="ads",
                pinyin="TXYL",
            )

    with factory() as session:
        imported = import_sec_us_listing(
            session,
            SecUsListingImportRequest(cik="1744676", symbol="TME"),
            client=FakeSecClient(),
            catalog_client=FakeCatalogClient(),
        )
        listing = _listing(session, "TME.US")
        assert imported.id == listing.id
        assert listing.security_type == "ads"
        assert listing.underlying_shares_per_listing_unit is None
        assert "腾讯音乐" in listing.company.aliases


def test_ah_catalog_search_import_and_cross_market_issuer_reuse(tmp_path: Path) -> None:
    factory, _ = _make_environment(tmp_path)
    candidates = [
        FetchedSecurityCatalogItem(
            quote_id="0.300001",
            company_name="示例科技",
            symbol="300001",
            ticker="300001.SZ",
            exchange="SZSE",
            market="A_SHARE",
            trading_currency="CNY",
            security_type="common_stock",
            pinyin="SLKJ",
        ),
        FetchedSecurityCatalogItem(
            quote_id="116.09901",
            company_name="示例科技-W",
            symbol="09901",
            ticker="09901.HK",
            exchange="HKEX",
            market="HK",
            trading_currency="HKD",
            security_type="common_stock",
            pinyin="SLKJ",
        ),
    ]

    class FakeCatalogClient:
        def search(self, query: str, *, limit: int = 20):
            assert query
            assert limit == 50
            return candidates

    fake = FakeCatalogClient()
    with factory() as session:
        results = search_ah_listing_catalog(session, "SLKJ", client=fake)
        assert {item.ticker for item in results} == {"300001.SZ", "09901.HK"}

        a_share = import_ah_listing(
            session,
            AhListingImportRequest(quote_id="0.300001"),
            client=fake,
        )
        hk_share = import_ah_listing(
            session,
            AhListingImportRequest(quote_id="116.09901"),
            client=fake,
        )
        hk_share_again = import_ah_listing(
            session,
            AhListingImportRequest(quote_id="116.09901"),
            client=fake,
        )

        assert a_share.company_id == hk_share.company_id
        assert hk_share.id == hk_share_again.id
        assert _listing(session, "300001.SZ").underlying_shares_per_listing_unit == 1.0
        assert _listing(session, "09901.HK").underlying_shares_per_listing_unit == 1.0


def test_ah_catalog_rest_endpoints_search_and_import(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _, app = _make_environment(tmp_path)
    candidate = FetchedSecurityCatalogItem(
        quote_id="0.920185",
        company_name="贝特瑞",
        symbol="920185",
        ticker="920185.BJ",
        exchange="BSE",
        market="A_SHARE",
        trading_currency="CNY",
        security_type="common_stock",
        pinyin="BTR",
    )

    class FakeCatalogClient:
        def search(self, query: str, *, limit: int = 20):
            assert query in {"BTR", "920185"}
            assert limit == 50
            return [candidate]

    monkeypatch.setattr(
        portfolio_service,
        "EastmoneySecurityCatalogClient",
        FakeCatalogClient,
    )
    with TestClient(app) as client:
        searched = client.get(
            "/api/investment-tools/portfolio-listings/ah-catalog/search",
            params={"q": "BTR"},
        )
        assert searched.status_code == 200
        assert searched.json()["items"][0]["ticker"] == "920185.BJ"

        imported = client.post(
            "/api/investment-tools/portfolio-listings/ah-catalog/import",
            json={"quote_id": "0.920185"},
        )
        assert imported.status_code == 201
        assert imported.json()["ticker"] == "920185.BJ"
        assert imported.json()["security_type"] == "common_stock"


def test_portfolio_owner_and_snapshot_order_is_persistent_and_validated(
    tmp_path: Path,
) -> None:
    _, app = _make_environment(tmp_path)
    with TestClient(app) as client:
        owner_ids = [
            client.post(
                "/api/investment-tools/portfolio-owners",
                json={"name": name, "owner_type": "investor"},
            ).json()["id"]
            for name in ["甲", "乙", "丙"]
        ]
        reordered_owner_ids = [owner_ids[2], owner_ids[0], owner_ids[1]]
        reordered = client.put(
            "/api/investment-tools/portfolio-owners/reorder",
            json={"ordered_ids": reordered_owner_ids},
        )
        assert reordered.status_code == 200
        assert [item["id"] for item in reordered.json()["items"]] == reordered_owner_ids
        assert [item["display_order"] for item in reordered.json()["items"]] == [0, 1, 2]
        assert [
            item["id"]
            for item in client.get(
                "/api/investment-tools/portfolio-owners"
            ).json()["items"]
        ] == reordered_owner_ids
        invalid_owner_order = client.put(
            "/api/investment-tools/portfolio-owners/reorder",
            json={"ordered_ids": owner_ids[:2]},
        )
        assert invalid_owner_order.status_code == 400

        owner_id = owner_ids[0]
        snapshot_ids = [
            client.post(
                f"/api/investment-tools/portfolio-owners/{owner_id}/snapshots",
                json={
                    "title": title,
                    "as_of_date": as_of_date,
                    "base_currency": "CNY",
                },
            ).json()["id"]
            for title, as_of_date in [
                ("一期", "2026-03-31"),
                ("二期", "2026-06-30"),
                ("三期", "2026-08-20"),
            ]
        ]
        reordered_snapshot_ids = [snapshot_ids[1], snapshot_ids[2], snapshot_ids[0]]
        reordered_snapshots = client.put(
            f"/api/investment-tools/portfolio-owners/{owner_id}/snapshots/reorder",
            json={"ordered_ids": reordered_snapshot_ids},
        )
        assert reordered_snapshots.status_code == 200
        assert [
            item["id"] for item in reordered_snapshots.json()["items"]
        ] == reordered_snapshot_ids
        persisted = client.get(
            f"/api/investment-tools/portfolio-owners/{owner_id}/snapshots"
        ).json()["items"]
        assert [item["id"] for item in persisted] == reordered_snapshot_ids
        assert [item["display_order"] for item in persisted] == [0, 1, 2]


def test_portfolio_valuation_handles_multi_listing_ads_fx_and_missing_data(
    tmp_path: Path,
) -> None:
    factory, _ = _make_environment(tmp_path)
    with factory() as session:
        owner = create_owner(
            session,
            PortfolioOwnerCreate(name="投资人甲", owner_type="investor"),
        )
        snapshot = create_snapshot(
            session,
            owner.id,
            PortfolioSnapshotCreate(
                title="阿里双市场",
                as_of_date=date.today(),
                base_currency="CNY",
            ),
        )
        alibaba = session.scalar(
            select(Company).where(Company.canonical_key == "alibaba-group")
        )
        assert alibaba is not None
        hk_listing = session.scalar(
            select(SecurityListing).where(
                SecurityListing.company_id == alibaba.id,
                SecurityListing.ticker == "09988.HK",
            )
        )
        ads_listing = session.scalar(
            select(SecurityListing).where(
                SecurityListing.company_id == alibaba.id,
                SecurityListing.ticker == "BABA.US",
            )
        )
        tencent = _listing(session, "00700.HK")
        assert hk_listing is not None and ads_listing is not None
        assert ads_listing.underlying_shares_per_listing_unit == 8.0
        create_holding(
            session,
            snapshot.id,
            PortfolioHoldingCreate(listing_id=hk_listing.id, quantity=Decimal("100")),
        )
        create_holding(
            session,
            snapshot.id,
            PortfolioHoldingCreate(
                listing_id=ads_listing.id,
                quantity=Decimal("2.50000000"),
            ),
        )
        create_holding(
            session,
            snapshot.id,
            PortfolioHoldingCreate(listing_id=tencent.id, quantity=Decimal("10")),
        )
        _add_market_snapshot(session, hk_listing, "80.25")
        _add_market_snapshot(session, ads_listing, "100.10")
        _add_fx(session, "HKD", "CNY", "0.91")
        _add_fx(session, "USD", "CNY", "7.12")

        valuation = value_portfolio(session, snapshot.id)
        by_ticker = {item.ticker: item for item in valuation.items}
        hk_item = by_ticker["09988.HK"]
        ads_item = by_ticker["BABA.US"]

        assert isinstance(hk_item.quantity, Decimal)
        assert hk_item.local_market_value == Decimal("8025.00000000")
        assert hk_item.quote_as_of is not None
        assert hk_item.quote_as_of.utcoffset() == timedelta(0)
        assert hk_item.base_market_value == Decimal("7302.750000000")
        assert ads_item.local_market_value == Decimal("250.250000000")
        assert ads_item.base_market_value == Decimal("1781.78000000000")
        assert ads_item.local_market_value != Decimal("2.5") * Decimal("8") * Decimal(
            "100.10"
        )
        assert hk_item.company_id == ads_item.company_id == alibaba.id
        assert valuation.priced_count == 2
        assert valuation.unpriced_count == 1
        assert valuation.valuation_status == "incomplete"
        assert [item.ticker for item in valuation.items] == [
            "09988.HK",
            "BABA.US",
            "00700.HK",
        ]
        assert by_ticker["00700.HK"].data_status == "missing_price"
        assert by_ticker["00700.HK"].base_market_value is None
        weight_sum = sum(
            (item.weight or Decimal("0")) for item in valuation.items
        )
        assert abs(weight_sum - Decimal("1")) <= Decimal("1e-27")

        missing_fx_snapshot = create_snapshot(
            session,
            owner.id,
            PortfolioSnapshotCreate(
                title="缺失 USD/HKD 汇率",
                as_of_date=date.today(),
                base_currency="HKD",
            ),
        )
        aapl = _listing(session, "AAPL.US")
        create_holding(
            session,
            missing_fx_snapshot.id,
            PortfolioHoldingCreate(
                listing_id=aapl.id,
                quantity=Decimal("0.12500000"),
            ),
        )
        _add_market_snapshot(session, aapl, "190.125")
        missing_fx = value_portfolio(session, missing_fx_snapshot.id)

        assert missing_fx.priced_total is None
        assert missing_fx.items[0].data_status == "missing_fx"
        assert missing_fx.items[0].local_market_value == Decimal("23.76562500000")
        assert missing_fx.items[0].base_market_value is None


def test_portfolio_quote_refresh_is_partial_and_revalues_successes(
    tmp_path: Path,
    monkeypatch,
) -> None:
    factory, app = _make_environment(tmp_path)
    with factory() as session:
        owner = create_owner(
            session,
            PortfolioOwnerCreate(name="刷新测试", owner_type="self"),
        )
        snapshot = create_snapshot(
            session,
            owner.id,
            PortfolioSnapshotCreate(
                title="部分成功",
                as_of_date=date.today(),
                base_currency="USD",
            ),
        )
        aapl = _listing(session, "AAPL.US")
        msft = _listing(session, "MSFT.US")
        create_holding(
            session,
            snapshot.id,
            PortfolioHoldingCreate(listing_id=aapl.id, quantity=Decimal("2")),
        )
        create_holding(
            session,
            snapshot.id,
            PortfolioHoldingCreate(listing_id=msft.id, quantity=Decimal("3")),
        )
        snapshot_id = snapshot.id

    def fake_refresh(session, listing):
        if listing.ticker == "MSFT.US":
            raise RuntimeError("fixture quote failure")
        return _add_market_snapshot(session, listing, "200.50")

    monkeypatch.setattr(
        portfolio_service,
        "refresh_listing_market_snapshot",
        fake_refresh,
    )
    with TestClient(app) as client:
        response = client.post(
            f"/api/investment-tools/portfolio-snapshots/{snapshot_id}/refresh-quotes"
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "partial"
    assert payload["succeeded"] == 1
    assert payload["failed"] == 1
    assert payload["valuation"]["priced_count"] == 1
    assert payload["valuation"]["unpriced_count"] == 1
    assert Decimal(payload["valuation"]["priced_total"]) == Decimal("401")
    failed = next(item for item in payload["quote_results"] if item["status"] == "failed")
    assert failed["ticker"] == "MSFT.US"
    assert "fixture quote failure" in failed["error"]


def test_portfolio_eastmoney_quote_time_keeps_shanghai_offset(tmp_path: Path) -> None:
    factory, _ = _make_environment(tmp_path)
    with factory() as session:
        owner = create_owner(
            session,
            PortfolioOwnerCreate(name="行情时间", owner_type="self"),
        )
        snapshot = create_snapshot(
            session,
            owner.id,
            PortfolioSnapshotCreate(
                title="上海时间",
                as_of_date=date.today(),
                base_currency="USD",
            ),
        )
        listing = _listing(session, "AAPL.US")
        create_holding(
            session,
            snapshot.id,
            PortfolioHoldingCreate(listing_id=listing.id, quantity=Decimal("1")),
        )
        market = _add_market_snapshot(session, listing, "190")
        market.source = "eastmoney_quote_snapshot"
        market.price_as_of = datetime(2026, 8, 22, 19, 9, 53)
        session.commit()

        item = value_portfolio(session, snapshot.id).items[0]

    assert item.quote_as_of is not None
    assert item.quote_as_of.utcoffset() == timedelta(hours=8)


def _listing(session, ticker: str) -> SecurityListing:
    listing = session.scalar(
        select(SecurityListing).where(SecurityListing.ticker == ticker)
    )
    assert listing is not None
    return listing


def _add_market_snapshot(
    session,
    listing: SecurityListing,
    price: str,
) -> MarketSnapshot:
    now = datetime.now(UTC)
    item = MarketSnapshot(
        listing_id=listing.id,
        price=float(price),
        currency=listing.trading_currency,
        price_as_of=now,
        fetched_at=now,
        source="portfolio_fixture_quote",
        source_url=f"https://fixture.invalid/{listing.ticker}",
        raw_snapshot_hash=f"portfolio-{listing.id}-{price}",
    )
    session.add(item)
    session.commit()
    session.refresh(item)
    return item


def _add_fx(session, base: str, quote: str, rate: str) -> FxRateSnapshot:
    item = FxRateSnapshot(
        base_currency=base,
        quote_currency=quote,
        rate=float(rate),
        rate_date=date.today(),
        fetched_at=datetime.now(UTC),
        source="portfolio_fixture_fx",
        source_url="https://fixture.invalid/fx",
        raw_snapshot_hash=f"portfolio-{base}-{quote}-{rate}",
    )
    session.add(item)
    session.commit()
    session.refresh(item)
    return item
