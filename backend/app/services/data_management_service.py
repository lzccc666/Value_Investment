from __future__ import annotations

import hashlib
import json
import shutil
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from threading import Lock
from typing import Any
from uuid import uuid4

from sqlalchemy import delete, func, select, text
from sqlalchemy.orm import Session

from app.db.base import Base
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
from app.schemas.data_management import (
    DataManagementSummary,
    DataOperationParameters,
    DataOperationPreview,
    DataOperationPreviewRequest,
    DataOperationResult,
    DataOperationType,
    ProtectedRecord,
)
from app.services.backup_service import (
    BUSINESS_TABLES,
    BackupError,
    BackupService,
    database_integrity_check,
    database_schema_version,
    engine_from_session,
    sqlite_database_path,
)
from app.services.maintenance_gate import MaintenanceBusyError, maintenance_gate

TOKEN_TTL = timedelta(minutes=10)
DERIVED_ANALYSIS_RUN_TYPES = {"analyst_view", "investment_memo"}

CONFIRMATION_PHRASES = {
    DataOperationType.RESET_COMPANY_RESEARCH_DATA: "清空公司研究数据",
    DataOperationType.CLEAR_ANALYSIS_HISTORY: "清空全部分析历史",
    DataOperationType.INITIALIZE_DATABASE: "完整初始化数据库",
    DataOperationType.PRUNE_VERSIONS: "清理旧版本",
    DataOperationType.PURGE_DELETED_AND_VACUUM: "物理清理并压缩数据库",
    DataOperationType.RESTORE_BACKUP: "恢复指定备份",
    DataOperationType.DELETE_BACKUP: "删除指定备份",
}

MODEL_BY_TABLE = {
    "financial_statements": FinancialStatement,
    "announcements": Announcement,
    "evidence": Evidence,
    "analysis_runs": AnalysisRun,
    "investment_memos": InvestmentMemo,
    "valuation_runs": ValuationRun,
    "price_decision_runs": PriceDecisionRun,
}


class DataManagementError(RuntimeError):
    pass


class InvalidOperationTokenError(DataManagementError):
    pass


@dataclass
class OperationTokenRecord:
    token: str
    operation_type: DataOperationType
    parameters: DataOperationParameters
    fingerprint: str
    plan: dict[str, Any]
    confirmation_phrase: str
    expires_at: datetime
    consumed: bool = False


class OperationTokenRegistry:
    def __init__(self) -> None:
        self._lock = Lock()
        self._records: dict[str, OperationTokenRecord] = {}

    def create(
        self,
        *,
        operation_type: DataOperationType,
        parameters: DataOperationParameters,
        fingerprint: str,
        plan: dict[str, Any],
    ) -> OperationTokenRecord:
        now = datetime.now(UTC)
        record = OperationTokenRecord(
            token=uuid4().hex + uuid4().hex,
            operation_type=operation_type,
            parameters=parameters,
            fingerprint=fingerprint,
            plan=plan,
            confirmation_phrase=CONFIRMATION_PHRASES[operation_type],
            expires_at=now + TOKEN_TTL,
        )
        with self._lock:
            self._records = {
                key: value for key, value in self._records.items() if value.expires_at > now
            }
            self._records[record.token] = record
        return record

    def consume(self, token: str, confirmation_phrase: str) -> OperationTokenRecord:
        with self._lock:
            record = self._records.get(token)
            if record is None or record.consumed:
                raise InvalidOperationTokenError("操作令牌不存在或已经使用。")
            if record.expires_at <= datetime.now(UTC):
                self._records.pop(token, None)
                raise InvalidOperationTokenError("操作令牌已过期，请重新预览。")
            if confirmation_phrase != record.confirmation_phrase:
                raise InvalidOperationTokenError("确认短语不正确。")
            record.consumed = True
            return record


operation_tokens = OperationTokenRegistry()


def get_summary(session: Session) -> DataManagementSummary:
    engine = engine_from_session(session)
    database_path = sqlite_database_path(engine)
    backup_service = BackupService(engine)
    backups = backup_service.list_backups()
    return DataManagementSummary(
        database_path=str(database_path),
        database_size=database_path.stat().st_size if database_path.exists() else 0,
        record_counts=_record_counts(session),
        soft_deleted_counts={
            "investment_memos": _count(session, InvestmentMemo, InvestmentMemo.status == "deleted"),
            "price_decision_runs": _count(
                session, PriceDecisionRun, PriceDecisionRun.status == "deleted"
            ),
        },
        latest_backup=backups[0] if backups else None,
        automatic_backup=backup_service.get_settings(),
        maintenance_active=maintenance_gate.active,
        maintenance_operation=maintenance_gate.operation,
        schema_version=database_schema_version(engine),
        integrity_check=database_integrity_check(engine),
    )


def preview_operation(
    session: Session, request: DataOperationPreviewRequest
) -> DataOperationPreview:
    plan = _build_plan(session, request.operation_type, request.parameters)
    record = operation_tokens.create(
        operation_type=request.operation_type,
        parameters=request.parameters,
        fingerprint=_database_fingerprint(session),
        plan=plan,
    )
    return DataOperationPreview(
        operation_token=record.token,
        operation_type=record.operation_type,
        parameters=record.parameters,
        affected_counts=plan["affected_counts"],
        protected_records=[
            ProtectedRecord.model_validate(item) for item in plan["protected_records"]
        ],
        estimated_reclaim_bytes=plan.get("estimated_reclaim_bytes", 0),
        requires_backup=record.operation_type != DataOperationType.DELETE_BACKUP,
        confirmation_phrase=record.confirmation_phrase,
        expires_at=record.expires_at,
    )


def execute_operation(
    session: Session,
    *,
    operation_token: str,
    confirmation_phrase: str,
    expected_operation: DataOperationType | None = None,
    expected_backup_id: str | None = None,
) -> DataOperationResult:
    record = operation_tokens.consume(operation_token, confirmation_phrase)
    if expected_operation is not None and record.operation_type != expected_operation:
        raise InvalidOperationTokenError("操作令牌类型与当前端点不匹配。")
    if expected_backup_id is not None and record.parameters.backup_id != expected_backup_id:
        raise InvalidOperationTokenError("操作令牌绑定的备份与当前端点不匹配。")
    if _database_fingerprint(session) != record.fingerprint:
        raise InvalidOperationTokenError("数据库状态已变化，原预览令牌失效。")

    try:
        with maintenance_gate.maintenance(record.operation_type.value):
            return _execute_locked(session, record)
    except MaintenanceBusyError:
        raise
    except BackupError as exc:
        raise DataManagementError(str(exc)) from exc


def _execute_locked(session: Session, record: OperationTokenRecord) -> DataOperationResult:
    engine = engine_from_session(session)
    backup_service = BackupService(engine)
    operation_type = record.operation_type
    database_path = sqlite_database_path(engine)
    size_before = database_path.stat().st_size if database_path.exists() else 0

    if operation_type == DataOperationType.DELETE_BACKUP:
        backup_service.delete_backup(str(record.parameters.backup_id))
        return DataOperationResult(
            operation_type=operation_type,
            affected_counts={"backups": 1},
            message="备份已删除。",
        )

    if operation_type == DataOperationType.RESTORE_BACKUP:
        pre_restore = backup_service.create_backup(reason="before_restore")
        session.close()
        try:
            integrity = backup_service.restore_backup(str(record.parameters.backup_id))
        except Exception:
            backup_service.restore_backup(pre_restore.backup_id)
            raise
        size_after = database_path.stat().st_size
        return DataOperationResult(
            operation_type=operation_type,
            affected_counts=record.plan["affected_counts"],
            backup_id=pre_restore.backup_id,
            database_size_before=size_before,
            database_size_after=size_after,
            reclaimed_bytes=max(0, size_before - size_after),
            integrity_check=integrity,
            restart_required=True,
            message="数据库已从指定备份恢复，请重新加载应用数据。",
        )

    backup = backup_service.create_backup(reason=f"before_{operation_type.value}")
    try:
        if operation_type == DataOperationType.RESET_COMPANY_RESEARCH_DATA:
            _reset_company(session, int(record.parameters.company_id or 0))
        elif operation_type == DataOperationType.CLEAR_ANALYSIS_HISTORY:
            _clear_analysis_history(session)
        elif operation_type == DataOperationType.PRUNE_VERSIONS:
            _delete_prune_plan(session, record.plan)
        elif operation_type == DataOperationType.PURGE_DELETED_AND_VACUUM:
            return _purge_deleted_and_vacuum(
                session,
                record=record,
                backup_id=backup.backup_id,
                size_before=size_before,
            )
        elif operation_type == DataOperationType.INITIALIZE_DATABASE:
            return _initialize_database(
                session,
                backup_service=backup_service,
                backup_id=backup.backup_id,
                size_before=size_before,
            )
        else:
            raise DataManagementError("不支持的数据管理操作。")
    except Exception:
        session.rollback()
        raise

    integrity = database_integrity_check(engine)
    if integrity != "ok":
        raise DataManagementError(f"操作后的数据库完整性检查失败：{integrity}")
    size_after = database_path.stat().st_size
    return DataOperationResult(
        operation_type=operation_type,
        affected_counts=record.plan["affected_counts"],
        backup_id=backup.backup_id,
        protected_records=[
            ProtectedRecord.model_validate(item) for item in record.plan["protected_records"]
        ],
        database_size_before=size_before,
        database_size_after=size_after,
        reclaimed_bytes=max(0, size_before - size_after),
        integrity_check=integrity,
        message="数据管理操作已完成。",
    )


def _build_plan(
    session: Session,
    operation_type: DataOperationType,
    parameters: DataOperationParameters,
) -> dict[str, Any]:
    if operation_type == DataOperationType.RESET_COMPANY_RESEARCH_DATA:
        company = session.get(Company, parameters.company_id)
        if company is None:
            raise DataManagementError("指定公司不存在。")
        counts = {
            table: _count(session, model, model.company_id == company.id)
            for table, model in MODEL_BY_TABLE.items()
        }
        return _plan(counts)
    if operation_type == DataOperationType.CLEAR_ANALYSIS_HISTORY:
        counts = {
            "price_decision_runs": _count(session, PriceDecisionRun),
            "valuation_runs": _count(session, ValuationRun),
            "investment_memos": _count(session, InvestmentMemo),
            "analysis_runs": _count(
                session, AnalysisRun, AnalysisRun.run_type.in_(DERIVED_ANALYSIS_RUN_TYPES)
            ),
        }
        return _plan(counts)
    if operation_type == DataOperationType.INITIALIZE_DATABASE:
        return _plan(_record_counts(session))
    if operation_type == DataOperationType.PRUNE_VERSIONS:
        return _build_prune_plan(
            session,
            company_id=parameters.company_id,
            keep_count=int(parameters.keep_count or 1),
        )
    if operation_type == DataOperationType.PURGE_DELETED_AND_VACUUM:
        return _build_purge_plan(session)
    if operation_type == DataOperationType.RESTORE_BACKUP:
        manifest = BackupService(engine_from_session(session)).get_backup(str(parameters.backup_id))
        return _plan(manifest.record_counts)
    if operation_type == DataOperationType.DELETE_BACKUP:
        BackupService(engine_from_session(session)).get_backup(str(parameters.backup_id))
        return _plan({"backups": 1})
    raise DataManagementError("不支持的数据管理操作。")


def _plan(
    affected_counts: dict[str, int],
    *,
    protected_records: list[dict[str, Any]] | None = None,
    delete_ids: dict[str, list[int]] | None = None,
) -> dict[str, Any]:
    return {
        "affected_counts": affected_counts,
        "protected_records": protected_records or [],
        "delete_ids": delete_ids or {},
        "estimated_reclaim_bytes": sum(affected_counts.values()) * 1024,
    }


def _reset_company(session: Session, company_id: int) -> None:
    if session.get(Company, company_id) is None:
        raise DataManagementError("指定公司不存在。")
    for model in (
        PriceDecisionRun,
        ValuationRun,
        InvestmentMemo,
        AnalysisRun,
        Evidence,
        Announcement,
        FinancialStatement,
    ):
        session.execute(delete(model).where(model.company_id == company_id))
    session.commit()


def _clear_analysis_history(session: Session) -> None:
    session.execute(delete(PriceDecisionRun))
    session.execute(delete(ValuationRun))
    session.execute(delete(InvestmentMemo))
    session.execute(delete(AnalysisRun).where(AnalysisRun.run_type.in_(DERIVED_ANALYSIS_RUN_TYPES)))
    session.commit()


def _build_prune_plan(
    session: Session, *, company_id: int | None, keep_count: int
) -> dict[str, Any]:
    company_filter = (
        (lambda model: [model.company_id == company_id]) if company_id else (lambda model: [])
    )
    if company_id and session.get(Company, company_id) is None:
        raise DataManagementError("指定公司不存在。")

    price_runs = list(
        session.scalars(
            select(PriceDecisionRun)
            .where(*company_filter(PriceDecisionRun))
            .order_by(
                PriceDecisionRun.company_id,
                PriceDecisionRun.created_at.desc(),
                PriceDecisionRun.id.desc(),
            )
        )
    )
    valuations = list(
        session.scalars(
            select(ValuationRun)
            .where(*company_filter(ValuationRun))
            .order_by(
                ValuationRun.company_id,
                ValuationRun.created_at.desc(),
                ValuationRun.id.desc(),
            )
        )
    )
    memos = list(
        session.scalars(
            select(InvestmentMemo)
            .where(*company_filter(InvestmentMemo))
            .order_by(
                InvestmentMemo.company_id,
                InvestmentMemo.created_at.desc(),
                InvestmentMemo.id.desc(),
            )
        )
    )
    analysis_runs = list(
        session.scalars(
            select(AnalysisRun)
            .where(*company_filter(AnalysisRun))
            .order_by(
                AnalysisRun.company_id,
                AnalysisRun.run_type,
                AnalysisRun.analyst_profile,
                AnalysisRun.created_at.desc(),
                AnalysisRun.id.desc(),
            )
        )
    )

    keep_price = _newest_ids(price_runs, keep_count, lambda item: item.company_id)
    keep_valuation = _newest_ids(valuations, keep_count, lambda item: item.company_id)
    keep_memo = _newest_ids(memos, keep_count, lambda item: item.company_id)
    keep_analysis = _newest_ids(
        analysis_runs,
        keep_count,
        lambda item: (item.company_id, item.run_type, item.analyst_profile),
    )
    reasons: dict[tuple[str, int], str] = {}

    for item in price_runs:
        if item.status != "deleted" and item.id == next(
            (
                run.id
                for run in price_runs
                if run.company_id == item.company_id and run.status != "deleted"
            ),
            None,
        ):
            keep_price.add(item.id)
            reasons[("price_decision_runs", item.id)] = "latest 价格决策"
    for item in valuations:
        latest_id = next((run.id for run in valuations if run.company_id == item.company_id), None)
        if item.id == latest_id:
            keep_valuation.add(item.id)
            reasons[("valuation_runs", item.id)] = "latest 估值"
    for item in memos:
        if item.is_latest or item.status == "archived":
            keep_memo.add(item.id)
            reasons[("investment_memos", item.id)] = (
                "archived Memo" if item.status == "archived" else "latest Memo"
            )
    for item in analysis_runs:
        if item.is_latest:
            keep_analysis.add(item.id)
            reasons[("analysis_runs", item.id)] = "latest 分析运行"

    memo_by_id = {item.id: item for item in memos}
    analysis_by_id = {item.id: item for item in analysis_runs}
    for item in price_runs:
        if item.id in keep_price:
            if item.valuation_run_id not in keep_valuation:
                reasons[("valuation_runs", item.valuation_run_id)] = "被保留的价格决策引用"
            if item.memo_id not in keep_memo:
                reasons[("investment_memos", item.memo_id)] = "被保留的价格决策引用"
            keep_valuation.add(item.valuation_run_id)
            keep_memo.add(item.memo_id)
    for item in valuations:
        if item.id in keep_valuation and item.memo_id is not None:
            if item.memo_id not in keep_memo:
                reasons[("investment_memos", item.memo_id)] = "被保留的估值引用"
            keep_memo.add(item.memo_id)

    changed = True
    while changed:
        changed = False
        for memo_id in tuple(keep_memo):
            memo = memo_by_id.get(memo_id)
            if memo and memo.parent_memo_id and memo.parent_memo_id not in keep_memo:
                keep_memo.add(memo.parent_memo_id)
                reasons[("investment_memos", memo.parent_memo_id)] = "被保留的 Memo 版本链引用"
                changed = True
    for memo_id in keep_memo:
        memo = memo_by_id.get(memo_id)
        if not memo:
            continue
        if memo.generation_run_id not in keep_analysis:
            reasons[("analysis_runs", memo.generation_run_id)] = "被保留的 Memo 生成记录引用"
        keep_analysis.add(memo.generation_run_id)
        for source_id in memo.source_analyst_run_ids or []:
            if source_id not in keep_analysis:
                reasons[("analysis_runs", source_id)] = "被保留的 Memo JSON 来源引用"
            keep_analysis.add(source_id)

    changed = True
    while changed:
        changed = False
        for run_id in tuple(keep_analysis):
            run = analysis_by_id.get(run_id)
            if run and run.parent_run_id and run.parent_run_id not in keep_analysis:
                keep_analysis.add(run.parent_run_id)
                reasons[("analysis_runs", run.parent_run_id)] = "被保留的分析运行父版本引用"
                changed = True

    delete_ids = {
        "price_decision_runs": [item.id for item in price_runs if item.id not in keep_price],
        "valuation_runs": [item.id for item in valuations if item.id not in keep_valuation],
        "investment_memos": [item.id for item in memos if item.id not in keep_memo],
        "analysis_runs": [item.id for item in analysis_runs if item.id not in keep_analysis],
    }
    protected = [
        {"table": table, "record_id": record_id, "reason": reason}
        for (table, record_id), reason in sorted(reasons.items())
    ]
    return _plan(
        {table: len(ids) for table, ids in delete_ids.items()},
        protected_records=protected,
        delete_ids=delete_ids,
    )


def _newest_ids(items: list[Any], count: int, key) -> set[int]:
    grouped: dict[Any, list[Any]] = defaultdict(list)
    for item in items:
        grouped[key(item)].append(item)
    return {item.id for values in grouped.values() for item in values[:count]}


def _delete_prune_plan(session: Session, plan: dict[str, Any]) -> None:
    delete_ids = plan["delete_ids"]
    for table, model in (
        ("price_decision_runs", PriceDecisionRun),
        ("valuation_runs", ValuationRun),
        ("investment_memos", InvestmentMemo),
        ("analysis_runs", AnalysisRun),
    ):
        ids = delete_ids.get(table, [])
        if ids:
            session.execute(delete(model).where(model.id.in_(ids)))
    _recompute_latest_flags(session)
    session.commit()


def _recompute_latest_flags(session: Session) -> None:
    session.execute(text("UPDATE analysis_runs SET is_latest = 0"))
    runs = list(
        session.scalars(
            select(AnalysisRun).order_by(
                AnalysisRun.company_id,
                AnalysisRun.run_type,
                AnalysisRun.analyst_profile,
                AnalysisRun.created_at.desc(),
                AnalysisRun.id.desc(),
            )
        )
    )
    seen: set[tuple[int, str, str | None]] = set()
    for run in runs:
        key = (run.company_id, run.run_type, run.analyst_profile)
        if key not in seen:
            run.is_latest = True
            seen.add(key)
    session.execute(text("UPDATE investment_memos SET is_latest = 0"))
    memos = list(
        session.scalars(
            select(InvestmentMemo)
            .where(InvestmentMemo.status != "deleted")
            .order_by(
                InvestmentMemo.company_id,
                InvestmentMemo.created_at.desc(),
                InvestmentMemo.id.desc(),
            )
        )
    )
    seen_companies: set[int] = set()
    for memo in memos:
        if memo.company_id not in seen_companies:
            memo.is_latest = True
            seen_companies.add(memo.company_id)


def _build_purge_plan(session: Session) -> dict[str, Any]:
    deleted_prices = list(
        session.scalars(select(PriceDecisionRun).where(PriceDecisionRun.status == "deleted"))
    )
    deleted_memos = list(
        session.scalars(select(InvestmentMemo).where(InvestmentMemo.status == "deleted"))
    )
    referenced_memo_ids = set(
        session.scalars(select(ValuationRun.memo_id).where(ValuationRun.memo_id.is_not(None)))
    ) | set(session.scalars(select(PriceDecisionRun.memo_id)))
    child_parent_ids = set(
        session.scalars(
            select(InvestmentMemo.parent_memo_id).where(InvestmentMemo.parent_memo_id.is_not(None))
        )
    )
    safe_memo_ids = [
        item.id
        for item in deleted_memos
        if item.id not in referenced_memo_ids and item.id not in child_parent_ids
    ]
    protected = []
    for item in deleted_memos:
        if item.id in safe_memo_ids:
            continue
        reasons = []
        if item.id in referenced_memo_ids:
            reasons.append("仍被估值或价格决策引用")
        if item.id in child_parent_ids:
            reasons.append("仍被 Memo 版本链引用")
        protected.append(
            {"table": "investment_memos", "record_id": item.id, "reason": "；".join(reasons)}
        )
    delete_ids = {
        "price_decision_runs": [item.id for item in deleted_prices],
        "investment_memos": safe_memo_ids,
    }
    return _plan(
        {table: len(ids) for table, ids in delete_ids.items()},
        protected_records=protected,
        delete_ids=delete_ids,
    )


def _purge_deleted_and_vacuum(
    session: Session,
    *,
    record: OperationTokenRecord,
    backup_id: str,
    size_before: int,
) -> DataOperationResult:
    engine = engine_from_session(session)
    database_path = sqlite_database_path(engine)
    if shutil.disk_usage(database_path.parent).free < max(size_before * 2, 16 * 1024 * 1024):
        raise DataManagementError("可用磁盘空间不足，无法安全执行 VACUUM。")
    ids = record.plan["delete_ids"]
    if ids.get("price_decision_runs"):
        session.execute(
            delete(PriceDecisionRun).where(PriceDecisionRun.id.in_(ids["price_decision_runs"]))
        )
    if ids.get("investment_memos"):
        session.execute(
            delete(InvestmentMemo).where(InvestmentMemo.id.in_(ids["investment_memos"]))
        )
    _recompute_latest_flags(session)
    session.commit()
    session.close()
    integrity = database_integrity_check(engine)
    if integrity != "ok":
        raise DataManagementError(f"物理清理后的完整性检查失败：{integrity}")
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
        connection.execute(text("VACUUM"))
        connection.execute(text("ANALYZE"))
    size_after = database_path.stat().st_size
    return DataOperationResult(
        operation_type=record.operation_type,
        affected_counts=record.plan["affected_counts"],
        backup_id=backup_id,
        protected_records=[
            ProtectedRecord.model_validate(item) for item in record.plan["protected_records"]
        ],
        database_size_before=size_before,
        database_size_after=size_after,
        reclaimed_bytes=max(0, size_before - size_after),
        integrity_check=database_integrity_check(engine),
        message="软删除记录已安全清理，数据库已完成 VACUUM 和 ANALYZE。",
    )


def _initialize_database(
    session: Session,
    *,
    backup_service: BackupService,
    backup_id: str,
    size_before: int,
) -> DataOperationResult:
    engine = engine_from_session(session)
    database_path = sqlite_database_path(engine)
    session.close()
    engine.dispose()
    try:
        Base.metadata.drop_all(bind=engine)
        init_db(engine)
        integrity = database_integrity_check(engine)
        if integrity != "ok":
            raise DataManagementError(f"初始化后的数据库完整性检查失败：{integrity}")
    except Exception:
        engine.dispose()
        backup_service.restore_backup(backup_id)
        raise
    size_after = database_path.stat().st_size
    return DataOperationResult(
        operation_type=DataOperationType.INITIALIZE_DATABASE,
        affected_counts={table: 0 for table in BUSINESS_TABLES},
        backup_id=backup_id,
        database_size_before=size_before,
        database_size_after=size_after,
        reclaimed_bytes=max(0, size_before - size_after),
        integrity_check=integrity,
        restart_required=True,
        message="数据库已按当前迁移和标准公司种子完成初始化。",
    )


def _record_counts(session: Session) -> dict[str, int]:
    return {
        "companies": _count(session, Company),
        **{table: _count(session, model) for table, model in MODEL_BY_TABLE.items()},
    }


def _count(session: Session, model, *filters) -> int:
    statement = select(func.count()).select_from(model)
    if filters:
        statement = statement.where(*filters)
    return int(session.scalar(statement) or 0)


def _database_fingerprint(session: Session) -> str:
    engine = engine_from_session(session)
    path = sqlite_database_path(engine)
    state = {
        "counts": _record_counts(session),
        "max_ids": {
            "companies": session.scalar(select(func.max(Company.id))) or 0,
            **{
                table: session.scalar(select(func.max(model.id))) or 0
                for table, model in MODEL_BY_TABLE.items()
            },
        },
        "file_size": path.stat().st_size if path.exists() else 0,
        "file_mtime_ns": path.stat().st_mtime_ns if path.exists() else 0,
    }
    payload = json.dumps(state, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
