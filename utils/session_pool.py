import os
import random
from datetime import timedelta
from typing import Dict, Optional

from django.core.cache import cache
from django.utils import timezone

from players.models import SessionUsage


class SessionPool:
    """
    Manage multiple EA accounts for load distribution.
    - Rotate sessions to avoid overuse
    - Track request count per session
    - Automatic cooldown periods
    - Session health monitoring
    """

    def __init__(self):
        self.max_requests_per_hour = int(os.getenv("MAX_REQUESTS_PER_SESSION_HOUR", "500"))
        self.cooldown_requests = int(os.getenv("SESSION_COOLDOWN_REQUESTS", "100"))
        self.cooldown_duration = int(os.getenv("SESSION_COOLDOWN_DURATION", "900"))  # 15 minutes

    def get_next_session(self) -> Optional[Dict]:
        """
        Get least recently used session that is healthy and not in cooldown.

        Returns:
            Session dict with id and credentials, or None if all sessions are unavailable
        """
        # Get all healthy sessions not in cooldown
        now = timezone.now()
        available_sessions = (
            SessionUsage.objects.filter(is_healthy=True)
            .exclude(cooldown_until__gt=now)
            .order_by("last_used", "requests_count")
        )

        if not available_sessions.exists():
            return None

        # Get least recently used session with lowest request count
        session = available_sessions.first()

        # Check hourly rate limit
        hour_ago = now - timedelta(hours=1)
        cache_key = f"session_requests_{session.session_id}_{hour_ago.hour}"
        hourly_requests = cache.get(cache_key, 0)

        if hourly_requests >= self.max_requests_per_hour:
            # Mark session for cooldown
            session.cooldown_until = now + timedelta(seconds=self.cooldown_duration)
            session.save()
            # Try next session
            return self.get_next_session()

        # Check if needs cooldown after consecutive requests
        if session.requests_count >= self.cooldown_requests:
            session.cooldown_until = now + timedelta(seconds=self.cooldown_duration)
            session.requests_count = 0
            session.save()
            # Try next session
            return self.get_next_session()

        # Update session usage
        session.requests_count += 1
        session.last_used = now
        session.save()

        # Update hourly counter
        cache.set(cache_key, hourly_requests + 1, 3600)

        # Return session credentials (would come from secure storage in production)
        return {"session_id": session.session_id, "credentials": self._get_session_credentials(session.session_id)}

    def mark_session_unhealthy(self, session_id: str, reason: str = None):
        """Mark a session as unhealthy due to errors."""
        try:
            session = SessionUsage.objects.get(session_id=session_id)
            session.is_healthy = False
            session.save()
        except SessionUsage.DoesNotExist:
            pass

    def reset_session_cooldown(self, session_id: str):
        """Reset cooldown for a specific session."""
        try:
            session = SessionUsage.objects.get(session_id=session_id)
            session.cooldown_until = None
            session.requests_count = 0
            session.save()
        except SessionUsage.DoesNotExist:
            pass

    def get_session_stats(self) -> Dict:
        """Get statistics about all sessions."""
        now = timezone.now()
        total = SessionUsage.objects.count()
        healthy = SessionUsage.objects.filter(is_healthy=True).count()
        in_cooldown = SessionUsage.objects.filter(cooldown_until__gt=now).count()

        return {
            "total_sessions": total,
            "healthy_sessions": healthy,
            "in_cooldown": in_cooldown,
            "available": healthy - in_cooldown,
        }

    def _get_session_credentials(self, session_id: str) -> Dict:
        """
        Get credentials for a session.
        In production, this would fetch from secure storage like AWS Secrets Manager.
        """
        # Placeholder - would integrate with actual credential storage
        return {
            "email": os.getenv(f"EA_SESSION_{session_id}_EMAIL"),
            "password": os.getenv(f"EA_SESSION_{session_id}_PASSWORD"),
            "token": cache.get(f"session_token_{session_id}"),
        }

    def weighted_random_selection(self, sessions):
        """
        Select a session using weighted random selection based on usage.
        Sessions with lower usage get higher probability of being selected.
        """
        if not sessions:
            return None

        # Calculate weights (inverse of request count)
        weights = []
        for session in sessions:
            weight = max(1, 100 - session.requests_count)
            weights.append(weight)

        # Weighted random choice
        total_weight = sum(weights)
        random_num = random.uniform(0, total_weight)

        current_weight = 0
        for session, weight in zip(sessions, weights):
            current_weight += weight
            if random_num <= current_weight:
                return session

        return sessions[-1]  # Fallback to last session
