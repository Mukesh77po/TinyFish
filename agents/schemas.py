"""Agent-layer contracts (PLAN.md §3.1, §3.3). Everything downstream consumes these."""
import re
from datetime import datetime
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field, field_validator

IST = ZoneInfo("Asia/Kolkata")

Portal = Literal["gem", "cppp", "haryana"]
AgentName = Literal["gem", "cppp", "haryana", "corrigenda", "all"]


# Formats seen on the portals: GeM "24-10-2026 2:00 PM IST", NIC GePNIC (CPPP/Haryana) "30-Oct-2026 03:00 PM".
_DATE_FORMATS = [
    "%d-%m-%Y %I:%M %p",
    "%d-%m-%Y %H:%M:%S",
    "%d-%m-%Y %H:%M",
    "%d-%b-%Y %I:%M %p",
    "%d-%b-%Y %H:%M",
    "%d-%m-%Y",
    "%d-%b-%Y",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d",
]


def parse_portal_date(value: str | datetime) -> datetime:
    """Parse a portal date string into an IST-aware datetime."""
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=IST)
    s = re.sub(r"\s+", " ", value.replace("IST", "")).strip().rstrip(",")
    try:
        dt = datetime.fromisoformat(s)
        return dt if dt.tzinfo else dt.replace(tzinfo=IST)
    except ValueError:
        pass
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(s, fmt).replace(tzinfo=IST)
        except ValueError:
            continue
    raise ValueError(f"unrecognised date: {value!r}")


def parse_inr(value: str | float | int | None) -> float | None:
    """'₹ 18,50,000' -> 1850000.0, '18.5 Lakh' -> 1850000.0, '' -> None."""
    if value is None or isinstance(value, (int, float)):
        return value
    s = value.lower().replace(",", "")
    m = re.search(r"\d+(\.\d+)?", s)
    if not m:
        return None
    n = float(m.group())
    if "crore" in s or re.search(r"\bcr\b", s):
        n *= 1e7
    elif "lakh" in s or "lac" in s:
        n *= 1e5
    return n


class BidListing(BaseModel):
    portal: Portal
    bid_no: str = Field(min_length=1)
    title: str = Field(min_length=1)
    item: str | None = None
    buyer: str | None = None
    quantity: str | None = None
    est_value: float | None = None
    end_date: datetime
    doc_url: str | None = None
    source_url: str

    _parse_date = field_validator("end_date", mode="before")(parse_portal_date)
    _parse_value = field_validator("est_value", mode="before")(parse_inr)

    @field_validator("quantity", mode="before")
    @classmethod
    def _quantity_str(cls, v):
        return None if v is None else str(v)


class Corrigendum(BaseModel):
    bid_no: str
    summary: str
    new_end_date: datetime | None = None
    source_url: str

    @field_validator("new_end_date", mode="before")
    @classmethod
    def _parse_date(cls, v):
        return None if v in (None, "") else parse_portal_date(v)


class StepEvent(BaseModel):
    sweep_id: str
    agent: AgentName
    # update: a late document parse changed a match (tender_id). settled: background reading finished.
    type: Literal["started", "step", "result", "error", "done", "update", "settled"]
    step: int = 0
    message: str = ""
    count: int | None = None
    direct_url: str | None = None
    pending: int | None = None      # on all/done: documents still being read in the background
    tender_id: int | None = None    # on all/update
    ts: datetime = Field(default_factory=lambda: datetime.now(IST))


# What we ask the TinyFish agent to return (passed as output_schema).
# Kept as strings: portals format values inconsistently, BidListing does the parsing.
# TinyFish rejects "description" keys here, so field hints live in the goal text (goals.py).
AGENT_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "blocked": {"type": "boolean"},
        "blocked_reason": {"type": "string"},
        "bids": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "bid_no": {"type": "string"},
                    "title": {"type": "string"},
                    "item": {"type": "string"},
                    "buyer": {"type": "string"},
                    "quantity": {"type": "string"},
                    "est_value": {"type": "string"},
                    "end_date": {"type": "string"},
                    "doc_url": {"type": "string"},
                },
                "required": ["bid_no", "title", "end_date"],
            },
        },
    },
    "required": ["bids"],
}
