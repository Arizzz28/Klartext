"""Versions of the legal texts and the consent check.

When you change the Terms or the Privacy Policy in a way that matters, raise the version here.
Everybody then has to accept again before they can use the app (the server enforces it, see security.py).
The texts themselves are the pages frontend/terms.html and frontend/privacy.html.
"""
import time

TERMS_VERSION = "2026-11-25"
PRIVACY_VERSION = "2026-11-25"


def consent_ok(user):
    c = user.get("consent") or {}
    return c.get("terms") == TERMS_VERSION and c.get("privacy") == PRIVACY_VERSION


def consent_record():
    return {"terms": TERMS_VERSION, "privacy": PRIVACY_VERSION, "at": time.time()}
