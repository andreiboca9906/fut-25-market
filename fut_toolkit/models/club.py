"""Club and inventory models."""

from dataclasses import dataclass
from typing import List, Optional


@dataclass
class ClubItem:
    """Item in the club inventory."""

    id: int
    resource_id: int
    item_type: str
    discardValue: int
    tradeState: Optional[str] = None
    cardSubTypeId: Optional[int] = None
    loans: Optional[int] = None
    pile: Optional[int] = None


@dataclass
class CreditsResponse:
    """User's credit information."""

    credits: int
    unopened_packs: int
    total_points: Optional[int] = None


@dataclass
class TradePileItem:
    """Item in the trade pile."""

    id: int
    resource_id: int
    item_data: dict
    trade_state: str
    trade_id: Optional[int] = None


@dataclass
class WatchlistItem:
    """Item in the watchlist."""

    trade_id: int
    resource_id: int
    item_data: dict
    current_bid: int
    buy_now_price: int
    time_remaining: int
    watched: bool = True


@dataclass
class SquadPlayer:
    """Player in a squad."""

    id: int
    index: int
    asset_id: int
    rating: int
    position: str
    chemistry: Optional[int] = None


@dataclass
class Squad:
    """Squad information."""

    id: int
    squad_name: str
    formation: str
    players: List[SquadPlayer]
    chemistry: Optional[int] = None


@dataclass
class SquadListResponse:
    """Response containing squads."""

    squads: List[Squad]


@dataclass
class TradeStatus:
    """Trade status information."""

    trade_id: int
    status: str
    expires: int
    current_bid: int
    bid_count: int


@dataclass
class TradeStatusResponse:
    """Response from trade status check."""

    trades: List[TradeStatus]


@dataclass
class QuickSellResult:
    """Result from quick sell operation."""

    success: bool
    coins_earned: int
    item_id: int


@dataclass
class SendToClubResult:
    """Result from sending item to club."""

    success: bool
    item_id: int
    duplicate: bool = False


@dataclass
class SendToTradePileResult:
    """Result from sending item to trade pile."""

    success: bool
    item_id: int


@dataclass
class RelistResult:
    """Result from relisting items."""

    success: bool
    relisted_count: int
    errors: List[str]
