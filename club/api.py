"""Club API endpoints using Django Ninja."""

import logging
from typing import List

from ninja import Router
from ninja.errors import HttpError

from auth_api.services import FutClient
from core.exceptions import APIError, RateLimitError

from .schemas import (
    ClubItem,
    CreditsResponse,
    ItemOperationResponse,
    PlayerItem,
    PlayerListResponse,
    QuickSellResponse,
    Squad,
    SquadListResponse,
)

logger = logging.getLogger(__name__)
router = Router()


@router.get("/credits", response=CreditsResponse)
async def get_credits(request):
    """Get user's credit balance."""
    try:
        async with FutClient() as client:
            credits = await client.get_credits()
            
            return CreditsResponse(
                total=credits.total,
                untradeable=credits.untradeable,
            )
    
    except RateLimitError:
        raise HttpError(429, "Rate limit exceeded")
    except APIError as e:
        raise HttpError(503, f"EA servers error: {str(e)}")
    except Exception as e:
        logger.error(f"Credits error: {e}")
        raise HttpError(500, "Failed to get credits")


@router.get("/players", response=PlayerListResponse)
async def get_club_players(request):
    """Get all players in club."""
    try:
        async with FutClient() as client:
            players = await client.get_club_players()
            
            player_items = [
                PlayerItem(
                    id=player.id,
                    resource_id=player.resource_id,
                    asset_id=player.asset_id,
                    rating=player.rating,
                    rare_flag=player.rare_flag,
                    preferred_position=player.preferred_position,
                    name=player.name,
                    untradeable=player.untradeable,
                )
                for player in players
            ]
            
            return PlayerListResponse(
                players=player_items,
                total=len(player_items),
            )
    
    except RateLimitError:
        raise HttpError(429, "Rate limit exceeded")
    except APIError as e:
        raise HttpError(503, f"EA servers error: {str(e)}")
    except Exception as e:
        logger.error(f"Players error: {e}")
        raise HttpError(500, "Failed to get players")


@router.get("/squads", response=SquadListResponse)
async def get_squads(request):
    """Get all squads."""
    try:
        async with FutClient() as client:
            squads_data = await client.get_squads()
            
            squads = [
                Squad(
                    id=squad.id,
                    name=squad.name,
                    formation=squad.formation,
                    rating=squad.rating,
                    chemistry=squad.chemistry,
                    players=squad.players,
                )
                for squad in squads_data.squads
            ]
            
            return SquadListResponse(
                squads=squads,
                active_squad_id=squads_data.active_squad_id,
            )
    
    except RateLimitError:
        raise HttpError(429, "Rate limit exceeded")
    except APIError as e:
        raise HttpError(503, f"EA servers error: {str(e)}")
    except Exception as e:
        logger.error(f"Squads error: {e}")
        raise HttpError(500, "Failed to get squads")


@router.get("/items", response=List[ClubItem])
async def get_club_items(request):
    """Get all items in club."""
    try:
        async with FutClient() as client:
            items = await client.get_club_items()
            
            return [
                ClubItem(
                    id=item.id,
                    resource_id=item.resource_id,
                    item_type=item.item_type,
                    untradeable=item.untradeable,
                    discard_value=item.discard_value,
                    item_state=item.item_state,
                    pile=item.pile,
                )
                for item in items
            ]
    
    except RateLimitError:
        raise HttpError(429, "Rate limit exceeded")
    except APIError as e:
        raise HttpError(503, f"EA servers error: {str(e)}")
    except Exception as e:
        logger.error(f"Items error: {e}")
        raise HttpError(500, "Failed to get items")


@router.delete("/items/{item_id}/quick-sell", response=QuickSellResponse)
async def quick_sell_item(request, item_id: int):
    """Quick sell an item."""
    try:
        async with FutClient() as client:
            result = await client.quick_sell(item_id)
            credits = await client.get_credits()
            
            return QuickSellResponse(
                success=result.success,
                credits_earned=result.credits_earned,
                total_credits=credits.total,
                message="Item sold successfully" if result.success else "Quick sell failed",
            )
    
    except RateLimitError:
        raise HttpError(429, "Rate limit exceeded")
    except APIError as e:
        raise HttpError(503, f"EA servers error: {str(e)}")
    except Exception as e:
        logger.error(f"Quick sell error: {e}")
        raise HttpError(500, "Quick sell failed")


@router.post("/items/{item_id}/send-to-club", response=ItemOperationResponse)
async def send_to_club(request, item_id: int):
    """Send item to club."""
    try:
        async with FutClient() as client:
            success = await client.send_to_club(item_id)
            
            return ItemOperationResponse(
                success=success,
                message="Item sent to club" if success else "Failed to send to club",
                item_id=item_id,
            )
    
    except RateLimitError:
        raise HttpError(429, "Rate limit exceeded")
    except APIError as e:
        raise HttpError(503, f"EA servers error: {str(e)}")
    except Exception as e:
        logger.error(f"Send to club error: {e}")
        raise HttpError(500, "Failed to send to club")


@router.post("/items/{item_id}/send-to-tradepile", response=ItemOperationResponse)
async def send_to_tradepile(request, item_id: int):
    """Send item to trade pile."""
    try:
        async with FutClient() as client:
            success = await client.send_to_tradepile(item_id)
            
            return ItemOperationResponse(
                success=success,
                message="Item sent to trade pile" if success else "Failed to send to trade pile",
                item_id=item_id,
            )
    
    except RateLimitError:
        raise HttpError(429, "Rate limit exceeded")
    except APIError as e:
        raise HttpError(503, f"EA servers error: {str(e)}")
    except Exception as e:
        logger.error(f"Send to tradepile error: {e}")
        raise HttpError(500, "Failed to send to trade pile")
