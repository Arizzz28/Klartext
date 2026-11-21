"""Sends verification codes by email.

Three ways, tried in this order:
1. Brevo web API  (BREVO_API_KEY + BREVO_SENDER set)  -> works on Render's free plan (HTTPS)
2. SMTP           (SMTP_HOST set)                      -> blocked on Render's free plan
3. nothing        -> the code only appears in the log (development)

This file is called mailer.py and NOT email.py on purpose:
Python already has a built-in package called "email".
"""
import json
import smtplib
import urllib.error
import urllib.request
from email.message import EmailMessage

import config

BREVO_URL = "https://api.brevo.com/v3/smtp/email"


def _subject_and_text(code):
    subject = "Your Chatisfying code"
    text = (f"Your verification code is {code}\n\n"
            f"It is valid for {config.CODE_TTL // 60} minutes. "
            "If you did not sign up, ignore this email.")
    return subject, text


def _send_with_brevo(to_address, code):
    subject, text = _subject_and_text(code)
    payload = {
        "sender": {"name": "Chatisfying", "email": config.BREVO_SENDER},
        "to": [{"email": to_address}],
        "subject": subject,
        "textContent": text,
    }
    request = urllib.request.Request(
        BREVO_URL, data=json.dumps(payload).encode("utf-8"), method="POST",
        headers={"api-key": config.BREVO_API_KEY, "accept": "application/json",
                 "content-type": "application/json"})
    print("[MAILER] Sending email via Brevo API", flush=True)
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            print(f"[MAILER] Brevo accepted the email (HTTP {response.status})", flush=True)
    except urllib.error.HTTPError as e:
        # Brevo explains the problem in the body (e.g. "sender not valid"). It never contains our key.
        body = e.read().decode("utf-8", "replace")[:300]
        print(f"[MAILER] Brevo rejected the email: HTTP {e.code} {body}", flush=True)


def _send_with_smtp(to_address, code):
    subject, text = _subject_and_text(code)
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = config.SMTP_FROM
    msg["To"] = to_address
    msg.set_content(text)
    print(f"[MAILER] Sending email via SMTP {config.SMTP_HOST}:{config.SMTP_PORT}", flush=True)
    with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT, timeout=15) as smtp:
        smtp.starttls()
        if config.SMTP_USER:
            smtp.login(config.SMTP_USER, config.SMTP_PASSWORD)
        smtp.send_message(msg)
    print("[MAILER] Email sent via SMTP", flush=True)


def send_verification_code(to_address, code):
    # DEBUG PHASE ONLY: the code is ALWAYS printed, before anything can fail.
    # Remove this print before real production use, otherwise everyone with log access can read codes!
    print(f"[MAILER] Verification code: {code}", flush=True)

    try:
        if config.BREVO_API_KEY and config.BREVO_SENDER:
            _send_with_brevo(to_address, code)
        elif config.SMTP_HOST:
            _send_with_smtp(to_address, code)
        else:
            print("[MAILER] No email provider configured, no email sent", flush=True)
    except Exception as e:
        # Only error type and message, never credentials. The code was already printed above.
        print(f"[MAILER] Email sending failed: {type(e).__name__}: {e}", flush=True)
