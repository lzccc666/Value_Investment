from __future__ import annotations

import hashlib
import sqlite3
from contextlib import closing
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Event, Thread
from uuid import uuid4

from sqlalchemy import Engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import DEFAULT_DATABASE_PATH, settings
from app.schemas.data_management import (
    AutomaticBackupSettings,
    BackupManifest,
    BackupVerifyResponse,
)
from app.services.maintenance_gate import MaintenanceBusyError, maintenance_gate

BUSINESS_TABLES = (
    "companies",
    "security_listings",
    "market_snapshots",
    "fx_rate_snapshots",
    "portfolio_owners",
    "portfolio_snapshots",
    "portfolio_holdings",
    "market_fear_snapshots",
    "buy_memo_entries",
    "reading_books",
    "reading_progress_entries",
    "financial_statements",
    "announcements",
    "evidence",
    "analysis_runs",
    "investment_memos",
    "valuation_runs",
    "price_decision_runs",
)
BACKUP_DATABASE_FILENAME = "database.sqlite3"
BACKUP_MANIFEST_FILENAME = "manifest.json"
BACKUP_SETTINGS_FILENAME = "settings.json"


class BackupError(RuntimeError):
    pass


def engine_from_session(session: Session) -> Engine:
    bind = session.get_bind()
    return bind.engine if hasattr(bind, "engine") else bind


def sqlite_database_path(engine: Engine) -> Path:
    url = make_url(str(engine.url))
    if not url.drivername.startswith("sqlite") or not url.database or url.database == ":memory:":
        raise BackupError("数据管理仅支持基于文件的 SQLite 数据库。")
    return Path(url.database).resolve()


def backup_directory_for_engine(engine: Engine) -> Path:
    database_path = sqlite_database_path(engine)
    if database_path == DEFAULT_DATABASE_PATH.resolve():
        return settings.backup_directory.resolve()
    return (database_path.parent / "backups").resolve()


class BackupService:
    def __init__(self, engine: Engine, backup_directory: Path | None = None) -> None:
        self.engine = engine
        self.database_path = sqlite_database_path(engine)
        self.backup_directory = (backup_directory or backup_directory_for_engine(engine)).resolve()

    def create_backup(self, *, reason: str) -> BackupManifest:
        if not self.database_path.exists():
            raise BackupError("数据库文件不存在，无法创建备份。")
        self.backup_directory.mkdir(parents=True, exist_ok=True)
        created_at = datetime.now(UTC)
        backup_id = f"{created_at.strftime('%Y%m%dT%H%M%S%fZ')}-{uuid4().hex[:10]}"
        backup_path = self._backup_path(backup_id)
        backup_path.mkdir(parents=False, exist_ok=False)
        database_copy = backup_path / BACKUP_DATABASE_FILENAME
        try:
            with closing(sqlite3.connect(str(self.database_path), timeout=30)) as source:
                with closing(sqlite3.connect(str(database_copy), timeout=30)) as destination:
                    source.backup(destination)
            integrity = _sqlite_integrity_check(database_copy)
            if integrity != "ok":
                raise BackupError(f"备份完整性检查失败：{integrity}")
            manifest = BackupManifest(
                backup_id=backup_id,
                created_at=created_at,
                database_filename=BACKUP_DATABASE_FILENAME,
                file_size=database_copy.stat().st_size,
                sha256=_sha256(database_copy),
                schema_version=_sqlite_schema_version(database_copy),
                record_counts=_sqlite_record_counts(database_copy),
                reason=reason,
                application_version=settings.app_version,
                verified=True,
                integrity_check=integrity,
            )
            self._write_manifest(backup_path, manifest)
            return manifest
        except Exception:
            _remove_backup_directory(backup_path)
            raise

    def list_backups(self) -> list[BackupManifest]:
        if not self.backup_directory.exists():
            return []
        manifests: list[BackupManifest] = []
        for path in self.backup_directory.iterdir():
            if not path.is_dir():
                continue
            manifest_path = path / BACKUP_MANIFEST_FILENAME
            if not manifest_path.is_file():
                continue
            try:
                manifests.append(
                    BackupManifest.model_validate_json(manifest_path.read_text("utf-8"))
                )
            except (OSError, ValueError):
                continue
        return sorted(manifests, key=lambda item: item.created_at, reverse=True)

    def get_backup(self, backup_id: str) -> BackupManifest:
        path = self._validated_existing_backup_path(backup_id)
        try:
            manifest = BackupManifest.model_validate_json(
                (path / BACKUP_MANIFEST_FILENAME).read_text("utf-8")
            )
        except (OSError, ValueError) as exc:
            raise BackupError("备份 manifest 无法读取。") from exc
        if manifest.backup_id != backup_id:
            raise BackupError("备份 ID 与 manifest 不一致。")
        return manifest

    def verify_backup(self, backup_id: str) -> BackupVerifyResponse:
        manifest = self.get_backup(backup_id)
        database_copy = self._backup_path(backup_id) / manifest.database_filename
        if not database_copy.is_file():
            return BackupVerifyResponse(
                backup_id=backup_id,
                valid=False,
                sha256_matches=False,
                integrity_check="missing_database_file",
            )
        sha_matches = _sha256(database_copy) == manifest.sha256
        integrity = _sqlite_integrity_check(database_copy)
        return BackupVerifyResponse(
            backup_id=backup_id,
            valid=sha_matches and integrity == "ok",
            sha256_matches=sha_matches,
            integrity_check=integrity,
        )

    def restore_backup(self, backup_id: str) -> str:
        verification = self.verify_backup(backup_id)
        if not verification.valid:
            raise BackupError("备份校验失败，拒绝恢复。")
        manifest = self.get_backup(backup_id)
        source_path = self._backup_path(backup_id) / manifest.database_filename
        self.engine.dispose()
        with closing(sqlite3.connect(str(source_path), timeout=30)) as source:
            with closing(sqlite3.connect(str(self.database_path), timeout=30)) as destination:
                source.backup(destination)
        self.engine.dispose()
        integrity = _sqlite_integrity_check(self.database_path)
        if integrity != "ok":
            raise BackupError(f"恢复后的数据库完整性检查失败：{integrity}")
        return integrity

    def delete_backup(self, backup_id: str) -> None:
        path = self._validated_existing_backup_path(backup_id)
        _remove_backup_directory(path)

    def prune_backups(self, max_backups: int) -> list[str]:
        manifests = self.list_backups()
        removed: list[str] = []
        for manifest in manifests[max_backups:]:
            self.delete_backup(manifest.backup_id)
            removed.append(manifest.backup_id)
        return removed

    def get_settings(self) -> AutomaticBackupSettings:
        path = self.backup_directory / BACKUP_SETTINGS_FILENAME
        if not path.is_file():
            return AutomaticBackupSettings()
        try:
            return AutomaticBackupSettings.model_validate_json(path.read_text("utf-8"))
        except (OSError, ValueError) as exc:
            raise BackupError("自动备份设置文件无法读取。") from exc

    def update_settings(self, value: AutomaticBackupSettings) -> AutomaticBackupSettings:
        self.backup_directory.mkdir(parents=True, exist_ok=True)
        path = self.backup_directory / BACKUP_SETTINGS_FILENAME
        path.write_text(value.model_dump_json(indent=2), encoding="utf-8")
        self.prune_backups(value.max_backups)
        return value

    def _write_manifest(self, backup_path: Path, manifest: BackupManifest) -> None:
        (backup_path / BACKUP_MANIFEST_FILENAME).write_text(
            manifest.model_dump_json(indent=2), encoding="utf-8"
        )

    def _backup_path(self, backup_id: str) -> Path:
        allowed = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_"
        if not backup_id or any(char not in allowed for char in backup_id):
            raise BackupError("备份 ID 格式无效。")
        path = (self.backup_directory / backup_id).resolve()
        if path.parent != self.backup_directory:
            raise BackupError("备份路径越界。")
        return path

    def _validated_existing_backup_path(self, backup_id: str) -> Path:
        path = self._backup_path(backup_id)
        if not path.is_dir():
            raise BackupError("指定备份不存在。")
        return path


class AutomaticBackupScheduler:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine
        self._stop_event = Event()
        self._thread: Thread | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = Thread(target=self._run, name="automatic-sqlite-backup", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5)
        self._thread = None

    def _run(self) -> None:
        service = BackupService(self.engine)
        session_factory = sessionmaker(bind=self.engine, expire_on_commit=False)
        while not self._stop_event.wait(30):
            try:
                backup_settings = service.get_settings()
                if not backup_settings.enabled or not _backup_due(backup_settings):
                    continue
                with maintenance_gate.maintenance("automatic_backup", wait_seconds=5):
                    with session_factory() as session:
                        session.commit()
                    service.create_backup(reason="automatic")
                    service.prune_backups(backup_settings.max_backups)
                    backup_settings.last_auto_backup_at = datetime.now(UTC)
                    service.update_settings(backup_settings)
            except (BackupError, MaintenanceBusyError, OSError):
                continue


def _backup_due(value: AutomaticBackupSettings) -> bool:
    if value.last_auto_backup_at is None:
        return True
    last = value.last_auto_backup_at
    if last.tzinfo is None:
        last = last.replace(tzinfo=UTC)
    return datetime.now(UTC) - last >= timedelta(hours=value.interval_hours)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sqlite_integrity_check(path: Path) -> str:
    try:
        with closing(sqlite3.connect(str(path), timeout=30)) as connection:
            row = connection.execute("PRAGMA integrity_check").fetchone()
    except sqlite3.Error as exc:
        return f"sqlite_error:{exc}"
    return str(row[0]) if row else "no_result"


def _sqlite_schema_version(path: Path) -> int:
    with closing(sqlite3.connect(str(path), timeout=30)) as connection:
        row = connection.execute("PRAGMA user_version").fetchone()
    return int(row[0]) if row else 0


def _sqlite_record_counts(path: Path) -> dict[str, int]:
    counts: dict[str, int] = {}
    with closing(sqlite3.connect(str(path), timeout=30)) as connection:
        existing = {
            str(row[0])
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        for table in BUSINESS_TABLES:
            counts[table] = (
                int(connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0])
                if table in existing
                else 0
            )
    return counts


def database_integrity_check(engine: Engine) -> str:
    with engine.connect() as connection:
        return str(connection.execute(text("PRAGMA integrity_check")).scalar_one())


def database_schema_version(engine: Engine) -> int:
    with engine.connect() as connection:
        return int(connection.execute(text("PRAGMA user_version")).scalar_one())


def _remove_backup_directory(path: Path) -> None:
    if not path.exists():
        return
    for filename in (BACKUP_DATABASE_FILENAME, BACKUP_MANIFEST_FILENAME):
        target = path / filename
        if target.is_file():
            target.unlink()
    try:
        path.rmdir()
    except OSError as exc:
        raise BackupError("备份目录包含未知文件，拒绝删除。") from exc
