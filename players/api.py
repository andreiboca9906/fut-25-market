"""Players API endpoints using Django Ninja."""

import logging
from datetime import datetime, timedelta
from typing import Optional

from asgiref.sync import sync_to_async
from django.db import transaction
from ninja import Router
from ninja.errors import HttpError

from players.models import Player, PlayerPrice, PlayerPriceHistory
from players.services import PlayerDataService

logger = logging.getLogger(__name__)
router = Router()


@router.post(
    path="/fetch-all",
    summary="[FUT Scraping] [Heavy] Fetch all players",
    description="Fetch all players from FUT authenticated API using defid endpoint and store in database. This is a heavy operation and should be used with caution.",
)
async def fetch_all_players(request):
    """Fetch all players from FUT API using defid endpoint and store in database."""
    try:
        sid = request.headers.get("x-ut-sid")
        if not sid:
            raise HttpError(400, "Missing X-UT-SID header")

        service = PlayerDataService(sid)
        result = await service.fetch_all_players()

        return {
            "success": True,
            "message": f"Fetched {result['total_players']} players",
            "meta": {"last_offset": result["last_offset"], "fetch_date": result["fetch_date"]},
        }
    except Exception as e:
        logger.error(f"Error fetching players: {e}")
        raise HttpError(500, f"An error occurred: {str(e)}")


@router.post(
    path="/update-names",
    summary="[FUT Scraping] [Heavy] Update all player names (first and last names)",
    description="Fetch player names from EA public API and update in database.",
)
async def update_player_names(request):
    """Update player names in database."""
    try:
        sid = request.headers.get("x-ut-sid", "")
        service = PlayerDataService(sid)
        result = await service.update_player_names()
        return {"success": True, "message": "Successfully updated names for all players", "meta": {**result}}
    except Exception as e:
        logger.error(f"Error updating player names: {e}")
        raise HttpError(500, f"An error occurred: {str(e)}")


@router.get("/sample")
async def get_players_sample(request, limit: int = 5):
    """Get a sample of players from database."""
    try:
        query = (
            Player.objects.filter(rating__gt=80)
            .order_by("-rating")[:limit]
            .values("id", "asset_id", "rating", "preferred_position", "first_name", "last_name")
        )
        players = await sync_to_async(lambda: list(query))()

        return {"success": True, "count": len(players), "players": players}

    except Exception as e:
        logger.error(f"Error getting players sample: {e}")
        raise HttpError(500, f"An error occurred: {str(e)}")


@router.get("/summary")
async def get_players_summary(request):
    """Get summary statistics of players in database."""
    try:
        summary = await sync_to_async(Player.objects.get_summary_stats)()

        return {"success": True, "summary": summary}

    except Exception as e:
        logger.error(f"Error getting players summary: {e}")
        raise HttpError(500, f"An error occurred: {str(e)}")


@router.post("/price/update")
async def update_player_price(request, player_id: int, platform: str, price: float, currency: str = "COINS"):
    """Update player price and add to history."""
    try:

        @transaction.atomic
        def _do_update():
            # Update or create current price
            PlayerPrice.objects.update_price(player_id, platform, price, currency)

            # Add to price history
            PlayerPriceHistory.objects.create(player_id=player_id, platform=platform, price=price, currency=currency)

        await sync_to_async(_do_update)()
        success = True

        if success:
            return {"success": True, "message": f"Successfully updated price for player {player_id} on {platform}"}
        else:
            raise HttpError(500, "Failed to update player price")

    except Exception as e:
        logger.error(f"Error updating player price: {e}")
        raise HttpError(500, f"An error occurred: {str(e)}")


@router.get("/price/{player_id}")
async def get_player_prices(request, player_id: int, platform: Optional[str] = None):
    """Get current prices for a player."""
    try:
        query = PlayerPrice.objects.filter(player_id=player_id)
        if platform:
            query = query.filter(platform=platform)

        prices = await sync_to_async(lambda: list(query.values()))()

        return {"success": True, "player_id": player_id, "prices": prices}

    except Exception as e:
        logger.error(f"Error getting player prices: {e}")
        raise HttpError(500, f"An error occurred: {str(e)}")


@router.get("/price/history/{player_id}")
async def get_price_history(request, player_id: int, platform: Optional[str] = None, days: int = 7):
    """Get price history for a player."""
    try:
        since = datetime.now() - timedelta(days=days)

        query = PlayerPriceHistory.objects.filter(player_id=player_id, fetched_at__gte=since)

        if platform:
            query = query.filter(platform=platform)

        history = await sync_to_async(lambda: list(query.order_by("-fetched_at").values()))()

        return {"success": True, "player_id": player_id, "days": days, "count": len(history), "history": history}

    except Exception as e:
        logger.error(f"Error getting price history: {e}")
        raise HttpError(500, f"An error occurred: {str(e)}")


@router.get("/prices/{player_id}")
async def get_player_price_series(request, player_id: int, platform: str = "ps", days: int = 7):
    """Get latest price and history for a player."""
    try:
        # Get latest price
        current_price = await sync_to_async(
            lambda: PlayerPrice.objects.filter(player_id=player_id, platform=platform).first()
        )()

        # Get price history
        since = datetime.now() - timedelta(days=days)
        history = await sync_to_async(
            lambda: list(
                PlayerPriceHistory.objects.filter(player_id=player_id, platform=platform, fetched_at__gte=since)
                .order_by("fetched_at")
                .values("fetched_at", "price")
            )
        )()

        series = [{"t": h["fetched_at"].isoformat(), "v": float(h["price"])} for h in history]

        return {
            "success": True,
            "player_id": player_id,
            "platform": platform,
            "current_price": float(current_price.current_price) if current_price else None,
            "last_updated": current_price.last_updated.isoformat() if current_price else None,
            "series": series,
        }

    except Exception as e:
        logger.error(f"Error getting player price series: {e}")
        raise HttpError(500, f"An error occurred: {str(e)}")


@router.get("/price-stats")
async def get_price_stats(request):
    """Get price statistics and scraping health."""
    try:
        # Stale prices count (older than 1 hour)
        one_hour_ago = datetime.now() - timedelta(hours=1)
        stale_count = await sync_to_async(lambda: PlayerPrice.objects.filter(last_updated__lt=one_hour_ago).count())()

        # Total prices tracked
        total_prices = await sync_to_async(lambda: PlayerPrice.objects.count())()

        return {
            "success": True,
            "total_prices_tracked": total_prices,
            "stale_prices": stale_count,
        }

    except Exception as e:
        logger.error(f"Error getting price stats: {e}")
        raise HttpError(500, f"An error occurred: {str(e)}")
