from fastapi import APIRouter, Request

from ml import config

from backend import deps, schemas

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health", response_model=schemas.HealthResponse)
def health(request: Request):
    """Never 503s -- this is what you call to find out WHY things are down."""
    state: deps.AppState = request.app.state.aml
    neo = deps.neo4j_status()

    if state.load_error:
        status = "error"
    elif not state.ready or not neo.reachable:
        status = "degraded"
    else:
        status = "ok"

    ts = state.X["timestamp"] if state.ready else None
    return schemas.HealthResponse(
        status=status,
        model_loaded=state.ready,
        load_error=state.load_error,
        anomaly_model_loaded=state.iforest is not None,
        anomaly_model_error=state.iforest_error,
        neo4j=neo,
        llm_configured=bool(config.gemini_key()) and config.gemini_key() != "your_key_here",
        rows_scored=len(state.X) if state.ready else 0,
        rows_total=state.rows_total,
        period_start=ts.min().to_pydatetime() if ts is not None else None,
        period_end=ts.max().to_pydatetime() if ts is not None else None,
        uptime_seconds=round(state.uptime, 1),
    )
