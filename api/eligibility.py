"""Eligibility parser: bid document text -> PLAN.md §3.4 JSON, every criterion with its source clause.

    python -m api.eligibility bid.pdf        # parse a local PDF or .txt
    python -m api.eligibility 12             # parse tender id 12 from the DB (uses its doc_text)
"""
import asyncio
import json
import sys
from pathlib import Path

from pydantic import BaseModel, Field

from api import llm
from api.documents import to_text

_CLAUSE = ("The shortest passage copied verbatim from the document (same words, numbers and spelling) "
           "that states this criterion, at most ~300 characters. null if the document does not mention it.")


class NumberCriterion(BaseModel):
    value: float | None
    source_clause: str | None = Field(description=_CLAUSE)


class FlagCriterion(BaseModel):
    value: bool | None
    source_clause: str | None = Field(description=_CLAUSE)


class ListCriterion(BaseModel):
    value: list[str]
    source_clause: str | None = Field(description=_CLAUSE)


class Eligibility(BaseModel):
    min_turnover: NumberCriterion = Field(
        description="Minimum average annual turnover required from the bidder, in rupees "
                    "(convert Lakh x 100000, Crore x 10000000). Bidder turnover, not OEM turnover.")
    past_experience_years: NumberCriterion = Field(
        description="Years of past experience supplying the same/similar items required from the bidder.")
    emd_amount: NumberCriterion = Field(
        description="Earnest Money Deposit (EMD / bid security) in rupees. 0 if EMD is explicitly not required.")
    emd_exemption_for_mse: FlagCriterion = Field(
        description="true if Micro and Small Enterprises (MSE / Udyam registered) are exempted from paying EMD. "
                    "GeM states this in its 'EMD EXEMPTION' paragraph (e.g. 'Under MSE category, only manufacturers "
                    "... are eligible for exemption from EMD'): that is true, quote that sentence.")
    mse_relaxation_experience_turnover: FlagCriterion = Field(
        description="The 'MSE Relaxation for Years of Experience and Turnover' value: true if Yes, false if No.")
    startup_relaxation_experience_turnover: FlagCriterion = Field(
        description="The 'Startup Relaxation for Years of Experience and Turnover' value: true if Yes, false if No.")
    required_certifications: ListCriterion = Field(
        description="Certifications/registrations the bidder must hold (e.g. 'ISO 9001', 'BIS', 'OEM authorization'). "
                    "Empty list if none.")
    documents_required: ListCriterion = Field(
        description="Documents the seller must upload with the bid, one item each "
                    "(e.g. 'Experience Criteria', 'Bidder Turnover', 'OEM Authorization Certificate'). Empty list if none.")
    states: ListCriterion = Field(
        description="Indian states the bidder must be located in or registered in, if the tender restricts this. "
                    "Empty list if there is no state restriction (a delivery/consignee location is NOT a restriction).")


SYSTEM = """You extract eligibility criteria from Indian government tender documents (GeM, CPPP, state e-procurement).
The document text is machine-extracted and may contain layout noise; bilingual labels have had their Hindi half removed.
Rules:
- Only report what the document states. Never infer or assume a criterion; use null when it is not stated.
- source_clause must be copied verbatim from the document so it can be highlighted there.
- Convert amounts to plain rupees: "40 Lakh (s)" -> 4000000, "1.5 Crore" -> 15000000.
- Criteria about the OEM (manufacturer) are not bidder criteria unless the bidder must meet them too."""


async def parse_eligibility(doc_text: str) -> dict:
    """Returns the §3.4 dict. Raises llm.LLMError when the model can't produce a valid result."""
    doc_text = doc_text[:llm.LLM_MAX_DOC_CHARS]
    el = await llm.extract(SYSTEM, f"<bid_document>\n{doc_text}\n</bid_document>", Eligibility)
    return el.model_dump()


def _load(arg: str) -> str:
    if arg.isdigit():
        from api.db import SessionLocal
        from api.models import Tender
        with SessionLocal() as db:
            t = db.get(Tender, int(arg))
            if not t or not t.doc_text:
                sys.exit(f"tender {arg} not found or has no doc_text")
            return t.doc_text
    return to_text(Path(arg).read_bytes())


if __name__ == "__main__":
    print(json.dumps(asyncio.run(parse_eligibility(_load(sys.argv[1]))), indent=2, ensure_ascii=False))
