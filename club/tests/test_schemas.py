"""Test club schemas with sample JSON data."""

import json
from pathlib import Path

from django.test import TestCase

from club.schemas import (
    ClubItem,
    CreditsResponse,
    ItemOperationResponse,
    PlayerListResponse,
    QuickSellResponse,
    SquadListResponse,
)


class ClubSchemaTestCase(TestCase):
    """Test club schemas against sample JSON data."""
    
    fixtures_dir = Path(__file__).parent / "fixtures"
    
    def load_json_fixture(self, filename: str) -> dict:
        """Load JSON fixture data."""
        with open(self.fixtures_dir / filename, "r") as f:
            return json.load(f)
    
    def test_credits_response_schema(self):
        """Test CreditsResponse schema with credits data."""
        data = self.load_json_fixture("get_credits.json")
        
        if data:
            response = CreditsResponse(**data)
            self.assertIsNotNone(response.total)
            self.assertIsNotNone(response.untradeable)
    
    def test_player_list_response_schema(self):
        """Test PlayerListResponse schema with player list data."""
        data = self.load_json_fixture("get_player_list.json")
        
        if data and "itemData" in data:
            # Map the API response format to our schema format
            mapped_data = {
                "players": [
                    {
                        "id": item["id"],
                        "resource_id": item["resourceId"],
                        "asset_id": item["assetId"],
                        "rating": item["rating"],
                        "rare_flag": item.get("rareflag", 0),
                        "preferred_position": item["preferredPosition"],
                        "name": item.get("name", "Unknown"),
                        "untradeable": item["untradeable"]
                    }
                    for item in data["itemData"]
                ],
                "total": len(data["itemData"])
            }
            response = PlayerListResponse(**mapped_data)
            self.assertIsInstance(response.players, list)
            self.assertIsNotNone(response.total)
    
    def test_squad_list_response_schema(self):
        """Test SquadListResponse schema with squad list data."""
        data = self.load_json_fixture("get_squad_list.json")
        
        if data:
            response = SquadListResponse(**data)
            self.assertIsInstance(response.squads, list)
            self.assertIsNotNone(response.active_squad_id)
    
    def test_club_items_schema(self):
        """Test ClubItem schema with club items data."""
        data = self.load_json_fixture("get_club_items.json")
        
        if data and isinstance(data, list):
            for item in data:
                club_item = ClubItem(**item)
                self.assertIsNotNone(club_item.id)
                self.assertIsNotNone(club_item.resource_id)
                self.assertIsNotNone(club_item.item_type)
    
    def test_quick_sell_response_schema(self):
        """Test QuickSellResponse schema with quick sell data."""
        data = self.load_json_fixture("quick_sell_item.json")
        
        if data:
            response = QuickSellResponse(**data)
            self.assertIsNotNone(response.success)
            self.assertIsNotNone(response.credits_earned)
            self.assertIsNotNone(response.total_credits)
    
    def test_item_operation_response_schema(self):
        """Test ItemOperationResponse schema with send to club data."""
        send_to_club_data = self.load_json_fixture("send_to_club.json")
        
        if send_to_club_data:
            response = ItemOperationResponse(**send_to_club_data)
            self.assertIsNotNone(response.success)
            self.assertIsNotNone(response.message)
            self.assertIsNotNone(response.item_id)
        
        send_to_trade_data = self.load_json_fixture("send_to_trade_pile.json")
        
        if send_to_trade_data:
            response = ItemOperationResponse(**send_to_trade_data)
            self.assertIsNotNone(response.success)
            self.assertIsNotNone(response.message)
