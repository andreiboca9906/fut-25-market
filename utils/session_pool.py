import asyncio
import logging
import os
import random
from datetime import timedelta
from enum import Enum
from typing import Dict, List, Optional, Set, Tuple

from asgiref.sync import sync_to_async
from django.core.cache import cache
from django.db import connection
from django.utils import timezone

logger = logging.getLogger(__name__)


class SessionPriority(Enum):
    """Priority levels for session allocation."""

    HIGH = "high"  # For HOT tier cards
    MEDIUM = "medium"  # For TRENDING/ACTIVE tiers
    LOW = "low"  # For NORMAL/COLD tiers


class SessionPool:
    """
    Manage multiple EA accounts for load distribution.
    Uses ea_accounts table which has:
    - id: account ID
    - email: account email
    - session_id: EA session token (updated by external process)
    - is_expired: whether session is still valid
    - last_updated: when session was last updated

    Features:
    - Rotate sessions to avoid overuse
    - Track request count per session (in cache)
    - Automatic cooldown periods
    - Session health monitoring
    """

    def __init__(self):
        self.max_requests_per_hour = int(os.getenv("MAX_REQUESTS_PER_SESSION_HOUR", "500"))
        self.cooldown_requests = int(os.getenv("SESSION_COOLDOWN_REQUESTS", "100"))
        self.cooldown_duration = int(os.getenv("SESSION_COOLDOWN_DURATION", "900"))  # 15 minutes

        # Session rotation settings
        self.rotation_interval = 300  # 5 minutes
        self.dedicated_high_priority_sessions: Set[int] = set()  # Account IDs
        self.session_locks: Dict[int, asyncio.Lock] = {}
        self.session_priority_map: Dict[int, SessionPriority] = {}  # Account ID to priority

    @sync_to_async
    def _get_active_sessions(self) -> List[Tuple]:
        """Get all active sessions from ea_accounts table."""
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT id, email, session_id, last_updated
                FROM ea_accounts
                WHERE session_id IS NOT NULL
                AND is_expired = FALSE
                ORDER BY last_updated DESC
            """)
            return cursor.fetchall()

    @sync_to_async
    def _get_session_by_id(self, account_id: int) -> Optional[Tuple]:
        """Get a specific session by account ID."""
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, email, session_id, last_updated
                FROM ea_accounts
                WHERE id = %s
                AND session_id IS NOT NULL
                AND is_expired = FALSE
            """,
                [account_id],
            )
            return cursor.fetchone()

    @sync_to_async
    def _mark_session_expired(self, account_id: int):
        """Mark a session as expired in the database."""
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE ea_accounts
                SET is_expired = TRUE
                WHERE id = %s
            """,
                [account_id],
            )

    def get_next_session(self) -> Optional[Dict]:
        """
        Synchronous version for backward compatibility.
        Get least recently used session that is healthy and not in cooldown.

        Returns:
            Session dict with id and credentials, or None if all sessions are unavailable
        """
        # This is a simplified synchronous version
        # For the full async functionality, use get_session_for_tier
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT id, email, session_id
                FROM ea_accounts
                WHERE session_id IS NOT NULL
                AND is_expired = FALSE
                ORDER BY RANDOM()
                LIMIT 1
            """)
            row = cursor.fetchone()

            if not row:
                return None

            account_id, email, session_id = row

            # Check cooldown
            now = timezone.now()
            cooldown_key = f"session_cooldown_{account_id}"
            if cache.get(cooldown_key):
                return self.get_next_session()  # Try another

            # Update usage
            requests_key = f"session_requests_{account_id}"
            requests_count = cache.get(requests_key, 0)

            # Check limits
            if requests_count >= self.cooldown_requests:
                cache.set(cooldown_key, True, self.cooldown_duration)
                return self.get_next_session()

            # Update counters
            cache.set(requests_key, requests_count + 1, 3600)

            return {
                "session_id": session_id,
                "account_id": account_id,
                "email": email,
            }

    def mark_session_unhealthy(self, account_id: int, reason: str = None):
        """Mark a session as unhealthy (expired) due to errors."""
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE ea_accounts
                SET is_expired = TRUE
                WHERE id = %s
            """,
                [account_id],
            )

        if reason:
            logger.warning(f"Session {account_id} marked unhealthy: {reason}")

    def reset_session_cooldown(self, account_id: int):
        """Reset cooldown for a specific session."""
        cooldown_key = f"session_cooldown_{account_id}"
        requests_key = f"session_requests_{account_id}"
        cache.delete(cooldown_key)
        cache.delete(requests_key)

    def get_session_stats(self) -> Dict:
        """Get statistics about all sessions."""
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT
                    COUNT(*) as total,
                    COUNT(CASE WHEN session_id IS NOT NULL AND is_expired = FALSE THEN 1 END) as active,
                    COUNT(CASE WHEN is_expired = TRUE THEN 1 END) as expired
                FROM ea_accounts
            """)
            row = cursor.fetchone()

            if not row:
                return {"total_sessions": 0, "active_sessions": 0, "expired_sessions": 0}

            total, active, expired = row

            # Count sessions in cooldown
            in_cooldown = 0
            cursor.execute("SELECT id FROM ea_accounts WHERE session_id IS NOT NULL")
            for (account_id,) in cursor.fetchall():
                if cache.get(f"session_cooldown_{account_id}"):
                    in_cooldown += 1

            return {
                "total_sessions": total,
                "active_sessions": active,
                "expired_sessions": expired,
                "in_cooldown": in_cooldown,
                "available": active - in_cooldown,
            }

    def _get_session_credentials(self, account_id: int) -> Dict:
        """
        Get credentials for a session.
        In production, this would fetch from secure storage like AWS Secrets Manager.
        """
        # Get session from database
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT email, session_id
                FROM ea_accounts
                WHERE id = %s
            """,
                [account_id],
            )
            row = cursor.fetchone()

            if not row:
                return {}

            email, session_id = row
            return {
                "email": email,
                "session_id": session_id,
            }

    def weighted_random_selection(self, sessions: List[Tuple]) -> Optional[Tuple]:
        """
        Select a session using weighted random selection based on usage.
        Sessions with lower usage get higher probability of being selected.
        """
        if not sessions:
            return None

        # Calculate weights (inverse of request count)
        weights = []
        for session in sessions:
            account_id = session[0]
            requests_key = f"session_requests_{account_id}"
            requests_count = cache.get(requests_key, 0)
            weight = max(1, 100 - requests_count)
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

    async def get_session_for_tier(self, tier: str) -> Optional[Dict]:
        """
        Get appropriate session based on player tier with smart rotation.

        Args:
            tier: Player tier (HOT, TRENDING, ACTIVE, NORMAL, COLD)

        Returns:
            Session dict with credentials or None
        """
        # Map tier to priority
        priority_map = {
            "HOT": SessionPriority.HIGH,
            "TRENDING": SessionPriority.MEDIUM,
            "ACTIVE": SessionPriority.MEDIUM,
            "NORMAL": SessionPriority.LOW,
            "COLD": SessionPriority.LOW,
        }

        priority = priority_map.get(tier, SessionPriority.LOW)

        # Try to get dedicated session for high priority
        if priority == SessionPriority.HIGH:
            session = await self._get_dedicated_session(priority)
            if session:
                return session

        # Get session with rotation strategy
        return await self._rotate_session(priority)

    async def _get_dedicated_session(self, priority: SessionPriority) -> Optional[Dict]:
        """Get or allocate dedicated session for high priority requests."""
        # Check if we have dedicated sessions
        if self.dedicated_high_priority_sessions:
            for account_id in self.dedicated_high_priority_sessions:
                session = await self._get_session_by_id(account_id)

                if session:
                    # Check if not in cooldown
                    cooldown_key = f"session_cooldown_{account_id}"
                    if not cache.get(cooldown_key):
                        if await self._check_session_limits(account_id):
                            await self._update_session_usage(account_id)
                            return await self._get_session_dict(account_id)

                # Remove from dedicated if no longer available
                self.dedicated_high_priority_sessions.discard(account_id)

        # Try to allocate a new dedicated session
        available_sessions = await self._get_active_sessions()

        if available_sessions:
            # Find least used session not already dedicated
            best_session = None
            min_requests = float("inf")

            for session in available_sessions[:5]:  # Check top 5
                account_id = session[0]
                if account_id not in self.dedicated_high_priority_sessions:
                    requests_key = f"session_requests_{account_id}"
                    requests_count = cache.get(requests_key, 0)
                    if requests_count < min_requests:
                        min_requests = requests_count
                        best_session = session

            if best_session:
                account_id = best_session[0]
                self.dedicated_high_priority_sessions.add(account_id)
                self.session_priority_map[account_id] = SessionPriority.HIGH

                await self._update_session_usage(account_id)
                return await self._get_session_dict(account_id)

        return None

    async def _rotate_session(self, priority: SessionPriority) -> Optional[Dict]:
        """
        Rotate between available sessions based on priority.
        Uses different strategies for different priorities.
        """
        # Get available sessions
        all_sessions = await self._get_active_sessions()

        # Filter out dedicated sessions and those in cooldown
        available_sessions = []
        for session in all_sessions:
            account_id = session[0]
            if account_id not in self.dedicated_high_priority_sessions:
                cooldown_key = f"session_cooldown_{account_id}"
                if not cache.get(cooldown_key):
                    available_sessions.append(session)

        if not available_sessions:
            logger.warning("No available sessions for rotation")
            return None

        # Select session based on priority strategy
        if priority == SessionPriority.HIGH:
            # For high priority, use least recently used
            session = available_sessions[-1]  # Already sorted by last_updated DESC
        elif priority == SessionPriority.MEDIUM:
            # For medium priority, use weighted random
            session = self.weighted_random_selection(available_sessions)
        else:
            # For low priority, use round-robin with randomness
            session = random.choice(available_sessions)

        if session:
            account_id = session[0]
            if await self._check_session_limits(account_id):
                await self._update_session_usage(account_id)
                return await self._get_session_dict(account_id)

        return None

    async def _check_session_limits(self, account_id: int) -> bool:
        """Check if session is within rate limits."""
        # Check hourly limit
        hour_ago = timezone.now() - timedelta(hours=1)
        cache_key = f"session_requests_hour_{account_id}_{hour_ago.hour}"
        hourly_requests = cache.get(cache_key, 0)

        if hourly_requests >= self.max_requests_per_hour:
            # Set cooldown
            cooldown_key = f"session_cooldown_{account_id}"
            cache.set(cooldown_key, True, self.cooldown_duration)
            logger.info(f"Session {account_id} hit hourly limit, entering cooldown")
            return False

        # Check consecutive request limit
        requests_key = f"session_requests_{account_id}"
        requests_count = cache.get(requests_key, 0)

        if requests_count >= self.cooldown_requests:
            cooldown_key = f"session_cooldown_{account_id}"
            cache.set(cooldown_key, True, self.cooldown_duration)
            logger.info(f"Session {account_id} hit consecutive limit, entering cooldown")
            return False

        return True

    async def _update_session_usage(self, account_id: int):
        """Update session usage statistics in cache."""
        # Update request count
        requests_key = f"session_requests_{account_id}"
        requests_count = cache.get(requests_key, 0)
        cache.set(requests_key, requests_count + 1, 3600)

        # Update hourly counter
        hour_ago = timezone.now() - timedelta(hours=1)
        cache_key = f"session_requests_hour_{account_id}_{hour_ago.hour}"
        hourly_requests = cache.get(cache_key, 0)
        cache.set(cache_key, hourly_requests + 1, 3600)

    async def _get_session_dict(self, account_id: int) -> Dict:
        """Get session dictionary with credentials."""
        session = await self._get_session_by_id(account_id)
        if not session:
            return None

        _, email, session_id, _ = session

        return {
            "account_id": account_id,
            "email": email,
            "session_id": session_id,
            "priority": self.session_priority_map.get(account_id, SessionPriority.LOW).value,
            "requests_count": cache.get(f"session_requests_{account_id}", 0),
        }

    async def rotate_all_sessions(self):
        """
        Force rotation of all sessions.
        Useful for periodic rotation or after detecting issues.
        """
        logger.info("Rotating all sessions")

        # Clear dedicated sessions
        self.dedicated_high_priority_sessions.clear()

        # Clear all cache entries for sessions
        sessions = await self._get_active_sessions()
        for session in sessions:
            account_id = session[0]
            cache.delete(f"session_requests_{account_id}")
            cache.delete(f"session_cooldown_{account_id}")
            # Clear hourly counters
            for hour in range(24):
                cache.delete(f"session_requests_hour_{account_id}_{hour}")

        logger.info("Session rotation complete")

    async def get_session_health_report(self) -> Dict:
        """Get detailed health report of all sessions."""
        sessions = await self._get_active_sessions()

        report = {
            "total": 0,
            "active": len(sessions),
            "in_cooldown": 0,
            "expired": 0,
            "dedicated_high_priority": len(self.dedicated_high_priority_sessions),
            "sessions": [],
        }

        # Get total and expired count
        with connection.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) FROM ea_accounts")
            report["total"] = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM ea_accounts WHERE is_expired = TRUE")
            report["expired"] = cursor.fetchone()[0]

        for session in sessions:
            account_id, email, session_id, last_updated = session

            # Check cooldown status
            cooldown_key = f"session_cooldown_{account_id}"
            in_cooldown = bool(cache.get(cooldown_key))

            if in_cooldown:
                report["in_cooldown"] += 1

            # Get request counts
            requests_key = f"session_requests_{account_id}"
            requests_count = cache.get(requests_key, 0)

            hour_ago = timezone.now() - timedelta(hours=1)
            hourly_key = f"session_requests_hour_{account_id}_{hour_ago.hour}"
            hourly_requests = cache.get(hourly_key, 0)

            report["sessions"].append(
                {
                    "account_id": account_id,
                    "email": email,
                    "status": "cooldown" if in_cooldown else "active",
                    "requests_count": requests_count,
                    "hourly_requests": hourly_requests,
                    "last_updated": last_updated.isoformat() if last_updated else None,
                    "is_dedicated": account_id in self.dedicated_high_priority_sessions,
                }
            )

        return report

    async def auto_balance_sessions(self):
        """
        Automatically balance load across sessions.
        Runs periodically to ensure optimal distribution.
        """
        report = await self.get_session_health_report()

        # If too many sessions in cooldown, reduce load
        active = report["active"]
        if active > 0:
            cooldown_ratio = report["in_cooldown"] / active

            if cooldown_ratio > 0.5:
                logger.warning(f"High cooldown ratio: {cooldown_ratio:.2%}, reducing load")
                # Reduce max requests temporarily
                self.max_requests_per_hour = int(self.max_requests_per_hour * 0.8)
                self.cooldown_requests = int(self.cooldown_requests * 0.8)
            elif cooldown_ratio < 0.1 and active > 5:
                # Can increase load slightly
                self.max_requests_per_hour = min(600, int(self.max_requests_per_hour * 1.1))
                self.cooldown_requests = min(120, int(self.cooldown_requests * 1.1))

        # Redistribute dedicated sessions if needed
        if len(self.dedicated_high_priority_sessions) > active * 0.3:
            # Too many dedicated sessions, release some
            to_release = len(self.dedicated_high_priority_sessions) - int(active * 0.2)
            for _ in range(to_release):
                if self.dedicated_high_priority_sessions:
                    self.dedicated_high_priority_sessions.pop()

        logger.info(f"Session auto-balance complete. Active: {active}, Cooldown: {report['in_cooldown']}")


# Global session pool instance
session_pool = SessionPool()
