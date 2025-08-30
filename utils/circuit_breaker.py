import asyncio
import logging
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, Optional

import redis
from django.conf import settings

from utils.logging_config import ErrorTracker
from utils.metrics import PrometheusMetrics, RiskMetrics

logger = logging.getLogger(__name__)


class CircuitState(Enum):
    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Circuit tripped, rejecting requests
    HALF_OPEN = "half_open"  # Testing if service recovered


class CircuitBreakerOpen(Exception):
    """Exception raised when circuit breaker is open."""


class EACircuitBreaker:
    """
    Circuit breaker for EA API calls.
    Detects and responds to EA defensive measures.
    """

    def __init__(
        self,
        failure_threshold: int = 3,
        timeout_threshold: int = 5,
        recovery_timeout: int = 300,
        half_open_max_calls: int = 3,
    ):
        self.failure_threshold = failure_threshold
        self.timeout_threshold = timeout_threshold
        self.recovery_timeout = recovery_timeout  # seconds
        self.half_open_max_calls = half_open_max_calls

        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.timeout_count = 0
        self.last_failure_time: Optional[datetime] = None
        self.half_open_calls = 0

        # Track different error types
        self.consecutive_429_errors = 0
        self.consecutive_timeouts = 0
        self.captcha_detected = False
        self.session_expired_count = 0

    def _reset_counts(self):
        """Reset all error counters."""
        self.failure_count = 0
        self.timeout_count = 0
        self.consecutive_429_errors = 0
        self.consecutive_timeouts = 0
        self.half_open_calls = 0

    def _should_trip(self) -> bool:
        """Check if circuit should trip to OPEN state."""
        if self.consecutive_429_errors >= self.failure_threshold:
            logger.warning(f"Circuit tripping: {self.consecutive_429_errors} consecutive 429 errors")
            return True

        if self.consecutive_timeouts >= self.timeout_threshold:
            logger.warning(f"Circuit tripping: {self.consecutive_timeouts} consecutive timeouts")
            return True

        if self.captcha_detected:
            logger.error("Circuit tripping: CAPTCHA detected")
            return True

        return False

    def _get_backoff_duration(self) -> int:
        """Calculate backoff duration based on error type."""
        if self.captcha_detected:
            return 3600  # 1 hour for captcha
        elif self.consecutive_429_errors >= 5:
            return 600  # 10 minutes for many rate limits
        elif self.consecutive_429_errors >= 3:
            return 300  # 5 minutes for rate limits
        elif self.consecutive_timeouts >= 5:
            return 600  # 10 minutes for timeouts
        else:
            return self.recovery_timeout

    async def call(self, func: Callable, *args, **kwargs) -> Any:
        """
        Execute function with circuit breaker protection.

        Args:
            func: Async function to execute
            *args: Function arguments
            **kwargs: Function keyword arguments

        Returns:
            Function result

        Raises:
            CircuitBreakerOpen: If circuit is open
            Original exception: If function fails
        """
        # Check circuit state
        if self.state == CircuitState.OPEN:
            if self._should_attempt_reset():
                self.state = CircuitState.HALF_OPEN
                self.half_open_calls = 0
                logger.info("Circuit breaker entering HALF_OPEN state")
            else:
                raise CircuitBreakerOpen(f"Circuit breaker is OPEN. Retry after {self._time_until_reset()} seconds")

        # In HALF_OPEN state, limit number of calls
        if self.state == CircuitState.HALF_OPEN:
            if self.half_open_calls >= self.half_open_max_calls:
                # Too many test calls, trip back to OPEN
                self.state = CircuitState.OPEN
                self.last_failure_time = datetime.now()
                logger.warning("Circuit breaker returning to OPEN state after HALF_OPEN test failures")
                raise CircuitBreakerOpen("Circuit breaker returned to OPEN after test failures")
            self.half_open_calls += 1

        try:
            # Execute the function
            result = await func(*args, **kwargs)

            # Success - update state
            self._on_success()

            return result

        except Exception as e:
            # Handle different types of failures
            self._on_failure(e)
            raise

    def _on_success(self):
        """Handle successful call."""
        if self.state == CircuitState.HALF_OPEN:
            # Success in half-open, check if we can close
            if self.half_open_calls >= self.half_open_max_calls:
                self.state = CircuitState.CLOSED
                self._reset_counts()
                logger.info("Circuit breaker recovered to CLOSED state")
        elif self.state == CircuitState.CLOSED:
            # Reset consecutive error counts on success
            self.consecutive_429_errors = 0
            self.consecutive_timeouts = 0

    def _on_failure(self, exception: Exception):
        """Handle failed call."""
        self.last_failure_time = datetime.now()

        # Categorize the error
        error_str = str(exception).lower()

        if "429" in error_str or "rate limit" in error_str:
            self.consecutive_429_errors += 1
            self.consecutive_timeouts = 0  # Reset other counter
            logger.warning(f"Rate limit error #{self.consecutive_429_errors}")

        elif "timeout" in error_str or isinstance(exception, asyncio.TimeoutError):
            self.consecutive_timeouts += 1
            self.consecutive_429_errors = 0  # Reset other counter
            logger.warning(f"Timeout error #{self.consecutive_timeouts}")

        elif "captcha" in error_str:
            self.captcha_detected = True
            logger.error("CAPTCHA detected!")

        elif "session" in error_str or "expired" in error_str or "401" in error_str:
            self.session_expired_count += 1
            logger.warning(f"Session expired #{self.session_expired_count}")

        # Check if we should trip the circuit
        if self._should_trip():
            self.state = CircuitState.OPEN
            backoff = self._get_backoff_duration()
            logger.error(f"Circuit breaker tripped to OPEN. Backoff: {backoff} seconds")

    def _should_attempt_reset(self) -> bool:
        """Check if enough time has passed to attempt reset."""
        if not self.last_failure_time:
            return True

        backoff_duration = self._get_backoff_duration()
        elapsed = (datetime.now() - self.last_failure_time).total_seconds()

        return elapsed >= backoff_duration

    def _time_until_reset(self) -> int:
        """Calculate seconds until circuit can attempt reset."""
        if not self.last_failure_time:
            return 0

        backoff_duration = self._get_backoff_duration()
        elapsed = (datetime.now() - self.last_failure_time).total_seconds()

        return max(0, int(backoff_duration - elapsed))

    def get_status(self) -> dict:
        """Get current circuit breaker status."""
        return {
            "state": self.state.value,
            "consecutive_429_errors": self.consecutive_429_errors,
            "consecutive_timeouts": self.consecutive_timeouts,
            "captcha_detected": self.captcha_detected,
            "session_expired_count": self.session_expired_count,
            "time_until_reset": self._time_until_reset() if self.state == CircuitState.OPEN else None,
        }

    def manual_reset(self):
        """Manually reset the circuit breaker."""
        self.state = CircuitState.CLOSED
        self._reset_counts()
        self.captcha_detected = False
        self.session_expired_count = 0
        logger.info("Circuit breaker manually reset to CLOSED")

    def manual_trip(self, reason: str = "Manual trip"):
        """Manually trip the circuit breaker."""
        self.state = CircuitState.OPEN
        self.last_failure_time = datetime.now()
        logger.warning(f"Circuit breaker manually tripped: {reason}")


class MetricsBasedCircuitBreaker(EACircuitBreaker):
    """Enhanced circuit breaker that uses Prometheus metrics for decisions"""

    def __init__(self, tier: str, session_id: str, **kwargs):
        super().__init__(**kwargs)
        self.tier = tier
        self.session_id = session_id
        self.redis = redis.Redis.from_url(settings.REDIS_URL)

    async def check_metrics(self) -> Dict[str, float]:
        """Query current metrics from Redis (cached by metrics collector)"""
        metrics_key = f"metrics:{self.tier}:current"

        # Get cached metrics from Redis
        raw_metrics = self.redis.hgetall(metrics_key)
        if not raw_metrics:
            return {"error_rate": 0.0, "rate_limit_hits": 0, "avg_response_time": 1.0, "success_rate": 1.0}

        return {
            "error_rate": float(raw_metrics.get(b"error_rate", 0)),
            "rate_limit_hits": int(raw_metrics.get(b"rate_limit_hits", 0)),
            "avg_response_time": float(raw_metrics.get(b"avg_response_time", 1.0)),
            "success_rate": float(raw_metrics.get(b"success_rate", 1.0)),
        }

    async def should_open(self) -> bool:
        """Decide if circuit should open based on global metrics"""
        if not settings.CIRCUIT_BREAKER_ENABLED:
            return False

        metrics = await self.check_metrics()

        # Multiple conditions for opening circuit
        reasons = []

        # High error rate
        if metrics["error_rate"] > settings.CIRCUIT_BREAKER_ERROR_THRESHOLD:
            reasons.append(f"Error rate {metrics['error_rate']:.2%} exceeds threshold")

        # Too many rate limits
        if metrics["rate_limit_hits"] > settings.CIRCUIT_BREAKER_RATE_LIMIT_THRESHOLD:
            reasons.append(f"Rate limit hits {metrics['rate_limit_hits']} exceeds threshold")

        # Low success rate
        if metrics["success_rate"] < settings.CIRCUIT_BREAKER_SUCCESS_THRESHOLD:
            reasons.append(f"Success rate {metrics['success_rate']:.2%} below threshold")

        # High response times
        if metrics["avg_response_time"] > settings.CIRCUIT_BREAKER_RESPONSE_TIME_THRESHOLD:
            reasons.append(f"Avg response time {metrics['avg_response_time']:.2f}s exceeds threshold")

        if reasons:
            logger.warning(
                f"Circuit breaker opening for tier {self.tier}",
                extra={"tier": self.tier, "session_id": self.session_id, "reasons": reasons, "metrics": metrics},
            )
            return True

        return False

    async def record_success(self):
        """Record successful request and check if circuit should close"""
        self._on_success()

        # Report to monitoring
        PrometheusMetrics.record_request(
            tier=self.tier,
            response_time=0,  # Will be set by caller
            success=True,
            session_id=self.session_id,
        )

        # Check if we should close circuit in half-open state
        if self.state == CircuitState.HALF_OPEN:
            metrics = await self.check_metrics()
            if metrics["success_rate"] > 0.9:  # 90% success rate
                self.close()

    async def record_failure(self, exception: Exception):
        """Record failure and check if circuit should open"""
        self._on_failure(exception)

        # Report to monitoring
        error_type = ErrorTracker.categorize_error(exception)
        RiskMetrics.record_error(tier=self.tier, error_type=error_type, session_id=self.session_id)

        # Check if we should open circuit
        if await self.should_open():
            self.open()

    def open(self):
        """Open circuit and report to monitoring"""
        super().open()
        RiskMetrics.set_circuit_breaker(tier=self.tier, is_open=True)

        # Store state in Redis for coordination
        state_key = f"circuit_breaker:{self.tier}:state"
        self.redis.setex(state_key, self.recovery_timeout, CircuitState.OPEN.value)

    def close(self):
        """Close circuit and report to monitoring"""
        super().close()
        RiskMetrics.set_circuit_breaker(tier=self.tier, is_open=False)

        # Clear state in Redis
        state_key = f"circuit_breaker:{self.tier}:state"
        self.redis.delete(state_key)

    async def is_open_globally(self) -> bool:
        """Check if any instance has opened the circuit"""
        state_key = f"circuit_breaker:{self.tier}:state"
        global_state = self.redis.get(state_key)

        if global_state and global_state.decode() == CircuitState.OPEN.value:
            # Sync local state with global
            if self.state != CircuitState.OPEN:
                self.state = CircuitState.OPEN
                self.last_failure_time = datetime.now()
            return True

        return self.state == CircuitState.OPEN


class CircuitBreakerManager:
    """Manages circuit breakers across tiers with global coordination"""

    def __init__(self):
        self.breakers: Dict[str, MetricsBasedCircuitBreaker] = {}
        self.redis = redis.Redis.from_url(settings.REDIS_URL)
        self.enabled = settings.CIRCUIT_BREAKER_ENABLED

    async def get_breaker(self, tier: str, session_id: str) -> MetricsBasedCircuitBreaker:
        """Get or create circuit breaker for a tier"""
        if not self.enabled:
            # Return a dummy breaker that never opens
            return MetricsBasedCircuitBreaker(tier=tier, session_id=session_id, failure_threshold=float("inf"))

        key = f"{tier}:{session_id}"
        if key not in self.breakers:
            self.breakers[key] = MetricsBasedCircuitBreaker(
                tier=tier,
                session_id=session_id,
                failure_threshold=settings.CIRCUIT_BREAKER_FAILURE_THRESHOLD,
                timeout_threshold=settings.CIRCUIT_BREAKER_TIMEOUT_THRESHOLD,
                recovery_timeout=settings.CIRCUIT_BREAKER_RECOVERY_TIMEOUT,
                half_open_max_calls=settings.CIRCUIT_BREAKER_HALF_OPEN_CALLS,
            )

        return self.breakers[key]

    async def check_all_circuits(self) -> Dict[str, bool]:
        """Check status of all circuits"""
        tiers = ["HOT", "TRENDING", "ACTIVE", "NORMAL", "COLD"]
        status = {}

        for tier in tiers:
            state_key = f"circuit_breaker:{tier}:state"
            state = self.redis.get(state_key)
            status[tier] = state is not None and state.decode() == CircuitState.OPEN.value

        return status

    async def force_open(self, tier: str, duration: int = 300):
        """Manually open a circuit for a specific duration"""
        state_key = f"circuit_breaker:{tier}:state"
        self.redis.setex(state_key, duration, CircuitState.OPEN.value)
        RiskMetrics.set_circuit_breaker(tier=tier, is_open=True)

        logger.info(f"Manually opened circuit for tier {tier} for {duration}s")

    async def force_close(self, tier: str):
        """Manually close a circuit"""
        state_key = f"circuit_breaker:{tier}:state"
        self.redis.delete(state_key)
        RiskMetrics.set_circuit_breaker(tier=tier, is_open=False)

        logger.info(f"Manually closed circuit for tier {tier}")

    async def get_circuit_health(self) -> Dict[str, Any]:
        """Get health report for all circuits"""
        status = await self.check_all_circuits()
        health = {"enabled": self.enabled, "circuits": {}}

        for tier, is_open in status.items():
            metrics_key = f"metrics:{tier}:current"
            raw_metrics = self.redis.hgetall(metrics_key)

            health["circuits"][tier] = {
                "is_open": is_open,
                "error_rate": float(raw_metrics.get(b"error_rate", 0)) if raw_metrics else 0,
                "success_rate": float(raw_metrics.get(b"success_rate", 1.0)) if raw_metrics else 1.0,
                "last_updated": raw_metrics.get(b"last_updated", b"").decode() if raw_metrics else None,
            }

        return health


# Global manager instance
circuit_breaker_manager = CircuitBreakerManager()
