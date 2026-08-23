from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.db.init_db import init_db
from app.db.models import (
    AnalysisRun,
    Announcement,
    BuyMemoEntry,
    Company,
    Evidence,
    FinancialStatement,
    FxRateSnapshot,
    InvestmentMemo,
    MarketFearSnapshot,
    MarketSnapshot,
    PortfolioHolding,
    PortfolioOwner,
    PortfolioSnapshot,
    PriceDecisionRun,
    ReadingBook,
    ReadingProgressEntry,
    SecurityListing,
    ValuationRun,
)
from app.db.session import create_sqlalchemy_engine, get_db
from app.main import create_app
from app.services import data_management_service
from app.services.backup_service import BackupService
from app.services.maintenance_gate import maintenance_gate


def _make_environment(tmp_path: Path):
    engine = create_sqlalchemy_engine(f"sqlite:///{(tmp_path / 'data-management.db').as_posix()}")
    init_db(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    app = create_app(initialize_database=False)

    def override_get_db():
        with factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    return engine, factory, TestClient(app)


def _company(session: Session, ticker: str) -> Company:
    item = Company(ticker=ticker, exchange="NYSE", name=ticker, current_price=10)
    session.add(item)
    session.commit()
    session.refresh(item)
    return item


def _research_chain(session: Session, company: Company, *, suffix: str = "") -> dict[str, int]:
    financial = FinancialStatement(
        company_id=company.id,
        period=f"2025{suffix}",
        statement_type="income_statement",
        fields={"revenue": 1},
    )
    announcement = Announcement(
        company_id=company.id,
        title=f"公告{suffix}",
        published_at=datetime.now(UTC),
        category="annual_report",
    )
    evidence = Evidence(
        company_id=company.id,
        source_type="news",
        title=f"证据{suffix}",
        summary="摘要",
        impact_direction="neutral",
        importance_score=0.5,
        credibility_score=0.5,
    )
    evidence_run = AnalysisRun(
        company_id=company.id,
        run_type="evidence_search",
        input_snapshot={},
        result={},
        status="success",
        is_latest=True,
    )
    analyst_run = AnalysisRun(
        company_id=company.id,
        run_type="analyst_view",
        analyst_profile="buffett",
        input_snapshot={},
        result={},
        status="success",
        is_latest=True,
    )
    memo_run = AnalysisRun(
        company_id=company.id,
        run_type="investment_memo",
        input_snapshot={},
        result={},
        status="success",
        is_latest=True,
    )
    session.add_all([financial, announcement, evidence, evidence_run, analyst_run, memo_run])
    session.flush()
    memo = InvestmentMemo(
        company_id=company.id,
        generation_run_id=memo_run.id,
        version_no=1,
        title="Memo",
        conclusion="review",
        source_analyst_run_ids=[analyst_run.id],
        status="draft",
        is_latest=True,
    )
    session.add(memo)
    session.flush()
    valuation = ValuationRun(company_id=company.id, memo_id=memo.id)
    session.add(valuation)
    session.flush()
    decision = PriceDecisionRun(
        company_id=company.id,
        valuation_run_id=valuation.id,
        memo_id=memo.id,
        input_snapshot={},
        input_snapshot_hash=f"hash-{company.id}-{suffix}",
        intrinsic_values_per_share={},
        current_price=10,
        market_data_updated_at=datetime.now(UTC),
        analyst_score_total=0,
        analyst_scorecard_snapshot={},
        suggested_safety_margin=0.2,
        effective_safety_margin=0.2,
        scenario_buy_prices={},
        suggested_buy_price=8,
        current_margin=0.2,
        price_status="active",
    )
    session.add(decision)
    session.commit()
    return {
        "financial": financial.id,
        "announcement": announcement.id,
        "evidence": evidence.id,
        "evidence_run": evidence_run.id,
        "analyst_run": analyst_run.id,
        "memo_run": memo_run.id,
        "memo": memo.id,
        "valuation": valuation.id,
        "decision": decision.id,
    }


def _market_foundation(
    session: Session, company: Company, decision_id: int
) -> tuple[SecurityListing, MarketSnapshot, FxRateSnapshot]:
    listing = SecurityListing(
        company_id=company.id,
        ticker=company.ticker,
        symbol=company.ticker,
        exchange=company.exchange,
        market="US",
        trading_currency="USD",
        is_primary=True,
    )
    fx = FxRateSnapshot(
        base_currency="CNY",
        quote_currency="USD",
        rate=0.14,
        rate_date=date(2026, 8, 20),
        fetched_at=datetime.now(UTC),
        source=f"test-{company.id}",
        calculation_audit={"formula": "quote_per_eur / base_per_eur"},
    )
    session.add_all([listing, fx])
    session.flush()
    market = MarketSnapshot(
        listing_id=listing.id,
        price=10,
        currency="USD",
        price_as_of=datetime.now(UTC),
        fetched_at=datetime.now(UTC),
        source="test",
    )
    session.add(market)
    session.flush()
    decision = session.get(PriceDecisionRun, decision_id)
    assert decision is not None
    decision.listing_id = listing.id
    decision.market_snapshot_id = market.id
    decision.fx_rate_snapshot_id = fx.id
    session.commit()
    return listing, market, fx


def _investment_tools_data(
    session: Session,
    listing: SecurityListing,
    decision_id: int,
) -> dict[str, int]:
    owner = PortfolioOwner(name="测试持仓人", owner_type="investor")
    session.add(owner)
    session.flush()
    snapshot = PortfolioSnapshot(
        owner_id=owner.id,
        title="2026 年中持仓",
        as_of_date=date(2026, 6, 30),
        base_currency="CNY",
    )
    session.add(snapshot)
    session.flush()
    holding = PortfolioHolding(
        snapshot_id=snapshot.id,
        listing_id=listing.id,
        quantity=Decimal("12.34567890"),
    )
    fear = MarketFearSnapshot(
        market="US",
        indicator_code="VIX",
        indicator_name="Cboe VIX",
        value=Decimal("18.125000"),
        daily_change=Decimal("-0.250000"),
        moving_average_20=Decimal("19.000000"),
        percentile_3y=Decimal("45.5000"),
        temperature_score=Decimal("45.5000"),
        temperature_level="升温",
        data_date=date(2026, 8, 21),
        observation_count=756,
        fetched_at=datetime.now(UTC),
        source="fixture",
    )
    session.add_all([holding, fear])
    decision = session.get(PriceDecisionRun, decision_id)
    assert decision is not None
    buy_memo = BuyMemoEntry(
        company_id=listing.company_id,
        source_price_decision_run_id=decision.id,
        company_name=listing.company.name,
        listing_ticker=listing.ticker,
        exchange=listing.exchange,
        trading_currency=listing.trading_currency,
        base_intrinsic_value=Decimal("10"),
        suggested_buy_price=Decimal("8"),
        designed_safety_margin=Decimal("0.2"),
        latest_report_period="2025A",
        price_decision_version_no=decision.version_no,
        price_decision_run_version=decision.run_version,
        price_decision_created_at=decision.created_at,
    )
    session.add(buy_memo)
    reading_book = ReadingBook(
        title="证券分析",
        author="本杰明·格雷厄姆",
        status="reading",
        notes="数据管理边界测试",
    )
    reading_book.progress_entries.append(
        ReadingProgressEntry(round_number=1, progress_percent=35)
    )
    session.add(reading_book)
    session.commit()
    return {
        "owner": owner.id,
        "snapshot": snapshot.id,
        "holding": holding.id,
        "fear": fear.id,
        "buy_memo": buy_memo.id,
        "reading_book": reading_book.id,
        "reading_progress": reading_book.progress_entries[0].id,
    }


def _preview_and_execute(client: TestClient, operation_type: str, parameters: dict):
    preview = client.post(
        "/api/data-management/operations/preview",
        json={"operation_type": operation_type, "parameters": parameters},
    )
    assert preview.status_code == 200, preview.text
    payload = preview.json()
    result = client.post(
        "/api/data-management/operations/execute",
        json={
            "operation_token": payload["operation_token"],
            "confirmation_phrase": payload["confirmation_phrase"],
        },
    )
    assert result.status_code == 200, result.text
    return payload, result.json()


def test_company_reset_is_isolated_and_preserves_company(tmp_path: Path) -> None:
    _, factory, client = _make_environment(tmp_path)
    with factory() as session:
        target = _company(session, "RESET.US")
        other = _company(session, "OTHER.US")
        target_ids = _research_chain(session, target)
        listing, market, fx = _market_foundation(session, target, target_ids["decision"])
        investment_ids = _investment_tools_data(session, listing, target_ids["decision"])
        other_ids = _research_chain(session, other, suffix="-other")

    preview, result = _preview_and_execute(
        client, "reset_company_research_data", {"company_id": target.id}
    )
    assert preview["affected_counts"]["investment_memos"] == 1
    protected = {(item["table"], item["record_id"]) for item in preview["protected_records"]}
    assert ("security_listings", listing.id) in protected
    assert ("market_snapshots", market.id) in protected
    assert ("fx_rate_snapshots", fx.id) in protected
    assert ("portfolio_owners", investment_ids["owner"]) in protected
    assert ("portfolio_snapshots", investment_ids["snapshot"]) in protected
    assert ("portfolio_holdings", investment_ids["holding"]) in protected
    assert ("buy_memo_entries", investment_ids["buy_memo"]) in protected
    assert result["backup_id"]
    with factory() as session:
        assert session.get(Company, target.id) is not None
        assert (
            session.scalar(
                select(FinancialStatement).where(FinancialStatement.company_id == target.id)
            )
            is None
        )
        assert session.get(Evidence, other_ids["evidence"]) is not None
        assert session.get(PriceDecisionRun, other_ids["decision"]) is not None
        assert session.get(SecurityListing, listing.id) is not None
        assert session.get(MarketSnapshot, market.id) is not None
        assert session.get(FxRateSnapshot, fx.id) is not None
        assert session.get(PortfolioOwner, investment_ids["owner"]) is not None
        assert session.get(PortfolioSnapshot, investment_ids["snapshot"]) is not None
        assert session.get(PortfolioHolding, investment_ids["holding"]) is not None
        assert session.get(MarketFearSnapshot, investment_ids["fear"]) is not None
        assert session.get(ReadingBook, investment_ids["reading_book"]) is not None
        assert session.get(ReadingProgressEntry, investment_ids["reading_progress"]) is not None
        buy_memo = session.get(BuyMemoEntry, investment_ids["buy_memo"])
        assert buy_memo is not None
        assert buy_memo.source_price_decision_run_id is None


def test_summary_and_backup_manifest_include_market_foundation_tables(tmp_path: Path) -> None:
    _, factory, client = _make_environment(tmp_path)
    with factory() as session:
        company = _company(session, "FOUNDATION.US")
        ids = _research_chain(session, company)
        listing, _, _ = _market_foundation(session, company, ids["decision"])
        _investment_tools_data(session, listing, ids["decision"])

    summary = client.get("/api/data-management/summary")
    assert summary.status_code == 200, summary.text
    counts = summary.json()["record_counts"]
    assert counts["security_listings"] >= 1
    assert counts["market_snapshots"] >= 1
    assert counts["fx_rate_snapshots"] >= 1
    assert counts["portfolio_owners"] == 1
    assert counts["portfolio_snapshots"] == 1
    assert counts["portfolio_holdings"] == 1
    assert counts["market_fear_snapshots"] == 1
    assert counts["buy_memo_entries"] == 1
    assert counts["reading_books"] == 1
    assert counts["reading_progress_entries"] == 1

    backup = client.post("/api/data-management/backups", json={"reason": "foundation"})
    assert backup.status_code == 200, backup.text
    manifest_counts = backup.json()["record_counts"]
    assert manifest_counts["security_listings"] == counts["security_listings"]
    assert manifest_counts["market_snapshots"] == counts["market_snapshots"]
    assert manifest_counts["fx_rate_snapshots"] == counts["fx_rate_snapshots"]
    for table in (
        "portfolio_owners",
        "portfolio_snapshots",
        "portfolio_holdings",
        "market_fear_snapshots",
        "buy_memo_entries",
        "reading_books",
        "reading_progress_entries",
    ):
        assert manifest_counts[table] == counts[table]


def test_clear_analysis_history_preserves_source_data_and_evidence_runs(tmp_path: Path) -> None:
    _, factory, client = _make_environment(tmp_path)
    with factory() as session:
        company = _company(session, "CLEAR.US")
        ids = _research_chain(session, company)
        listing, _, _ = _market_foundation(session, company, ids["decision"])
        investment_ids = _investment_tools_data(session, listing, ids["decision"])

    _preview_and_execute(client, "clear_analysis_history", {})
    with factory() as session:
        assert session.get(FinancialStatement, ids["financial"]) is not None
        assert session.get(Announcement, ids["announcement"]) is not None
        assert session.get(Evidence, ids["evidence"]) is not None
        assert session.get(AnalysisRun, ids["evidence_run"]) is not None
        assert session.get(AnalysisRun, ids["analyst_run"]) is None
        buy_memo = session.get(BuyMemoEntry, investment_ids["buy_memo"])
        assert buy_memo is not None
        assert buy_memo.source_price_decision_run_id is None
        assert session.get(AnalysisRun, ids["memo_run"]) is None
        assert session.get(PortfolioOwner, investment_ids["owner"]) is not None
        assert session.get(PortfolioSnapshot, investment_ids["snapshot"]) is not None
        assert session.get(PortfolioHolding, investment_ids["holding"]) is not None
        assert session.get(MarketFearSnapshot, investment_ids["fear"]) is not None
        assert session.get(ReadingBook, investment_ids["reading_book"]) is not None
        assert session.get(ReadingProgressEntry, investment_ids["reading_progress"]) is not None


def test_operation_token_is_single_use_rejects_wrong_phrase_and_state_change(
    tmp_path: Path,
) -> None:
    _, factory, client = _make_environment(tmp_path)
    preview = client.post(
        "/api/data-management/operations/preview",
        json={"operation_type": "clear_analysis_history", "parameters": {}},
    ).json()
    wrong = client.post(
        "/api/data-management/operations/execute",
        json={"operation_token": preview["operation_token"], "confirmation_phrase": "wrong"},
    )
    assert wrong.status_code == 409
    with factory() as session:
        _company(session, "STATE-CHANGED.US")
    stale = client.post(
        "/api/data-management/operations/execute",
        json={
            "operation_token": preview["operation_token"],
            "confirmation_phrase": preview["confirmation_phrase"],
        },
    )
    assert stale.status_code == 409
    reused = client.post(
        "/api/data-management/operations/execute",
        json={
            "operation_token": preview["operation_token"],
            "confirmation_phrase": preview["confirmation_phrase"],
        },
    )
    assert reused.status_code == 409


def test_expired_operation_token_is_rejected(tmp_path: Path) -> None:
    _, _, client = _make_environment(tmp_path)
    preview = client.post(
        "/api/data-management/operations/preview",
        json={"operation_type": "clear_analysis_history", "parameters": {}},
    ).json()
    record = data_management_service.operation_tokens._records[preview["operation_token"]]
    record.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    response = client.post(
        "/api/data-management/operations/execute",
        json={
            "operation_token": preview["operation_token"],
            "confirmation_phrase": preview["confirmation_phrase"],
        },
    )
    assert response.status_code == 409
    assert "已过期" in response.json()["detail"]


def test_backup_verify_restore_and_pre_restore_backup(tmp_path: Path) -> None:
    _, factory, client = _make_environment(tmp_path)
    with factory() as session:
        original = _company(session, "BACKUP.US")
    created = client.post("/api/data-management/backups", json={"reason": "test"})
    assert created.status_code == 200
    backup = created.json()
    assert len(backup["sha256"]) == 64
    assert client.post(f"/api/data-management/backups/{backup['backup_id']}/verify").json() == {
        "backup_id": backup["backup_id"],
        "valid": True,
        "sha256_matches": True,
        "integrity_check": "ok",
    }
    with factory() as session:
        added = _company(session, "AFTER-BACKUP.US")

    preview = client.post(
        f"/api/data-management/backups/{backup['backup_id']}/restore/preview"
    ).json()
    restored = client.post(
        "/api/data-management/operations/execute",
        json={
            "operation_token": preview["operation_token"],
            "confirmation_phrase": preview["confirmation_phrase"],
        },
    )
    assert restored.status_code == 200, restored.text
    assert restored.json()["restart_required"] is True
    assert restored.json()["backup_id"] != backup["backup_id"]
    with factory() as session:
        assert session.get(Company, original.id) is not None
        assert session.scalar(select(Company).where(Company.ticker == added.ticker)) is None


def test_prune_protects_latest_archived_and_json_references(tmp_path: Path) -> None:
    _, factory, client = _make_environment(tmp_path)
    now = datetime.now(UTC)
    with factory() as session:
        company = _company(session, "PRUNE.US")
        analyst_runs = []
        for index in range(3):
            run = AnalysisRun(
                company_id=company.id,
                run_type="analyst_view",
                analyst_profile="buffett",
                input_snapshot={},
                result={},
                status="success",
                is_latest=index == 2,
                created_at=now + timedelta(minutes=index),
            )
            analyst_runs.append(run)
        session.add_all(analyst_runs)
        session.flush()
        memo_runs = []
        for index in range(3):
            run = AnalysisRun(
                company_id=company.id,
                run_type="investment_memo",
                input_snapshot={},
                result={},
                status="success",
                is_latest=index == 2,
                created_at=now + timedelta(minutes=index),
            )
            memo_runs.append(run)
        session.add_all(memo_runs)
        session.flush()
        memos = []
        for index in range(3):
            memo = InvestmentMemo(
                company_id=company.id,
                generation_run_id=memo_runs[index].id,
                version_no=index + 1,
                title=f"Memo {index}",
                conclusion="review",
                source_analyst_run_ids=[analyst_runs[0].id] if index == 2 else [],
                status="archived" if index == 1 else "draft",
                is_latest=index == 2,
                created_at=now + timedelta(minutes=index),
            )
            memos.append(memo)
        session.add_all(memos)
        session.commit()

    preview, _ = _preview_and_execute(
        client, "prune_versions", {"company_id": company.id, "keep_count": 1}
    )
    protected = {(item["table"], item["record_id"]) for item in preview["protected_records"]}
    assert ("investment_memos", memos[1].id) in protected
    assert ("analysis_runs", analyst_runs[0].id) in protected
    with factory() as session:
        assert session.get(InvestmentMemo, memos[1].id) is not None
        assert session.get(AnalysisRun, analyst_runs[0].id) is not None
        assert session.get(InvestmentMemo, memos[0].id) is None


def test_purge_deleted_keeps_referenced_memo_and_vacuums(tmp_path: Path) -> None:
    _, factory, client = _make_environment(tmp_path)
    with factory() as session:
        company = _company(session, "PURGE.US")
        ids = _research_chain(session, company)
        memo = session.get(InvestmentMemo, ids["memo"])
        decision = session.get(PriceDecisionRun, ids["decision"])
        assert memo and decision
        memo.status = "deleted"
        decision.status = "deleted"
        decision.deleted_at = datetime.now(UTC)
        session.commit()

    preview, result = _preview_and_execute(client, "purge_deleted_and_vacuum", {})
    assert preview["affected_counts"]["price_decision_runs"] == 1
    assert any(item["record_id"] == ids["memo"] for item in preview["protected_records"])
    assert result["integrity_check"] == "ok"
    assert result["database_size_after"] > 0
    with factory() as session:
        assert session.get(PriceDecisionRun, ids["decision"]) is None
        assert session.get(InvestmentMemo, ids["memo"]) is not None


def test_initialize_database_restores_standard_seed_and_reports_restart(tmp_path: Path) -> None:
    _, factory, client = _make_environment(tmp_path)
    with factory() as session:
        custom = _company(session, "CUSTOM-INIT.US")
        ids = _research_chain(session, custom)
        listing, _, _ = _market_foundation(session, custom, ids["decision"])
        investment_ids = _investment_tools_data(session, listing, ids["decision"])
    preview, result = _preview_and_execute(client, "initialize_database", {})
    assert preview["affected_counts"]["portfolio_owners"] == 1
    assert preview["affected_counts"]["portfolio_snapshots"] == 1
    assert preview["affected_counts"]["portfolio_holdings"] == 1
    assert preview["affected_counts"]["market_fear_snapshots"] == 1
    assert preview["affected_counts"]["buy_memo_entries"] == 1
    assert preview["affected_counts"]["reading_books"] == 1
    assert preview["affected_counts"]["reading_progress_entries"] == 1
    assert result["restart_required"] is True
    assert result["integrity_check"] == "ok"
    with factory() as session:
        assert session.scalar(select(Company).where(Company.ticker == custom.ticker)) is None
        assert session.scalar(select(Company).where(Company.ticker == "600519.SH")) is not None
        assert session.get(PortfolioOwner, investment_ids["owner"]) is None
        assert session.get(PortfolioSnapshot, investment_ids["snapshot"]) is None
        assert session.get(PortfolioHolding, investment_ids["holding"]) is None
        assert session.get(MarketFearSnapshot, investment_ids["fear"]) is None
        assert session.get(BuyMemoEntry, investment_ids["buy_memo"]) is None
        assert session.get(ReadingBook, investment_ids["reading_book"]) is None
        assert session.get(ReadingProgressEntry, investment_ids["reading_progress"]) is None


def test_write_requests_are_rejected_during_maintenance(tmp_path: Path) -> None:
    _, _, client = _make_environment(tmp_path)
    with maintenance_gate.maintenance("test"):
        response = client.post(
            "/api/companies",
            json={"ticker": "LOCK.US", "exchange": "NYSE", "name": "Locked"},
        )
    assert response.status_code == 503
    assert "正在维护" in response.json()["detail"]


def test_automatic_backup_settings_and_retention(tmp_path: Path) -> None:
    engine, _, client = _make_environment(tmp_path)
    updated = client.put(
        "/api/data-management/settings",
        json={"enabled": True, "interval_hours": 6, "max_backups": 2},
    )
    assert updated.status_code == 200
    assert updated.json()["enabled"] is True
    service = BackupService(engine)
    service.create_backup(reason="one")
    service.create_backup(reason="two")
    service.create_backup(reason="three")
    removed = service.prune_backups(2)
    assert len(removed) == 1
    assert len(service.list_backups()) == 2
