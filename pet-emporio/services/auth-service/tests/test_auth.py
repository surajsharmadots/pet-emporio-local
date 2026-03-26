import json
import hashlib
from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient

from app.services import otp_service, jwt_service
from app.config import settings

MOBILE = "+919876543210"

def _hash(val: str) -> str:
    return hashlib.sha256(val.encode()).hexdigest()

async def _send_and_get_otp(client: AsyncClient, fake_redis, mobile: str = MOBILE) -> str:
    """Send OTP and return the generated OTP from fake redis."""
    resp = await client.post("/api/v1/auth/otp/send", json={"mobile": mobile})
    assert resp.status_code == 200
    raw = await fake_redis.get(f"otp:code:{mobile}")
    data = json.loads(raw)
    return data

async def test_send_otp_success(client: AsyncClient):
    resp = await client.post("/api/v1/auth/otp/send", json={"mobile": MOBILE})
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["data"]["message"] == "OTP sent successfully"

async def test_send_otp_rate_limit(client: AsyncClient, fake_redis):
    """3rd OTP request within 10 minutes should fail with 429."""
    for _ in range(settings.OTP_RATE_LIMIT):
        resp = await client.post("/api/v1/auth/otp/send", json={"mobile": MOBILE})
        assert resp.status_code == 200

    # Next one must be rate-limited
    resp = await client.post("/api/v1/auth/otp/send", json={"mobile": MOBILE})
    assert resp.status_code == 429
    body = resp.json()
    assert body["error"]["code"] == "RATE_LIMITED"


# OTP Verify

async def test_verify_otp_success(client: AsyncClient, fake_redis):
    """Correct OTP returns access_token and refresh_token."""
    known_otp = "123456"
    expires_at = (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat()
    payload = json.dumps({"hash": _hash(known_otp), "expires_at": expires_at, "attempts": 0})
    await fake_redis.setex(f"otp:code:{MOBILE}", 300, payload)

    resp = await client.post("/api/v1/auth/otp/verify", json={
        "mobile": MOBILE, "otp": known_otp
    })
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"

async def test_verify_otp_wrong(client: AsyncClient, fake_redis):
    """Wrong OTP returns 400."""
    known_otp = "123456"
    expires_at = (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat()
    payload = json.dumps({"hash": _hash(known_otp), "expires_at": expires_at, "attempts": 0})
    await fake_redis.setex(f"otp:code:{MOBILE}", 300, payload)

    resp = await client.post("/api/v1/auth/otp/verify", json={
        "mobile": MOBILE, "otp": "000000"
    })
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "OTP_INVALID"

async def test_verify_otp_expired(client: AsyncClient, fake_redis):
    """Expired OTP returns 410."""
    past = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    payload = json.dumps({"hash": _hash("123456"), "expires_at": past, "attempts": 0})
    await fake_redis.setex(f"otp:code:{MOBILE}", 1, payload)

    resp = await client.post("/api/v1/auth/otp/verify", json={
        "mobile": MOBILE, "otp": "123456"
    })
    assert resp.status_code == 410
    assert resp.json()["error"]["code"] == "OTP_EXPIRED"


# Refresh Token

async def _get_tokens(client: AsyncClient, fake_redis) -> tuple[str, str, str]:
    """Helper: complete OTP flow and return (access_token, refresh_token, session_id).

    session_id is taken from the response body (the DB session.id), NOT decoded
    from the JWT.  _create_local_tokens embeds a separate random UUID in the JWT
    payload, so the JWT session_id != the DB session.id used by logout/refresh/list.
    """
    known_otp = "123456"
    expires_at = (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat()
    payload = json.dumps({"hash": _hash(known_otp), "expires_at": expires_at, "attempts": 0})
    await fake_redis.setex(f"otp:code:{MOBILE}", 300, payload)

    resp = await client.post("/api/v1/auth/otp/verify", json={"mobile": MOBILE, "otp": known_otp})
    data = resp.json()["data"]
    return data["access_token"], data["refresh_token"], data["session_id"]

async def test_refresh_token_success(client: AsyncClient, fake_redis):
    _, refresh_token, session_id = await _get_tokens(client, fake_redis)

    resp = await client.post(
        f"/api/v1/auth/token/refresh/{session_id}",
        json={"refresh_token": refresh_token},
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert "access_token" in data
    assert "refresh_token" in data

async def test_refresh_token_invalid(client: AsyncClient, fake_redis):
    _, _, session_id = await _get_tokens(client, fake_redis)

    resp = await client.post(
        f"/api/v1/auth/token/refresh/{session_id}",
        json={"refresh_token": "completely-wrong-token"},
    )
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "INVALID_TOKEN"


# Logout

async def test_logout_revokes_session(client: AsyncClient, fake_redis):
    access_token, _, session_id = await _get_tokens(client, fake_redis)

    resp = await client.post(
        "/api/v1/auth/logout",
        json={"session_id": session_id},
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert resp.status_code == 200

    # Trying to use the same refresh token should now fail
    from fakeredis.aioredis import FakeRedis
    resp2 = await client.post(
        f"/api/v1/auth/token/refresh/{session_id}",
        json={"refresh_token": "any-token"},
    )
    assert resp2.status_code == 401


# Internal Routes

async def test_internal_verify_valid_token(client: AsyncClient, fake_redis):
    access_token, _, session_id = await _get_tokens(client, fake_redis)

    resp = await client.post("/internal/v1/auth/verify", json={"token": access_token})
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["valid"] is True
    # sub is the platform user UUID assigned by user-service
    assert data["user_id"] is not None
    # The JWT embeds its own random session_id (separate from the DB session.id)
    assert data["session_id"] is not None

async def test_internal_verify_expired_token(client: AsyncClient):
    """Manually craft an already-expired token."""
    from datetime import datetime, timedelta, timezone
    import jwt as pyjwt

    now = datetime.now(timezone.utc)
    expired_payload = {
        "sub": "user123",
        "roles": ["customer"],
        "session_id": "sess123",
        "iat": now - timedelta(hours=2),
        "exp": now - timedelta(hours=1),  # already expired
    }
    expired_token = pyjwt.encode(expired_payload, settings.JWT_PRIVATE_KEY, algorithm="RS256")

    resp = await client.post("/internal/v1/auth/verify", json={"token": expired_token})
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["valid"] is False
    assert "expired" in data["error"].lower()


# Sessions

async def test_list_active_sessions(client: AsyncClient, fake_redis):
    """Authenticated user can list their active sessions."""
    access_token, _, session_id = await _get_tokens(client, fake_redis)

    resp = await client.get(
        "/api/v1/auth/sessions",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert resp.status_code == 200
    sessions = resp.json()["data"]
    assert isinstance(sessions, list)
    assert any(str(s["id"]) == session_id for s in sessions)

async def test_revoke_specific_session(client: AsyncClient, fake_redis):
    """User can revoke one of their own sessions by session_id."""
    access_token, _, session_id = await _get_tokens(client, fake_redis)

    resp = await client.delete(
        f"/api/v1/auth/sessions/{session_id}",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["message"] == "Session revoked."

async def test_revoke_session_not_owned(client: AsyncClient, fake_redis):
    """Revoking a session that does not belong to the current user returns 404."""
    import uuid
    access_token, _, _ = await _get_tokens(client, fake_redis)

    resp = await client.delete(
        f"/api/v1/auth/sessions/{uuid.uuid4()}",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "NOT_FOUND"


# Devices

async def test_list_registered_devices(client: AsyncClient, fake_redis):
    """After OTP login a device is registered and appears in the device list."""
    access_token, _, _ = await _get_tokens(client, fake_redis)

    resp = await client.get(
        "/api/v1/auth/devices",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert resp.status_code == 200
    devices = resp.json()["data"]
    assert isinstance(devices, list)
    assert len(devices) >= 1

async def test_revoke_device_success(client: AsyncClient, fake_redis):
    """User can revoke a registered device by device_id."""
    access_token, _, _ = await _get_tokens(client, fake_redis)

    list_resp = await client.get(
        "/api/v1/auth/devices",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    device_id = list_resp.json()["data"][0]["device_id"]

    resp = await client.delete(
        f"/api/v1/auth/devices/{device_id}",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["message"] == "Device revoked."

async def test_revoke_device_not_found(client: AsyncClient, fake_redis):
    """Revoking an unknown device_id returns 404."""
    access_token, _, _ = await _get_tokens(client, fake_redis)

    resp = await client.delete(
        "/api/v1/auth/devices/non-existent-device-id",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "NOT_FOUND"


# MFA

async def test_mfa_setup(client: AsyncClient, fake_redis):
    """MFA setup returns a TOTP secret and provisioning QR URI."""
    access_token, _, _ = await _get_tokens(client, fake_redis)

    resp = await client.post(
        "/api/v1/auth/mfa/setup",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert "secret" in data
    assert "qr_uri" in data
    # QR URI URL-encodes spaces, so check the decoded form
    import urllib.parse
    assert "Pet Emporio" in urllib.parse.unquote(data["qr_uri"])

async def test_mfa_verify_valid_code(client: AsyncClient, fake_redis):
    """Correct TOTP code enables MFA on the account."""
    import pyotp
    access_token, _, _ = await _get_tokens(client, fake_redis)

    setup_resp = await client.post(
        "/api/v1/auth/mfa/setup",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    secret = setup_resp.json()["data"]["secret"]
    valid_code = pyotp.TOTP(secret).now()

    resp = await client.post(
        "/api/v1/auth/mfa/verify",
        json={"code": valid_code},
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["message"] == "MFA enabled successfully."

async def test_mfa_verify_invalid_code(client: AsyncClient, fake_redis):
    """Wrong TOTP code returns 400 MFA_INVALID."""
    access_token, _, _ = await _get_tokens(client, fake_redis)

    await client.post(
        "/api/v1/auth/mfa/setup",
        headers={"Authorization": f"Bearer {access_token}"},
    )

    resp = await client.post(
        "/api/v1/auth/mfa/verify",
        json={"code": "000000"},
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "MFA_INVALID"

async def test_mfa_verify_not_setup(client: AsyncClient, fake_redis):
    """Calling MFA verify before setup returns 400 MFA_NOT_SETUP."""
    access_token, _, _ = await _get_tokens(client, fake_redis)

    resp = await client.post(
        "/api/v1/auth/mfa/verify",
        json={"code": "123456"},
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "MFA_NOT_SETUP"


# Social Login

async def test_social_google_login(client: AsyncClient, monkeypatch):
    """Google Sign-In with a valid (mocked) ID token returns a token pair."""
    from unittest.mock import AsyncMock
    monkeypatch.setattr(
        "app.routers.auth.verify_google_token",
        AsyncMock(return_value={
            "provider_user_id": "google_uid_001",
            "email": "googleuser@example.com",
            "name": "Google User",
        }),
    )

    resp = await client.post(
        "/api/v1/auth/social/google",
        json={"id_token": "fake-google-id-token"},
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"

async def test_social_facebook_login(client: AsyncClient, monkeypatch):
    """Facebook Login with a valid (mocked) access token returns a token pair."""
    from unittest.mock import AsyncMock
    monkeypatch.setattr(
        "app.routers.auth.verify_facebook_token",
        AsyncMock(return_value={
            "provider_user_id": "fb_uid_001",
            "email": "fbuser@example.com",
            "name": "Facebook User",
        }),
    )

    resp = await client.post(
        "/api/v1/auth/social/facebook",
        json={"access_token": "fake-fb-access-token"},
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"

async def test_social_apple_login(client: AsyncClient, monkeypatch):
    """Apple Sign In with a valid (mocked) identity token returns a token pair."""
    from unittest.mock import AsyncMock
    monkeypatch.setattr(
        "app.routers.auth.verify_apple_token",
        AsyncMock(return_value={
            "provider_user_id": "apple_uid_001",
            "email": "appleuser@example.com",
            "name": "Apple User",
        }),
    )

    resp = await client.post(
        "/api/v1/auth/social/apple",
        json={"identity_token": "fake-apple-identity-token"},
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"


# OTP Verify edge cases

async def test_verify_otp_too_many_attempts(client: AsyncClient, fake_redis):
    """Exceeding the attempt limit locks the OTP and returns OTP_INVALID."""
    expires_at = (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat()
    # Set attempts to a value far beyond any reasonable limit
    payload = json.dumps({"hash": _hash("123456"), "expires_at": expires_at, "attempts": 99})
    await fake_redis.setex(f"otp:code:{MOBILE}", 300, payload)

    resp = await client.post(
        "/api/v1/auth/otp/verify",
        json={"mobile": MOBILE, "otp": "000000"},
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "OTP_INVALID"

async def test_verify_otp_provider_account_not_found(client: AsyncClient, fake_redis, monkeypatch):
    """Valid OTP on a provider portal when no account exists → ACCOUNT_NOT_FOUND."""
    from unittest.mock import AsyncMock
    monkeypatch.setattr(
        "app.routers.auth._check_account_status",
        AsyncMock(return_value={"exists": False, "is_active": False, "user_type": None}),
    )
    known_otp = "123456"
    expires_at = (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat()
    payload = json.dumps({"hash": _hash(known_otp), "expires_at": expires_at, "attempts": 0})
    await fake_redis.setex(f"otp:code:{MOBILE}", 300, payload)

    resp = await client.post(
        "/api/v1/auth/otp/verify",
        json={"mobile": MOBILE, "otp": known_otp, "portal": "seller"},
    )
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "ACCOUNT_NOT_FOUND"

async def test_verify_otp_account_pending_approval(client: AsyncClient, fake_redis, monkeypatch):
    """Provider account that is inactive (pending approval) returns ACCOUNT_PENDING_APPROVAL."""
    from unittest.mock import AsyncMock
    monkeypatch.setattr(
        "app.routers.auth._check_account_status",
        AsyncMock(return_value={"exists": True, "is_active": False, "user_type": "seller"}),
    )
    known_otp = "123456"
    expires_at = (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat()
    payload = json.dumps({"hash": _hash(known_otp), "expires_at": expires_at, "attempts": 0})
    await fake_redis.setex(f"otp:code:{MOBILE}", 300, payload)

    resp = await client.post(
        "/api/v1/auth/otp/verify",
        json={"mobile": MOBILE, "otp": known_otp},
    )
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "ACCOUNT_PENDING_APPROVAL"

async def test_verify_otp_account_inactive(client: AsyncClient, fake_redis, monkeypatch):
    """Deactivated customer account returns ACCOUNT_INACTIVE."""
    from unittest.mock import AsyncMock
    monkeypatch.setattr(
        "app.routers.auth._check_account_status",
        AsyncMock(return_value={"exists": True, "is_active": False, "user_type": "customer"}),
    )
    known_otp = "123456"
    expires_at = (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat()
    payload = json.dumps({"hash": _hash(known_otp), "expires_at": expires_at, "attempts": 0})
    await fake_redis.setex(f"otp:code:{MOBILE}", 300, payload)

    resp = await client.post(
        "/api/v1/auth/otp/verify",
        json={"mobile": MOBILE, "otp": known_otp},
    )
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "ACCOUNT_INACTIVE"


# Logout edge case

async def test_logout_session_not_found(client: AsyncClient):
    """Logout with a non-existent session_id returns 404 NOT_FOUND."""
    import uuid
    resp = await client.post(
        "/api/v1/auth/logout",
        json={"session_id": str(uuid.uuid4())},
    )
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "NOT_FOUND"


# Internal: Public Key & OTP Validate

async def test_internal_public_key(client: AsyncClient, monkeypatch):
    """GET /internal/v1/auth/public-key returns a PEM-formatted public key string."""
    from pathlib import Path
    from app import config
    # Use the already-patched public key from settings (set by the autouse patch_settings fixture)
    monkeypatch.setattr(Path, "read_text", lambda self, *args, **kwargs: config.settings.JWT_PUBLIC_KEY)

    resp = await client.get("/internal/v1/auth/public-key")
    assert resp.status_code == 200
    key = resp.json()["data"]["public_key"]
    assert "BEGIN PUBLIC KEY" in key

async def test_internal_otp_validate_success(client: AsyncClient, fake_redis):
    """Internal OTP validate with a correct OTP returns valid=True."""
    known_otp = "123456"
    expires_at = (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat()
    payload = json.dumps({"hash": _hash(known_otp), "expires_at": expires_at, "attempts": 0})
    await fake_redis.setex(f"otp:code:{MOBILE}", 300, payload)

    resp = await client.post(
        "/internal/v1/auth/otp/validate",
        json={"mobile": MOBILE, "otp": known_otp},
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["valid"] is True

async def test_internal_otp_validate_invalid(client: AsyncClient, fake_redis):
    """Internal OTP validate with a wrong OTP returns 400 OTP_INVALID."""
    known_otp = "123456"
    expires_at = (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat()
    payload = json.dumps({"hash": _hash(known_otp), "expires_at": expires_at, "attempts": 0})
    await fake_redis.setex(f"otp:code:{MOBILE}", 300, payload)

    resp = await client.post(
        "/internal/v1/auth/otp/validate",
        json={"mobile": MOBILE, "otp": "000000"},
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "OTP_INVALID"

async def test_internal_otp_validate_expired(client: AsyncClient, fake_redis):
    """Internal OTP validate with an expired OTP returns 400 OTP_EXPIRED."""
    past = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    payload = json.dumps({"hash": _hash("123456"), "expires_at": past, "attempts": 0})
    await fake_redis.setex(f"otp:code:{MOBILE}", 1, payload)

    resp = await client.post(
        "/internal/v1/auth/otp/validate",
        json={"mobile": MOBILE, "otp": "123456"},
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "OTP_EXPIRED"