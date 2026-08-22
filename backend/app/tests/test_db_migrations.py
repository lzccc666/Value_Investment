from pathlib import Path

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.db.init_db import init_db
from app.db.migrations import CURRENT_SQLITE_SCHEMA_VERSION, run_schema_migrations
from app.db.models import AnalysisRun, Company, Evidence
from app.db.session import create_sqlalchemy_engine


def test_init_db_migrates_legacy_sqlite_database(tmp_path: Path) -> None:
    engine = create_sqlalchemy_engine(f"sqlite:///{(tmp_path / 'legacy.db').as_posix()}")
    _create_legacy_sqlite_schema(engine)

    init_db(engine)
    init_db(engine)

    with engine.connect() as connection:
        company_columns = _table_columns(connection, "companies")
        announcement_columns = _table_columns(connection, "announcements")
        analysis_run_columns = _table_columns(connection, "analysis_runs")
        investment_memo_columns = _table_columns(connection, "investment_memos")
        valuation_run_columns = _table_columns(connection, "valuation_runs")
        price_decision_run_columns = _table_columns(connection, "price_decision_runs")
        price_decision_run_info = {
            str(row[1]): row
            for row in connection.execute(text("PRAGMA table_info(price_decision_runs)"))
        }
        price_decision_indexes = {
            str(row[1])
            for row in connection.execute(text("PRAGMA index_list(price_decision_runs)"))
        }
        parameter_config_columns = _table_columns(connection, "parameter_config_versions")
        evidence_columns = _table_columns(connection, "evidence")
        fx_rate_columns = _table_columns(connection, "fx_rate_snapshots")
        table_names = {
            str(row[0])
            for row in connection.execute(
                text("SELECT name FROM sqlite_master WHERE type='table'")
            )
        }
        sqlite_schema_version = connection.scalar(text("PRAGMA user_version"))

    assert {"market_cap", "current_price", "market_data_updated_at"}.issubset(company_columns)
    assert {"raw_content", "summary_status", "summary_model_name"}.issubset(announcement_columns)
    assert {
        "run_version",
        "is_latest",
        "status",
        "config_version",
        "config_hash",
        "config_snapshot",
    }.issubset(analysis_run_columns)
    assert {
        "version_no",
        "sections",
        "is_latest",
        "status",
        "config_version",
        "config_hash",
        "config_snapshot",
    }.issubset(investment_memo_columns)
    assert {
        "memo_id",
        "price_blind",
        "assumptions",
        "results",
        "config_version",
        "config_hash",
        "config_snapshot",
    }.issubset(valuation_run_columns)
    assert {
        "valuation_run_id",
        "memo_id",
        "input_snapshot_hash",
        "suggested_buy_price",
        "price_status",
        "deleted_at",
        "config_version",
        "config_hash",
        "config_snapshot",
        "listing_id",
        "market_snapshot_id",
        "fx_rate_snapshot_id",
        "issuer_intrinsic_values_per_share",
        "valuation_currency",
        "trading_currency",
        "underlying_shares_per_listing_unit",
        "fx_rate",
    }.issubset(price_decision_run_columns)
    assert {
        "version_no",
        "schema_version",
        "status",
        "config_json",
        "config_hash",
        "change_note",
        "published_at",
    }.issubset(parameter_config_columns)
    assert {"analysis_status", "analysis_note", "price_sensitive", "use_scope"}.issubset(
        evidence_columns
    )
    assert "calculation_audit" in fx_rate_columns
    assert {
        "portfolio_owners",
        "portfolio_snapshots",
        "portfolio_holdings",
        "market_fear_snapshots",
        "buy_memo_entries",
    }.issubset(table_names)
    assert sqlite_schema_version == CURRENT_SQLITE_SCHEMA_VERSION
    assert price_decision_run_info["analyst_score_total"][3] == 0
    assert {
        "ix_price_decision_runs_listing_id",
        "ix_price_decision_runs_market_snapshot_id",
        "ix_price_decision_runs_fx_rate_snapshot_id",
    }.issubset(price_decision_indexes)

    with Session(engine) as session:
        seed_company = session.scalar(select(Company).where(Company.ticker == "600519.SH"))
        legacy_evidence = session.scalar(select(Evidence).where(Evidence.title == "Legacy lead"))
        old_summary_run = session.scalar(
            select(AnalysisRun).where(AnalysisRun.run_type == "announcement_summary")
        )

    assert seed_company is not None
    assert legacy_evidence is not None
    assert legacy_evidence.analysis_status == "search_lead"
    assert legacy_evidence.analysis_note is not None
    assert "搜索线索" in legacy_evidence.analysis_note
    assert old_summary_run is not None


def test_schema_9_backfills_and_preserves_portfolio_directory_order(tmp_path: Path) -> None:
    engine = create_sqlalchemy_engine(f"sqlite:///{(tmp_path / 'portfolio-v7.db').as_posix()}")
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                CREATE TABLE portfolio_owners (
                    id INTEGER PRIMARY KEY,
                    name VARCHAR(120) NOT NULL,
                    owner_type VARCHAR(16) NOT NULL,
                    notes TEXT,
                    created_at DATETIME NOT NULL,
                    updated_at DATETIME NOT NULL
                )
                """
            )
        )
        connection.execute(
            text(
                """
                CREATE TABLE portfolio_snapshots (
                    id INTEGER PRIMARY KEY,
                    owner_id INTEGER NOT NULL,
                    title VARCHAR(160) NOT NULL,
                    as_of_date DATE NOT NULL,
                    base_currency VARCHAR(3) NOT NULL,
                    notes TEXT,
                    created_at DATETIME NOT NULL,
                    updated_at DATETIME NOT NULL
                )
                """
            )
        )
        connection.execute(
            text(
                """
                INSERT INTO portfolio_owners
                    (id, name, owner_type, created_at, updated_at)
                VALUES
                    (8, '后建', 'investor', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
                    (3, '先建', 'self', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """
            )
        )
        connection.execute(
            text(
                """
                INSERT INTO portfolio_snapshots
                    (id, owner_id, title, as_of_date, base_currency, created_at, updated_at)
                VALUES
                    (11, 3, '旧期', '2025-12-31', 'CNY', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
                    (12, 3, '新期', '2026-06-30', 'CNY', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
                    (13, 3, '同日后建', '2026-06-30', 'CNY', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """
            )
        )
        connection.execute(text("PRAGMA user_version = 7"))

    run_schema_migrations(engine)
    with engine.begin() as connection:
        owner_order = connection.execute(
            text("SELECT id, display_order FROM portfolio_owners ORDER BY display_order")
        ).all()
        snapshot_order = connection.execute(
            text("SELECT id, display_order FROM portfolio_snapshots ORDER BY display_order")
        ).all()
        connection.execute(
            text("UPDATE portfolio_owners SET display_order = CASE id WHEN 8 THEN 0 ELSE 1 END")
        )

    assert owner_order == [(3, 0), (8, 1)]
    assert snapshot_order == [(13, 0), (12, 1), (11, 2)]

    run_schema_migrations(engine)
    with engine.connect() as connection:
        preserved_order = connection.execute(
            text("SELECT id FROM portfolio_owners ORDER BY display_order")
        ).scalars().all()
        assert preserved_order == [8, 3]
        assert connection.scalar(text("PRAGMA user_version")) == 9


def _create_legacy_sqlite_schema(engine) -> None:
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                CREATE TABLE companies (
                    id INTEGER PRIMARY KEY,
                    ticker VARCHAR(32) NOT NULL,
                    exchange VARCHAR(32) NOT NULL,
                    name VARCHAR(255) NOT NULL,
                    industry VARCHAR(120),
                    description TEXT,
                    listed_date DATE,
                    status VARCHAR(40) DEFAULT 'watchlist' NOT NULL,
                    tags JSON DEFAULT '[]' NOT NULL,
                    created_at DATETIME,
                    updated_at DATETIME
                )
                """
            )
        )
        connection.execute(
            text(
                """
                CREATE TABLE announcements (
                    id INTEGER PRIMARY KEY,
                    company_id INTEGER NOT NULL,
                    title VARCHAR(255) NOT NULL,
                    published_at DATETIME NOT NULL,
                    category VARCHAR(80) NOT NULL,
                    content TEXT,
                    summary TEXT,
                    source_url TEXT,
                    importance_score FLOAT,
                    created_at DATETIME
                )
                """
            )
        )
        connection.execute(
            text(
                """
                CREATE TABLE analysis_runs (
                    id INTEGER PRIMARY KEY,
                    company_id INTEGER NOT NULL,
                    run_type VARCHAR(80) NOT NULL,
                    analyst_profile VARCHAR(80),
                    input_snapshot JSON DEFAULT '{}' NOT NULL,
                    result JSON DEFAULT '{}' NOT NULL,
                    confidence FLOAT,
                    created_at DATETIME
                )
                """
            )
        )
        connection.execute(
            text(
                """
                CREATE TABLE evidence (
                    id INTEGER PRIMARY KEY,
                    company_id INTEGER NOT NULL,
                    source_type VARCHAR(40) NOT NULL,
                    title VARCHAR(255) NOT NULL,
                    source VARCHAR(160),
                    source_url TEXT,
                    published_at DATETIME,
                    summary TEXT NOT NULL,
                    key_facts JSON DEFAULT '[]' NOT NULL,
                    impact_direction VARCHAR(40) NOT NULL,
                    importance_score FLOAT NOT NULL,
                    credibility_score FLOAT NOT NULL,
                    tags JSON DEFAULT '[]' NOT NULL,
                    requires_review BOOLEAN DEFAULT 1 NOT NULL,
                    raw_snapshot JSON DEFAULT '{}' NOT NULL,
                    created_at DATETIME
                )
                """
            )
        )
        connection.execute(
            text(
                """
                CREATE TABLE price_decision_runs (
                    id INTEGER PRIMARY KEY,
                    company_id INTEGER NOT NULL,
                    valuation_run_id INTEGER NOT NULL,
                    memo_id INTEGER NOT NULL,
                    version_no INTEGER DEFAULT 1 NOT NULL,
                    run_version VARCHAR(40) DEFAULT '011_v1' NOT NULL,
                    formula_version VARCHAR(40) DEFAULT '011_v1' NOT NULL,
                    status VARCHAR(40) DEFAULT 'active' NOT NULL,
                    input_snapshot JSON DEFAULT '{}' NOT NULL,
                    input_snapshot_hash VARCHAR(120) NOT NULL,
                    intrinsic_values_per_share JSON DEFAULT '{}' NOT NULL,
                    current_price FLOAT NOT NULL,
                    market_data_updated_at DATETIME NOT NULL,
                    analyst_score_total FLOAT,
                    analyst_scorecard_snapshot JSON DEFAULT '{}' NOT NULL,
                    suggested_safety_margin FLOAT NOT NULL,
                    safety_margin_override FLOAT,
                    effective_safety_margin FLOAT NOT NULL,
                    scenario_buy_prices JSON DEFAULT '{}' NOT NULL,
                    suggested_buy_price FLOAT NOT NULL,
                    current_margin FLOAT NOT NULL,
                    price_status VARCHAR(80) NOT NULL,
                    created_at DATETIME NOT NULL,
                    updated_at DATETIME NOT NULL,
                    deleted_at DATETIME
                )
                """
            )
        )
        connection.execute(
            text(
                """
                INSERT INTO companies (
                    id, ticker, exchange, name, status, tags, created_at, updated_at
                )
                VALUES (
                    1, 'LEGACY.US', 'NYSE', 'Legacy Manual Company', '观察中',
                    '["manual"]', '2026-01-01 00:00:00', '2026-01-01 00:00:00'
                )
                """
            )
        )
        connection.execute(
            text(
                """
                INSERT INTO evidence (
                    company_id, source_type, title, summary, impact_direction,
                    importance_score, credibility_score, requires_review, raw_snapshot,
                    created_at
                )
                VALUES (
                    1, 'web', 'Legacy lead', '模型结构化失败，兜底入库为搜索线索。',
                    'unknown', 0.3, 0.4, 1, '{"snippet":"legacy"}',
                    '2026-01-01 00:00:00'
                )
                """
            )
        )
        connection.execute(
            text(
                """
                INSERT INTO analysis_runs (
                    company_id, run_type, analyst_profile, input_snapshot, result,
                    confidence, created_at
                )
                VALUES (
                    1, 'announcement_summary', 'announcement_summary', '{}', '{}',
                    0.5, '2026-01-01 00:00:00'
                )
                """
            )
        )


def _table_columns(connection, table_name: str) -> set[str]:
    return {str(row[1]) for row in connection.execute(text(f"PRAGMA table_info({table_name})"))}
