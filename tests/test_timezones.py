"""Deadlines are IST-correct whatever the server's TZ is (a container usually runs in UTC)."""
import os
import time
from datetime import datetime, timedelta, timezone

import pytest

from agents.schemas import IST, BidListing, parse_portal_date
from api.clock import as_ist
from api.matcher import NOT_ELIGIBLE, ProfileFacts, evaluate
from delivery.alerts import _closes

ELIG = {"min_turnover": {"value": 100000, "source_clause": "Minimum Average Annual Turnover 1 Lakh"}}
RAMESH = ProfileFacts(annual_turnover=12_000_000, years_in_business=8, certifications=["Udyam"],
                      states_served=["Haryana"])


@pytest.fixture(params=["UTC", "America/Los_Angeles", "Asia/Kolkata"])
def server_tz(request):
    old = os.environ.get("TZ")
    os.environ["TZ"] = request.param
    time.tzset()
    yield request.param
    if old is None:
        os.environ.pop("TZ", None)
    else:
        os.environ["TZ"] = old
    time.tzset()


def _deadline_failed(end, now) -> bool:
    r = evaluate(RAMESH, end, ELIG, now=now)
    return any(x["criterion"] == "deadline" for x in r.reasons) and r.verdict == NOT_ELIGIBLE


def test_gem_date_string_parses_to_ist(server_tz):
    dt = parse_portal_date("24-10-2026 2:00 PM IST")
    assert dt == datetime(2026, 10, 24, 14, 0, tzinfo=IST)
    assert dt.astimezone(timezone.utc) == datetime(2026, 10, 24, 8, 30, tzinfo=timezone.utc)
    bid = BidListing(portal="gem", bid_no="GEM/2026/B/1", title="Steel rack", end_date="24-10-2026 2:00 PM IST",
                     source_url="https://bidplus.gem.gov.in/all-bids")
    assert bid.end_date.utcoffset() == timedelta(hours=5, minutes=30)


def test_bid_closing_1500_ist_open_at_1459_closed_at_1501(server_tz):
    end = parse_portal_date("24-10-2026 3:00 PM")
    assert not _deadline_failed(end, datetime(2026, 10, 24, 14, 59, tzinfo=IST))
    assert _deadline_failed(end, datetime(2026, 10, 24, 15, 1, tzinfo=IST))


def test_db_utc_value_compares_like_ist(server_tz):
    """Postgres timestamptz comes back in UTC; 09:30 UTC is 15:00 IST."""
    end = datetime(2026, 10, 24, 9, 30, tzinfo=timezone.utc)
    assert not _deadline_failed(end, datetime(2026, 10, 24, 14, 59, tzinfo=IST))
    assert _deadline_failed(end, datetime(2026, 10, 24, 9, 31, tzinfo=timezone.utc))


def test_naive_datetimes_mean_ist_not_server_local(server_tz):
    end = datetime(2026, 10, 24, 15, 0)  # naive: must be read as 15:00 IST in every server TZ
    assert as_ist(end) == datetime(2026, 10, 24, 15, 0, tzinfo=IST)
    assert not _deadline_failed(end, datetime(2026, 10, 24, 14, 59))
    assert _deadline_failed(end, datetime(2026, 10, 24, 15, 1, tzinfo=IST))
    assert _closes(end) == "24 Oct, 03:00 PM"
    assert _closes(datetime(2026, 10, 24, 9, 30, tzinfo=timezone.utc)) == "24 Oct, 03:00 PM"
