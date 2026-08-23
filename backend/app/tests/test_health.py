from fastapi.testclient import TestClient

from app.main import create_app


def test_health_check_returns_service_status() -> None:
    client = TestClient(create_app(initialize_database=False))

    response = client.get("/api/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["service"] == "Value Investment API"
    assert payload["version"] == "0.1.0"
    assert payload["environment"] == "development"
    assert payload["local_control_enabled"] is False
    assert "checked_at" in payload
