import random
from datetime import datetime
from typing import Any, Dict

import redis
from django.conf import settings

from utils.metrics import MetricsCollector, RiskMonitor


class AdaptiveThrottler:
    def __init__(self):
        self.redis = redis.Redis.from_url(settings.CELERY_BROKER_URL)
        self.base_delays = {
            "HOT": 1.5,
            "TRENDING": 2.0,
            "ACTIVE": 3.0,
            "NORMAL": 4.0,
            "COLD": 1.5,
        }  # Cold was previously 6.0
        self.adjustment_factor = 1.0

    async def get_adjusted_delay(self, tier: str) -> float:
        """Get delay with adaptive adjustments"""
        base = self.base_delays[tier]
        factor = await self.get_adjustment_factor()
        return base * factor * random.uniform(0.85, 1.15)

    async def get_adjustment_factor(self) -> float:
        """Calculate adjustment based on recent metrics"""
        metrics = await MetricsCollector().get_performance_metrics("all", 10)  # previous 60
        risk = await RiskMonitor().get_risk_score()

        if risk > 70:
            # High risk - increase delays significantly
            self.adjustment_factor = min(self.adjustment_factor * 1.5, 3.0)
        elif risk > 50:
            # Medium risk - increase delays moderately
            self.adjustment_factor = min(self.adjustment_factor * 1.2, 2.0)
        elif risk < 20 and metrics["success_rate"] > 0.98:
            # Low risk, high success - carefully decrease
            self.adjustment_factor = max(self.adjustment_factor * 0.95, 0.5)

        # Store adjustment history
        self.redis.hset("throttle:adjustments", datetime.now().isoformat(), self.adjustment_factor)

        return self.adjustment_factor

    async def get_batch_size(self, tier: str) -> int:
        """Get adjusted batch size based on conditions"""
        base_sizes = {"HOT": 12, "TRENDING": 25, "ACTIVE": 35, "NORMAL": 45, "COLD": 55}

        factor = await self.get_adjustment_factor()
        if factor > 1.5:
            # Reduce batch size when throttled
            return int(base_sizes[tier] * 0.7)
        elif factor < 0.8:
            # Increase batch size when performing well
            return int(base_sizes[tier] * 1.2)

        return base_sizes[tier]


class CooldownManager:
    def __init__(self):
        self.redis = redis.Redis.from_url(settings.CELERY_BROKER_URL)

    async def get_session_metrics(self, session_id: str) -> Dict[str, Any]:
        """Get metrics for a specific session"""
        # This would aggregate session-specific metrics
        # For now, return mock data
        return {"error_rate": 0.05, "consecutive_successes": 50, "requests_last_hour": 200, "consecutive_requests": 30}

    async def get_cooldown_duration(self, session_id: str) -> int:
        """Calculate dynamic cooldown based on session health"""
        session_metrics = await self.get_session_metrics(session_id)

        base_cooldown = 900  # 15 minutes

        if session_metrics["error_rate"] > 0.1:
            # High error rate - extend cooldown
            return base_cooldown * 2
        elif session_metrics["consecutive_successes"] > 100:
            # Performing well - reduce cooldown
            return base_cooldown // 2

        return base_cooldown

    async def should_cooldown(self, session_id: str) -> bool:
        """Check if session needs cooldown"""
        metrics = await self.get_session_metrics(session_id)

        return (
            metrics["requests_last_hour"] > 400 or metrics["consecutive_requests"] > 80 or metrics["error_rate"] > 0.15
        )
