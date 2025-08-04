"""Tests to validate JSON sample data against Pydantic schemas."""

import json
import pytest
from pathlib import Path
from typing import Any, Dict

from api.schemas import (
    LoginResponseSchema,
    SearchResponseSchema,
    BidResponseSchema,
    WatchlistItemSchema,
    TradePileItemSchema,
    TradeStatusResponseSchema,
    CreditsResponseSchema,
    PlayerListResponseSchema,
    SquadListResponseSchema,
    ClubItemSchema,
    QuickSellResponseSchema,
    ItemOperationResponseSchema,
    RelistResponseSchema,
)


def load_json_data(filename: str) -> Dict[str, Any]:
    """Load JSON data from data directory."""
    data_path = Path(__file__).parent.parent / "data" / filename
    with open(data_path, 'r') as f:
        return json.load(f)


class TestJSONSchemas:
    """Test JSON sample data against their corresponding schemas."""
    
    def test_login_json_schema(self):
        """Test login JSON data against LoginResponseSchema."""
        data = load_json_data("login.json")
        
        if data:
            LoginResponseSchema(**data)
        else:
            pytest.skip("Empty JSON data - will be populated later")
    
    def test_login_with_2fa_json_schema(self):
        """Test login with 2FA JSON data against LoginResponseSchema."""
        data = load_json_data("login_with_2fa.json")
        
        if data:
            LoginResponseSchema(**data)
        else:
            pytest.skip("Empty JSON data - will be populated later")
    
    def test_search_players_json_schema(self):
        """Test search players JSON data against SearchResponseSchema."""
        data = load_json_data("search_players.json")
        
        if data:
            SearchResponseSchema(**data)
        else:
            pytest.skip("Empty JSON data - will be populated later")
    
    def test_place_bid_json_schema(self):
        """Test place bid JSON data against BidResponseSchema."""
        data = load_json_data("place_bid.json")
        
        if data:
            BidResponseSchema(**data)
        else:
            pytest.skip("Empty JSON data - will be populated later")
    
    def test_buy_now_json_schema(self):
        """Test buy now JSON data against BidResponseSchema."""
        data = load_json_data("buy_now.json")
        
        if data:
            BidResponseSchema(**data)
        else:
            pytest.skip("Empty JSON data - will be populated later")
    
    def test_get_watchlist_json_schema(self):
        """Test get watchlist JSON data against list of WatchlistItemSchema."""
        data = load_json_data("get_watchlist.json")
        
        if data:
            # Should be a list of watchlist items
            assert isinstance(data, list), "Watchlist data should be a list"
            for item in data:
                WatchlistItemSchema(**item)
        else:
            pytest.skip("Empty JSON data - will be populated later")
    
    def test_get_trade_pile_json_schema(self):
        """Test get trade pile JSON data against list of TradePileItemSchema."""
        data = load_json_data("get_trade_pile.json")
        
        if data:
            # Should be a list of trade pile items
            assert isinstance(data, list), "Trade pile data should be a list"
            for item in data:
                TradePileItemSchema(**item)
        else:
            pytest.skip("Empty JSON data - will be populated later")
    
    def test_get_trade_status_json_schema(self):
        """Test get trade status JSON data against TradeStatusResponseSchema."""
        data = load_json_data("get_trade_status.json")
        
        if data:
            TradeStatusResponseSchema(**data)
        else:
            pytest.skip("Empty JSON data - will be populated later")
    
    def test_add_to_watchlist_json_schema(self):
        """Test add to watchlist JSON data against simple success response."""
        data = load_json_data("add_to_watchlist.json")
        
        if data:
            # Should have a 'success' boolean field
            assert "success" in data, "Response should contain 'success' field"
            assert isinstance(data["success"], bool), "Success field should be boolean"
        else:
            pytest.skip("Empty JSON data - will be populated later")
    
    def test_remove_from_watchlist_json_schema(self):
        """Test remove from watchlist JSON data against simple success response."""
        data = load_json_data("remove_from_watchlist.json")
        
        if data:
            # Should have a 'success' boolean field
            assert "success" in data, "Response should contain 'success' field"
            assert isinstance(data["success"], bool), "Success field should be boolean"
        else:
            pytest.skip("Empty JSON data - will be populated later")
    
    def test_remove_from_trade_pile_json_schema(self):
        """Test remove from trade pile JSON data against simple success response."""
        data = load_json_data("remove_from_trade_pile.json")
        
        if data:
            # Should have a 'success' boolean field
            assert "success" in data, "Response should contain 'success' field"
            assert isinstance(data["success"], bool), "Success field should be boolean"
        else:
            pytest.skip("Empty JSON data - will be populated later")
    
    def test_relist_items_json_schema(self):
        """Test relist items JSON data against RelistResponseSchema."""
        data = load_json_data("relist_items.json")
        
        if data:
            RelistResponseSchema(**data)
        else:
            pytest.skip("Empty JSON data - will be populated later")
    
    def test_get_credits_json_schema(self):
        """Test get credits JSON data against CreditsResponseSchema."""
        data = load_json_data("get_credits.json")
        
        if data:
            CreditsResponseSchema(**data)
        else:
            pytest.skip("Empty JSON data - will be populated later")
    
    def test_get_player_list_json_schema(self):
        """Test get player list JSON data against PlayerListResponseSchema."""
        data = load_json_data("get_player_list.json")
        
        if data:
            PlayerListResponseSchema(**data)
        else:
            pytest.skip("Empty JSON data - will be populated later")
    
    def test_get_squad_list_json_schema(self):
        """Test get squad list JSON data against SquadListResponseSchema."""
        data = load_json_data("get_squad_list.json")
        
        if data:
            SquadListResponseSchema(**data)
        else:
            pytest.skip("Empty JSON data - will be populated later")
    
    def test_get_club_items_json_schema(self):
        """Test get club items JSON data against list of ClubItemSchema."""
        data = load_json_data("get_club_items.json")
        
        if data:
            # Should be a list of club items
            assert isinstance(data, list), "Club items data should be a list"
            for item in data:
                ClubItemSchema(**item)
        else:
            pytest.skip("Empty JSON data - will be populated later")
    
    def test_quick_sell_item_json_schema(self):
        """Test quick sell item JSON data against QuickSellResponseSchema."""
        data = load_json_data("quick_sell_item.json")
        
        if data:
            QuickSellResponseSchema(**data)
        else:
            pytest.skip("Empty JSON data - will be populated later")
    
    def test_send_to_club_json_schema(self):
        """Test send to club JSON data against ItemOperationResponseSchema."""
        data = load_json_data("send_to_club.json")
        
        if data:
            ItemOperationResponseSchema(**data)
        else:
            pytest.skip("Empty JSON data - will be populated later")
    
    def test_send_to_trade_pile_json_schema(self):
        """Test send to trade pile JSON data against ItemOperationResponseSchema."""
        data = load_json_data("send_to_trade_pile.json")
        
        if data:
            ItemOperationResponseSchema(**data)
        else:
            pytest.skip("Empty JSON data - will be populated later")