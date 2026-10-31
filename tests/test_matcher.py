from datetime import datetime, timedelta

from agents.schemas import IST
from api.documents import excerpt, locate_clause
from api.matcher import (CHECK_DOCS, ELIGIBLE, NOT_ELIGIBLE, ProfileFacts, evaluate, inr, keyword_fit,
                         same_state)

NOW = datetime(2026, 10, 24, 12, 0, tzinfo=IST)
OPEN = NOW + timedelta(days=4)
RAMESH = ProfileFacts(annual_turnover=12_000_000, years_in_business=8,
                      certifications=["Udyam", "MSE", "GeM Seller"],
                      states_served=["Haryana", "Delhi", "Uttar Pradesh", "Rajasthan"])


def el(**kw) -> dict:
    base = {k: {"value": None, "source_clause": None} for k in (
        "min_turnover", "past_experience_years", "emd_amount", "emd_exemption_for_mse",
        "mse_relaxation_experience_turnover", "startup_relaxation_experience_turnover")}
    base.update({k: {"value": [], "source_clause": None}
                 for k in ("required_certifications", "documents_required", "states")})
    for k, v in kw.items():
        base[k] = {"value": v, "source_clause": f"clause for {k}"}
    return base


def texts(r):
    return [x["text"] for x in r.reasons]


def test_demo_example_turnover_met_emd_exempt_needs_experience_proof():
    r = evaluate(RAMESH, OPEN, el(min_turnover=5_000_000, past_experience_years=3, emd_amount=37_000,
                                  emd_exemption_for_mse=True, mse_relaxation_experience_turnover=False), NOW)
    assert r.verdict == CHECK_DOCS
    assert "Turnover met (₹1.2 Cr ≥ ₹50 L)" in texts(r)
    assert "MSE EMD exemption applies (saves ₹37,000)" in texts(r)
    assert "Needs 3 years past-supply proof" in texts(r)
    assert all(x["source_clause"] for x in r.reasons)
    assert "Past supply orders / completion certificates (3 years)" in r.missing_docs


def test_eligible_when_everything_met():
    r = evaluate(RAMESH, OPEN, el(min_turnover=4_000_000, emd_amount=0), NOW)
    assert r.verdict == ELIGIBLE


def test_turnover_short_is_not_eligible():
    r = evaluate(RAMESH, OPEN, el(min_turnover=50_000_000), NOW)
    assert r.verdict == NOT_ELIGIBLE
    assert "Turnover short (₹1.2 Cr < ₹5 Cr)" in texts(r)


def test_mse_relaxation_waives_turnover_and_experience():
    r = evaluate(RAMESH, OPEN, el(min_turnover=50_000_000, past_experience_years=10,
                                  mse_relaxation_experience_turnover=True), NOW)
    assert r.verdict == ELIGIBLE
    assert "Turnover criterion (₹5 Cr) relaxed for MSEs" in texts(r)


def test_relaxation_does_not_apply_to_non_mse():
    big = ProfileFacts(10_000_000, 2, ["ISO 9001"], ["Delhi"])
    r = evaluate(big, OPEN, el(min_turnover=50_000_000, mse_relaxation_experience_turnover=True), NOW)
    assert r.verdict == NOT_ELIGIBLE


def test_experience_is_check_docs_even_when_years_in_business_is_lower():
    # PLAN §3.6: past experience needs proof -> CHECK_DOCS, never a hard fail
    young = ProfileFacts(12_000_000, 1, ["Udyam"], ["Haryana"])
    r = evaluate(young, OPEN, el(past_experience_years=3), NOW)
    assert r.verdict == CHECK_DOCS
    assert "Needs 3 years past-supply proof (profile shows only 1 in business)" in texts(r)


def test_parse_with_no_criteria_is_check_docs_not_eligible():
    # e.g. Fetch returned a landing page and the LLM found nothing: must not show green
    r = evaluate(RAMESH, OPEN, el(), NOW)
    assert r.verdict == CHECK_DOCS
    assert r.reasons[0]["criterion"] == "document"


def test_state_names_match_loosely():
    assert same_state("Haryana", "State of Haryana")
    assert same_state("Uttar Pradesh", "UP")
    assert same_state("Delhi", "NCT of Delhi")
    assert same_state("Jammu and Kashmir", "J&K") and same_state("Jammu & Kashmir", "Jammu and Kashmir")
    assert not same_state("Punjab", "Haryana")
    assert evaluate(RAMESH, OPEN, el(states=["State of Haryana"]), NOW).verdict == ELIGIBLE


def test_state_restriction():
    assert evaluate(RAMESH, OPEN, el(states=["Punjab"]), NOW).verdict == NOT_ELIGIBLE
    assert evaluate(RAMESH, OPEN, el(states=["haryana"]), NOW).verdict == ELIGIBLE


def test_missing_certification_needs_docs():
    r = evaluate(RAMESH, OPEN, el(required_certifications=["ISO 9001", "Udyam"]), NOW)
    assert r.verdict == CHECK_DOCS
    assert "Needs ISO 9001 (not on your profile)" in texts(r)
    assert "Has Udyam" in texts(r)
    assert "ISO 9001" in r.missing_docs


def test_deadline_passed():
    r = evaluate(RAMESH, NOW - timedelta(hours=1), el(), NOW)
    assert r.verdict == NOT_ELIGIBLE and r.reasons[0]["criterion"] == "deadline"


def test_no_parse_is_check_docs():
    assert evaluate(RAMESH, OPEN, None, NOW).verdict == CHECK_DOCS


def test_unreadable_value_with_clause_is_check_docs():
    e = el()
    e["min_turnover"] = {"value": None, "source_clause": "Turnover as per ATC"}
    assert evaluate(RAMESH, OPEN, e, NOW).verdict == CHECK_DOCS


def test_bid_document_checklist_is_merged_without_duplicates():
    r = evaluate(RAMESH, OPEN, el(min_turnover=1, past_experience_years=3, documents_required=[
        "Experience Criteria", "Past Performance", "Bidder Turnover", "OEM Authorization"]), NOW)
    assert r.missing_docs == ["Turnover proof (audited statements / CA certificate)",
                              "Past supply orders / completion certificates (3 years)", "OEM Authorization"]


def test_inr_format():
    assert (inr(4_000_000), inr(12_000_000), inr(37_000), inr(18_50_000)) == ("₹40 L", "₹1.2 Cr", "₹37,000", "₹18.5 L")


def test_keyword_fit():
    phrases = ["steel rack", "steel almirah"]
    assert keyword_fit(phrases, "Supply of Steel Storage Racks", None) == 1.0
    assert keyword_fit(phrases, "TORPEDO LADLES REFRACTORY SETS...", None) == 0.0


def test_locate_clause_ignores_whitespace_and_case():
    doc = "Bid Details\nMinimum Average Annual Turnover of\nthe bidder (For 3 Years)\n40 Lakh (s)\nmore"
    a, b = locate_clause(doc, "minimum average annual turnover of the bidder (For 3 Years) 40 Lakh (s)")
    assert doc[a:b].startswith("Minimum") and doc[a:b].endswith("40 Lakh (s)")
    ex = excerpt(doc, "40 Lakh (s)", context=5)
    assert ex["text"][ex["highlight_start"]:ex["highlight_end"]] == "40 Lakh (s)"
    assert locate_clause(doc, "not in the document at all") is None
