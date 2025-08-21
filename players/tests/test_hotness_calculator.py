"""Unit tests for CardHotnessCalculator."""

from decimal import Decimal

import pytest
from django.test import TestCase
from django.utils import timezone

from players.models import Player, PlayerPriceHistory, PlayerTier
from players.services import CardHotnessCalculator


class TestCardHotnessCalculator(TestCase):
    """Test suite for CardHotnessCalculator."""

    def setUp(self):
        """Set up test data."""
        self.calculator = CardHotnessCalculator()

        # Create a test player
        self.player = Player.objects.create(
            id=1,
            asset_id=1001,
            rating=85,
            rare_flag=1,
            league_id=13,  # Premier League
            nation=14,  # England
            item_type="player",
        )

        # Create price history
        now = timezone.now()
        for i in range(10):
            PlayerPriceHistory.objects.create(
                player=self.player,
                platform="ps",
                price=Decimal(1000 + i * 10),  # Increasing prices
                fetched_at=now - timezone.timedelta(hours=i),
                is_verified=True,
            )

    def test_get_tier_from_score(self):
        """Test tier assignment based on score."""
        calculator = CardHotnessCalculator()

        assert calculator.get_tier_from_score(85) == PlayerTier.HOT
        assert calculator.get_tier_from_score(70) == PlayerTier.TRENDING
        assert calculator.get_tier_from_score(45) == PlayerTier.ACTIVE
        assert calculator.get_tier_from_score(25) == PlayerTier.NORMAL
        assert calculator.get_tier_from_score(10) == PlayerTier.COLD

    @pytest.mark.asyncio
    async def test_calculate_volatility(self):
        """Test volatility calculation."""
        # Add more varied prices for volatility
        now = timezone.now()
        prices = [1000, 1200, 900, 1100, 950, 1150]
        for i, price in enumerate(prices):
            PlayerPriceHistory.objects.create(
                player=self.player,
                platform="ps",
                price=Decimal(price),
                fetched_at=now - timezone.timedelta(hours=i * 2),
                is_verified=True,
            )

        volatility = await self.calculator._calculate_volatility(self.player.id)

        # Should have some volatility
        assert volatility > 0
        assert volatility <= 100

    @pytest.mark.asyncio
    async def test_calculate_volume(self):
        """Test volume calculation."""
        volume = await self.calculator._calculate_volume(self.player.id)

        # We have 10 verified trades in history
        assert volume == 20  # 10 trades * 2 (normalization factor)

    @pytest.mark.asyncio
    async def test_calculate_trend(self):
        """Test trend calculation."""
        # Clear existing history
        PlayerPriceHistory.objects.filter(player=self.player).delete()

        # Create clear upward trend
        now = timezone.now()
        # First half: lower prices
        for i in range(5):
            PlayerPriceHistory.objects.create(
                player=self.player,
                platform="ps",
                price=Decimal(1000),
                fetched_at=now - timezone.timedelta(hours=20 - i),
                is_verified=True,
            )

        # Second half: higher prices
        for i in range(5):
            PlayerPriceHistory.objects.create(
                player=self.player,
                platform="ps",
                price=Decimal(1500),
                fetched_at=now - timezone.timedelta(hours=5 - i),
                is_verified=True,
            )

        trend = await self.calculator._calculate_trend(self.player.id)

        # 50% increase should give max score
        assert trend == 100.0

    @pytest.mark.asyncio
    async def test_calculate_event_relevance(self):
        """Test event relevance calculation."""
        relevance = await self.calculator._calculate_event_relevance(self.player.id)

        # Player has: rating 85 (+20), rare (+20), premier league (+10), england (+10) = 60
        assert relevance == 60.0

    @pytest.mark.asyncio
    async def test_calculate_hotness_score(self):
        """Test overall hotness score calculation."""
        score = await self.calculator.calculate_hotness_score(self.player.id)

        # Should create/update PlayerTier
        tier = await PlayerTier.objects.aget(player_id=self.player.id)
        assert tier.hotness_score == score
        assert score >= 0
        assert score <= 100

    @pytest.mark.asyncio
    async def test_assign_player_tier(self):
        """Test tier assignment."""
        tier = await self.calculator.assign_player_tier(self.player.id)

        # Verify tier was saved
        player_tier = await PlayerTier.objects.aget(player_id=self.player.id)
        assert player_tier.tier == tier
