## Goal
Migrate current project to Django ORM with TimescaleDB support for handling player prices and history.

## How?
Use postgres mcp to connect and view current database structure. It just has players table for now,
Use context7 mcp for upto date docs for TimescaleDB and Django ORM integration and framework details.


## DB Structure
1. `players` table already exists and contains one row per FIFA player (`players.id` = EA/FIFA player id). 
2. id and resource_id in `players` table are the same. It represents unique card/item of that player. 
3. asset_id is unique id of a player that may have multiple cards/items.

Refer the below SQL for migration files. Use drizzle to handle migrations.

```sql
-- 1) Enable TimescaleDB extension (run as a superuser once per database)
CREATE EXTENSION IF NOT EXISTS timescaledb;

-- 2) Current price snapshot table (latest known minimum buy-now price)
CREATE TABLE IF NOT EXISTS player_prices (
    player_id    INT NOT NULL REFERENCES players(player_id) ON DELETE CASCADE,
    platform     TEXT NOT NULL,                -- e.g. 'PS', 'XBOX', 'PC'
    current_price NUMERIC(12,2) NOT NULL,     -- use NUMERIC for money/coins
    currency     CHAR(3) NOT NULL DEFAULT 'COINS',
    last_updated TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (player_id, platform)
);

-- 3) Full history (time-series) table
CREATE TABLE IF NOT EXISTS player_price_history (
    history_id   BIGSERIAL PRIMARY KEY,
    player_id    INT NOT NULL REFERENCES players(player_id) ON DELETE CASCADE,
    platform     TEXT NOT NULL,
    price        NUMERIC(12,2) NOT NULL,
    currency     CHAR(3) NOT NULL DEFAULT 'COINS',
    fetched_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Convert to a TimescaleDB hypertable (fast time-series performance)
SELECT create_hypertable('player_price_history', 'fetched_at', if_not_exists => TRUE);

-- Indexes to speed common queries (get recent history per player/platform)
CREATE INDEX IF NOT EXISTS idx_price_history_player_platform_time
  ON player_price_history (player_id, platform, fetched_at DESC);

-- 4) Example upsert + history insert pattern (use parameterized queries from your script)
-- Run inside a transaction in your client to keep atomicity for each observation.
BEGIN;

-- Upsert the current (latest) price snapshot
INSERT INTO player_prices (player_id, platform, current_price, currency, last_updated)
VALUES ($1, $2, $3, 'COINS', now())
ON CONFLICT (player_id, platform) DO UPDATE
  SET current_price = EXCLUDED.current_price,
      currency = EXCLUDED.currency,
      last_updated = EXCLUDED.last_updated;

-- Append the observed price to history
INSERT INTO player_price_history (player_id, platform, price, currency, fetched_at)
VALUES ($1, $2, $3, 'COINS', now());

COMMIT;

-- 5) Example with literal values (quick test)
BEGIN;
INSERT INTO player_prices (player_id, platform, current_price, currency, last_updated)
VALUES (12345, 'PS', 2500, 'COINS', now())
ON CONFLICT (player_id, platform) DO UPDATE
  SET current_price = EXCLUDED.current_price,
      currency = EXCLUDED.currency,
      last_updated = EXCLUDED.last_updated;

INSERT INTO player_price_history (player_id, platform, price, currency, fetched_at)
VALUES (12345, 'PS', 2500, 'COINS', now());
COMMIT;
```