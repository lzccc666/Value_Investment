import {
  ArchiveRestore,
  CheckCircle2,
  Database,
  FileArchive,
  HardDrive,
  LoaderCircle,
  Save,
  Search,
  Settings2,
  ShieldAlert,
  Trash2,
  Wrench
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";
import { useCallback, useEffect, useState } from "react";

import {
  createBackup,
  deleteBackup,
  executeDataOperation,
  getAutomaticBackupSettings,
  getBackups,
  getCompanies,
  getDataManagementSummary,
  previewBackupRestore,
  previewDataOperation,
  updateAutomaticBackupSettings,
  verifyBackup,
  type AutomaticBackupSettings,
  type BackupManifest,
  type Company,
  type DataManagementSummary,
  type DataOperationParameters,
  type DataOperationPreview,
  type DataOperationResult,
  type DataOperationType
} from "../services/api";

type DataManagementViewProps = {
  refreshToken: number;
};

type ActionState =
  | { kind: "idle"; message: "" }
  | { kind: "loading"; message: string }
  | { kind: "success" | "error" | "blocked" | "restart"; message: string };

const TABLE_LABELS: Record<string, string> = {
  companies: "公司",
  security_listings: "证券 Listing",
  market_snapshots: "行情快照",
  fx_rate_snapshots: "汇率快照",
  portfolio_owners: "持仓人",
  portfolio_snapshots: "持仓快照",
  portfolio_holdings: "持仓明细",
  market_fear_snapshots: "市场温度缓存",
  financial_statements: "财务报表",
  announcements: "公告",
  evidence: "外部证据",
  analysis_runs: "分析运行",
  investment_memos: "投资备忘录",
  valuation_runs: "估值版本",
  price_decision_runs: "价格决策",
  backups: "备份"
};

export function DataManagementView({ refreshToken }: DataManagementViewProps) {
  const [summary, setSummary] = useState<DataManagementSummary | null>(null);
  const [backups, setBackups] = useState<BackupManifest[]>([]);
  const [backupSettings, setBackupSettings] = useState<AutomaticBackupSettings | null>(null);
  const [companies, setCompanies] = useState<Company[]>([]);
  const [companyQuery, setCompanyQuery] = useState("");
  const [selectedCompanyId, setSelectedCompanyId] = useState<number | null>(null);
  const [pruneCompanyId, setPruneCompanyId] = useState<number | null>(null);
  const [keepCount, setKeepCount] = useState(3);
  const [preview, setPreview] = useState<DataOperationPreview | null>(null);
  const [confirmation, setConfirmation] = useState("");
  const [deleteBackupId, setDeleteBackupId] = useState<string | null>(null);
  const [state, setState] = useState<ActionState>({ kind: "idle", message: "" });
  const [result, setResult] = useState<DataOperationResult | null>(null);

  const loadPage = useCallback(async (signal?: AbortSignal): Promise<boolean> => {
    try {
      const [nextSummary, backupList, nextSettings, companyList] = await Promise.all([
        getDataManagementSummary(signal),
        getBackups(signal),
        getAutomaticBackupSettings(signal),
        getCompanies({ limit: 100, offset: 0, signal })
      ]);
      setSummary(nextSummary);
      setBackups(backupList.items);
      setBackupSettings(nextSettings);
      setCompanies(companyList.items);
      return true;
    } catch (error) {
      if (!signal?.aborted) {
        setState(toErrorState(error));
      }
      return false;
    }
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    setState({ kind: "loading", message: "正在读取数据库状态" });
    loadPage(controller.signal).then((loaded) => {
      if (loaded && !controller.signal.aborted) {
        setState({ kind: "idle", message: "" });
      }
    });
    return () => controller.abort();
  }, [loadPage, refreshToken]);

  async function searchCompanies() {
    setState({ kind: "loading", message: "正在搜索公司" });
    try {
      const response = await getCompanies({ q: companyQuery.trim(), limit: 100, offset: 0 });
      setCompanies(response.items);
      setState({ kind: "idle", message: "" });
    } catch (error) {
      setState(toErrorState(error));
    }
  }

  async function prepareOperation(
    operationType: DataOperationType,
    parameters: DataOperationParameters = {},
    restore = false
  ) {
    setState({ kind: "loading", message: "正在计算真实影响范围" });
    setResult(null);
    try {
      const nextPreview = restore && parameters.backup_id
        ? await previewBackupRestore(parameters.backup_id)
        : await previewDataOperation(operationType, parameters);
      setPreview(nextPreview);
      setConfirmation("");
      setDeleteBackupId(operationType === "delete_backup" ? parameters.backup_id ?? null : null);
      setState({ kind: "idle", message: "" });
    } catch (error) {
      setState(toErrorState(error));
    }
  }

  async function confirmOperation() {
    if (!preview) {
      return;
    }
    setState({ kind: "loading", message: "数据库维护操作执行中" });
    try {
      const nextResult = deleteBackupId
        ? await deleteBackup(
            deleteBackupId,
            preview.operation_token,
            confirmation
          )
        : await executeDataOperation(preview.operation_token, confirmation);
      setResult(nextResult);
      setPreview(null);
      setDeleteBackupId(null);
      setConfirmation("");
      setState({
        kind: nextResult.restart_required ? "restart" : "success",
        message: nextResult.message
      });
      await loadPage();
    } catch (error) {
      setState(toErrorState(error));
    }
  }

  async function handleCreateBackup() {
    setState({ kind: "loading", message: "正在创建一致性备份" });
    try {
      const manifest = await createBackup("manual");
      setState({ kind: "success", message: `备份 ${manifest.backup_id} 已创建并校验` });
      await loadPage();
    } catch (error) {
      setState(toErrorState(error));
    }
  }

  async function handleVerifyBackup(backupId: string) {
    setState({ kind: "loading", message: "正在校验备份" });
    try {
      const verification = await verifyBackup(backupId);
      setState({
        kind: verification.valid ? "success" : "error",
        message: verification.valid
          ? `备份 ${backupId} 的 SHA-256 与 SQLite 完整性检查均通过`
          : `备份 ${backupId} 校验失败：${verification.integrity_check}`
      });
    } catch (error) {
      setState(toErrorState(error));
    }
  }

  async function saveBackupSettings() {
    if (!backupSettings) {
      return;
    }
    setState({ kind: "loading", message: "正在保存自动备份设置" });
    try {
      const saved = await updateAutomaticBackupSettings(backupSettings);
      setBackupSettings(saved);
      setState({ kind: "success", message: "自动备份设置已保存" });
    } catch (error) {
      setState(toErrorState(error));
    }
  }

  const selectedCompany = companies.find((item) => item.id === selectedCompanyId) ?? null;

  return (
    <div className="data-management-view">
      <ActionNotice state={state} result={result} />

      <section className="dm-section" aria-labelledby="database-overview-heading">
        <SectionHeading
          icon={Database}
          title="数据库概览"
          description={summary?.database_path ?? "正在读取数据库位置"}
        />
        {summary ? (
          <>
            <dl className="dm-metrics">
              <Metric label="数据库大小" value={formatBytes(summary.database_size)} />
              <Metric label="公司" value={String(summary.record_counts.companies ?? 0)} />
              <Metric
                label="业务记录"
                value={String(
                  Object.entries(summary.record_counts)
                    .filter(([key]) => key !== "companies")
                    .reduce((total, [, value]) => total + value, 0)
                )}
              />
              <Metric
                label="软删除"
                value={String(Object.values(summary.soft_deleted_counts).reduce((a, b) => a + b, 0))}
              />
              <Metric label="完整性" value={summary.integrity_check} />
              <Metric
                label="最近备份"
                value={summary.latest_backup ? formatDate(summary.latest_backup.created_at) : "尚无"}
              />
            </dl>
            <RecordCountTable counts={summary.record_counts} />
          </>
        ) : (
          <LoadingLine />
        )}
      </section>

      <section className="dm-section" aria-labelledby="company-cleanup-heading">
        <SectionHeading
          icon={Trash2}
          title="公司数据清理"
          description="保留公司证券身份、档案与当前行情，清空全部下游研究数据"
        />
        <div className="dm-form-row">
          <label className="dm-field dm-field--grow">
            <span>搜索公司</span>
            <div className="dm-input-action">
              <input
                value={companyQuery}
                onChange={(event) => setCompanyQuery(event.target.value)}
                placeholder="名称、代码或行业"
              />
              <button className="icon-button" type="button" title="搜索公司" onClick={searchCompanies}>
                <Search aria-hidden="true" size={17} />
              </button>
            </div>
          </label>
          <label className="dm-field dm-field--grow">
            <span>目标公司</span>
            <select
              value={selectedCompanyId ?? ""}
              onChange={(event) => setSelectedCompanyId(Number(event.target.value) || null)}
            >
              <option value="">请选择</option>
              {companies.map((company) => (
                <option key={company.id} value={company.id}>
                  {company.name} · {company.ticker}
                </option>
              ))}
            </select>
          </label>
          <button
            className="dm-danger-action"
            type="button"
            disabled={!selectedCompany}
            onClick={() =>
              selectedCompany &&
              prepareOperation("reset_company_research_data", { company_id: selectedCompany.id })
            }
          >
            <Trash2 aria-hidden="true" size={16} />
            预览影响
          </button>
        </div>
      </section>

      <section className="dm-section" aria-labelledby="history-cleanup-heading">
        <SectionHeading
          icon={ShieldAlert}
          title="全局分析历史"
          description="删除分析师、Memo、估值和价格决策；保留财务、公告、Evidence 及搜索诊断"
        />
        <button
          className="dm-danger-action"
          type="button"
          onClick={() => prepareOperation("clear_analysis_history")}
        >
          <Trash2 aria-hidden="true" size={16} />
          预览全局清理
        </button>
      </section>

      <section className="dm-section" aria-labelledby="version-retention-heading">
        <SectionHeading
          icon={FileArchive}
          title="版本保留"
          description="按依赖方向生成 prune plan，并保护 latest、archived 及下游引用"
        />
        <div className="dm-form-row">
          <label className="dm-field dm-field--grow">
            <span>公司范围</span>
            <select
              value={pruneCompanyId ?? ""}
              onChange={(event) => setPruneCompanyId(Number(event.target.value) || null)}
            >
              <option value="">全部公司</option>
              {companies.map((company) => (
                <option key={company.id} value={company.id}>
                  {company.name} · {company.ticker}
                </option>
              ))}
            </select>
          </label>
          <label className="dm-field dm-field--number">
            <span>每组保留版本</span>
            <input
              type="number"
              min={1}
              max={100}
              value={keepCount}
              onChange={(event) => setKeepCount(Number(event.target.value))}
            />
          </label>
          <button
            className="primary-action"
            type="button"
            disabled={!Number.isInteger(keepCount) || keepCount < 1 || keepCount > 100}
            onClick={() =>
              prepareOperation("prune_versions", {
                company_id: pruneCompanyId,
                keep_count: keepCount
              })
            }
          >
            <FileArchive aria-hidden="true" size={16} />
            生成 prune plan
          </button>
        </div>
      </section>

      <section className="dm-section" aria-labelledby="backup-heading">
        <SectionHeading
          icon={HardDrive}
          title="备份与恢复"
          description="SQLite Backup API 一致性快照，附 manifest、SHA-256 和完整性校验"
          action={
            <button className="primary-action" type="button" onClick={handleCreateBackup}>
              <Save aria-hidden="true" size={16} />
              创建备份
            </button>
          }
        />
        <BackupTable
          backups={backups}
          onVerify={handleVerifyBackup}
          onRestore={(backupId) =>
            prepareOperation("restore_backup", { backup_id: backupId }, true)
          }
          onDelete={(backupId) =>
            prepareOperation("delete_backup", { backup_id: backupId })
          }
        />
        {backupSettings ? (
          <div className="dm-settings-row">
            <label className="dm-toggle">
              <input
                type="checkbox"
                checked={backupSettings.enabled}
                onChange={(event) =>
                  setBackupSettings({ ...backupSettings, enabled: event.target.checked })
                }
              />
              <span>自动备份</span>
            </label>
            <label className="dm-field dm-field--number">
              <span>间隔小时</span>
              <input
                type="number"
                min={1}
                max={720}
                value={backupSettings.interval_hours}
                onChange={(event) =>
                  setBackupSettings({
                    ...backupSettings,
                    interval_hours: Number(event.target.value)
                  })
                }
              />
            </label>
            <label className="dm-field dm-field--number">
              <span>最多保留</span>
              <input
                type="number"
                min={1}
                max={200}
                value={backupSettings.max_backups}
                onChange={(event) =>
                  setBackupSettings({
                    ...backupSettings,
                    max_backups: Number(event.target.value)
                  })
                }
              />
            </label>
            <button className="primary-action" type="button" onClick={saveBackupSettings}>
              <Settings2 aria-hidden="true" size={16} />
              保存设置
            </button>
          </div>
        ) : null}
      </section>

      <section className="dm-section dm-section--critical" aria-labelledby="maintenance-heading">
        <SectionHeading
          icon={Wrench}
          title="数据库维护"
          description="维护期间暂停写入；所有破坏性操作先自动创建并校验备份"
        />
        <div className="dm-command-row">
          <button
            className="dm-danger-action"
            type="button"
            onClick={() => prepareOperation("purge_deleted_and_vacuum")}
          >
            <HardDrive aria-hidden="true" size={16} />
            清理软删除并压缩
          </button>
          <button
            className="dm-danger-action dm-danger-action--critical"
            type="button"
            onClick={() => prepareOperation("initialize_database")}
          >
            <ShieldAlert aria-hidden="true" size={16} />
            完整初始化数据库
          </button>
        </div>
      </section>

      {preview ? (
        <ConfirmationDialog
          preview={preview}
          confirmation={confirmation}
          loading={state.kind === "loading"}
          onConfirmationChange={setConfirmation}
          onCancel={() => {
            setPreview(null);
            setDeleteBackupId(null);
          }}
          onConfirm={confirmOperation}
        />
      ) : null}
    </div>
  );
}

function SectionHeading({
  icon: Icon,
  title,
  description,
  action
}: {
  icon: LucideIcon;
  title: string;
  description: string;
  action?: ReactNode;
}) {
  return (
    <div className="dm-section-heading">
      <div className="dm-section-title">
        <Icon aria-hidden="true" size={20} />
        <div>
          <h2>{title}</h2>
          <p>{description}</p>
        </div>
      </div>
      {action}
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt>{label}</dt>
      <dd>{value}</dd>
    </div>
  );
}

function RecordCountTable({ counts }: { counts: Record<string, number> }) {
  return (
    <div className="dm-count-grid" aria-label="数据库记录数量">
      {Object.entries(counts).map(([table, count]) => (
        <div key={table}>
          <span>{TABLE_LABELS[table] ?? table}</span>
          <strong>{count}</strong>
        </div>
      ))}
    </div>
  );
}

function BackupTable({
  backups,
  onVerify,
  onRestore,
  onDelete
}: {
  backups: BackupManifest[];
  onVerify: (backupId: string) => void;
  onRestore: (backupId: string) => void;
  onDelete: (backupId: string) => void;
}) {
  if (!backups.length) {
    return <p className="dm-empty">尚无备份</p>;
  }
  return (
    <div className="dm-table-scroll">
      <table className="dm-table">
        <thead>
          <tr>
            <th>创建时间</th>
            <th>原因</th>
            <th>大小</th>
            <th>校验</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          {backups.map((backup) => (
            <tr key={backup.backup_id}>
              <td>
                <strong>{formatDate(backup.created_at)}</strong>
                <small>{backup.backup_id}</small>
              </td>
              <td>{backup.reason}</td>
              <td>{formatBytes(backup.file_size)}</td>
              <td>{backup.verified ? "已通过" : "未校验"}</td>
              <td>
                <div className="dm-table-actions">
                  <button type="button" title="校验备份" onClick={() => onVerify(backup.backup_id)}>
                    <CheckCircle2 aria-hidden="true" size={16} />
                  </button>
                  <button type="button" title="恢复备份" onClick={() => onRestore(backup.backup_id)}>
                    <ArchiveRestore aria-hidden="true" size={16} />
                  </button>
                  <button
                    className="dm-table-action--danger"
                    type="button"
                    title="删除备份"
                    onClick={() => onDelete(backup.backup_id)}
                  >
                    <Trash2 aria-hidden="true" size={16} />
                  </button>
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ConfirmationDialog({
  preview,
  confirmation,
  loading,
  onConfirmationChange,
  onCancel,
  onConfirm
}: {
  preview: DataOperationPreview;
  confirmation: string;
  loading: boolean;
  onConfirmationChange: (value: string) => void;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  return (
    <div className="dm-dialog-backdrop" role="presentation">
      <div className="dm-dialog" role="dialog" aria-modal="true" aria-labelledby="dm-dialog-heading">
        <div className="dm-dialog-heading">
          <ShieldAlert aria-hidden="true" size={22} />
          <div>
            <h2 id="dm-dialog-heading">确认数据库操作</h2>
            <p>令牌将在 {formatDate(preview.expires_at)} 过期，且只能使用一次。</p>
          </div>
        </div>
        <RecordCountTable counts={preview.affected_counts} />
        {preview.protected_records.length ? (
          <div className="dm-protected-list">
            <strong>受引用保护或被阻塞</strong>
            <ul>
              {preview.protected_records.map((item) => (
                <li key={`${item.table}-${item.record_id}`}>
                  {TABLE_LABELS[item.table] ?? item.table} #{item.record_id}：{item.reason}
                </li>
              ))}
            </ul>
          </div>
        ) : null}
        <p className="dm-backup-note">
          {preview.requires_backup ? "执行前将自动创建并校验备份。" : "该操作不会修改当前数据库。"}
        </p>
        <label className="dm-field">
          <span>输入确认短语：{preview.confirmation_phrase}</span>
          <input
            autoFocus
            value={confirmation}
            onChange={(event) => onConfirmationChange(event.target.value)}
          />
        </label>
        <div className="dm-dialog-actions">
          <button className="dm-secondary-action" type="button" disabled={loading} onClick={onCancel}>
            取消
          </button>
          <button
            className="dm-danger-action dm-danger-action--critical"
            type="button"
            disabled={loading || confirmation !== preview.confirmation_phrase}
            onClick={onConfirm}
          >
            {loading ? <LoaderCircle className="dm-spin" aria-hidden="true" size={16} /> : <Trash2 aria-hidden="true" size={16} />}
            确认执行
          </button>
        </div>
      </div>
    </div>
  );
}

function ActionNotice({ state, result }: { state: ActionState; result: DataOperationResult | null }) {
  if (state.kind === "idle") {
    return null;
  }
  return (
    <div className={`dm-notice dm-notice--${state.kind}`} role="status">
      {state.kind === "loading" ? (
        <LoaderCircle className="dm-spin" aria-hidden="true" size={18} />
      ) : state.kind === "success" ? (
        <CheckCircle2 aria-hidden="true" size={18} />
      ) : (
        <ShieldAlert aria-hidden="true" size={18} />
      )}
      <div>
        <strong>{state.message}</strong>
        {result?.backup_id ? <span>安全备份：{result.backup_id}</span> : null}
        {result?.reclaimed_bytes != null ? (
          <span>释放空间：{formatBytes(result.reclaimed_bytes)}</span>
        ) : null}
      </div>
    </div>
  );
}

function LoadingLine() {
  return (
    <div className="dm-loading-line">
      <LoaderCircle className="dm-spin" aria-hidden="true" size={18} />
      正在读取
    </div>
  );
}

function toErrorState(error: unknown): ActionState {
  const message = error instanceof Error ? error.message : "数据管理操作失败";
  const blocked = /维护|阻塞|引用|令牌|状态已变化/.test(message);
  return { kind: blocked ? "blocked" : "error", message };
}

function formatBytes(value: number): string {
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`;
  if (value < 1024 * 1024 * 1024) return `${(value / 1024 / 1024).toFixed(1)} MB`;
  return `${(value / 1024 / 1024 / 1024).toFixed(2)} GB`;
}

function formatDate(value: string): string {
  return new Intl.DateTimeFormat("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false
  }).format(new Date(value));
}
