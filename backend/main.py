"""FastAPI entry point.

    uvicorn backend.main:app --reload --port 8000

Startup loads the pipeline once (see deps.load_state). A failed load
does NOT crash the server: /api/health reports the error and every
other endpoint returns 503, so the frontend can show what went wrong.
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from neo4j import exceptions as neo4j_exc

from ml import config

from backend import deps
from backend.routers import accounts, alerts, ask, health, predict, stats, transactions

log = config.get_logger("backend")

ORIGINS = ["http://localhost:5173", "http://127.0.0.1:5173"]


@asynccontextmanager
async def lifespan(app: FastAPI):
    state = deps.AppState()
    app.state.aml = state
    log.info("loading pipeline (this takes about a minute) ...")
    try:
        deps.load_state(state)
    except deps.StartupError as e:
        state.load_error = str(e)
        log.error("startup: %s", e)
    except Exception as e:                       # anything unexpected
        state.load_error = f"{type(e).__name__}: {e}"
        log.exception("startup failed")
    neo = deps.neo4j_status()
    if neo.reachable:
        log.info("neo4j reachable at %s (%.0f ms)", neo.uri, neo.latency_ms)
    else:
        log.warning("neo4j NOT reachable: %s -- graph endpoints will 503", neo.error)
    yield
    state.executor.shutdown(wait=False, cancel_futures=True)


app = FastAPI(title="AML Detection API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(stats.router)
app.include_router(alerts.router)
app.include_router(accounts.router)
app.include_router(transactions.router)
app.include_router(predict.router)
app.include_router(ask.router)


async def _neo4j_handler(request: Request, exc: Exception):
    """Catches graph failures that escape a router."""
    e = deps.neo4j_unavailable(exc)
    return JSONResponse(status_code=e.status_code, content={"detail": e.detail})


for _cls in (neo4j_exc.DriverError, neo4j_exc.Neo4jError):
    app.add_exception_handler(_cls, _neo4j_handler)


@app.exception_handler(Exception)
async def _unhandled(request: Request, exc: Exception):
    log.exception("unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500,
                        content={"detail": f"{type(exc).__name__}: {exc}"})
