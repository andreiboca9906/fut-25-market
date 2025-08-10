"""Player-related models."""

from dataclasses import dataclass
from typing import List


@dataclass
class PlayerDefinition:
    """Basic player definition."""

    id: int
    timestamp: int
    formation: str
    untradeable: bool
    asset_id: int
    rating: int
    dream: bool
    item_type: str
    resource_id: int
    owners: int
    discard_value: int
    cardsubtypeid: int
    last_sale_price: int
    injury_type: str
    injury_games: int
    preferred_position: str
    stats_list: List = None
    lifetime_stats: List = None
    contract: int = 0
    teamid: int = 0
    rareflag: int = 0
    play_style: int = 0
    league_id: int = 0
    loyalty_bonus: int = 0
    pile: int = 0
    nation: int = 0
    resource_game_year: int = 0
    guid_asset_id: str = ""
    attribute_array: List[int] = None
    skillmoves: int = 0
    weakfootabilitytypecode: int = 0
    preferredfoot: int = 0
    possible_positions: List[str] = None
    gender: int = 0
    base_traits: List[int] = None
    icon_traits_priorities: dict = None
    plus_plus_roles: List[int] = None


@dataclass
class PlayerListResponse:
    """Response containing list of players."""

    players: List[PlayerDefinition]
    total_results: int
