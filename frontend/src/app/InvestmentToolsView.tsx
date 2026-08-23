import {
  Activity,
  AlertTriangle,
  BookOpen,
  CheckCircle2,
  ClipboardList,
  Clock3,
  Copy,
  Gauge,
  GripVertical,
  LoaderCircle,
  Pencil,
  Plus,
  RefreshCw,
  Save,
  Trash2,
  WalletCards,
  X
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import type { CSSProperties, DragEvent, FormEvent, KeyboardEvent } from "react";
import { useEffect, useMemo, useState } from "react";

import { ReadingListWorkspace } from "./ReadingListWorkspace";

import {
  createPortfolioHolding,
  createBuyMemoEntry,
  createPortfolioOwner,
  createPortfolioSnapshot,
  deletePortfolioHolding,
  deleteBuyMemoEntry,
  deletePortfolioOwner,
  deletePortfolioSnapshot,
  getMarketFear,
  getBuyMemoDecisions,
  getBuyMemoEntries,
  getPortfolioHoldings,
  getPortfolioOwners,
  getPortfolioSnapshots,
  getPortfolioValuation,
  importAhListing,
  importSecUsListing,
  refreshMarketFear,
  refreshPortfolioQuotes,
  reorderPortfolioOwners,
  reorderPortfolioSnapshots,
  searchPortfolioListings,
  searchAhListingCatalog,
  searchBuyMemoCompanies,
  searchSecUsListingCatalog,
  updatePortfolioHolding,
  updatePortfolioOwner,
  updatePortfolioSnapshot,
  type AhListingCatalogItem,
  type MarketFearIndicator,
  type MarketFearResponse,
  type BuyMemoCompanyCandidate,
  type BuyMemoDecisionCandidate,
  type BuyMemoEntry,
  type PortfolioCurrency,
  type PortfolioHolding,
  type PortfolioListingSearchItem,
  type PortfolioOwner,
  type PortfolioOwnerType,
  type PortfolioSnapshot,
  type PortfolioValuation,
  type PortfolioValuationItem,
  type SecUsListingCatalogItem,
  type SecurityListing
} from "../services/api";

export type InvestmentToolId = "portfolio" | "buy-memo" | "market-fear" | "reading-list";

export type InvestmentToolDefinition = {
  id: InvestmentToolId;
  label: string;
  icon: LucideIcon;
};

export const investmentToolRegistry: InvestmentToolDefinition[] = [
  { id: "portfolio", label: "持仓组合", icon: WalletCards },
  { id: "buy-memo", label: "买入备忘录", icon: ClipboardList },
  { id: "market-fear", label: "市场温度", icon: Gauge },
  { id: "reading-list", label: "阅读书单", icon: BookOpen }
];

type InvestmentToolsViewProps = {
  refreshToken: number;
};

type Message = {
  tone: "success" | "error" | "info";
  text: string;
} | null;

type OwnerDraft = {
  id: number | null;
  name: string;
  ownerType: PortfolioOwnerType;
  notes: string;
};

type SnapshotDraft = {
  id: number | null;
  title: string;
  asOfDate: string;
  baseCurrency: PortfolioCurrency;
  notes: string;
  copyFromSnapshotId: string;
};

type ListingChoice =
  | { kind: "local"; item: PortfolioListingSearchItem }
  | { kind: "ah"; item: AhListingCatalogItem }
  | { kind: "sec"; item: SecUsListingCatalogItem };

const PIE_COLORS = [
  "#0f766e",
  "#c24135",
  "#2563a6",
  "#b7791f",
  "#6d4aa2",
  "#24858b",
  "#a44d6f",
  "#607a3f",
  "#7a6251",
  "#4f6475"
];
const OTHER_PIE_COLOR = "#8a9692";

const STATUS_LABELS: Record<PortfolioValuationItem["data_status"], string> = {
  priced: "已计价",
  missing_price: "缺少行情",
  missing_fx: "缺少汇率",
  currency_mismatch: "币种不一致",
  inactive_listing: "Listing 已停用"
};

const MARKET_LABELS: Record<MarketFearIndicator["market"], string> = {
  A_SHARE: "A 股",
  HK: "港股",
  US: "美股"
};

const FRESHNESS_LABELS: Record<MarketFearIndicator["freshness"], string> = {
  fresh: "新鲜",
  stale: "已过期",
  unavailable: "不可用"
};

export function InvestmentToolsView({ refreshToken }: InvestmentToolsViewProps) {
  const [activeTool, setActiveTool] = useState<InvestmentToolId>("portfolio");

  return (
    <section className="investment-tools-view">
      <div className="tool-tabs" role="tablist" aria-label="投资小工具">
        {investmentToolRegistry.map((tool) => {
          const Icon = tool.icon;
          const isActive = activeTool === tool.id;
          return (
            <button
              key={tool.id}
              type="button"
              role="tab"
              aria-selected={isActive}
              className={isActive ? "tool-tab is-active" : "tool-tab"}
              onClick={() => setActiveTool(tool.id)}
            >
              <Icon aria-hidden="true" size={18} />
              <span>{tool.label}</span>
            </button>
          );
        })}
      </div>

      {activeTool === "portfolio" ? <PortfolioWorkspace refreshToken={refreshToken} /> : null}
      {activeTool === "buy-memo" ? <BuyMemoWorkspace refreshToken={refreshToken} /> : null}
      {activeTool === "market-fear" ? <MarketFearWorkspace refreshToken={refreshToken} /> : null}
      {activeTool === "reading-list" ? <ReadingListWorkspace refreshToken={refreshToken} /> : null}
    </section>
  );
}

function PortfolioWorkspace({ refreshToken }: InvestmentToolsViewProps) {
  const [owners, setOwners] = useState<PortfolioOwner[]>([]);
  const [snapshots, setSnapshots] = useState<PortfolioSnapshot[]>([]);
  const [holdings, setHoldings] = useState<PortfolioHolding[]>([]);
  const [valuation, setValuation] = useState<PortfolioValuation | null>(null);
  const [selectedOwnerId, setSelectedOwnerId] = useState<number | null>(null);
  const [selectedSnapshotId, setSelectedSnapshotId] = useState<number | null>(null);
  const [ownerDraft, setOwnerDraft] = useState<OwnerDraft | null>(null);
  const [snapshotDraft, setSnapshotDraft] = useState<SnapshotDraft | null>(null);
  const [ownerVersion, setOwnerVersion] = useState(0);
  const [snapshotVersion, setSnapshotVersion] = useState(0);
  const [valuationVersion, setValuationVersion] = useState(0);
  const [loadingOwners, setLoadingOwners] = useState(true);
  const [loadingSnapshots, setLoadingSnapshots] = useState(false);
  const [loadingValuation, setLoadingValuation] = useState(false);
  const [saving, setSaving] = useState(false);
  const [refreshingQuotes, setRefreshingQuotes] = useState(false);
  const [reorderingDirectory, setReorderingDirectory] = useState(false);
  const [draggedOwnerId, setDraggedOwnerId] = useState<number | null>(null);
  const [draggedSnapshotId, setDraggedSnapshotId] = useState<number | null>(null);
  const [message, setMessage] = useState<Message>(null);

  useEffect(() => {
    const controller = new AbortController();
    setLoadingOwners(true);
    getPortfolioOwners(controller.signal)
      .then((response) => {
        setOwners(response.items);
        setSelectedOwnerId((current) =>
          current && response.items.some((item) => item.id === current)
            ? current
            : (response.items[0]?.id ?? null)
        );
      })
      .catch((error: unknown) => {
        if (!isAbortError(error)) setMessage(errorMessage(error));
      })
      .finally(() => setLoadingOwners(false));
    return () => controller.abort();
  }, [ownerVersion, refreshToken]);

  useEffect(() => {
    if (!selectedOwnerId) {
      setSnapshots([]);
      setSelectedSnapshotId(null);
      return;
    }
    const controller = new AbortController();
    setLoadingSnapshots(true);
    getPortfolioSnapshots(selectedOwnerId, controller.signal)
      .then((response) => {
        setSnapshots(response.items);
        setSelectedSnapshotId((current) =>
          current && response.items.some((item) => item.id === current)
            ? current
            : (response.items[0]?.id ?? null)
        );
      })
      .catch((error: unknown) => {
        if (!isAbortError(error)) setMessage(errorMessage(error));
      })
      .finally(() => setLoadingSnapshots(false));
    return () => controller.abort();
  }, [refreshToken, selectedOwnerId, snapshotVersion]);

  useEffect(() => {
    if (!selectedSnapshotId) {
      setValuation(null);
      setHoldings([]);
      return;
    }
    const controller = new AbortController();
    setLoadingValuation(true);
    Promise.all([
      getPortfolioValuation(selectedSnapshotId, controller.signal),
      getPortfolioHoldings(selectedSnapshotId, controller.signal)
    ])
      .then(([nextValuation, holdingResponse]) => {
        setValuation(nextValuation);
        setHoldings(holdingResponse.items);
      })
      .catch((error: unknown) => {
        if (!isAbortError(error)) setMessage(errorMessage(error));
      })
      .finally(() => setLoadingValuation(false));
    return () => controller.abort();
  }, [refreshToken, selectedSnapshotId, valuationVersion]);

  const selectedOwner = owners.find((item) => item.id === selectedOwnerId) ?? null;
  const selectedSnapshot = snapshots.find((item) => item.id === selectedSnapshotId) ?? null;

  async function saveOwner(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!ownerDraft || !ownerDraft.name.trim()) return;
    setSaving(true);
    setMessage(null);
    try {
      const payload = {
        name: ownerDraft.name.trim(),
        owner_type: ownerDraft.ownerType,
        notes: ownerDraft.notes.trim() || null
      };
      const saved = ownerDraft.id
        ? await updatePortfolioOwner(ownerDraft.id, payload)
        : await createPortfolioOwner(payload);
      setOwnerDraft(null);
      setSelectedOwnerId(saved.id);
      setOwnerVersion((value) => value + 1);
      setMessage({ tone: "success", text: ownerDraft.id ? "持仓人已更新。" : "持仓人已创建。" });
    } catch (error) {
      setMessage(errorMessage(error));
    } finally {
      setSaving(false);
    }
  }

  async function removeOwner(owner: PortfolioOwner) {
    if (!window.confirm(`确认删除持仓人“${owner.name}”？`)) return;
    setSaving(true);
    setMessage(null);
    try {
      await deletePortfolioOwner(owner.id);
      setSelectedOwnerId(null);
      setOwnerVersion((value) => value + 1);
      setMessage({ tone: "success", text: "持仓人已删除。" });
    } catch (error) {
      setMessage(errorMessage(error));
    } finally {
      setSaving(false);
    }
  }

  async function saveSnapshot(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!snapshotDraft || !selectedOwnerId) return;
    setSaving(true);
    setMessage(null);
    try {
      const commonPayload = {
        title: snapshotDraft.title.trim(),
        as_of_date: snapshotDraft.asOfDate,
        base_currency: snapshotDraft.baseCurrency,
        notes: snapshotDraft.notes.trim() || null
      };
      const saved = snapshotDraft.id
        ? await updatePortfolioSnapshot(snapshotDraft.id, commonPayload)
        : await createPortfolioSnapshot(selectedOwnerId, {
            ...commonPayload,
            copy_from_snapshot_id: snapshotDraft.copyFromSnapshotId
              ? Number(snapshotDraft.copyFromSnapshotId)
              : null
          });
      setSnapshotDraft(null);
      setSelectedSnapshotId(saved.id);
      setSnapshotVersion((value) => value + 1);
      setValuationVersion((value) => value + 1);
      setMessage({ tone: "success", text: snapshotDraft.id ? "持仓快照已更新。" : "持仓快照已创建。" });
    } catch (error) {
      setMessage(errorMessage(error));
    } finally {
      setSaving(false);
    }
  }

  async function removeSnapshot(snapshot: PortfolioSnapshot) {
    if (!window.confirm(`确认删除快照“${snapshot.title}”及其全部持仓？`)) return;
    setSaving(true);
    setMessage(null);
    try {
      await deletePortfolioSnapshot(snapshot.id);
      setSelectedSnapshotId(null);
      setSnapshotVersion((value) => value + 1);
      setMessage({ tone: "success", text: "持仓快照已删除。" });
    } catch (error) {
      setMessage(errorMessage(error));
    } finally {
      setSaving(false);
    }
  }

  async function refreshQuotes() {
    if (!selectedSnapshotId) return;
    setRefreshingQuotes(true);
    setMessage(null);
    try {
      const response = await refreshPortfolioQuotes(selectedSnapshotId);
      setValuation(response.valuation);
      setValuationVersion((value) => value + 1);
      setMessage({
        tone: response.status === "success" ? "success" : "info",
        text: `行情刷新完成：${response.succeeded} 项成功，${response.failed} 项失败。`
      });
    } catch (error) {
      setMessage(errorMessage(error));
    } finally {
      setRefreshingQuotes(false);
    }
  }

  async function moveOwner(sourceId: number, targetId: number) {
    const previous = owners;
    const next = moveDirectoryItem(owners, sourceId, targetId);
    setDraggedOwnerId(null);
    if (next === owners) return;
    setOwners(next.map((item, index) => ({ ...item, display_order: index })));
    setReorderingDirectory(true);
    setMessage(null);
    try {
      const response = await reorderPortfolioOwners(next.map((item) => item.id));
      setOwners(response.items);
      setMessage({ tone: "success", text: "持仓人顺序已保存。" });
    } catch (error) {
      setOwners(previous);
      setMessage(errorMessage(error));
    } finally {
      setReorderingDirectory(false);
    }
  }

  async function moveSnapshot(sourceId: number, targetId: number) {
    if (!selectedOwnerId) return;
    const previous = snapshots;
    const next = moveDirectoryItem(snapshots, sourceId, targetId);
    setDraggedSnapshotId(null);
    if (next === snapshots) return;
    setSnapshots(next.map((item, index) => ({ ...item, display_order: index })));
    setReorderingDirectory(true);
    setMessage(null);
    try {
      const response = await reorderPortfolioSnapshots(
        selectedOwnerId,
        next.map((item) => item.id)
      );
      setSnapshots(response.items);
      setMessage({ tone: "success", text: "持仓快照顺序已保存。" });
    } catch (error) {
      setSnapshots(previous);
      setMessage(errorMessage(error));
    } finally {
      setReorderingDirectory(false);
    }
  }

  function moveOwnerByOffset(ownerId: number, offset: number) {
    const index = owners.findIndex((item) => item.id === ownerId);
    const target = owners[index + offset];
    if (target) void moveOwner(ownerId, target.id);
  }

  function moveSnapshotByOffset(snapshotId: number, offset: number) {
    const index = snapshots.findIndex((item) => item.id === snapshotId);
    const target = snapshots[index + offset];
    if (target) void moveSnapshot(snapshotId, target.id);
  }

  return (
    <div className="portfolio-workspace" role="tabpanel" aria-label="持仓组合">
      {message ? <ToolNotice message={message} onClose={() => setMessage(null)} /> : null}

      <div className="portfolio-layout">
        <aside className="portfolio-directory" aria-label="持仓目录">
          <section className="tool-section portfolio-directory__section" aria-labelledby="owner-heading">
            <div className="tool-section-heading">
              <div>
                <span className="tool-kicker">Portfolio Owners</span>
                <h2 id="owner-heading">持仓人</h2>
              </div>
              <button
                type="button"
                className="tool-icon-button"
                title="新增持仓人"
                onClick={() => setOwnerDraft(emptyOwnerDraft())}
              >
                <Plus aria-hidden="true" size={17} />
              </button>
            </div>

            {ownerDraft ? (
              <OwnerForm
                draft={ownerDraft}
                saving={saving}
                onChange={setOwnerDraft}
                onCancel={() => setOwnerDraft(null)}
                onSubmit={saveOwner}
              />
            ) : null}

            {loadingOwners ? <InlineLoading label="正在读取持仓人" /> : null}
            {!loadingOwners && owners.length === 0 ? (
              <p className="tool-empty">先新增持仓人，再创建统计日期快照。</p>
            ) : null}
            <div className="directory-list">
              {owners.map((owner) => (
                <div
                  key={owner.id}
                  className={[
                    "directory-row",
                    selectedOwnerId === owner.id ? "is-active" : "",
                    draggedOwnerId === owner.id ? "is-dragging" : ""
                  ].filter(Boolean).join(" ")}
                  onDragOver={(event) => {
                    if (draggedOwnerId !== null) event.preventDefault();
                  }}
                  onDrop={(event) => {
                    event.preventDefault();
                    if (draggedOwnerId !== null) void moveOwner(draggedOwnerId, owner.id);
                  }}
                >
                  <button
                    type="button"
                    className="directory-row__drag"
                    draggable={!reorderingDirectory && owners.length > 1}
                    disabled={reorderingDirectory || owners.length < 2}
                    title={`拖动持仓人 ${owner.name} 调整顺序`}
                    aria-label={`拖动持仓人 ${owner.name} 调整顺序`}
                    onDragStart={(event: DragEvent<HTMLButtonElement>) => {
                      event.dataTransfer.effectAllowed = "move";
                      event.dataTransfer.setData("text/plain", String(owner.id));
                      setDraggedOwnerId(owner.id);
                    }}
                    onDragEnd={() => setDraggedOwnerId(null)}
                    onKeyDown={(event: KeyboardEvent<HTMLButtonElement>) => {
                      if (event.key === "ArrowUp" || event.key === "ArrowDown") {
                        event.preventDefault();
                        moveOwnerByOffset(owner.id, event.key === "ArrowUp" ? -1 : 1);
                      }
                    }}
                  >
                    <GripVertical aria-hidden="true" size={15} />
                  </button>
                  <button
                    type="button"
                    className="directory-row__select"
                    onClick={() => {
                      setSelectedOwnerId(owner.id);
                      setSelectedSnapshotId(null);
                    }}
                  >
                    <strong>{owner.name}</strong>
                    <span>{owner.owner_type === "self" ? "本人" : "投资人"}</span>
                  </button>
                  <div className="directory-row__actions">
                    <button
                      type="button"
                      title={`编辑持仓人 ${owner.name}`}
                      onClick={() => setOwnerDraft(ownerToDraft(owner))}
                    >
                      <Pencil aria-hidden="true" size={15} />
                    </button>
                    <button
                      type="button"
                      title={`删除持仓人 ${owner.name}`}
                      onClick={() => void removeOwner(owner)}
                    >
                      <Trash2 aria-hidden="true" size={15} />
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </section>

          <section className="tool-section portfolio-directory__section" aria-labelledby="snapshot-heading">
            <div className="tool-section-heading">
              <div>
                <span className="tool-kicker">Historical Snapshots</span>
                <h2 id="snapshot-heading">持仓快照</h2>
              </div>
              <button
                type="button"
                className="tool-icon-button"
                title="创建持仓快照"
                disabled={!selectedOwner}
                onClick={() => setSnapshotDraft(emptySnapshotDraft(selectedSnapshot))}
              >
                <Plus aria-hidden="true" size={17} />
              </button>
            </div>

            {snapshotDraft ? (
              <SnapshotForm
                draft={snapshotDraft}
                snapshots={snapshots}
                saving={saving}
                onChange={setSnapshotDraft}
                onCancel={() => setSnapshotDraft(null)}
                onSubmit={saveSnapshot}
              />
            ) : null}

            {loadingSnapshots ? <InlineLoading label="正在读取历史快照" /> : null}
            {!loadingSnapshots && selectedOwner && snapshots.length === 0 ? (
              <p className="tool-empty">该持仓人还没有历史快照。</p>
            ) : null}
            <div className="directory-list">
              {snapshots.map((snapshot) => (
                <div
                  key={snapshot.id}
                  className={[
                    "directory-row",
                    selectedSnapshotId === snapshot.id ? "is-active" : "",
                    draggedSnapshotId === snapshot.id ? "is-dragging" : ""
                  ].filter(Boolean).join(" ")}
                  onDragOver={(event) => {
                    if (draggedSnapshotId !== null) event.preventDefault();
                  }}
                  onDrop={(event) => {
                    event.preventDefault();
                    if (draggedSnapshotId !== null) void moveSnapshot(draggedSnapshotId, snapshot.id);
                  }}
                >
                  <button
                    type="button"
                    className="directory-row__drag"
                    draggable={!reorderingDirectory && snapshots.length > 1}
                    disabled={reorderingDirectory || snapshots.length < 2}
                    title={`拖动快照 ${snapshot.title} 调整顺序`}
                    aria-label={`拖动快照 ${snapshot.title} 调整顺序`}
                    onDragStart={(event: DragEvent<HTMLButtonElement>) => {
                      event.dataTransfer.effectAllowed = "move";
                      event.dataTransfer.setData("text/plain", String(snapshot.id));
                      setDraggedSnapshotId(snapshot.id);
                    }}
                    onDragEnd={() => setDraggedSnapshotId(null)}
                    onKeyDown={(event: KeyboardEvent<HTMLButtonElement>) => {
                      if (event.key === "ArrowUp" || event.key === "ArrowDown") {
                        event.preventDefault();
                        moveSnapshotByOffset(snapshot.id, event.key === "ArrowUp" ? -1 : 1);
                      }
                    }}
                  >
                    <GripVertical aria-hidden="true" size={15} />
                  </button>
                  <button
                    type="button"
                    className="directory-row__select"
                    onClick={() => setSelectedSnapshotId(snapshot.id)}
                  >
                    <strong>{snapshot.title}</strong>
                    <span>{snapshot.as_of_date} · {snapshot.base_currency}</span>
                  </button>
                  <div className="directory-row__actions">
                    <button
                      type="button"
                      title={`编辑快照 ${snapshot.title}`}
                      onClick={() => setSnapshotDraft(snapshotToDraft(snapshot))}
                    >
                      <Pencil aria-hidden="true" size={15} />
                    </button>
                    <button
                      type="button"
                      title={`删除快照 ${snapshot.title}`}
                      onClick={() => void removeSnapshot(snapshot)}
                    >
                      <Trash2 aria-hidden="true" size={15} />
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </section>
        </aside>

        <div className="portfolio-content">
          {!selectedOwner ? (
            <div className="tool-empty-state">
              <WalletCards aria-hidden="true" size={28} />
              <h2>尚未建立持仓目录</h2>
              <p>新增持仓人后，可按披露日期保存多期持仓。</p>
            </div>
          ) : null}
          {selectedOwner && !selectedSnapshot ? (
            <div className="tool-empty-state">
              <Copy aria-hidden="true" size={28} />
              <h2>选择或创建持仓快照</h2>
              <p>每个统计日期使用独立快照，也可以从上一期复制持仓。</p>
            </div>
          ) : null}
          {selectedSnapshot ? (
            <PortfolioDetail
              snapshot={selectedSnapshot}
              valuation={valuation}
              holdings={holdings}
              loading={loadingValuation}
              saving={saving}
              refreshing={refreshingQuotes}
              onRefresh={() => void refreshQuotes()}
              onChanged={() => setValuationVersion((value) => value + 1)}
              onSavingChange={setSaving}
              onMessage={setMessage}
            />
          ) : null}
        </div>
      </div>
    </div>
  );
}

function OwnerForm({
  draft,
  saving,
  onChange,
  onCancel,
  onSubmit
}: {
  draft: OwnerDraft;
  saving: boolean;
  onChange: (draft: OwnerDraft) => void;
  onCancel: () => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
}) {
  return (
    <form className="compact-tool-form" onSubmit={onSubmit} aria-label={draft.id ? "编辑持仓人" : "新增持仓人"}>
      <label>
        <span>姓名</span>
        <input
          value={draft.name}
          maxLength={120}
          required
          onChange={(event) => onChange({ ...draft, name: event.target.value })}
        />
      </label>
      <label>
        <span>类型</span>
        <select
          value={draft.ownerType}
          onChange={(event) => onChange({ ...draft, ownerType: event.target.value as PortfolioOwnerType })}
        >
          <option value="self">本人</option>
          <option value="investor">投资人</option>
        </select>
      </label>
      <label>
        <span>备注</span>
        <textarea
          value={draft.notes}
          rows={2}
          maxLength={4000}
          onChange={(event) => onChange({ ...draft, notes: event.target.value })}
        />
      </label>
      <FormActions saving={saving} onCancel={onCancel} saveLabel="保存持仓人" />
    </form>
  );
}

function SnapshotForm({
  draft,
  snapshots,
  saving,
  onChange,
  onCancel,
  onSubmit
}: {
  draft: SnapshotDraft;
  snapshots: PortfolioSnapshot[];
  saving: boolean;
  onChange: (draft: SnapshotDraft) => void;
  onCancel: () => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
}) {
  return (
    <form className="compact-tool-form" onSubmit={onSubmit} aria-label={draft.id ? "编辑持仓快照" : "创建持仓快照"}>
      <label>
        <span>标题</span>
        <input
          value={draft.title}
          maxLength={160}
          required
          onChange={(event) => onChange({ ...draft, title: event.target.value })}
        />
      </label>
      <div className="compact-tool-form__split">
        <label>
          <span>统计日期</span>
          <input
            type="date"
            value={draft.asOfDate}
            max={todayString()}
            required
            onChange={(event) => onChange({ ...draft, asOfDate: event.target.value })}
          />
        </label>
        <label>
          <span>基准币种</span>
          <select
            value={draft.baseCurrency}
            onChange={(event) => onChange({ ...draft, baseCurrency: event.target.value as PortfolioCurrency })}
          >
            <option value="CNY">CNY</option>
            <option value="HKD">HKD</option>
            <option value="USD">USD</option>
          </select>
        </label>
      </div>
      {!draft.id && snapshots.length > 0 ? (
        <label>
          <span>复制持仓</span>
          <select
            value={draft.copyFromSnapshotId}
            onChange={(event) => onChange({ ...draft, copyFromSnapshotId: event.target.value })}
          >
            <option value="">不复制</option>
            {snapshots.map((snapshot) => (
              <option key={snapshot.id} value={snapshot.id}>{snapshot.title} · {snapshot.as_of_date}</option>
            ))}
          </select>
        </label>
      ) : null}
      <label>
        <span>备注</span>
        <textarea
          value={draft.notes}
          rows={2}
          maxLength={4000}
          onChange={(event) => onChange({ ...draft, notes: event.target.value })}
        />
      </label>
      <FormActions saving={saving} onCancel={onCancel} saveLabel="保存快照" />
    </form>
  );
}

function FormActions({ saving, onCancel, saveLabel }: { saving: boolean; onCancel: () => void; saveLabel: string }) {
  return (
    <div className="compact-tool-form__actions">
      <button type="button" className="tool-button tool-button--quiet" onClick={onCancel}>
        <X aria-hidden="true" size={15} />
        取消
      </button>
      <button type="submit" className="tool-button tool-button--primary" disabled={saving}>
        {saving ? <LoaderCircle className="spin" aria-hidden="true" size={15} /> : <Save aria-hidden="true" size={15} />}
        {saveLabel}
      </button>
    </div>
  );
}

function PortfolioDetail({
  snapshot,
  valuation,
  holdings,
  loading,
  saving,
  refreshing,
  onRefresh,
  onChanged,
  onSavingChange,
  onMessage
}: {
  snapshot: PortfolioSnapshot;
  valuation: PortfolioValuation | null;
  holdings: PortfolioHolding[];
  loading: boolean;
  saving: boolean;
  refreshing: boolean;
  onRefresh: () => void;
  onChanged: () => void;
  onSavingChange: (value: boolean) => void;
  onMessage: (message: Message) => void;
}) {
  const [listingQuery, setListingQuery] = useState("");
  const [listingResults, setListingResults] = useState<PortfolioListingSearchItem[]>([]);
  const [ahCatalogResults, setAhCatalogResults] = useState<AhListingCatalogItem[]>([]);
  const [catalogResults, setCatalogResults] = useState<SecUsListingCatalogItem[]>([]);
  const [catalogError, setCatalogError] = useState<string | null>(null);
  const [selectedListing, setSelectedListing] = useState<PortfolioListingSearchItem | null>(null);
  const [listingMenuOpen, setListingMenuOpen] = useState(false);
  const [activeListingIndex, setActiveListingIndex] = useState(0);
  const [quantity, setQuantity] = useState("");
  const [notes, setNotes] = useState("");
  const [searching, setSearching] = useState(false);
  const [catalogImporting, setCatalogImporting] = useState(false);
  const [editingHoldingId, setEditingHoldingId] = useState<number | null>(null);
  const [editingQuantity, setEditingQuantity] = useState("");
  const [editingNotes, setEditingNotes] = useState("");
  const slices = useMemo(() => buildPieSlices(valuation?.items ?? []), [valuation]);
  const holdingById = useMemo(() => new Map(holdings.map((item) => [item.id, item])), [holdings]);
  const listingChoices = useMemo<ListingChoice[]>(
    () => [
      ...listingResults.map((item) => ({ kind: "local" as const, item })),
      ...ahCatalogResults.map((item) => ({ kind: "ah" as const, item })),
      ...catalogResults.map((item) => ({ kind: "sec" as const, item }))
    ],
    [ahCatalogResults, catalogResults, listingResults]
  );

  useEffect(() => {
    setListingQuery("");
    setListingResults([]);
    setAhCatalogResults([]);
    setCatalogResults([]);
    setCatalogError(null);
    setSelectedListing(null);
    setListingMenuOpen(false);
    setActiveListingIndex(0);
    setQuantity("");
    setNotes("");
    setEditingHoldingId(null);
  }, [snapshot.id]);

  useEffect(() => {
    const query = listingQuery.trim();
    if (selectedListing || !query) {
      setSearching(false);
      if (!query) setListingResults([]);
      return;
    }
    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      Promise.allSettled([
        searchPortfolioListings(query, controller.signal),
        searchAhListingCatalog(query, controller.signal),
        searchSecUsListingCatalog(query, controller.signal)
      ])
        .then(([localResult, ahCatalogResult, catalogResult]) => {
          const sourceErrors: string[] = [];
          if (localResult.status === "fulfilled") {
            setListingResults(localResult.value.items);
          } else if (!isAbortError(localResult.reason)) {
            onMessage(errorMessage(localResult.reason));
          }
          if (ahCatalogResult.status === "fulfilled") {
            setAhCatalogResults(ahCatalogResult.value.items);
          } else if (!isAbortError(ahCatalogResult.reason)) {
            setAhCatalogResults([]);
            sourceErrors.push("A/H 证券目录");
          }
          if (catalogResult.status === "fulfilled") {
            setCatalogResults(catalogResult.value.items);
          } else if (!isAbortError(catalogResult.reason)) {
            setCatalogResults([]);
            sourceErrors.push("SEC 公司目录");
          }
          setCatalogError(sourceErrors.length > 0 ? `${sourceErrors.join("、")}暂不可用` : null);
          setActiveListingIndex(0);
          setListingMenuOpen(true);
        })
        .finally(() => setSearching(false));
    }, 200);
    setSearching(true);
    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [listingQuery, onMessage, selectedListing]);

  function chooseListing(listing: PortfolioListingSearchItem) {
    setSelectedListing(listing);
    setListingQuery(`${listing.company_name} · ${listing.ticker}`);
    setListingMenuOpen(false);
  }

  async function chooseListingChoice(choice: ListingChoice) {
    if (choice.kind === "local") {
      chooseListing(choice.item);
      return;
    }
    setCatalogImporting(true);
    onMessage(null);
    try {
      const listing = choice.kind === "ah"
        ? await importAhListing({ quote_id: choice.item.quote_id })
        : await importSecUsListing({
            cik: choice.item.cik,
            symbol: choice.item.symbol
          });
      chooseListing(listing);
      onMessage({
        tone: "success",
        text: `${listing.ticker} 已从${choice.kind === "ah" ? " A/H 证券目录" : " SEC 公司目录"}导入。`
      });
    } catch (error) {
      onMessage(errorMessage(error));
    } finally {
      setCatalogImporting(false);
    }
  }

  function handleListingKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key === "Escape") {
      setListingMenuOpen(false);
      return;
    }
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      if (!listingMenuOpen) setListingMenuOpen(true);
      const direction = event.key === "ArrowDown" ? 1 : -1;
      setActiveListingIndex((current) => {
        if (listingChoices.length === 0) return 0;
        return (current + direction + listingChoices.length) % listingChoices.length;
      });
      return;
    }
    if (event.key === "Enter" && listingMenuOpen && listingChoices[activeListingIndex]) {
      event.preventDefault();
      void chooseListingChoice(listingChoices[activeListingIndex]);
    }
  }

  async function addHolding(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const listing = selectedListing;
    const quantityError = validateQuantity(quantity, listing ?? undefined);
    if (!listing || quantityError) {
      onMessage({ tone: "error", text: quantityError ?? "请选择具体 Listing。" });
      return;
    }
    onSavingChange(true);
    onMessage(null);
    try {
      await createPortfolioHolding(snapshot.id, {
        listing_id: listing.id,
        quantity,
        notes: notes.trim() || null
      });
      setQuantity("");
      setNotes("");
      setListingQuery("");
      setListingResults([]);
      setAhCatalogResults([]);
      setCatalogResults([]);
      setSelectedListing(null);
      onChanged();
      onMessage({ tone: "success", text: "持仓已录入并重新估值。" });
    } catch (error) {
      onMessage(errorMessage(error));
    } finally {
      onSavingChange(false);
    }
  }

  async function saveHolding(item: PortfolioValuationItem) {
    const listing = { market: item.market } as SecurityListing;
    const quantityError = validateQuantity(editingQuantity, listing);
    if (quantityError) {
      onMessage({ tone: "error", text: quantityError });
      return;
    }
    onSavingChange(true);
    onMessage(null);
    try {
      await updatePortfolioHolding(item.holding_id, {
        quantity: editingQuantity,
        notes: editingNotes.trim() || null
      });
      setEditingHoldingId(null);
      onChanged();
      onMessage({ tone: "success", text: "持仓股数已更新并重新估值。" });
    } catch (error) {
      onMessage(errorMessage(error));
    } finally {
      onSavingChange(false);
    }
  }

  async function removeHolding(item: PortfolioValuationItem) {
    if (!window.confirm(`确认删除 ${item.company_name} ${item.ticker} 的持仓？`)) return;
    onSavingChange(true);
    onMessage(null);
    try {
      await deletePortfolioHolding(item.holding_id);
      onChanged();
      onMessage({ tone: "success", text: "持仓已删除并重新估值。" });
    } catch (error) {
      onMessage(errorMessage(error));
    } finally {
      onSavingChange(false);
    }
  }

  return (
    <div className="portfolio-detail">
      <section className="tool-section portfolio-overview" aria-labelledby="portfolio-detail-heading">
        <div className="portfolio-detail-heading">
          <div>
            <span className="tool-kicker">{snapshot.as_of_date} · 基准币种 {snapshot.base_currency}</span>
            <h2 id="portfolio-detail-heading">{snapshot.title}</h2>
          </div>
          <button
            type="button"
            className="tool-button tool-button--primary"
            disabled={refreshing || loading}
            onClick={onRefresh}
          >
            <RefreshCw className={refreshing ? "spin" : undefined} aria-hidden="true" size={16} />
            {refreshing ? "正在刷新" : "刷新全部行情"}
          </button>
        </div>

        {loading ? <InlineLoading label="正在按最新数据估值" /> : null}
        {valuation ? (
          <>
            <div className="portfolio-metrics">
              <div>
                <span>已计价总市值</span>
                <strong>{formatCurrency(valuation.priced_total, valuation.base_currency)}</strong>
              </div>
              <div>
                <span>已计价持仓</span>
                <strong>{valuation.priced_count}</strong>
              </div>
              <div className={valuation.unpriced_count > 0 ? "is-warning" : ""}>
                <span>未计价持仓</span>
                <strong>{valuation.unpriced_count}</strong>
              </div>
            </div>
            {valuation.valuation_status === "incomplete" ? (
              <div className="valuation-warning">
                <AlertTriangle aria-hidden="true" size={17} />
                组合估值不完整，未计价项目不进入总市值和比例分母。
              </div>
            ) : null}
            <PortfolioPie valuation={valuation} slices={slices} />
          </>
        ) : null}
      </section>

      <section className="tool-section holding-entry" aria-labelledby="holding-entry-heading">
        <div className="tool-section-heading">
          <div>
            <span className="tool-kicker">Listing-level Position</span>
            <h2 id="holding-entry-heading">录入持仓股数</h2>
          </div>
        </div>
        <form className="holding-entry-form" onSubmit={addHolding}>
          <label className="holding-entry-form__search">
            <span>公司与 Listing</span>
            <div
              className="listing-combobox"
              onBlur={(event) => {
                if (!event.currentTarget.contains(event.relatedTarget as Node | null)) {
                  setListingMenuOpen(false);
                }
              }}
            >
              <input
                role="combobox"
                aria-label="公司与 Listing"
                aria-autocomplete="list"
                aria-expanded={listingMenuOpen}
                aria-controls={`portfolio-listing-results-${snapshot.id}`}
                aria-activedescendant={
                  listingMenuOpen && listingChoices[activeListingIndex]
                    ? listingChoiceId(listingChoices[activeListingIndex])
                    : undefined
                }
                value={listingQuery}
                placeholder="公司名称或证券代码"
                autoComplete="off"
                onFocus={() => {
                  if (listingQuery.trim() && !selectedListing) setListingMenuOpen(true);
                }}
                onKeyDown={handleListingKeyDown}
                onChange={(event) => {
                  setListingQuery(event.target.value);
                  setListingResults([]);
                  setAhCatalogResults([]);
                  setCatalogResults([]);
                  setCatalogError(null);
                  setSelectedListing(null);
                  setActiveListingIndex(0);
                  setListingMenuOpen(Boolean(event.target.value.trim()));
                }}
              />
              {searching || catalogImporting ? (
                <LoaderCircle className="listing-combobox__spinner spin" aria-hidden="true" size={16} />
              ) : null}
              {listingMenuOpen ? (
                <div
                  id={`portfolio-listing-results-${snapshot.id}`}
                  className="listing-combobox__menu"
                  role="listbox"
                  aria-label="Listing 搜索结果"
                >
                  {!searching && listingChoices.length === 0 ? (
                    <p className="listing-combobox__empty">没有找到可录入的 Listing</p>
                  ) : null}
                  {catalogError ? <p className="listing-combobox__source-error">{catalogError}</p> : null}
                  {listingChoices.map((choice, index) => (
                    <button
                      key={listingChoiceId(choice)}
                      id={listingChoiceId(choice)}
                      type="button"
                      role="option"
                      aria-selected={
                        choice.kind === "local" && selectedListing?.id === choice.item.id
                      }
                      className={index === activeListingIndex ? "is-active" : ""}
                      disabled={catalogImporting}
                      onMouseEnter={() => setActiveListingIndex(index)}
                      onClick={() => void chooseListingChoice(choice)}
                    >
                      {choice.kind === "local" ? (
                        <>
                          <strong>{choice.item.company_name}</strong>
                          <span>
                            {choice.item.ticker} · {choice.item.exchange} · {choice.item.trading_currency} · {securityTypeLabel(choice.item.security_type)}
                          </span>
                        </>
                      ) : choice.kind === "ah" ? (
                        <>
                          <strong>{choice.item.company_name}</strong>
                          <span>
                            {choice.item.ticker} · {choice.item.exchange} · {choice.item.trading_currency} · A/H 证券目录导入
                          </span>
                        </>
                      ) : (
                        <>
                          <strong>{choice.item.company_name}</strong>
                          <span>{choice.item.ticker} · {choice.item.exchange} · SEC 目录导入</span>
                        </>
                      )}
                    </button>
                  ))}
                </div>
              ) : null}
            </div>
          </label>
          <label>
            <span>持有数量</span>
            <input
              aria-label="持有数量"
              type="text"
              inputMode="decimal"
              placeholder="例如 100 或 2.5"
              value={quantity}
              onChange={(event) => setQuantity(event.target.value.trim())}
            />
          </label>
          <label>
            <span>备注（可选）</span>
            <input value={notes} maxLength={4000} onChange={(event) => setNotes(event.target.value)} />
          </label>
          <button type="submit" className="tool-button tool-button--primary" disabled={saving || !selectedListing}>
            <Plus aria-hidden="true" size={16} />
            添加持仓
          </button>
        </form>
        <p className="field-help">数量表示所选 Listing 的实际证券单位；美股及 ADS 支持最多 8 位小数。</p>
      </section>

      <section className="tool-section holding-table-section" aria-labelledby="holding-table-heading">
        <div className="tool-section-heading">
          <div>
            <span className="tool-kicker">Derived Valuation</span>
            <h2 id="holding-table-heading">持仓明细</h2>
          </div>
          <span className="holding-count">{valuation?.holding_count ?? 0} 项</span>
        </div>
        {!loading && valuation?.items.length === 0 ? <p className="tool-empty">当前快照还没有持仓。</p> : null}
        {valuation && valuation.items.length > 0 ? (
          <div className="holding-table-wrap">
            <table className="holding-table">
              <thead>
                <tr>
                  <th>公司</th>
                  <th>证券</th>
                  <th>持有数量</th>
                  <th>最新价格</th>
                  <th>行情日期</th>
                  <th>本地市值</th>
                  <th>基准市值</th>
                  <th>比例</th>
                  <th>数据状态</th>
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                {valuation.items.map((item) => {
                  const storedHolding = holdingById.get(item.holding_id);
                  const isEditing = editingHoldingId === item.holding_id;
                  return (
                    <tr key={item.holding_id} className={item.data_status === "priced" ? "" : "is-unpriced"}>
                      <td data-label="公司"><strong>{item.company_name}</strong></td>
                      <td data-label="证券"><strong>{item.ticker}</strong><small>{item.exchange} · {securityTypeLabel(item.security_type)}</small></td>
                      <td data-label="持有数量">
                        {isEditing ? (
                          <input
                            className="table-edit-input"
                            aria-label={`编辑 ${item.ticker} 持有数量`}
                            value={editingQuantity}
                            inputMode="decimal"
                            onChange={(event) => setEditingQuantity(event.target.value.trim())}
                          />
                        ) : formatQuantity(item.quantity)}
                      </td>
                      <td data-label="最新价格">{formatNumber(item.latest_price)} {item.quote_currency ?? ""}</td>
                      <td data-label="行情日期">{formatDateTime(item.quote_as_of)}</td>
                      <td data-label="本地市值">{formatCurrency(item.local_market_value, item.trading_currency)}</td>
                      <td data-label="基准市值">{formatCurrency(item.base_market_value, valuation.base_currency)}</td>
                      <td data-label="比例">{formatPercent(item.weight)}</td>
                      <td data-label="数据状态">
                        <span className={`holding-status holding-status--${item.data_status}`} title={item.status_reason}>
                          {STATUS_LABELS[item.data_status]}
                        </span>
                        <small>{item.quote_source ?? item.status_reason}</small>
                        {item.fx_rate_date ? <small>FX {item.fx_rate_date}</small> : null}
                      </td>
                      <td data-label="操作">
                        {isEditing ? (
                          <div className="holding-actions holding-actions--edit">
                            <input
                              className="table-edit-notes"
                              aria-label={`编辑 ${item.ticker} 备注`}
                              placeholder="备注"
                              value={editingNotes}
                              onChange={(event) => setEditingNotes(event.target.value)}
                            />
                            <button type="button" title={`保存 ${item.ticker}`} onClick={() => void saveHolding(item)}>
                              <Save aria-hidden="true" size={15} />
                            </button>
                            <button type="button" title={`取消编辑 ${item.ticker}`} onClick={() => setEditingHoldingId(null)}>
                              <X aria-hidden="true" size={15} />
                            </button>
                          </div>
                        ) : (
                          <div className="holding-actions">
                            <button
                              type="button"
                              title={`编辑 ${item.ticker} 持仓`}
                              onClick={() => {
                                setEditingHoldingId(item.holding_id);
                                setEditingQuantity(formatQuantity(item.quantity));
                                setEditingNotes(storedHolding?.notes ?? "");
                              }}
                            >
                              <Pencil aria-hidden="true" size={15} />
                            </button>
                            <button type="button" title={`删除 ${item.ticker} 持仓`} onClick={() => void removeHolding(item)}>
                              <Trash2 aria-hidden="true" size={15} />
                            </button>
                          </div>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        ) : null}
      </section>
    </div>
  );
}

type PieSlice = { label: string; value: number; color: string };

function PortfolioPie({ valuation, slices }: { valuation: PortfolioValuation; slices: PieSlice[] }) {
  let cursor = 0;
  const stops = slices.map((slice) => {
    const start = cursor;
    cursor += slice.value * 100;
    return `${slice.color} ${start}% ${cursor}%`;
  });
  const style = {
    background: stops.length > 0 ? `conic-gradient(${stops.join(", ")})` : "#e6ebe9"
  } as CSSProperties;

  return (
    <div className="portfolio-allocation">
      <div
        className="portfolio-pie"
        style={style}
        role="img"
        aria-label={`已计价持仓比例图，共 ${valuation.priced_count} 项`}
      >
        <div>
          <strong>{valuation.priced_count}</strong>
          <span>已计价</span>
        </div>
      </div>
      <div className="portfolio-legend" aria-label="持仓比例图例">
        {slices.length === 0 ? <p className="tool-empty">暂无可计价持仓，比例图等待行情与汇率。</p> : null}
        {slices.map((slice) => (
          <div key={slice.label}>
            <span className="legend-swatch" style={{ background: slice.color }} />
            <strong>{slice.label}</strong>
            <span>{(slice.value * 100).toFixed(2)}%</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function BuyMemoWorkspace({ refreshToken }: InvestmentToolsViewProps) {
  const [entries, setEntries] = useState<BuyMemoEntry[]>([]);
  const [companies, setCompanies] = useState<BuyMemoCompanyCandidate[]>([]);
  const [decisions, setDecisions] = useState<BuyMemoDecisionCandidate[]>([]);
  const [selectedCompanyId, setSelectedCompanyId] = useState("");
  const [selectedDecisionId, setSelectedDecisionId] = useState("");
  const [loading, setLoading] = useState(true);
  const [loadingDecisions, setLoadingDecisions] = useState(false);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<Message>(null);
  const [version, setVersion] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    Promise.all([
      getBuyMemoEntries(controller.signal),
      searchBuyMemoCompanies("", controller.signal)
    ])
      .then(([entryResponse, companyResponse]) => {
        setEntries(entryResponse.items);
        setCompanies(companyResponse.items);
        setSelectedCompanyId((current) => {
          if (companyResponse.items.some((item) => String(item.company_id) === current)) {
            return current;
          }
          return companyResponse.items[0] ? String(companyResponse.items[0].company_id) : "";
        });
      })
      .catch((error: unknown) => {
        if (!isAbortError(error)) setMessage(errorMessage(error));
      })
      .finally(() => setLoading(false));
    return () => controller.abort();
  }, [refreshToken, version]);

  useEffect(() => {
    if (!selectedCompanyId) {
      setDecisions([]);
      setSelectedDecisionId("");
      return;
    }
    const controller = new AbortController();
    setLoadingDecisions(true);
    getBuyMemoDecisions(Number(selectedCompanyId), controller.signal)
      .then((response) => {
        setDecisions(response.items);
        const available = response.items.find((item) => !item.already_imported);
        setSelectedDecisionId(available ? String(available.price_decision_run_id) : "");
      })
      .catch((error: unknown) => {
        if (!isAbortError(error)) setMessage(errorMessage(error));
      })
      .finally(() => setLoadingDecisions(false));
    return () => controller.abort();
  }, [selectedCompanyId, version]);

  async function importDecision(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedDecisionId) return;
    setSaving(true);
    setMessage(null);
    try {
      await createBuyMemoEntry(Number(selectedDecisionId));
      setVersion((current) => current + 1);
      setMessage({ tone: "success", text: "011 投资决策结果已导入买入备忘录。" });
    } catch (error) {
      setVersion((current) => current + 1);
      setMessage(errorMessage(error));
    } finally {
      setSaving(false);
    }
  }

  async function removeEntry(entry: BuyMemoEntry) {
    if (!window.confirm(`确认从买入备忘录删除 ${entry.company_name}？`)) return;
    setSaving(true);
    setMessage(null);
    try {
      await deleteBuyMemoEntry(entry.id);
      setVersion((current) => current + 1);
      setMessage({ tone: "success", text: "买入备忘录条目已删除。" });
    } catch (error) {
      setMessage(errorMessage(error));
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="buy-memo-workspace">
      {message ? <ToolNotice message={message} onClose={() => setMessage(null)} /> : null}
      <section className="tool-section buy-memo-import" aria-labelledby="buy-memo-heading">
        <div className="tool-section-heading">
          <div>
            <span className="tool-kicker">011 Decision Snapshot</span>
            <h2 id="buy-memo-heading">买入备忘录</h2>
          </div>
          <span className="holding-count">{entries.length} 项</span>
        </div>
        <form className="buy-memo-import-form" onSubmit={importDecision}>
          <label>
            <span>公司</span>
            <select
              aria-label="买入备忘录公司"
              value={selectedCompanyId}
              disabled={loading || companies.length === 0}
              onChange={(event) => setSelectedCompanyId(event.target.value)}
            >
              {companies.length === 0 ? <option value="">暂无 011 投资决策结果</option> : null}
              {companies.map((company) => (
                <option key={company.company_id} value={company.company_id}>
                  {company.company_name} · {company.primary_ticker} · {company.decision_count} 个版本
                </option>
              ))}
            </select>
          </label>
          <label>
            <span>011 投资决策版本</span>
            <select
              aria-label="011 投资决策版本"
              value={selectedDecisionId}
              disabled={loadingDecisions || decisions.length === 0}
              onChange={(event) => setSelectedDecisionId(event.target.value)}
            >
              {decisions.length === 0 ? <option value="">暂无可导入版本</option> : null}
              {decisions.length > 0 && decisions.every((decision) => decision.already_imported) ? (
                <option value="">该公司全部版本已导入</option>
              ) : null}
              {decisions.map((decision) => (
                <option
                  key={decision.price_decision_run_id}
                  value={decision.price_decision_run_id}
                  disabled={decision.already_imported}
                >
                  011 V{decision.version_no} · {decision.listing_ticker} · {decision.latest_report_period ?? "报告期未知"}
                  {decision.already_imported ? " · 已导入" : ""}
                </option>
              ))}
            </select>
          </label>
          <button
            type="submit"
            className="tool-button tool-button--primary"
            disabled={saving || loadingDecisions || !selectedDecisionId}
          >
            {saving ? <LoaderCircle className="spin" aria-hidden="true" size={16} /> : <Plus aria-hidden="true" size={16} />}
            导入结果
          </button>
        </form>
      </section>

      <section className="tool-section buy-memo-table-section" aria-label="买入备忘录表格">
        {loading ? <InlineLoading label="正在读取买入备忘录" /> : null}
        {!loading && entries.length === 0 ? (
          <p className="tool-empty">尚未导入 011 投资决策结果。</p>
        ) : null}
        {entries.length > 0 ? (
          <div className="buy-memo-table-wrap">
            <table className="buy-memo-table">
              <thead>
                <tr>
                  <th>公司与 Listing</th>
                  <th>中性内在价值</th>
                  <th>建议买入价</th>
                  <th>设计安全边际</th>
                  <th>最新报告期</th>
                  <th>011 决策版本</th>
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                {entries.map((entry) => (
                  <tr key={entry.id}>
                    <td data-label="公司与 Listing">
                      <strong>{entry.company_name}</strong>
                      <small>{entry.listing_ticker}{entry.exchange ? ` · ${entry.exchange}` : ""}</small>
                    </td>
                    <td data-label="中性内在价值">
                      {formatCurrency(entry.base_intrinsic_value, entry.trading_currency ?? "USD")}
                    </td>
                    <td data-label="建议买入价">
                      {formatCurrency(entry.suggested_buy_price, entry.trading_currency ?? "USD")}
                    </td>
                    <td data-label="设计安全边际">{formatPercent(entry.designed_safety_margin)}</td>
                    <td data-label="最新报告期">{entry.latest_report_period ?? "--"}</td>
                    <td data-label="011 决策版本">
                      <strong>V{entry.price_decision_version_no}</strong>
                      <small>{entry.price_decision_run_version}</small>
                    </td>
                    <td data-label="操作">
                      <button
                        type="button"
                        className="tool-icon-button"
                        title={`删除 ${entry.company_name} 买入备忘录`}
                        disabled={saving}
                        onClick={() => void removeEntry(entry)}
                      >
                        <Trash2 aria-hidden="true" size={15} />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}
      </section>
    </div>
  );
}

function MarketFearWorkspace({ refreshToken }: InvestmentToolsViewProps) {
  const [data, setData] = useState<MarketFearResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState<MarketFearIndicator["market"] | "all" | null>(null);
  const [message, setMessage] = useState<Message>(null);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    getMarketFear(controller.signal)
      .then(setData)
      .catch((error: unknown) => {
        if (!isAbortError(error)) setMessage(errorMessage(error));
      })
      .finally(() => setLoading(false));
    return () => controller.abort();
  }, [refreshToken]);

  async function runRefresh(market?: MarketFearIndicator["market"]) {
    setRefreshing(market ?? "all");
    setMessage(null);
    try {
      const response = await refreshMarketFear(market);
      if (market && data) {
        const updated = response.items.find((item) => item.market === market);
        setData({
          ...data,
          status: response.status,
          items: data.items.map((item) => item.market === market && updated ? updated : item)
        });
      } else {
        setData(response);
      }
      setMessage({
        tone: response.status === "success" ? "success" : "info",
        text: response.status === "success" ? "日频指标已刷新。" : "部分数据源未更新，已保留最近成功缓存。"
      });
    } catch (error) {
      setMessage(errorMessage(error));
    } finally {
      setRefreshing(null);
    }
  }

  return (
    <div className="market-fear-workspace" role="tabpanel" aria-label="市场温度">
      {message ? <ToolNotice message={message} onClose={() => setMessage(null)} /> : null}
      <section className="market-fear-header">
        <div>
          <span className="tool-kicker">Daily Volatility Close</span>
          <h2>三市场波动率温度</h2>
          <p>各市场按自身过去 3 年历史百分位映射，不能直接比较指数绝对值。</p>
        </div>
        <button
          type="button"
          className="tool-button tool-button--primary"
          disabled={refreshing !== null}
          onClick={() => void runRefresh()}
        >
          <RefreshCw className={refreshing === "all" ? "spin" : undefined} aria-hidden="true" size={16} />
          刷新全部指标
        </button>
      </section>

      <div className="market-fear-disclaimer">
        <AlertTriangle aria-hidden="true" size={18} />
        <span>{data?.notice ?? "波动率指标反映市场预期波动程度，不代表价格方向，也不是买卖建议。"}</span>
      </div>

      {loading ? <InlineLoading label="正在读取市场温度" /> : null}
      <div className="market-fear-grid">
        {data?.items.map((item) => (
          <MarketFearCard
            key={item.market}
            item={item}
            refreshing={refreshing === item.market}
            onRefresh={() => void runRefresh(item.market)}
          />
        ))}
      </div>
      {!loading && (!data || data.items.length === 0) ? (
        <div className="tool-empty-state">
          <Activity aria-hidden="true" size={28} />
          <h2>尚无成功缓存</h2>
          <p>刷新指标后将保存最近一次成功的日频结果。</p>
        </div>
      ) : null}
    </div>
  );
}

function MarketFearCard({
  item,
  refreshing,
  onRefresh
}: {
  item: MarketFearIndicator;
  refreshing: boolean;
  onRefresh: () => void;
}) {
  const score = Math.max(0, Math.min(100, Number(item.temperature_score ?? 0)));
  return (
    <article className={`market-fear-card market-fear-card--${item.freshness}`}>
      <header>
        <div>
          <span>{MARKET_LABELS[item.market]}</span>
          <h3>{item.indicator_name}</h3>
          <small>{item.indicator_code}</small>
        </div>
        <button type="button" className="tool-icon-button" title={`刷新 ${MARKET_LABELS[item.market]} 指标`} disabled={refreshing} onClick={onRefresh}>
          <RefreshCw className={refreshing ? "spin" : undefined} aria-hidden="true" size={16} />
        </button>
      </header>
      <div className="fear-value-row">
        <strong>{formatNumber(item.value, 2)}</strong>
        <span className={Number(item.daily_change ?? 0) >= 0 ? "is-up" : "is-down"}>
          {formatSigned(item.daily_change)}
        </span>
      </div>
      <div className="fear-date"><Clock3 aria-hidden="true" size={14} />数据日期 {item.data_date ?? "--"}</div>
      <dl className="fear-metrics">
        <div><dt>20 日均值</dt><dd>{formatNumber(item.moving_average_20, 2)}</dd></div>
        <div><dt>3 年百分位</dt><dd>{formatNumber(item.percentile_3y, 1)}%</dd></div>
        <div><dt>历史样本</dt><dd>{item.observation_count ?? "--"}</dd></div>
      </dl>
      <div className="temperature-block">
        <div><span>市场温度</span><strong>{item.temperature_level ?? "不可用"}</strong></div>
        <div className="temperature-track" aria-label={`市场温度 ${formatNumber(item.temperature_score, 1)}`}>
          <span style={{ width: `${score}%` }} />
        </div>
        <small>{formatNumber(item.temperature_score, 1)} / 100</small>
      </div>
      {item.is_proxy && item.proxy_notice ? <p className="proxy-notice">{item.proxy_notice}</p> : null}
      {item.refresh_error ? <p className="fear-error">{item.refresh_error}</p> : null}
      <footer>
        <span className={`freshness freshness--${item.freshness}`}>
          {item.freshness === "fresh" ? <CheckCircle2 aria-hidden="true" size={14} /> : <AlertTriangle aria-hidden="true" size={14} />}
          {FRESHNESS_LABELS[item.freshness]}
        </span>
        <div>
          {item.source_url ? <a href={item.source_url} target="_blank" rel="noreferrer">{item.source ?? "数据来源"}</a> : <span>{item.source ?? "暂无来源"}</span>}
          <small>抓取 {formatDateTime(item.fetched_at)}</small>
        </div>
      </footer>
    </article>
  );
}

function ToolNotice({ message, onClose }: { message: NonNullable<Message>; onClose: () => void }) {
  return (
    <div className={`tool-notice tool-notice--${message.tone}`} role={message.tone === "error" ? "alert" : "status"}>
      <span>{message.text}</span>
      <button type="button" title="关闭提示" onClick={onClose}><X aria-hidden="true" size={15} /></button>
    </div>
  );
}

function InlineLoading({ label }: { label: string }) {
  return <div className="tool-loading"><LoaderCircle className="spin" aria-hidden="true" size={16} /><span>{label}</span></div>;
}

function emptyOwnerDraft(): OwnerDraft {
  return { id: null, name: "", ownerType: "self", notes: "" };
}

function ownerToDraft(owner: PortfolioOwner): OwnerDraft {
  return { id: owner.id, name: owner.name, ownerType: owner.owner_type, notes: owner.notes ?? "" };
}

function emptySnapshotDraft(previous: PortfolioSnapshot | null): SnapshotDraft {
  return {
    id: null,
    title: "",
    asOfDate: todayString(),
    baseCurrency: previous?.base_currency ?? "CNY",
    notes: "",
    copyFromSnapshotId: previous ? String(previous.id) : ""
  };
}

function snapshotToDraft(snapshot: PortfolioSnapshot): SnapshotDraft {
  return {
    id: snapshot.id,
    title: snapshot.title,
    asOfDate: snapshot.as_of_date,
    baseCurrency: snapshot.base_currency,
    notes: snapshot.notes ?? "",
    copyFromSnapshotId: ""
  };
}

function buildPieSlices(items: PortfolioValuationItem[]): PieSlice[] {
  const priced = items
    .filter((item) => item.weight !== null && Number(item.weight) > 0)
    .map((item) => ({ label: `${item.company_name} · ${item.ticker}`, value: Number(item.weight) }))
    .sort((left, right) => right.value - left.value);
  if (priced.length <= 10) {
    return priced.map((item, index) => ({ ...item, color: PIE_COLORS[index % PIE_COLORS.length] }));
  }
  const primary = priced.slice(0, 10);
  const other = priced.slice(10).reduce((sum, item) => sum + item.value, 0);
  return [
    ...primary.map((item, index) => ({ ...item, color: PIE_COLORS[index] })),
    { label: "其他", value: other, color: OTHER_PIE_COLOR }
  ];
}

function moveDirectoryItem<T extends { id: number }>(items: T[], sourceId: number, targetId: number): T[] {
  const sourceIndex = items.findIndex((item) => item.id === sourceId);
  const targetIndex = items.findIndex((item) => item.id === targetId);
  if (sourceIndex < 0 || targetIndex < 0 || sourceIndex === targetIndex) return items;
  const next = [...items];
  const [moved] = next.splice(sourceIndex, 1);
  next.splice(targetIndex, 0, moved);
  return next;
}

function validateQuantity(quantity: string, listing?: Pick<SecurityListing, "market">): string | null {
  if (!/^\d+(\.\d{1,8})?$/.test(quantity) || Number(quantity) <= 0) {
    return "持有数量必须大于 0，且最多保留 8 位小数。";
  }
  if ((listing?.market === "A_SHARE" || listing?.market === "HK") && quantity.includes(".")) {
    return "A 股和港股持仓请输入整数证券数量。";
  }
  return null;
}

function securityTypeLabel(value: string): string {
  if (value === "ads") return "ADS";
  if (value === "common_stock") return "普通股";
  return value;
}

function listingChoiceId(choice: ListingChoice): string {
  if (choice.kind === "local") return `portfolio-listing-option-local-${choice.item.id}`;
  if (choice.kind === "ah") return `portfolio-listing-option-ah-${choice.item.quote_id}`;
  return `portfolio-listing-option-sec-${choice.item.cik}-${choice.item.symbol}`;
}

function formatQuantity(value: string): string {
  return value.replace(/\.0+$/, "").replace(/(\.\d*?)0+$/, "$1");
}

function formatNumber(value: string | null, maximumFractionDigits = 4): string {
  if (value === null || value === "" || !Number.isFinite(Number(value))) return "--";
  return new Intl.NumberFormat("zh-CN", { maximumFractionDigits }).format(Number(value));
}

function formatCurrency(value: string | null, currency: string): string {
  if (value === null || !Number.isFinite(Number(value))) return "--";
  return new Intl.NumberFormat("zh-CN", {
    style: "currency",
    currency,
    maximumFractionDigits: 2
  }).format(Number(value));
}

function formatPercent(value: string | null): string {
  return value === null ? "--" : `${(Number(value) * 100).toFixed(2)}%`;
}

function formatSigned(value: string | null): string {
  if (value === null || !Number.isFinite(Number(value))) return "--";
  const number = Number(value);
  return `${number > 0 ? "+" : ""}${number.toFixed(2)}`;
}

function formatDateTime(value: string | null): string {
  if (!value) return "--";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return new Intl.DateTimeFormat("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false
  }).format(parsed);
}

function todayString(): string {
  const now = new Date();
  const local = new Date(now.getTime() - now.getTimezoneOffset() * 60_000);
  return local.toISOString().slice(0, 10);
}

function errorMessage(error: unknown): NonNullable<Message> {
  return { tone: "error", text: error instanceof Error ? error.message : "操作失败，请稍后重试。" };
}

function isAbortError(error: unknown): boolean {
  return error instanceof DOMException && error.name === "AbortError";
}
