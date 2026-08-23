from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.db.models import ReadingBook, ReadingProgressEntry, utc_now
from app.schemas.investment_tools import (
    ReadingBookCreate,
    ReadingBookUpdate,
    ReadingProgressCreate,
    ReadingProgressUpdate,
)


class ReadingListError(RuntimeError):
    pass


class ReadingListNotFoundError(ReadingListError):
    pass


class ReadingListConflictError(ReadingListError):
    pass


def list_reading_books(session: Session) -> list[ReadingBook]:
    return list(
        session.scalars(
            select(ReadingBook)
            .options(selectinload(ReadingBook.progress_entries))
            .order_by(ReadingBook.updated_at.desc(), ReadingBook.id.desc())
        )
    )


def get_reading_book(session: Session, book_id: int) -> ReadingBook:
    book = session.scalar(
        select(ReadingBook)
        .options(selectinload(ReadingBook.progress_entries))
        .where(ReadingBook.id == book_id)
    )
    if book is None:
        raise ReadingListNotFoundError("书籍不存在。")
    return book


def create_reading_book(session: Session, payload: ReadingBookCreate) -> ReadingBook:
    values = payload.model_dump(exclude={"initial_progress"})
    book = ReadingBook(**values)
    book.progress_entries.append(
        ReadingProgressEntry(round_number=1, progress_percent=payload.initial_progress)
    )
    session.add(book)
    session.commit()
    return get_reading_book(session, book.id)


def update_reading_book(
    session: Session,
    book_id: int,
    payload: ReadingBookUpdate,
) -> ReadingBook:
    book = get_reading_book(session, book_id)
    for field_name, value in payload.model_dump(exclude_unset=True).items():
        setattr(book, field_name, value)
    session.commit()
    return get_reading_book(session, book.id)


def delete_reading_book(session: Session, book_id: int) -> None:
    book = get_reading_book(session, book_id)
    session.delete(book)
    session.commit()


def create_reading_progress(
    session: Session,
    book_id: int,
    payload: ReadingProgressCreate,
) -> ReadingProgressEntry:
    book = get_reading_book(session, book_id)
    latest_round = session.scalar(
        select(func.max(ReadingProgressEntry.round_number)).where(
            ReadingProgressEntry.book_id == book_id
        )
    )
    entry = ReadingProgressEntry(
        book_id=book_id,
        round_number=int(latest_round or 0) + 1,
        progress_percent=payload.progress_percent,
    )
    session.add(entry)
    book.updated_at = utc_now()
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise ReadingListConflictError("新增阅读轮次发生冲突，请刷新后重试。") from exc
    session.refresh(entry)
    return entry


def update_reading_progress(
    session: Session,
    progress_id: int,
    payload: ReadingProgressUpdate,
) -> ReadingProgressEntry:
    entry = _get_progress(session, progress_id)
    entry.progress_percent = payload.progress_percent
    entry.book.updated_at = utc_now()
    session.commit()
    session.refresh(entry)
    return entry


def delete_reading_progress(session: Session, progress_id: int) -> None:
    entry = _get_progress(session, progress_id)
    count = session.scalar(
        select(func.count()).select_from(ReadingProgressEntry).where(
            ReadingProgressEntry.book_id == entry.book_id
        )
    )
    if int(count or 0) <= 1:
        raise ReadingListConflictError("每本书至少保留一轮阅读进度。")
    book = entry.book
    session.delete(entry)
    book.updated_at = utc_now()
    session.commit()


def _get_progress(session: Session, progress_id: int) -> ReadingProgressEntry:
    entry = session.scalar(
        select(ReadingProgressEntry)
        .options(selectinload(ReadingProgressEntry.book))
        .where(ReadingProgressEntry.id == progress_id)
    )
    if entry is None:
        raise ReadingListNotFoundError("阅读进度不存在。")
    return entry
