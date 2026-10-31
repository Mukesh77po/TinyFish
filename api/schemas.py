"""API request/response models (PLAN.md §3.5)."""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ProfileIn(BaseModel):
    name: str = Field(min_length=1)
    phone: str | None = None
    email: str | None = None
    products: list[str] = []
    keywords: list[str] = []
    hsn_codes: list[str] = []
    annual_turnover: int | None = Field(default=None, ge=0, description="INR")
    years_in_business: int | None = Field(default=None, ge=0)
    certifications: list[str] = []
    states_served: list[str] = []


class ProfileOut(ProfileIn):
    model_config = ConfigDict(from_attributes=True)
    id: int


class Created(BaseModel):
    id: int


class SweepIn(BaseModel):
    profile_id: int


class SweepOut(BaseModel):
    sweep_id: str


class TenderSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    portal: str
    bid_no: str
    title: str
    item: str | None
    buyer: str | None
    quantity: str | None
    est_value: float | None
    end_date: datetime
    source_url: str
    doc_url: str | None


class Reason(BaseModel):
    kind: str            # ok | info | warn | fail
    criterion: str
    text: str
    source_clause: str | None
    source_url: str | None = None  # corrigenda: link to the notice
    excerpt: dict | None = None   # detail only: {text, highlight_start, highlight_end, ...}


class MatchSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    profile_id: int
    verdict: str
    fit_score: float | None
    relevant: bool
    reasons: list[Reason]
    missing_docs: list[str]
    alerted_at: datetime | None
    tender: TenderSummary


class Provenance(BaseModel):
    """Where each part of a verdict came from, shown on the match page."""
    found_by: str                 # "TinyFish agent on GeM" / "recorded TinyFish run (GeM)"
    portal: str
    doc_source: str | None        # fetch | direct | fixture; None = no document text
    eligibility_by: str | None    # "LLM (openai/gpt-oss-120b)" / "recorded parse"; None = not parsed
    verdict_by: str = "rules (api/matcher.py)"


class MatchDetail(MatchSummary):
    eligibility: dict | None
    corrigenda: list
    provenance: Provenance


class MatchRunOut(BaseModel):
    counts: dict[str, int]
    relevant: int = 0
    total: int = 0
    method: str = "keywords"
