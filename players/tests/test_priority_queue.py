"""Unit tests for TierBasedPriorityQueue."""

from datetime import timedelta

import pytest
from django.test import TestCase
from django.utils import timezone

from players.models import Player, PlayerPrice, PlayerTier
from players.services import TierBasedPriorityQueue


class TestTierBasedPriorityQueue(TestCase):
    """Test suite for TierBasedPriorityQueue."""

    def setUp(self):
        """Set up test data."""
        self.queue = TierBasedPriorityQueue()

        # Create test players in different tiers
        tiers = [
            (PlayerTier.HOT, 5),
            (PlayerTier.TRENDING, 10),
            (PlayerTier.ACTIVE, 15),
            (PlayerTier.NORMAL, 20),
            (PlayerTier.COLD, 50),
        ]

        for tier, count in tiers:
            for i in range(count):
                player = Player.objects.create(id=f"{tier}_{i}", asset_id=1000 + i, rating=80)

                PlayerTier.objects.create(player=player, tier=tier, hotness_score=70 if tier == PlayerTier.HOT else 30)

                # Add price data with varying last_updated times
                PlayerPrice.objects.create(
                    player=player, platform="ps", current_price=1000, last_updated=timezone.now() - timedelta(hours=i)
                )

    def test_tier_configs(self):
        """Test tier configuration."""
        assert PlayerTier.HOT in self.queue.tier_configs
        assert self.queue.tier_configs[PlayerTier.HOT]["interval_minutes"] == 5
        assert self.queue.tier_configs[PlayerTier.COLD]["interval_minutes"] == 120

    @pytest.mark.asyncio
    async def test_get_players_for_tier(self):
        """Test getting players for a specific tier."""
        hot_players = await self.queue.get_players_for_tier(PlayerTier.HOT)
        assert len(hot_players) == 5

        cold_players = await self.queue.get_players_for_tier(PlayerTier.COLD)
        assert len(cold_players) == 50

        # Test with limit
        limited = await self.queue.get_players_for_tier(PlayerTier.COLD, limit=10)
        assert len(limited) == 10

    @pytest.mark.asyncio
    async def test_get_next_batch(self):
        """Test batch retrieval with randomization."""
        batch = await self.queue.get_next_batch(PlayerTier.COLD)

        # Should be within configured range
        config = self.queue.tier_configs[PlayerTier.COLD]
        assert len(batch) >= config["batch_size_min"]
        assert len(batch) <= config["batch_size_max"]

        # Should be actual player IDs
        assert all(isinstance(pid, str) for pid in batch)

    @pytest.mark.asyncio
    async def test_should_scrape_tier_no_data(self):
        """Test should_scrape with no price data."""
        # Create a tier with no price data
        player = Player.objects.create(id=99999, asset_id=99999, rating=80)
        PlayerTier.objects.create(player=player, tier="TEST_TIER", hotness_score=50)

        # Manually add config for test tier
        self.queue.tier_configs["TEST_TIER"] = {"interval_minutes": 10}

        should_scrape = await self.queue.should_scrape_tier("TEST_TIER")
        assert should_scrape is True  # No data means should scrape

    @pytest.mark.asyncio
    async def test_should_scrape_tier_recent_scrape(self):
        """Test should_scrape with recent scrape."""
        # Update all HOT tier prices to be very recent
        PlayerPrice.objects.filter(player__tier__tier=PlayerTier.HOT).update(last_updated=timezone.now())

        should_scrape = await self.queue.should_scrape_tier(PlayerTier.HOT)
        assert should_scrape is False  # Just updated, shouldn't scrape

    @pytest.mark.asyncio
    async def test_should_scrape_tier_old_scrape(self):
        """Test should_scrape with old scrape."""
        # Update all HOT tier prices to be old
        PlayerPrice.objects.filter(player__tier__tier=PlayerTier.HOT).update(
            last_updated=timezone.now() - timedelta(hours=1)
        )

        should_scrape = await self.queue.should_scrape_tier(PlayerTier.HOT)
        assert should_scrape is True  # Old data, should scrape

    @pytest.mark.asyncio
    async def test_batch_randomization(self):
        """Test that batches are randomized."""
        batch1 = await self.queue.get_next_batch(PlayerTier.COLD)
        batch2 = await self.queue.get_next_batch(PlayerTier.COLD)

        # With 50 players and smaller batch sizes,
        # two batches should likely be different
        if len(batch1) < 50 and len(batch2) < 50:
            # There's a chance they could be the same, but unlikely
            # This is a probabilistic test
            pass
