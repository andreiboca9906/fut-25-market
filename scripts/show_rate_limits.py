"""
Display current rate limit configuration.
Run: uv run python scripts/show_rate_limits.py
"""

import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.rate_limit_config import BASE_RATE_LIMIT, RateLimitConfig


def main():
    print(f"\n{'=' * 60}")
    print(f"RATE LIMIT CONFIGURATION (BASE: {BASE_RATE_LIMIT} req/min)")
    print(f"{'=' * 60}\n")

    config = RateLimitConfig.get_config_summary()

    print("SESSION LIMITS:")
    print(f"  Hourly limit: {config['session_limits']['hourly']} requests")
    print(f"  Consecutive limit: {config['session_limits']['consecutive']} requests")
    print(f"  Circuit breaker threshold: {config['circuit_breaker_threshold']} rate limit hits/hour")

    print("\nTIER CONFIGURATIONS:")
    print(f"{'Tier':<10} {'Rate/min':<10} {'% of Base':<12} {'Base Delay':<12} {'Task Timeout':<12}")
    print("-" * 60)

    for tier in ["HOT", "TRENDING", "ACTIVE", "NORMAL", "COLD"]:
        rate = config["tier_rate_limits"][tier]
        pct = f"{rate / BASE_RATE_LIMIT * 100:.0f}%"
        delay = config["base_delays"][tier]
        timeout = config["task_timeouts"][tier]
        print(f"{tier:<10} {rate:<10} {pct:<12} {delay:<12} {timeout:<12}")

    print(f"\n{'=' * 60}")
    print("To change all limits: Edit BASE_RATE_LIMIT in utils/rate_limit_config.py")
    print(f"{'=' * 60}\n")


if __name__ == "__main__":
    main()
