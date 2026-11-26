"""Relational tables for everything that grows: messages, reactions, attachments, reports, audit log.

Same idea as storage.py: PostgreSQL when DATABASE_URL is set (Neon), otherwise a local SQLite file
(backend/data/chatisfying.db) so you can still run everything on your own PC.
The SQL in this project is written so that it works on both. Placeholders are written as "?".
"""
import sqlite3
import threading
from contextlib import contextmanager

import config
import storage

_pg = storage.get_pool()
_lock = threading.RLock()
_lite = None
if _pg is None:
    _lite = sqlite3.connect(config.DATA_DIR / "chatisfying.db", check_same_thread=False, isolation_level=None)
    _lite.row_factory = sqlite3.Row
    _lite.execute("PRAGMA journal_mode=WAL")


class _Tx:
    """One open database transaction. Everything done through it is saved together or not at all."""

    def __init__(self, conn):
        self._conn = conn

    def _run(self, sql, params):
        if _pg:
            # psycopg uses % for its own placeholders, so a literal % (e.g. in LIKE 'abc%') must be doubled.
            return self._conn.execute(sql.replace("%", "%%").replace("?", "%s"), tuple(params))
        return self._conn.execute(sql, tuple(params))

    def query(self, sql, params=()):
        cur = self._run(sql, params)
        if _pg:
            if cur.description is None:
                return []
            cols = [d.name for d in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]
        return [dict(r) for r in cur.fetchall()]

    def execute(self, sql, params=()):
        return self._run(sql, params).rowcount


@contextmanager
def transaction():
    if _pg:
        with _pg.connection() as conn:          # commits on success, rolls back on an exception
            yield _Tx(conn)
    else:
        with _lock:
            _lite.execute("BEGIN")
            try:
                yield _Tx(_lite)
                _lite.execute("COMMIT")
            except BaseException:
                _lite.execute("ROLLBACK")
                raise


def query(sql, params=()):
    with transaction() as tx:
        return tx.query(sql, params)


def execute(sql, params=()):
    with transaction() as tx:
        return tx.execute(sql, params)


def placeholders(items):
    """'?,?,?' for an IN (...) list."""
    return ",".join("?" * len(items))


def add_column(table, column, decl):
    """Adds a column to an existing table if it is not there yet (safe to call on every start)."""
    if _pg:
        execute(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column} {decl}")
    else:
        have = [r["name"] for r in query(f"PRAGMA table_info({table})")]
        if column not in have:
            execute(f"ALTER TABLE {table} ADD COLUMN {column} {decl}")


def init():
    pk = "BIGSERIAL PRIMARY KEY" if _pg else "INTEGER PRIMARY KEY AUTOINCREMENT"
    statements = [
        f"""CREATE TABLE IF NOT EXISTS messages (
            id {pk}, chat_type TEXT NOT NULL, chat_key TEXT NOT NULL, sender TEXT NOT NULL,
            body TEXT NOT NULL DEFAULT '', reply_to BIGINT, created DOUBLE PRECISION NOT NULL,
            edited DOUBLE PRECISION, deleted INTEGER NOT NULL DEFAULT 0, is_system INTEGER NOT NULL DEFAULT 0)""",
        "CREATE INDEX IF NOT EXISTS idx_messages_chat ON messages (chat_type, chat_key, id)",
        """CREATE TABLE IF NOT EXISTS reactions (
            message_id BIGINT NOT NULL, username TEXT NOT NULL, emoji TEXT NOT NULL,
            created DOUBLE PRECISION NOT NULL, PRIMARY KEY (message_id, username, emoji))""",
        """CREATE TABLE IF NOT EXISTS attachments (
            id TEXT PRIMARY KEY, username TEXT NOT NULL, kind TEXT NOT NULL, message_id BIGINT,
            chat_type TEXT, chat_key TEXT, storage_key TEXT NOT NULL, name TEXT NOT NULL, mime TEXT NOT NULL,
            size BIGINT NOT NULL DEFAULT 0, status TEXT NOT NULL DEFAULT 'pending', created DOUBLE PRECISION NOT NULL)""",
        "CREATE INDEX IF NOT EXISTS idx_attachments_message ON attachments (message_id)",
        f"""CREATE TABLE IF NOT EXISTS reports (
            id {pk}, message_id BIGINT, reporter TEXT NOT NULL, reason TEXT NOT NULL DEFAULT '',
            snapshot TEXT NOT NULL, created DOUBLE PRECISION NOT NULL, status TEXT NOT NULL DEFAULT 'open',
            handled_by TEXT, handled_at DOUBLE PRECISION)""",
        f"""CREATE TABLE IF NOT EXISTS audit_log (
            id {pk}, ts DOUBLE PRECISION NOT NULL, actor TEXT NOT NULL, action TEXT NOT NULL,
            target TEXT NOT NULL DEFAULT '', details TEXT NOT NULL DEFAULT '')""",
        """CREATE TABLE IF NOT EXISTS chat_clears (
            username TEXT NOT NULL, chat_type TEXT NOT NULL, chat_key TEXT NOT NULL,
            cleared_before BIGINT NOT NULL, PRIMARY KEY (username, chat_type, chat_key))""",
        """CREATE TABLE IF NOT EXISTS chat_settings (
            username TEXT NOT NULL, chat_type TEXT NOT NULL, chat_key TEXT NOT NULL,
            background TEXT NOT NULL DEFAULT '', dim INTEGER NOT NULL DEFAULT 30,
            PRIMARY KEY (username, chat_type, chat_key))""",

        # ------------------------------------------------------------------ Version 3
        f"""CREATE TABLE IF NOT EXISTS perm_requests (
            id {pk}, from_user TEXT NOT NULL, perm TEXT NOT NULL, text TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'open', created DOUBLE PRECISION NOT NULL,
            decided_by TEXT, decided_at DOUBLE PRECISION, answer TEXT NOT NULL DEFAULT '')""",
        f"""CREATE TABLE IF NOT EXISTS offers (
            id {pk}, username TEXT NOT NULL, text TEXT NOT NULL, created DOUBLE PRECISION NOT NULL,
            status TEXT NOT NULL DEFAULT 'open', decided_by TEXT, decided_at DOUBLE PRECISION,
            answer TEXT NOT NULL DEFAULT '', reward TEXT NOT NULL DEFAULT '')""",
        f"""CREATE TABLE IF NOT EXISTS notifications (
            id {pk}, username TEXT NOT NULL, kind TEXT NOT NULL, text TEXT NOT NULL,
            link TEXT NOT NULL DEFAULT '', created DOUBLE PRECISION NOT NULL, is_read INTEGER NOT NULL DEFAULT 0)""",
        "CREATE INDEX IF NOT EXISTS idx_notifications_user ON notifications (username, is_read, id)",
        """CREATE TABLE IF NOT EXISTS read_state (
            username TEXT NOT NULL, chat_type TEXT NOT NULL, chat_key TEXT NOT NULL, last_id BIGINT NOT NULL DEFAULT 0,
            PRIMARY KEY (username, chat_type, chat_key))""",
        f"""CREATE TABLE IF NOT EXISTS notes (
            id {pk}, username TEXT NOT NULL, title TEXT NOT NULL DEFAULT '', body TEXT NOT NULL DEFAULT '',
            created DOUBLE PRECISION NOT NULL, updated DOUBLE PRECISION NOT NULL)""",
        f"""CREATE TABLE IF NOT EXISTS events (
            id {pk}, owner TEXT NOT NULL, title TEXT NOT NULL, note TEXT NOT NULL DEFAULT '',
            start_ts DOUBLE PRECISION NOT NULL, end_ts DOUBLE PRECISION, created DOUBLE PRECISION NOT NULL)""",
        "CREATE TABLE IF NOT EXISTS event_shares (event_id BIGINT NOT NULL, username TEXT NOT NULL, PRIMARY KEY (event_id, username))",
        f"""CREATE TABLE IF NOT EXISTS tasks (
            id {pk}, owner TEXT NOT NULL, title TEXT NOT NULL, done INTEGER NOT NULL DEFAULT 0,
            due DOUBLE PRECISION, created DOUBLE PRECISION NOT NULL)""",
        "CREATE TABLE IF NOT EXISTS task_shares (task_id BIGINT NOT NULL, username TEXT NOT NULL, PRIMARY KEY (task_id, username))",
        f"""CREATE TABLE IF NOT EXISTS playlists (
            id {pk}, owner TEXT NOT NULL, name TEXT NOT NULL, visibility TEXT NOT NULL DEFAULT 'private',
            created DOUBLE PRECISION NOT NULL)""",
        f"""CREATE TABLE IF NOT EXISTS playlist_tracks (
            id {pk}, playlist_id BIGINT NOT NULL, title TEXT NOT NULL, url TEXT NOT NULL,
            added_by TEXT NOT NULL, created DOUBLE PRECISION NOT NULL)""",
        f"""CREATE TABLE IF NOT EXISTS forum_posts (
            id {pk}, author TEXT NOT NULL, title TEXT NOT NULL, body TEXT NOT NULL DEFAULT '',
            created DOUBLE PRECISION NOT NULL, status TEXT NOT NULL DEFAULT 'open', pinned INTEGER NOT NULL DEFAULT 0)""",
        f"""CREATE TABLE IF NOT EXISTS forum_comments (
            id {pk}, post_id BIGINT NOT NULL, author TEXT NOT NULL, body TEXT NOT NULL, created DOUBLE PRECISION NOT NULL)""",
        "CREATE TABLE IF NOT EXISTS forum_votes (post_id BIGINT NOT NULL, username TEXT NOT NULL, PRIMARY KEY (post_id, username))",
        """CREATE TABLE IF NOT EXISTS releases (
            id TEXT PRIMARY KEY, title TEXT NOT NULL, body TEXT NOT NULL DEFAULT '',
            created DOUBLE PRECISION NOT NULL, created_by TEXT NOT NULL)""",
        "CREATE TABLE IF NOT EXISTS release_seen (username TEXT NOT NULL, release_id TEXT NOT NULL, PRIMARY KEY (username, release_id))",
        """CREATE TABLE IF NOT EXISTS profile_visits (
            visited TEXT NOT NULL, visitor TEXT NOT NULL, ts DOUBLE PRECISION NOT NULL)""",
        "CREATE INDEX IF NOT EXISTS idx_visits ON profile_visits (visited, ts)",
        f"""CREATE TABLE IF NOT EXISTS login_log (
            id {pk}, username TEXT NOT NULL, ts DOUBLE PRECISION NOT NULL, ok INTEGER NOT NULL DEFAULT 1)""",
        f"""CREATE TABLE IF NOT EXISTS ad_items (
            id {pk}, kind TEXT NOT NULL, title TEXT NOT NULL, url TEXT NOT NULL DEFAULT '',
            body TEXT NOT NULL DEFAULT '', active INTEGER NOT NULL DEFAULT 1, created DOUBLE PRECISION NOT NULL)""",
        "CREATE TABLE IF NOT EXISTS ai_usage (username TEXT NOT NULL, day TEXT NOT NULL, n INTEGER NOT NULL DEFAULT 0, PRIMARY KEY (username, day))",
        "CREATE TABLE IF NOT EXISTS wallets (username TEXT PRIMARY KEY, coins BIGINT NOT NULL DEFAULT 0)",
        f"""CREATE TABLE IF NOT EXISTS coin_log (
            id {pk}, username TEXT NOT NULL, delta BIGINT NOT NULL, reason TEXT NOT NULL,
            actor TEXT NOT NULL DEFAULT '', ts DOUBLE PRECISION NOT NULL)""",
        f"""CREATE TABLE IF NOT EXISTS missions (
            id {pk}, title TEXT NOT NULL, kind TEXT NOT NULL, target INTEGER NOT NULL, period TEXT NOT NULL,
            reward INTEGER NOT NULL, active INTEGER NOT NULL DEFAULT 1)""",
        "CREATE TABLE IF NOT EXISTS mission_claims (username TEXT NOT NULL, mission_id BIGINT NOT NULL, period_key TEXT NOT NULL, ts DOUBLE PRECISION NOT NULL, PRIMARY KEY (username, mission_id, period_key))",
        """CREATE TABLE IF NOT EXISTS push_subscriptions (
            endpoint TEXT PRIMARY KEY, username TEXT NOT NULL, p256dh TEXT NOT NULL, auth TEXT NOT NULL,
            created DOUBLE PRECISION NOT NULL)""",
        f"""CREATE TABLE IF NOT EXISTS custom_tabs (
            id {pk}, username TEXT NOT NULL, title TEXT NOT NULL, kind TEXT NOT NULL, content TEXT NOT NULL DEFAULT '',
            created DOUBLE PRECISION NOT NULL)""",
        "CREATE TABLE IF NOT EXISTS game_scores (game TEXT NOT NULL, username TEXT NOT NULL, best BIGINT NOT NULL DEFAULT 0, plays BIGINT NOT NULL DEFAULT 0, PRIMARY KEY (game, username))",
    ]
    statements += V4_STATEMENTS(pk)
    for statement in statements:
        execute(statement)
    # columns added after Version 3 (a database from an older version gets them here, nothing is lost)
    add_column("missions", "rarity", "TEXT NOT NULL DEFAULT 'common'")
    add_column("missions", "min_rank", "TEXT NOT NULL DEFAULT ''")
    add_column("offers", "kind", "TEXT NOT NULL DEFAULT 'offer'")


def V4_STATEMENTS(pk):
    """Tables added in Version 4 (random missions, translations, games, ...)."""
    return [
        "CREATE TABLE IF NOT EXISTS mission_draws (username TEXT NOT NULL, period TEXT NOT NULL, period_key TEXT NOT NULL, "
        "mission_id BIGINT NOT NULL, PRIMARY KEY (username, period, period_key, mission_id))",
        f"""CREATE TABLE IF NOT EXISTS translation_items (
            id {pk}, source TEXT NOT NULL, hint TEXT NOT NULL DEFAULT '', active INTEGER NOT NULL DEFAULT 1)""",
        f"""CREATE TABLE IF NOT EXISTS translation_tasks (
            id {pk}, username TEXT NOT NULL, mission_id BIGINT NOT NULL, period_key TEXT NOT NULL, item_id BIGINT NOT NULL,
            answer TEXT NOT NULL DEFAULT '', status TEXT NOT NULL DEFAULT 'open', created DOUBLE PRECISION NOT NULL,
            submitted DOUBLE PRECISION, reviewed_by TEXT, reviewed_at DOUBLE PRECISION, note TEXT NOT NULL DEFAULT '')""",
        "CREATE INDEX IF NOT EXISTS idx_transtasks ON translation_tasks (username, mission_id, period_key)",
        f"""CREATE TABLE IF NOT EXISTS matches (
            id {pk}, game TEXT NOT NULL, p0 TEXT NOT NULL, p1 TEXT NOT NULL, level TEXT NOT NULL DEFAULT 'easy',
            status TEXT NOT NULL DEFAULT 'invited', state TEXT NOT NULL DEFAULT '{{}}', rev INTEGER NOT NULL DEFAULT 0,
            created DOUBLE PRECISION NOT NULL, updated DOUBLE PRECISION NOT NULL, winner TEXT NOT NULL DEFAULT '')""",
        "CREATE INDEX IF NOT EXISTS idx_matches_p0 ON matches (p0, status)",
        "CREATE INDEX IF NOT EXISTS idx_matches_p1 ON matches (p1, status)",
        "CREATE TABLE IF NOT EXISTS elo (game TEXT NOT NULL, username TEXT NOT NULL, rating INTEGER NOT NULL DEFAULT 1000, games INTEGER NOT NULL DEFAULT 0, PRIMARY KEY (game, username))",
        "CREATE TABLE IF NOT EXISTS pc_status (id INTEGER PRIMARY KEY, url TEXT NOT NULL DEFAULT '', ts DOUBLE PRECISION NOT NULL DEFAULT 0)",
        "CREATE TABLE IF NOT EXISTS streaks (username TEXT PRIMARY KEY, last_day TEXT NOT NULL DEFAULT '', streak INTEGER NOT NULL DEFAULT 0, best INTEGER NOT NULL DEFAULT 0)",
        f"CREATE TABLE IF NOT EXISTS polls (id {pk}, author TEXT NOT NULL, question TEXT NOT NULL, options TEXT NOT NULL, created DOUBLE PRECISION NOT NULL, closed INTEGER NOT NULL DEFAULT 0)",
        "CREATE TABLE IF NOT EXISTS poll_votes (poll_id INTEGER NOT NULL, username TEXT NOT NULL, choice INTEGER NOT NULL, PRIMARY KEY (poll_id, username))",
        "CREATE TABLE IF NOT EXISTS prank_optin (username TEXT PRIMARY KEY, enabled INTEGER NOT NULL DEFAULT 0)",
        f"CREATE TABLE IF NOT EXISTS prank_inbox (id {pk}, to_user TEXT NOT NULL, from_user TEXT NOT NULL, kind TEXT NOT NULL, created DOUBLE PRECISION NOT NULL, seen INTEGER NOT NULL DEFAULT 0)",
        "CREATE INDEX IF NOT EXISTS idx_prank_to ON prank_inbox (to_user, seen)",
        "CREATE TABLE IF NOT EXISTS game_points (username TEXT NOT NULL, game TEXT NOT NULL, points INTEGER NOT NULL DEFAULT 0, PRIMARY KEY (username, game))",
    ]
