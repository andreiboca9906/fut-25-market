import asyncio
import json
import logging
import time
from typing import Dict, Optional

import redis.asyncio as redis

logger = logging.getLogger(__name__)


class DistributedTokenBucket:
    """
    Redis-based token bucket for distributed rate limiting.

    Configurations per tier:
    - HOT: 20 req/min
    - TRENDING: 15 req/min
    - ACTIVE: 10 req/min
    - NORMAL: 8 req/min
    - COLD: 5 req/min
    """

    # Default rate limits per tier (requests per minute)
    TIER_LIMITS = {
        "HOT": 20,
        "TRENDING": 15,
        "ACTIVE": 10,
        "NORMAL": 8,
        "COLD": 5,
    }

    def __init__(
        self,
        redis_client: Optional[redis.Redis] = None,
        redis_url: str = "redis://localhost:6379",
        key_prefix: str = "rate_limit",
    ):
        self.redis_client = redis_client
        self.redis_url = redis_url
        self.key_prefix = key_prefix
        self._local_cache: Dict[str, dict] = {}  # Fallback for Redis failures

    async def _get_redis(self) -> redis.Redis:
        """Get or create Redis connection."""
        if not self.redis_client:
            self.redis_client = await redis.from_url(self.redis_url)
        return self.redis_client

    def _get_bucket_key(self, tier: str, identifier: str = "default") -> str:
        """Generate Redis key for bucket."""
        return f"{self.key_prefix}:{tier}:{identifier}"

    async def _get_bucket_state(self, key: str, max_tokens: int) -> dict:
        """Get current bucket state from Redis or local cache."""
        try:
            redis_client = await self._get_redis()
            data = await redis_client.get(key)

            if data:
                return json.loads(data)
            else:
                # Initialize new bucket
                now = time.time()
                state = {
                    "tokens": max_tokens,
                    "last_refill": now,
                }
                await redis_client.set(key, json.dumps(state), ex=3600)  # 1 hour expiry
                return state

        except Exception as e:
            logger.warning(f"Redis error, using local cache: {e}")
            # Fallback to local cache
            if key not in self._local_cache:
                self._local_cache[key] = {
                    "tokens": max_tokens,
                    "last_refill": time.time(),
                }
            return self._local_cache[key]

    async def _save_bucket_state(self, key: str, state: dict):
        """Save bucket state to Redis or local cache."""
        try:
            redis_client = await self._get_redis()
            await redis_client.set(key, json.dumps(state), ex=3600)  # 1 hour expiry
        except Exception as e:
            logger.warning(f"Redis save error, using local cache: {e}")
            self._local_cache[key] = state

    def _calculate_refill(self, state: dict, max_tokens: int, refill_rate: float) -> dict:
        """Calculate token refill based on elapsed time."""
        now = time.time()
        elapsed = now - state["last_refill"]

        # Calculate tokens to add (refill_rate is tokens per second)
        tokens_to_add = elapsed * refill_rate

        # Update state
        state["tokens"] = min(max_tokens, state["tokens"] + tokens_to_add)
        state["last_refill"] = now

        return state

    async def acquire(
        self,
        tier: str,
        tokens: int = 1,
        identifier: str = "default",
        wait: bool = True,
        max_wait: float = 60.0,
    ) -> bool:
        """
        Acquire tokens from the bucket.

        Args:
            tier: Player tier (HOT, TRENDING, etc.)
            tokens: Number of tokens to acquire
            identifier: Optional identifier for separate buckets (e.g., session_id)
            wait: Whether to wait if tokens not available
            max_wait: Maximum time to wait for tokens in seconds

        Returns:
            True if tokens acquired, False otherwise
        """
        # Get rate limit for tier
        requests_per_minute = self.TIER_LIMITS.get(tier, 10)
        max_tokens = requests_per_minute
        refill_rate = requests_per_minute / 60.0  # tokens per second

        key = self._get_bucket_key(tier, identifier)
        start_time = time.time()

        while True:
            # Get current state
            state = await self._get_bucket_state(key, max_tokens)

            # Calculate refill
            state = self._calculate_refill(state, max_tokens, refill_rate)

            # Check if we have enough tokens
            if state["tokens"] >= tokens:
                state["tokens"] -= tokens
                await self._save_bucket_state(key, state)
                return True

            # If not waiting, return immediately
            if not wait:
                await self._save_bucket_state(key, state)
                return False

            # Check timeout
            if time.time() - start_time > max_wait:
                logger.warning(f"Token bucket timeout for {tier}:{identifier}")
                return False

            # Calculate wait time
            tokens_needed = tokens - state["tokens"]
            wait_time = tokens_needed / refill_rate
            wait_time = min(wait_time, 1.0)  # Cap at 1 second per iteration

            # Save state and wait
            await self._save_bucket_state(key, state)
            await asyncio.sleep(wait_time)

    async def get_wait_time(self, tier: str, tokens: int = 1, identifier: str = "default") -> float:
        """
        Get estimated wait time for tokens to be available.

        Returns:
            Estimated wait time in seconds
        """
        requests_per_minute = self.TIER_LIMITS.get(tier, 10)
        max_tokens = requests_per_minute
        refill_rate = requests_per_minute / 60.0

        key = self._get_bucket_key(tier, identifier)
        state = await self._get_bucket_state(key, max_tokens)
        state = self._calculate_refill(state, max_tokens, refill_rate)

        if state["tokens"] >= tokens:
            return 0.0

        tokens_needed = tokens - state["tokens"]
        return tokens_needed / refill_rate

    async def get_status(self, tier: str, identifier: str = "default") -> dict:
        """Get current status of a token bucket."""
        requests_per_minute = self.TIER_LIMITS.get(tier, 10)
        max_tokens = requests_per_minute
        refill_rate = requests_per_minute / 60.0

        key = self._get_bucket_key(tier, identifier)
        state = await self._get_bucket_state(key, max_tokens)
        state = self._calculate_refill(state, max_tokens, refill_rate)

        return {
            "tier": tier,
            "identifier": identifier,
            "available_tokens": state["tokens"],
            "max_tokens": max_tokens,
            "refill_rate_per_second": refill_rate,
            "requests_per_minute": requests_per_minute,
        }

    async def reset(self, tier: str, identifier: str = "default"):
        """Reset a token bucket to full capacity."""
        requests_per_minute = self.TIER_LIMITS.get(tier, 10)
        max_tokens = requests_per_minute

        key = self._get_bucket_key(tier, identifier)
        state = {
            "tokens": max_tokens,
            "last_refill": time.time(),
        }
        await self._save_bucket_state(key, state)

    async def close(self):
        """Close Redis connection."""
        if self.redis_client:
            await self.redis_client.close()


class AdaptiveRateLimiter:
    """
    Adaptive rate limiter that adjusts limits based on success/failure rates.
    """

    def __init__(self, token_bucket: DistributedTokenBucket):
        self.token_bucket = token_bucket
        self.metrics: Dict[str, dict] = {}
        self.adjustment_interval = 300  # 5 minutes
        self.last_adjustment: Dict[str, float] = {}

    def _get_metrics_key(self, tier: str, identifier: str) -> str:
        return f"{tier}:{identifier}"

    async def record_request(
        self,
        tier: str,
        identifier: str,
        success: bool,
        response_time: float,
    ):
        """Record request metrics."""
        key = self._get_metrics_key(tier, identifier)

        if key not in self.metrics:
            self.metrics[key] = {
                "success_count": 0,
                "failure_count": 0,
                "total_response_time": 0,
                "rate_limit_hits": 0,
            }

        if success:
            self.metrics[key]["success_count"] += 1
        else:
            self.metrics[key]["failure_count"] += 1

        self.metrics[key]["total_response_time"] += response_time

    async def record_rate_limit_hit(self, tier: str, identifier: str):
        """Record when rate limit is hit."""
        key = self._get_metrics_key(tier, identifier)

        if key not in self.metrics:
            self.metrics[key] = {"rate_limit_hits": 0}

        self.metrics[key]["rate_limit_hits"] = self.metrics[key].get("rate_limit_hits", 0) + 1

    async def adjust_limits(self, tier: str, identifier: str = "default"):
        """
        Automatically adjust rate limits based on metrics.
        """
        key = self._get_metrics_key(tier, identifier)

        # Check if enough time has passed since last adjustment
        now = time.time()
        if key in self.last_adjustment:
            if now - self.last_adjustment[key] < self.adjustment_interval:
                return

        if key not in self.metrics:
            return

        metrics = self.metrics[key]
        total_requests = metrics.get("success_count", 0) + metrics.get("failure_count", 0)

        if total_requests == 0:
            return

        success_rate = metrics.get("success_count", 0) / total_requests
        rate_limit_hits = metrics.get("rate_limit_hits", 0)

        # Get current limit
        current_limit = self.token_bucket.TIER_LIMITS[tier]
        new_limit = current_limit

        # Adjust based on success rate and rate limit hits
        if rate_limit_hits > 5:
            # Too many rate limit hits, decrease limit
            new_limit = int(current_limit * 0.8)
            logger.info(f"Decreasing rate limit for {tier}:{identifier} from {current_limit} to {new_limit}")
        elif success_rate > 0.98 and rate_limit_hits == 0:
            # Very high success rate, carefully increase
            new_limit = int(current_limit * 1.05)
            logger.info(f"Increasing rate limit for {tier}:{identifier} from {current_limit} to {new_limit}")

        # Apply bounds
        min_limit = 3
        max_limit = 30
        new_limit = max(min_limit, min(max_limit, new_limit))

        # Update limit
        if new_limit != current_limit:
            self.token_bucket.TIER_LIMITS[tier] = new_limit
            self.last_adjustment[key] = now

        # Reset metrics
        self.metrics[key] = {
            "success_count": 0,
            "failure_count": 0,
            "total_response_time": 0,
            "rate_limit_hits": 0,
        }

    def get_metrics(self, tier: str, identifier: str = "default") -> dict:
        """Get current metrics for a tier/identifier."""
        key = self._get_metrics_key(tier, identifier)

        if key not in self.metrics:
            return {}

        metrics = self.metrics[key]
        total_requests = metrics.get("success_count", 0) + metrics.get("failure_count", 0)

        if total_requests == 0:
            return metrics

        # Calculate additional metrics
        metrics["success_rate"] = metrics.get("success_count", 0) / total_requests
        metrics["avg_response_time"] = metrics.get("total_response_time", 0) / total_requests
        metrics["current_limit"] = self.token_bucket.TIER_LIMITS[tier]

        return metrics


# Global rate limiter instances
token_bucket = DistributedTokenBucket()
adaptive_limiter = AdaptiveRateLimiter(token_bucket)
