import pytest

pytest.importorskip("httpx")


def test_demo_page_is_served():
    from fastapi.testclient import TestClient
    from api.main import app
    r = TestClient(app).get("/demo")  # no `with`: skip lifespan, so no scheduler starts
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/html")
    assert "TenderHawk" in r.text and "EventSource" in r.text
