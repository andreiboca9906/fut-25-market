"""
Test script for task deduplication system.
Run with: uv run python test_deduplication.py
"""

import os
import time
from datetime import datetime

import django
from celery.result import AsyncResult

# Setup Django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "fut_market.settings")
django.setup()

from players.metrics_tasks import update_metrics
from players.tasks import (
    recalculate_player_tiers,
    scrape_market_prices,
    scrape_tier_prices,
    verify_pending_trades,
)


def test_duplicate_prevention():
    """Test that duplicate tasks are prevented in queue"""
    print("\n=== Testing Duplicate Prevention ===")

    # Queue multiple instances of the same task
    print("\n1. Queueing 3 instances of scrape_tier_prices for HOT tier...")
    task1 = scrape_tier_prices.delay(tier="HOT")
    print(f"   Task 1 ID: {task1.id}")

    time.sleep(0.5)
    task2 = scrape_tier_prices.delay(tier="HOT")
    print(f"   Task 2 ID: {task2.id}")

    time.sleep(0.5)
    task3 = scrape_tier_prices.delay(tier="HOT")
    print(f"   Task 3 ID: {task3.id}")

    print("\n   Expected: Only task3 should execute, task1 and task2 should be revoked")

    # Queue different tiers (should not interfere)
    print("\n2. Queueing tasks for different tiers...")
    task_trending = scrape_tier_prices.delay(tier="TRENDING")
    print(f"   TRENDING tier task ID: {task_trending.id}")

    task_active = scrape_tier_prices.delay(tier="ACTIVE")
    print(f"   ACTIVE tier task ID: {task_active.id}")

    print("\n   Expected: Both should execute as they have different dedup keys")

    # Test other tasks
    print("\n3. Testing other deduplicated tasks...")

    # Multiple verify trades
    verify1 = verify_pending_trades.delay()
    print(f"   Verify trades 1 ID: {verify1.id}")

    time.sleep(0.5)
    verify2 = verify_pending_trades.delay()
    print(f"   Verify trades 2 ID: {verify2.id}")

    print("\n   Expected: Only verify2 should execute")

    # Multiple metrics updates
    metrics1 = update_metrics.delay()
    print(f"   Metrics update 1 ID: {metrics1.id}")

    time.sleep(0.5)
    metrics2 = update_metrics.delay()
    print(f"   Metrics update 2 ID: {metrics2.id}")

    print("\n   Expected: Only metrics2 should execute")

    print("\n4. Testing full market scrape deduplication...")
    scrape1 = scrape_market_prices.delay()
    print(f"   Full scrape 1 ID: {scrape1.id}")

    time.sleep(0.5)
    scrape2 = scrape_market_prices.delay()
    print(f"   Full scrape 2 ID: {scrape2.id}")

    print("\n   Expected: Only scrape2 should execute, scrape1 should be revoked")


def test_running_task_cancellation():
    """Test that running tasks are cancelled when new ones arrive"""
    print("\n\n=== Testing Running Task Cancellation ===")

    print("\n1. Starting a long-running recalculation task...")
    recalc1 = recalculate_player_tiers.delay()
    print(f"   Task 1 ID: {recalc1.id}")

    print("\n2. Waiting 2 seconds then queueing another...")
    time.sleep(2)

    recalc2 = recalculate_player_tiers.delay()
    print(f"   Task 2 ID: {recalc2.id}")

    print("\n   Expected: Task 1 should be revoked/terminated, Task 2 should run")


def check_task_statuses(task_ids):
    """Check and print task statuses"""
    print("\n\n=== Checking Task Statuses ===")
    for task_id, desc in task_ids:
        try:
            result = AsyncResult(task_id)
            print(f"{desc} ({task_id}): {result.state}")
        except Exception as e:
            print(f"{desc} ({task_id}): Error checking - {e}")


if __name__ == "__main__":
    print("Task Deduplication System Test")
    print("=" * 50)
    print(f"Started at: {datetime.now()}")

    # Collect task IDs for status check
    task_ids = []

    # Run tests
    test_duplicate_prevention()
    test_running_task_cancellation()

    print("\n\nNote: Check Celery worker logs to verify actual execution behavior.")
    print("Look for messages like:")
    print("  - 'Skipping task X - newer instance Y exists'")
    print("  - 'Revoked running task X for newer instance'")
    print("  - 'Revoked queued task X for newer instance'")

    print("\nYou can also check Redis keys with:")
    print("  redis-cli KEYS 'task_dedup:*'")
    print("\nTo see current deduplication locks.")
