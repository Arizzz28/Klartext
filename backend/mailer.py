"""Sends verification codes by email.

This file is called mailer.py and NOT email.py on purpose:
Python already has a built-in package called "email".
"""

import smtplib
from email.message import EmailMessage

import config


def send_verification_code(to_address, code):
    # DEBUG PHASE ONLY: the code is ALWAYS printed, before anything can fail.
    # Remove this print (or guard it with an env variable) before real production use!
    print(f"[MAILER] Verification code: {code}", flush=True)

    if not config.SMTP_HOST:
        print("[MAILER] SMTP not configured, no email sent", flush=True)
        return

    try:
        msg = EmailMessage()
        msg["Subject"] = "Your Chatisfying code"
        msg["From"] = config.SMTP_FROM
        msg["To"] = to_address
        msg.set_content(
            f"Your verification code is {code}\n\n"
            f"It is valid for {config.CODE_TTL // 60} minutes. "
            "If you did not sign up, ignore this email."
        )

        print(f"[MAILER] Sending email via {config.SMTP_HOST}:{config.SMTP_PORT}", flush=True)
        with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT, timeout=15) as smtp:
            smtp.starttls()
            if config.SMTP_USER:
                smtp.login(config.SMTP_USER, config.SMTP_PASSWORD)
            smtp.send_message(msg)
        print("[MAILER] Email sent", flush=True)

    except Exception as e:
        # Only the error type and message, never credentials. The code was already printed above.
        print(f"[MAILER] Email sending failed: {type(e).__name__}: {e}", flush=True)
