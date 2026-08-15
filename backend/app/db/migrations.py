from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import Connection, Engine, text

CURRENT_SQLITE_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class ColumnMigration:
    table_name: str
    column_name: str
    column_type: str


SQLITE_COLUMN_MIGRATIONS: tuple[ColumnMigration, ...] = (
    ColumnMigration("companies", "listed_date", "DATE"),
    ColumnMigration("companies", "status", "VARCHAR(40) DEFAULT 'watchlist' NOT NULL"),
    ColumnMigration("companies", "tags", "JSON DEFAULT '[]' NOT NULL"),
    ColumnMigration("companies", "market_cap", "FLOAT"),
    ColumnMigration("companies", "current_price", "FLOAT"),
    ColumnMigration("companies", "pe_ttm", "FLOAT"),
    ColumnMigration("companies", "pe_dynamic", "FLOAT"),
    ColumnMigration("companies", "pe_static", "FLOAT"),
    ColumnMigration("companies", "pb_ratio", "FLOAT"),
    ColumnMigration("companies", "ps_ratio", "FLOAT"),
    ColumnMigration("companies", "dividend_yield_ttm", "FLOAT"),
    ColumnMigration("companies", "dividend_yield_static", "FLOAT"),
    ColumnMigration("companies", "market_data_source", "VARCHAR(120)"),
    ColumnMigration("companies", "market_data_source_url", "TEXT"),
    ColumnMigration("companies", "market_data_updated_at", "DATETIME"),
    ColumnMigration("announcements", "raw_content", "TEXT"),
    ColumnMigration("announcements", "source", "VARCHAR(120)"),
    ColumnMigration("announcements", "raw_url", "TEXT"),
    ColumnMigration("announcements", "key_facts", "JSON DEFAULT '[]' NOT NULL"),
    ColumnMigration("announcements", "impact_direction", "VARCHAR(40)"),
    ColumnMigration("announcements", "sentiment", "VARCHAR(40)"),
    ColumnMigration("announcements", "positive_impacts", "JSON DEFAULT '[]' NOT NULL"),
    ColumnMigration("announcements", "negative_impacts", "JSON DEFAULT '[]' NOT NULL"),
    ColumnMigration("announcements", "neutral_impacts", "JSON DEFAULT '[]' NOT NULL"),
    ColumnMigration("announcements", "risk_tips", "JSON DEFAULT '[]' NOT NULL"),
    ColumnMigration("announcements", "review_questions", "JSON DEFAULT '[]' NOT NULL"),
    ColumnMigration("announcements", "tags", "JSON DEFAULT '[]' NOT NULL"),
    ColumnMigration(
        "announcements",
        "summary_status",
        "VARCHAR(40) DEFAULT 'unprocessed' NOT NULL",
    ),
    ColumnMigration("announcements", "summary_model_name", "VARCHAR(120)"),
    ColumnMigration("announcements", "summary_prompt_version", "VARCHAR(80)"),
    ColumnMigration("announcements", "summarized_at", "DATETIME"),
    ColumnMigration("analysis_runs", "run_version", "VARCHAR(40)"),
    ColumnMigration("analysis_runs", "model_name", "VARCHAR(120)"),
    ColumnMigration("analysis_runs", "prompt_version", "VARCHAR(80)"),
    ColumnMigration("analysis_runs", "data_snapshot_hash", "VARCHAR(120)"),
    ColumnMigration("analysis_runs", "parent_run_id", "INTEGER"),
    ColumnMigration("analysis_runs", "is_latest", "BOOLEAN DEFAULT 0 NOT NULL"),
    ColumnMigration("analysis_runs", "user_note", "TEXT"),
    ColumnMigration("analysis_runs", "status", "VARCHAR(40) DEFAULT 'success' NOT NULL"),
    ColumnMigration(
        "evidence",
        "analysis_status",
        "VARCHAR(40) DEFAULT 'model_analyzed' NOT NULL",
    ),
    ColumnMigration("evidence", "analysis_note", "TEXT"),
    ColumnMigration("evidence", "price_sensitive", "BOOLEAN DEFAULT 0 NOT NULL"),
    ColumnMigration(
        "evidence",
        "use_scope",
        ('JSON DEFAULT \'["fundamental_analysis","analyst_view","intrinsic_valuation"]\' NOT NULL'),
    ),
)


def run_schema_migrations(database_engine: Engine) -> None:
    if database_engine.dialect.name.startswith("sqlite"):
        _run_sqlite_schema_migrations(database_engine)

    _delete_legacy_announcement_summary_runs(database_engine)


def _run_sqlite_schema_migrations(database_engine: Engine) -> None:
    with database_engine.begin() as connection:
        _ensure_sqlite_investment_memos_table(connection)
        _ensure_sqlite_valuation_runs_table(connection)
        _ensure_sqlite_columns(connection, SQLITE_COLUMN_MIGRATIONS)
        _normalize_legacy_evidence_analysis_status(connection)
        _set_sqlite_schema_version(connection)


def _ensure_sqlite_investment_memos_table(connection: Connection) -> None:
    connection.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS investment_memos (
                id INTEGER PRIMARY KEY,
                company_id INTEGER NOT NULL,
                generation_run_id INTEGER NOT NULL,
                parent_memo_id INTEGER,
                version_no INTEGER NOT NULL,
                editor_type VARCHAR(40) DEFAULT 'model' NOT NULL,
                title VARCHAR(255) NOT NULL,
                conclusion VARCHAR(40) NOT NULL,
                sections JSON DEFAULT '{}' NOT NULL,
                markdown TEXT,
                source_analyst_run_ids JSON DEFAULT '[]' NOT NULL,
                source_snapshot_hash VARCHAR(120),
                change_note TEXT,
                status VARCHAR(40) DEFAULT 'draft' NOT NULL,
                is_latest BOOLEAN DEFAULT 0 NOT NULL,
                created_at DATETIME NOT NULL,
                updated_at DATETIME NOT NULL,
                FOREIGN KEY(company_id) REFERENCES companies (id),
                FOREIGN KEY(generation_run_id) REFERENCES analysis_runs (id),
                FOREIGN KEY(parent_memo_id) REFERENCES investment_memos (id)
            )
            """
        )
    )
    connection.execute(
        text(
            """
            CREATE INDEX IF NOT EXISTS ix_investment_memos_company_id
            ON investment_memos (company_id)
            """
        )
    )
    connection.execute(
        text(
            """
            CREATE INDEX IF NOT EXISTS ix_investment_memos_generation_run_id
            ON investment_memos (generation_run_id)
            """
        )
    )
    connection.execute(
        text(
            """
            CREATE INDEX IF NOT EXISTS ix_investment_memos_parent_memo_id
            ON investment_memos (parent_memo_id)
            """
        )
    )
    connection.execute(
        text(
            """
            CREATE INDEX IF NOT EXISTS ix_investment_memos_company_latest
            ON investment_memos (company_id, is_latest)
            """
        )
    )
    connection.execute(
        text(
            """
            CREATE INDEX IF NOT EXISTS ix_investment_memos_company_created
            ON investment_memos (company_id, created_at)
            """
        )
    )


def _ensure_sqlite_valuation_runs_table(connection: Connection) -> None:
    connection.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS valuation_runs (
                id INTEGER PRIMARY KEY,
                company_id INTEGER NOT NULL,
                memo_id INTEGER,
                run_version VARCHAR(40) DEFAULT '010_v1' NOT NULL,
                status VARCHAR(40) DEFAULT 'draft' NOT NULL,
                price_blind BOOLEAN DEFAULT 1 NOT NULL,
                forbidden_price_inputs JSON DEFAULT '{}' NOT NULL,
                input_snapshot JSON DEFAULT '{}' NOT NULL,
                input_snapshot_hash VARCHAR(120),
                valuation_inputs JSON DEFAULT '{}' NOT NULL,
                model_suggested_assumptions JSON DEFAULT '{}' NOT NULL,
                user_adjusted_assumptions JSON DEFAULT '{}' NOT NULL,
                assumptions JSON DEFAULT '{}' NOT NULL,
                methods JSON DEFAULT '{}' NOT NULL,
                results JSON DEFAULT '{}' NOT NULL,
                sensitivity JSON DEFAULT '{}' NOT NULL,
                confidence FLOAT,
                confidence_summary JSON DEFAULT '{}' NOT NULL,
                source_map JSON DEFAULT '{}' NOT NULL,
                user_note TEXT,
                created_at DATETIME NOT NULL,
                updated_at DATETIME NOT NULL,
                FOREIGN KEY(company_id) REFERENCES companies (id),
                FOREIGN KEY(memo_id) REFERENCES investment_memos (id)
            )
            """
        )
    )
    connection.execute(
        text(
            """
            CREATE INDEX IF NOT EXISTS ix_valuation_runs_company_id
            ON valuation_runs (company_id)
            """
        )
    )
    connection.execute(
        text(
            """
            CREATE INDEX IF NOT EXISTS ix_valuation_runs_memo_id
            ON valuation_runs (memo_id)
            """
        )
    )
    connection.execute(
        text(
            """
            CREATE INDEX IF NOT EXISTS ix_valuation_runs_company_created
            ON valuation_runs (company_id, created_at)
            """
        )
    )
    connection.execute(
        text(
            """
            CREATE INDEX IF NOT EXISTS ix_valuation_runs_company_status
            ON valuation_runs (company_id, status)
            """
        )
    )


def _ensure_sqlite_columns(
    connection: Connection, column_migrations: tuple[ColumnMigration, ...]
) -> None:
    table_names = {migration.table_name for migration in column_migrations}
    existing_tables = _existing_sqlite_tables(connection, table_names)

    for table_name in table_names:
        if table_name not in existing_tables:
            continue

        existing_columns = _existing_sqlite_columns(connection, table_name)
        for migration in column_migrations:
            if migration.table_name != table_name:
                continue
            if migration.column_name in existing_columns:
                continue
            connection.execute(
                text(
                    f"ALTER TABLE {migration.table_name} "
                    f"ADD COLUMN {migration.column_name} {migration.column_type}"
                )
            )


def _existing_sqlite_tables(connection: Connection, table_names: set[str]) -> set[str]:
    existing_tables = {
        str(row[0])
        for row in connection.execute(
            text(
                """
                SELECT name
                FROM sqlite_master
                WHERE type = 'table'
                """
            )
        )
    }
    return existing_tables & table_names


def _existing_sqlite_columns(connection: Connection, table_name: str) -> set[str]:
    return {str(row[1]) for row in connection.execute(text(f"PRAGMA table_info({table_name})"))}


def _normalize_legacy_evidence_analysis_status(connection: Connection) -> None:
    if {"analysis_status", "analysis_note"}.difference(
        _existing_sqlite_columns(connection, "evidence")
    ):
        return

    connection.execute(
        text(
            """
            UPDATE evidence
            SET
              analysis_status = 'search_lead',
              analysis_note = COALESCE(
                analysis_note,
                '模型结构化失败或超时，本条仅为搜索线索，影响方向、重要性和可信度尚未完成模型分析。'
              )
            WHERE analysis_status = 'model_analyzed'
              AND impact_direction = 'unknown'
              AND requires_review = 1
              AND importance_score <= 0.3000001
              AND credibility_score <= 0.4000001
              AND (
                summary LIKE '%兜底入库%'
                OR summary LIKE '%搜索线索%'
                OR raw_snapshot LIKE '%snippet%'
              )
            """
        )
    )


def _set_sqlite_schema_version(connection: Connection) -> None:
    current_version = connection.scalar(text("PRAGMA user_version")) or 0
    if int(current_version) < CURRENT_SQLITE_SCHEMA_VERSION:
        connection.execute(text(f"PRAGMA user_version = {CURRENT_SQLITE_SCHEMA_VERSION}"))


def _delete_legacy_announcement_summary_runs(database_engine: Engine) -> None:
    with database_engine.begin() as connection:
        connection.execute(
            text("DELETE FROM analysis_runs WHERE run_type = 'announcement_summary'")
        )
