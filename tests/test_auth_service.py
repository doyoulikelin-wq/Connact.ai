"""AuthService unit tests (invite-only + email verification)."""

from __future__ import annotations

import pytest

from src.services.auth_service import (
    AuthService,
    EmailNotVerifiedError,
    InviteInvalidError,
    InviteRequiredError,
)


def test_invite_only_password_signup_requires_valid_code(tmp_path):
    service = AuthService(
        db_path=tmp_path / "app.db",
        invite_only=True,
        invite_codes=["INV123"],
        email_verify_ttl_hours=24,
    )

    with pytest.raises(InviteRequiredError):
        service.create_password_user(email="a@example.com", password="password123")

    with pytest.raises(InviteInvalidError):
        service.create_password_user(email="a@example.com", password="password123", invite_code="NOPE")

    verification = service.create_password_user(
        email="a@example.com", password="password123", invite_code="INV123"
    )
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
        invite_codes=[],
        email_verify_ttl_hours=24,
    )
    invite = service.create_invite(allowed_email="test@example.com", label="test")

    with pytest.raises(InviteRequiredError):
        service.validate_invite_for_login(None)

    with pytest.raises(InviteInvalidError):
        service.validate_invite_for_login("NOPE", email="test@example.com")

    invite_id = service.validate_invite_for_login(invite.code, email="test@example.com")
    assert invite_id


def test_db_invite_is_bound_to_email(tmp_path):
    service = AuthService(
        db_path=tmp_path / "app.db",
        invite_only=True,
        invite_required_for_login=True,
        invite_codes=[],
        email_verify_ttl_hours=24,
    )
    invite = service.create_invite(allowed_email="bound@example.com", label="bound")

    # Signup must use the invite and match the bound email.
    verification = service.create_password_user(
        email="bound@example.com",
        password="password123",
        invite_code=invite.code,
    )
    assert verification.email == "bound@example.com"

    with pytest.raises(InviteInvalidError):
        service.create_password_user(
            email="other@example.com",
            password="password123",
            invite_code=invite.code,
        )

    # Login gating must also match the bound email.
    service.validate_invite_for_login(invite.code, email="bound@example.com")
    with pytest.raises(InviteInvalidError):
        service.validate_invite_for_login(invite.code, email="other@example.com")
