"""Central JSON storage.

Safety measures:
- one process-wide lock, so two requests never write at the same time
- atomic writes (write to a temp file, then os.replace) so a crash cannot leave a half-written file
- a corrupt file is moved aside instead of crashing the server

Run the server as ONE process (threads are fine), because the lock only exists inside one process.
"""
import copy
import json
import os
import tempfile
import threading
from contextlib import contextmanager

import config

_lock = threading.RLock()

DEFAULTS = {
    "users": {},            # key: lowercase username
    "whitelist": [],        # lowercase usernames that may register
    "messages": [],         # private messages
    "groups": {},           # key: group id
    "group_messages": [],
    "invitations": [],
    "verification": {},     # key: lowercase username
}


def _path(name):
    return config.DATA_DIR / f"{name}.json"


def read(name):
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


def write(name, data):
    with _lock:
        fd, tmp = tempfile.mkstemp(dir=config.DATA_DIR, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(tmp, _path(name))
        finally:
            if os.path.exists(tmp):
                os.remove(tmp)


@contextmanager
def transaction(*names):
    """Read several files, let the caller change them, save them all.
    If the caller raises an error, NOTHING is saved."""
    with _lock:
        db = {n: read(n) for n in names}
        yield db
        for n in names:
            write(n, db[n])


def ensure_files():
    for name in DEFAULTS:
        if not _path(name).exists():
            write(name, DEFAULTS[name])


def next_id(items):
    return (items[-1]["id"] + 1) if items else 1
