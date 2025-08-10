"""Search parameter models."""

from dataclasses import dataclass
from typing import Optional

from core.constants import (
    ChemistryStyle,
    ClubInfoType,
    DevelopmentType,
    Level,
    Position,
    StaffType,
    TrainingType,
)


@dataclass
class SearchParameterBase:
    """Base search parameters."""

    page: int = 1
    type: Optional[str] = None
    start: int = 0
    num: int = 50


@dataclass
class PlayerSearchParameters(SearchParameterBase):
    """Parameters for searching players."""

    level: Optional[Level] = None
    chemistry_style: Optional[ChemistryStyle] = None
    league: Optional[int] = None
    nation: Optional[int] = None
    position: Optional[Position] = None
    team: Optional[int] = None
    resource_id: Optional[int] = None
    asset_id: Optional[int] = None
    min_price: Optional[int] = None
    max_price: Optional[int] = None
    min_buy: Optional[int] = None
    max_buy: Optional[int] = None
    def_id: Optional[int] = None
    masked_def_id: Optional[int] = None


@dataclass
class DevelopmentSearchParameters(SearchParameterBase):
    """Parameters for searching development items."""

    development_type: Optional[DevelopmentType] = None
    level: Optional[Level] = None


@dataclass
class TrainingSearchParameters(SearchParameterBase):
    """Parameters for searching training items."""

    training_type: Optional[TrainingType] = None
    level: Optional[Level] = None


@dataclass
class StaffSearchParameters(SearchParameterBase):
    """Parameters for searching staff."""

    staff_type: Optional[StaffType] = None
    level: Optional[Level] = None
    league: Optional[int] = None
    nation: Optional[int] = None


@dataclass
class StadiumSearchParameters(SearchParameterBase):
    """Parameters for searching stadiums."""

    level: Optional[Level] = None


@dataclass
class ClubInfoSearchParameters(SearchParameterBase):
    """Parameters for searching club info items."""

    club_info_type: Optional[ClubInfoType] = None
    level: Optional[Level] = None
    league: Optional[int] = None
    nation: Optional[int] = None
    team: Optional[int] = None


@dataclass
class BallSearchParameters(SearchParameterBase):
    """Parameters for searching balls."""

    level: Optional[Level] = None
