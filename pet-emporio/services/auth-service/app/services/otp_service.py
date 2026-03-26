import hashlib
import json
import random
import string
from datetime import datetime, timedelta, timezone

import httpx
import redis.asyncio as aioredis
from pe_common.logging import get_logger

from ..config import settings

logger = get_logger(__name__)

OTP_KEY_PREFIX = "otp:code:"
RATE_KEY_PREFIX = "otp:rate:"

MSG91_SEND_URL = "https://control.msg91.com/api/v5/otp"


def _generate_otp() -> str:
    return "".join(random.choices(string.digits, k=6))


def _hash_otp(otp: str) -> str:
    return hashlib.sha256(otp.encode()).hexdigest()


def _normalize_mobile(mobile: str) -> str:
    """
    MSG91 requires mobile in format: 919876543210 (country code + number, no + or spaces).
    Input can be: +919876543210 or 919876543210 or 9876543210
    """
    mobile = mobile.strip().replace(" ", "").replace("-", "")
    if mobile.startswith("+"):
        mobile = mobile[1:]
    if len(mobile) == 10:
        mobile = "91" + mobile
    return mobile


async def _send_via_msg91(mobile: str, otp: str) -> bool:
    """
    Send OTP via MSG91. Returns True on success, False on failure.
    Docs: https://docs.msg91.com/reference/send-otp
    """
    normalized = _normalize_mobile(mobile)

    headers = {
        "authkey": settings.MSG91_AUTH_KEY,
        "content-type": "application/json",
        "accept": "application/json",
    }
    payload = {
        "template_id": settings.MSG91_TEMPLATE_ID,
        "mobile": normalized,
        "otp": otp,
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(MSG91_SEND_URL, json=payload, headers=headers)
            data = response.json()

            if response.status_code == 200 and data.get("type") == "success":
                logger.info("otp_sent_msg91", mobile=mobile)
                return True
            else:
                logger.error("msg91_send_failed", mobile=mobile, response=data)
                return False

    except Exception as e:
        logger.error("msg91_request_error", mobile=mobile, error=str(e))
        return False


async def check_rate_limit(redis: aioredis.Redis, mobile: str) -> bool:
    """Returns True if under rate limit, False if limit exceeded."""
    key = f"{RATE_KEY_PREFIX}{mobile}"
    count = await redis.get(key)
    if count and int(count) >= settings.OTP_RATE_LIMIT:
        return False
    return True


async def send_otp(redis: aioredis.Redis, mobile: str) -> bool:
    """
    Generate OTP, store in Redis, and send via MSG91 (prod) or log to terminal (dev).
    Returns True on success.
    """
    rate_key = f"{RATE_KEY_PREFIX}{mobile}"
    otp_key = f"{OTP_KEY_PREFIX}{mobile}"

    # Check if OTP already exists
    existing_otp = await redis.get(otp_key)
    existing_ttl = await redis.ttl(otp_key)
    
    logger.info("otp_send_check", 
                otp_key=otp_key,
                existing_otp_exists=existing_otp is not None,
                existing_ttl=existing_ttl)

    # Increment rate counter
    pipe = redis.pipeline()
    pipe.incr(rate_key)
    pipe.expire(rate_key, settings.OTP_RATE_WINDOW_SECONDS)
    await pipe.execute()

    # otp = _generate_otp()
    otp = "123456"  # Hardcoded for testing
    otp_hash = _hash_otp(otp)
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=settings.OTP_EXPIRE_SECONDS)

    payload = json.dumps({
        "hash": otp_hash,
        "expires_at": expires_at.isoformat(),
        "attempts": 0,
    })
    
    logger.info("otp_redis_debug", 
                otp_key=otp_key, 
                expire_seconds=settings.OTP_EXPIRE_SECONDS,
                expires_at=expires_at.isoformat())
    
    await redis.setex(otp_key, settings.OTP_EXPIRE_SECONDS, payload)
    
    # Verify TTL was set correctly
    ttl = await redis.ttl(otp_key)
    logger.info("otp_ttl_check", otp_key=otp_key, ttl=ttl)

    if settings.DEV_MODE:
        # Dev mode: print OTP in terminal (no real SMS sent)
        logger.info("DEV MODE — OTP not sent via SMS", mobile=mobile, otp=otp)
        return True
    else:
        # Production: send via MSG91
        if not settings.MSG91_AUTH_KEY or not settings.MSG91_TEMPLATE_ID:
            logger.error("msg91_not_configured", detail="MSG91_AUTH_KEY or MSG91_TEMPLATE_ID is missing in .env")
            return False
        return await _send_via_msg91(mobile, otp)


async def verify_otp(redis: aioredis.Redis, mobile: str, otp: str) -> str:
    """
    Verify OTP. Returns one of: 'ok', 'expired', 'invalid', 'too_many_attempts'.
    """
    otp_key = f"{OTP_KEY_PREFIX}{mobile}"
    raw = await redis.get(otp_key)

    if raw is None:
        return "expired"

    data = json.loads(raw)
    expires_at = datetime.fromisoformat(data["expires_at"])

    # Support both tz-aware and tz-naive datetimes
    now = datetime.now(timezone.utc)
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)

    if now > expires_at:
        await redis.delete(otp_key)
        return "expired"

    if data["attempts"] >= 5:
        await redis.delete(otp_key)
        return "too_many_attempts"

    if _hash_otp(otp) != data["hash"]:
        data["attempts"] += 1
        await redis.setex(otp_key, settings.OTP_EXPIRE_SECONDS, json.dumps(data))
        return "invalid"

    # Valid — clean up
    await redis.delete(otp_key)
    return "ok"