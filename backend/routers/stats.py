from fastapi import APIRouter, Depends

from backend import deps, schemas

router = APIRouter(prefix="/api", tags=["stats"])


@router.get("/stats", response_model=schemas.StatsResponse)
def stats(state: deps.AppState = Depends(deps.get_state)):
    """Precomputed at startup; the scored set never changes at runtime."""
    return state.stats
