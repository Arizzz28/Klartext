"""Central backend configuration (values come from .env / environment variables)."""
import os
import secrets
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

# PostgreSQL connection string (e.g. from Neon). Empty = use JSON files. It contains a password: never log it.
DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()

DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)


def _load_secret_key() -> str:
    key = os.environ.get("SECRET_KEY", "").strip()
    if key:
        return key
    # No key configured: create one once and keep it, so logins survive restarts.
    key_file = DATA_DIR / ".secret_key"
    if not key_file.exists():
        key_file.write_text(secrets.token_hex(32), encoding="utf-8")
    return key_file.read_text(encoding="utf-8").strip()


SECRET_KEY = _load_secret_key()

ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin").strip()
# The Owner is the top instance: all permissions, cannot be demoted, suspended or deleted.
# If OWNER_USERNAME is empty, ADMIN_USERNAME is used (so old setups keep working).
OWNER_USERNAME = os.environ.get("OWNER_USERNAME", "").strip() or ADMIN_USERNAME
ALLOWED_ORIGINS = [o.strip() for o in os.environ.get(
    "ALLOWED_ORIGINS", "http://localhost:8000,http://127.0.0.1:8000").split(",") if o.strip()]

# Email through the Brevo web API (works on Render's free plan, because it uses HTTPS instead of SMTP ports).
# BREVO_API_KEY is a secret. BREVO_SENDER must be a sender address you verified in Brevo.
BREVO_API_KEY = os.environ.get("BREVO_API_KEY", "").strip()
BREVO_SENDER = os.environ.get("BREVO_SENDER", "").strip()

SMTP_HOST = os.environ.get("SMTP_HOST", "").strip()
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER = os.environ.get("SMTP_USER", "").strip()
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
SMTP_FROM = os.environ.get("SMTP_FROM", "Chatisfying <no-reply@example.com>")

TOKEN_TTL = 7 * 24 * 3600      # login stays valid for 7 days
CODE_TTL = 10 * 60             # verification code valid for 10 minutes
MAX_CODE_ATTEMPTS = 5
MAX_MESSAGE_LENGTH = 2000

# Object storage for uploads (any S3-compatible service: Backblaze B2, Cloudflare R2, ...).
# All five values are secrets/settings from your provider. If one is empty, uploads are switched off.
S3_ENDPOINT_URL = os.environ.get("S3_ENDPOINT_URL", "").strip()
S3_REGION = os.environ.get("S3_REGION", "auto").strip() or "auto"
S3_BUCKET = os.environ.get("S3_BUCKET", "").strip()
S3_ACCESS_KEY_ID = os.environ.get("S3_ACCESS_KEY_ID", "").strip()
S3_SECRET_ACCESS_KEY = os.environ.get("S3_SECRET_ACCESS_KEY", "").strip()
UPLOAD_URL_TTL = 3 * 3600        # a prepared upload link works for 3 hours (big files need time)
DOWNLOAD_URL_TTL = 6 * 3600      # a download link works for 6 hours
HARD_MAX_UPLOAD_MB = 200         # nobody (not even an admin setting) can go above this

# Verification codes are only written to the log if you switch this on (debugging). Default: off,
# because everybody with access to the server log could otherwise read login codes.
DEBUG_LOG_CODES = os.environ.get("DEBUG_LOG_CODES", "").strip().lower() in ("1", "true", "yes")

# Google Gemini (AI tab). The key only ever lives here on the server, never in the frontend.
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash").strip()

# Web push (VAPID). Create the pair with:  python gen_vapid.py
VAPID_PUBLIC_KEY = os.environ.get("VAPID_PUBLIC_KEY", "").strip()
VAPID_PRIVATE_KEY = os.environ.get("VAPID_PRIVATE_KEY", "").strip()
VAPID_SUBJECT = os.environ.get("VAPID_SUBJECT", "").strip() or "mailto:" + (BREVO_SENDER or "owner@example.com")
