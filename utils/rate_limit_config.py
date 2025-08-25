"""
Cross-related rate limit configuration.
Change BASE_RATE_LIMIT and all other limits adjust automatically.
"""

# Primary configuration - CHANGE THIS to adjust all limits
BASE_RATE_LIMIT = 50  # EA's rate limit per minute per session


# Derived configurations (automatically calculated)
class RateLimitConfig:
    """Cross-related rate limit configurations based on BASE_RATE_LIMIT."""

    # Session limits
    HOURLY_REQUEST_LIMIT = BASE_RATE_LIMIT * 10  # 500 requests/hour (conservative, allows for bursts)
    CONSECUTIVE_REQUEST_LIMIT = BASE_RATE_LIMIT * 2  # 100 requests (2 minutes of continuous requests)

    # Tier-based rate limits (percentage of base rate)
    TIER_LIMITS = {
        "HOT": int(BASE_RATE_LIMIT * 0.4),  # 20 req/min (40% - most aggressive)
        "TRENDING": int(BASE_RATE_LIMIT * 0.3),  # 15 req/min (30%)
        "ACTIVE": int(BASE_RATE_LIMIT * 0.2),  # 10 req/min (20%)
        "NORMAL": int(BASE_RATE_LIMIT * 0.16),  # 8 req/min (16%)
        "COLD": int(BASE_RATE_LIMIT * 0.1),  # 5 req/min (10% - most conservative)
    }

    # Base delays (inversely proportional to rate limits)
    BASE_DELAYS = {
        "HOT": 60 / TIER_LIMITS["HOT"] * 0.5,  # 1.5s (50% of theoretical max)
        "TRENDING": 60 / TIER_LIMITS["TRENDING"] * 0.5,  # 2.0s
        "ACTIVE": 60 / TIER_LIMITS["ACTIVE"] * 0.5,  # 3.0s
        "NORMAL": 60 / TIER_LIMITS["NORMAL"] * 0.5,  # 3.75s
        "COLD": 60 / TIER_LIMITS["COLD"] * 0.5,  # 6.0s
    }

    # Task timeouts (based on batch sizes and delays)
    TASK_TIMEOUTS = {
        "HOT": int(15 * BASE_DELAYS["HOT"] * 5),  # ~90s (15 players * delay * 5x margin)
        "TRENDING": int(30 * BASE_DELAYS["TRENDING"] * 5),  # ~180s
        "ACTIVE": int(40 * BASE_DELAYS["ACTIVE"] * 5),  # ~240s
        "NORMAL": int(50 * BASE_DELAYS["NORMAL"] * 5),  # ~300s
        "COLD": int(60 * BASE_DELAYS["COLD"] * 5),  # ~360s
    }

    # Circuit breaker thresholds (based on base rate)
    CIRCUIT_BREAKER_RATE_LIMIT_THRESHOLD = max(10, int(BASE_RATE_LIMIT * 0.2))  # 20% of base rate

    @classmethod
    def get_config_summary(cls):
        """Get a summary of all calculated configurations."""
        return {
            "base_rate_limit": BASE_RATE_LIMIT,
            "session_limits": {
                "hourly": cls.HOURLY_REQUEST_LIMIT,
                "consecutive": cls.CONSECUTIVE_REQUEST_LIMIT,
            },
            "tier_rate_limits": cls.TIER_LIMITS,
            "base_delays": {k: f"{v:.1f}s" for k, v in cls.BASE_DELAYS.items()},
            "task_timeouts": {k: f"{v}s" for k, v in cls.TASK_TIMEOUTS.items()},
            "circuit_breaker_threshold": cls.CIRCUIT_BREAKER_RATE_LIMIT_THRESHOLD,
        }


# Usage example:
# from utils.rate_limit_config import RateLimitConfig
# limits = RateLimitConfig.TIER_LIMITS["HOT"]  # Gets HOT tier limit
# config = RateLimitConfig.get_config_summary()  # Gets all configurations
