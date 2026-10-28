"""Vision routes — placeholder for Phase 5."""
from fastapi import APIRouter

router = APIRouter(prefix="/api", tags=["vision"])


@router.post("/vision/analyze")
async def analyze():
    return {"error": "Vision not yet available (Phase 5)."}
