import logging
from datetime import datetime
from typing import Any, Dict

import redis
from django.conf import settings

from utils.circuit_breaker import CircuitState, EACircuitBreaker
from utils.logging_config import ErrorTracker
from utils.metrics import PrometheusMetrics, RiskMetrics

logger = logging.getLogger(__name__)


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
        await super().record_success()

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
        await super().record_failure(exception)

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
