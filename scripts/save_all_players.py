"""
Script to fetch and save all players from FUT API to PostgreSQL
Handles rate limiting, checkpointing, and session expiry
"""

import json
import os
import sys
import time
from datetime import datetime
from typing import Dict, List, Optional

import requests
from db_manager import DB_CONFIG, DatabaseManager

API_URL = "https://utas.mob.v4.prd.futc-ext.gcp.ea.com/ut/game/fc25/defid"
RATE_LIMIT = 50  # requests per minute
BATCH_SIZE = 200  # max items per request

# Ensure directories exist
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SUMMARY_DIR = os.path.join(SCRIPT_DIR, "post-execution-summaries")
LOG_DIR = os.path.join(SCRIPT_DIR, "logs")

os.makedirs(SUMMARY_DIR, exist_ok=True)
os.makedirs(LOG_DIR, exist_ok=True)

CHECKPOINT_FILE = os.path.join(SCRIPT_DIR, "player_fetch_checkpoint.json")
LOG_FILE = os.path.join(LOG_DIR, f"player_fetch_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log")


class PlayerFetcher:
    def __init__(self, sid: str):
        self.sid = sid
        self.headers = {
            "x-ut-sid": sid,
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        self.all_players = []
        self.checkpoint = self.load_checkpoint()
        self.request_count = 0
        self.last_minute_start = time.time()
        self.db = DatabaseManager()
        
    def log(self, message: str):
        """Log message to both console and file"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_entry = f"[{timestamp}] {message}"
        print(log_entry)
        with open(LOG_FILE, "a") as f:
            f.write(log_entry + "\n")
    
    def load_checkpoint(self) -> Dict:
        """Load checkpoint if it exists"""
        if os.path.exists(CHECKPOINT_FILE):
            try:
                with open(CHECKPOINT_FILE, "r") as f:
                    checkpoint = json.load(f)
                    self.log(f"Loaded checkpoint: {checkpoint['fetched_count']} players fetched, starting at offset {checkpoint['offset']}")
                    return checkpoint
            except Exception as e:
                self.log(f"Error loading checkpoint: {e}")
        return {"offset": 0, "fetched_count": 0}
    
    def save_checkpoint(self, offset: int):
        """Save current progress to checkpoint"""
        checkpoint = {
            "offset": offset,
            "fetched_count": len(self.all_players),
            "timestamp": datetime.now().isoformat(),
            "last_player_id": self.all_players[-1]["id"] if self.all_players else None
        }
        with open(CHECKPOINT_FILE, "w") as f:
            json.dump(checkpoint, f, indent=2)
        self.log(f"Checkpoint saved: {len(self.all_players)} players fetched, next offset: {offset}")
    
    def rate_limit(self):
        """Implement rate limiting - 50 requests per minute"""
        self.request_count += 1
        
        # Check if we need to wait for the next minute
        current_time = time.time()
        elapsed = current_time - self.last_minute_start
        
        if elapsed >= 60:
            # Reset for new minute
            self.request_count = 1
            self.last_minute_start = current_time
        elif self.request_count >= RATE_LIMIT:
            # Wait for the remainder of the minute
            wait_time = 60 - elapsed + 1  # Add 1 second buffer
            self.log(f"Rate limit reached. Waiting {wait_time:.1f} seconds...")
            time.sleep(wait_time)
            self.request_count = 1
            self.last_minute_start = time.time()
    
    def fetch_batch(self, offset: int) -> Optional[List[Dict]]:
        """Fetch a batch of players from the API"""
        self.rate_limit()
        
        params = {
            "count": BATCH_SIZE,
            "sort": "desc",
            "start": offset,
            "type": "player"
        }
        
        try:
            self.log(f"Fetching batch at offset {offset}...")
            response = requests.get(API_URL, headers=self.headers, params=params, timeout=30)
            
            if response.status_code == 401:
                # Session expired
                data = response.json()
                if data.get("reason") == "expired session":
                    self.log("Session expired! Need new SID.")
                    new_sid = input("\nSession expired. Please enter new SID: ").strip()
                    self.sid = new_sid
                    self.headers["x-ut-sid"] = new_sid
                    self.log("Updated SID, retrying...")
                    return self.fetch_batch(offset)  # Retry with new SID
            
            response.raise_for_status()
            data = response.json()
            
            if "itemData" in data:
                items = data["itemData"]
                self.log(f"Fetched {len(items)} players at offset {offset}")
                return items
            else:
                self.log(f"Unexpected response structure: {data.keys()}")
                return None
                
        except requests.exceptions.RequestException as e:
            self.log(f"Request error at offset {offset}: {e}")
            return None
        except json.JSONDecodeError as e:
            self.log(f"JSON decode error at offset {offset}: {e}")
            return None
    
    def fetch_all_players(self):
        """Main function to fetch all players"""
        # Initialize database
        if not self.db.connect():
            self.log("Failed to connect to database. Exiting.")
            return
        
        if not self.db.create_table():
            self.log("Failed to create table. Exiting.")
            self.db.close()
            return
        
        self.log("Database connection established and table ready")
        
        # Load offset from checkpoint
        offset = self.checkpoint.get("offset", 0)
        
        # Note: We don't load players from checkpoint anymore since they're in the database
        # The fetched_count in checkpoint is just for reference
        
        consecutive_empty = 0
        max_consecutive_empty = 3  # Stop after 3 consecutive empty responses
        batch_for_db = []  # Batch for database insertion
        
        while True:
            batch = self.fetch_batch(offset)
            
            if batch is None:
                # Error occurred, save checkpoint and ask user
                self.save_checkpoint(offset)
                retry = input("\nError occurred. Retry? (y/n): ").strip().lower()
                if retry != "y":
                    break
                continue
            
            if len(batch) == 0:
                consecutive_empty += 1
                self.log(f"Empty batch received ({consecutive_empty}/{max_consecutive_empty})")
                
                if consecutive_empty >= max_consecutive_empty:
                    self.log("Reached end of data (multiple empty batches)")
                    break
            else:
                consecutive_empty = 0
                self.all_players.extend(batch)
                batch_for_db.extend(batch)
                
                # Save to database every 500 players
                if len(batch_for_db) >= 500:
                    if self.db.upsert_players(batch_for_db):
                        self.log(f"Saved {len(batch_for_db)} players to database")
                        batch_for_db = []
                    else:
                        self.log("CRITICAL: Failed to save players to database - stopping fetch")
                        self.save_checkpoint(offset)
                        self.log(f"Checkpoint saved at offset {offset}")
                        self.log("Fix the database issue and resume from checkpoint")
                        break
                
                # Save checkpoint every 1000 players
                if len(self.all_players) % 1000 == 0:
                    self.save_checkpoint(offset + BATCH_SIZE)
            
            # Check if we got less than full batch (likely end of data)
            if len(batch) < BATCH_SIZE:
                self.log(f"Partial batch received ({len(batch)}/{BATCH_SIZE}), likely end of data")
                break
            
            offset += BATCH_SIZE
            
            # Progress update
            if len(self.all_players) % 500 == 0:
                self.log(f"Progress: {len(self.all_players)} players fetched so far")
        
        # Save any remaining players to database
        if batch_for_db:
            if self.db.upsert_players(batch_for_db):
                self.log(f"Saved final {len(batch_for_db)} players to database")
            else:
                self.log("CRITICAL: Failed to save final batch to database")
                self.save_checkpoint(offset)
                self.log(f"Checkpoint saved at offset {offset}")
                self.log("Fix the database issue and resume from checkpoint")
        
        # Final save
        self.log(f"Fetching complete. Total players: {len(self.all_players)}")
        self.save_players_summary()
        
        # Close database connection
        self.db.close()
        self.log("Database connection closed")
        
        # Clean up checkpoint file
        if os.path.exists(CHECKPOINT_FILE):
            os.remove(CHECKPOINT_FILE)
            self.log("Checkpoint file removed")
    
    def save_players_summary(self):
        """Save a summary of fetched players"""
        summary = {
            "total_players": len(self.all_players),
            "fetch_date": datetime.now().isoformat(),
            "unique_teams": len(set(p.get("teamid", 0) for p in self.all_players)),
            "unique_nations": len(set(p.get("nation", 0) for p in self.all_players)),
            "unique_leagues": len(set(p.get("leagueId", 0) for p in self.all_players)),
            "rating_distribution": {}
        }
        
        # Calculate rating distribution
        for player in self.all_players:
            rating = player.get("rating", 0)
            if rating > 0:
                summary["rating_distribution"][str(rating)] = summary["rating_distribution"].get(str(rating), 0) + 1
        
        summary_file = os.path.join(SUMMARY_DIR, f"player_fetch_summary_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
        with open(summary_file, "w") as f:
            json.dump(summary, f, indent=2)
        
        self.log(f"Saved fetch summary to {summary_file}")


def main():
    print("FUT Player Fetcher (PostgreSQL Version)")
    print("========================================")
    print("This will fetch all players from the FUT API and save to PostgreSQL")
    print(f"Database: {DB_CONFIG['database']}")
    print(f"Rate limit: {RATE_LIMIT} requests/minute")
    print(f"Checkpoint file: {CHECKPOINT_FILE}")
    print(f"Log file: {LOG_FILE}\n")
    
    # Check if we have a checkpoint
    if os.path.exists(CHECKPOINT_FILE):
        resume = input("Found existing checkpoint. Resume from checkpoint? (y/n): ").strip().lower()
        if resume != "y":
            # Clear checkpoint
            os.remove(CHECKPOINT_FILE)
            print("Checkpoint cleared. Starting fresh.\n")
    
    # Get SID
    sid = input("Enter your x-ut-sid: ").strip()
    
    if not sid:
        print("Error: SID is required")
        sys.exit(1)
    
    # Create fetcher and run
    fetcher = PlayerFetcher(sid)
    
    try:
        fetcher.fetch_all_players()
        print(f"\nSuccess! {len(fetcher.all_players)} players saved to PostgreSQL database")
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
        fetcher.save_checkpoint(fetcher.checkpoint.get("offset", 0))
        print("Progress saved to checkpoint. You can resume later.")
        if fetcher.db:
            fetcher.db.close()
        sys.exit(0)
    except Exception as e:
        print(f"\nUnexpected error: {e}")
        fetcher.save_checkpoint(fetcher.checkpoint.get("offset", 0))
        print("Progress saved to checkpoint. You can resume later.")
        if fetcher.db:
            fetcher.db.close()
        sys.exit(1)


if __name__ == "__main__":
    main()
