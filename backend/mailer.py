"""Sends verification codes by email.

This file is called mailer.py and NOT email.py on purpose: Python already has a built-in
package called "email" (used by smtplib). A file named email.py next to app.py would hide it
and break the import.
"""
import smtplib
from email.message import EmailMessage

import config


def send_verification_code(to_address, code):
    if not config.SMTP_HOST:
        print(f"[DEV MODE] Verification code for {to_address}: {code}")
        return

    msg = EmailMessage()
    msg["Subject"] = "Your Chatisfying code"
    msg["From"] = config.SMTP_FROM
    msg["To"] = to_address
    msg.set_content(
        f"Your verification code is {code}\n\n"
        f"It is valid for {config.CODE_TTL // 60} minutes. If you did not sign up, ignore this email."
    )
    with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT, timeout=15) as smtp:
        smtp.starttls()
        if config.SMTP_USER:
            smtp.login(config.SMTP_USER, config.SMTP_PASSWORD)
        smtp.send_message(msg)
