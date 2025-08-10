"""Market schemas for Django Ninja."""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class SearchCriteria(BaseModel):
    type: str = "player"
    min_price: Optional[int] = None
    max_price: Optional[int] = None
    min_buy_now: Optional[int] = None
    max_buy_now: Optional[int] = None
    league: Optional[int] = None
    club: Optional[int] = None
    position: Optional[str] = None
    nationality: Optional[int] = None
    rare: Optional[bool] = None
    player_id: Optional[int] = None
    page: int = 0


class AuctionInfo(BaseModel):
    trade_id: int
    buy_now_price: int
    current_bid: int
    start_price: int
    expires: int
    trade_state: str
    bid_state: str
    seller_id: int
    seller_name: str
    watched: bool


class ItemData(BaseModel):
    id: int
    timestamp: int
    formation: str
    untradeable: bool
    asset_id: int
    rating: int
    item_type: str
    resource_id: int
    owners: int
    discard_value: int
    item_state: str
    card_subtype_id: int
    rare_flag: int


class SearchResult(BaseModel):
    total_pages: int
    total_results: int
    page: int
    page_size: int
    items: List[Dict[str, Any]]


class BidRequest(BaseModel):
    trade_id: int
    bid_amount: int


class BidResponse(BaseModel):
    success: bool
    message: str
    trade_id: int
    bid_amount: int
    credits: int


class WatchlistItem(BaseModel):
    trade_id: int
    item_data: ItemData
    auction_info: Optional[AuctionInfo] = None
    watched: bool


class TradePileItem(BaseModel):
    id: int
    pile: str
    trade_id: Optional[int] = None
    item_data: ItemData
    auction_info: Optional[AuctionInfo] = None
    trade_state: str


class TradeStatusRequest(BaseModel):
    trade_ids: List[int]


class TradeStatus(BaseModel):
    trade_id: int
    status: str
    expires: int
    current_bid: int
    bid_count: int


class TradeStatusResponse(BaseModel):
    credits: int
    bid_tokens: int
    currencies: List[Dict[str, Any]]
    duplicate_item_id_list: List[Any]
    auction_info: List[AuctionInfo]
    trades: Optional[List[TradeStatus]] = None


class RelistRequest(BaseModel):
    trade_ids: List[int]
    start_price: Optional[int] = None
    buy_now_price: Optional[int] = None
    duration: int = 3600


class RelistResponse(BaseModel):
    success: bool
    message: str
    relisted_count: int
