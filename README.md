# FIFA Ultimate Team Server

A Python web server providing RESTful API access to EA's FIFA Ultimate Team web services.

## Features

- **Authentication**: Login with two-factor authentication support
- **Transfer Market**: Search players, place bids, buy items
- **Club Management**: View credits, watchlist, and inventory
- **Session Management**: Cookie-based session persistence
- **Modern API**: Django with Django Ninja for high-performance REST APIs

## Installation

This project uses `uv` for package management:

```bash
uv sync
```

## Database Setup

This project requires PostgreSQL. Start the database using Docker Compose:

```bash
docker-compose up -d
```

Run database migrations:

```bash
# Apply all migrations
uv run python manage.py migrate

# Create migrations after model changes
uv run python manage.py makemigrations
```

## Running the Server

Start the development server:

```bash
uv run python manage.py runserver 8010
```

The API will be available at `http://localhost:8010` with interactive documentation at `http://localhost:8010/api/docs`.

## Running Tests

Run all tests:

```bash
# Run all tests
uv run python manage.py test

# Run tests for specific apps
uv run python manage.py test auth_api
uv run python manage.py test market
uv run python manage.py test club

# Run with verbose output
uv run python manage.py test --verbosity=2

# Keep test database between runs (faster for repeated testing)
uv run python manage.py test --keepdb
```

## API Endpoints

### Authentication
- `POST /api/auth/login` - Login with credentials
- `POST /api/auth/login-with-2fa` - Login with two-factor authentication

### Transfer Market
- `POST /api/market/search` - Search for players on transfer market
- `POST /api/market/bid` - Place a bid on an auction
- `POST /api/market/buy-now/{trade_id}` - Buy item immediately at buy-now price
- `GET /api/market/watchlist` - Get user's watchlist items
- `POST /api/market/watchlist/{trade_id}` - Add item to watchlist
- `DELETE /api/market/watchlist/{trade_id}` - Remove item from watchlist
- `GET /api/market/tradepile` - Get trade pile items
- `DELETE /api/market/tradepile/{trade_id}` - Remove item from trade pile
- `GET /api/market/trade-status` - Get trade status for active auctions
- `POST /api/market/relist` - Relist all items in trade pile

### Club Management
- `GET /api/club/credits` - Get current credit balance and packs
- `GET /api/club/player-items` - Get all player items in club
- `GET /api/club/squads` - Get user's squad list
- `GET /api/club/items` - Get club items
- `DELETE /api/club/items/{item_id}/quick-sell` - Quick sell an item
- `POST /api/club/items/{item_id}/send-to-club` - Send item to club
- `POST /api/club/items/{item_id}/send-to-tradepile` - Send item to trade pile

## Example Usage with curl

### Login
```bash
curl -X POST "http://localhost:8010/api/auth/login" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "your.email@example.com",
    "password": "yourpassword",
    "platform": "ps5",
    "app_version": "WebApp",
    "secret_answer": "your_secret_answer",
    "x_ut_sid": "45542323-24ea-4619-a5c6-cb8f314c3137"
  }'
```

### Search Players (requires X-UT-SID header)
```bash
curl -X POST "http://localhost:8010/api/market/search" \
  -H "Content-Type: application/json" \
  -H "x-ut-sid: 45542323-24ea-4619-a5c6-cb8f314c3137" \
  -d '{
    "type": "player",
    "page": 0,
    "position": "ST",
    "max_price": 100000,
    "min_buy_now": 50000
  }'
```

### Place Bid (requires X-UT-SID header)
```bash
curl -X POST "http://localhost:8010/api/market/bid" \
  -H "Content-Type: application/json" \
  -H "x-ut-sid: 45542323-24ea-4619-a5c6-cb8f314c3137" \
  -d '{
    "trade_id": 123456789,
    "bid_amount": 75000
  }'
```

### Get Trade Pile (requires X-UT-SID header)
```bash
curl -X GET "http://localhost:8010/api/market/tradepile" \
  -H "x-ut-sid: 45542323-24ea-4619-a5c6-cb8f314c3137"
```

### Get Club Items (requires X-UT-SID header)
```bash
curl -X GET "http://localhost:8010/api/club/items" \
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

The project uses `ruff` for linting and formatting:

```bash
# Linting with auto-fix
uv run ruff check . --fix

# Code formatting
uv run ruff format .
```

## Architecture

- `auth_api/` - Authentication app with login endpoints
- `market/` - Transfer market functionality
- `club/` - Club management endpoints
- `players/` - Player data management
- `core/` - Shared models and utilities
- `fut_market/` - Django project settings
- `manage.py` - Django management command entry point