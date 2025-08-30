import random
import time
from typing import TypeVar

T = TypeVar("T")


def human_delay(base_seconds: float, variance: float = 0.15) -> float:
    """
    Add human-like variance to delays.

    Args:
        base_seconds: Base delay time
        variance: Percentage variance (0.15 = ±15%)

    Returns:
        Varied delay time
    """
    jitter = base_seconds * variance
    return base_seconds + random.uniform(-jitter, jitter)


def human_sleep(base_seconds: float):
    """Sleep with human-like variance."""
    time.sleep(human_delay(base_seconds))


def exponential_backoff_with_jitter(attempt: int, base: float = 2.0, max_delay: float = 300) -> float:
    """
    Exponential backoff with jitter for retries.

    Args:
        attempt: Current attempt number (0-indexed)
        base: Base multiplier for exponential growth
        max_delay: Maximum delay in seconds

    Returns:
        Delay time with jitter
    """
    delay = min(base**attempt, max_delay)
    return human_delay(delay, variance=0.3)
