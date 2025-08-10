"""Player data management service."""

import time
from datetime import datetime
from typing import Dict, List, Optional

import requests

from .db_manager import DatabaseManager


class PlayerDataService:
    """Service for fetching and managing player data."""
    
    FUT_API_URL = "https://utas.mob.v4.prd.futc-ext.gcp.ea.com/ut/game/fc25/defid"
    EA_PLAYERS_API_URL = "https://www.ea.com/ea-sports-fc/ultimate-team/web-app/content/25E4CDAE-799B-45BE-B257-667FDCDE8044/2025/fut/items/web/players.json"
    
    RATE_LIMIT = 50  # requests per minute
    BATCH_SIZE = 200  # max items per request
    
    def __init__(self, sid: Optional[str] = None):
        self.sid = sid
        self.headers = {}
        if sid:
            self.headers = {
                "x-ut-sid": sid,
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }
        self.request_count = 0
        self.last_minute_start = time.time()
        self.db = DatabaseManager()
    
    def _rate_limit(self):
        """Implement rate limiting."""
        self.request_count += 1
        
        current_time = time.time()
        elapsed = current_time - self.last_minute_start
        
        if elapsed >= 60:
            self.request_count = 1
            self.last_minute_start = current_time
        elif self.request_count >= self.RATE_LIMIT:
            wait_time = 60 - elapsed + 1
            time.sleep(wait_time)
            self.request_count = 1
            self.last_minute_start = time.time()
    
    def fetch_players_batch(self, offset: int = 0, count: int = BATCH_SIZE) -> Optional[List[Dict]]:
        """Fetch a batch of players from FUT API."""
        if not self.sid:
            raise ValueError("SID is required for FUT API calls")
        
        self._rate_limit()
        
        params = {
            "count": count,
            "sort": "desc",
            "start": offset,
            "type": "player"
        }
        
        try:
            response = requests.get(
                self.FUT_API_URL,
                headers=self.headers,
                params=params,
                timeout=30
            )
            
            if response.status_code == 401:
                data = response.json()
                if data.get("reason") == "expired session":
                    raise Exception("Session expired. Need new SID.")
            
            response.raise_for_status()
            data = response.json()
            
            if "itemData" in data:
                return data["itemData"]
            
            return None
            
        except requests.exceptions.RequestException as e:
            print(f"Request error at offset {offset}: {e}")
            return None
    
    def fetch_all_players(self, checkpoint: Optional[Dict] = None) -> Dict:
        """Fetch all players from FUT API and save to database."""
        if not self.db.connect():
            raise Exception("Failed to connect to database")
        
        if not self.db.create_table():
            self.db.close()
            raise Exception("Failed to create table")
        
        offset = checkpoint.get("offset", 0) if checkpoint else 0
        all_players = []
        consecutive_empty = 0
        max_consecutive_empty = 3
        batch_for_db = []
        
        while True:
            batch = self.fetch_players_batch(offset)
            
            if batch is None:
                break
            
            if len(batch) == 0:
                consecutive_empty += 1
                if consecutive_empty >= max_consecutive_empty:
                    break
            else:
                consecutive_empty = 0
                all_players.extend(batch)
                batch_for_db.extend(batch)
                
                if len(batch_for_db) >= 500:
                    if self.db.upsert_players(batch_for_db):
                        batch_for_db = []
                    else:
                        break
            
            if len(batch) < self.BATCH_SIZE:
                break
            
            offset += self.BATCH_SIZE
        
        if batch_for_db:
            self.db.upsert_players(batch_for_db)
        
        self.db.close()
        
        return {
            "total_players": len(all_players),
            "last_offset": offset,
            "fetch_date": datetime.now().isoformat()
        }
    
    def fetch_player_names(self) -> Optional[Dict]:
        """Fetch player names from EA API."""
        try:
            response = requests.get(self.EA_PLAYERS_API_URL, timeout=30)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"Failed to fetch player names: {e}")
            return None
    
    def update_player_names(self) -> Dict:
        """Update player names in the database."""
        data = self.fetch_player_names()
        if not data:
            raise Exception("Failed to fetch player data")
        
        if not self.db.connect():
            raise Exception("Failed to connect to database")
        
        if not self.db.add_name_columns_if_not_exists():
            self.db.close()
            raise Exception("Failed to add name columns")
        
        total_updated = 0
        all_not_found = []
        
        players = data.get("Players", [])
        for player in players:
            asset_id = player.get("id")
            first_name = player.get("f", "")
            last_name = player.get("l", "")
            
            if asset_id:
                if self.db.update_player_names(asset_id, first_name, last_name):
                    total_updated += 1
                else:
                    all_not_found.append({
                        "asset_id": asset_id,
                        "first_name": first_name,
                        "last_name": last_name,
                        "type": "regular"
                    })
        
        legend_players = data.get("LegendsPlayers", [])
        for player in legend_players:
            asset_id = player.get("id")
            first_name = player.get("f", "")
            last_name = player.get("l", "")
            
            if asset_id:
                if self.db.update_player_names(asset_id, first_name, last_name):
                    total_updated += 1
                else:
                    all_not_found.append({
                        "asset_id": asset_id,
                        "first_name": first_name,
                        "last_name": last_name,
                        "type": "legend"
                    })
        
        self.db.conn.commit()
        self.db.close()
        
        return {
            "total_processed": len(players) + len(legend_players),
            "total_updated": total_updated,
            "total_not_found": len(all_not_found),
            "not_found_players": all_not_found
        }
    
    def get_sample_players(self, limit: int = 5) -> List[Dict]:
        """Get a sample of players from the database."""
        if not self.db.connect():
            return []
        
        players = self.db.get_players_sample(limit)
        self.db.close()
        return players
    
    def get_players_summary(self) -> Dict:
        """Get summary statistics of players in the database."""
        if not self.db.connect():
            return {
                "error": "Failed to connect to database",
                "general_stats": {},
                "rating_distribution": [],
                "position_distribution": [],
                "card_type_distribution": []
            }
        
        summary = self.db.get_players_summary()
        self.db.close()
        return summary
