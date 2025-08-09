"""
Script to fetch player names from EA API and update the database
"""

import json
import os
import sys
from datetime import datetime

import requests
from db_manager import DatabaseManager

API_URL = "https://www.ea.com/ea-sports-fc/ultimate-team/web-app/content/25E4CDAE-799B-45BE-B257-667FDCDE8044/2025/fut/items/web/players.json"

# Ensure directories exist
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SUMMARY_DIR = os.path.join(SCRIPT_DIR, "post-execution-summaries")
LOG_DIR = os.path.join(SCRIPT_DIR, "logs")

os.makedirs(SUMMARY_DIR, exist_ok=True)
os.makedirs(LOG_DIR, exist_ok=True)


def fetch_player_names():
    """Fetch player names from EA API"""
    try:
        print("Fetching player names from EA API...")
        response = requests.get(API_URL, timeout=30)
        response.raise_for_status()
        data = response.json()
        print("Successfully fetched player data")
        return data
    except requests.exceptions.RequestException as e:
        print(f"Failed to fetch player names: {e}")
        return None
    except Exception as e:
        print(f"Unexpected error: {e}")
        return None


def process_player_list(db, players, player_type):
    """Process a list of players and update their names in the database"""
    updated_count = 0
    not_found_players = []
    
    print(f"Processing {len(players)} {player_type}...")
    
    for player in players:
        asset_id = player.get("id")
        first_name = player.get("f", "")
        last_name = player.get("l", "")
        
        if asset_id:
            if db.update_player_names(asset_id, first_name, last_name):
                updated_count += 1
            else:
                not_found_players.append({
                    "asset_id": asset_id,
                    "first_name": first_name,
                    "last_name": last_name,
                    "type": player_type,
                    "rating": player.get("r", None)
                })
    
    return updated_count, not_found_players


def update_player_names(data):
    """Update player names in the database"""
    db = DatabaseManager()
    
    if not db.connect():
        print("Failed to connect to database")
        return False
    
    # Ensure name columns exist
    if not db.add_name_columns_if_not_exists():
        print("Failed to add name columns")
        db.close()
        return False
    
    total_updated = 0
    all_not_found = []
    
    # Process regular players
    players = data.get("Players", [])
    updated, not_found = process_player_list(db, players, "regular players")
    total_updated += updated
    all_not_found.extend(not_found)
    
    # Process legend players
    legend_players = data.get("LegendsPlayers", [])
    updated, not_found = process_player_list(db, legend_players, "legend players")
    total_updated += updated
    all_not_found.extend(not_found)
    
    # Commit all changes
    db.conn.commit()
    
    # Save summary to JSON file
    summary = {
        "timestamp": datetime.now().isoformat(),
        "total_processed": len(players) + len(legend_players),
        "total_updated": total_updated,
        "total_not_found": len(all_not_found),
        "regular_players_count": len(players),
        "legend_players_count": len(legend_players),
        "not_found_players": all_not_found
    }
    
    summary_file = os.path.join(SUMMARY_DIR, f"player_names_save_summary_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
    with open(summary_file, "w") as f:
        json.dump(summary, f, indent=2)
    
    print("\nSummary:")
    print(f"- Updated: {total_updated} players")
    print(f"- Not found in database: {len(all_not_found)} players")
    print(f"- Total processed: {len(players) + len(legend_players)} players")
    print(f"\nDetailed summary saved to {summary_file}")
    
    db.close()
    return True


def main():
    print("FUT Player Names Updater")
    print("========================\n")
    
    # Fetch player names from API
    data = fetch_player_names()
    if not data:
        print("Failed to fetch player data")
        sys.exit(1)
    
    # Update database
    if update_player_names(data):
        print("\nPlayer names updated successfully!")
    else:
        print("\nFailed to update player names")
        sys.exit(1)


if __name__ == "__main__":
    main()
