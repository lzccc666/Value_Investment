from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from app.db.init_db import init_db
from app.db.models import ReadingBook, ReadingProgressEntry
from app.db.session import create_sqlalchemy_engine, get_db
from app.main import create_app


def _make_environment(tmp_path: Path):
    engine = create_sqlalchemy_engine(
        f"sqlite:///{(tmp_path / 'reading-list.db').as_posix()}"
    )
    init_db(engine)
    factory = sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
    )
    app = create_app(initialize_database=False)

    def override_get_db():
        with factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    return factory, TestClient(app)


def test_reading_book_crud_tracks_multiple_rounds_and_progress(tmp_path: Path) -> None:
    factory, client = _make_environment(tmp_path)

    created = client.post(
        "/api/investment-tools/reading-books",
        json={
            "title": "  聪明的投资者  ",
            "author": "本杰明·格雷厄姆",
            "status": "reading",
            "notes": "重读安全边际章节",
            "initial_progress": 100,
        },
    )
    assert created.status_code == 201, created.text
    book = created.json()
    assert book["title"] == "聪明的投资者"
    assert book["status"] == "reading"
    first_rounds = [
        (item["round_number"], item["progress_percent"])
        for item in book["progress_entries"]
    ]
    assert first_rounds == [(1, 100)]

    second = client.post(
        f"/api/investment-tools/reading-books/{book['id']}/progress",
        json={"progress_percent": 30},
    )
    assert second.status_code == 201, second.text
    assert second.json()["round_number"] == 2
    assert second.json()["progress_percent"] == 30

    updated_progress = client.patch(
        f"/api/investment-tools/reading-progress/{second.json()['id']}",
        json={"progress_percent": 47},
    )
    assert updated_progress.status_code == 200, updated_progress.text
    assert updated_progress.json()["progress_percent"] == 47

    updated_book = client.patch(
        f"/api/investment-tools/reading-books/{book['id']}",
        json={"status": "finished", "notes": "两轮阅读完成"},
    )
    assert updated_book.status_code == 200, updated_book.text
    assert updated_book.json()["status"] == "finished"
    assert updated_book.json()["notes"] == "两轮阅读完成"

    listed = client.get("/api/investment-tools/reading-books")
    assert listed.status_code == 200, listed.text
    assert listed.json()["total"] == 1
    assert [item["progress_percent"] for item in listed.json()["items"][0]["progress_entries"]] == [
        100,
        47,
    ]

    deleted_round = client.delete(
        f"/api/investment-tools/reading-progress/{second.json()['id']}"
    )
    assert deleted_round.status_code == 200, deleted_round.text
    first_progress_id = book["progress_entries"][0]["id"]
    assert client.delete(
        f"/api/investment-tools/reading-progress/{first_progress_id}"
    ).status_code == 409

    deleted_book = client.delete(f"/api/investment-tools/reading-books/{book['id']}")
    assert deleted_book.status_code == 200, deleted_book.text
    with factory() as session:
        assert session.get(ReadingBook, book["id"]) is None
        assert session.scalar(select(func.count()).select_from(ReadingProgressEntry)) == 0


def test_reading_list_rejects_invalid_input_and_missing_records(tmp_path: Path) -> None:
    _, client = _make_environment(tmp_path)

    assert client.post(
        "/api/investment-tools/reading-books",
        json={"title": "   ", "status": "planned"},
    ).status_code == 422
    assert client.post(
        "/api/investment-tools/reading-books",
        json={"title": "测试", "status": "unknown"},
    ).status_code == 422
    assert client.post(
        "/api/investment-tools/reading-books/999/progress",
        json={"progress_percent": 0},
    ).status_code == 404
    assert client.patch(
        "/api/investment-tools/reading-progress/999",
        json={"progress_percent": 101},
    ).status_code == 422
    assert client.get("/api/investment-tools/reading-books/999").status_code == 404
