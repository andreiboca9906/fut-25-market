"""FastAPI application entry point."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routers import auth, club, market

app = FastAPI(title="FIFA Ultimate Team API", description="FIFA Ultimate Team web API server", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(market.router)
app.include_router(club.router)


@app.get("/")
async def root():
    """Root endpoint."""
    return {"message": "FIFA Ultimate Team API", "version": "1.0.0", "docs": "/docs"}


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8010, reload=True)
