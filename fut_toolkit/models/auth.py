"""Authentication-related models."""
from dataclasses import dataclass
from typing import Optional

from ..constants import AppVersion, Platform


@dataclass
class LoginDetails:
    """Login credentials and platform information."""
    
    email: str
    password: str
    platform: Platform
    app_version: AppVersion = AppVersion.WEB_APP
    secret_answer: Optional[str] = None
    
    
@dataclass
class LoginResponse:
    """Response from login authentication."""
    
    session_id: str
    nucleus_id: str
    persona_id: str
    dob: Optional[str] = None
    email: Optional[str] = None
    country: Optional[str] = None
    
    
@dataclass
class SessionInfo:
    """Session information."""
    
    session_id: str
    persona_id: str
    nucleus_id: str
    expires_at: Optional[int] = None
