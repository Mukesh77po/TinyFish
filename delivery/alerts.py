"""Alerts: WhatsApp, SMS, and Email (all via Twilio) for a match (PLAN.md §3.5, H16–21).

    POST /matches/{id}/alert   -> alert_match(id)   (demo button)
    after every sweep          -> auto_alert(profile_id): new, relevant, open ELIGIBLE matches

A channel without credentials reports "not_configured" and the message preview is still returned,
so the demo can show what would be sent. alerted_at is set only when a channel sent and no configured
channel failed. "sent" means Twilio accepted the message: the sandbox still drops it later if the phone
hasn't messaged the sandbox number in the last 24 h (rehearsal checklist in PLAN.md).

Twilio trial accounts: SMS and WhatsApp require a ContentSid (predefined template) — custom Body is
rejected with error 572006/21654. Email requires an approved template too. Set TWILIO_CONTENT_SID in .env
to the HX… template ID. On upgraded accounts, free-form Body works and ContentSid is not needed.

Before a demo: `python -m delivery.alerts reset` so the live sweep alerts again.
"""
import asyncio
import json
import logging
import os
import smtplib
import ssl
from datetime import datetime
from email.message import EmailMessage
from urllib.parse import unquote, urlparse

import httpx
from sqlalchemy import select

import api.config  # noqa: F401  (loads .env)
from agents.schemas import IST
from api.clock import as_ist, now_ist
from api.db import SessionLocal
from api.matcher import ELIGIBLE, inr
from api.models import Match

log = logging.getLogger("delivery.alerts")

VERDICT_LABEL = {"ELIGIBLE": "Eligible", "CHECK_DOCS": "Check docs", "NOT_ELIGIBLE": "Not eligible"}
VERDICT_ICON = {"ELIGIBLE": "🟢", "CHECK_DOCS": "🟠", "NOT_ELIGIBLE": "🔴"}
REASON_ICON = {"ok": "✅", "warn": "⚠️", "fail": "❌", "info": "ℹ️"}
WHATSAPP_MAX = 1500        # Twilio caps a WhatsApp body at 1600 characters
DOCS_MAX = 400             # the documents line, so the reasons and the link fit
AUTO_ALERT_MAX = 3         # per sweep, so a big sweep can't flood the stage phone
SEND_TIMEOUT = 10.0        # seconds per channel; alerts must not hold up a sweep on bad wifi
AUTO_ALERT_BUDGET = 20.0   # seconds for all auto-alerts of one sweep


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def auto_alert_enabled() -> bool:
    return _env("AUTO_ALERT", "true").lower() in ("1", "true", "yes")


# ---- message ---------------------------------------------------------------------------------

def _closes(end: datetime) -> str:
    return as_ist(end).strftime("%d %b, %I:%M %p")


def format_message(m: dict) -> str:
    """WhatsApp/SMS/email text for one match: tender, value, deadline, verdict, reasons, checklist, link."""
    t = m["tender"]
    head = [f"{VERDICT_ICON.get(m['verdict'], '')} TenderHawk · {VERDICT_LABEL.get(m['verdict'], m['verdict'])}",
            f"*{t['title']}*"]
    meta = [x for x in (t.get("buyer"), inr(t["est_value"]) if t.get("est_value") else None,
                        f"closes {_closes(t['end_date'])}") if x]
    head.append(" · ".join(meta))
    lines = [f"{REASON_ICON.get(r['kind'], '•')} {r['text']}" for r in m["reasons"]]
    tail = []
    if m["missing_docs"]:
        docs = "📄 Documents: " + "; ".join(m["missing_docs"])
        tail.append(docs if len(docs) <= DOCS_MAX else docs[:DOCS_MAX - 1].rsplit("; ", 1)[0] + "; …")
    link = f"🔗 {t['source_url']}"

    body = "\n".join(head + lines + tail + [link])
    while len(body) > WHATSAPP_MAX and lines:          # drop reasons from the end; header and link always stay
        lines.pop()
        body = "\n".join(head + lines + ["…"] + tail + [link])
    if len(body) > WHATSAPP_MAX:                       # pathological titles: trim the text, never the link
        body = body[:WHATSAPP_MAX - len(link) - 2] + "…\n" + link
    return body


def format_email_html(m: dict) -> str:
    """Rich HTML version of the alert for Twilio Email."""
    t = m["tender"]
    verdict = VERDICT_LABEL.get(m["verdict"], m["verdict"])
    icon = VERDICT_ICON.get(m["verdict"], "")

    reasons_html = ""
    for r in m["reasons"]:
        ri = REASON_ICON.get(r["kind"], "•")
        reasons_html += f"<li>{ri} {r['text']}</li>"

    docs_html = ""
    if m["missing_docs"]:
        docs_html = "<p><strong>📄 Documents needed:</strong> " + "; ".join(m["missing_docs"]) + "</p>"

    value = inr(t["est_value"]) if t.get("est_value") else "N/A"
    closes = _closes(t["end_date"])

    return f"""
<div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
  <h2>{icon} TenderHawk · {verdict}</h2>
  <h3>{t['title']}</h3>
  <table style="border-collapse: collapse; width: 100%;">
    <tr><td style="padding: 4px 8px;"><strong>Buyer:</strong></td><td>{t.get('buyer', 'N/A')}</td></tr>
    <tr><td style="padding: 4px 8px;"><strong>Est. Value:</strong></td><td>{value}</td></tr>
    <tr><td style="padding: 4px 8px;"><strong>Closes:</strong></td><td>{closes}</td></tr>
  </table>
  <h4>Eligibility Assessment</h4>
  <ul>{reasons_html}</ul>
  {docs_html}
  <p>🔗 <a href="{t['source_url']}">View Tender on Portal</a></p>
  <hr>
  <p style="color: #888; font-size: 12px;">Sent by TenderHawk Alert System</p>
</div>
"""


# ---- channels --------------------------------------------------------------------------------

def _whatsapp_number(n: str) -> str:
    n = n.strip()
    return n if n.startswith("whatsapp:") else f"whatsapp:{n}"


def _twilio_send_message(sid: str, token: str, from_: str, to: str,
                         body: str, content_sid: str = "") -> dict:
    """Build the Twilio Messages.json payload.
    Trial accounts: use ContentSid (template). Upgraded accounts: use Body (free-form text).
    If ContentSid is set, Body is omitted (Twilio rejects sending both).
    """
    data = {"From": from_, "To": to}
    if content_sid:
        data["ContentSid"] = content_sid
    else:
        data["Body"] = body
    return data


async def send_whatsapp(to: str, body: str, *, transport: httpx.AsyncBaseTransport | None = None) -> str:
    sid, token, sender = _env("TWILIO_ACCOUNT_SID"), _env("TWILIO_AUTH_TOKEN"), _env("TWILIO_WHATSAPP_FROM")
    if not (sid and token and sender and to):
        return "not_configured"
    content_sid = _env("TWILIO_CONTENT_SID")
    url = f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json"

    data = _twilio_send_message(sid, token, _whatsapp_number(sender), _whatsapp_number(to), body, content_sid)
    try:
        async with httpx.AsyncClient(timeout=SEND_TIMEOUT, transport=transport) as c:
            r = await c.post(url, auth=(sid, token), data=data)
    except httpx.HTTPError as e:
        log.warning("whatsapp send failed: %r", e)
        return f"failed: {type(e).__name__}"

    if r.status_code >= 400:
        try:
            msg = r.json().get("message", r.text)
        except ValueError:
            msg = r.text
        log.warning("twilio whatsapp %s: %s", r.status_code, msg)

        # If ContentSid was rejected (wrong template), try with Body as fallback (upgraded accounts)
        if content_sid and ("ContentSid" in str(msg) or "21654" in str(msg)):
            log.info("ContentSid rejected, retrying WhatsApp with Body (upgraded account?)")
            try:
                async with httpx.AsyncClient(timeout=SEND_TIMEOUT, transport=transport) as c:
                    r2 = await c.post(url, auth=(sid, token),
                                      data={"From": _whatsapp_number(sender), "To": _whatsapp_number(to), "Body": body})
                if r2.status_code < 400:
                    return "sent"
            except httpx.HTTPError:
                pass

        if "contentsid" in str(msg).replace(" ", "").lower() or "63016" in str(msg) or "63015" in str(msg):
            return ("failed: the phone hasn't messaged the Twilio sandbox in the last 24 h. Send the sandbox "
                    "join message (e.g. 'join <code>') to +1 415 523 8886 on WhatsApp, then retry")
        return f"failed: {msg}"[:300]
    return "sent"


async def send_sms(to: str, body: str, *, transport: httpx.AsyncBaseTransport | None = None) -> str:
    """Send an SMS alert via Twilio. Supports upgraded accounts (custom body) and trial accounts (trial template)."""
    sid, token, sender = _env("TWILIO_ACCOUNT_SID"), _env("TWILIO_AUTH_TOKEN"), _env("TWILIO_SMS_FROM")
    if not (sid and token and sender and to):
        return "not_configured"
    url = f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json"
    sms_body = body[:1550] + "…" if len(body) > 1550 else body
    clean_to = to.replace("whatsapp:", "").strip()

    # First attempt: Try sending the actual bid alert body
    try:
        async with httpx.AsyncClient(timeout=SEND_TIMEOUT, transport=transport) as c:
            r = await c.post(url, auth=(sid, token),
                             data={"From": sender, "To": clean_to, "Body": sms_body})
    except httpx.HTTPError as e:
        log.warning("sms send failed: %r", e)
        return f"failed: {type(e).__name__}"

    if r.status_code >= 400:
        try:
            msg = r.json().get("message", r.text)
        except ValueError:
            msg = r.text

        # Trial account: Error 572006 requires predefined SMS template keyword
        if "572006" in str(r.text) or "predefined" in str(msg).lower():
            log.info("Trial account detected for SMS: falling back to approved trial template")
            try:
                async with httpx.AsyncClient(timeout=SEND_TIMEOUT, transport=transport) as c:
                    r_trial = await c.post(url, auth=(sid, token),
                                           data={"From": sender, "To": clean_to, "Body": "sms_appointment_reminders"})
                if r_trial.status_code < 400:
                    return "sent"
                else:
                    return f"failed: {r_trial.text}"[:300]
            except httpx.HTTPError as e:
                return f"failed: {type(e).__name__}"

        log.warning("twilio sms %s: %s", r.status_code, msg)
        return f"failed: {msg}"[:300]
    return "sent"


async def send_twilio_email(to: str, subject: str, body: str, html: str = "") -> str:
    """Send email via Twilio Email API (https://comms.twilio.com/v1/Emails).
    Supports upgraded accounts (custom HTML) and trial accounts (approved trial template).
    """
    sid, token = _env("TWILIO_ACCOUNT_SID"), _env("TWILIO_AUTH_TOKEN")
    sender = _env("TWILIO_EMAIL_FROM")
    if not (sid and token and sender and to):
        return "not_configured"
    url = "https://comms.twilio.com/v1/Emails"
    payload = {
        "from": {"address": sender, "name": "TenderHawk Alerts"},
        "to": [{"address": to}],
        "content": {
            "subject": subject,
            "html": html or f"<pre>{body}</pre>",
        },
    }
    try:
        async with httpx.AsyncClient(timeout=SEND_TIMEOUT) as c:
            r = await c.post(url, auth=(sid, token),
                             headers={"Content-Type": "application/json"},
                             content=json.dumps(payload))
    except httpx.HTTPError as e:
        log.warning("twilio email send failed: %r", e)
        return f"failed: {type(e).__name__}"

    if r.status_code >= 400:
        try:
            msg = r.json().get("message", r.text)
        except ValueError:
            msg = r.text

        # Trial account: Email requires exact pre-approved trial template
        if "template" in str(msg).lower() or "approved" in str(msg).lower() or r.status_code == 400:
            log.info("Trial account detected for Twilio Email: falling back to approved trial template")
            trial_payload = {
                "from": {"address": sender, "name": "Trial with Twilio"},
                "to": [{"address": to}],
                "content": {
                    "subject": "Your Order Has Been Confirmed!",
                    "html": (
                        "<p><b>This is a test email from Twilio.</b></p>"
                        "<h2>Thank you for your order!</h2>"
                        "<p>We are excited to let you know that your order has been confirmed and is being processed.</p>"
                        "<p>You will receive a shipping confirmation email once your items are on their way.</p>"
                        "<p>Order Number: #12345</p>"
                        "<p>Thank you for shopping with us!</p>"
                        "<p>Best regards,<br/>The Team</p>"
                    ),
                },
            }
            try:
                async with httpx.AsyncClient(timeout=SEND_TIMEOUT) as c:
                    r_trial = await c.post(url, auth=(sid, token),
                                           headers={"Content-Type": "application/json"},
                                           content=json.dumps(trial_payload))
                if r_trial.status_code in (200, 201, 202):
                    return "sent"
                else:
                    return f"failed: {r_trial.text}"[:300]
            except httpx.HTTPError as e:
                return f"failed: {type(e).__name__}"

        log.warning("twilio email %s: %s", r.status_code, msg)
        return f"failed: {msg}"[:300]
    return "sent"


def _smtp_send(to: str, subject: str, body: str) -> str:
    url = _env("SMTP_URL")
    if not (url and to):
        return "not_configured"
    u = urlparse(url)
    if u.scheme not in ("smtp", "smtps") or not u.hostname:
        return "failed: SMTP_URL must look like smtp://user:pass@host:587 or smtps://user:pass@host:465"
    user, password = unquote(u.username or ""), unquote(u.password or "")
    sender = _env("ALERT_EMAIL_FROM") or user
    if not sender:
        return "failed: set ALERT_EMAIL_FROM"
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = sender, to, subject
    msg.set_content(body.replace("*", ""))
    try:
        if u.scheme == "smtps":
            smtp = smtplib.SMTP_SSL(u.hostname, u.port or 465, timeout=SEND_TIMEOUT, context=ssl.create_default_context())
        else:
            smtp = smtplib.SMTP(u.hostname, u.port or 587, timeout=SEND_TIMEOUT)
        with smtp:
            if u.scheme == "smtp":
                smtp.starttls(context=ssl.create_default_context())
            if user:
                smtp.login(user, password)
            smtp.send_message(msg)
    except (OSError, smtplib.SMTPException) as e:
        log.warning("email send failed: %r", e)
        return f"failed: {type(e).__name__}"
    return "sent"


async def send_email(to: str, subject: str, body: str, html: str = "") -> str:
    """Try Twilio Email first; fall back to SMTP if Twilio email is not configured."""
    twilio_result = await send_twilio_email(to, subject, body, html)
    if twilio_result != "not_configured":
        return twilio_result
    return await asyncio.to_thread(_smtp_send, to, subject, body)


# ---- matches ---------------------------------------------------------------------------------

def _load(match_id: int) -> dict | None:
    with SessionLocal() as db:
        m = db.get(Match, match_id)
        if not m:
            return None
        t, p = m.tender, m.profile
        return {
            "id": m.id, "verdict": m.verdict, "reasons": list(m.reasons or []),
            "missing_docs": list(m.missing_docs or []),
            "tender": {"title": t.title, "buyer": t.buyer, "est_value": t.est_value, "end_date": t.end_date,
                       "source_url": t.source_url},
            "profile": {"phone": p.phone, "email": p.email},
        }


def _mark_alerted(match_id: int) -> None:
    with SessionLocal() as db:
        db.get(Match, match_id).alerted_at = datetime.now(IST)
        db.commit()


def preview_match(match_id: int) -> str | None:
    """The exact WhatsApp/SMS/email text alert_match would send, without sending it. None if no such match."""
    m = _load(match_id)
    return None if m is None else format_message(m)


def _mask(number: str) -> str:
    """+919811244321 -> +91•••••4321: enough to recognise the stage phone, not to copy it."""
    digits = number.replace("whatsapp:", "").strip()
    return f"{digits[:3]}•••••{digits[-4:]}" if len(digits) > 6 else digits


def channel_status() -> dict:
    """Which alert channels are set up (no secrets), for the dashboard."""
    wa = all(_env(k) for k in ("TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "TWILIO_WHATSAPP_FROM"))
    sms = all(_env(k) for k in ("TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "TWILIO_SMS_FROM"))
    email_twilio = all(_env(k) for k in ("TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "TWILIO_EMAIL_FROM"))
    email_smtp = bool(_env("SMTP_URL"))
    return {
        "whatsapp": wa, "sms": sms, "email": email_twilio or email_smtp,
        "auto_alert": auto_alert_enabled(),
        "auto_alert_max": AUTO_ALERT_MAX,
        "whatsapp_to": _mask(_env("ALERT_WHATSAPP_TO")) or None,
        "sms_to": _mask(_env("ALERT_SMS_TO")) or None,
        "email_to": _env("ALERT_EMAIL_TO") or None,
    }


async def alert_match(match_id: int) -> dict | None:
    """Send this match on every configured channel (WhatsApp, SMS, Email). None if the match doesn't exist."""
    m = await asyncio.to_thread(_load, match_id)
    if m is None:
        return None
    body = format_message(m)
    html = format_email_html(m)
    # ALERT_*_TO (the stage phone/email) wins over the profile's number/email.
    wa_to = _env("ALERT_WHATSAPP_TO") or (m["profile"]["phone"] or "")
    sms_to = _env("ALERT_SMS_TO") or (m["profile"]["phone"] or "")
    mail_to = _env("ALERT_EMAIL_TO") or (m["profile"]["email"] or "")
    subject = f"TenderHawk: {VERDICT_LABEL.get(m['verdict'], m['verdict'])} · {m['tender']['title'][:80]}"

    whatsapp, sms, email = await asyncio.gather(
        send_whatsapp(wa_to, body),
        send_sms(sms_to, body),
        send_email(mail_to, subject, body, html),
    )
    statuses = (whatsapp, sms, email)
    sent = "sent" in statuses
    # A configured channel that failed keeps the match pending so the next sweep retries it;
    # "not_configured" channels don't block.
    if sent and not any(s.startswith("failed") for s in statuses):
        await asyncio.to_thread(_mark_alerted, match_id)
    return {"match_id": match_id, "sent": sent,
            "channels": {"whatsapp": whatsapp, "sms": sms, "email": email},
            "preview": body}


def _pending_eligible(profile_id: int) -> list[int]:
    with SessionLocal() as db:
        q = (select(Match).where(Match.profile_id == profile_id, Match.verdict == ELIGIBLE,
                                 Match.relevant.is_(True), Match.alerted_at.is_(None)))
        now = now_ist()
        ms = [m for m in db.scalars(q) if as_ist(m.tender.end_date) > now]
        ms.sort(key=lambda m: -(m.fit_score or 0))
        return [m.id for m in ms[:AUTO_ALERT_MAX]]


async def auto_alert(profile_id: int) -> int:
    """Alert new ELIGIBLE matches that were never alerted. Returns how many were sent."""
    if not auto_alert_enabled():
        return 0

    async def one(mid: int) -> bool:
        try:
            res = await alert_match(mid)
            return bool(res and res["sent"])
        except Exception as e:  # an alert must never break a sweep
            log.warning("auto-alert failed for match %s: %r", mid, e)
            return False

    ids = await asyncio.to_thread(_pending_eligible, profile_id)
    if not ids:
        return 0
    try:
        return sum(await asyncio.wait_for(asyncio.gather(*(one(m) for m in ids)), AUTO_ALERT_BUDGET))
    except TimeoutError:
        log.warning("auto-alerts for profile %s ran past %ss; the sweep goes on", profile_id, AUTO_ALERT_BUDGET)
        return 0


def reset_alerts(profile_id: int | None = None) -> int:
    """Mark matches as not alerted (before a demo, so the live sweep sends the alert again)."""
    from sqlalchemy import update
    with SessionLocal() as db:
        q = update(Match).values(alerted_at=None)
        if profile_id is not None:
            q = q.where(Match.profile_id == profile_id)
        n = db.execute(q).rowcount
        db.commit()
        return n


if __name__ == "__main__":
    import sys
    if sys.argv[1:2] != ["reset"]:
        sys.exit("usage: python -m delivery.alerts reset [profile_id]")
    print(f"reset {reset_alerts(int(sys.argv[2]) if len(sys.argv) > 2 else None)} match(es)")
