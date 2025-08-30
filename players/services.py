"""Player data services."""

import asyncio
import logging
import random
from datetime import timedelta
from typing import Dict, List, Optional

import httpx
from asgiref.sync import sync_to_async
from django.db import transaction
from django.db.models import Avg, Count, F, Max, Min, StdDev
from django.utils import timezone

from core.constants import TIER_SCAN_WINDOWS
from players.models import Player, PlayerPriceHistory, PlayerTier

logger = logging.getLogger(__name__)


class PlayerDataService:
    """Service for fetching and managing player data."""

    FUT_API_URL = "https://utas.mob.v4.prd.futc-ext.gcp.ea.com/ut/game/fc25/defid"
    EA_PLAYERS_API_URL = "https://www.ea.com/ea-sports-fc/ultimate-team/web-app/content/25E4CDAE-799B-45BE-B257-667FDCDE8044/2025/fut/items/web/players.json"

    RATE_LIMIT = 50  # requests per minute
    BATCH_SIZE = 200  # max items per request

    def __init__(self, sid: Optional[str] = None):
        self.sid = sid
        self.headers = {}
        if sid:
            self.headers = {
                "x-ut-sid": sid,
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            }
        self.request_count = 0
        self.last_minute_start = 0

    async def _rate_limit(self):
        """Implement rate limiting."""
        self.request_count += 1

        current_time = asyncio.get_event_loop().time()
        elapsed = current_time - self.last_minute_start

        if elapsed >= 60:
            self.request_count = 1
            self.last_minute_start = current_time
        elif self.request_count >= self.RATE_LIMIT:
            wait_time = 60 - elapsed + 1
            await asyncio.sleep(wait_time)
            self.request_count = 1
            self.last_minute_start = asyncio.get_event_loop().time()

    async def fetch_players_batch(self, offset: int = 0, count: int = BATCH_SIZE) -> Optional[List[Dict]]:
        """Fetch a batch of players from FUT API."""
        if not self.sid:
            raise ValueError("SID is required for FUT API calls")

        await self._rate_limit()

        params = {"count": count, "sort": "desc", "start": offset, "type": "player"}

        try:
            async with httpx.AsyncClient(headers=self.headers, timeout=30) as client:
                response = await client.get(self.FUT_API_URL, params=params)

            if response.status_code == 401:
                data = response.json()
                if data.get("reason") == "expired session":
                    raise Exception("Session expired. Need new SID.")

            response.raise_for_status()
            data = response.json()

            if "itemData" in data:
                return data["itemData"]

            return None

        except httpx.HTTPError as e:
            logger.error(f"Request error at offset {offset}: {e}", exc_info=True)
            return None

    async def fetch_all_players(self, checkpoint: Optional[Dict] = None) -> Dict:
        """Fetch all players from FUT API and save to database."""
        offset = checkpoint.get("offset", 0) if checkpoint else 0
        all_players = []
        consecutive_empty = 0
        max_consecutive_empty = 3
        batch_for_db = []

        while True:
            batch = await self.fetch_players_batch(offset)

            if batch is None:
                break

            if len(batch) == 0:
                consecutive_empty += 1
                if consecutive_empty >= max_consecutive_empty:
                    break
            else:
                consecutive_empty = 0
                all_players.extend(batch)
                batch_for_db.extend(batch)

                if len(batch_for_db) >= 500:
                    ok = await sync_to_async(Player.objects.bulk_upsert)(batch_for_db)
                    if ok:
                        batch_for_db = []
                    else:
                        break

            if len(batch) < self.BATCH_SIZE:
                break

            offset += self.BATCH_SIZE

        if batch_for_db:
            await sync_to_async(Player.objects.bulk_upsert)(batch_for_db)

        return {"total_players": len(all_players), "last_offset": offset, "fetch_date": timezone.now().isoformat()}

    async def fetch_player_names(self) -> Optional[Dict]:
        """Fetch player names from EA API."""
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.get(self.EA_PLAYERS_API_URL)
                response.raise_for_status()
                return response.json()
        except httpx.HTTPError as e:
            logger.error(f"Failed to fetch player names: {e}", exc_info=True)
            return None

    async def update_player_names(self) -> Dict:
        """Update player names in the database."""
        data = await self.fetch_player_names()
        if not data:
            raise Exception("Failed to fetch player data")

        total_updated = 0
        all_not_found = []

        @transaction.atomic
        def _do_update():
            nonlocal total_updated, all_not_found
            players = data.get("Players", [])
            for player in players:
                asset_id = player.get("id")
                first_name = player.get("f", "")
                last_name = player.get("l", "")

                if asset_id:
                    updated = Player.objects.filter(asset_id=asset_id).update(
                        first_name=first_name, last_name=last_name
                    )
                    if updated:
                        total_updated += updated
                    else:
                        all_not_found.append(
                            {"asset_id": asset_id, "first_name": first_name, "last_name": last_name, "type": "regular"}
                        )

            legend_players = data.get("LegendsPlayers", [])
            for player in legend_players:
                asset_id = player.get("id")
                first_name = player.get("f", "")
                last_name = player.get("l", "")

                if asset_id:
                    updated = Player.objects.filter(asset_id=asset_id).update(
                        first_name=first_name, last_name=last_name
                    )
                    if updated:
                        total_updated += updated
                    else:
                        all_not_found.append(
                            {"asset_id": asset_id, "first_name": first_name, "last_name": last_name, "type": "legend"}
                        )

        await sync_to_async(_do_update)()

        players = data.get("Players", [])
        legend_players = data.get("LegendsPlayers", [])

        return {
            "total_processed": len(players) + len(legend_players),
            "total_updated": total_updated,
            "total_not_found": len(all_not_found),
            "not_found_players": all_not_found,
        }

    async def get_sample_players(self, limit: int = 5) -> List[Dict]:
        """Get a sample of players from the database."""
        query = (
            Player.objects.filter(rating__gt=80)
            .order_by("-rating")[:limit]
            .values("id", "asset_id", "rating", "preferred_position", "first_name", "last_name")
        )
        players = await sync_to_async(lambda: list(query))()
        return players

    async def get_players_summary(self) -> Dict:
        """Get summary statistics of players in the database."""
        return await sync_to_async(Player.objects.get_summary_stats)()


class CardHotnessCalculator:
    """Calculate card 'hotness' based on multiple factors."""

    def __init__(self):
        self.lookback_hours = 24
        self.min_trades_for_calculation = 3

    async def _calculate_volatility(self, player_id: int) -> float:
        """Calculate price volatility over the last 24 hours."""
        cutoff_time = timezone.now() - timedelta(hours=self.lookback_hours)

        query = PlayerPriceHistory.objects.filter(player_id=player_id, fetched_at__gte=cutoff_time)

        stats = await sync_to_async(query.aggregate)(
            price_std=StdDev("price"), price_avg=Avg("price"), count=Count("id")
        )

        if stats["count"] < self.min_trades_for_calculation or not stats["price_avg"]:
            return 0.0

        if stats["price_std"] is None:
            return 0.0

        # Normalize volatility as coefficient of variation (CV)
        cv = float(stats["price_std"]) / float(stats["price_avg"]) * 100
        # Cap at 100 for scoring purposes
        return min(cv, 100.0)

    async def _calculate_volume(self, player_id: int) -> float:
        """Calculate trade volume over the last 24 hours."""
        cutoff_time = timezone.now() - timedelta(hours=self.lookback_hours)

        # Count completed trades
        trade_count = await sync_to_async(
            PlayerPriceHistory.objects.filter(player_id=player_id, fetched_at__gte=cutoff_time, is_verified=True).count
        )()

        # Normalize to 0-100 scale (assuming 50+ trades/day is very high)
        return min(float(trade_count * 2), 100.0)

    async def _calculate_trend(self, player_id: int) -> float:
        """Calculate price trend (sharp increases/decreases)."""
        cutoff_time = timezone.now() - timedelta(hours=self.lookback_hours)
        half_time = timezone.now() - timedelta(hours=self.lookback_hours / 2)

        # Get average price for first half and second half
        first_half = await sync_to_async(
            PlayerPriceHistory.objects.filter(
                player_id=player_id, fetched_at__gte=cutoff_time, fetched_at__lt=half_time
            ).aggregate
        )(avg_price=Avg("price"))

        second_half = await sync_to_async(
            PlayerPriceHistory.objects.filter(player_id=player_id, fetched_at__gte=half_time).aggregate
        )(avg_price=Avg("price"))

        if not first_half["avg_price"] or not second_half["avg_price"]:
            return 0.0

        # Calculate percentage change
        price_change = (
            (float(second_half["avg_price"]) - float(first_half["avg_price"])) / float(first_half["avg_price"])
        ) * 100

        # Convert to 0-100 scale (±50% change = max score)
        return min(abs(price_change) * 2, 100.0)

    async def _calculate_event_relevance(self, player_id: int) -> float:
        """Calculate relevance to current events (TOTW, promos, SBCs)."""
        # For now, we'll use simple heuristics
        # This can be enhanced with actual event data

        player = await sync_to_async(Player.objects.filter(id=player_id).first)()

        if not player:
            return 0.0

        score = 0.0

        # High-rated players are often needed for SBCs
        if player.rating >= 88:
            score += 30
        elif player.rating >= 85:
            score += 20
        elif player.rating >= 83:
            score += 10

        # Special card types are more event-relevant
        if player.item_type and player.item_type != "player":
            score += 30

        # Rare cards are more valuable for SBCs
        if player.rare_flag == 1:
            score += 20

        # Popular leagues/nations
        popular_leagues = [13, 16, 19, 31, 53]  # Premier League, Ligue 1, Bundesliga, Serie A, La Liga
        popular_nations = [
            14,
            18,
            21,
            27,
            34,
            45,
            52,
            54,
        ]  # England, France, Germany, Italy, Spain, Brazil, Argentina, Portugal

        if player.league_id in popular_leagues:
            score += 10

        if player.nation in popular_nations:
            score += 10

        return min(score, 100.0)

    async def calculate_hotness_score(self, player_id: int) -> float:
        """Calculate overall hotness score for a player."""
        volatility_score = await self._calculate_volatility(player_id) * 0.3
        volume_score = await self._calculate_volume(player_id) * 0.3
        trend_score = await self._calculate_trend(player_id) * 0.2
        event_score = await self._calculate_event_relevance(player_id) * 0.2

        total_score = volatility_score + volume_score + trend_score + event_score

        # Update the PlayerTier record
        await sync_to_async(PlayerTier.objects.update_or_create)(
            player_id=player_id,
            defaults={
                "hotness_score": total_score,
                "volatility_score": volatility_score / 0.3,
                "volume_score": volume_score / 0.3,
                "trend_score": trend_score / 0.2,
                "event_score": event_score / 0.2,
                "last_calculated": timezone.now(),
            },
        )

        return total_score

    def get_tier_from_score(self, score: float) -> str:
        """Determine tier based on hotness score."""
        if score >= 80:
            return PlayerTier.HOT
        elif score >= 60:
            return PlayerTier.TRENDING
        elif score >= 40:
            return PlayerTier.ACTIVE
        elif score >= 20:
            return PlayerTier.NORMAL
        else:
            return PlayerTier.COLD

    async def assign_player_tier(self, player_id: int) -> str:
        """Calculate hotness and assign tier to a player."""
        score = await self.calculate_hotness_score(player_id)
        tier = self.get_tier_from_score(score)

        # Update tier in database
        await sync_to_async(PlayerTier.objects.filter(player_id=player_id).update)(tier=tier)

        return tier

    async def recalculate_all_tiers(self, batch_size: int = 100):
        """Recalculate tiers for all players."""
        # Get all players with recent price activity
        cutoff_time = timezone.now() - timedelta(hours=48)

        player_ids = await sync_to_async(
            lambda: list(
                PlayerPriceHistory.objects.filter(fetched_at__gte=cutoff_time)
                .values_list("player_id", flat=True)
                .distinct()
            )
        )()

        logger.info(f"Recalculating tiers for {len(player_ids)} players")

        # Process in batches
        for i in range(0, len(player_ids), batch_size):
            batch = player_ids[i : i + batch_size]
            tasks = [self.assign_player_tier(player_id) for player_id in batch]
            await asyncio.gather(*tasks)
            logger.info(f"Processed {min(i + batch_size, len(player_ids))}/{len(player_ids)} players")

        # Set all inactive players to COLD
        inactive_player_ids = await sync_to_async(
            lambda: list(Player.objects.exclude(id__in=player_ids).values_list("id", flat=True))
        )()

        if inactive_player_ids:
            await sync_to_async(PlayerTier.objects.filter(player_id__in=inactive_player_ids).update)(
                tier=PlayerTier.COLD, hotness_score=0, last_calculated=timezone.now()
            )
            logger.info(f"Set {len(inactive_player_ids)} inactive players to COLD tier")


class TierBasedPriorityQueue:
    """Manage priority queues for different player tiers."""

    def __init__(self):
        self.tier_configs = {
            PlayerTier.HOT: {
                "interval_minutes": TIER_SCAN_WINDOWS["HOT"].total_seconds() / 60,
                "batch_size_min": 10,
                "batch_size_max": 15,
            },
            PlayerTier.TRENDING: {
                "interval_minutes": TIER_SCAN_WINDOWS["TRENDING"].total_seconds() / 60,
                "batch_size_min": 20,
                "batch_size_max": 30,
            },
            PlayerTier.ACTIVE: {
                "interval_minutes": TIER_SCAN_WINDOWS["ACTIVE"].total_seconds() / 60,
                "batch_size_min": 30,
                "batch_size_max": 40,
            },
            PlayerTier.NORMAL: {
                "interval_minutes": TIER_SCAN_WINDOWS["NORMAL"].total_seconds() / 60,
                "batch_size_min": 40,
                "batch_size_max": 50,
            },
            PlayerTier.COLD: {
                "interval_minutes": TIER_SCAN_WINDOWS["COLD"].total_seconds() / 60,
                "batch_size_min": 50,
                "batch_size_max": 60,
            },
        }

    async def get_players_for_tier(self, tier: str, limit: Optional[int] = None) -> List[int]:
        """Get player IDs for a specific tier, ordered by last scraped time."""
        query = PlayerTier.objects.filter(tier=tier).select_related("player")

        # Join with PlayerPrice to get last scraped time
        # Use nulls_first=True to prioritize never-scraped players
        query = query.annotate(last_scraped=Max("player__prices__last_updated")).order_by(
            F("last_scraped").asc(nulls_first=True)
        )

        if limit:
            query = query[:limit]

        player_ids = await sync_to_async(lambda: list(query.values_list("player_id", flat=True)))()

        return player_ids

    async def get_next_batch(self, tier: str) -> List[int]:
        """Get the next batch of players to scrape for a tier."""
        config = self.tier_configs[tier]
        batch_size = random.randint(config["batch_size_min"], config["batch_size_max"])

        player_ids = await self.get_players_for_tier(tier, limit=batch_size * 2)

        # Randomize order within the batch to avoid patterns
        if len(player_ids) > batch_size:
            selected = random.sample(player_ids, batch_size)
        else:
            selected = player_ids
            random.shuffle(selected)

        return selected

    async def should_scrape_tier(self, tier: str) -> bool:
        """Check if it's time to scrape a tier based on interval."""
        config = self.tier_configs[tier]
        interval = timedelta(minutes=config["interval_minutes"])

        # Check last scrape time for this tier
        last_scrape = await sync_to_async(
            lambda: PlayerTier.objects.filter(tier=tier)
            .annotate(last_scraped=Max("player__prices__last_updated"))
            .aggregate(oldest=Min("last_scraped"))
        )()

        if not last_scrape["oldest"]:
            return True  # No data, should scrape

        return timezone.now() - last_scrape["oldest"] >= interval
