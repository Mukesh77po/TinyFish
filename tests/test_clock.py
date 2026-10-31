"""DEMO_NOW / frozen demo clock (api/clock.py): fixture deadlines never expire in FALLBACK_MODE."""
import json
from datetime import datetime, timedelta

import pytest

from agents.schemas import IST
from api import clock
from api.matcher import NOT_ELIGIBLE, ProfileFacts, evaluate

ELIG = {k: {"value": None, "source_clause": None} for k in
        ("min_turnover", "past_experience_years", "emd_amount", "emd_exemption_for_mse")}
RAMESH = ProfileFacts(annual_turnover=12_000_000, years_in_business=8, certifications=["MSE", "Udyam"],
                      states_served=["Haryana"])


@pytest.fixture
def fixtures_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(clock, "FIXTURES_DIR", tmp_path)
    (tmp_path / "gem_storage_rack.json").write_text(json.dumps({"recorded_at": "2026-10-20T10:00:00+05:30"}))
    (tmp_path / "cppp_storage_rack.json").write_text(json.dumps({"recorded_at": "2026-10-21T09:30:00+05:30"}))
    (tmp_path / "broken.json").write_text("{not json")
    return tmp_path


def test_live_mode_uses_the_real_clock(monkeypatch, fixtures_dir):
    monkeypatch.setenv("FALLBACK_MODE", "false")
    monkeypatch.setenv("DEMO_NOW", "2020-01-01T00:00:00")
    assert clock.demo_now() == (None, "real")
    assert abs(clock.now_ist() - datetime.now(IST)) < timedelta(seconds=5)


def test_demo_now_wins_in_fallback_and_naive_means_ist(monkeypatch, fixtures_dir):
    monkeypatch.setenv("FALLBACK_MODE", "true")
    monkeypatch.setenv("DEMO_NOW", "2026-10-25T11:00:00")
    assert clock.now_ist() == datetime(2026, 10, 25, 11, 0, tzinfo=IST)
    assert clock.demo_now()[1] == "DEMO_NOW"
    monkeypatch.setenv("DEMO_NOW", "2026-10-25T05:30:00+00:00")
    assert clock.now_ist() == datetime(2026, 10, 25, 11, 0, tzinfo=IST)


def test_fallback_without_demo_now_freezes_at_newest_recording(monkeypatch, fixtures_dir):
    monkeypatch.setenv("FALLBACK_MODE", "true")
    monkeypatch.delenv("DEMO_NOW", raising=False)
    assert clock.demo_now() == (datetime(2026, 10, 21, 9, 30, tzinfo=IST), "fixture recorded_at")


def test_bad_demo_now_is_ignored_not_fatal(monkeypatch, fixtures_dir):
    monkeypatch.setenv("FALLBACK_MODE", "true")
    monkeypatch.setenv("DEMO_NOW", "next tuesday")
    assert clock.demo_now()[1] == "fixture recorded_at"


def _verdict_in_fallback(monkeypatch, demo_now: str, end: datetime):
    monkeypatch.setenv("FALLBACK_MODE", "true")
    monkeypatch.setenv("DEMO_NOW", demo_now)
    return evaluate(RAMESH, end, ELIG)


def test_deadline_in_3_days_stays_open_on_the_demo_clock(monkeypatch, fixtures_dir):
    """A bid that closed in real life (fixture recorded weeks ago) is still open on the demo clock."""
    end = datetime(2026, 10, 28, 15, 0, tzinfo=IST)
    r = _verdict_in_fallback(monkeypatch, "2026-10-25T15:00:00", end)
    assert r.verdict != NOT_ELIGIBLE
    assert not any("passed" in x["text"].lower() or "closed" in x["text"].lower() for x in r.reasons)


def test_deadline_passed_on_the_demo_clock(monkeypatch, fixtures_dir):
    end = datetime(2026, 10, 24, 15, 0, tzinfo=IST)
    r = _verdict_in_fallback(monkeypatch, "2026-10-25T15:00:00", end)
    assert r.verdict == NOT_ELIGIBLE
