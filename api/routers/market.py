"""Transfer market endpoints."""

from typing import Annotated, List

from fastapi import APIRouter, Depends, HTTPException, status

from fut_toolkit.exceptions import APIError, RateLimitError, SessionExpiredError
from fut_toolkit.models.auction import PlayerSearchParameters
from fut_toolkit.services.fut_client import FutClient

from ..dependencies import get_fut_client
from ..schemas import (
    BidRequest,
    BidResponseSchema,
    PlayerSearchRequest,
    RelistResponseSchema,
    SearchResponseSchema,
    TradePileItemSchema,
    TradeStatusResponseSchema,
    WatchlistItemSchema,
)

router = APIRouter(prefix="/market", tags=["Transfer Market"])


@router.post("/search", response_model=SearchResponseSchema)
async def search_players(search_params: PlayerSearchRequest, client: Annotated[FutClient, Depends(get_fut_client)]):
    """Search for players on the transfer market."""
    try:
        params = PlayerSearchParameters(
            page=search_params.page,
            level=search_params.level,
            chemistry_style=search_params.chemistry_style,
            league=search_params.league,
            nation=search_params.nation,
            position=search_params.position,
            team=search_params.team,
            resource_id=search_params.resource_id,
            asset_id=search_params.asset_id,
            min_price=search_params.min_price,
            max_price=search_params.max_price,
            min_buy=search_params.min_buy,
            max_buy=search_params.max_buy,
        )

        async with client:
            result = await client.search_players(params)

            return SearchResponseSchema(
                auctions=[
                    {
                        "trade_id": auction.trade_id,
                        "resource_id": auction.resource_id,
                        "item_data": auction.item_data,
                        "current_bid": auction.current_bid,
                        "buy_now_price": auction.buy_now_price,
                        "starting_bid": auction.starting_bid,
                        "bid_count": auction.bid_count,
                        "time_remaining": auction.time_remaining,
                        "expires": auction.expires,
                        "seller_id": auction.seller_id,
                        "seller_name": auction.seller_name,
                    }
                    for auction in result.auctions
                ],
                total_results=result.total_results,
                page=result.page,
                credits=result.credits,
            )

    except SessionExpiredError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))
    except RateLimitError as e:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=str(e))
    except APIError as e:
        raise HTTPException(status_code=e.status_code or status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post("/bid", response_model=BidResponseSchema)
async def place_bid(bid_data: BidRequest, client: Annotated[FutClient, Depends(get_fut_client)]):
    """Place a bid on an auction."""
    try:
        async with client:
            result = await client.place_bid(bid_data.trade_id, bid_data.bid_amount)

            return BidResponseSchema(
                success=result.success, current_bid=result.current_bid, error_message=result.error_message
            )

    except SessionExpiredError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))
    except APIError as e:
        raise HTTPException(status_code=e.status_code or status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post("/buy-now/{trade_id}", response_model=BidResponseSchema)
async def buy_now(trade_id: int, client: Annotated[FutClient, Depends(get_fut_client)]):
    """Buy an item immediately at buy-now price."""
    try:
        async with client:
            result = await client.buy_now(trade_id)

            return BidResponseSchema(
                success=result.success, current_bid=result.current_bid, error_message=result.error_message
            )

    except SessionExpiredError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))
    except APIError as e:
        raise HTTPException(status_code=e.status_code or status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/watchlist", response_model=List[WatchlistItemSchema])
async def get_watchlist(client: Annotated[FutClient, Depends(get_fut_client)]):
    """Get user's watchlist items."""
    try:
        async with client:
            items = await client.get_watchlist()

            return [
                WatchlistItemSchema(
                    trade_id=item.trade_id,
                    resource_id=item.resource_id,
                    item_data=item.item_data,
                    current_bid=item.current_bid,
                    buy_now_price=item.buy_now_price,
                    time_remaining=item.time_remaining,
                    watched=item.watched,
                )
                for item in items
            ]

    except SessionExpiredError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))
    except APIError as e:
        raise HTTPException(status_code=e.status_code or status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/tradepile", response_model=List[TradePileItemSchema])
async def get_trade_pile(client: Annotated[FutClient, Depends(get_fut_client)]):
    """Get trade pile items."""
    try:
        async with client:
            items = await client.get_trade_pile()

            return [
                TradePileItemSchema(
                    id=item.id,
                    resource_id=item.resource_id,
                    item_data=item.item_data,
                    trade_state=item.trade_state,
                    trade_id=item.trade_id,
                )
                for item in items
            ]

    except SessionExpiredError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))
    except APIError as e:
        raise HTTPException(status_code=e.status_code or status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/trade-status", response_model=TradeStatusResponseSchema)
async def get_trade_status(client: Annotated[FutClient, Depends(get_fut_client)]):
    """Get trade status for active auctions."""
    try:
        async with client:
            response = await client.get_trade_status()

            return TradeStatusResponseSchema(
                trades=[
                    {
                        "trade_id": trade.trade_id,
                        "status": trade.status,
                        "expires": trade.expires,
                        "current_bid": trade.current_bid,
                        "bid_count": trade.bid_count,
                    }
                    for trade in response.trades
                ]
            )

    except SessionExpiredError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))
    except APIError as e:
        raise HTTPException(status_code=e.status_code or status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post("/watchlist/{trade_id}")
async def add_to_watchlist(trade_id: int, client: Annotated[FutClient, Depends(get_fut_client)]):
    """Add item to watchlist."""
    try:
        async with client:
            success = await client.add_to_watchlist(trade_id)
            return {"success": success}

    except SessionExpiredError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))


@router.delete("/watchlist/{trade_id}")
async def remove_from_watchlist(trade_id: int, client: Annotated[FutClient, Depends(get_fut_client)]):
    """Remove item from watchlist."""
    try:
        async with client:
            success = await client.remove_from_watchlist(trade_id)
            return {"success": success}

    except SessionExpiredError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))


@router.delete("/tradepile/{trade_id}")
async def remove_from_trade_pile(trade_id: int, client: Annotated[FutClient, Depends(get_fut_client)]):
    """Remove item from trade pile."""
    try:
        async with client:
            success = await client.remove_from_trade_pile(trade_id)
            return {"success": success}

    except SessionExpiredError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))


@router.post("/relist", response_model=RelistResponseSchema)
async def relist_items(client: Annotated[FutClient, Depends(get_fut_client)]):
    """Relist all items in trade pile."""
    try:
        async with client:
            result = await client.relist_items()

            return RelistResponseSchema(
                success=result.success, relisted_count=result.relisted_count, errors=result.errors
            )

    except SessionExpiredError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))
    except APIError as e:
        raise HTTPException(status_code=e.status_code or status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
