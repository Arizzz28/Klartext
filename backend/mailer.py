
"""Sends verification codes by email.

This file is called mailer.py and NOT email.py on purpose:
Python already has a built-in package called "email".
"""
import smtplib
from email.message import EmailMessage

import config


def send_verification_code(to_address, code):
    # ALWAYS print the verification code to the terminal
    print(f"\n{'=' * 45}", flush=True)
    print(f"[CHATISFYING] Verification code", flush=True)
    print(f"Email: {to_address}", flush=True)
    print(f"CODE: {code}", flush=True)
    print(f"{'=' * 45}\n", flush=True)

    # No SMTP configured: terminal output is enough
    if not config.SMTP_HOST:
        print("[CHATISFYING] SMTP not configured. Email skipped.", flush=True)
        return

    # SMTP configured: attempt to send email
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

        with smtplib.SMTP(
            config.SMTP_HOST,
            config.SMTP_PORT,
            timeout=15
        ) as smtp:
            smtp.starttls()

            if config.SMTP_USER:
                smtp.login(config.SMTP_USER, config.SMTP_PASSWORD)

            smtp.send_message(msg)

        print("[CHATISFYING] Email successfully sent.", flush=True)

    except Exception as e:
        print(f"[CHATISFYING] Email sending failed: {e}", flush=True)
