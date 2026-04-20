"""AuthService unit tests (invite-only + email verification)."""

from __future__ import annotations

import pytest

from src.services.auth_service import (
    AuthService,
    AuthError,
    AccountLockedError,
    EmailNotVerifiedError,
    InviteInvalidError,
    InviteRequiredError,
)


def test_password_signup_is_open_even_when_invite_only(tmp_path):
    """Invite-code gating has been removed from password signup; the flag is
    retained for legacy /access route only."""
    service = AuthService(
        db_path=tmp_path / "app.db",
        invite_only=True,
        invite_codes=["INV123"],
        email_verify_ttl_hours=24,
    )

    verification = service.create_password_user(email="a@example.com", password="password123")
    assert verification.email == "a@example.com"
    assert verification.token


def test_password_login_requires_email_verification(tmp_path):
    service = AuthService(
        db_path=tmp_path / "app.db",
        invite_only=True,
        invite_codes=["INV123"],
        email_verify_ttl_hours=24,
    )
    verification = service.create_password_user(
        email="b@example.com", password="password123", invite_code="INV123"
    )

    with pytest.raises(EmailNotVerifiedError):
        service.authenticate_password(email="b@example.com", password="password123")

    verified_user_id = service.verify_email_token(verification.token)
    assert verified_user_id

    user = service.authenticate_password(email="b@example.com", password="password123")
    assert user.id == verified_user_id
    assert user.primary_email == "b@example.com"


def test_resend_verification_creates_new_token(tmp_path):
    service = AuthService(
        db_path=tmp_path / "app.db",
        invite_only=True,
        invite_codes=["INV123"],
        email_verify_ttl_hours=24,
    )
    first = service.create_password_user(email="c@example.com", password="password123", invite_code="INV123")
    second = service.resend_email_verification(email="c@example.com")

    assert first.token != second.token
    assert service.verify_email_token(second.token)


def test_google_login_links_to_existing_password_user_by_verified_email(tmp_path):
    service = AuthService(
        db_path=tmp_path / "app.db",
        invite_only=True,
        invite_codes=["INV123"],
        email_verify_ttl_hours=24,
    )
    verification = service.create_password_user(
        email="d@example.com", password="password123", invite_code="INV123"
    )
    user_id = service.verify_email_token(verification.token)
    assert user_id

    user = service.authenticate_google(
        google_sub="google-sub-1",
        email="d@example.com",
        display_name="D",
        avatar_url=None,
        email_verified=True,
        invite_code=None,  # should not be needed when linking existing user
    )
    assert user.id == user_id


def test_profile_persistence_roundtrip(tmp_path):
    service = AuthService(
        db_path=tmp_path / "app.db",
        invite_only=False,
        invite_required_for_login=False,
        invite_codes=[],
        email_verify_ttl_hours=24,
    )
    verification = service.create_password_user(email="e@example.com", password="password123", invite_code=None)
    user_id = service.verify_email_token(verification.token)
    assert user_id

    sender_profile = {"name": "E", "education": ["X"], "experiences": [], "skills": [], "projects": [], "raw_text": ""}
    preferences = {"track": "finance", "location": "NYC"}

    service.update_user_profile(user_id=user_id, sender_profile=sender_profile, preferences=preferences)
    loaded = service.get_user_profile(user_id)

    assert loaded["sender_profile"]["name"] == "E"
    assert loaded["preferences"]["location"] == "NYC"


def test_invite_required_for_login_validation(tmp_path):
    service = AuthService(
        db_path=tmp_path / "app.db",
        invite_only=False,
        invite_required_for_login=True,
        invite_codes=["INV123"],
        email_verify_ttl_hours=24,
    )

    with pytest.raises(InviteRequiredError):
        service.validate_invite_for_login(None)

    with pytest.raises(InviteInvalidError):
        service.validate_invite_for_login("NOPE")

    service.validate_invite_for_login("INV123")


def test_waitlist_records_and_dedupes(tmp_path):
    service = AuthService(
        db_path=tmp_path / "app.db",
        invite_only=False,
        invite_required_for_login=False,
        invite_codes=[],
        email_verify_ttl_hours=24,
    )

    assert service.add_waitlist_email("Waitlist@Example.com", ip="127.0.0.1", user_agent="pytest") is True
    assert service.add_waitlist_email("waitlist@example.com") is False

    with pytest.raises(AuthError):
        service.add_waitlist_email("")


def test_beta_access_grant_and_check(tmp_path):
    service = AuthService(
        db_path=tmp_path / "app.db",
        invite_only=False,
        invite_required_for_login=True,
        invite_codes=["INV123"],
        email_verify_ttl_hours=24,
    )
    service.create_password_user(email="beta@example.com", password="password123", invite_code=None)

    user_id = service.get_user_id_for_password_email("beta@example.com")
    assert user_id
    assert service.user_has_beta_access(user_id) is False

    service.grant_beta_access(user_id)
    assert service.user_has_beta_access(user_id) is True

    user = service.get_user(user_id)
    assert user
    assert user.beta_access == 1
    assert user.beta_access_granted_at


# ============================================================================
# Password Complexity Tests
# ============================================================================


def test_password_must_have_two_character_categories(tmp_path):
    """Password must include at least 2 of: uppercase, lowercase, digits."""
    service = AuthService(
        db_path=tmp_path / "app.db",
        invite_only=False,
        invite_codes=[],
        email_verify_ttl_hours=24,
    )

    # All lowercase => fail (only 1 category)
    with pytest.raises(AuthError, match="uppercase.*lowercase.*digits"):
        service.create_password_user(email="a@example.com", password="abcdefgh")

    # All digits => fail
    with pytest.raises(AuthError, match="uppercase.*lowercase.*digits"):
        service.create_password_user(email="b@example.com", password="12345678")

    # lowercase + digit => pass
    v = service.create_password_user(email="c@example.com", password="abcdef12")
    assert v.token

    # uppercase + digit => pass
    v2 = service.create_password_user(email="d@example.com", password="ABCDEF12")
    assert v2.token


# ============================================================================
# Login Lockout Tests
# ============================================================================


def test_login_lockout_after_5_failures(tmp_path):
    """Account should be locked after 5 failed login attempts from same IP."""
    service = AuthService(
        db_path=tmp_path / "app.db",
        invite_only=False,
        invite_codes=[],
        email_verify_ttl_hours=24,
    )
    # Create and verify a user
    verification = service.create_password_user(
        email="lock@example.com", password="Secure123"
    )
    service.verify_email_token(verification.token)

    test_ip = "192.168.1.100"

    # 5 failed attempts
    from src.services.auth_service import InvalidCredentialsError
    for _ in range(5):
        with pytest.raises(InvalidCredentialsError):
            service.authenticate_password(
                email="lock@example.com", password="wrong", ip=test_ip
            )

    # 6th attempt should be locked
    with pytest.raises(AccountLockedError, match="Too many failed"):
        service.authenticate_password(
            email="lock@example.com", password="Secure123", ip=test_ip
        )

    # Same user but different IP should still work
    user = service.authenticate_password(
        email="lock@example.com", password="Secure123", ip="10.0.0.1"
    )
    assert user.primary_email == "lock@example.com"
