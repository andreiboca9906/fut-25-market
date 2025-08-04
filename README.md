# FIFA Ultimate Team Server

A Python web server providing RESTful API access to EA's FIFA Ultimate Team web services.

## Features

- **Authentication**: Login with two-factor authentication support
- **Transfer Market**: Search players, place bids, buy items
- **Club Management**: View credits, watchlist, and inventory
- **Session Management**: Cookie-based session persistence
- **Modern API**: FastAPI with automatic OpenAPI documentation

## Installation

This project uses `uv` for package management:

```bash
uv sync
```

## Development Setup (Mandatory)

**All developers must set up git hooks before making any commits:**

Option 1 - Quick setup with script:
```bash
./scripts/setup_dev.sh
```

Option 2 - Manual setup:
```bash
# Install dependencies
uv sync

# Install git hooks (REQUIRED)
./scripts/setup_dev.sh
```

The git hooks will automatically:
- Run `ruff check --fix` to lint and auto-fix issues
- Run `ruff format` to format code consistently

**This setup is mandatory for all contributors.** Your commits will be rejected if the hooks are not installed and passing.

## Running the Server

Start the development server:

```bash
uv run python main.py
```

The API will be available at `http://localhost:8010` with interactive documentation at `http://localhost:8010/docs`.

## API Endpoints

### Authentication
- `POST /auth/login` - Login with credentials
- `POST /auth/login-with-2fa` - Login with two-factor authentication

### Transfer Market
- `POST /market/search` - Search for players on transfer market
- `POST /market/bid` - Place a bid on an auction
- `POST /market/buy-now/{trade_id}` - Buy item immediately at buy-now price
- `GET /market/watchlist` - Get user's watchlist items
- `POST /market/watchlist/{trade_id}` - Add item to watchlist
- `DELETE /market/watchlist/{trade_id}` - Remove item from watchlist
- `GET /market/tradepile` - Get trade pile items
- `DELETE /market/tradepile/{trade_id}` - Remove item from trade pile
- `GET /market/trade-status` - Get trade status for active auctions
- `POST /market/relist` - Relist all items in trade pile

### Club Management
- `GET /club/credits` - Get current credit balance and packs
- `GET /club/players` - Get all players and legends list
- `GET /club/squads` - Get user's squad list
- `GET /club/items` - Get club items
- `DELETE /club/items/{item_id}/quick-sell` - Quick sell an item
- `POST /club/items/{item_id}/send-to-club` - Send item to club
- `POST /club/items/{item_id}/send-to-tradepile` - Send item to trade pile

## Example Usage

### Login
```bash
curl -X POST "http://localhost:8010/auth/login" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "your.email@example.com",
    "password": "yourpassword",
    "platform": "ps5",
    "x_ut_sid": "45542323-24ea-4619-a5c6-cb8f314c3137"
  }'
```

### Search Players (requires X-UT-SID header)
```bash
curl -X POST "http://localhost:8010/market/search" \
  -H "Content-Type: application/json" \
  -H "x-ut-sid: 45542323-24ea-4619-a5c6-cb8f314c3137" \
  -d '{
    "page": 1,
    "position": "ST",
    "max_price": 100000,
    "min_buy": 50000
  }'
```

### Place Bid (requires X-UT-SID header)
```bash
curl -X POST "http://localhost:8010/market/bid" \
  -H "Content-Type: application/json" \
  -H "x-ut-sid: 45542323-24ea-4619-a5c6-cb8f314c3137" \
  -d '{
    "trade_id": 123456789,
    "bid_amount": 75000
  }'
```

### Get Trade Pile (requires X-UT-SID header)
```bash
curl -X GET "http://localhost:8010/market/tradepile" \
  -H "x-ut-sid: 45542323-24ea-4619-a5c6-cb8f314c3137"
```

### Get Club Items (requires X-UT-SID header)
```bash
curl -X GET "http://localhost:8010/club/items" \
  -H "x-ut-sid: 45542323-24ea-4619-a5c6-cb8f314c3137"
```

## Session Management

Most endpoints require the `X-UT-SID` header containing your session ID. This header:

- **Authenticates requests** - Without it, you'll get 401 Unauthorized errors
- **Identifies your session** - Links requests to your EA account session  
- **Rotates user agents** - Automatically varies browser fingerprints for better security
- **Uses EA-compliant headers** - Mimics official web app requests

The session ID can be obtained through the login process or external authentication methods.

## Development

The project uses `ruff` for linting and formatting. Git hooks automatically run these tools on every commit:

```bash
# Manual linting (hooks do this automatically)
uv run ruff check . --fix
uv run ruff format .
```

Run tests with:

```bash
uv run pytest
```

## Architecture

- `fut_toolkit/` - Core FIFA Ultimate Team API client
- `api/` - FastAPI web server and routes  
- `main.py` - Application entry point