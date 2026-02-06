"""User Data Service - Manages user contacts, emails history, and Apollo credits.

This service handles:
- User saved contacts
- Generated email history
- Apollo credits for email lookup

Storage: SQLite at {DATA_DIR}/app.db (same as auth_service).
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from config import DB_PATH

# Default Apollo credits per user
DEFAULT_APOLLO_CREDITS = 5


@dataclass
class SavedContact:
    """A contact saved by the user."""
    id: str
    user_id: str
    name: str
    position: str
    linkedin_url: str
    email: Optional[str]  # Unlocked via Apollo
    email_unlocked_at: Optional[str]
    match_score: int
    match_reason: str
    common_interests: str
    evidence: list[str]
    sources: list[str]
    raw_data: dict  # Full original recommendation data
    created_at: str
    updated_at: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class SavedEmail:
    """A generated email saved by the user."""
    id: str
    user_id: str
    contact_id: Optional[str]  # Reference to saved contact if exists
    contact_name: str
    contact_position: str
    subject: str
    body: str
    goal: str
    template_used: Optional[str]
    created_at: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class UserCredits:
    """User's Apollo credits."""
    user_id: str
    apollo_credits: int
    total_used: int
    last_used_at: Optional[str]

    def to_dict(self) -> dict:
        return asdict(self)


class UserDataService:
    """SQLite-backed user data service."""

    def __init__(self, db_path: Path = DB_PATH):
        self._db_path = db_path
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self._db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _init_db(self) -> None:
        """Initialize database tables for user data."""
        with self._connect() as conn:
            # Saved contacts table
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS user_contacts (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    position TEXT,
                    linkedin_url TEXT,
                    email TEXT,
                    email_unlocked_at TEXT,
                    match_score INTEGER DEFAULT 0,
                    match_reason TEXT,
                    common_interests TEXT,
                    evidence_json TEXT DEFAULT '[]',
                    sources_json TEXT DEFAULT '[]',
                    raw_data_json TEXT DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_user_contacts_user_id ON user_contacts(user_id)"
            )

            # Saved emails table
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS user_emails (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    contact_id TEXT,
                    contact_name TEXT NOT NULL,
                    contact_position TEXT,
                    subject TEXT NOT NULL,
                    body TEXT NOT NULL,
                    goal TEXT,
                    template_used TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
                    FOREIGN KEY(contact_id) REFERENCES user_contacts(id) ON DELETE SET NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_user_emails_user_id ON user_emails(user_id)"
            )

            # User credits table
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS user_credits (
                    user_id TEXT PRIMARY KEY,
                    apollo_credits INTEGER NOT NULL DEFAULT 5,
                    total_used INTEGER NOT NULL DEFAULT 0,
                    last_used_at TEXT,
                    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
                )
                """
            )

            # User activity sessions and events
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS user_activities (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    activity_index INTEGER NOT NULL,
                    title TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS user_activity_events (
                    id TEXT PRIMARY KEY,
                    activity_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    payload_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(activity_id) REFERENCES user_activities(id) ON DELETE CASCADE,
                    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_user_activities_user ON user_activities(user_id, created_at)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_user_activity_events ON user_activity_events(activity_id, created_at)"
            )

            conn.commit()

    # ==================== Contact Methods ====================

    def save_contact(
        self,
        user_id: str,
        contact_data: dict,
    ) -> SavedContact:
        """Save a contact for a user."""
        now = datetime.utcnow().isoformat() + "Z"
        contact_id = f"contact_{uuid.uuid4().hex[:12]}"

        contact = SavedContact(
            id=contact_id,
            user_id=user_id,
            name=contact_data.get("name", ""),
            position=contact_data.get("position", ""),
            linkedin_url=contact_data.get("linkedin_url", ""),
            email=contact_data.get("email"),
            email_unlocked_at=None,
            match_score=contact_data.get("match_score", 0),
            match_reason=contact_data.get("match_reason", ""),
            common_interests=contact_data.get("common_interests", ""),
            evidence=contact_data.get("evidence", []),
            sources=contact_data.get("sources", []),
            raw_data=contact_data,
            created_at=now,
            updated_at=now,
        )

        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO user_contacts (
                    id, user_id, name, position, linkedin_url, email, email_unlocked_at,
                    match_score, match_reason, common_interests,
                    evidence_json, sources_json, raw_data_json,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    contact.id,
                    contact.user_id,
                    contact.name,
                    contact.position,
                    contact.linkedin_url,
                    contact.email,
                    contact.email_unlocked_at,
                    contact.match_score,
                    contact.match_reason,
                    contact.common_interests,
                    json.dumps(contact.evidence),
                    json.dumps(contact.sources),
                    json.dumps(contact.raw_data),
                    contact.created_at,
                    contact.updated_at,
                ),
            )
            conn.commit()

        return contact

    def get_user_contacts(
        self,
        user_id: str,
        limit: int = 50,
        offset: int = 0,
    ) -> list[SavedContact]:
        """Get all saved contacts for a user."""
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM user_contacts
                WHERE user_id = ?
                ORDER BY created_at DESC
                LIMIT ? OFFSET ?
                """,
                (user_id, limit, offset),
            ).fetchall()

        contacts = []
        for row in rows:
            contacts.append(self._row_to_contact(row))
        return contacts

    def get_contact(self, contact_id: str) -> Optional[SavedContact]:
        """Get a specific contact by ID."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM user_contacts WHERE id = ?",
                (contact_id,),
            ).fetchone()

        if row:
            return self._row_to_contact(row)
        return None

    def update_contact_email(
        self,
        contact_id: str,
        email: str,
    ) -> Optional[SavedContact]:
        """Update a contact's email (after Apollo lookup)."""
        now = datetime.utcnow().isoformat() + "Z"

        with self._connect() as conn:
            conn.execute(
                """
                UPDATE user_contacts
                SET email = ?, email_unlocked_at = ?, updated_at = ?
                WHERE id = ?
                """,
                (email, now, now, contact_id),
            )
            conn.commit()

        return self.get_contact(contact_id)

    def delete_contact(self, contact_id: str, user_id: str) -> bool:
        """Delete a contact (only if owned by user)."""
        with self._connect() as conn:
            result = conn.execute(
                "DELETE FROM user_contacts WHERE id = ? AND user_id = ?",
                (contact_id, user_id),
            )
            conn.commit()
            return result.rowcount > 0

    def _row_to_contact(self, row: sqlite3.Row) -> SavedContact:
        return SavedContact(
            id=row["id"],
            user_id=row["user_id"],
            name=row["name"],
            position=row["position"] or "",
            linkedin_url=row["linkedin_url"] or "",
            email=row["email"],
            email_unlocked_at=row["email_unlocked_at"],
            match_score=row["match_score"] or 0,
            match_reason=row["match_reason"] or "",
            common_interests=row["common_interests"] or "",
            evidence=json.loads(row["evidence_json"] or "[]"),
            sources=json.loads(row["sources_json"] or "[]"),
            raw_data=json.loads(row["raw_data_json"] or "{}"),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    # ==================== Email Methods ====================

    def save_email(
        self,
        user_id: str,
        contact_name: str,
        contact_position: str,
        subject: str,
        body: str,
        goal: str = "",
        contact_id: Optional[str] = None,
        template_used: Optional[str] = None,
    ) -> SavedEmail:
        """Save a generated email for a user."""
        now = datetime.utcnow().isoformat() + "Z"
        email_id = f"email_{uuid.uuid4().hex[:12]}"

        email = SavedEmail(
            id=email_id,
            user_id=user_id,
            contact_id=contact_id,
            contact_name=contact_name,
            contact_position=contact_position,
            subject=subject,
            body=body,
            goal=goal,
            template_used=template_used,
            created_at=now,
        )

        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO user_emails (
                    id, user_id, contact_id, contact_name, contact_position,
                    subject, body, goal, template_used, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    email.id,
                    email.user_id,
                    email.contact_id,
                    email.contact_name,
                    email.contact_position,
                    email.subject,
                    email.body,
                    email.goal,
                    email.template_used,
                    email.created_at,
                ),
            )
            conn.commit()

        return email

    def get_user_emails(
        self,
        user_id: str,
        limit: int = 50,
        offset: int = 0,
    ) -> list[SavedEmail]:
        """Get all saved emails for a user."""
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM user_emails
                WHERE user_id = ?
                ORDER BY created_at DESC
                LIMIT ? OFFSET ?
                """,
                (user_id, limit, offset),
            ).fetchall()

        emails = []
        for row in rows:
            emails.append(self._row_to_email(row))
        return emails

    def get_email(self, email_id: str) -> Optional[SavedEmail]:
        """Get a specific email by ID."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM user_emails WHERE id = ?",
                (email_id,),
            ).fetchone()

        if row:
            return self._row_to_email(row)
        return None

    def delete_email(self, email_id: str, user_id: str) -> bool:
        """Delete an email (only if owned by user)."""
        with self._connect() as conn:
            result = conn.execute(
                "DELETE FROM user_emails WHERE id = ? AND user_id = ?",
                (email_id, user_id),
            )
            conn.commit()
            return result.rowcount > 0

    def _row_to_email(self, row: sqlite3.Row) -> SavedEmail:
        return SavedEmail(
            id=row["id"],
            user_id=row["user_id"],
            contact_id=row["contact_id"],
            contact_name=row["contact_name"],
            contact_position=row["contact_position"] or "",
            subject=row["subject"],
            body=row["body"],
            goal=row["goal"] or "",
            template_used=row["template_used"],
            created_at=row["created_at"],
        )

    # ==================== Credits Methods ====================

    def get_user_credits(self, user_id: str) -> UserCredits:
        """Get user's Apollo credits, initializing if needed."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM user_credits WHERE user_id = ?",
                (user_id,),
            ).fetchone()

            if not row:
                # Initialize credits for new user
                conn.execute(
                    """
                    INSERT INTO user_credits (user_id, apollo_credits, total_used)
                    VALUES (?, ?, 0)
                    """,
                    (user_id, DEFAULT_APOLLO_CREDITS),
                )
                conn.commit()
                return UserCredits(
                    user_id=user_id,
                    apollo_credits=DEFAULT_APOLLO_CREDITS,
                    total_used=0,
                    last_used_at=None,
                )

        return UserCredits(
            user_id=row["user_id"],
            apollo_credits=row["apollo_credits"],
            total_used=row["total_used"],
            last_used_at=row["last_used_at"],
        )

    def use_credit(self, user_id: str) -> tuple[bool, int]:
        """
        Use one Apollo credit. Returns (success, remaining_credits).
        """
        credits = self.get_user_credits(user_id)

        if credits.apollo_credits <= 0:
            return False, 0

        now = datetime.utcnow().isoformat() + "Z"
        new_credits = credits.apollo_credits - 1

        with self._connect() as conn:
            conn.execute(
                """
                UPDATE user_credits
                SET apollo_credits = ?, total_used = total_used + 1, last_used_at = ?
                WHERE user_id = ?
                """,
                (new_credits, now, user_id),
            )
            conn.commit()

        return True, new_credits

    def add_credits(self, user_id: str, amount: int) -> int:
        """Add credits to a user (admin function). Returns new total."""
        credits = self.get_user_credits(user_id)
        new_credits = credits.apollo_credits + amount

        with self._connect() as conn:
            conn.execute(
                "UPDATE user_credits SET apollo_credits = ? WHERE user_id = ?",
                (new_credits, user_id),
            )
            conn.commit()

        return new_credits

    # ==================== Dashboard Methods ====================

    def get_user_dashboard(self, user_id: str) -> dict:
        """Get user's dashboard data."""
        credits = self.get_user_credits(user_id)

        with self._connect() as conn:
            # Count contacts
            contacts_count = conn.execute(
                "SELECT COUNT(*) FROM user_contacts WHERE user_id = ?",
                (user_id,),
            ).fetchone()[0]

            # Count emails
            emails_count = conn.execute(
                "SELECT COUNT(*) FROM user_emails WHERE user_id = ?",
                (user_id,),
            ).fetchone()[0]

            # Count unlocked emails
            unlocked_count = conn.execute(
                "SELECT COUNT(*) FROM user_contacts WHERE user_id = ? AND email IS NOT NULL",
                (user_id,),
            ).fetchone()[0]

            # Get recent contacts (last 5)
            recent_contacts = conn.execute(
                """
                SELECT * FROM user_contacts
                WHERE user_id = ?
                ORDER BY created_at DESC
                LIMIT 5
                """,
                (user_id,),
            ).fetchall()

            # Get recent emails (last 5)
            recent_emails = conn.execute(
                """
                SELECT * FROM user_emails
                WHERE user_id = ?
                ORDER BY created_at DESC
                LIMIT 5
                """,
                (user_id,),
            ).fetchall()

        return {
            "credits": credits.to_dict(),
            "stats": {
                "contacts_count": contacts_count,
                "emails_count": emails_count,
                "unlocked_emails_count": unlocked_count,
            },
            "recent_contacts": [self._row_to_contact(r).to_dict() for r in recent_contacts],
            "recent_emails": [self._row_to_email(r).to_dict() for r in recent_emails],
        }

    # ==================== Activity Methods ====================

    def start_activity(self, user_id: str, title: Optional[str] = None) -> dict:
        """Start a new activity session for a user."""
        now = datetime.utcnow().isoformat() + "Z"
        activity_id = f"activity_{uuid.uuid4().hex[:12]}"

        with self._connect() as conn:
            row = conn.execute(
                "SELECT COALESCE(MAX(activity_index), 0) as max_idx FROM user_activities WHERE user_id = ?",
                (user_id,),
            ).fetchone()
            next_index = (row["max_idx"] or 0) + 1
            activity_title = title or f"Activity {next_index}"

            conn.execute(
                """
                INSERT INTO user_activities (
                    id, user_id, activity_index, title, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (activity_id, user_id, next_index, activity_title, now, now),
            )
            conn.commit()

        return {
            "id": activity_id,
            "activity_index": next_index,
            "title": activity_title,
            "created_at": now,
            "updated_at": now,
        }

    def add_activity_event(
        self,
        user_id: str,
        activity_id: str,
        event_type: str,
        payload: Optional[dict] = None,
    ) -> dict:
        """Append an event to an activity session."""
        now = datetime.utcnow().isoformat() + "Z"
        event_id = f"event_{uuid.uuid4().hex[:12]}"
        payload_json = json.dumps(payload or {})

        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO user_activity_events (
                    id, activity_id, user_id, event_type, payload_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (event_id, activity_id, user_id, event_type, payload_json, now),
            )
            conn.execute(
                "UPDATE user_activities SET updated_at = ? WHERE id = ?",
                (now, activity_id),
            )
            conn.commit()

        return {
            "id": event_id,
            "activity_id": activity_id,
            "event_type": event_type,
            "payload": payload or {},
            "created_at": now,
        }

    def get_user_activities(self, user_id: str, limit: int = 20, offset: int = 0) -> list[dict]:
        """Return recent activities with their events."""
        activities: list[dict] = []

        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, user_id, activity_index, title, created_at, updated_at
                FROM user_activities
                WHERE user_id = ?
                ORDER BY created_at DESC
                LIMIT ? OFFSET ?
                """,
                (user_id, limit, offset),
            ).fetchall()

            for row in rows:
                events_rows = conn.execute(
                    """
                    SELECT id, event_type, payload_json, created_at
                    FROM user_activity_events
                    WHERE activity_id = ?
                    ORDER BY created_at ASC
                    """,
                    (row["id"],),
                ).fetchall()

                events = []
                for ev in events_rows:
                    events.append(
                        {
                            "id": ev["id"],
                            "event_type": ev["event_type"],
                            "payload": json.loads(ev["payload_json"] or "{}"),
                            "created_at": ev["created_at"],
                        }
                    )

                activities.append(
                    {
                        "id": row["id"],
                        "activity_index": row["activity_index"],
                        "title": row["title"],
                        "created_at": row["created_at"],
                        "updated_at": row["updated_at"],
                        "events": events,
                    }
                )

        return activities


# Global instance
user_data_service = UserDataService()
