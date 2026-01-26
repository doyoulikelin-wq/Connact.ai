"""Auth + User Profile Service (SQLite).

Supports:
- Invite-only signups (configurable)
- Email/password accounts with email verification
- Google OAuth accounts (stable identity via OIDC `sub` when available)
- Per-user profile persistence (sender profile + preferences)

Storage: SQLite at {DATA_DIR}/app.db (see config.DB_PATH).
"""

from __future__ import annotations

import hashlib
import json
import secrets
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from werkzeug.security import check_password_hash, generate_password_hash

from config import (
    DB_PATH,
    INVITE_CODES,
    INVITE_ONLY,
    INVITE_REQUIRED_FOR_LOGIN,
    EMAIL_VERIFY_TTL_HOURS,
)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _now_iso() -> str:
    return _utc_now().isoformat()


def _normalize_email(email: str) -> str:
    return (email or "").strip().lower()


def _sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()

def _parse_int(value: object, default: int = 0) -> int:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


class AuthError(Exception):
    """Base class for auth errors."""


class InvalidCredentialsError(AuthError):
    """Raised when credentials are invalid."""


class EmailNotVerifiedError(AuthError):
    """Raised when password identity email is not verified."""


class InviteRequiredError(AuthError):
    """Raised when invite code is required but missing."""


class InviteInvalidError(AuthError):
    """Raised when invite code is present but invalid."""


class SignupDisabledError(AuthError):
    """Raised when signup is disabled due to missing invite configuration."""


@dataclass(frozen=True)
class User:
    id: str
    primary_email: str | None
    display_name: str | None
    avatar_url: str | None
    created_at: str
    last_login_at: str | None
    beta_access: int = 0
    beta_access_granted_at: str | None = None


@dataclass(frozen=True)
class EmailVerification:
    token: str
    expires_at: str
    email: str


class AuthService:
    """SQLite-backed auth + profile service."""

    def __init__(
        self,
        *,
        db_path: Path | None = None,
        invite_only: bool | None = None,
        invite_required_for_login: bool | None = None,
        invite_codes: list[str] | None = None,
        email_verify_ttl_hours: int | None = None,
    ) -> None:
        self._db_path = Path(db_path) if db_path is not None else DB_PATH
        self._invite_only = INVITE_ONLY if invite_only is None else bool(invite_only)
        self._invite_required_for_login = (
            INVITE_REQUIRED_FOR_LOGIN
            if invite_required_for_login is None
            else bool(invite_required_for_login)
        )
        self._invite_codes = INVITE_CODES if invite_codes is None else [c for c in invite_codes if c]
        self._email_verify_ttl_hours = (
            EMAIL_VERIFY_TTL_HOURS if email_verify_ttl_hours is None else int(email_verify_ttl_hours)
        )
        self._ensure_parent_dir()
        self._init_db()

    @property
    def db_path(self) -> Path:
        return self._db_path

    @property
    def invite_only(self) -> bool:
        return self._invite_only

    @property
    def invite_required_for_login(self) -> bool:
        return self._invite_required_for_login

    def _ensure_parent_dir(self) -> None:
        try:
            self._db_path.parent.mkdir(parents=True, exist_ok=True)
        except PermissionError:
            pass

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self._db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")

            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY,
                    primary_email TEXT,
                    display_name TEXT,
                    avatar_url TEXT,
                    created_at TEXT NOT NULL,
                    last_login_at TEXT,
                    is_active INTEGER NOT NULL DEFAULT 1
                )
                """
            )
            self._ensure_user_columns(conn)

            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS auth_identities (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    provider_sub TEXT NOT NULL,
                    email TEXT,
                    password_hash TEXT,
                    email_verified INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    last_used_at TEXT,
                    UNIQUE(provider, provider_sub),
                    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
                )
                """
            )

            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS user_profiles (
                    user_id TEXT PRIMARY KEY,
                    sender_profile_json TEXT NOT NULL DEFAULT '{}',
                    preferences_json TEXT NOT NULL DEFAULT '{}',
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
                )
                """
            )

            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS email_verifications (
                    id TEXT PRIMARY KEY,
                    identity_id TEXT NOT NULL,
                    token_hash TEXT NOT NULL UNIQUE,
                    expires_at TEXT NOT NULL,
                    used_at TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(identity_id) REFERENCES auth_identities(id) ON DELETE CASCADE
                )
                """
            )

            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS login_events (
                    id TEXT PRIMARY KEY,
                    user_id TEXT,
                    provider TEXT,
                    email TEXT,
                    success INTEGER NOT NULL,
                    reason TEXT,
                    ip TEXT,
                    user_agent TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE SET NULL
                )
                """
            )

            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS waitlist (
                    id TEXT PRIMARY KEY,
                    email TEXT NOT NULL UNIQUE,
                    created_at TEXT NOT NULL,
                    ip TEXT,
                    user_agent TEXT
                )
                """
            )

    def _ensure_user_columns(self, conn: sqlite3.Connection) -> None:
        """Best-effort schema migrations for the users table."""
        # NOTE: SQLite doesn't support ADD COLUMN IF NOT EXISTS.
        migrations = [
            ("beta_access", "ALTER TABLE users ADD COLUMN beta_access INTEGER DEFAULT 0"),
            ("beta_access_granted_at", "ALTER TABLE users ADD COLUMN beta_access_granted_at TEXT"),
        ]
        for _, statement in migrations:
            try:
                conn.execute(statement)
            except sqlite3.OperationalError:
                # Column likely already exists.
                continue

    def _validate_invite_code(self, invite_code: str | None, *, enforce: bool) -> None:
        if not enforce:
            return
        if not self._invite_codes:
            raise SignupDisabledError("Invite-only is enabled but no invite codes are configured.")
        code = (invite_code or "").strip()
        if not code:
            raise InviteRequiredError("Invite code is required.")
        if code not in self._invite_codes:
            raise InviteInvalidError("Invalid invite code.")

    def validate_invite_code(self, invite_code: str | None) -> None:
        """Validate invite code against configured allowlist (always enforced)."""
        self._validate_invite_code(invite_code, enforce=True)

    def validate_invite_for_login(self, invite_code: str | None) -> None:
        """Validate invite code for login gating (internal beta).

        When enabled, *every* login attempt (Google + Email/Password) must provide a valid code.
        """
        self._validate_invite_code(invite_code, enforce=self._invite_required_for_login)

    def get_user_id_for_password_email(self, email: str) -> str | None:
        email_norm = _normalize_email(email)
        if not email_norm:
            return None
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT user_id
                FROM auth_identities
                WHERE provider = 'password' AND provider_sub = ?
                LIMIT 1
                """,
                (email_norm,),
            ).fetchone()
            return row["user_id"] if row else None

    def get_user_id_for_google_sub(self, google_sub: str) -> str | None:
        google_sub = (google_sub or "").strip()
        if not google_sub:
            return None
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT user_id
                FROM auth_identities
                WHERE provider = 'google' AND provider_sub = ?
                LIMIT 1
                """,
                (google_sub,),
            ).fetchone()
            return row["user_id"] if row else None

    def user_has_beta_access(self, user_id: str) -> bool:
        if not user_id:
            return False
        with self._connect() as conn:
            row = conn.execute("SELECT beta_access FROM users WHERE id = ? LIMIT 1", (user_id,)).fetchone()
            return bool(_parse_int(row["beta_access"] if row else 0))

    def grant_beta_access(self, user_id: str) -> None:
        if not user_id:
            return
        now = _now_iso()
        with self._connect() as conn:
            conn.execute(
                "UPDATE users SET beta_access = 1, beta_access_granted_at = COALESCE(beta_access_granted_at, ?) WHERE id = ?",
                (now, user_id),
            )

    def add_waitlist_email(
        self,
        email: str,
        *,
        ip: str | None = None,
        user_agent: str | None = None,
    ) -> bool:
        email_norm = _normalize_email(email)
        if not email_norm:
            raise AuthError("Email is required.")

        with self._connect() as conn:
            existing = conn.execute("SELECT 1 FROM waitlist WHERE email = ? LIMIT 1", (email_norm,)).fetchone()
            if existing:
                return False
            conn.execute(
                """
                INSERT INTO waitlist (id, email, created_at, ip, user_agent)
                VALUES (?, ?, ?, ?, ?)
                """,
                (str(uuid.uuid4()), email_norm, _now_iso(), ip, user_agent),
            )
            return True

    def _ensure_profile_row(self, conn: sqlite3.Connection, user_id: str) -> None:
        now = _now_iso()
        conn.execute(
            """
            INSERT OR IGNORE INTO user_profiles (user_id, sender_profile_json, preferences_json, updated_at)
            VALUES (?, '{}', '{}', ?)
            """,
            (user_id, now),
        )

    def _record_login_event(
        self,
        conn: sqlite3.Connection,
        *,
        user_id: str | None,
        provider: str | None,
        email: str | None,
        success: bool,
        reason: str | None = None,
        ip: str | None = None,
        user_agent: str | None = None,
    ) -> None:
        conn.execute(
            """
            INSERT INTO login_events (id, user_id, provider, email, success, reason, ip, user_agent, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(uuid.uuid4()),
                user_id,
                provider,
                email,
                1 if success else 0,
                reason,
                ip,
                user_agent,
                _now_iso(),
            ),
        )

    def _row_to_user(self, row: sqlite3.Row) -> User:
        keys = set(row.keys())
        beta_access = _parse_int(row["beta_access"]) if "beta_access" in keys else 0
        beta_access_granted_at = row["beta_access_granted_at"] if "beta_access_granted_at" in keys else None
        return User(
            id=row["id"],
            primary_email=row["primary_email"],
            display_name=row["display_name"],
            avatar_url=row["avatar_url"],
            created_at=row["created_at"],
            last_login_at=row["last_login_at"],
            beta_access=beta_access,
            beta_access_granted_at=beta_access_granted_at,
        )

    def get_user(self, user_id: str) -> User | None:
        if not user_id:
            return None
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT
                    id, primary_email, display_name, avatar_url, created_at, last_login_at,
                    COALESCE(beta_access, 0) AS beta_access,
                    beta_access_granted_at
                FROM users
                WHERE id = ?
                """,
                (user_id,),
            ).fetchone()
            return self._row_to_user(row) if row else None

    # ---------------------------------------------------------------------
    # Password accounts
    # ---------------------------------------------------------------------

    def create_password_user(
        self,
        *,
        email: str,
        password: str,
        display_name: str | None = None,
        invite_code: str | None = None,
        ip: str | None = None,
        user_agent: str | None = None,
    ) -> EmailVerification:
        email_norm = _normalize_email(email)
        if not email_norm:
            raise AuthError("Email is required.")
        if not password or len(password) < 8:
            raise AuthError("Password must be at least 8 characters.")

        self._validate_invite_code(invite_code, enforce=self._invite_only)

        now = _now_iso()
        user_id = str(uuid.uuid4())
        identity_id = str(uuid.uuid4())

        password_hash = generate_password_hash(password)

        with self._connect() as conn:
            existing = conn.execute(
                """
                SELECT 1
                FROM auth_identities
                WHERE email = ?
                LIMIT 1
                """,
                (email_norm,),
            ).fetchone()
            if existing:
                raise AuthError("An account with this email already exists.")

            conn.execute(
                """
                INSERT INTO users (id, primary_email, display_name, avatar_url, created_at, last_login_at, is_active)
                VALUES (?, ?, ?, NULL, ?, NULL, 1)
                """,
                (user_id, email_norm, (display_name or "").strip() or None, now),
            )
            conn.execute(
                """
                INSERT INTO auth_identities (
                    id, user_id, provider, provider_sub, email, password_hash, email_verified, created_at, last_used_at
                )
                VALUES (?, ?, 'password', ?, ?, ?, 0, ?, NULL)
                """,
                (identity_id, user_id, email_norm, email_norm, password_hash, now),
            )
            self._ensure_profile_row(conn, user_id)

            verification = self._create_email_verification(conn, identity_id, email_norm)
            self._record_login_event(
                conn,
                user_id=user_id,
                provider="password",
                email=email_norm,
                success=True,
                reason="signup",
                ip=ip,
                user_agent=user_agent,
            )
            return verification

    def authenticate_password(
        self,
        *,
        email: str,
        password: str,
        ip: str | None = None,
        user_agent: str | None = None,
    ) -> User:
        email_norm = _normalize_email(email)
        if not email_norm or not password:
            raise InvalidCredentialsError("Invalid email or password.")

        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT
                    ai.id AS identity_id,
                    ai.user_id,
                    ai.password_hash,
                    ai.email_verified,
                    u.id,
                    u.primary_email,
                    u.display_name,
                    u.avatar_url,
                    u.created_at,
                    u.last_login_at
                FROM auth_identities ai
                JOIN users u ON u.id = ai.user_id
                WHERE ai.provider = 'password' AND ai.provider_sub = ?
                LIMIT 1
                """,
                (email_norm,),
            ).fetchone()

            if not row or not row["password_hash"] or not check_password_hash(row["password_hash"], password):
                self._record_login_event(
                    conn,
                    user_id=None,
                    provider="password",
                    email=email_norm,
                    success=False,
                    reason="invalid_credentials",
                    ip=ip,
                    user_agent=user_agent,
                )
                raise InvalidCredentialsError("Invalid email or password.")

            if not int(row["email_verified"] or 0):
                self._record_login_event(
                    conn,
                    user_id=row["user_id"],
                    provider="password",
                    email=email_norm,
                    success=False,
                    reason="email_not_verified",
                    ip=ip,
                    user_agent=user_agent,
                )
                raise EmailNotVerifiedError("Email not verified.")

            now = _now_iso()
            conn.execute(
                "UPDATE auth_identities SET last_used_at = ? WHERE id = ?",
                (now, row["identity_id"]),
            )
            conn.execute("UPDATE users SET last_login_at = ? WHERE id = ?", (now, row["user_id"]))
            self._record_login_event(
                conn,
                user_id=row["user_id"],
                provider="password",
                email=email_norm,
                success=True,
                reason="login",
                ip=ip,
                user_agent=user_agent,
            )
            self._ensure_profile_row(conn, row["user_id"])
            return self._row_to_user(row)

    def _create_email_verification(
        self, conn: sqlite3.Connection, identity_id: str, email: str
    ) -> EmailVerification:
        token = secrets.token_urlsafe(32)
        token_hash = _sha256_hex(token)
        now_dt = _utc_now()
        expires_at_dt = now_dt + timedelta(hours=self._email_verify_ttl_hours)

        conn.execute(
            """
            INSERT INTO email_verifications (id, identity_id, token_hash, expires_at, used_at, created_at)
            VALUES (?, ?, ?, ?, NULL, ?)
            """,
            (
                str(uuid.uuid4()),
                identity_id,
                token_hash,
                expires_at_dt.isoformat(),
                now_dt.isoformat(),
            ),
        )
        return EmailVerification(token=token, expires_at=expires_at_dt.isoformat(), email=email)

    def resend_email_verification(
        self,
        *,
        email: str,
        ip: str | None = None,
        user_agent: str | None = None,
    ) -> EmailVerification:
        email_norm = _normalize_email(email)
        if not email_norm:
            raise AuthError("Email is required.")

        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT ai.id AS identity_id, ai.user_id, ai.email_verified
                FROM auth_identities ai
                WHERE ai.provider = 'password' AND ai.provider_sub = ?
                LIMIT 1
                """,
                (email_norm,),
            ).fetchone()
            if not row:
                raise AuthError("No password account found for this email.")
            if int(row["email_verified"] or 0):
                raise AuthError("Email is already verified.")

            verification = self._create_email_verification(conn, row["identity_id"], email_norm)
            self._record_login_event(
                conn,
                user_id=row["user_id"],
                provider="password",
                email=email_norm,
                success=True,
                reason="resend_verification",
                ip=ip,
                user_agent=user_agent,
            )
            return verification

    def verify_email_token(self, token: str) -> str | None:
        token = (token or "").strip()
        if not token:
            return None
        token_hash = _sha256_hex(token)
        now = _utc_now()

        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT ev.id AS verification_id, ev.expires_at, ev.used_at, ai.id AS identity_id, ai.user_id
                FROM email_verifications ev
                JOIN auth_identities ai ON ai.id = ev.identity_id
                WHERE ev.token_hash = ?
                LIMIT 1
                """,
                (token_hash,),
            ).fetchone()
            if not row:
                return None
            if row["used_at"]:
                return None
            try:
                expires_at = datetime.fromisoformat(row["expires_at"])
            except Exception:
                return None
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
            if expires_at < now:
                return None

            now_iso = now.isoformat()
            conn.execute(
                "UPDATE auth_identities SET email_verified = 1, last_used_at = ? WHERE id = ?",
                (now_iso, row["identity_id"]),
            )
            conn.execute(
                "UPDATE email_verifications SET used_at = ? WHERE id = ?",
                (now_iso, row["verification_id"]),
            )
            self._ensure_profile_row(conn, row["user_id"])
            return row["user_id"]

    # ---------------------------------------------------------------------
    # Google accounts
    # ---------------------------------------------------------------------

    def authenticate_google(
        self,
        *,
        google_sub: str,
        email: str | None,
        display_name: str | None,
        avatar_url: str | None,
        email_verified: bool | None = None,
        invite_code: str | None = None,
        ip: str | None = None,
        user_agent: str | None = None,
    ) -> User:
        if not google_sub:
            raise AuthError("Missing Google subject.")

        email_norm = _normalize_email(email or "") if email else None
        now = _now_iso()

        with self._connect() as conn:
            identity = conn.execute(
                """
                SELECT ai.user_id
                FROM auth_identities ai
                WHERE ai.provider = 'google' AND ai.provider_sub = ?
                LIMIT 1
                """,
                (google_sub,),
            ).fetchone()

            if identity:
                user_id = identity["user_id"]
                conn.execute(
                    "UPDATE auth_identities SET last_used_at = ? WHERE provider = 'google' AND provider_sub = ?",
                    (now, google_sub),
                )
                conn.execute(
                    """
                    UPDATE users
                    SET primary_email = COALESCE(primary_email, ?),
                        display_name = COALESCE(?, display_name),
                        avatar_url = COALESCE(?, avatar_url),
                        last_login_at = ?
                    WHERE id = ?
                    """,
                    (email_norm, (display_name or "").strip() or None, avatar_url, now, user_id),
                )
                self._ensure_profile_row(conn, user_id)
                self._record_login_event(
                    conn,
                    user_id=user_id,
                    provider="google",
                    email=email_norm,
                    success=True,
                    reason="login",
                    ip=ip,
                    user_agent=user_agent,
                )
                row = conn.execute(
                    "SELECT id, primary_email, display_name, avatar_url, created_at, last_login_at FROM users WHERE id = ?",
                    (user_id,),
                ).fetchone()
                return self._row_to_user(row)

            # Link to existing user by verified email (preferred) or by any matching email (fallback).
            user_row = None
            if email_norm:
                user_row = conn.execute(
                    """
                    SELECT id, primary_email, display_name, avatar_url, created_at, last_login_at
                    FROM users
                    WHERE primary_email = ?
                    LIMIT 1
                    """,
                    (email_norm,),
                ).fetchone()
                if not user_row:
                    user_row = conn.execute(
                        """
                        SELECT u.id, u.primary_email, u.display_name, u.avatar_url, u.created_at, u.last_login_at
                        FROM auth_identities ai
                        JOIN users u ON u.id = ai.user_id
                        WHERE ai.email = ?
                        LIMIT 1
                        """,
                        (email_norm,),
                    ).fetchone()

            if user_row and (email_verified is True):
                user_id = user_row["id"]
                conn.execute(
                    """
                    INSERT INTO auth_identities (
                        id, user_id, provider, provider_sub, email, password_hash, email_verified, created_at, last_used_at
                    )
                    VALUES (?, ?, 'google', ?, ?, NULL, ?, ?, ?)
                    """,
                    (
                        str(uuid.uuid4()),
                        user_id,
                        google_sub,
                        email_norm,
                        1,
                        now,
                        now,
                    ),
                )
                conn.execute(
                    """
                    UPDATE users
                    SET display_name = COALESCE(?, display_name),
                        avatar_url = COALESCE(?, avatar_url),
                        last_login_at = ?
                    WHERE id = ?
                    """,
                    ((display_name or "").strip() or None, avatar_url, now, user_id),
                )
                self._ensure_profile_row(conn, user_id)
                self._record_login_event(
                    conn,
                    user_id=user_id,
                    provider="google",
                    email=email_norm,
                    success=True,
                    reason="link_and_login",
                    ip=ip,
                    user_agent=user_agent,
                )
                return self._row_to_user(user_row)

            # New user (invite-only)
            self._validate_invite_code(invite_code, enforce=self._invite_only)

            user_id = str(uuid.uuid4())
            conn.execute(
                """
                INSERT INTO users (id, primary_email, display_name, avatar_url, created_at, last_login_at, is_active)
                VALUES (?, ?, ?, ?, ?, ?, 1)
                """,
                (
                    user_id,
                    email_norm,
                    (display_name or "").strip() or None,
                    avatar_url,
                    now,
                    now,
                ),
            )
            conn.execute(
                """
                INSERT INTO auth_identities (
                    id, user_id, provider, provider_sub, email, password_hash, email_verified, created_at, last_used_at
                )
                VALUES (?, ?, 'google', ?, ?, NULL, ?, ?, ?)
                """,
                (
                    str(uuid.uuid4()),
                    user_id,
                    google_sub,
                    email_norm,
                    1 if (email_verified is True) else 0,
                    now,
                    now,
                ),
            )
            self._ensure_profile_row(conn, user_id)
            self._record_login_event(
                conn,
                user_id=user_id,
                provider="google",
                email=email_norm,
                success=True,
                reason="signup_and_login",
                ip=ip,
                user_agent=user_agent,
            )
            row = conn.execute(
                "SELECT id, primary_email, display_name, avatar_url, created_at, last_login_at FROM users WHERE id = ?",
                (user_id,),
            ).fetchone()
            return self._row_to_user(row)

    # ---------------------------------------------------------------------
    # User profile (sender profile + preferences)
    # ---------------------------------------------------------------------

    def get_user_profile(self, user_id: str) -> dict[str, Any]:
        if not user_id:
            return {"sender_profile": None, "preferences": None}
        with self._connect() as conn:
            self._ensure_profile_row(conn, user_id)
            row = conn.execute(
                "SELECT sender_profile_json, preferences_json, updated_at FROM user_profiles WHERE user_id = ?",
                (user_id,),
            ).fetchone()
            if not row:
                return {"sender_profile": None, "preferences": None}
            sender_profile = json.loads(row["sender_profile_json"] or "{}")
            preferences = json.loads(row["preferences_json"] or "{}")
            return {
                "sender_profile": sender_profile or None,
                "preferences": preferences or None,
                "updated_at": row["updated_at"],
            }

    def update_user_profile(
        self,
        *,
        user_id: str,
        sender_profile: dict[str, Any] | None = None,
        preferences: dict[str, Any] | None = None,
    ) -> None:
        if not user_id:
            raise AuthError("Missing user_id.")

        now = _now_iso()
        with self._connect() as conn:
            self._ensure_profile_row(conn, user_id)
            if sender_profile is not None:
                conn.execute(
                    "UPDATE user_profiles SET sender_profile_json = ?, updated_at = ? WHERE user_id = ?",
                    (json.dumps(sender_profile, ensure_ascii=False), now, user_id),
                )
            if preferences is not None:
                conn.execute(
                    "UPDATE user_profiles SET preferences_json = ?, updated_at = ? WHERE user_id = ?",
                    (json.dumps(preferences, ensure_ascii=False), now, user_id),
                )


# Global instance for app usage
auth_service = AuthService()
