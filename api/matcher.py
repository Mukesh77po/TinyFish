"""Verdict rules (PLAN.md §3.6). Pure functions: no DB, no network, easy to test.

NOT_ELIGIBLE  deadline passed | turnover short | limited to states not served
CHECK_DOCS    needs proof we can't verify (past supply, certifications) | unreadable criterion | no parse
              | a parse that found no criteria at all (e.g. the fetch returned a landing page, not the bid)
ELIGIBLE      otherwise
Every reason carries the source clause it came from.
"""
import re
from dataclasses import dataclass, field
from datetime import datetime

from api.clock import as_ist, now_ist

ELIGIBLE, CHECK_DOCS, NOT_ELIGIBLE = "ELIGIBLE", "CHECK_DOCS", "NOT_ELIGIBLE"
VERDICT_RANK = {ELIGIBLE: 0, CHECK_DOCS: 1, NOT_ELIGIBLE: 2}
OK, INFO, WARN, FAIL = "ok", "info", "warn", "fail"


@dataclass
class ProfileFacts:
    annual_turnover: int | None
    years_in_business: int | None
    certifications: list[str]
    states_served: list[str]


@dataclass
class Result:
    verdict: str
    reasons: list[dict] = field(default_factory=list)
    missing_docs: list[str] = field(default_factory=list)


def inr(v: float) -> str:
    """4000000 -> '₹40 L', 12000000 -> '₹1.2 Cr', 37000 -> '₹37,000'."""
    if v >= 1e7:
        return f"₹{v / 1e7:.2f}".rstrip("0").rstrip(".") + " Cr"
    if v >= 1e5:
        return f"₹{v / 1e5:.2f}".rstrip("0").rstrip(".") + " L"
    return f"₹{v:,.0f}"


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


def has_cert(profile_certs: list[str], required: str) -> bool:
    r = _norm(required)
    return any(r in _norm(c) or _norm(c) in r for c in profile_certs if _norm(c))


def is_mse(p: ProfileFacts) -> bool:
    return any(re.search(r"\b(udyam|mse|msme|micro|small enterprise)\b", c, re.I) for c in p.certifications)


def is_startup(p: ProfileFacts) -> bool:
    return any(re.search(r"\b(startup|start-up|dpiit)\b", c, re.I) for c in p.certifications)


def _crit(el: dict, key: str) -> tuple:
    c = el.get(key) or {}
    return c.get("value"), c.get("source_clause")


def evaluate(p: ProfileFacts, end_date: datetime, eligibility: dict | None, now: datetime | None = None,
             corrigenda: list[dict] | None = None) -> Result:
    now = as_ist(now or now_ist())
    end_date = as_ist(end_date)
    reasons: list[dict] = []
    docs: list[str] = []

    def add(kind: str, criterion: str, text: str, clause: str | None = None, url: str | None = None) -> None:
        reasons.append({"kind": kind, "criterion": criterion, "text": text, "source_clause": clause,
                        "source_url": url})

    if end_date < now:
        add(FAIL, "deadline", f"Deadline passed (closed {end_date:%d %b, %I:%M %p})")

    for c in corrigenda or []:
        ext = c.get("extends_to")
        text = (f"Deadline extended to {as_ist(datetime.fromisoformat(ext)):%d %b}" if ext
                else "Corrigendum posted")
        add(INFO, "corrigendum", text, c.get("summary"), c.get("source_url"))

    if not eligibility:
        add(WARN, "document", "Couldn't read eligibility from the bid document. Check the document yourself.")
        return _finish(reasons, docs)
    if not any((c or {}).get("source_clause") for c in eligibility.values() if isinstance(c, dict)):
        add(WARN, "document", "No eligibility clauses found in the document. Check the document yourself.")
        return _finish(reasons, docs)

    mse, startup = is_mse(p), is_startup(p)
    mse_relax, mse_relax_clause = _crit(eligibility, "mse_relaxation_experience_turnover")
    st_relax, st_relax_clause = _crit(eligibility, "startup_relaxation_experience_turnover")
    relaxed = (mse and mse_relax is True) or (startup and st_relax is True)
    relax_clause = mse_relax_clause if (mse and mse_relax) else st_relax_clause
    relax_who = "MSEs" if (mse and mse_relax) else "startups"

    # Turnover
    need, clause = _crit(eligibility, "min_turnover")
    if need is None and clause:
        add(WARN, "turnover", "Couldn't read the turnover requirement. See the clause.", clause)
    elif need:
        if relaxed:
            add(OK, "turnover", f"Turnover criterion ({inr(need)}) relaxed for {relax_who}", relax_clause or clause)
        elif p.annual_turnover is None:
            add(WARN, "turnover", f"Needs {inr(need)} turnover. Add yours to the profile.", clause)
        elif p.annual_turnover >= need:
            add(OK, "turnover", f"Turnover met ({inr(p.annual_turnover)} ≥ {inr(need)})", clause)
        else:
            add(FAIL, "turnover", f"Turnover short ({inr(p.annual_turnover)} < {inr(need)})", clause)
        if not relaxed:
            docs.append("Turnover proof (audited statements / CA certificate)")

    # Past experience: always needs proof, so at best CHECK_DOCS
    years, clause = _crit(eligibility, "past_experience_years")
    if years is None and clause:
        add(WARN, "experience", "Couldn't read the experience requirement. See the clause.", clause)
    elif years:
        y = f"{years:g} year{'s' if years != 1 else ''}"
        if relaxed:
            add(OK, "experience", f"Experience criterion ({y}) relaxed for {relax_who}", relax_clause or clause)
        else:
            # Years in business is not years of past supply, so this is never a hard fail (§3.6).
            note = (f" (profile shows only {p.years_in_business} in business)"
                    if p.years_in_business is not None and p.years_in_business < years else "")
            add(WARN, "experience", f"Needs {y} past-supply proof{note}", clause)
            docs.append(f"Past supply orders / completion certificates ({y})")

    # EMD
    emd, clause = _crit(eligibility, "emd_amount")
    exempt, exempt_clause = _crit(eligibility, "emd_exemption_for_mse")
    if emd:
        if mse and exempt:
            add(OK, "emd", f"MSE EMD exemption applies (saves {inr(emd)})", exempt_clause or clause)
            docs.append("Udyam certificate (for EMD exemption)")
        else:
            add(INFO, "emd", f"EMD of {inr(emd)} required", clause)
            docs.append(f"EMD {inr(emd)} (bank guarantee or online payment)")
    elif emd == 0:
        add(OK, "emd", "No EMD required", clause)

    # Certifications
    certs, clause = _crit(eligibility, "required_certifications")
    for c in certs or []:
        if has_cert(p.certifications, c):
            add(OK, "certification", f"Has {c}", clause)
        else:
            add(WARN, "certification", f"Needs {c} (not on your profile)", clause)
            docs.append(c)

    # State restriction
    states, clause = _crit(eligibility, "states")
    if states:
        if not p.states_served:
            add(WARN, "states", f"Limited to {', '.join(states)}. Add the states you serve.", clause)
        elif not any(same_state(s, t) for s in p.states_served for t in states):
            add(FAIL, "states", f"Limited to bidders from {', '.join(states)}", clause)
        else:
            add(OK, "states", f"State requirement met ({', '.join(states)})", clause)

    # Document checklist from the bid itself, minus items our own checklist already covers
    required_docs, _ = _crit(eligibility, "documents_required")
    covered = {g for x in docs for g in _doc_groups(x)}
    for d in required_docs or []:
        groups = _doc_groups(d)
        if groups and groups <= covered:
            continue
        if not any(_norm(d) in _norm(x) or _norm(x) in _norm(d) for x in docs):
            docs.append(d)

    return _finish(reasons, docs)


_STATE_ALIASES = {
    "up": "uttar pradesh", "mp": "madhya pradesh", "hp": "himachal pradesh", "ap": "andhra pradesh",
    "tn": "tamil nadu", "wb": "west bengal", "jk": "jammu and kashmir", "j and k": "jammu and kashmir",
    "nct of delhi": "delhi", "new delhi": "delhi", "orissa": "odisha", "uk": "uttarakhand",
    "uttaranchal": "uttarakhand", "pondicherry": "puducherry",
}


def _state(s: str) -> str:
    n = re.sub(r"^(the )?(state|ut|union territory) of ", "", _norm(s.replace("&", " and "))).strip()
    return _STATE_ALIASES.get(n, n)


def same_state(a: str, b: str) -> bool:
    """'Haryana' ~ 'State of Haryana', 'UP' ~ 'Uttar Pradesh', 'Delhi' ~ 'NCT of Delhi'."""
    x, y = _state(a), _state(b)
    return bool(x and y) and (x == y or f" {x} " in f" {y} " or f" {y} " in f" {x} ")


_DOC_GROUPS = {
    "turnover": ("turnover", "balance sheet", "financial statement", "ca certificate"),
    "experience": ("experience", "past performance", "past supply", "completion certificate", "work order"),
    "emd": ("emd", "earnest money", "bid security"),
}


def _doc_groups(d: str) -> set[str]:
    n = _norm(d)
    return {g for g, keys in _DOC_GROUPS.items() if any(k in n for k in keys)}


def _finish(reasons: list[dict], docs: list[str]) -> Result:
    kinds = {r["kind"] for r in reasons}
    verdict = NOT_ELIGIBLE if FAIL in kinds else CHECK_DOCS if WARN in kinds else ELIGIBLE
    order = {FAIL: 0, WARN: 1, OK: 2, INFO: 3}
    return Result(verdict, sorted(reasons, key=lambda r: order[r["kind"]]), list(dict.fromkeys(docs)))


# ---- product fit -------------------------------------------------------------------------------

_STOP = {"and", "for", "the", "of", "with", "supply", "items", "item", "set", "sets"}


def _words(s: str) -> set[str]:
    return {w[:-1] if w.endswith("s") and len(w) > 3 else w for w in _norm(s).split()
            if len(w) > 2 and w not in _STOP}


def keyword_fit(phrases: list[str], title: str, item: str | None) -> float:
    """Offline fallback for embeddings: best share of a profile phrase's words found in the tender."""
    t = _words(f"{title} {item or ''}")
    best = 0.0
    for ph in phrases:
        w = _words(ph)
        if w:
            best = max(best, len(w & t) / len(w))
    return round(best, 3)


# Below these the tender is shown as "low relevance" under the relevant ones.
MIN_FIT_COSINE = 0.35
MIN_FIT_KEYWORD = 0.5
