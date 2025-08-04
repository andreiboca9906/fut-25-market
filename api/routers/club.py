"""Club management endpoints."""

from typing import Annotated, List

from fastapi import APIRouter, Depends, HTTPException, status

from fut_toolkit.exceptions import APIError, SessionExpiredError
from fut_toolkit.services.fut_client import FutClient

from ..dependencies import get_fut_client
from ..schemas import (
    ClubItemSchema,
    CreditsResponseSchema,
    ItemOperationResponseSchema,
    PlayerListResponseSchema,
    QuickSellResponseSchema,
    SquadListResponseSchema,
)

router = APIRouter(prefix="/club", tags=["Club Management"])


@router.get("/credits", response_model=CreditsResponseSchema)
async def get_credits(client: Annotated[FutClient, Depends(get_fut_client)]):
    """Get user's current credit balance."""
    try:
        async with client:
            credits = await client.get_credits()

            return CreditsResponseSchema(
                credits=credits.credits, unopened_packs=credits.unopened_packs, total_points=credits.total_points
            )

    except SessionExpiredError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))
    except APIError as e:
        raise HTTPException(status_code=e.status_code or status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/players", response_model=PlayerListResponseSchema)
async def get_player_list(client: Annotated[FutClient, Depends(get_fut_client)]):
    """Get all players and legends list."""
    try:
        async with client:
            result = await client.get_player_list()

            return PlayerListResponseSchema(
                players=[
                    {
                        "asset_id": player.asset_id,
                        "resource_id": player.resource_id,
                        "first_name": player.first_name,
                        "last_name": player.last_name,
                        "common_name": player.common_name,
                        "rating": player.rating,
                        "position": player.position,
                        "nation": player.nation,
                        "league": player.league,
                        "team": player.team,
                    }
                    for player in result.players
                ],
                total_results=result.total_results,
            )

    except SessionExpiredError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))
    except APIError as e:
        raise HTTPException(status_code=e.status_code or status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/squads", response_model=SquadListResponseSchema)
async def get_squad_list(client: Annotated[FutClient, Depends(get_fut_client)]):
    """Get user's squad list."""
    try:
        async with client:
            result = await client.get_squad_list()

            return SquadListResponseSchema(
                squads=[
                    {
                        "id": squad.id,
                        "squad_name": squad.squad_name,
                        "formation": squad.formation,
                        "players": [
                            {
                                "id": player.id,
                                "index": player.index,
                                "asset_id": player.asset_id,
                                "rating": player.rating,
                                "position": player.position,
                                "chemistry": player.chemistry,
                            }
                            for player in squad.players
                        ],
                        "chemistry": squad.chemistry,
                    }
                    for squad in result.squads
                ]
            )

    except SessionExpiredError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))
    except APIError as e:
        raise HTTPException(status_code=e.status_code or status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/items", response_model=List[ClubItemSchema])
async def get_club_items(client: Annotated[FutClient, Depends(get_fut_client)]):
    """Get club items."""
    try:
        async with client:
            items = await client.get_club_items()

            return [
                ClubItemSchema(
                    id=item.id,
                    resource_id=item.resource_id,
                    item_type=item.item_type,
                    discardValue=item.discardValue,
                    tradeState=item.tradeState,
                    cardSubTypeId=item.cardSubTypeId,
                    loans=item.loans,
                    pile=item.pile,
                )
                for item in items
            ]

    except SessionExpiredError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))
    except APIError as e:
        raise HTTPException(status_code=e.status_code or status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.delete("/items/{item_id}/quick-sell", response_model=QuickSellResponseSchema)
async def quick_sell_item(item_id: int, client: Annotated[FutClient, Depends(get_fut_client)]):
    """Quick sell an item."""
    try:
        async with client:
            result = await client.quick_sell_item(item_id)

            return QuickSellResponseSchema(
                success=result.success, coins_earned=result.coins_earned, item_id=result.item_id
            )

    except SessionExpiredError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))
    except APIError as e:
        raise HTTPException(status_code=e.status_code or status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post("/items/{item_id}/send-to-club", response_model=ItemOperationResponseSchema)
async def send_to_club(item_id: int, client: Annotated[FutClient, Depends(get_fut_client)]):
    """Send item to club."""
    try:
        async with client:
            result = await client.send_to_club(item_id)

            return ItemOperationResponseSchema(
                success=result.success, item_id=result.item_id, duplicate=result.duplicate
            )

    except SessionExpiredError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))
    except APIError as e:
        raise HTTPException(status_code=e.status_code or status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post("/items/{item_id}/send-to-tradepile", response_model=ItemOperationResponseSchema)
async def send_to_trade_pile(item_id: int, client: Annotated[FutClient, Depends(get_fut_client)]):
    """Send item to trade pile."""
    try:
        async with client:
            result = await client.send_to_trade_pile(item_id)

            return ItemOperationResponseSchema(success=result.success, item_id=result.item_id)

    except SessionExpiredError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))
    except APIError as e:
        raise HTTPException(status_code=e.status_code or status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
