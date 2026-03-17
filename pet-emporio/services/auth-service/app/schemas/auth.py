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


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = 900  # 15 min in seconds


class RefreshRequest(BaseModel):
    refresh_token: str


class LogoutRequest(BaseModel):
    session_id: str


class SessionInfo(BaseModel):
    id: str
    device_info: Optional[str]
    ip_address: Optional[str]
    created_at: datetime
    expires_at: datetime


class GoogleAuthRequest(BaseModel):
    code: str
    redirect_uri: str


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