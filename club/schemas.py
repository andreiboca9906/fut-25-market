"""Club schemas for Django Ninja."""

from typing import Any, Dict, List

from pydantic import BaseModel


class CreditsResponse(BaseModel):
    credits: int
    unopened_packs: int
    total_points: int | None = None


class PlayerItem(BaseModel):
    id: int
    resource_id: int
    asset_id: int
    rating: int
    rare_flag: int
    preferred_position: str
    name: str
    untradeable: bool


class PlayerListResponse(BaseModel):
    players: List[PlayerItem]
    total: int


class Squad(BaseModel):
    id: int
    name: str
    formation: str
    rating: int
    chemistry: int
    players: List[Dict[str, Any]]


class SquadListResponse(BaseModel):
    squads: List[Squad]
    active_squad_id: int


class ClubItem(BaseModel):
    id: int
    resource_id: int
    item_type: str
    untradeable: bool
    discard_value: int
    item_state: str
    pile: int


class QuickSellResponse(BaseModel):
    success: bool
    coins_earned: int
    total_credits: int
    message: str


class ItemOperationResponse(BaseModel):
    success: bool
    message: str
    item_id: int
