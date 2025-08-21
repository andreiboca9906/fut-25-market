"""Market and trading services."""

import logging
from typing import Dict, List

import httpx

from core.constants import API_ENDPOINTS
from core.exceptions import APIError, SessionExpiredError
from core.fut_models.club import TradeStatus

logger = logging.getLogger(__name__)


class MarketService:
    """Service for market and trading operations."""

    def __init__(self, session: httpx.AsyncClient, x_ut_sid: str):
        self.session = session
        self.x_ut_sid = x_ut_sid
        self.base_url = API_ENDPOINTS["base_url"]

    def _check_response_auth(self, response: httpx.Response) -> None:
        """Check response for authentication errors."""
        if response.status_code == 401:
            raise SessionExpiredError("Session expired or invalid X-UT-SID")
        elif response.status_code == 403:
            raise SessionExpiredError("Access forbidden - check session permissions")

    async def get_trade_status(self, trade_ids: List[str]) -> Dict[str, TradeStatus]:
        """Get trade status for specific trade IDs.

        Args:
            trade_ids: List of trade IDs to check (max 20)

        Returns:
            Dictionary mapping trade_id to TradeStatus
        """
        if not self.x_ut_sid:
            raise SessionExpiredError("Not authenticated")

        if not trade_ids:
            return {}

        # TODO: Verify max 20 trade IDs limit with EA API
        if len(trade_ids) > 20:
            logger.warning(f"Checking {len(trade_ids)} trades, API may limit to 20")
            trade_ids = trade_ids[:20]

        try:
            # Build the trade IDs query parameter
            trade_ids_param = ",".join(str(tid) for tid in trade_ids)

            response = await self.session.get(
                f"{self.base_url}/trade/status/lite", params={"tradeIds": trade_ids_param}
            )

            self._check_response_auth(response)
            response.raise_for_status()
            data = response.json()

            trades = {}
            for item in data.get("auctionInfo", []):
                trade_id = str(item["tradeId"])

                # Determine status based on trade state
                trade_state = item.get("tradeState", "")
                if trade_state == "closed":
                    # Check if it was sold or expired
                    if item.get("bidState") == "buyNow" or item.get("currentBid", 0) > 0:
                        status = "sold"
                    else:
                        status = "expired"
                elif trade_state == "active":
                    status = "active"
                else:
                    status = trade_state.lower()

                trade_status = TradeStatus(
                    trade_id=item["tradeId"],
                    status=status,
                    expires=item.get("expires", 0),
                    current_bid=item.get("currentBid", 0),
                    bid_count=item.get("offers", 0),
                )
                trades[trade_id] = trade_status

            return trades

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                raise APIError("Rate limit exceeded", 429)
            logger.error(f"HTTP error in get_trade_status: {e}", exc_info=True)
            raise APIError(f"Get trade status failed: {e}", e.response.status_code)
