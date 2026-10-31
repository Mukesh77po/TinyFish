import asyncio
from datetime import datetime, timedelta

import pymupdf

from agents.schemas import IST
from delivery import build_fixture as bf

NOW = datetime(2026, 10, 25, 12, 0, tzinfo=IST)


def bid(n, days):
    return {"portal": "gem", "bid_no": f"GEM/2026/B/{n}", "title": "Storage rack",
            "end_date": (NOW + timedelta(days=days)).isoformat(),
            "doc_url": f"https://bidplus.gem.gov.in/showbidDocument/{n}0", "source_url": "https://x"}


def test_find_documents_by_doc_id_or_bid_number(tmp_path):
    (tmp_path / "10.pdf").write_bytes(b"%PDF")
    (tmp_path / "GEM_2026_B_2.txt").write_text("doc")
    (tmp_path / "notes.docx").write_text("ignored")
    found = bf.find_documents([bid(1, 3), bid(2, 3), bid(3, 3)], tmp_path)
    assert {u.rsplit("/", 1)[-1]: p.name for u, p in found.items()} == {"10": "10.pdf", "20": "GEM_2026_B_2.txt"}


def test_attach_converts_pdf_and_records_parse(tmp_path, monkeypatch):
    doc = pymupdf.open()
    doc.new_page().insert_text((72, 72), "Minimum Average Annual Turnover 40 Lakh (s)")
    (tmp_path / "10.pdf").write_bytes(doc.tobytes())

    async def fake_parse(text):
        assert "40 Lakh" in text
        return {"min_turnover": {"value": 4000000, "source_clause": "Minimum Average Annual Turnover 40 Lakh (s)"}}

    monkeypatch.setattr(bf, "parse_eligibility", fake_parse)
    fx = {"result": [bid(1, 3)], "steps": [{"step": 1, "message": "x"}]}
    asyncio.run(bf.attach(fx, tmp_path, parse=True, log=lambda *a: None))
    url = "https://bidplus.gem.gov.in/showbidDocument/10"
    assert "40 Lakh" in fx["docs"][url] and fx["eligibility"][url]["min_turnover"]["value"] == 4000000


def test_check_flags_what_would_break_the_demo():
    assert "no bids recorded" in bf.check({"result": [], "steps": []}, NOW)
    closed = bf.check({"result": [bid(1, -1)], "steps": [{"step": 1}]}, NOW)
    assert any("every bid has closed" in p for p in closed)
    p = bf.check({"result": [bid(1, 3)], "steps": [{"step": 1}], "docs": {}, "eligibility": {}}, NOW)
    assert any("no document text" in x for x in p) and any("no recorded parse" in x for x in p)


def test_check_passes_a_complete_fixture():
    url = "https://bidplus.gem.gov.in/showbidDocument/10"
    el = {k: {"value": None, "source_clause": None} for k in (
        "min_turnover", "past_experience_years", "emd_amount", "emd_exemption_for_mse",
        "mse_relaxation_experience_turnover", "startup_relaxation_experience_turnover")}
    el.update({k: {"value": [], "source_clause": None} for k in ("required_certifications", "documents_required", "states")})
    fx = {"result": [bid(1, 3)], "steps": [{"step": 1}], "docs": {url: "text"}, "eligibility": {url: el}}
    assert bf.check(fx, NOW) == []


def test_cli_reports_missing_fixture(capsys):
    assert bf.main(["check", "gem", "no such category"]) == 2
    assert "Record one first" in capsys.readouterr().out


def test_bid_without_document_link_is_not_a_problem():
    """CPPP/Haryana give no readable document link: the bid is shown as CHECK_DOCS with the portal link."""
    no_doc = {**bid(9, 3), "portal": "cppp", "doc_url": None}
    assert bf.check({"result": [no_doc], "steps": [{"step": 1}]}, NOW) == []
