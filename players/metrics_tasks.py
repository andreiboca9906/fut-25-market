"""Metrics update task with proper sync_to_async wrappers."""

import asyncio
import logging

from celery import shared_task

from utils.metrics import QualityMetrics, SystemMetrics
from utils.task_deduplication import DeduplicatedTask

logger = logging.getLogger("players")


@shared_task(base=DeduplicatedTask)
def update_metrics():
    """Update all Prometheus metrics periodically"""
    logger.info("Running metrics update task")

    async def _run_metrics_updates():
        """Run all metrics updates with proper async handling"""
        try:
            # Update quality metrics
            await QualityMetrics.update_freshness_metrics()
            await QualityMetrics.update_verification_metrics()

            # Update system metrics
            await SystemMetrics.update_celery_metrics()
            await SystemMetrics.update_session_metrics()

            logger.info("Metrics update completed successfully")
            return "Metrics update complete"
        except Exception as e:
            logger.error(f"Error updating metrics: {e}")
            raise

    # Run the async function in a new event loop
    return asyncio.run(_run_metrics_updates())
