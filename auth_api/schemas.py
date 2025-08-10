"""Authentication schemas for Django Ninja."""

from typing import Optional

from pydantic import BaseModel, EmailStr


class LoginRequest(BaseModel):
    email: EmailStr
    password: str
    platform: str = "ps5"
    app_version: str = "WebApp"
    secret_answer: Optional[str] = None
    x_ut_sid: Optional[str] = None


class LoginWith2FARequest(BaseModel):
    email: EmailStr
    password: str
    platform: str = "ps5"
    app_version: str = "WebApp"
    secret_answer: Optional[str] = None
    two_factor_code: str
    x_ut_sid: Optional[str] = None


class LoginResponse(BaseModel):
    session_id: str
    persona_id: str
    persona_name: str
    club_name: str
    club_abbr: str
    fut_web_phishing: str
    fut_sid: str
    fut_sku: str
    fut_pid: str
    fut_phishing: str
    message: str = "Login successful"
