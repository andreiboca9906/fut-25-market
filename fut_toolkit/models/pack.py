"""Pack and store models."""

from dataclasses import dataclass
from typing import List, Optional


@dataclass
class PackInfo:
    """Pack information."""

    pack_id: int
    resource_id: int
    name: str
    description: Optional[str] = None
    pack_price: int = 0
    coins_price: int = 0
    fifa_points_price: int = 0


@dataclass
class PackResponse:
    """Response from pack operations."""

    packs: List[PackInfo]
    credits: int


@dataclass
class PackItem:
    """Item from opened pack."""

    id: int
    resource_id: int
    item_type: str
    rating: Optional[int] = None
    rare: bool = False


@dataclass
class PackOpenResponse:
    """Response from opening a pack."""

    items: List[PackItem]
    credits: int
    duplicates: List[PackItem]
