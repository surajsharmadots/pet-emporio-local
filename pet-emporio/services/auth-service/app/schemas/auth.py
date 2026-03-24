from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class OtpSendRequest(BaseModel):
    mobile: str = Field(..., pattern=r"^\+?[1-9]\d{7,14}$")


class OtpSendResponse(BaseModel):
    message: str = "OTP sent successfully"
    expires_in: int = 300


class OtpVerifyRequest(BaseModel):
    mobile: str
    otp: str = Field(..., min_length=6, max_length=6)
    device_info: Optional[str] = None
    remember_me: bool = False
    portal: Optional[str] = None  # "customer" (default) | "doctor" | "seller" | "lab" | "pharmacy" | "groomer" | "admin"


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    session_id: str
    token_type: str = "bearer"
    expires_in: int = 900  # 15 min in seconds


class RefreshRequest(BaseModel):
    refresh_token: str


class LogoutRequest(BaseModel):
    session_id: str


class SessionInfo(BaseModel):
    id: str
    device_info: Optional[str] = None
    ip_address: Optional[str] = None
    created_at: datetime
    expires_at: datetime


class GoogleAuthRequest(BaseModel):
    id_token: str                        # ID token from Google Sign-In SDK
    device_info: Optional[str] = None
    remember_me: bool = False


class FacebookAuthRequest(BaseModel):
    access_token: str
    device_info: Optional[str] = None
    remember_me: bool = False


class AppleAuthRequest(BaseModel):
    identity_token: str
    device_info: Optional[str] = None
    remember_me: bool = False


class MfaSetupResponse(BaseModel):
    secret: str
    qr_uri: str


class MfaVerifyRequest(BaseModel):
    code: str = Field(..., min_length=6, max_length=6)


class InternalVerifyRequest(BaseModel):
    token: str


class InternalVerifyResponse(BaseModel):
    valid: bool
    user_id: Optional[str] = None
    tenant_id: Optional[str] = None
    roles: Optional[list[str]] = None
    session_id: Optional[str] = None
    error: Optional[str] = None