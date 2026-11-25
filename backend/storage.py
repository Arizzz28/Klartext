"""Central data storage.

Two modes, chosen automatically:
- DATABASE_URL is set  -> PostgreSQL (e.g. Neon). Data survives restarts, deploys and sleep.
- DATABASE_URL is empty -> JSON files in backend/data (handy on your own PC).

Both modes offer the same functions, so no other file has to know which one is active:
    read(name), write(name, data), transaction(*names), ensure_files(), next_id(items)

Why PostgreSQL here? Render's free plan deletes local files whenever the service restarts or
falls asleep. A database outside of Render keeps the data.

How the database is used: one table "kv" with one row per former JSON file
(name = "users", "groups", ...; data = the same JSON as before, stored as JSONB).
"""
import copy
import json
import os
import tempfile
import threading
from contextlib import contextmanager

import config

DEFAULTS = {
    "users": {},            # key: lowercase username
    "whitelist": [],        # lowercase usernames that may register
    "messages": [],         # private messages
    "groups": {},           # key: group id
    "group_messages": [],
    "invitations": [],
    "verification": {},     # key: lowercase username
    "settings": {},         # global settings changed by admins (see appsettings.py)
    "ranks": {},            # key: rank id (see perms.py)
}

# =====================================================================================
# PostgreSQL mode
# =====================================================================================
_pool = None

if config.DATABASE_URL:
    from psycopg.types.json import Jsonb
    from psycopg_pool import ConnectionPool

    try:
        _pool = ConnectionPool(
            conninfo=config.DATABASE_URL,
            min_size=1, max_size=20, timeout=30,
            max_idle=120, max_lifetime=1800,
            check=ConnectionPool.check_connection,       # drops connections the server has closed
            kwargs={"prepare_threshold": None},          # needed for poolers like Neon's PgBouncer
            open=False,
        )
        _pool.open(wait=True, timeout=30)
    except Exception as e:                               # never print the URL: it contains the password
        print(f"[STORAGE] Cannot connect to PostgreSQL: {type(e).__name__}", flush=True)
        raise
    print("[STORAGE] Using PostgreSQL", flush=True)
else:
    print("[STORAGE] Using JSON files (no DATABASE_URL set)", flush=True)

# =====================================================================================
# JSON-file mode
# =====================================================================================
# One process-wide lock, atomic writes (temp file + os.replace) and a corrupt file is moved aside.
# Run as ONE process: the lock only exists inside one process.
_lock = threading.RLock()


def _path(name):
    return config.DATA_DIR / f"{name}.json"


def _file_read(name):
    with _lock:
        path = _path(name)
        if not path.exists():
            return copy.deepcopy(DEFAULTS[name])
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except json.JSONDecodeError:
            os.replace(path, path.with_suffix(".corrupt.json"))
            return copy.deepcopy(DEFAULTS[name])


def _file_write(name, data):
    with _lock:
        fd, tmp = tempfile.mkstemp(dir=config.DATA_DIR, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(tmp, _path(name))
        finally:
            if os.path.exists(tmp):
                os.remove(tmp)


# =====================================================================================
# Public functions
# =====================================================================================
def read(name):
    if _pool is None:
        return _file_read(name)
    with _pool.connection() as conn:
        row = conn.execute("SELECT data FROM kv WHERE name = %s", (name,)).fetchone()
    return row[0] if row else copy.deepcopy(DEFAULTS[name])


def write(name, data):
    if _pool is None:
        return _file_write(name, data)
    with _pool.connection() as conn:
        conn.execute(
            "INSERT INTO kv (name, data) VALUES (%s, %s) "
            "ON CONFLICT (name) DO UPDATE SET data = EXCLUDED.data",
            (name, Jsonb(data)))


@contextmanager
def transaction(*names):
    """Read several data sets, let the caller change them, save them all.
    If the caller raises an error, NOTHING is saved."""
    if _pool is None:
        with _lock:
            db = {n: _file_read(n) for n in names}
            yield db
            for n in names:
                _file_write(n, db[n])
        return

    # PostgreSQL: a real database transaction. "FOR UPDATE" locks the rows, so a second request
    # that wants the same data has to wait until we are done (no lost updates).
    # Locking in sorted order prevents two requests from waiting for each other forever.
    # Leaving the "with" block normally commits, an exception rolls everything back.
    with _pool.connection() as conn:
        db = {}
        for n in sorted(set(names)):
            conn.execute("INSERT INTO kv (name, data) VALUES (%s, %s) ON CONFLICT (name) DO NOTHING",
                         (n, Jsonb(DEFAULTS[n])))
            db[n] = conn.execute("SELECT data FROM kv WHERE name = %s FOR UPDATE", (n,)).fetchone()[0]
        yield db
        for n, data in db.items():
            conn.execute("UPDATE kv SET data = %s WHERE name = %s", (Jsonb(data), n))


def get_pool():
    """The PostgreSQL connection pool, or None in JSON-file mode (used by db.py)."""
    return _pool


def ensure_files():
    """Create the table / files with empty defaults on first start."""
    if _pool is None:
        for name in DEFAULTS:
            if not _path(name).exists():
                _file_write(name, DEFAULTS[name])
        return
    with _pool.connection() as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS kv (name text PRIMARY KEY, data jsonb NOT NULL)")
        for name, default in DEFAULTS.items():
            conn.execute("INSERT INTO kv (name, data) VALUES (%s, %s) ON CONFLICT (name) DO NOTHING",
                         (name, Jsonb(default)))


def next_id(items):
    return (items[-1]["id"] + 1) if items else 1
