"""Player-related models."""
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class PlayerDefinition:
    """Basic player definition."""
    
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
    

@dataclass
class PlayerItem:
    """Player item with stats and attributes."""
    
    id: int
    asset_id: int
    resource_id: int
    item_type: str
    rating: int
    first_name: str
    last_name: str
    common_name: Optional[str] = None
    position: Optional[str] = None
    nation: Optional[int] = None
    league: Optional[int] = None
    team: Optional[int] = None
    contract: Optional[int] = None
    fitness: Optional[int] = None
    training: Optional[int] = None
    suspension: Optional[int] = None
    injury: Optional[int] = None
    attributes: Optional[List[dict]] = None
    

@dataclass
class PlayerListResponse:
    """Response containing list of players."""
    
    players: List[PlayerDefinition]
    total_results: int
