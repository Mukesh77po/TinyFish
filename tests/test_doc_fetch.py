"""Bid document chain in agents/: TinyFish Fetch first, direct PDF download only as a last resort."""
import asyncio

import httpx
import pymupdf
import pytest

from agents import client

GEM_DOC = "https://bidplus.gem.gov.in/showbidDocument/9845350"


def _pdf(text: str) -> bytes:
    doc = pymupdf.open()
    doc.new_page().insert_text((72, 72), text)
    return doc.tobytes()


@pytest.fixture
def live(monkeypatch):
    monkeypatch.setenv("FALLBACK_MODE", "false")
    calls = {"fetch": 0, "direct": []}

    async def no_fetch(url):
        calls["fetch"] += 1
        return ""
    monkeypatch.setattr(client, "_fetch", no_fetch)
    return calls


def _serve(monkeypatch, calls, status=200, body=b""):
    real = httpx.AsyncClient

    def handler(request):
        calls["direct"].append(str(request.url))
        return httpx.Response(status, content=body)
    monkeypatch.setattr(client.httpx, "AsyncClient",
                        lambda **kw: real(transport=httpx.MockTransport(handler), **kw))


def test_fetch_text_wins_without_direct_download(monkeypatch, live):
    async def fetch(url):
        return "EMD Amount 100000"
    monkeypatch.setattr(client, "_fetch", fetch)
    _serve(monkeypatch, live, body=_pdf("never used"))
    assert asyncio.run(client.fetch_doc_text(GEM_DOC)) == ("EMD Amount 100000", "fetch")
    assert live["direct"] == []


def test_fetch_failure_falls_back_to_direct_pdf(monkeypatch, live):
    _serve(monkeypatch, live, body=_pdf("Minimum Average Annual Turnover of the bidder 3 Lakh"))
    text, source = asyncio.run(client.fetch_doc_text(GEM_DOC))
    assert source == "direct" and "Annual Turnover of the bidder 3 Lakh" in text
    assert live["fetch"] == 1 and live["direct"] == [GEM_DOC]


@pytest.mark.parametrize("url", ["https://evil.example.com/x.pdf", "http://bidplus.gem.gov.in/showbidDocument/1"])
def test_direct_download_only_https_on_swept_portals(monkeypatch, live, url):
    _serve(monkeypatch, live, body=_pdf("x"))
    assert asyncio.run(client.fetch_doc_text(url)) == ("", "")
    assert live["direct"] == []


@pytest.mark.parametrize("status,body", [(200, b"<html>login</html>"), (503, b"%PDF-")])
def test_direct_download_rejects_non_pdf_and_errors(monkeypatch, live, status, body):
    _serve(monkeypatch, live, status=status, body=body)
    assert asyncio.run(client.fetch_doc_text(GEM_DOC)) == ("", "")


def test_fallback_mode_reads_fixture_docs_only(monkeypatch):
    monkeypatch.setenv("FALLBACK_MODE", "true")
    monkeypatch.setattr(client, "_fixture_docs", lambda: {GEM_DOC: "EMD Amount 1"})
    assert asyncio.run(client.fetch_doc_text(GEM_DOC)) == ("EMD Amount 1", "fixture")
    assert asyncio.run(client.fetch_doc_text("https://bidplus.gem.gov.in/showbidDocument/0")) == ("", "")


def test_agent_limits_never_send_max_steps():
    """The account rejects a custom max_steps with HTTP 403, which would fail every live sweep."""
    assert client.AGENT_LIMITS.max_steps is None
    assert 300 <= client.AGENT_LIMITS.max_duration_seconds < client.AGENT_TIMEOUT  # we outwait the agent's own budget


def test_session_bound_portal_links_are_dropped():
    """CPPP/Haryana DirectLink URLs expire ("Stale Session"): keep the stable list page as the link instead."""
    raw = {"bid_no": "SAI/RC-TVM/INFRA/2026-27", "title": "Storage racks", "end_date": "09-Nov-2026 06:00 PM",
           "doc_url": "https://eprocure.gov.in/eprocure/app?component=%24DirectLink&page=FrontEndLatestActiveTenders"
                      "&service=direct&session=T&sp=S7Pc"}
    (b,) = client.to_listings("cppp", [raw])
    assert b.doc_url is None and b.source_url == client.PORTALS["cppp"]["url"]
    (g,) = client.to_listings("gem", [{**raw, "doc_url": GEM_DOC}])
    assert g.doc_url == GEM_DOC


def test_blocked_fixture_replays_as_error_card_with_portal_link(monkeypatch, tmp_path):
    import json
    monkeypatch.setenv("FALLBACK_MODE", "true")
    monkeypatch.setattr(client, "FIXTURES_DIR", tmp_path)
    monkeypatch.setattr(client.random, "uniform", lambda a, b: 0)
    (tmp_path / "haryana_storage_rack.json").write_text(json.dumps({
        "url": client.PORTALS["haryana"]["url"], "steps": [{"step": 1, "message": "Open"}, {"step": 2, "message": "Search"}],
        "blocked": True, "result": [],
        "blocked_reason": "The Haryana e-procurement site requires a captcha to perform tender searches. More detail."}))
    events = []
    assert asyncio.run(client.sweep_portal("haryana", "storage rack", events.append)) == []
    assert [e.type for e in events] == ["started", "step", "step", "error"]
    assert events[-1].direct_url == client.PORTALS["haryana"]["url"]
    assert events[-1].message == ("Blocked: The Haryana e-procurement site requires a captcha to perform tender "
                                  "searches. Open on portal.")


def test_agent_run_past_the_hard_timeout_becomes_an_error_card(monkeypatch):
    """TinyFish's max_duration_seconds is soft (a run went 352 s): we stop waiting ourselves."""
    monkeypatch.setenv("FALLBACK_MODE", "false")
    monkeypatch.setattr(client, "AGENT_TIMEOUT", 0.2)

    class Hanging:
        async def __aenter__(self):
            return self
        async def __aexit__(self, *a):
            return False
        def __aiter__(self):
            return self
        started = False
        async def __anext__(self):
            if not self.started:
                self.started = True
                return client.StartedEvent.model_construct(run_id="run-1")
            await asyncio.sleep(10)

    class TF:
        class agent:
            @staticmethod
            def stream(**kw):
                return Hanging()
    monkeypatch.setattr(client, "_tf", lambda: TF)
    cancelled = []

    async def cancel(run_id):
        cancelled.append(run_id)
    monkeypatch.setattr(client, "_cancel_run", cancel)
    events = []
    assert asyncio.run(client.sweep_portal("gem", "storage rack", events.append)) == []
    assert events[-1].type == "error" and "cancelled" in events[-1].message
    assert cancelled == ["run-1"]  # the TinyFish run is stopped too, not left running and billing
    assert events[-1].direct_url == client.PORTALS["gem"]["url"]


def test_guessed_gem_document_urls_are_dropped():
    raw = {"bid_no": "GEM/2026/B/8186409", "title": "Steel Almirah", "end_date": "13-11-2026 7:00 PM",
           "doc_url": "https://bidplus.gem.gov.in/showbiddata/GEM/2026/B/8186409"}
    (b,) = client.to_listings("gem", [raw])
    assert b.doc_url is None and b.source_url == client.PORTALS["gem"]["url"]


@pytest.mark.parametrize("text,bid", [
    # Real search results for recorded bids (2026-10-25): none of them is a corrigendum for that bid.
    ("eProcurement System Government of India Search | Active Tenders | Tenders by Closing Date | Corrigendum | "
     "Bid Awards | CPPP Home ... [ BARCF/INR-PRJ/ME/TR/41/2026 ][2026_BARC_928841_1], Bhabha Atomic", "BARCF/INR-PRJ/ME/TR/41/2026"),
    ("CPPP Tenders Title/Ref.No./Tender Id · Organisation Name · Corrigendum ... 07-October-2026 06:00:00 PM, "
     "SHEET ROOFING OVER THE TERRACE AREA/ SAI/RC-TVM/INFRA/2026-27 /", "SAI/RC-TVM/INFRA/2026-27"),
    ("2 days ago — GEM/2026/B/8151881 . Tender Agency. all india institute of medical ... 8. corrigendum tender "
     "for gas chromatograph · 9. corrigendum tender for", "GEM/2026/B/8151881"),
    ("Bid Number: GEM/2026/B/8171651 . Dated: 22 ... Bid document, ATC and Corrigendum if any. 10. Certificates.",
     "GEM/2026/B/8171651"),
])
def test_corrigendum_word_alone_is_not_a_notice(text, bid):
    assert not client.is_corrigendum_notice(text, bid)


@pytest.mark.parametrize("text", [
    "Corrigendum 1 for GEM/2026/B/8171651: bid end date extended to 20-11-2026",
    "GEM/2026/B/8171651 - Bid End Date has been extended till 20-11-2026 03:00 PM",
    "Tender GEM/2026/B/8171651: extension of bid due date",
    "Amendment No. 2 issued for GEM/2026/B/8171651",
])
def test_real_notices_are_found(text):
    assert client.is_corrigendum_notice(text, "GEM/2026/B/8171651")


def test_notice_about_another_bid_on_the_same_page_is_ignored():
    text = "GEM/2026/B/8171651 Steel almirah. " + "x" * 400 + " Corrigendum 1 for GEM/2026/B/9999999"
    assert not client.is_corrigendum_notice(text, "GEM/2026/B/8171651")


def test_agent_runs_queue_locally_beyond_the_plan_concurrency(monkeypatch):
    """A 3rd run would wait in TinyFish's queue and burn our timeout: it waits for a local slot instead."""
    monkeypatch.setattr(client, "_slots", asyncio.Semaphore(2))
    running, peak, waits = 0, 0, []

    async def fake_run(portal, category, on_step):
        nonlocal running, peak
        running += 1
        peak = max(peak, running)
        await asyncio.sleep(0.05)
        running -= 1
        return {"result": {"bids": []}}

    monkeypatch.setattr(client, "_run_agent", fake_run)

    async def sweep():
        await asyncio.gather(*(client.run_agent(p, "rack", lambda n, m, p=p: waits.append(p))
                               for p in ("gem", "cppp", "haryana")))
    asyncio.run(sweep())
    assert peak == 2 and waits == ["haryana"]
