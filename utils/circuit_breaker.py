import asyncio
import logging
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


class CircuitState(Enum):
    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Circuit tripped, rejecting requests
    HALF_OPEN = "half_open"  # Testing if service recovered


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


class CircuitBreakerOpen(Exception):
    """Exception raised when circuit breaker is open."""


class CircuitBreakerManager:
    """Manages multiple circuit breakers for different endpoints or sessions."""

    def __init__(self):
        self.breakers: dict[str, EACircuitBreaker] = {}

    def get_breaker(self, name: str) -> EACircuitBreaker:
        """Get or create circuit breaker for given name."""
        if name not in self.breakers:
            self.breakers[name] = EACircuitBreaker()
        return self.breakers[name]

    def get_all_status(self) -> dict[str, dict]:
        """Get status of all circuit breakers."""
        return {name: breaker.get_status() for name, breaker in self.breakers.items()}

    def reset_all(self):
        """Reset all circuit breakers."""
        for breaker in self.breakers.values():
            breaker.manual_reset()

    def trip_all(self, reason: str = "Manual trip all"):
        """Trip all circuit breakers."""
        for breaker in self.breakers.values():
            breaker.manual_trip(reason)


# Global circuit breaker manager instance
circuit_breaker_manager = CircuitBreakerManager()
