from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import Connection, Engine, text

CURRENT_SQLITE_SCHEMA_VERSION = 10


@dataclass(frozen=True)
class ColumnMigration:
    table_name: str
    column_name: str
    column_type: str


SQLITE_COLUMN_MIGRATIONS: tuple[ColumnMigration, ...] = (
    ColumnMigration("companies", "canonical_key", "VARCHAR(160)"),
    ColumnMigration("companies", "legal_name", "VARCHAR(255)"),
    ColumnMigration("companies", "aliases", "JSON DEFAULT '[]' NOT NULL"),
    ColumnMigration("companies", "domicile_country", "VARCHAR(2)"),
    ColumnMigration("companies", "reporting_currency", "VARCHAR(3)"),
    ColumnMigration("companies", "fiscal_year_end", "VARCHAR(5)"),
    ColumnMigration("companies", "external_ids", "JSON DEFAULT '{}' NOT NULL"),
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
    ColumnMigration("financial_statements", "source_record_id", "VARCHAR(160)"),
    ColumnMigration("financial_statements", "filing_type", "VARCHAR(40)"),
    ColumnMigration("financial_statements", "taxonomy", "VARCHAR(40)"),
    ColumnMigration("financial_statements", "period_start", "DATE"),
    ColumnMigration("financial_statements", "period_end", "DATE"),
    ColumnMigration("financial_statements", "period_type", "VARCHAR(24)"),
    ColumnMigration("financial_statements", "fiscal_year", "INTEGER"),
    ColumnMigration("financial_statements", "fiscal_period", "VARCHAR(16)"),
    ColumnMigration("financial_statements", "filed_at", "DATETIME"),
    ColumnMigration("financial_statements", "unit_scale", "FLOAT DEFAULT 1.0 NOT NULL"),
    ColumnMigration("financial_statements", "is_amendment", "BOOLEAN DEFAULT 0 NOT NULL"),
    ColumnMigration("financial_statements", "raw_snapshot_hash", "VARCHAR(64)"),
    ColumnMigration("announcements", "listing_id", "INTEGER"),
    ColumnMigration("announcements", "raw_content", "TEXT"),
    ColumnMigration("announcements", "source", "VARCHAR(120)"),
    ColumnMigration("announcements", "raw_url", "TEXT"),
    ColumnMigration("announcements", "source_document_id", "VARCHAR(160)"),
    ColumnMigration("announcements", "document_type", "VARCHAR(80)"),
    ColumnMigration("announcements", "filing_form", "VARCHAR(40)"),
    ColumnMigration("announcements", "language", "VARCHAR(16)"),
    ColumnMigration("announcements", "period_end", "DATE"),
    ColumnMigration("announcements", "content_type", "VARCHAR(80)"),
    ColumnMigration("announcements", "content_source", "VARCHAR(120)"),
    ColumnMigration("announcements", "content_fetched_at", "DATETIME"),
    ColumnMigration("announcements", "raw_content_hash", "VARCHAR(64)"),
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
    ColumnMigration("analysis_runs", "config_version", "INTEGER"),
    ColumnMigration("analysis_runs", "config_hash", "VARCHAR(64)"),
    ColumnMigration("analysis_runs", "config_snapshot", "JSON DEFAULT '{}' NOT NULL"),
    ColumnMigration("investment_memos", "config_version", "INTEGER"),
    ColumnMigration("investment_memos", "config_hash", "VARCHAR(64)"),
    ColumnMigration("investment_memos", "config_snapshot", "JSON DEFAULT '{}' NOT NULL"),
    ColumnMigration("valuation_runs", "config_version", "INTEGER"),
    ColumnMigration("valuation_runs", "config_hash", "VARCHAR(64)"),
    ColumnMigration("valuation_runs", "config_snapshot", "JSON DEFAULT '{}' NOT NULL"),
    ColumnMigration("valuation_runs", "valuation_currency", "VARCHAR(3)"),
    ColumnMigration("valuation_runs", "share_basis_snapshot", "JSON DEFAULT '{}' NOT NULL"),
    ColumnMigration("price_decision_runs", "config_version", "INTEGER"),
    ColumnMigration("price_decision_runs", "config_hash", "VARCHAR(64)"),
    ColumnMigration("price_decision_runs", "config_snapshot", "JSON DEFAULT '{}' NOT NULL"),
    ColumnMigration("price_decision_runs", "listing_id", "INTEGER"),
    ColumnMigration("price_decision_runs", "market_snapshot_id", "INTEGER"),
    ColumnMigration("price_decision_runs", "fx_rate_snapshot_id", "INTEGER"),
    ColumnMigration(
        "price_decision_runs",
        "issuer_intrinsic_values_per_share",
        "JSON DEFAULT '{}' NOT NULL",
    ),
    ColumnMigration("price_decision_runs", "valuation_currency", "VARCHAR(3)"),
    ColumnMigration("price_decision_runs", "trading_currency", "VARCHAR(3)"),
    ColumnMigration(
        "price_decision_runs", "underlying_shares_per_listing_unit", "FLOAT"
    ),
    ColumnMigration("price_decision_runs", "fx_rate", "FLOAT"),
    ColumnMigration("fx_rate_snapshots", "calculation_audit", "JSON"),
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
    ColumnMigration(
        "portfolio_owners", "display_order", "INTEGER DEFAULT 0 NOT NULL"
    ),
    ColumnMigration(
        "portfolio_snapshots", "display_order", "INTEGER DEFAULT 0 NOT NULL"
    ),
)


def run_schema_migrations(database_engine: Engine) -> None:
    if database_engine.dialect.name.startswith("sqlite"):
        _run_sqlite_schema_migrations(database_engine)


def _run_sqlite_schema_migrations(database_engine: Engine) -> None:
    with database_engine.begin() as connection:
        previous_version = int(connection.scalar(text("PRAGMA user_version")) or 0)
        _ensure_sqlite_parameter_config_versions_table(connection)
        _ensure_sqlite_investment_memos_table(connection)
        _ensure_sqlite_valuation_runs_table(connection)
        _ensure_sqlite_buy_memo_entries_table(connection)
        _ensure_sqlite_columns(connection, SQLITE_COLUMN_MIGRATIONS)
        if previous_version < 8:
            _backfill_portfolio_display_order(connection)
        _ensure_sqlite_price_decision_runs_table(connection)
        _make_price_decision_analyst_score_nullable(connection)
        _ensure_market_foundation_indexes(connection)
        _backfill_market_foundation(connection)
        _normalize_legacy_evidence_analysis_status(connection)
        _set_sqlite_schema_version(connection)


def _ensure_sqlite_buy_memo_entries_table(connection: Connection) -> None:
    connection.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS buy_memo_entries (
                id INTEGER PRIMARY KEY,
                company_id INTEGER NOT NULL,
                source_price_decision_run_id INTEGER,
                company_name VARCHAR(255) NOT NULL,
                listing_ticker VARCHAR(32) NOT NULL,
                exchange VARCHAR(32),
                trading_currency VARCHAR(3),
                base_intrinsic_value NUMERIC(28, 8) NOT NULL,
                suggested_buy_price NUMERIC(28, 8) NOT NULL,
                designed_safety_margin NUMERIC(10, 8) NOT NULL,
                latest_report_period VARCHAR(32),
                price_decision_version_no INTEGER NOT NULL,
                price_decision_run_version VARCHAR(40) NOT NULL,
                price_decision_created_at DATETIME NOT NULL,
                created_at DATETIME NOT NULL,
                updated_at DATETIME NOT NULL,
                CONSTRAINT uq_buy_memo_entries_source_price_decision
                    UNIQUE (source_price_decision_run_id),
                CONSTRAINT ck_buy_memo_entries_intrinsic_value_positive
                    CHECK (base_intrinsic_value > 0),
                CONSTRAINT ck_buy_memo_entries_buy_price_positive
                    CHECK (suggested_buy_price > 0),
                CONSTRAINT ck_buy_memo_entries_safety_margin_range
                    CHECK (designed_safety_margin >= 0 AND designed_safety_margin <= 1),
                FOREIGN KEY(company_id) REFERENCES companies (id),
                FOREIGN KEY(source_price_decision_run_id)
                    REFERENCES price_decision_runs (id) ON DELETE SET NULL
            )
            """
        )
    )
    connection.execute(
        text(
            "CREATE INDEX IF NOT EXISTS ix_buy_memo_entries_company_id "
            "ON buy_memo_entries (company_id)"
        )
    )
    connection.execute(
        text(
            "CREATE INDEX IF NOT EXISTS ix_buy_memo_entries_source_price_decision_run_id "
            "ON buy_memo_entries (source_price_decision_run_id)"
        )
    )
    connection.execute(
        text(
            "CREATE INDEX IF NOT EXISTS ix_buy_memo_entries_company_created "
            "ON buy_memo_entries (company_id, created_at)"
        )
    )


def _backfill_portfolio_display_order(connection: Connection) -> None:
    required_tables = {"portfolio_owners", "portfolio_snapshots"}
    if _existing_sqlite_tables(connection, required_tables) != required_tables:
        return
    connection.execute(
        text(
            """
            UPDATE portfolio_owners AS current
            SET display_order = (
                SELECT COUNT(*)
                FROM portfolio_owners AS earlier
                WHERE earlier.id < current.id
            )
            """
        )
    )
    connection.execute(
        text(
            """
            UPDATE portfolio_snapshots AS current
            SET display_order = (
                SELECT COUNT(*)
                FROM portfolio_snapshots AS earlier
                WHERE earlier.owner_id = current.owner_id
                  AND (
                    earlier.as_of_date > current.as_of_date
                    OR (
                      earlier.as_of_date = current.as_of_date
                      AND earlier.id > current.id
                    )
                  )
            )
            """
        )
    )


def _ensure_sqlite_parameter_config_versions_table(connection: Connection) -> None:
    connection.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS parameter_config_versions (
                id INTEGER PRIMARY KEY,
                version_no INTEGER NOT NULL UNIQUE,
                schema_version VARCHAR(40) NOT NULL,
                status VARCHAR(40) DEFAULT 'draft' NOT NULL,
                scope_type VARCHAR(40) DEFAULT 'global' NOT NULL,
                scope_key VARCHAR(120),
                config_json JSON DEFAULT '{}' NOT NULL,
                config_hash VARCHAR(64) NOT NULL,
                change_note TEXT,
                created_at DATETIME NOT NULL,
                published_at DATETIME
            )
            """
        )
    )
    connection.execute(
        text(
            """
            CREATE INDEX IF NOT EXISTS ix_parameter_config_versions_status
            ON parameter_config_versions (status)
            """
        )
    )


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


def _ensure_sqlite_price_decision_runs_table(connection: Connection) -> None:
    connection.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS price_decision_runs (
                id INTEGER PRIMARY KEY,
                company_id INTEGER NOT NULL,
                valuation_run_id INTEGER NOT NULL,
                memo_id INTEGER NOT NULL,
                listing_id INTEGER,
                market_snapshot_id INTEGER,
                fx_rate_snapshot_id INTEGER,
                version_no INTEGER DEFAULT 1 NOT NULL,
                run_version VARCHAR(40) DEFAULT '011_v1' NOT NULL,
                formula_version VARCHAR(40) DEFAULT '011_v1' NOT NULL,
                status VARCHAR(40) DEFAULT 'active' NOT NULL,
                input_snapshot JSON DEFAULT '{}' NOT NULL,
                input_snapshot_hash VARCHAR(120) NOT NULL,
                intrinsic_values_per_share JSON DEFAULT '{}' NOT NULL,
                issuer_intrinsic_values_per_share JSON DEFAULT '{}' NOT NULL,
                valuation_currency VARCHAR(3),
                trading_currency VARCHAR(3),
                underlying_shares_per_listing_unit FLOAT,
                fx_rate FLOAT,
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
                deleted_at DATETIME,
                FOREIGN KEY(company_id) REFERENCES companies (id),
                FOREIGN KEY(valuation_run_id) REFERENCES valuation_runs (id),
                FOREIGN KEY(memo_id) REFERENCES investment_memos (id),
                FOREIGN KEY(listing_id) REFERENCES security_listings (id),
                FOREIGN KEY(market_snapshot_id) REFERENCES market_snapshots (id),
                FOREIGN KEY(fx_rate_snapshot_id) REFERENCES fx_rate_snapshots (id)
            )
            """
        )
    )
    for index_name, columns in (
        ("ix_price_decision_runs_company_id", "company_id"),
        ("ix_price_decision_runs_valuation_run_id", "valuation_run_id"),
        ("ix_price_decision_runs_memo_id", "memo_id"),
        ("ix_price_decision_runs_listing_id", "listing_id"),
        ("ix_price_decision_runs_market_snapshot_id", "market_snapshot_id"),
        ("ix_price_decision_runs_fx_rate_snapshot_id", "fx_rate_snapshot_id"),
        ("ix_price_decision_runs_company_created", "company_id, created_at"),
        ("ix_price_decision_runs_company_status", "company_id, status"),
    ):
        connection.execute(
            text(f"CREATE INDEX IF NOT EXISTS {index_name} ON price_decision_runs ({columns})")
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


def _make_price_decision_analyst_score_nullable(connection: Connection) -> None:
    columns = list(connection.execute(text("PRAGMA table_info(price_decision_runs)")))
    score_column = next((row for row in columns if str(row[1]) == "analyst_score_total"), None)
    if score_column is None or int(score_column[3]) == 0:
        return

    connection.execute(
        text(
            """
            CREATE TABLE price_decision_runs_v4 (
                id INTEGER PRIMARY KEY,
                company_id INTEGER NOT NULL,
                valuation_run_id INTEGER NOT NULL,
                memo_id INTEGER NOT NULL,
                listing_id INTEGER,
                market_snapshot_id INTEGER,
                fx_rate_snapshot_id INTEGER,
                version_no INTEGER DEFAULT 1 NOT NULL,
                run_version VARCHAR(40) DEFAULT '011_v1' NOT NULL,
                formula_version VARCHAR(40) DEFAULT '011_v1' NOT NULL,
                status VARCHAR(40) DEFAULT 'active' NOT NULL,
                input_snapshot JSON DEFAULT '{}' NOT NULL,
                input_snapshot_hash VARCHAR(120) NOT NULL,
                config_version INTEGER,
                config_hash VARCHAR(64),
                config_snapshot JSON DEFAULT '{}' NOT NULL,
                intrinsic_values_per_share JSON DEFAULT '{}' NOT NULL,
                issuer_intrinsic_values_per_share JSON DEFAULT '{}' NOT NULL,
                valuation_currency VARCHAR(3),
                trading_currency VARCHAR(3),
                underlying_shares_per_listing_unit FLOAT,
                fx_rate FLOAT,
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
                deleted_at DATETIME,
                FOREIGN KEY(company_id) REFERENCES companies (id),
                FOREIGN KEY(valuation_run_id) REFERENCES valuation_runs (id),
                FOREIGN KEY(memo_id) REFERENCES investment_memos (id),
                FOREIGN KEY(listing_id) REFERENCES security_listings (id),
                FOREIGN KEY(market_snapshot_id) REFERENCES market_snapshots (id),
                FOREIGN KEY(fx_rate_snapshot_id) REFERENCES fx_rate_snapshots (id)
            )
            """
        )
    )
    column_names = ", ".join(str(row[1]) for row in columns)
    connection.execute(
        text(
            f"INSERT INTO price_decision_runs_v4 ({column_names}) "
            f"SELECT {column_names} FROM price_decision_runs"
        )
    )
    connection.execute(text("DROP TABLE price_decision_runs"))
    connection.execute(text("ALTER TABLE price_decision_runs_v4 RENAME TO price_decision_runs"))
    for index_name, index_columns in (
        ("ix_price_decision_runs_company_id", "company_id"),
        ("ix_price_decision_runs_valuation_run_id", "valuation_run_id"),
        ("ix_price_decision_runs_memo_id", "memo_id"),
        ("ix_price_decision_runs_listing_id", "listing_id"),
        ("ix_price_decision_runs_market_snapshot_id", "market_snapshot_id"),
        ("ix_price_decision_runs_fx_rate_snapshot_id", "fx_rate_snapshot_id"),
        ("ix_price_decision_runs_company_created", "company_id, created_at"),
        ("ix_price_decision_runs_company_status", "company_id, status"),
    ):
        connection.execute(
            text(
                f"CREATE INDEX IF NOT EXISTS {index_name} ON price_decision_runs ({index_columns})"
            )
        )


def _ensure_market_foundation_indexes(connection: Connection) -> None:
    if "companies" in _existing_sqlite_tables(connection, {"companies"}):
        connection.execute(
            text(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_companies_canonical_key "
                "ON companies (canonical_key)"
            )
        )
    if "security_listings" in _existing_sqlite_tables(connection, {"security_listings"}):
        connection.execute(
            text(
                "CREATE UNIQUE INDEX IF NOT EXISTS "
                "uq_security_listings_company_primary_active "
                "ON security_listings (company_id) WHERE is_primary = 1 AND is_active = 1"
            )
        )
    if "announcements" in _existing_sqlite_tables(connection, {"announcements"}):
        connection.execute(
            text(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_announcements_source_document "
                "ON announcements (company_id, source, source_document_id) "
                "WHERE source_document_id IS NOT NULL"
            )
        )
        connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_announcements_listing_published "
                "ON announcements (listing_id, published_at)"
            )
        )


def _backfill_market_foundation(connection: Connection) -> None:
    required_tables = {"companies", "security_listings", "market_snapshots"}
    if _existing_sqlite_tables(connection, required_tables) != required_tables:
        return

    companies = connection.execute(
        text(
            """
            SELECT id, ticker, exchange, name, listed_date, current_price, market_cap,
                   pe_ttm, pe_dynamic, pe_static, pb_ratio, ps_ratio,
                   dividend_yield_ttm, dividend_yield_static,
                   market_data_source, market_data_source_url, market_data_updated_at,
                   canonical_key, domicile_country, reporting_currency, fiscal_year_end
            FROM companies
            ORDER BY id
            """
        )
    ).mappings()
    for company in companies:
        company_id = int(company["id"])
        ticker = str(company["ticker"]).strip().upper()
        exchange = str(company["exchange"]).strip().upper()
        market, trading_currency, domicile_country = _market_defaults(exchange)
        canonical_key = str(company["canonical_key"] or "").strip() or _legacy_canonical_key(
            company_id, ticker
        )
        reporting_currency = str(company["reporting_currency"] or "").strip().upper()
        if not reporting_currency:
            reporting_currency = _known_reporting_currency(ticker) or trading_currency
        connection.execute(
            text(
                """
                UPDATE companies
                SET canonical_key = :canonical_key,
                    aliases = COALESCE(aliases, '[]'),
                    external_ids = COALESCE(external_ids, '{}'),
                    domicile_country = COALESCE(domicile_country, :domicile_country),
                    reporting_currency = COALESCE(reporting_currency, :reporting_currency),
                    fiscal_year_end = COALESCE(fiscal_year_end, '12-31')
                WHERE id = :company_id
                """
            ),
            {
                "company_id": company_id,
                "canonical_key": canonical_key,
                "domicile_country": domicile_country,
                "reporting_currency": reporting_currency,
            },
        )

        listing_id = connection.scalar(
            text(
                "SELECT id FROM security_listings "
                "WHERE exchange = :exchange AND ticker = :ticker"
            ),
            {"exchange": exchange, "ticker": ticker},
        )
        if listing_id is None:
            connection.execute(
                text(
                    """
                    INSERT INTO security_listings (
                        company_id, ticker, symbol, exchange, market, trading_currency,
                        security_type, listed_date, is_primary, is_active,
                        underlying_shares_per_listing_unit, provider_identifiers,
                        created_at, updated_at
                    ) VALUES (
                        :company_id, :ticker, :symbol, :exchange, :market, :trading_currency,
                        'common_stock', :listed_date, 1, 1, 1.0, '{}',
                        CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                    )
                    """
                ),
                {
                    "company_id": company_id,
                    "ticker": ticker,
                    "symbol": _ticker_symbol(ticker),
                    "exchange": exchange,
                    "market": market,
                    "trading_currency": trading_currency,
                    "listed_date": company["listed_date"],
                },
            )
            listing_id = connection.scalar(text("SELECT last_insert_rowid()"))
        else:
            has_primary = connection.scalar(
                text(
                    "SELECT 1 FROM security_listings "
                    "WHERE company_id = :company_id AND is_primary = 1 AND is_active = 1 LIMIT 1"
                ),
                {"company_id": company_id},
            )
            if has_primary is None:
                connection.execute(
                    text("UPDATE security_listings SET is_primary = 1 WHERE id = :listing_id"),
                    {"listing_id": listing_id},
                )

        price = company["current_price"]
        market_time = company["market_data_updated_at"]
        if price is None or market_time is None or float(price) <= 0:
            continue
        has_snapshot = connection.scalar(
            text("SELECT 1 FROM market_snapshots WHERE listing_id = :listing_id LIMIT 1"),
            {"listing_id": listing_id},
        )
        if has_snapshot is not None:
            continue
        connection.execute(
            text(
                """
                INSERT INTO market_snapshots (
                    listing_id, price, currency, market_cap, pe_ttm, pe_dynamic, pe_static,
                    pb_ratio, ps_ratio, dividend_yield_ttm, dividend_yield_static,
                    price_as_of, fetched_at, source, source_url, raw_snapshot_hash
                ) VALUES (
                    :listing_id, :price, :currency, :market_cap, :pe_ttm, :pe_dynamic,
                    :pe_static, :pb_ratio, :ps_ratio, :dividend_yield_ttm,
                    :dividend_yield_static, :market_time, :market_time, :source,
                    :source_url, NULL
                )
                """
            ),
            {
                "listing_id": listing_id,
                "price": price,
                "currency": trading_currency,
                "market_cap": company["market_cap"],
                "pe_ttm": company["pe_ttm"],
                "pe_dynamic": company["pe_dynamic"],
                "pe_static": company["pe_static"],
                "pb_ratio": company["pb_ratio"],
                "ps_ratio": company["ps_ratio"],
                "dividend_yield_ttm": company["dividend_yield_ttm"],
                "dividend_yield_static": company["dividend_yield_static"],
                "market_time": market_time,
                "source": company["market_data_source"] or "legacy_company_snapshot",
                "source_url": company["market_data_source_url"],
            },
        )


def _market_defaults(exchange: str) -> tuple[str, str, str]:
    if exchange in {"SSE", "SZSE", "BSE"}:
        return "A_SHARE", "CNY", "CN"
    if exchange == "HKEX":
        return "HK", "HKD", "HK"
    if exchange in {"NASDAQ", "NYSE", "AMEX"}:
        return "US", "USD", "US"
    return "OTHER", "XXX", "ZZ"


def _known_reporting_currency(ticker: str) -> str | None:
    if ticker in {"00700.HK", "09988.HK", "01810.HK"}:
        return "CNY"
    return None


def _legacy_canonical_key(company_id: int, ticker: str) -> str:
    known = {
        "00700.HK": "tencent-holdings",
        "09988.HK": "alibaba-group",
        "600941.SH": "china-mobile",
        "00941.HK": "china-mobile",
        "AAPL.US": "apple-inc",
    }
    return known.get(ticker, f"legacy-company-{company_id}")


def _ticker_symbol(ticker: str) -> str:
    return ticker.rsplit(".", 1)[0] if "." in ticker else ticker


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
