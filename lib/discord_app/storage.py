from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

from werkzeug.security import check_password_hash, generate_password_hash

from .security import KeyRing, new_token, token_hash


BROWSER_SESSION_VERSION = 2


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: Optional[datetime] = None) -> str:
    return (dt or utc_now()).isoformat()


SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS admins (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 1,
    failed_attempts INTEGER NOT NULL DEFAULT 0,
    locked_until TEXT,
    created_at TEXT NOT NULL,
    last_login_at TEXT
);

CREATE TABLE IF NOT EXISTS admin_sessions (
    token_hash TEXT PRIMARY KEY,
    admin_id INTEGER NOT NULL REFERENCES admins(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL
);


CREATE TABLE IF NOT EXISTS browser_sessions (
    token_hash TEXT PRIMARY KEY,
    auth_version INTEGER NOT NULL DEFAULT 1,
    user_id TEXT,
    email TEXT,
    username TEXT,
    global_name TEXT,
    email_confirmed INTEGER NOT NULL DEFAULT 1,
    verification_kind TEXT NOT NULL DEFAULT 'signup',
    role TEXT NOT NULL DEFAULT 'user',
    access_token_enc TEXT,
    refresh_token_enc TEXT,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS secure_settings (
    name TEXT PRIMARY KEY,
    value_enc TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    updated_by INTEGER REFERENCES admins(id)
);

CREATE TABLE IF NOT EXISTS audit_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    occurred_at TEXT NOT NULL,
    actor_type TEXT NOT NULL,
    actor_id TEXT,
    action TEXT NOT NULL,
    outcome TEXT NOT NULL,
    target TEXT,
    remote_addr TEXT,
    details_json TEXT NOT NULL,
    prev_hash TEXT NOT NULL,
    event_hash TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_audit_occurred_at ON audit_events(occurred_at DESC);
CREATE INDEX IF NOT EXISTS idx_browser_sessions_expires ON browser_sessions(expires_at);
CREATE INDEX IF NOT EXISTS idx_browser_sessions_user ON browser_sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_admin_sessions_expires ON admin_sessions(expires_at);

CREATE TABLE IF NOT EXISTS rate_limit_events (
    bucket TEXT NOT NULL,
    occurred_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_rate_limit_bucket_time ON rate_limit_events(bucket, occurred_at);
"""


class ControlStore:
    def __init__(self, db_path: Path, keys: KeyRing):
        self.db_path = db_path
        self.keys = keys
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.init_schema()

    @contextmanager
    def connect(self):
        conn = sqlite3.connect(self.db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def init_schema(self) -> None:
        with self.connect() as conn:
            conn.executescript(SCHEMA)
            # Existing installations predate the explicit browser-session version.
            # Version 2 intentionally invalidates pre-v3.9 browser sessions so
            # every authenticated browser must establish the paired-cookie contract.
            columns = {str(row[1]) for row in conn.execute("PRAGMA table_info(browser_sessions)").fetchall()}
            if "auth_version" not in columns:
                conn.execute("ALTER TABLE browser_sessions ADD COLUMN auth_version INTEGER NOT NULL DEFAULT 1")
            if "role" not in columns:
                conn.execute("ALTER TABLE browser_sessions ADD COLUMN role TEXT NOT NULL DEFAULT 'user'")
            if "username" not in columns:
                conn.execute("ALTER TABLE browser_sessions ADD COLUMN username TEXT")
            if "global_name" not in columns:
                conn.execute("ALTER TABLE browser_sessions ADD COLUMN global_name TEXT")
            if "email_confirmed" not in columns:
                # Existing authenticated sessions predate the verification flag;
                # successful password/passkey sessions are treated as confirmed.
                conn.execute("ALTER TABLE browser_sessions ADD COLUMN email_confirmed INTEGER NOT NULL DEFAULT 1")
            if "verification_kind" not in columns:
                # Public sign-up sessions use the normal confirmation resend flow.
                # Server-side invite fallback sessions retain their invite kind so
                # the resend endpoint can use the matching provider operation.
                conn.execute("ALTER TABLE browser_sessions ADD COLUMN verification_kind TEXT NOT NULL DEFAULT 'signup'")

    def admin_count(self) -> int:
        with self.connect() as conn:
            return int(conn.execute("SELECT COUNT(*) FROM admins WHERE is_active=1").fetchone()[0])

    def create_or_replace_admin(self, username: str, password: str) -> int:
        username = username.strip().lower()
        password_hash = generate_password_hash(password, method="scrypt")
        now = iso()
        with self.connect() as conn:
            row = conn.execute("SELECT id FROM admins WHERE username=?", (username,)).fetchone()
            if row:
                admin_id = int(row["id"])
                conn.execute(
                    "UPDATE admins SET password_hash=?, is_active=1, failed_attempts=0, locked_until=NULL WHERE id=?",
                    (password_hash, admin_id),
                )
                conn.execute("DELETE FROM admin_sessions WHERE admin_id=?", (admin_id,))
                return admin_id
            cur = conn.execute(
                "INSERT INTO admins(username,password_hash,created_at) VALUES(?,?,?)",
                (username, password_hash, now),
            )
            return int(cur.lastrowid)

    def authenticate_admin(self, username: str, password: str) -> tuple[bool, Optional[sqlite3.Row], str]:
        username = username.strip().lower()
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM admins WHERE username=?", (username,)).fetchone()
            if not row or not row["is_active"]:
                return False, None, "invalid"
            locked_until = row["locked_until"]
            if locked_until:
                try:
                    if datetime.fromisoformat(locked_until) > utc_now():
                        return False, row, "locked"
                except ValueError:
                    pass
            if not check_password_hash(row["password_hash"], password):
                failed = int(row["failed_attempts"]) + 1
                lock_value = None
                if failed >= 5:
                    lock_value = iso(utc_now() + timedelta(minutes=15))
                    failed = 0
                conn.execute(
                    "UPDATE admins SET failed_attempts=?, locked_until=? WHERE id=?",
                    (failed, lock_value, int(row["id"])),
                )
                return False, row, "invalid"
            conn.execute(
                "UPDATE admins SET failed_attempts=0, locked_until=NULL, last_login_at=? WHERE id=?",
                (iso(), int(row["id"])),
            )
            fresh = conn.execute("SELECT * FROM admins WHERE id=?", (int(row["id"]),)).fetchone()
            return True, fresh, "ok"

    def create_admin_session(self, admin_id: int, hours: int = 8) -> str:
        raw = new_token()
        now = utc_now()
        with self.connect() as conn:
            conn.execute("DELETE FROM admin_sessions WHERE admin_id=?", (admin_id,))
            conn.execute(
                "INSERT INTO admin_sessions(token_hash,admin_id,created_at,expires_at,last_seen_at) VALUES(?,?,?,?,?)",
                (token_hash(raw), admin_id, iso(now), iso(now + timedelta(hours=hours)), iso(now)),
            )
        return raw

    def get_admin_session(self, raw: str) -> Optional[sqlite3.Row]:
        if not raw:
            return None
        now = utc_now()
        with self.connect() as conn:
            row = conn.execute(
                "SELECT s.*, a.username, a.is_active FROM admin_sessions s JOIN admins a ON a.id=s.admin_id WHERE s.token_hash=?",
                (token_hash(raw),),
            ).fetchone()
            if not row or not row["is_active"]:
                return None
            try:
                if datetime.fromisoformat(row["expires_at"]) <= now:
                    conn.execute("DELETE FROM admin_sessions WHERE token_hash=?", (token_hash(raw),))
                    return None
            except ValueError:
                return None
            conn.execute("UPDATE admin_sessions SET last_seen_at=? WHERE token_hash=?", (iso(now), token_hash(raw)))
            return row

    def delete_admin_session(self, raw: str) -> None:
        if not raw:
            return
        with self.connect() as conn:
            conn.execute("DELETE FROM admin_sessions WHERE token_hash=?", (token_hash(raw),))

    def ensure_browser_session(self, raw: Optional[str], hours: int = 12) -> tuple[str, Optional[sqlite3.Row]]:
        row = self.get_browser_session(raw) if raw else None
        if row:
            return raw or "", row
        raw_new = new_token()
        now = utc_now()
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO browser_sessions(token_hash,auth_version,created_at,expires_at,last_seen_at) VALUES(?,?,?,?,?)",
                (token_hash(raw_new), BROWSER_SESSION_VERSION, iso(now), iso(now + timedelta(hours=hours)), iso(now)),
            )
        return raw_new, self.get_browser_session(raw_new)

    def get_browser_session(self, raw: Optional[str]) -> Optional[sqlite3.Row]:
        if not raw:
            return None
        now = utc_now()
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM browser_sessions WHERE token_hash=?", (token_hash(raw),)).fetchone()
            if not row:
                return None
            try:
                if int(row["auth_version"] or 0) != BROWSER_SESSION_VERSION:
                    conn.execute("DELETE FROM browser_sessions WHERE token_hash=?", (token_hash(raw),))
                    return None
                if datetime.fromisoformat(row["expires_at"]) <= now:
                    conn.execute("DELETE FROM browser_sessions WHERE token_hash=?", (token_hash(raw),))
                    return None
            except (TypeError, ValueError):
                conn.execute("DELETE FROM browser_sessions WHERE token_hash=?", (token_hash(raw),))
                return None
            # Session reads are deliberately side-effect free. Older versions
            # updated last_seen_at on every request, turning the 3-second
            # watchdog into continuous SQLite writes and unnecessary WAL lock
            # contention. Authentication/rotation remains the write boundary.
            return row

    def authenticate_browser_session(
        self,
        old_raw: str,
        user_id: str,
        email: str,
        access_token: Optional[str],
        refresh_token: Optional[str],
        expires_at_epoch: Optional[int],
        role: str = "user",
        username: str = "",
        global_name: str = "",
        email_confirmed: bool = True,
        verification_kind: str = "signup",
    ) -> str:
        new_raw = new_token()
        now = utc_now()
        expires = now + timedelta(hours=12)
        if expires_at_epoch:
            try:
                provider_exp = datetime.fromtimestamp(int(expires_at_epoch), tz=timezone.utc)
                if provider_exp > now:
                    expires = min(expires, provider_exp)
            except (TypeError, ValueError, OSError):
                pass
        if role not in {"pending", "user", "admin"}:
            raise ValueError("Invalid browser-session role")
        if verification_kind not in {"signup", "invite"}:
            raise ValueError("Invalid browser-session verification kind")
        access_enc = self.keys.encrypt(access_token) if access_token else None
        refresh_enc = self.keys.encrypt(refresh_token) if refresh_token else None
        with self.connect() as conn:
            if old_raw:
                conn.execute("DELETE FROM browser_sessions WHERE token_hash=?", (token_hash(old_raw),))
            conn.execute(
                """INSERT INTO browser_sessions(
                    token_hash,auth_version,user_id,email,username,global_name,email_confirmed,verification_kind,role,access_token_enc,refresh_token_enc,created_at,expires_at,last_seen_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    token_hash(new_raw), BROWSER_SESSION_VERSION, user_id, email, username or None, global_name or None,
                    1 if email_confirmed else 0, verification_kind, role, access_enc, refresh_enc,
                    iso(now), iso(expires), iso(now),
                ),
            )
        return new_raw

    def update_browser_session_identity(
        self,
        raw: str,
        *,
        role: Optional[str] = None,
        email: Optional[str] = None,
        username: Optional[str] = None,
        global_name: Optional[str] = None,
        email_confirmed: Optional[bool] = None,
        verification_kind: Optional[str] = None,
        clear_provider_tokens: bool = False,
    ) -> Optional[sqlite3.Row]:
        if not raw:
            return None
        updates: list[str] = []
        values: list[Any] = []
        if role is not None:
            if role not in {"pending", "user", "admin"}:
                raise ValueError("Invalid browser-session role")
            updates.append("role=?")
            values.append(role)
        if email is not None:
            updates.append("email=?")
            values.append(email)
        if username is not None:
            updates.append("username=?")
            values.append(username or None)
        if global_name is not None:
            updates.append("global_name=?")
            values.append(global_name or None)
        if email_confirmed is not None:
            updates.append("email_confirmed=?")
            values.append(1 if email_confirmed else 0)
        if verification_kind is not None:
            if verification_kind not in {"signup", "invite"}:
                raise ValueError("Invalid browser-session verification kind")
            updates.append("verification_kind=?")
            values.append(verification_kind)
        if clear_provider_tokens:
            updates.append("access_token_enc=NULL")
            updates.append("refresh_token_enc=NULL")
        if not updates:
            return self.get_browser_session(raw)
        values.append(token_hash(raw))
        with self.connect() as conn:
            conn.execute(f"UPDATE browser_sessions SET {', '.join(updates)} WHERE token_hash=?", values)
        return self.get_browser_session(raw)

    def delete_browser_session(self, raw: str) -> None:
        if not raw:
            return
        with self.connect() as conn:
            conn.execute("DELETE FROM browser_sessions WHERE token_hash=?", (token_hash(raw),))

    def delete_browser_sessions_for_user(self, user_id: str) -> int:
        """Revoke every local browser session bound to one Supabase principal."""
        value = (user_id or "").strip()
        if not value:
            return 0
        with self.connect() as conn:
            cur = conn.execute("DELETE FROM browser_sessions WHERE user_id=?", (value,))
            return max(0, int(cur.rowcount or 0))

    def set_secret(self, name: str, value: str, admin_id: Optional[int]) -> None:
        encrypted = self.keys.encrypt(value)
        with self.connect() as conn:
            conn.execute(
                """INSERT INTO secure_settings(name,value_enc,updated_at,updated_by) VALUES(?,?,?,?)
                ON CONFLICT(name) DO UPDATE SET value_enc=excluded.value_enc, updated_at=excluded.updated_at, updated_by=excluded.updated_by""",
                (name, encrypted, iso(), admin_id),
            )

    def delete_secret(self, name: str) -> None:
        with self.connect() as conn:
            conn.execute("DELETE FROM secure_settings WHERE name=?", (name,))

    def get_secret(self, name: str) -> Optional[str]:
        with self.connect() as conn:
            row = conn.execute("SELECT value_enc FROM secure_settings WHERE name=?", (name,)).fetchone()
        if not row:
            return None
        try:
            return self.keys.decrypt(row["value_enc"])
        except Exception:
            return None


    def list_local_tables(self) -> list[dict[str, Any]]:
        """Inventory the local SQLite control plane without exposing row data."""
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
            ).fetchall()
            result: list[dict[str, Any]] = []
            for row in rows:
                name = str(row["name"])
                columns = conn.execute(f'PRAGMA table_info("{name}")').fetchall()
                count = int(conn.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0])
                result.append({
                    "table": name,
                    "columns": len(columns),
                    "rows": count,
                    "storage": "instance/control.sqlite3",
                })
            return result

    def add_audit(
        self,
        actor_type: str,
        actor_id: Optional[str],
        action: str,
        outcome: str,
        target: Optional[str] = None,
        remote_addr: Optional[str] = None,
        details: Optional[dict[str, Any]] = None,
    ) -> int:
        details_json = json.dumps(details or {}, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        occurred = iso()
        with self.connect() as conn:
            prev = conn.execute("SELECT event_hash FROM audit_events ORDER BY id DESC LIMIT 1").fetchone()
            prev_hash = prev["event_hash"] if prev else "GENESIS"
            payload = "|".join([
                occurred, actor_type, actor_id or "", action, outcome, target or "", remote_addr or "", details_json, prev_hash
            ])
            event_hash = self.keys.audit_digest(payload)
            cur = conn.execute(
                """INSERT INTO audit_events(
                    occurred_at,actor_type,actor_id,action,outcome,target,remote_addr,details_json,prev_hash,event_hash
                ) VALUES(?,?,?,?,?,?,?,?,?,?)""",
                (occurred, actor_type, actor_id, action, outcome, target, remote_addr, details_json, prev_hash, event_hash),
            )
            return int(cur.lastrowid)

    def list_audit(self, limit: int = 200) -> list[sqlite3.Row]:
        limit = max(1, min(int(limit), 1000))
        with self.connect() as conn:
            return list(conn.execute("SELECT * FROM audit_events ORDER BY id DESC LIMIT ?", (limit,)).fetchall())

    def verify_audit_chain(self) -> tuple[bool, Optional[int]]:
        with self.connect() as conn:
            rows = conn.execute("SELECT * FROM audit_events ORDER BY id ASC").fetchall()
        expected_prev = "GENESIS"
        for row in rows:
            if row["prev_hash"] != expected_prev:
                return False, int(row["id"])
            payload = "|".join([
                row["occurred_at"], row["actor_type"], row["actor_id"] or "", row["action"], row["outcome"],
                row["target"] or "", row["remote_addr"] or "", row["details_json"], row["prev_hash"]
            ])
            expected_hash = self.keys.audit_digest(payload)
            if expected_hash != row["event_hash"]:
                return False, int(row["id"])
            expected_prev = row["event_hash"]
        return True, None


    def allow_rate(self, bucket: str, *, limit: int, window_seconds: int) -> bool:
        now = utc_now()
        cutoff = iso(now - timedelta(seconds=window_seconds))
        with self.connect() as conn:
            conn.execute("DELETE FROM rate_limit_events WHERE occurred_at < ?", (cutoff,))
            count = int(conn.execute(
                "SELECT COUNT(*) FROM rate_limit_events WHERE bucket=? AND occurred_at>=?",
                (bucket, cutoff),
            ).fetchone()[0])
            if count >= limit:
                return False
            conn.execute("INSERT INTO rate_limit_events(bucket,occurred_at) VALUES(?,?)", (bucket, iso(now)))
            return True

    def cleanup(self) -> None:
        now = iso()
        with self.connect() as conn:
            conn.execute("DELETE FROM admin_sessions WHERE expires_at <= ?", (now,))
            conn.execute("DELETE FROM browser_sessions WHERE expires_at <= ?", (now,))
            conn.execute("DELETE FROM rate_limit_events WHERE occurred_at < ?", (iso(utc_now() - timedelta(days=1)),))
