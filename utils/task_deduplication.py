"""
Celery task deduplication system to prevent duplicate tasks in queue
and cancel running tasks when new instances are queued.
"""

import logging

from celery import Task, current_app
from celery.exceptions import Ignore
from django.core.cache import cache

logger = logging.getLogger("task_deduplication")


class DeduplicatedTask(Task):
    """Custom task class that provides deduplication"""

    dedup_key = None  # Override in subclass to customize dedup key

    def __call__(self, *args, **kwargs):
        """Override to check deduplication before task execution"""
        task_id = self.request.id
        task_key = self.get_dedup_key(args, kwargs)
        running_key = f"{task_key}:running"
        queued_key = f"{task_key}:queued"

        # Get currently running task ID
        running_task_id = cache.get(running_key)

        # If there's a running task and it's not us
        if running_task_id and running_task_id != task_id:
            # Check if we're the latest queued task
            latest_queued_id = cache.get(queued_key)

            if latest_queued_id != task_id:
                # We're not the latest, skip execution
                logger.info(
                    f"Skipping task {task_id} - newer instance exists",
                    extra={"task_name": self.name, "task_id": task_id, "latest_id": latest_queued_id},
                )
                raise Ignore()

            # We're the latest and something is running
            # Don't revoke the running task - let it complete
            # We'll execute after it's done
            logger.info(
                f"Task {task_id} waiting for running task {running_task_id} to complete",
                extra={"task_name": self.name, "task_id": task_id, "running_id": running_task_id},
            )

        # Mark ourselves as running
        cache.set(running_key, task_id, timeout=7200)  # 2 hour timeout

        # Clear queued marker since we're now running
        cache.delete(queued_key)

        try:
            # Execute the actual task
            return super().__call__(*args, **kwargs)
        finally:
            # Clean up our running marker
            if cache.get(running_key) == task_id:
                cache.delete(running_key)

    def after_return(self, status, retval, task_id, args, kwargs, einfo):
        """Called after task execution completes"""
        # This is now handled in the finally block of __call__
        return super().after_return(status, retval, task_id, args, kwargs, einfo)

    def apply_async(self, args=None, kwargs=None, **options):
        """Override to implement queue deduplication"""
        task_key = self.get_dedup_key(args or (), kwargs or {})
        queued_key = f"{task_key}:queued"

        # Get result first
        result = super().apply_async(args=args, kwargs=kwargs, **options)

        if result:
            # Get previously queued task
            prev_queued_id = cache.get(queued_key)

            # Mark new task as queued
            cache.set(queued_key, result.id, timeout=7200)  # 2 hour timeout

            # Revoke previously queued task if exists
            if prev_queued_id and prev_queued_id != result.id:
                try:
                    current_app.control.revoke(prev_queued_id, terminate=False)
                    logger.info(
                        f"Revoked queued task {prev_queued_id}",
                        extra={"task_name": self.name, "old_task_id": prev_queued_id, "new_task_id": result.id},
                    )
                except Exception as e:
                    logger.error(f"Failed to revoke queued task {prev_queued_id}: {e}")

        return result

    def get_dedup_key(self, args, kwargs) -> str:
        """Get deduplication key for this task"""
        if self.dedup_key:
            return self.dedup_key

        # For tier-based tasks, include tier in key
        if "tier" in kwargs:
            return f"task_dedup:{self.name}:tier:{kwargs['tier']}"

        # Default: just use task name
        return f"task_dedup:{self.name}"
