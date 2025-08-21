import random
import time
from typing import List, TypeVar

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


class RequestPatternRandomizer:
    """Randomizes request patterns to avoid detection."""

    def __init__(self, base_batch_size: int = 50, batch_variance: float = 0.2):
        self.base_batch_size = base_batch_size
        self.batch_variance = batch_variance
        self.skip_probability = 0.05  # 5% chance to skip and return later
        self.micro_pause_range = (0.5, 2.0)  # Random pauses between requests

    def get_random_batch_size(self) -> int:
        """Get randomized batch size with variance."""
        variance = int(self.base_batch_size * self.batch_variance)
        return random.randint(max(1, self.base_batch_size - variance), self.base_batch_size + variance)

    def should_skip_batch(self) -> bool:
        """Randomly decide whether to skip a batch."""
        return random.random() < self.skip_probability

    def get_micro_pause(self) -> float:
        """Get random micro-pause duration between requests."""
        return random.uniform(*self.micro_pause_range)

    def shuffle_with_groups(self, items: List[T], group_size: int = 5) -> List[T]:
        """
        Shuffle items while keeping some locality (not completely random).
        This mimics human behavior of processing related items together.
        """
        if len(items) <= group_size:
            random.shuffle(items)
            return items

        # Split into groups
        groups = [items[i : i + group_size] for i in range(0, len(items), group_size)]

        # Shuffle within groups
        for group in groups:
            random.shuffle(group)

        # Shuffle the groups themselves
        random.shuffle(groups)

        # Flatten back to list
        result = []
        for group in groups:
            result.extend(group)

        return result

    def add_random_delays(self, base_delay: float = 1.0) -> float:
        """
        Add multiple layers of randomness to delays.
        Combines different patterns to be less predictable.
        """
        # Base human variance
        delay = human_delay(base_delay)

        # Occasionally add longer pauses (simulate distraction)
        if random.random() < 0.1:  # 10% chance
            delay += random.uniform(2, 5)

        # Very rarely add very long pause (simulate break)
        if random.random() < 0.02:  # 2% chance
            delay += random.uniform(10, 30)

        return delay

    def get_burst_pattern(self, total_items: int) -> List[int]:
        """
        Generate a burst pattern for processing items.
        Simulates human behavior of working in bursts with breaks.
        """
        pattern = []
        remaining = total_items

        while remaining > 0:
            # Random burst size (humans work in chunks)
            burst_size = random.randint(3, min(15, remaining))
            pattern.append(burst_size)
            remaining -= burst_size

            if remaining > 0:
                # Add pause indicator (negative number = pause duration)
                pause_duration = random.uniform(5, 15)
                pattern.append(-pause_duration)

        return pattern
