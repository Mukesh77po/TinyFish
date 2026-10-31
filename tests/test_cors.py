"""The API answers CORS preflights for the dashboard origin (WEB_ORIGINS), not for arbitrary sites."""
from fastapi.testclient import TestClient

from api.main import app

client = TestClient(app)


def _preflight(origin: str):
    return client.options("/profiles", headers={"Origin": origin, "Access-Control-Request-Method": "POST",
                                                "Access-Control-Request-Headers": "content-type"})


def test_dashboard_origin_allowed():
    for origin in ("http://localhost:3000", "http://127.0.0.1:3000"):
        assert _preflight(origin).headers.get("access-control-allow-origin") == origin


def test_other_origins_refused():
    assert "access-control-allow-origin" not in _preflight("https://evil.example.com").headers


def test_database_down_is_a_plain_503_not_a_stack_trace(monkeypatch):
    from sqlalchemy.exc import OperationalError
    from api import main

    def broken_db():
        raise OperationalError("SELECT 1", {}, Exception("connection refused\nTraceback ..."))
        yield
    app.dependency_overrides[main.get_db] = broken_db
    try:
        r = TestClient(app, raise_server_exceptions=False).get("/matches/1")
    finally:
        app.dependency_overrides.clear()
    assert r.status_code == 503
    assert r.json()["detail"].startswith("The database is not reachable") and "Traceback" not in r.text
