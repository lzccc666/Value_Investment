from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app.db.init_db import init_db
from app.db.session import create_sqlalchemy_engine, get_db
from app.main import create_app


def _make_test_db(tmp_path: Path):
    database_url = f"sqlite:///{(tmp_path / 'companies.db').as_posix()}"
    engine = create_sqlalchemy_engine(database_url)
    init_db(engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def test_company_list_returns_seed_companies(tmp_path: Path) -> None:
    session_factory = _make_test_db(tmp_path)
    app = create_app(initialize_database=False)

    def override_get_db():
        with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as client:
        response = client.get("/api/companies")

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 3
    assert payload["limit"] == 20
    assert payload["offset"] == 0
    assert {item["ticker"] for item in payload["items"]} == {"VI0001", "VI0002", "VI0003"}


def test_company_list_filters_by_query(tmp_path: Path) -> None:
    session_factory = _make_test_db(tmp_path)
    app = create_app(initialize_database=False)

    def override_get_db():
        with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as client:
        response = client.get("/api/companies", params={"q": "平台"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["items"][0]["ticker"] == "VI0003"


def test_company_detail_returns_seed_company(tmp_path: Path) -> None:
    session_factory = _make_test_db(tmp_path)
    app = create_app(initialize_database=False)

    def override_get_db():
        with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as client:
        response = client.get("/api/companies/1")

    assert response.status_code == 200
    payload = response.json()
    assert payload["ticker"] == "VI0001"
    assert payload["name"] == "护城河消费样本"
