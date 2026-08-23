import {
  BookOpen,
  LoaderCircle,
  Pencil,
  Plus,
  RotateCcw,
  Save,
  Trash2,
  X
} from "lucide-react";
import type { FormEvent, KeyboardEvent } from "react";
import { useEffect, useMemo, useState } from "react";

import {
  createReadingBook,
  createReadingProgress,
  deleteReadingBook,
  deleteReadingProgress,
  getReadingBooks,
  updateReadingBook,
  updateReadingProgress,
  type ReadingBook,
  type ReadingBookStatus,
  type ReadingProgressEntry
} from "../services/api";

type ReadingListWorkspaceProps = {
  refreshToken: number;
};

type BookDraft = {
  id: number | null;
  title: string;
  author: string;
  status: ReadingBookStatus;
  notes: string;
  initialProgress: number;
};

type Notice = {
  tone: "success" | "error";
  text: string;
} | null;

const STATUS_LABELS: Record<ReadingBookStatus, string> = {
  reading: "阅读中",
  planned: "待阅读",
  finished: "已读完"
};

const EMPTY_DRAFT: BookDraft = {
  id: null,
  title: "",
  author: "",
  status: "planned",
  notes: "",
  initialProgress: 0
};

export function ReadingListWorkspace({ refreshToken }: ReadingListWorkspaceProps) {
  const [books, setBooks] = useState<ReadingBook[]>([]);
  const [filter, setFilter] = useState<ReadingBookStatus | "all">("all");
  const [draft, setDraft] = useState<BookDraft | null>(null);
  const [progressDrafts, setProgressDrafts] = useState<Record<number, number>>({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [savingProgressIds, setSavingProgressIds] = useState<Set<number>>(new Set());
  const [notice, setNotice] = useState<Notice>(null);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    getReadingBooks(controller.signal)
      .then((response) => {
        setBooks(response.items);
        setProgressDrafts(
          Object.fromEntries(
            response.items.flatMap((book) =>
              book.progress_entries.map((entry) => [entry.id, entry.progress_percent])
            )
          )
        );
      })
      .catch((error: unknown) => {
        if (!isAbortError(error)) setNotice(errorNotice(error));
      })
      .finally(() => setLoading(false));
    return () => controller.abort();
  }, [refreshToken]);

  const visibleBooks = useMemo(
    () => books.filter((book) => filter === "all" || book.status === filter),
    [books, filter]
  );

  function beginEdit(book: ReadingBook) {
    setDraft({
      id: book.id,
      title: book.title,
      author: book.author ?? "",
      status: book.status,
      notes: book.notes ?? "",
      initialProgress: book.progress_entries.at(-1)?.progress_percent ?? 0
    });
    setNotice(null);
  }

  async function saveBook(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!draft?.title.trim()) return;
    setSaving(true);
    setNotice(null);
    try {
      const saved = draft.id
        ? await updateReadingBook(draft.id, {
            title: draft.title,
            author: draft.author || null,
            status: draft.status,
            notes: draft.notes || null
          })
        : await createReadingBook({
            title: draft.title,
            author: draft.author || null,
            status: draft.status,
            notes: draft.notes || null,
            initial_progress: draft.initialProgress
          });
      setBooks((current) =>
        draft.id
          ? current.map((book) => (book.id === saved.id ? saved : book))
          : [saved, ...current]
      );
      setProgressDrafts((current) => ({
        ...current,
        ...Object.fromEntries(
          saved.progress_entries.map((entry) => [entry.id, entry.progress_percent])
        )
      }));
      setDraft(null);
      setNotice({ tone: "success", text: draft.id ? "书籍信息已更新。" : "书籍已加入阅读书单。" });
    } catch (error) {
      setNotice(errorNotice(error));
    } finally {
      setSaving(false);
    }
  }

  async function changeStatus(book: ReadingBook, status: ReadingBookStatus) {
    setSaving(true);
    setNotice(null);
    try {
      const updated = await updateReadingBook(book.id, { status });
      setBooks((current) => current.map((item) => (item.id === updated.id ? updated : item)));
    } catch (error) {
      setNotice(errorNotice(error));
    } finally {
      setSaving(false);
    }
  }

  async function addRound(book: ReadingBook) {
    setSaving(true);
    setNotice(null);
    try {
      const entry = await createReadingProgress(book.id, 0);
      setBooks((current) =>
        current.map((item) =>
          item.id === book.id
            ? { ...item, progress_entries: [...item.progress_entries, entry] }
            : item
        )
      );
      setProgressDrafts((current) => ({ ...current, [entry.id]: 0 }));
      setNotice({ tone: "success", text: `已开始第 ${entry.round_number} 次阅读。` });
    } catch (error) {
      setNotice(errorNotice(error));
    } finally {
      setSaving(false);
    }
  }

  async function commitProgress(book: ReadingBook, entry: ReadingProgressEntry) {
    const nextValue = progressDrafts[entry.id] ?? entry.progress_percent;
    if (nextValue === entry.progress_percent || savingProgressIds.has(entry.id)) return;
    setSavingProgressIds((current) => new Set(current).add(entry.id));
    setNotice(null);
    try {
      const updated = await updateReadingProgress(entry.id, nextValue);
      setBooks((current) =>
        current.map((item) =>
          item.id === book.id
            ? {
                ...item,
                progress_entries: item.progress_entries.map((progress) =>
                  progress.id === updated.id ? updated : progress
                )
              }
            : item
        )
      );
    } catch (error) {
      setProgressDrafts((current) => ({ ...current, [entry.id]: entry.progress_percent }));
      setNotice(errorNotice(error));
    } finally {
      setSavingProgressIds((current) => {
        const next = new Set(current);
        next.delete(entry.id);
        return next;
      });
    }
  }

  async function removeRound(book: ReadingBook, entry: ReadingProgressEntry) {
    if (!window.confirm(`确认删除“${book.title}”的第 ${entry.round_number} 次阅读记录？`)) return;
    setSaving(true);
    setNotice(null);
    try {
      await deleteReadingProgress(entry.id);
      setBooks((current) =>
        current.map((item) =>
          item.id === book.id
            ? {
                ...item,
                progress_entries: item.progress_entries.filter(
                  (progress) => progress.id !== entry.id
                )
              }
            : item
        )
      );
      setNotice({ tone: "success", text: "该轮阅读记录已删除。" });
    } catch (error) {
      setNotice(errorNotice(error));
    } finally {
      setSaving(false);
    }
  }

  async function removeBook(book: ReadingBook) {
    if (!window.confirm(`确认从阅读书单删除《${book.title}》及其全部阅读进度？`)) return;
    setSaving(true);
    setNotice(null);
    try {
      await deleteReadingBook(book.id);
      setBooks((current) => current.filter((item) => item.id !== book.id));
      if (draft?.id === book.id) setDraft(null);
      setNotice({ tone: "success", text: "书籍及其阅读进度已删除。" });
    } catch (error) {
      setNotice(errorNotice(error));
    } finally {
      setSaving(false);
    }
  }

  function handleProgressKeyUp(
    event: KeyboardEvent<HTMLInputElement>,
    book: ReadingBook,
    entry: ReadingProgressEntry
  ) {
    if (["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown", "Home", "End", "PageUp", "PageDown"].includes(event.key)) {
      void commitProgress(book, entry);
    }
  }

  return (
    <div className="reading-list-workspace" role="tabpanel" aria-label="阅读书单">
      {notice ? (
        <div className={`tool-notice tool-notice--${notice.tone}`} role="status">
          <span>{notice.text}</span>
          <button type="button" title="关闭提示" onClick={() => setNotice(null)}>
            <X aria-hidden="true" size={15} />
          </button>
        </div>
      ) : null}

      <section className="tool-section reading-list-header" aria-labelledby="reading-list-heading">
        <div className="tool-section-heading">
          <div>
            <span className="tool-kicker">Personal Reading Log</span>
            <h2 id="reading-list-heading">阅读书单</h2>
          </div>
          <span className="holding-count">{books.length} 本</span>
        </div>
        <div className="reading-list-toolbar">
          <label>
            <span>阅读状态</span>
            <select
              aria-label="筛选阅读状态"
              value={filter}
              onChange={(event) => setFilter(event.target.value as ReadingBookStatus | "all")}
            >
              <option value="all">全部状态</option>
              <option value="reading">阅读中</option>
              <option value="planned">待阅读</option>
              <option value="finished">已读完</option>
            </select>
          </label>
          <button
            type="button"
            className="tool-button tool-button--primary"
            onClick={() => setDraft({ ...EMPTY_DRAFT })}
          >
            <Plus aria-hidden="true" size={16} />
            添加书籍
          </button>
        </div>
      </section>

      {draft ? (
        <form className="tool-section reading-book-form" onSubmit={saveBook}>
          <div className="tool-section-heading">
            <div>
              <span className="tool-kicker">{draft.id ? "Edit Book" : "New Book"}</span>
              <h2>{draft.id ? "编辑书籍" : "录入书籍"}</h2>
            </div>
            <button type="button" className="tool-icon-button" title="关闭表单" onClick={() => setDraft(null)}>
              <X aria-hidden="true" size={16} />
            </button>
          </div>
          <div className="reading-book-form__fields">
            <label>
              <span>书名</span>
              <input
                required
                maxLength={255}
                value={draft.title}
                onChange={(event) => setDraft({ ...draft, title: event.target.value })}
              />
            </label>
            <label>
              <span>作者（可选）</span>
              <input
                maxLength={160}
                value={draft.author}
                onChange={(event) => setDraft({ ...draft, author: event.target.value })}
              />
            </label>
            <label>
              <span>状态</span>
              <select
                value={draft.status}
                onChange={(event) => setDraft({ ...draft, status: event.target.value as ReadingBookStatus })}
              >
                <option value="reading">阅读中</option>
                <option value="planned">待阅读</option>
                <option value="finished">已读完</option>
              </select>
            </label>
            {!draft.id ? (
              <label className="reading-book-form__progress">
                <span>第一次阅读进度</span>
                <div>
                  <input
                    type="range"
                    min="0"
                    max="100"
                    step="1"
                    value={draft.initialProgress}
                    onChange={(event) => setDraft({ ...draft, initialProgress: Number(event.target.value) })}
                  />
                  <output>{draft.initialProgress}%</output>
                </div>
              </label>
            ) : null}
            <label className="reading-book-form__notes">
              <span>备注（可选）</span>
              <textarea
                maxLength={8000}
                rows={3}
                value={draft.notes}
                onChange={(event) => setDraft({ ...draft, notes: event.target.value })}
              />
            </label>
          </div>
          <div className="reading-book-form__actions">
            <button type="button" className="tool-button tool-button--quiet" onClick={() => setDraft(null)}>
              取消
            </button>
            <button type="submit" className="tool-button tool-button--primary" disabled={saving || !draft.title.trim()}>
              {saving ? <LoaderCircle className="spin" aria-hidden="true" size={16} /> : <Save aria-hidden="true" size={16} />}
              保存书籍
            </button>
          </div>
        </form>
      ) : null}

      {loading ? (
        <div className="tool-loading">
          <LoaderCircle className="spin" aria-hidden="true" size={16} />
          正在读取书单
        </div>
      ) : null}
      {!loading && books.length === 0 ? (
        <div className="tool-empty-state">
          <BookOpen aria-hidden="true" size={30} />
          <h2>书单还是空的</h2>
          <p>添加第一本书，开始记录每一轮阅读进度。</p>
        </div>
      ) : null}
      {!loading && books.length > 0 && visibleBooks.length === 0 ? (
        <p className="tool-empty">当前状态下没有书籍。</p>
      ) : null}

      <div className="reading-book-list">
        {visibleBooks.map((book) => (
          <article className="reading-book-card" key={book.id}>
            <header>
              <div>
                <h3>{book.title}</h3>
                <span>{book.author || "未填写作者"}</span>
              </div>
              <div className="reading-book-card__actions">
                <label>
                  <span className="sr-only">《{book.title}》阅读状态</span>
                  <select
                    aria-label={`《${book.title}》阅读状态`}
                    value={book.status}
                    disabled={saving}
                    onChange={(event) => void changeStatus(book, event.target.value as ReadingBookStatus)}
                  >
                    {Object.entries(STATUS_LABELS).map(([value, label]) => (
                      <option key={value} value={value}>{label}</option>
                    ))}
                  </select>
                </label>
                <button type="button" className="tool-icon-button" title={`编辑《${book.title}》`} onClick={() => beginEdit(book)}>
                  <Pencil aria-hidden="true" size={15} />
                </button>
                <button type="button" className="tool-icon-button" title={`删除《${book.title}》`} disabled={saving} onClick={() => void removeBook(book)}>
                  <Trash2 aria-hidden="true" size={15} />
                </button>
              </div>
            </header>

            {book.notes ? <p className="reading-book-notes">{book.notes}</p> : null}

            <div className="reading-progress-list">
              {book.progress_entries.map((entry) => {
                const progress = progressDrafts[entry.id] ?? entry.progress_percent;
                const isSaving = savingProgressIds.has(entry.id);
                return (
                  <div className="reading-progress-row" key={entry.id}>
                    <div className="reading-progress-row__label">
                      <strong>第 {entry.round_number} 次阅读</strong>
                      {isSaving ? <LoaderCircle className="spin" aria-label="正在保存进度" size={14} /> : null}
                    </div>
                    <input
                      type="range"
                      min="0"
                      max="100"
                      step="1"
                      aria-label={`《${book.title}》第 ${entry.round_number} 次阅读进度`}
                      value={progress}
                      disabled={isSaving}
                      onChange={(event) => setProgressDrafts((current) => ({ ...current, [entry.id]: Number(event.target.value) }))}
                      onPointerUp={() => void commitProgress(book, entry)}
                      onKeyUp={(event) => handleProgressKeyUp(event, book, entry)}
                    />
                    <output>{progress}%</output>
                    <button
                      type="button"
                      className="tool-icon-button"
                      title={`删除第 ${entry.round_number} 次阅读记录`}
                      disabled={saving || book.progress_entries.length <= 1}
                      onClick={() => void removeRound(book, entry)}
                    >
                      <Trash2 aria-hidden="true" size={14} />
                    </button>
                  </div>
                );
              })}
            </div>

            <footer>
              <span>{STATUS_LABELS[book.status]} · {book.progress_entries.length} 轮记录</span>
              <button type="button" className="tool-button tool-button--quiet" disabled={saving} onClick={() => void addRound(book)}>
                <RotateCcw aria-hidden="true" size={15} />
                新增一轮
              </button>
            </footer>
          </article>
        ))}
      </div>
    </div>
  );
}

function isAbortError(error: unknown): boolean {
  return error instanceof DOMException && error.name === "AbortError";
}

function errorNotice(error: unknown): NonNullable<Notice> {
  return {
    tone: "error",
    text: error instanceof Error ? error.message : "阅读书单操作失败。"
  };
}
