from fastapi import APIRouter
from app.api.v1 import planner, analytics

router = APIRouter()

# Registering the sub-routers
router.include_router(planner.router, prefix="/planner", tags=["Planning"])
router.include_router(analytics.router, prefix="/analytics", tags=["Analytics"])