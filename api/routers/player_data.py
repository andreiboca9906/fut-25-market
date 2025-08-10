"""Player data management endpoints."""

from typing import Annotated, Dict, Optional

from fastapi import APIRouter, HTTPException, Query, status

from fut_toolkit.services import PlayerDataService

router = APIRouter(prefix="/player-data", tags=["Player Data Management"])


def get_player_service(sid: Optional[str] = None) -> PlayerDataService:
    """Get player data service instance."""
    return PlayerDataService(sid=sid)


@router.post("/fetch-all")
async def fetch_all_players(
    sid: Annotated[str, Query(description="FUT session ID")],
    checkpoint: Optional[Dict] = None
):
    """Fetch all players from FUT API and save to database."""
    try:
        service = get_player_service(sid)
        result = service.fetch_all_players(checkpoint)
        return {
            "success": True,
            "data": result
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.post("/fetch-batch")
async def fetch_players_batch(
    sid: Annotated[str, Query(description="FUT session ID")],
    offset: int = 0,
    count: int = 200
):
    """Fetch a batch of players from FUT API."""
    try:
        service = get_player_service(sid)
        players = service.fetch_players_batch(offset, count)
        return {
            "success": True,
            "players": players,
            "count": len(players) if players else 0
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.post("/update-names")
async def update_player_names():
    """Update player names from EA API."""
    try:
        service = get_player_service()
        result = service.update_player_names()
        return {
            "success": True,
            "data": result
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.get("/sample")
async def get_sample_players(limit: Annotated[int, Query(le=20)] = 5):
    """Get a sample of players from the database."""
    try:
        service = get_player_service()
        players = service.get_sample_players(limit)
        return {
            "success": True,
            "players": players,
            "count": len(players)
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.get("/summary")
async def get_players_summary():
    """Get summary statistics of players in the database."""
    try:
        service = get_player_service()
        summary = service.get_players_summary()
        
        if summary.get("error"):
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=summary["error"]
            )
        
        return {
            "success": True,
            "data": summary
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )
