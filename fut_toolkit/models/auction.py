"""Auction and trading models."""
from dataclasses import dataclass
from typing import List, Optional

from ..constants import AuctionDuration


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
class PlayerSearchParameters:
    """Parameters for searching players."""
    
    page: int = 1
    level: Optional[str] = None
    chemistry_style: Optional[int] = None
    league: Optional[int] = None
    nation: Optional[int] = None
    position: Optional[str] = None
    team: Optional[int] = None
    resource_id: Optional[int] = None
    asset_id: Optional[int] = None
    min_price: Optional[int] = None
    max_price: Optional[int] = None
    min_buy: Optional[int] = None
    max_buy: Optional[int] = None


@dataclass
class SearchResponse:
    """Response from search operations."""
    
    auctions: List[AuctionInfo]
    total_results: int
    page: int
    credits: Optional[int] = None
