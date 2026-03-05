"""Constants and enums for EA Sports FC Ultimate Team API."""

from datetime import timedelta
from enum import Enum


class Platform(Enum):
    """Gaming platforms supported by EA Sports FC Ultimate Team."""

    PS4 = "ps4"
    PS5 = "ps5"
    XBOX_ONE = "xboxone"
    XBOX_SERIES_X = "xboxseriesx"
    PC = "pc"


class AppVersion(Enum):
    """Supported app versions for EA Sports FC Ultimate Team."""

    WEB_APP = "26.1.0"
    COMPANION_APP = "26.1.0"


class AuctionDuration(Enum):
    """Auction duration options."""

    ONE_HOUR = 3600
    THREE_HOURS = 10800
    SIX_HOURS = 21600
    TWELVE_HOURS = 43200
    ONE_DAY = 86400
    THREE_DAYS = 259200


class Position(Enum):
    """Player positions."""

    GK = "GK"
    RWB = "RWB"
    RB = "RB"
    CB = "CB"
    LB = "LB"
    LWB = "LWB"
    CDM = "CDM"
    RM = "RM"
    CM = "CM"
    LM = "LM"
    CAM = "CAM"
    RF = "RF"
    CF = "CF"
    LF = "LF"
    RW = "RW"
    ST = "ST"
    LW = "LW"


class ChemistryStyle(Enum):
    """Chemistry styles for players."""

    BASIC = 250
    SNIPER = 251
    FINISHER = 252
    DEADEYE = 253
    MARKSMAN = 254
    HAWK = 255
    ARTIST = 256
    ARCHITECT = 257
    POWERHOUSE = 258
    MAESTRO = 259
    ENGINE = 260
    SENTINEL = 261
    GUARDIAN = 262
    GLADIATOR = 263
    BACKBONE = 264
    ANCHOR = 265
    HUNTER = 266
    CATALYST = 267
    SHADOW = 268
    WALL = 269


class ResourceId(Enum):
    """Resource identifiers."""

    PLAYERS = 5002
    CONSUMABLES = 5003
    CLUB_ITEMS = 5004
    STAFF = 5005
    MANAGERS = 5006
    STADIUMS = 5007
    KITS = 5008
    BADGES = 5009
    BALLS = 5010


class Level(Enum):
    """Card levels."""

    BRONZE = "bronze"
    SILVER = "silver"
    GOLD = "gold"


class ItemType(Enum):
    """Item types."""

    PLAYER = "player"
    DEVELOPMENT = "development"
    TRAINING = "training"
    CONSUMABLES = "consumables"
    STAFF = "staff"
    STADIUM = "stadium"


class DevelopmentType(Enum):
    """Development item types."""

    FITNESS = "fitness"
    INJURY_HEALING = "injury"
    CONTRACT = "contract"
    POSITION_CHANGE = "position"


class TrainingType(Enum):
    """Training item types."""

    CHEMISTRY_STYLE = "playerstyle"
    MANAGER_LEAGUE = "managerleague"


class StaffType(Enum):
    """Staff types."""

    MANAGER = "manager"
    HEAD_COACH = "headCoach"


class ClubInfoType(Enum):
    """Club info types."""

    KITS = "kit"
    BADGES = "badge"
    STADIUMS = "stadium"
    BALLS = "ball"


API_ENDPOINTS = {
    "base_url": "https://utas.mob.v4.prd.futc-ext.gcp.ea.com/ut/game/fc26",
    "login": "/user/auth",
    "session": "/user/sessionInfo",
    "transfermarket": "/transfermarket",
    "bid": "/trade/{auction_id}/bid",
    "watchlist": "/watchlist",
    "tradepile": "/tradepile",
    "club": "/club",
    "credits": "/user/credits",
    "packs": "/store/catalog",
    "relist": "/auctionhouse/relist",
    "purchased_items": "/purchased/items",
    "player_list": "/defid",
    "squad_list": "/squad/list",
    "squad_details": "/squad/{squad_id}",
    "consumables": "/club/consumables/{type}",
    "send_to_club": "/item",
    "send_to_tradepile": "/item",
    "quick_sell": "/item/{item_id}",
    "remove_from_tradepile": "/trade/{trade_id}",
    "remove_from_watchlist": "/watchlist/{trade_id}",
    "add_to_watchlist": "/watchlist",
    "list_auction": "/auctionhouse",
    "trade_status": "/trade/status",
    "club_items": "/club",
    "images": "/items/images",
    "pack_open": "/purchased/items",
}


def get_base_headers(user_agent: str = None, platform: str = "macOS") -> dict:
    """Get base headers with optional custom user agent."""
    if not user_agent:
        user_agent = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"

    return {
        "accept": "*/*",
        "accept-language": "en-GB,en;q=0.7",
        "cache-control": "no-cache",
        "content-type": "application/json",
        "sec-ch-ua": '"Not)A;Brand";v="8", "Chromium";v="138", "Brave";v="138"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": f'"{platform}"',
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-site",
        "sec-gpc": "1",
        "user-agent": user_agent,
        "referer": "https://www.ea.com/",
    }


PLATFORMS = ["macOS", "Windows", "Linux"]

CHROME_VERSIONS = ["138", "137", "136", "135"]

REFERRER = "https://www.ea.com/"

# Tier-based scan windows for price scraping
TIER_SCAN_WINDOWS = {
    "HOT": timedelta(minutes=5),
    "TRENDING": timedelta(minutes=10),
    "ACTIVE": timedelta(minutes=20),
    "NORMAL": timedelta(minutes=45),
    # "COLD": timedelta(hours=2),  # Change this back
    "COLD": timedelta(minutes=2),  # For testing purposes
}
