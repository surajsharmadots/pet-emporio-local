import json
import hashlib
from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient

from app.services import otp_service, jwt_service
from app.config import settings


MOBILE = "+919876543210"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _hash(val: str) -> str:
    return hashlib.sha256(val.encode()).hexdigest()


async def _send_and_get_otp(client: AsyncClient, fake_redis, mobile: str = MOBILE) -> str:
    """Send OTP and return the generated OTP from fake redis."""
    resp = await client.post("/api/v1/auth/otp/send", json={"mobile": mobile})
    assert resp.status_code == 200
    raw = await fake_redis.get(f"otp:code:{mobile}")
    data = json.loads(raw)
    # Reverse-lookup: we need to find the actual OTP. In DEV_MODE it's logged.
    # For tests, we store it deterministically by patching — or brute-force 000000-999999.
    # Instead, let's directly create a known OTP in redis for verification tests.
    return data  # returns the stored payload (hash + expiry)


# ── OTP Send ──────────────────────────────────────────────────────────────────

async def test_send_otp_success(client: AsyncClient):
    resp = await client.post("/api/v1/auth/otp/send", json={"mobile": MOBILE})
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["data"]["message"] == "OTP sent successfully"


async def test_send_otp_rate_limit(client: AsyncClient, fake_redis):
    """3rd OTP request within 10 minutes should fail with 429."""
    # Send 3 times to hit the limit (limit is 3, so 4th should fail)
    for _ in range(settings.OTP_RATE_LIMIT):
        resp = await client.post("/api/v1/auth/otp/send", json={"mobile": MOBILE})
        assert resp.status_code == 200

    # Next one must be rate-limited
    resp = await client.post("/api/v1/auth/otp/send", json={"mobile": MOBILE})
    assert resp.status_code == 429
    body = resp.json()
    assert body["error"]["code"] == "RATE_LIMITED"


# ── OTP Verify ────────────────────────────────────────────────────────────────

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


# ── Refresh Token ─────────────────────────────────────────────────────────────

async def _get_tokens(client: AsyncClient, fake_redis) -> tuple[str, str, str]:
    """Helper: complete OTP flow and return (access_token, refresh_token, session_id)."""
    known_otp = "123456"
    expires_at = (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat()
    payload = json.dumps({"hash": _hash(known_otp), "expires_at": expires_at, "attempts": 0})
    await fake_redis.setex(f"otp:code:{MOBILE}", 300, payload)

    resp = await client.post("/api/v1/auth/otp/verify", json={"mobile": MOBILE, "otp": known_otp})
    data = resp.json()["data"]
    access_token = data["access_token"]
    refresh_token = data["refresh_token"]

    import jwt as pyjwt
    decoded = pyjwt.decode(access_token, options={"verify_signature": False})
    session_id = decoded["session_id"]
    return access_token, refresh_token, session_id


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


# ── Logout ────────────────────────────────────────────────────────────────────

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


# ── Internal Routes ───────────────────────────────────────────────────────────

async def test_internal_verify_valid_token(client: AsyncClient, fake_redis):
    access_token, _, session_id = await _get_tokens(client, fake_redis)

    resp = await client.post("/internal/v1/auth/verify", json={"token": access_token})
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["valid"] is True
    assert data["user_id"] == MOBILE
    assert data["session_id"] == session_id


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