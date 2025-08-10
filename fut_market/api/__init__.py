"""Main API configuration using Django Ninja."""

from ninja import NinjaAPI

from auth_api.api import router as auth_router
from club.api import router as club_router
from market.api import router as market_router
from players.api import router as players_router

api = NinjaAPI(
    title="FIFA Ultimate Team API",
    version="2.0.0",
    description="Django-based FIFA Ultimate Team web API server"
)

# Register routers
api.add_router("/auth/", auth_router, tags=["Authentication"])
api.add_router("/market/", market_router, tags=["Market"])
api.add_router("/club/", club_router, tags=["Club"])
api.add_router("/players/", players_router, tags=["Players"])
