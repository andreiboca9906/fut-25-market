"""Session management for maintaining authenticated sessions."""
from typing import Dict, Optional

import httpx

from ..models.auth import SessionInfo


class SessionManager:
    """Manages authenticated sessions and cookie persistence."""
    
    def __init__(self):
        self.sessions: Dict[str, httpx.Cookies] = {}
        self.session_info: Dict[str, SessionInfo] = {}
        
    def store_session(self, user_id: str, cookies: httpx.Cookies, session_info: SessionInfo):
        """Store session cookies and info for a user."""
        self.sessions[user_id] = cookies
        self.session_info[user_id] = session_info
        
    def get_session(self, user_id: str) -> Optional[httpx.Cookies]:
        """Get stored session cookies for a user."""
        return self.sessions.get(user_id)
        
    def get_session_info(self, user_id: str) -> Optional[SessionInfo]:
        """Get stored session info for a user."""
        return self.session_info.get(user_id)
        
    def remove_session(self, user_id: str):
        """Remove session for a user."""
        self.sessions.pop(user_id, None)
        self.session_info.pop(user_id, None)
        
    def is_session_valid(self, user_id: str) -> bool:
        """Check if user has a valid session."""
        return user_id in self.sessions and user_id in self.session_info


# Global session manager instance
session_manager = SessionManager()
