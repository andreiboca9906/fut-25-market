"""Auction and trading models."""

from dataclasses import dataclass
from typing import List, Optional

from core.constants import AuctionDuration


@dataclass
class AuctionInfo:
    """Information about an auction item."""

    trade_id: int
    resource_id: int
    item_data: dict
    current_bid: int
    buy_now_price: int
    starting_bid: int
    bid_count: int
    time_remaining: int
    expires: int
    seller_id: Optional[int] = None
    seller_name: Optional[str] = None


@dataclass
class AuctionDetails:
    """Details for creating an auction."""

    item_id: int
    duration: AuctionDuration
    start_price: int
    buy_now_price: Optional[int] = None


@dataclass
class BidResult:
    """Result of placing a bid."""

    success: bool
    current_bid: int
    auction_info: Optional[AuctionInfo] = None
    error_message: Optional[str] = None


@dataclass
class SearchResponse:
    """Response from search operations."""

    auctions: List[AuctionInfo]
    total_results: int
    page: int
    credits: Optional[int] = None
