"""Test set-up: a throw-away data folder, so the tests never touch real data."""
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ["DATABASE_URL"] = os.environ.get("TEST_DATABASE_URL", "")
os.environ["OWNER_USERNAME"] = "Boss"
os.environ["ADMIN_USERNAME"] = "Boss"
os.environ["VAPID_PUBLIC_KEY"] = "BHQpgQdbf8u71JEOaJ56aiILM39uEEXfTNmCOtJz_Lw1cWHhuZea8y1Y-SSuVCH8X2sAofgyscCNBFgh9wr9gWs"
os.environ["VAPID_PRIVATE_KEY"] = "2mucAib9LHlgnaL5yTvDWX5yRCI-ij_uALyidQKS9Ns"
os.environ["GEMINI_API_KEY"] = "fake-key-for-tests"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config  # noqa: E402

_tmp = Path(tempfile.mkdtemp(prefix="chatisfying-test-"))
config.DATA_DIR = _tmp

import pytest  # noqa: E402

import app as app_module  # noqa: E402
import perms  # noqa: E402
import security  # noqa: E402
import storage  # noqa: E402
import time  # noqa: E402


@pytest.fixture(scope="session")
def client():
    return app_module.app.test_client()


@pytest.fixture(scope="session")
def make_user():
    """make_user("anna", rank="basic") -> (username, auth header). Creates an active, consented account directly."""
    import legalconf

    def _make(name, rank="basic", consent=True, **extra):
        with storage.transaction("users") as db:
            db["users"][name.lower()] = {
                "username": name, "email": f"{name.lower()}@example.com", "password_hash": security.hash_password("password123"),
                "display_name": name, "avatar": "", "rank": rank, "status": "active", "token_version": 0,
                "created": time.time(), **({"consent": legalconf.consent_record()} if consent else {}), **extra}
            user = db["users"][name.lower()]
        return {"Authorization": "Bearer " + security.create_token(user)}
    return _make


@pytest.fixture(scope="session")
def owner(make_user):
    return make_user("Boss", rank="owner")
