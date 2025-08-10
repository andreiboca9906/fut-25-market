"""Test market schemas with sample JSON data."""

import json
from pathlib import Path

from django.test import TestCase

from market.schemas import BidResponse, RelistResponse, SearchResult, TradePileItem, TradeStatusResponse, WatchlistItem


class MarketSchemaTestCase(TestCase):
    """Test market schemas against sample JSON data."""
    
    fixtures_dir = Path(__file__).parent / "fixtures"
    
    def load_json_fixture(self, filename: str) -> dict:
        """Load JSON fixture data."""
        with open(self.fixtures_dir / filename, "r") as f:
            return json.load(f)
    
    def test_search_response_schema(self):
        """Test SearchResult schema with sample search data."""
        data = self.load_json_fixture("search_players.json")
        
        if data:
            # Expecting search result format
            if "total_pages" in data:
                response = SearchResult(**data)
                self.assertIsNotNone(response.total_pages)
                self.assertIsInstance(response.items, list)
    
    def test_bid_response_schema(self):
        """Test BidResponse schema with place bid data."""
        data = self.load_json_fixture("place_bid.json")
        
        if data:
            response = BidResponse(**data)
            self.assertIsNotNone(response.success)
            self.assertIsNotNone(response.trade_id)
    
    def test_buy_now_response_schema(self):
        """Test BidResponse schema with buy now data."""
        data = self.load_json_fixture("buy_now.json")
        
        if data:
            response = BidResponse(**data)
            self.assertIsNotNone(response.success)
    
    def test_watchlist_schema(self):
        """Test WatchlistItem schema with watchlist data."""
        data = self.load_json_fixture("get_watchlist.json")
        
        if data and isinstance(data, list):
            for item in data:
                watchlist_item = WatchlistItem(**item)
                self.assertIsNotNone(watchlist_item.trade_id)
                self.assertTrue(watchlist_item.watched)
    
    def test_trade_pile_schema(self):
        """Test TradePileItem schema with trade pile data."""
        data = self.load_json_fixture("get_trade_pile.json")
        
        if data and isinstance(data, list):
            for item in data:
                trade_item = TradePileItem(**item)
                self.assertIsNotNone(trade_item.trade_id)
                self.assertIsNotNone(trade_item.trade_state)
    
    def test_trade_status_schema(self):
        """Test TradeStatusResponse schema with trade status data."""
        data = self.load_json_fixture("get_trade_status.json")
        
        if data:
            response = TradeStatusResponse(**data)
            self.assertIsNotNone(response.credits)
            self.assertIsInstance(response.auction_info, list)
    
    def test_relist_response_schema(self):
        """Test RelistResponse schema with relist data."""
        data = self.load_json_fixture("relist_items.json")
        
        if data:
            response = RelistResponse(**data)
            self.assertIsNotNone(response.success)
            self.assertIsNotNone(response.relisted_count)
    
    def test_watchlist_operations(self):
        """Test watchlist add/remove operations response."""
        add_data = self.load_json_fixture("add_to_watchlist.json")
        if add_data:
            self.assertIn("success", add_data)
            self.assertIsInstance(add_data["success"], bool)
        
        remove_data = self.load_json_fixture("remove_from_watchlist.json")
        if remove_data:
            self.assertIn("success", remove_data)
            self.assertIsInstance(remove_data["success"], bool)
    
    def test_trade_pile_remove(self):
        """Test trade pile remove operation response."""
        data = self.load_json_fixture("remove_from_trade_pile.json")
        
        if data:
            self.assertIn("success", data)
            self.assertIsInstance(data["success"], bool)
