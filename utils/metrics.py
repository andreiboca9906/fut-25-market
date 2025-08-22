from typing import Any, Dict

import redis
from asgiref.sync import sync_to_async
from celery import current_app
from django.conf import settings
from django.db import connection
from django.db.models import Avg, Count, F, Q
from django.http import HttpResponse
from django.utils import timezone
from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram, generate_latest

from players.models import PlayerPrice, TradeWatch

# Create custom registry for scraper metrics
registry = CollectorRegistry()

# Performance Metrics
request_counter = Counter(
    "scraper_requests_total", "Total number of scraper requests", ["tier", "status", "session_id"], registry=registry
)

response_time_histogram = Histogram(
    "scraper_response_time_seconds",
    "Response time in seconds",
    ["tier"],
    buckets=(0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
    registry=registry,
)

active_scrapers = Gauge("scraper_active_tasks", "Number of active scraper tasks", ["tier"], registry=registry)

# Risk & Error Metrics
rate_limit_counter = Counter("scraper_rate_limits_total", "Total rate limit hits", ["session_id"], registry=registry)

session_expiration_counter = Counter(
    "scraper_session_expirations_total", "Total session expirations", ["session_id"], registry=registry
)

error_counter = Counter(
    "scraper_errors_total", "Total scraper errors", ["tier", "error_type", "session_id"], registry=registry
)

circuit_breaker_gauge = Gauge(
    "scraper_circuit_breaker_status", "Circuit breaker status (0=closed, 1=open)", ["tier"], registry=registry
)

# Data Quality Metrics
price_freshness_gauge = Gauge(
    "scraper_price_freshness_minutes", "Average price age in minutes", ["tier"], registry=registry
)

verified_trades_gauge = Gauge("scraper_verified_trades_ratio", "Ratio of verified to total trades", registry=registry)

missing_prices_gauge = Gauge("scraper_missing_prices_count", "Number of players without prices", registry=registry)

stale_prices_gauge = Gauge(
    "scraper_stale_prices_count", "Number of prices older than 2 hours", ["tier"], registry=registry
)

# System Health Metrics
active_sessions_gauge = Gauge("scraper_active_sessions", "Number of active EA sessions", registry=registry)

queue_depth_gauge = Gauge("scraper_queue_depth", "Number of tasks in queue", ["queue_name"], registry=registry)

worker_utilization_gauge = Gauge(
    "scraper_worker_utilization", "Worker utilization percentage", ["worker_name"], registry=registry
)


class PrometheusMetrics:
    @staticmethod
    def record_request(tier: str, response_time: float, success: bool, session_id: str):
        """Record scraper request metrics"""
        status = "success" if success else "failure"
        request_counter.labels(tier=tier, status=status, session_id=session_id).inc()
        response_time_histogram.labels(tier=tier).observe(response_time)

    @staticmethod
    def set_active_scrapers(tier: str, count: int):
        """Update active scraper count"""
        active_scrapers.labels(tier=tier).set(count)

    @staticmethod
    def increment_active_scrapers(tier: str):
        """Increment active scraper count"""
        active_scrapers.labels(tier=tier).inc()

    @staticmethod
    def decrement_active_scrapers(tier: str):
        """Decrement active scraper count"""
        active_scrapers.labels(tier=tier).dec()


class RiskMetrics:
    @staticmethod
    def record_rate_limit(session_id: str):
        """Record rate limit hit"""
        rate_limit_counter.labels(session_id=session_id).inc()

    @staticmethod
    def record_session_expiration(session_id: str):
        """Record session expiration"""
        session_expiration_counter.labels(session_id=session_id).inc()

    @staticmethod
    def record_error(tier: str, error_type: str, session_id: str):
        """Record error occurrence"""
        error_counter.labels(tier=tier, error_type=error_type, session_id=session_id).inc()

    @staticmethod
    def set_circuit_breaker(tier: str, is_open: bool):
        """Update circuit breaker status"""
        circuit_breaker_gauge.labels(tier=tier).set(1 if is_open else 0)


class QualityMetrics:
    @staticmethod
    async def update_freshness_metrics():
        """Update price freshness metrics"""
        tiers = ["HOT", "TRENDING", "ACTIVE", "NORMAL", "COLD"]

        for tier in tiers:
            # Calculate average age for each tier
            avg_age_result = await sync_to_async(
                lambda: PlayerPrice.objects.filter(player__playertier__tier=tier).aggregate(
                    avg_age=Avg(timezone.now() - F("last_updated"))
                )
            )()

            avg_age = avg_age_result.get("avg_age")
            if avg_age:
                minutes = avg_age.total_seconds() / 60
                price_freshness_gauge.labels(tier=tier).set(minutes)

            # Count stale prices
            stale_count = await sync_to_async(
                lambda: PlayerPrice.objects.filter(
                    player__playertier__tier=tier, last_updated__lt=timezone.now() - timezone.timedelta(hours=2)
                ).count()
            )()
            stale_prices_gauge.labels(tier=tier).set(stale_count)

        # Count missing prices
        missing_count = await sync_to_async(
            lambda: PlayerPrice.objects.filter(Q(current_low_price__isnull=True) | Q(current_low_price=0)).count()
        )()
        missing_prices_gauge.set(missing_count)

    @staticmethod
    async def update_verification_metrics():
        """Update trade verification metrics"""
        stats = await sync_to_async(
            lambda: TradeWatch.objects.aggregate(total=Count("id"), sold=Count("id", filter=Q(status="sold")))
        )()

        if stats["total"] > 0:
            ratio = stats["sold"] / stats["total"]
            verified_trades_gauge.set(ratio)


class SystemMetrics:
    @staticmethod
    async def update_celery_metrics():
        """Update Celery queue and worker metrics"""
        r = redis.Redis.from_url(settings.REDIS_URL)
        inspect = current_app.control.inspect()

        # Queue depth metrics
        for tier in ["hot", "trending", "active", "normal", "cold"]:
            queue_name = f"scraper_{tier}"
            depth = r.llen(f"celery:queue:{queue_name}")
            queue_depth_gauge.labels(queue_name=queue_name).set(depth)

        # Worker metrics
        active = inspect.active()
        if active:
            for worker_name, tasks in active.items():
                utilization = len(tasks) / settings.CELERY_WORKER_CONCURRENCY * 100
                worker_utilization_gauge.labels(worker_name=worker_name).set(utilization)

    @staticmethod
    async def update_session_metrics():
        """Update EA session metrics"""
        with connection.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) FROM ea_accounts WHERE is_expired = FALSE")
            active_count = cursor.fetchone()[0]

        active_sessions_gauge.set(active_count)

    @staticmethod
    def increment_active_tasks(tier: str):
        """Increment active tasks for a tier"""
        PrometheusMetrics.increment_active_scrapers(tier)

    @staticmethod
    def decrement_active_tasks(tier: str):
        """Decrement active tasks for a tier"""
        PrometheusMetrics.decrement_active_scrapers(tier)


# Django view to expose metrics
def metrics_view(request):
    """Prometheus metrics endpoint"""
    return HttpResponse(generate_latest(registry), content_type="text/plain")


# Metrics collector for aggregating metrics
class MetricsCollector:
    def __init__(self):
        self.redis = redis.Redis.from_url(settings.REDIS_URL)

    async def record_request(self, tier: str, response_time: float, success: bool, session_id: str):
        """Record request metrics"""
        PrometheusMetrics.record_request(tier, response_time, success, session_id)

        # Update cached metrics for circuit breaker
        await self._update_cached_metrics(tier)

    async def get_performance_metrics(self, tier: str, minutes: int) -> Dict[str, Any]:
        """Get performance metrics for the last N minutes"""
        # Get from Redis cache
        metrics_key = f"metrics:{tier}:current"
        raw_metrics = self.redis.hgetall(metrics_key)

        if raw_metrics:
            return {
                "success_rate": float(raw_metrics.get(b"success_rate", 0.95)),
                "avg_response_time": float(raw_metrics.get(b"avg_response_time", 1.2)),
                "total_requests": int(raw_metrics.get(b"total_requests", 1000)),
                "error_rate": float(raw_metrics.get(b"error_rate", 0.05)),
            }

        return {"success_rate": 0.95, "avg_response_time": 1.2, "total_requests": 1000, "error_rate": 0.05}

    async def _update_cached_metrics(self, tier: str):
        """Update cached metrics in Redis for circuit breaker"""
        # This is a simplified version - in production would aggregate from Prometheus
        metrics_key = f"metrics:{tier}:current"

        # Get current counts from Redis
        success_key = f"metrics:{tier}:success_count"
        failure_key = f"metrics:{tier}:failure_count"
        rate_limit_key = f"metrics:{tier}:rate_limit_count"

        success_count = int(self.redis.get(success_key) or 0)
        failure_count = int(self.redis.get(failure_key) or 0)
        rate_limit_count = int(self.redis.get(rate_limit_key) or 0)

        total = success_count + failure_count
        if total > 0:
            success_rate = success_count / total
            error_rate = failure_count / total
        else:
            success_rate = 1.0
            error_rate = 0.0

        # Cache aggregated metrics
        self.redis.hset(
            metrics_key,
            mapping={
                "success_rate": success_rate,
                "error_rate": error_rate,
                "rate_limit_hits": rate_limit_count,
                "avg_response_time": 1.5,  # Would calculate from histogram
                "last_updated": timezone.now().isoformat(),
            },
        )

        # Expire after 5 minutes
        self.redis.expire(metrics_key, 300)


# Risk monitor for adaptive behavior
class RiskMonitor:
    async def get_risk_score(self) -> float:
        """Calculate current risk score based on metrics"""
        # This would aggregate various risk factors
        # For now, return a mock value
        return 25.0
