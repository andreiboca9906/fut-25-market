"""
Database manager for FUT data operations
"""

import os
import traceback
from typing import Dict, List

import psycopg2
from psycopg2.extras import Json, execute_batch

# Database configuration
DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", "5432")),
    "database": os.getenv("DB_NAME", "eafc25"),
    "user": os.getenv("DB_USER", "postgres"),
    "password": os.getenv("DB_PASSWORD", "postgres")
}


class DatabaseManager:
    """Manages database connections and operations"""
    
    def __init__(self):
        self.conn = None
        self.cursor = None
        
    def connect(self):
        """Establish database connection"""
        try:
            self.conn = psycopg2.connect(**DB_CONFIG)
            self.cursor = self.conn.cursor()
            return True
        except Exception as e:
            print(f"Failed to connect to database: {e}")
            return False
    
    def create_table(self):
        """Create players table if it doesn't exist"""
        create_table_query = """
        CREATE TABLE IF NOT EXISTS players (
            id BIGINT PRIMARY KEY,
            timestamp BIGINT,
            formation VARCHAR(20),
            untradeable BOOLEAN,
            asset_id INTEGER,
            rating INTEGER,
            dream BOOLEAN,
            item_type VARCHAR(50),
            resource_id BIGINT,
            owners INTEGER,
            discard_value INTEGER,
            card_subtype_id INTEGER,
            last_sale_price INTEGER,
            injury_type VARCHAR(50),
            injury_games INTEGER,
            preferred_position VARCHAR(10),
            stats_list JSONB,
            lifetime_stats JSONB,
            contract INTEGER,
            team_id INTEGER,
            rare_flag INTEGER,
            play_style INTEGER,
            league_id INTEGER,
            loyalty_bonus INTEGER,
            pile INTEGER,
            nation INTEGER,
            resource_game_year INTEGER,
            guid_asset_id UUID,
            attribute_array JSONB,
            skill_moves INTEGER,
            weak_foot_ability_type_code INTEGER,
            preferred_foot INTEGER,
            possible_positions JSONB,
            gender INTEGER,
            base_traits JSONB,
            icon_traits_priorities JSONB,
            icon_traits JSONB,
            plus_plus_roles JSONB,
            groups JSONB,
            first_name VARCHAR(100),
            last_name VARCHAR(100),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        
        CREATE INDEX IF NOT EXISTS idx_players_asset_id ON players(asset_id);
        CREATE INDEX IF NOT EXISTS idx_players_rating ON players(rating);
        CREATE INDEX IF NOT EXISTS idx_players_preferred_position ON players(preferred_position);
        CREATE INDEX IF NOT EXISTS idx_players_team_id ON players(team_id);
        CREATE INDEX IF NOT EXISTS idx_players_nation ON players(nation);
        CREATE INDEX IF NOT EXISTS idx_players_league_id ON players(league_id);
        """
        try:
            self.cursor.execute(create_table_query)
            self.conn.commit()
            return True
        except Exception as e:
            print(f"Failed to create table: {e}")
            self.conn.rollback()
            return False
    
    def add_name_columns_if_not_exists(self):
        """Add first_name and last_name columns if they don't exist"""
        try:
            # Check if columns exist
            self.cursor.execute("""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = 'players'
                AND column_name IN ('first_name', 'last_name')
            """)
            existing_columns = [row[0] for row in self.cursor.fetchall()]
            
            # Add missing columns
            if "first_name" not in existing_columns:
                self.cursor.execute("ALTER TABLE players ADD COLUMN first_name VARCHAR(100)")
                print("Added first_name column to players table")
            
            if "last_name" not in existing_columns:
                self.cursor.execute("ALTER TABLE players ADD COLUMN last_name VARCHAR(100)")
                print("Added last_name column to players table")
            
            self.conn.commit()
            return True
        except Exception as e:
            print(f"Failed to add name columns: {e}")
            self.conn.rollback()
            return False
    
    def upsert_players(self, players: List[Dict]):
        """Insert or update players in batch"""
        if not players:
            return True
            
        insert_query = """
        INSERT INTO players (
            id, timestamp, formation, untradeable, asset_id, rating, dream,
            item_type, resource_id, owners, discard_value, card_subtype_id,
            last_sale_price, injury_type, injury_games, preferred_position,
            stats_list, lifetime_stats, contract, team_id, rare_flag, play_style,
            league_id, loyalty_bonus, pile, nation, resource_game_year,
            guid_asset_id, attribute_array, skill_moves, weak_foot_ability_type_code,
            preferred_foot, possible_positions, gender, base_traits,
            icon_traits_priorities, icon_traits, plus_plus_roles, groups,
            first_name, last_name
        ) VALUES (
            %(id)s, %(timestamp)s, %(formation)s, %(untradeable)s, %(assetId)s,
            %(rating)s, %(dream)s, %(itemType)s, %(resourceId)s, %(owners)s,
            %(discardValue)s, %(cardsubtypeid)s, %(lastSalePrice)s, %(injuryType)s,
            %(injuryGames)s, %(preferredPosition)s, %(statsList)s, %(lifetimeStats)s,
            %(contract)s, %(teamid)s, %(rareflag)s, %(playStyle)s, %(leagueId)s,
            %(loyaltyBonus)s, %(pile)s, %(nation)s, %(resourceGameYear)s,
            %(guidAssetId)s, %(attributeArray)s, %(skillmoves)s,
            %(weakfootabilitytypecode)s, %(preferredfoot)s, %(possiblePositions)s,
            %(gender)s, %(baseTraits)s, %(iconTraitsPriorities)s, %(iconTraits)s,
            %(plusPlusRoles)s, %(groups)s, %(first_name)s, %(last_name)s
        )
        ON CONFLICT (id) DO UPDATE SET
            timestamp = EXCLUDED.timestamp,
            formation = EXCLUDED.formation,
            untradeable = EXCLUDED.untradeable,
            asset_id = EXCLUDED.asset_id,
            rating = EXCLUDED.rating,
            dream = EXCLUDED.dream,
            item_type = EXCLUDED.item_type,
            resource_id = EXCLUDED.resource_id,
            owners = EXCLUDED.owners,
            discard_value = EXCLUDED.discard_value,
            card_subtype_id = EXCLUDED.card_subtype_id,
            last_sale_price = EXCLUDED.last_sale_price,
            injury_type = EXCLUDED.injury_type,
            injury_games = EXCLUDED.injury_games,
            preferred_position = EXCLUDED.preferred_position,
            stats_list = EXCLUDED.stats_list,
            lifetime_stats = EXCLUDED.lifetime_stats,
            contract = EXCLUDED.contract,
            team_id = EXCLUDED.team_id,
            rare_flag = EXCLUDED.rare_flag,
            play_style = EXCLUDED.play_style,
            league_id = EXCLUDED.league_id,
            loyalty_bonus = EXCLUDED.loyalty_bonus,
            pile = EXCLUDED.pile,
            nation = EXCLUDED.nation,
            resource_game_year = EXCLUDED.resource_game_year,
            guid_asset_id = EXCLUDED.guid_asset_id,
            attribute_array = EXCLUDED.attribute_array,
            skill_moves = EXCLUDED.skill_moves,
            weak_foot_ability_type_code = EXCLUDED.weak_foot_ability_type_code,
            preferred_foot = EXCLUDED.preferred_foot,
            possible_positions = EXCLUDED.possible_positions,
            gender = EXCLUDED.gender,
            base_traits = EXCLUDED.base_traits,
            icon_traits_priorities = EXCLUDED.icon_traits_priorities,
            icon_traits = EXCLUDED.icon_traits,
            plus_plus_roles = EXCLUDED.plus_plus_roles,
            groups = EXCLUDED.groups,
            first_name = COALESCE(EXCLUDED.first_name, players.first_name),
            last_name = COALESCE(EXCLUDED.last_name, players.last_name),
            updated_at = CURRENT_TIMESTAMP;
        """
        
        try:
            # Prepare data for insertion
            prepared_data = []
            for player in players:
                # Convert JSON fields to Json type for proper storage
                prepared_player = player.copy()
                
                # Handle missing guidAssetId field specifically
                if "guidAssetId" not in prepared_player:
                    prepared_player["guidAssetId"] = None
                
                # Handle name fields
                if "first_name" not in prepared_player:
                    prepared_player["first_name"] = None
                if "last_name" not in prepared_player:
                    prepared_player["last_name"] = None
                
                # Handle JSON fields
                json_fields = ["statsList", "lifetimeStats", "attributeArray",
                              "possiblePositions", "baseTraits", "iconTraitsPriorities",
                              "iconTraits", "plusPlusRoles", "groups"]
                
                for field in json_fields:
                    if field in prepared_player:
                        prepared_player[field] = Json(prepared_player[field])
                    else:
                        prepared_player[field] = None
                        
                prepared_data.append(prepared_player)
            
            # Execute batch insert
            execute_batch(self.cursor, insert_query, prepared_data, page_size=100)
            self.conn.commit()
            return True
        except Exception as e:
            error_details = traceback.format_exc()
            print(f"Failed to insert players: {e}")
            print(f"Error type: {type(e).__name__}")
            print(f"Full traceback:\n{error_details}")
            
            # Log sample player data for debugging
            if players:
                print(f"Sample player keys: {list(players[0].keys())}")
                print(f"Total players in batch: {len(players)}")
            
            self.conn.rollback()
            return False
    
    def update_player_names(self, asset_id: int, first_name: str, last_name: str):
        """Update first_name and last_name for a specific player by asset_id"""
        try:
            update_query = """
            UPDATE players
            SET first_name = %s, last_name = %s, updated_at = CURRENT_TIMESTAMP
            WHERE asset_id = %s
            """
            self.cursor.execute(update_query, (first_name, last_name, asset_id))
            return self.cursor.rowcount > 0
        except Exception as e:
            print(f"Failed to update player names for asset_id {asset_id}: {e}")
            self.conn.rollback()
            return False
    
    def close(self):
        """Close database connection"""
        if self.cursor:
            self.cursor.close()
        if self.conn:
            self.conn.close()
