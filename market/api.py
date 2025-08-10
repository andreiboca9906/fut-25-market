"""Market API endpoints using Django Ninja."""

import logging
from dataclasses import asdict
from typing import List

from ninja import Router
from ninja.errors import HttpError

from auth_api.services import FutClient
from core.exceptions import APIError, RateLimitError
from core.fut_models.search import PlayerSearchParameters

from .schemas import (
    BidRequest,
    BidResponse,
    ItemData,
    RelistRequest,
    RelistResponse,
    SearchCriteria,
    SearchResult,
    TradePileItem,
    TradeStatusRequest,
    TradeStatusResponse,
    WatchlistItem,
)

logger = logging.getLogger(__name__)
router = Router()


@router.post("/search", response=SearchResult)
async def search_market(request, criteria: SearchCriteria):
    """Search the transfer market."""
    try:
        fut_criteria = PlayerSearchParameters(
            page=criteria.page,
            type=criteria.type,
            min_price=criteria.min_price,
            max_price=criteria.max_price,
            min_buy=criteria.min_buy_now,
            max_buy=criteria.max_buy_now,
            league=criteria.league,
            team=criteria.club,
            position=criteria.position,
            nation=criteria.nationality,
            resource_id=criteria.player_id,
        )
        
        async with FutClient() as client:
            result = await client.search_players(fut_criteria)
            
            page_size = len(result.auctions)
            total_pages = (result.total_results + page_size - 1) // page_size if page_size else 0
            
            return SearchResult(
                total_pages=total_pages,
                total_results=result.total_results,
                page=result.page,
                page_size=page_size,
                items=[asdict(a) for a in result.auctions],
            )
    
    except RateLimitError:
        raise HttpError(429, "Rate limit exceeded")
    except APIError as e:
        raise HttpError(503, f"EA servers error: {str(e)}")
    except Exception as e:
        logger.error(f"Search error: {e}")
        raise HttpError(500, "Search failed")


@router.post("/bid", response=BidResponse)
async def place_bid(request, bid_data: BidRequest):
    """Place a bid on an item."""
    try:
        async with FutClient() as client:
            bid_result = await client.place_bid(bid_data.trade_id, bid_data.bid_amount)
            credits = await client.get_credits()
            
            return BidResponse(
                success=bid_result.success,
                message="Bid placed successfully" if bid_result.success else "Bid failed",
                trade_id=bid_data.trade_id,
                bid_amount=bid_data.bid_amount,
                credits=credits.credits,
            )
    
    except RateLimitError:
        raise HttpError(429, "Rate limit exceeded")
    except APIError as e:
        raise HttpError(503, f"EA servers error: {str(e)}")
    except Exception as e:
        logger.error(f"Bid error: {e}")
        raise HttpError(500, "Bid failed")


@router.post("/buy-now/{trade_id}", response=BidResponse)
async def buy_now(request, trade_id: int):
    """Buy an item immediately at buy-now price."""
    try:
        async with FutClient() as client:
            res = await client.buy_now(trade_id)
            credits = await client.get_credits()
            
            return BidResponse(
                success=res.success,
                message="Purchase successful" if res.success else "Purchase failed",
                trade_id=trade_id,
                bid_amount=res.current_bid,
                credits=credits.credits,
            )
    
    except RateLimitError:
        raise HttpError(429, "Rate limit exceeded")
    except APIError as e:
        raise HttpError(503, f"EA servers error: {str(e)}")
    except Exception as e:
        logger.error(f"Buy now error: {e}")
        raise HttpError(500, "Purchase failed")


@router.get("/watchlist", response=List[WatchlistItem])
async def get_watchlist(request):
    """Get current watchlist."""
    try:
        async with FutClient() as client:
            watchlist = await client.get_watchlist()
            
            return [
                WatchlistItem(
                    trade_id=item.trade_id,
                    item_data=ItemData(**item.item_data) if isinstance(item.item_data, dict) else ItemData(**asdict(item.item_data)),
                    auction_info=None,
                    watched=True,
                )
                for item in watchlist
            ]
    
    except RateLimitError:
        raise HttpError(429, "Rate limit exceeded")
    except APIError as e:
        raise HttpError(503, f"EA servers error: {str(e)}")
    except Exception as e:
        logger.error(f"Watchlist error: {e}")
        raise HttpError(500, "Failed to get watchlist")


@router.get("/tradepile", response=List[TradePileItem])
async def get_tradepile(request):
    """Get current trade pile."""
    try:
        async with FutClient() as client:
            tradepile = await client.get_trade_pile()
            
            return [
                TradePileItem(
                    id=item.id,
                    pile="trade",
                    trade_id=item.trade_id,
                    item_data=ItemData(**item.item_data) if isinstance(item.item_data, dict) else ItemData(**asdict(item.item_data)),
                    auction_info=None,
                    trade_state=item.trade_state,
                )
                for item in tradepile
            ]
    
    except RateLimitError:
        raise HttpError(429, "Rate limit exceeded")
    except APIError as e:
        raise HttpError(503, f"EA servers error: {str(e)}")
    except Exception as e:
        logger.error(f"Tradepile error: {e}")
        raise HttpError(500, "Failed to get trade pile")


@router.post("/trade-status", response=TradeStatusResponse)
async def get_trade_status(request, data: TradeStatusRequest):
    """Get status of specific trades."""
    try:
        async with FutClient() as client:
            status = await client.get_trade_status()
            # Filter by requested trade_ids if provided
            if data.trade_ids:
                status.trades = [t for t in status.trades if t.trade_id in data.trade_ids]
            
            return TradeStatusResponse(
                credits=0,
                bid_tokens=0,
                currencies=[],
                duplicate_item_id_list=[],
                auction_info=[],
                trades=status.trades,
            )
    
    except RateLimitError:
        raise HttpError(429, "Rate limit exceeded")
    except APIError as e:
        raise HttpError(503, f"EA servers error: {str(e)}")
    except Exception as e:
        logger.error(f"Trade status error: {e}")
        raise HttpError(500, "Failed to get trade status")


@router.post("/watchlist/{trade_id}")
async def add_to_watchlist(request, trade_id: int):
    """Add item to watchlist."""
    try:
        async with FutClient() as client:
            success = await client.add_to_watchlist(trade_id)
            
            return {"success": success, "message": "Added to watchlist" if success else "Failed to add"}
    
    except RateLimitError:
        raise HttpError(429, "Rate limit exceeded")
    except APIError as e:
        raise HttpError(503, f"EA servers error: {str(e)}")
    except Exception as e:
        logger.error(f"Watchlist add error: {e}")
        raise HttpError(500, "Failed to add to watchlist")


@router.delete("/watchlist/{trade_id}")
async def remove_from_watchlist(request, trade_id: int):
    """Remove item from watchlist."""
    try:
        async with FutClient() as client:
            success = await client.remove_from_watchlist(trade_id)
            
            return {"success": success, "message": "Removed from watchlist" if success else "Failed to remove"}
    
    except RateLimitError:
        raise HttpError(429, "Rate limit exceeded")
    except APIError as e:
        raise HttpError(503, f"EA servers error: {str(e)}")
    except Exception as e:
        logger.error(f"Watchlist remove error: {e}")
        raise HttpError(500, "Failed to remove from watchlist")


@router.delete("/tradepile/{trade_id}")
async def remove_from_tradepile(request, trade_id: int):
    """Remove item from trade pile."""
    try:
        async with FutClient() as client:
            success = await client.remove_from_trade_pile(trade_id)
            
            return {"success": success, "message": "Removed from trade pile" if success else "Failed to remove"}
    
    except RateLimitError:
        raise HttpError(429, "Rate limit exceeded")
    except APIError as e:
        raise HttpError(503, f"EA servers error: {str(e)}")
    except Exception as e:
        logger.error(f"Tradepile remove error: {e}")
        raise HttpError(500, "Failed to remove from trade pile")


@router.post("/relist", response=RelistResponse)
async def relist_items(request, data: RelistRequest):
    """Relist items on transfer market."""
    try:
        async with FutClient() as client:
            result = await client.relist_items()
            
            return RelistResponse(
                success=result.success,
                message=f"Relisted {result.relisted_count} items",
                relisted_count=result.relisted_count,
            )
    
    except RateLimitError:
        raise HttpError(429, "Rate limit exceeded")
    except APIError as e:
        raise HttpError(503, f"EA servers error: {str(e)}")
    except Exception as e:
        logger.error(f"Relist error: {e}")
        raise HttpError(500, "Failed to relist items")
