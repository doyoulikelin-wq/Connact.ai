"""Invite management CLI (SQLite).

Usage:
  python -m src.manage_invites create --email user@example.com --label "User"
  python -m src.manage_invites list
  python -m src.manage_invites revoke --email user@example.com

This tool writes to the auth DB at {DATA_DIR}/app.db (or DB_PATH override).
"""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
from pathlib import Path

from src.services.auth_service import AuthService


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Manage per-user invite codes (SQLite).")
    parser.add_argument("--db-path", type=Path, default=None, help="Override DB path (default: config.DB_PATH)")

    sub = parser.add_subparsers(dest="command", required=True)

    p_create = sub.add_parser("create", help="Create an invite for an email")
    p_create.add_argument("--email", required=True, help="Allowed email for this invite")
    p_create.add_argument("--label", default=None, help="Optional label (e.g., team/name)")
    p_create.add_argument("--max-uses", type=int, default=None, help="Optional max uses (default: unlimited)")
    p_create.add_argument("--expires-days", type=int, default=None, help="Optional expiry in days")
    p_create.add_argument("--expires-hours", type=int, default=None, help="Optional expiry in hours")

    p_list = sub.add_parser("list", help="List invites (no plaintext codes)")
    p_list.add_argument("--email", default=None, help="Filter by email")
    p_list.add_argument("--active-only", action="store_true", help="Only show non-revoked invites")

    p_revoke = sub.add_parser("revoke", help="Revoke invites")
    group = p_revoke.add_mutually_exclusive_group(required=True)
    group.add_argument("--id", dest="invite_id", default=None, help="Invite ID to revoke")
    group.add_argument("--email", default=None, help="Revoke all invites for this email")

    return parser.parse_args()


def _format_status(invite: dict) -> str:
    if invite.get("revoked_at"):
        return "revoked"
    expires_at = invite.get("expires_at")
    if expires_at:
        try:
            dt = datetime.fromisoformat(expires_at)
        except Exception:
            dt = None
        if dt is not None:
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            if dt < _utc_now():
                return "expired"
    return "active"


def _print_invites(invites: list[dict]) -> None:
    if not invites:
        print("No invites found.")
        return
    for inv in invites:
        status = _format_status(inv)
        print(
            f"- {status:7} id={inv['id']} email={inv.get('allowed_email') or ''}"
            f" uses={inv.get('used_count', 0)}"
            f" max={inv.get('max_uses') if inv.get('max_uses') is not None else '∞'}"
            f" label={inv.get('label') or ''}"
        )


def main() -> None:
    args = _parse_args()
    service = AuthService(db_path=args.db_path) if args.db_path else AuthService()

    if args.command == "create":
        expires_at = None
        if args.expires_days is not None:
            expires_at = _utc_now() + timedelta(days=int(args.expires_days))
        if args.expires_hours is not None:
            expires_at = _utc_now() + timedelta(hours=int(args.expires_hours))

        invite = service.create_invite(
            allowed_email=args.email,
            label=args.label,
            expires_at=expires_at,
            max_uses=args.max_uses,
        )
        print("Invite created:")
        print(f"- email: {invite.allowed_email}")
        print(f"- code:  {invite.code}")
        print(f"- id:    {invite.id}")
        return

    if args.command == "list":
        invites = service.list_invites(email=args.email, include_revoked=not args.active_only)
        _print_invites(invites)
        return

    if args.command == "revoke":
        if args.invite_id:
            ok = service.revoke_invite_by_id(args.invite_id)
            print("Revoked." if ok else "No active invite found for that id.")
            return
        count = service.revoke_invites_for_email(args.email)
        print(f"Revoked {count} invite(s) for {args.email}.")
        return


if __name__ == "__main__":
    main()

