"""Main FIFA Ultimate Team client."""

import random
from typing import List, Optional, Protocol

import httpx
from fake_useragent import UserAgent

from ..constants import API_ENDPOINTS, PLATFORMS, get_base_headers
from ..exceptions import (
    APIError,
    AuthenticationError,
    RateLimitError,
    SessionExpiredError,
    TwoFactorCodeRequiredError,
)
from ..models.auction import (
    AuctionInfo,
    BidResult,
    SearchResponse,
)
from ..models.auth import LoginDetails, LoginResponse, SessionInfo
from ..models.club import (
    ClubItem,
    CreditsResponse,
    QuickSellResult,
    RelistResult,
    SendToClubResult,
    SendToTradePileResult,
    Squad,
    SquadListResponse,
    SquadPlayer,
    TradePileItem,
    TradeStatus,
    TradeStatusResponse,
    WatchlistItem,
)
from ..models.player import PlayerDefinition, PlayerListResponse
from ..models.search import (
    PlayerSearchParameters,
)


class TwoFactorCodeProvider(Protocol):
    """Protocol for providing two-factor authentication codes."""

    async def get_code(self) -> str:
        """Get the two-factor authentication code."""
        ...


class FutClient:
    """FIFA Ultimate Team API client."""

    def __init__(
        self, cookie_jar: Optional[httpx.Cookies] = None, x_ut_sid: Optional[str] = None, rotate_ua: bool = True
    ):
        # Generate random user agent and platform
        if rotate_ua:
            ua = UserAgent()
            user_agent = ua.chrome
            platform = random.choice(PLATFORMS)
        else:
            user_agent = None
            platform = "macOS"

        # Get base headers
        headers = get_base_headers(user_agent, platform)

        # Add session ID if provided
        if x_ut_sid:
            headers["x-ut-sid"] = x_ut_sid

        self.session = httpx.AsyncClient(cookies=cookie_jar, headers=headers, timeout=30.0)
        self.session_info: Optional[SessionInfo] = None
        self.base_url = API_ENDPOINTS["base_url"]
        self.x_ut_sid = x_ut_sid

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.session.aclose()

    def update_session_id(self, x_ut_sid: str):
        """Update the X-UT-SID header for all requests."""
        self.x_ut_sid = x_ut_sid
        self.session.headers["x-ut-sid"] = x_ut_sid

    def _handle_auth_error(self, status_code: int) -> None:
        """Handle authentication errors based on status code."""
        if status_code == 401:
            if self.x_ut_sid:
                raise SessionExpiredError("Session expired or invalid X-UT-SID")
            else:
                raise SessionExpiredError("Authentication required - missing X-UT-SID")
        elif status_code == 403:
            raise AuthenticationError("Access forbidden - check session permissions")

    def _check_response_auth(self, response: httpx.Response) -> None:
        """Check response for authentication errors."""
        if response.status_code in (401, 403):
            self._handle_auth_error(response.status_code)

    async def login(
        self, login_details: LoginDetails, two_factor_provider: Optional[TwoFactorCodeProvider] = None
    ) -> LoginResponse:
        """Authenticate with EA servers."""
        auth_data = {
            "email": login_details.email,
            "password": login_details.password,
            "platform": login_details.platform.value,
            "appVersion": login_details.app_version.value,
        }

        if login_details.secret_answer:
            auth_data["secretAnswer"] = login_details.secret_answer

        try:
            response = await self.session.post(f"{self.base_url}{API_ENDPOINTS['login']}", json=auth_data)

            if response.status_code in (401, 403):
                self._handle_auth_error(response.status_code)
            elif response.status_code == 458:
                if not two_factor_provider:
                    raise TwoFactorCodeRequiredError("Two-factor code required")

                code = await two_factor_provider.get_code()
                auth_data["twoFactorCode"] = code

                response = await self.session.post(f"{self.base_url}{API_ENDPOINTS['login']}", json=auth_data)

            response.raise_for_status()
            data = response.json()

            login_response = LoginResponse(
                session_id=data["session"]["id"],
                nucleus_id=data["nucleusId"],
                persona_id=data["personaId"],
                dob=data.get("dob"),
                email=data.get("email"),
                country=data.get("country"),
            )

            self.session_info = SessionInfo(
                session_id=login_response.session_id,
                persona_id=login_response.persona_id,
                nucleus_id=login_response.nucleus_id,
            )

            return login_response

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                raise RateLimitError("Rate limit exceeded")
            raise APIError(f"Login failed: {e.response.text}", e.response.status_code)

    async def search_players(self, params: PlayerSearchParameters) -> SearchResponse:
        """Search for players on the transfer market."""
        if not self.x_ut_sid:
            raise SessionExpiredError("Not authenticated")

        search_params = {"type": "player", "start": (params.page - 1) * 50}

        if params.level:
            search_params["lev"] = params.level
        if params.chemistry_style:
            search_params["playStyle"] = params.chemistry_style
        if params.league:
            search_params["leag"] = params.league
        if params.nation:
            search_params["nat"] = params.nation
        if params.position:
            search_params["pos"] = params.position
        if params.team:
            search_params["team"] = params.team
        if params.resource_id:
            search_params["definitionId"] = params.resource_id
        if params.asset_id:
            search_params["maskedDefId"] = params.asset_id
        if params.min_price:
            search_params["minPrice"] = params.min_price
        if params.max_price:
            search_params["maxPrice"] = params.max_price
        if params.min_buy:
            search_params["minBuy"] = params.min_buy
        if params.max_buy:
            search_params["maxBuy"] = params.max_buy

        try:
            response = await self.session.get(f"{self.base_url}{API_ENDPOINTS['transfermarket']}", params=search_params)

            self._check_response_auth(response)
            response.raise_for_status()
            data = response.json()

            auctions = []
            for item in data.get("auctionInfo", []):
                auction = AuctionInfo(
                    trade_id=item["tradeId"],
                    resource_id=item["itemData"]["resourceId"],
                    item_data=item.get("itemData", {}),
                    current_bid=item["currentBid"],
                    buy_now_price=item["buyNowPrice"],
                    starting_bid=item["startingBid"],
                    bid_count=item.get("offers", 0),
                    time_remaining=item["expires"],
                    expires=item["expires"],
                    seller_id=item.get("sellerId"),
                    seller_name=item.get("sellerName"),
                )
                auctions.append(auction)

            return SearchResponse(
                auctions=auctions,
                total_results=data.get("total", len(auctions)),
                page=params.page,
                credits=data.get("credits"),
            )

        except httpx.HTTPStatusError as e:
            raise APIError(f"Search failed: {e.response.text}", e.response.status_code)

    async def place_bid(self, trade_id: int, bid_amount: int) -> BidResult:
        """Place a bid on an auction."""
        if not self.x_ut_sid:
            raise SessionExpiredError("Not authenticated")

        try:
            response = await self.session.put(
                f"{self.base_url}{API_ENDPOINTS['bid'].format(auction_id=trade_id)}", json={"bid": bid_amount}
            )

            if response.status_code == 401:
                raise SessionExpiredError("Session expired")
            elif response.status_code == 478:
                return BidResult(success=False, current_bid=0, error_message="Auction expired or invalid")
            elif response.status_code == 461:
                return BidResult(success=False, current_bid=0, error_message="Bid too low")

            response.raise_for_status()
            data = response.json()

            return BidResult(
                success=True,
                current_bid=data["auctionInfo"][0]["currentBid"],
                auction_info=None,  # Could populate if needed
            )

        except httpx.HTTPStatusError as e:
            raise APIError(f"Bid failed: {e.response.text}", e.response.status_code)

    async def buy_now(self, trade_id: int) -> BidResult:
        """Buy item immediately at buy-now price."""
        if not self.x_ut_sid:
            raise SessionExpiredError("Not authenticated")

        try:
            response = await self.session.put(
                f"{self.base_url}{API_ENDPOINTS['bid'].format(auction_id=trade_id)}",
                json={"bid": -1},  # -1 indicates buy now
            )

            self._check_response_auth(response)
            response.raise_for_status()
            data = response.json()

            return BidResult(success=True, current_bid=data["auctionInfo"][0]["buyNowPrice"], auction_info=None)

        except httpx.HTTPStatusError as e:
            raise APIError(f"Buy now failed: {e.response.text}", e.response.status_code)

    async def get_credits(self) -> CreditsResponse:
        """Get current credit balance."""
        if not self.x_ut_sid:
            raise SessionExpiredError("Not authenticated")

        try:
            response = await self.session.get(f"{self.base_url}{API_ENDPOINTS['credits']}")

            self._check_response_auth(response)
            response.raise_for_status()
            data = response.json()

            return CreditsResponse(
                credits=data["credits"],
                unopened_packs=data["unopenedPacks"]["count"],
                total_points=data.get("totalPoints"),
            )

        except httpx.HTTPStatusError as e:
            raise APIError(f"Get credits failed: {e.response.text}", e.response.status_code)

    async def get_watchlist(self) -> List[WatchlistItem]:
        """Get watchlist items."""
        if not self.x_ut_sid:
            raise SessionExpiredError("Not authenticated")

        try:
            response = await self.session.get(f"{self.base_url}{API_ENDPOINTS['watchlist']}")

            self._check_response_auth(response)
            response.raise_for_status()
            data = response.json()

            items = []
            for item in data.get("auctionInfo", []):
                watchlist_item = WatchlistItem(
                    trade_id=item["tradeId"],
                    resource_id=item["resourceId"],
                    item_data=item.get("itemData", {}),
                    current_bid=item["currentBid"],
                    buy_now_price=item["buyNowPrice"],
                    time_remaining=item["timeRemaining"],
                )
                items.append(watchlist_item)

            return items

        except httpx.HTTPStatusError as e:
            raise APIError(f"Get watchlist failed: {e.response.text}", e.response.status_code)

    async def get_player_list(self) -> PlayerListResponse:
        """Get all players and legends list."""
        if not self.x_ut_sid:
            raise SessionExpiredError("Not authenticated")

        try:
            response = await self.session.get(f"{self.base_url}{API_ENDPOINTS['player_list']}")

            self._check_response_auth(response)
            response.raise_for_status()
            data = response.json()

            players = []
            for item in data.get("players", []):
                player = PlayerDefinition(
                    asset_id=item["assetId"],
                    resource_id=item["resourceId"],
                    first_name=item["firstName"],
                    last_name=item["lastName"],
                    common_name=item.get("commonName"),
                    rating=item.get("rating"),
                    position=item.get("position"),
                    nation=item.get("nation"),
                    league=item.get("league"),
                    team=item.get("team"),
                )
                players.append(player)

            return PlayerListResponse(players=players, total_results=len(players))

        except httpx.HTTPStatusError as e:
            raise APIError(f"Get player list failed: {e.response.text}", e.response.status_code)

    async def get_trade_pile(self) -> List[TradePileItem]:
        """Get trade pile items."""
        if not self.x_ut_sid:
            raise SessionExpiredError("Not authenticated")

        try:
            response = await self.session.get(f"{self.base_url}{API_ENDPOINTS['tradepile']}")

            self._check_response_auth(response)
            response.raise_for_status()
            data = response.json()

            items = []
            for item in data.get("auctionInfo", []):
                trade_item = TradePileItem(
                    id=item["id"],
                    resource_id=item["resourceId"],
                    item_data=item.get("itemData", {}),
                    trade_state=item.get("tradeState", ""),
                    trade_id=item.get("tradeId"),
                )
                items.append(trade_item)

            return items

        except httpx.HTTPStatusError as e:
            raise APIError(f"Get trade pile failed: {e.response.text}", e.response.status_code)

    async def get_squad_list(self) -> SquadListResponse:
        """Get user's squad list."""
        if not self.x_ut_sid:
            raise SessionExpiredError("Not authenticated")

        try:
            response = await self.session.get(f"{self.base_url}{API_ENDPOINTS['squad_list']}")

            self._check_response_auth(response)
            response.raise_for_status()
            data = response.json()

            squads = []
            for squad_data in data.get("squads", []):
                players = []
                for player_data in squad_data.get("players", []):
                    player = SquadPlayer(
                        id=player_data["id"],
                        index=player_data["index"],
                        asset_id=player_data["assetId"],
                        rating=player_data["rating"],
                        position=player_data["position"],
                        chemistry=player_data.get("chemistry"),
                    )
                    players.append(player)

                squad = Squad(
                    id=squad_data["id"],
                    squad_name=squad_data["squadName"],
                    formation=squad_data["formation"],
                    players=players,
                    chemistry=squad_data.get("chemistry"),
                )
                squads.append(squad)

            return SquadListResponse(squads=squads)

        except httpx.HTTPStatusError as e:
            raise APIError(f"Get squad list failed: {e.response.text}", e.response.status_code)

    async def get_club_items(self) -> List[ClubItem]:
        """Get club items."""
        if not self.x_ut_sid:
            raise SessionExpiredError("Not authenticated")

        try:
            response = await self.session.get(f"{self.base_url}{API_ENDPOINTS['club_items']}")

            self._check_response_auth(response)
            response.raise_for_status()
            data = response.json()

            items = []
            for item in data.get("itemData", []):
                club_item = ClubItem(
                    id=item["id"],
                    resource_id=item["resourceId"],
                    item_type=item["itemType"],
                    discardValue=item.get("discardValue", 0),
                    tradeState=item.get("tradeState"),
                    cardSubTypeId=item.get("cardSubTypeId"),
                    loans=item.get("loans"),
                    pile=item.get("pile"),
                )
                items.append(club_item)

            return items

        except httpx.HTTPStatusError as e:
            raise APIError(f"Get club items failed: {e.response.text}", e.response.status_code)

    async def quick_sell_item(self, item_id: int) -> QuickSellResult:
        """Quick sell an item."""
        if not self.x_ut_sid:
            raise SessionExpiredError("Not authenticated")

        try:
            response = await self.session.delete(
                f"{self.base_url}{API_ENDPOINTS['quick_sell'].format(item_id=item_id)}"
            )

            self._check_response_auth(response)
            response.raise_for_status()
            data = response.json()

            return QuickSellResult(success=True, coins_earned=data.get("coins", 0), item_id=item_id)

        except httpx.HTTPStatusError as e:
            return QuickSellResult(success=False, coins_earned=0, item_id=item_id)

    async def send_to_club(self, item_id: int) -> SendToClubResult:
        """Send item to club."""
        if not self.x_ut_sid:
            raise SessionExpiredError("Not authenticated")

        try:
            response = await self.session.put(
                f"{self.base_url}{API_ENDPOINTS['send_to_club']}", json={"itemData": [{"id": item_id, "pile": "club"}]}
            )

            self._check_response_auth(response)
            response.raise_for_status()
            data = response.json()

            return SendToClubResult(success=True, item_id=item_id, duplicate=data.get("duplicate", False))

        except httpx.HTTPStatusError as e:
            return SendToClubResult(success=False, item_id=item_id)

    async def send_to_trade_pile(self, item_id: int) -> SendToTradePileResult:
        """Send item to trade pile."""
        if not self.x_ut_sid:
            raise SessionExpiredError("Not authenticated")

        try:
            response = await self.session.put(
                f"{self.base_url}{API_ENDPOINTS['send_to_tradepile']}",
                json={"itemData": [{"id": item_id, "pile": "trade"}]},
            )

            self._check_response_auth(response)
            response.raise_for_status()

            return SendToTradePileResult(success=True, item_id=item_id)

        except httpx.HTTPStatusError as e:
            return SendToTradePileResult(success=False, item_id=item_id)

    async def relist_items(self) -> RelistResult:
        """Relist all items in trade pile."""
        if not self.x_ut_sid:
            raise SessionExpiredError("Not authenticated")

        try:
            response = await self.session.put(f"{self.base_url}{API_ENDPOINTS['relist']}")

            self._check_response_auth(response)
            response.raise_for_status()
            data = response.json()

            return RelistResult(success=True, relisted_count=data.get("count", 0), errors=[])

        except httpx.HTTPStatusError as e:
            return RelistResult(success=False, relisted_count=0, errors=[e.response.text])

    async def add_to_watchlist(self, trade_id: int) -> bool:
        """Add item to watchlist."""
        if not self.x_ut_sid:
            raise SessionExpiredError("Not authenticated")

        try:
            response = await self.session.put(
                f"{self.base_url}{API_ENDPOINTS['add_to_watchlist']}", json={"auctionInfo": [{"id": trade_id}]}
            )

            self._check_response_auth(response)
            response.raise_for_status()
            return True

        except httpx.HTTPStatusError:
            return False

    async def remove_from_watchlist(self, trade_id: int) -> bool:
        """Remove item from watchlist."""
        if not self.x_ut_sid:
            raise SessionExpiredError("Not authenticated")

        try:
            response = await self.session.delete(
                f"{self.base_url}{API_ENDPOINTS['remove_from_watchlist'].format(trade_id=trade_id)}"
            )

            self._check_response_auth(response)
            response.raise_for_status()
            return True

        except httpx.HTTPStatusError:
            return False

    async def remove_from_trade_pile(self, trade_id: int) -> bool:
        """Remove item from trade pile."""
        if not self.x_ut_sid:
            raise SessionExpiredError("Not authenticated")

        try:
            response = await self.session.delete(
                f"{self.base_url}{API_ENDPOINTS['remove_from_tradepile'].format(trade_id=trade_id)}"
            )

            self._check_response_auth(response)
            response.raise_for_status()
            return True

        except httpx.HTTPStatusError:
            return False

    async def get_trade_status(self) -> TradeStatusResponse:
        """Get trade status for active auctions."""
        if not self.x_ut_sid:
            raise SessionExpiredError("Not authenticated")

        try:
            response = await self.session.get(f"{self.base_url}{API_ENDPOINTS['trade_status']}")

            self._check_response_auth(response)
            response.raise_for_status()
            data = response.json()

            trades = []
            for trade in data.get("auctionInfo", []):
                status = TradeStatus(
                    trade_id=trade["tradeId"],
                    status=trade.get("tradeState", ""),
                    expires=trade["expires"],
                    current_bid=trade["currentBid"],
                    bid_count=trade["bidCount"],
                )
                trades.append(status)

            return TradeStatusResponse(trades=trades)

        except httpx.HTTPStatusError as e:
            raise APIError(f"Get trade status failed: {e.response.text}", e.response.status_code)
