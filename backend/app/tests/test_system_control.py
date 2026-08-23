from pathlib import Path

from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import create_app


def _configure_local_control(monkeypatch, runtime_directory: Path, token: str) -> Path:
    stop_request_file = runtime_directory / "stop-test-session.request"
    monkeypatch.setattr(settings, "local_app_control_enabled", True)
    monkeypatch.setattr(settings, "local_control_token", token)
    monkeypatch.setattr(settings, "runtime_directory", runtime_directory)
    monkeypatch.setattr(settings, "stop_request_file", stop_request_file)
    return stop_request_file


def test_local_shutdown_is_hidden_when_control_is_disabled() -> None:
    client = TestClient(
        create_app(initialize_database=False),
        client=("127.0.0.1", 51000),
    )

    response = client.post("/api/system/shutdown")

    assert response.status_code == 404


def test_local_shutdown_requires_loopback_and_matching_token(monkeypatch, tmp_path: Path) -> None:
    token = "t" * 32
    stop_request_file = _configure_local_control(monkeypatch, tmp_path, token)
    app = create_app(initialize_database=False)

    local_client = TestClient(app, client=("127.0.0.1", 51000))
    invalid_token_response = local_client.post(
        "/api/system/shutdown",
        headers={"X-Local-Control-Token": "wrong"},
    )
    assert invalid_token_response.status_code == 403

    remote_client = TestClient(app, client=("192.0.2.10", 51000))
    remote_response = remote_client.post(
        "/api/system/shutdown",
        headers={"X-Local-Control-Token": token},
    )
    assert remote_response.status_code == 403
    assert not stop_request_file.exists()


def test_local_shutdown_writes_controller_request(monkeypatch, tmp_path: Path) -> None:
    token = "s" * 32
    stop_request_file = _configure_local_control(monkeypatch, tmp_path, token)
    client = TestClient(
        create_app(initialize_database=False),
        client=("127.0.0.1", 51000),
    )

    health_response = client.get("/api/health")
    response = client.post(
        "/api/system/shutdown",
        headers={
            "Origin": "http://127.0.0.1:5173",
            "X-Local-Control-Token": token,
        },
    )

    assert health_response.json()["local_control_enabled"] is True
    assert response.status_code == 202
    assert response.json()["status"] == "accepted"
    assert stop_request_file.exists()
    assert '"status": "requested"' in stop_request_file.read_text(encoding="utf-8")
