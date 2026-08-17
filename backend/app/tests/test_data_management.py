from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.db.init_db import init_db
from app.db.models import (
    AnalysisRun,
    Announcement,
    Company,
    Evidence,
    FinancialStatement,
    InvestmentMemo,
    PriceDecisionRun,
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
        _research_chain(session, target)
        other_ids = _research_chain(session, other, suffix="-other")

    preview, result = _preview_and_execute(
        client, "reset_company_research_data", {"company_id": target.id}
    )
    assert preview["affected_counts"]["investment_memos"] == 1
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


def test_clear_analysis_history_preserves_source_data_and_evidence_runs(tmp_path: Path) -> None:
    _, factory, client = _make_environment(tmp_path)
    with factory() as session:
        company = _company(session, "CLEAR.US")
        ids = _research_chain(session, company)

    _preview_and_execute(client, "clear_analysis_history", {})
    with factory() as session:
        assert session.get(FinancialStatement, ids["financial"]) is not None
        assert session.get(Announcement, ids["announcement"]) is not None
        assert session.get(Evidence, ids["evidence"]) is not None
        assert session.get(AnalysisRun, ids["evidence_run"]) is not None
        assert session.get(AnalysisRun, ids["analyst_run"]) is None
        assert session.get(AnalysisRun, ids["memo_run"]) is None


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
    _, result = _preview_and_execute(client, "initialize_database", {})
    assert result["restart_required"] is True
    assert result["integrity_check"] == "ok"
    with factory() as session:
        assert session.scalar(select(Company).where(Company.ticker == custom.ticker)) is None
        assert session.scalar(select(Company).where(Company.ticker == "600519.SH")) is not None


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
