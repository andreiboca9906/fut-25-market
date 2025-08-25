import asyncio
import logging
import time

from celery import Task, shared_task

from utils.integrated_circuit_breaker import circuit_breaker_manager
from utils.logging_config import ErrorTracker
from utils.metrics import PrometheusMetrics, QualityMetrics, RiskMetrics, SystemMetrics
from utils.task_deduplication import DeduplicatedTask

logger = logging.getLogger("players")


class MonitoredTask(Task):
    """Base Celery task with Prometheus monitoring"""

    def __call__(self, *args, **kwargs):
        tier = kwargs.get("tier", "unknown")
        session_id = kwargs.get("session_id", "unknown")

        # Increment active tasks
        SystemMetrics.increment_active_tasks(tier)

        start_time = time.time()
        try:
            result = super().__call__(*args, **kwargs)
            # Record success
            PrometheusMetrics.record_request(
                tier=tier, response_time=time.time() - start_time, success=True, session_id=session_id
            )
            return result
        except Exception as e:
            # Record failure
            PrometheusMetrics.record_request(
                tier=tier, response_time=time.time() - start_time, success=False, session_id=session_id
            )
            RiskMetrics.record_error(tier=tier, error_type=ErrorTracker.categorize_error(e), session_id=session_id)
            raise
        finally:
            # Decrement active tasks
            SystemMetrics.decrement_active_tasks(tier)


async def should_circuit_break(tier: str) -> bool:
    """Check if circuit breaker should be triggered"""
    # Check if any circuit is open for the tier
    status = await circuit_breaker_manager.check_all_circuits()
    return status.get(tier, False)


def chunk(lst, n):
    """Yield successive n-sized chunks from lst."""
    for i in range(0, len(lst), n):
        yield lst[i : i + n]


@shared_task(base=DeduplicatedTask)
def update_metrics():
    """Update all Prometheus metrics periodically"""

    async def _run():
        await QualityMetrics.update_freshness_metrics()
        await QualityMetrics.update_verification_metrics()
        await QualityMetrics.update_players_with_prices_by_rating()
        await SystemMetrics.update_celery_metrics()
        await SystemMetrics.update_session_metrics()

    asyncio.run(_run())
