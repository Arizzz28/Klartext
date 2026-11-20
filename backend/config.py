"""Central backend configuration (values come from .env / environment variables)."""
import os
import secrets
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

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
ALLOWED_ORIGINS = [o.strip() for o in os.environ.get(
    "ALLOWED_ORIGINS", "http://localhost:8000,http://127.0.0.1:8000").split(",") if o.strip()]

SMTP_HOST = os.environ.get("SMTP_HOST", "").strip()
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER = os.environ.get("SMTP_USER", "").strip()
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
SMTP_FROM = os.environ.get("SMTP_FROM", "Chatisfying <no-reply@example.com>")

TOKEN_TTL = 7 * 24 * 3600      # login stays valid for 7 days
CODE_TTL = 10 * 60             # verification code valid for 10 minutes
MAX_CODE_ATTEMPTS = 5
MAX_MESSAGE_LENGTH = 2000
