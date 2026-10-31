import asyncio
import base64
from datetime import datetime
from urllib.parse import parse_qs

import httpx
import pytest

from agents.schemas import IST
from delivery import alerts

MATCH = {
    "id": 7, "verdict": "ELIGIBLE",
    "reasons": [{"kind": "ok", "text": "Turnover met (₹1.2 Cr ≥ ₹50 L)"},
                {"kind": "ok", "text": "MSE EMD exemption applies (saves ₹37,000)"},
                {"kind": "warn", "text": "Needs 3 years past-supply proof"}],
    "missing_docs": ["Udyam certificate (for EMD exemption)", "Past supply orders"],
    "tender": {"title": "Supply of steel storage racks", "buyer": "MoD", "est_value": 1_850_000,
               "end_date": datetime(2026, 10, 28, 15, 0, tzinfo=IST), "source_url": "https://bidplus.gem.gov.in/x"},
    "profile": {"phone": "+919800000000", "email": "ramesh@example.com"},
}


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for k in ("TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "TWILIO_WHATSAPP_FROM", "ALERT_WHATSAPP_TO",
              "SMTP_URL", "ALERT_EMAIL_FROM", "ALERT_EMAIL_TO", "AUTO_ALERT"):
        monkeypatch.delenv(k, raising=False)


def test_message_has_everything_the_plan_lists():
    body = alerts.format_message(MATCH)
    assert body.splitlines()[0] == "🟢 TenderHawk · Eligible"
    assert "*Supply of steel storage racks*" in body
    assert "MoD · ₹18.5 L · closes 28 Oct, 03:00 PM" in body
    assert "✅ Turnover met (₹1.2 Cr ≥ ₹50 L)" in body and "⚠️ Needs 3 years past-supply proof" in body
    assert "📄 Documents: Udyam certificate (for EMD exemption); Past supply orders" in body
    assert body.endswith("🔗 https://bidplus.gem.gov.in/x")


def test_long_message_is_trimmed_but_keeps_header_and_link():
    m = {**MATCH, "reasons": [{"kind": "warn", "text": "x" * 200}] * 20}
    body = alerts.format_message(m)
    assert len(body) <= alerts.WHATSAPP_MAX
    assert body.startswith("🟢 TenderHawk") and body.endswith("🔗 https://bidplus.gem.gov.in/x") and "…" in body


def _twilio_env(monkeypatch):
    monkeypatch.setenv("TWILIO_ACCOUNT_SID", "AC123")
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", "tok")
    monkeypatch.setenv("TWILIO_WHATSAPP_FROM", "whatsapp:+14155238886")


def test_whatsapp_request_shape(monkeypatch):
    _twilio_env(monkeypatch)
    seen = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen["url"] = str(req.url)
        seen["auth"] = req.headers["authorization"]
        seen["form"] = parse_qs(req.content.decode())
        return httpx.Response(201, json={"sid": "SM1"})

    res = asyncio.run(alerts.send_whatsapp("+919800000000", "hi", transport=httpx.MockTransport(handler)))
    assert res == "sent"
    assert seen["url"] == "https://api.twilio.com/2010-04-01/Accounts/AC123/Messages.json"
    assert seen["auth"] == "Basic " + base64.b64encode(b"AC123:tok").decode()
    assert seen["form"] == {"From": ["whatsapp:+14155238886"], "To": ["whatsapp:+919800000000"], "Body": ["hi"]}


def test_whatsapp_error_and_unconfigured(monkeypatch):
    assert asyncio.run(alerts.send_whatsapp("+91", "hi")) == "not_configured"
    _twilio_env(monkeypatch)
    t = httpx.MockTransport(lambda r: httpx.Response(400, json={"message": "not joined to sandbox"}))
    assert asyncio.run(alerts.send_whatsapp("+91", "hi", transport=t)) == "failed: not joined to sandbox"

    def boom(r):
        raise httpx.ConnectError("offline")
    assert asyncio.run(alerts.send_whatsapp("+91", "hi", transport=httpx.MockTransport(boom))) == \
        "failed: ConnectError"


class FakeSMTP:
    instances = []

    def __init__(self, host, port, timeout=None, context=None):
        self.host, self.port, self.calls = host, port, []
        FakeSMTP.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def starttls(self, context=None):
        self.calls.append("starttls")

    def login(self, user, password):
        self.calls.append(("login", user, password))

    def send_message(self, msg):
        self.calls.append(("send", msg["From"], msg["To"], msg["Subject"], msg.get_content()))


def test_email_over_smtp_with_starttls(monkeypatch):
    FakeSMTP.instances.clear()
    monkeypatch.setattr(alerts.smtplib, "SMTP", FakeSMTP)
    monkeypatch.setenv("SMTP_URL", "smtp://bot%40th.in:p%40ss@smtp.example.com:587")
    assert alerts._smtp_send("ramesh@example.com", "Subj", "*Bold* body") == "sent"
    s = FakeSMTP.instances[0]
    assert (s.host, s.port) == ("smtp.example.com", 587)
    assert s.calls[0] == "starttls" and s.calls[1] == ("login", "bot@th.in", "p@ss")
    assert s.calls[2][:4] == ("send", "bot@th.in", "ramesh@example.com", "Subj")
    assert s.calls[2][4].strip() == "Bold body"


def test_email_unconfigured_and_bad_url(monkeypatch):
    assert alerts._smtp_send("a@b.c", "s", "b") == "not_configured"
    monkeypatch.setenv("SMTP_URL", "http://nope")
    assert alerts._smtp_send("a@b.c", "s", "b").startswith("failed: SMTP_URL")


def test_alert_match_marks_alerted_only_when_sent(monkeypatch):
    marked = []
    monkeypatch.setattr(alerts, "_load", lambda mid: MATCH if mid == 7 else None)
    monkeypatch.setattr(alerts, "_mark_alerted", marked.append)
    monkeypatch.setenv("ALERT_WHATSAPP_TO", "+911111111111")
    sent_to = []

    async def wa(to, body):
        sent_to.append(to)
        return "sent"

    async def mail(to, subject, body):
        return "not_configured"

    monkeypatch.setattr(alerts, "send_whatsapp", wa)
    monkeypatch.setattr(alerts, "send_email", mail)
    res = asyncio.run(alerts.alert_match(7))
    assert res["sent"] and res["channels"] == {"whatsapp": "sent", "email": "not_configured"}
    assert marked == [7] and sent_to == ["+911111111111"]       # stage phone wins over profile phone
    assert asyncio.run(alerts.alert_match(99)) is None

    async def nothing(*a):
        return "not_configured"
    monkeypatch.setattr(alerts, "send_whatsapp", nothing)
    res = asyncio.run(alerts.alert_match(7))
    assert not res["sent"] and res["preview"].startswith("🟢") and marked == [7]


def test_auto_alert_counts_and_isolates_failures(monkeypatch):
    monkeypatch.setattr(alerts, "_pending_eligible", lambda pid: [1, 2, 3])

    async def fake(mid):
        if mid == 2:
            raise RuntimeError("boom")
        return {"sent": mid == 1}

    monkeypatch.setattr(alerts, "alert_match", fake)
    assert asyncio.run(alerts.auto_alert(1)) == 1
    monkeypatch.setenv("AUTO_ALERT", "false")
    assert asyncio.run(alerts.auto_alert(1)) == 0


def test_alert_endpoint_404():
    from fastapi.testclient import TestClient
    from api.main import app
    assert TestClient(app).post("/matches/987654321/alert").status_code == 404


def test_failed_whatsapp_keeps_match_pending_for_retry(monkeypatch):
    marked = []
    monkeypatch.setattr(alerts, "_load", lambda mid: MATCH)
    monkeypatch.setattr(alerts, "_mark_alerted", marked.append)

    async def wa(to, body):
        return "failed: not joined to sandbox"

    async def mail(to, subject, body):
        return "sent"

    monkeypatch.setattr(alerts, "send_whatsapp", wa)
    monkeypatch.setattr(alerts, "send_email", mail)
    res = asyncio.run(alerts.alert_match(7))
    assert res["sent"] and marked == []          # email went, but WhatsApp will be retried next sweep


def test_huge_checklist_never_cuts_the_link():
    m = {**MATCH, "missing_docs": ["Additional Doc (Requested in ATC) " * 3] * 60, "title": "x" * 1400}
    m["tender"] = {**MATCH["tender"], "title": "T" * 1400}
    body = alerts.format_message(m)
    assert len(body) <= alerts.WHATSAPP_MAX and body.endswith("🔗 https://bidplus.gem.gov.in/x")


def test_auto_alerts_run_in_parallel_within_a_budget(monkeypatch):
    monkeypatch.setattr(alerts, "_pending_eligible", lambda pid: [1, 2, 3])
    monkeypatch.setattr(alerts, "AUTO_ALERT_BUDGET", 0.3)

    async def slow(mid):
        await asyncio.sleep(0.2)
        return {"sent": True}

    monkeypatch.setattr(alerts, "alert_match", slow)
    assert asyncio.run(alerts.auto_alert(1)) == 3          # parallel: 0.2 s total, inside the budget

    async def hung(mid):
        await asyncio.sleep(5)

    monkeypatch.setattr(alerts, "alert_match", hung)
    assert asyncio.run(alerts.auto_alert(1)) == 0          # gives up at the budget instead of hanging


def test_reset_alerts_for_unknown_profile_touches_nothing():
    assert alerts.reset_alerts(987654321) == 0


def test_channel_status_reports_setup_without_secrets(monkeypatch):
    from delivery import alerts
    for k in ("TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "TWILIO_WHATSAPP_FROM", "SMTP_URL", "ALERT_EMAIL_TO"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("ALERT_WHATSAPP_TO", "+919811244321")
    s = alerts.channel_status()
    assert s["whatsapp"] is False and s["email"] is False and s["whatsapp_to"] == "+91•••••4321"
    monkeypatch.setenv("TWILIO_ACCOUNT_SID", "AC123")
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", "secret-token")
    monkeypatch.setenv("TWILIO_WHATSAPP_FROM", "whatsapp:+14155238886")
    s = alerts.channel_status()
    assert s["whatsapp"] is True and "secret-token" not in str(s) and "AC123" not in str(s)


def test_preview_is_the_message_and_sends_nothing(monkeypatch):
    from delivery import alerts
    m = {"id": 1, "verdict": "ELIGIBLE", "reasons": [{"kind": "ok", "text": "No EMD required"}], "missing_docs": [],
         "tender": {"title": "Metal Shelving Racks", "buyer": "WB", "est_value": None,
                    "end_date": __import__("datetime").datetime(2026, 11, 21, 17, 0), "source_url": "https://x"},
         "profile": {"phone": "+91", "email": None}}
    monkeypatch.setattr(alerts, "_load", lambda mid: m if mid == 1 else None)

    async def boom(*a, **k):
        raise AssertionError("preview must not send")
    monkeypatch.setattr(alerts, "send_whatsapp", boom)
    assert alerts.preview_match(1) == alerts.format_message(m) and "Metal Shelving Racks" in alerts.preview_match(1)
    assert alerts.preview_match(2) is None


def test_sandbox_session_expired_gets_a_plain_instruction(monkeypatch):
    _twilio_env(monkeypatch)
    t = httpx.MockTransport(lambda r: httpx.Response(400, json={"message": "ContentSid Required"}))
    res = asyncio.run(alerts.send_whatsapp("+91", "hi", transport=t))
    assert res.startswith("failed: the phone hasn't messaged the Twilio sandbox") and "+1 415 523 8886" in res
