"""Player data services."""

import asyncio
import logging
from datetime import datetime
from typing import Dict, List, Optional

import httpx
from asgiref.sync import sync_to_async
from django.db import transaction

from players.models import Player

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

        return {"total_players": len(all_players), "last_offset": offset, "fetch_date": datetime.now().isoformat()}

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
