"""Test script for the priority system."""

import asyncio
import os

import django
from asgiref.sync import sync_to_async
from django.db.models import Count

# Setup Django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "fut_market.settings")
django.setup()

from decimal import Decimal

from django.utils import timezone

from players.models import Player, PlayerPriceHistory, PlayerTier
from players.services import CardHotnessCalculator, TierBasedPriorityQueue


async def test_hotness_calculator():
    """Test the hotness calculator."""
    print("\n=== Testing Hotness Calculator ===")

    calculator = CardHotnessCalculator()

    # Get a sample player with price history
    player = await sync_to_async(Player.objects.filter(price_history__isnull=False).first)()

    if player:
        print(f"Testing with player: {player} (ID: {player.id})")

        # Calculate hotness score
        score = await calculator.calculate_hotness_score(player.id)
        tier = calculator.get_tier_from_score(score)

        print(f"Hotness Score: {score:.2f}")
        print(f"Assigned Tier: {tier}")

        # Get tier details
        tier_obj = await sync_to_async(PlayerTier.objects.filter(player_id=player.id).first)()

        if tier_obj:
            print(f"Volatility Score: {tier_obj.volatility_score:.2f}")
            print(f"Volume Score: {tier_obj.volume_score:.2f}")
            print(f"Trend Score: {tier_obj.trend_score:.2f}")
            print(f"Event Score: {tier_obj.event_score:.2f}")
    else:
        print("No players with price history found. Creating sample data...")

        # Create sample price history for testing
        player = await sync_to_async(Player.objects.first)()
        if player:
            now = timezone.now()
            for i in range(10):
                await sync_to_async(PlayerPriceHistory.objects.create)(
                    player=player,
                    platform="ps",
                    price=Decimal(1000 + i * 50),
                    fetched_at=now - timezone.timedelta(hours=i),
                    is_verified=True,
                )
            print(f"Created sample price history for {player}")

            # Now calculate
            score = await calculator.calculate_hotness_score(player.id)
            tier = calculator.get_tier_from_score(score)
            print(f"Hotness Score: {score:.2f}")
            print(f"Assigned Tier: {tier}")


async def test_priority_queue():
    """Test the priority queue system."""
    print("\n=== Testing Priority Queue ===")

    queue = TierBasedPriorityQueue()

    # Test each tier
    for tier in [PlayerTier.HOT, PlayerTier.TRENDING, PlayerTier.ACTIVE, PlayerTier.NORMAL, PlayerTier.COLD]:
        print(f"\nTesting {tier} tier:")

        # Get configuration
        config = queue.tier_configs[tier]
        print(f"  Interval: {config['interval_minutes']} minutes")
        print(f"  Batch size: {config['batch_size_min']}-{config['batch_size_max']}")

        # Get players for this tier
        player_ids = await queue.get_players_for_tier(tier, limit=5)
        print(f"  Sample players: {player_ids[:5]}")

        # Test batch retrieval
        batch = await queue.get_next_batch(tier)
        print(f"  Batch size: {len(batch)}")

        # Test should_scrape
        should_scrape = await queue.should_scrape_tier(tier)
        print(f"  Should scrape now: {should_scrape}")


async def test_tier_distribution():
    """Test the distribution of players across tiers."""
    print("\n=== Tier Distribution ===")

    distribution = await sync_to_async(
        lambda: list(PlayerTier.objects.values("tier").annotate(count=Count("player_id")).order_by("tier"))
    )()

    total = sum(d["count"] for d in distribution)

    for item in distribution:
        percentage = (item["count"] / total * 100) if total > 0 else 0
        print(f"{item['tier']:10} : {item['count']:6} players ({percentage:.1f}%)")

    print(f"{'TOTAL':10} : {total:6} players")


async def main():
    """Run all tests."""
    print("Testing EA FC 26 Priority System")
    print("=" * 40)

    await test_hotness_calculator()
    await test_priority_queue()
    await test_tier_distribution()

    print("\n" + "=" * 40)
    print("All tests completed!")


if __name__ == "__main__":
    asyncio.run(main())
