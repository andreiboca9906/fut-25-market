"""Pydantic schemas for API requests/responses."""

from typing import List, Optional

from pydantic import BaseModel, EmailStr, Field

from fut_toolkit.constants import AppVersion, Platform


class LoginRequest(BaseModel):
    """Request schema for user login."""

    email: EmailStr
    password: str
    platform: Platform
    app_version: AppVersion = AppVersion.WEB_APP
    secret_answer: Optional[str] = None
    x_ut_sid: Optional[str] = None


class LoginResponseSchema(BaseModel):
    """Response schema for successful login."""

    session_id: str
    nucleus_id: str
    persona_id: str
    dob: Optional[str] = None
    email: Optional[str] = None
    country: Optional[str] = None


class PlayerSearchRequest(BaseModel):
    """Request schema for player search."""

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


class AuctionInfoSchema(BaseModel):
    """Schema for auction information."""

    trade_id: int = Field(alias="tradeId")
    resource_id: int = Field(default=0)
    item_data: dict = Field(alias="itemData")
    current_bid: int = Field(alias="currentBid")
    buy_now_price: int = Field(alias="buyNowPrice")
    starting_bid: int = Field(alias="startingBid")
    bid_count: int = Field(alias="offers", default=0)
    time_remaining: int = Field(default=0)
    expires: int
    seller_id: Optional[int] = Field(alias="sellerId", default=None)
    seller_name: Optional[str] = Field(alias="sellerName", default=None)
    trade_state: str = Field(alias="tradeState")
    watched: bool = Field(default=False)
    bid_state: str = Field(alias="bidState")
    confidence_value: int = Field(alias="confidenceValue")
    seller_established: Optional[int] = Field(alias="sellerEstablished", default=None)
    trade_owner: bool = Field(alias="tradeOwner")
    trade_id_str: str = Field(alias="tradeIdStr")


class SearchResponseSchema(BaseModel):
    """Schema for search results."""

    auctions: List[AuctionInfoSchema] = Field(alias="auctionInfo")
    bid_tokens: dict = Field(alias="bidTokens", default_factory=dict)


class BidRequest(BaseModel):
    """Request schema for placing bids."""

    trade_id: int
    bid_amount: int


class BidResponseSchema(BaseModel):
    """Response schema for bid results."""

    success: bool
    current_bid: int
    error_message: Optional[str] = None


class CreditsResponseSchema(BaseModel):
    """Schema for credits information."""

    credits: int
    unopened_packs: int
    total_points: Optional[int] = None


class WatchlistItemSchema(BaseModel):
    """Schema for watchlist items."""

    trade_id: int
    resource_id: int
    item_data: dict
    current_bid: int
    buy_now_price: int
    time_remaining: int
    watched: bool = True


class TradePileItemSchema(BaseModel):
    """Schema for trade pile items."""

    id: int
    resource_id: int
    item_data: dict
    trade_state: str
    trade_id: Optional[int] = None


class TradeStatusSchema(BaseModel):
    """Schema for individual trade status."""

    trade_id: int
    status: str
    expires: int
    current_bid: int
    bid_count: int


class TradeStatusResponseSchema(BaseModel):
    """Schema for trade status response."""

    trades: List[TradeStatusSchema]


class QuickSellResponseSchema(BaseModel):
    """Schema for quick sell response."""

    success: bool
    coins_earned: int
    item_id: int


class ItemOperationResponseSchema(BaseModel):
    """Schema for item operation responses."""

    success: bool
    item_id: int
    duplicate: Optional[bool] = None


class RelistResponseSchema(BaseModel):
    """Schema for relist response."""

    success: bool
    relisted_count: int
    errors: List[str]


class PlayerListItemSchema(BaseModel):
    """Schema for player list item."""

    asset_id: int
    resource_id: int
    first_name: str
    last_name: str
    common_name: Optional[str] = None
    rating: Optional[int] = None
    position: Optional[str] = None
    nation: Optional[int] = None
    league: Optional[int] = None
    team: Optional[int] = None


class PlayerListResponseSchema(BaseModel):
    """Schema for player list response."""

    players: List[PlayerListItemSchema]
    total_results: int


class ClubItemSchema(BaseModel):
    """Schema for club items."""

    id: int
    resource_id: int
    item_type: str
    discardValue: int
    tradeState: Optional[str] = None
    cardSubTypeId: Optional[int] = None
    loans: Optional[int] = None
    pile: Optional[int] = None


class SquadPlayerSchema(BaseModel):
    """Schema for squad player."""

    id: int
    index: int
    asset_id: int
    rating: int
    position: str
    chemistry: Optional[int] = None


class SquadSchema(BaseModel):
    """Schema for squad."""

    id: int
    squad_name: str
    formation: str
    players: List[SquadPlayerSchema]
    chemistry: Optional[int] = None


class SquadListResponseSchema(BaseModel):
    """Schema for squad list response."""

    squads: List[SquadSchema]


class ErrorResponse(BaseModel):
    """Error response schema."""

    error: str
    detail: Optional[str] = None
    status_code: Optional[int] = None
