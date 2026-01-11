"""API v1 router - combines all endpoint routers."""

from fastapi import APIRouter

from app.api.v1.endpoints import events, fighters, fights, predictions

api_router = APIRouter()

# Include all endpoint routers
api_router.include_router(events.router)
api_router.include_router(fighters.router)
api_router.include_router(fights.router)
api_router.include_router(predictions.router)
