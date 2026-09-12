"""Startup state: everything expensive is loaded exactly once here.

The feature matrix is ~2GB and fuse() takes ~30s, so nothing in this
file may run per request. Routers get the state through get_state(),
which returns 503 until loading has finished (or if it failed).
"""
import gc
import math
import threading
from collections import OrderedDict
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime

import numpy as np
import pandas as pd
from fastapi import HTTPException, Request
from neo4j import GraphDatabase
from neo4j import exceptions as neo4j_exc

from ml import config, explain
from ml.agent.tools import ToolBox
from ml.features import build
from ml.models import fusion, iforest
from ml.models import xgb as xgbm

from backend import schemas

log = config.get_logger("backend.deps")

TEST_QUANTILE = 0.85
RAW_PATH = config.DATA_PROCESSED / "transactions_clean.parquet"

BAND_RANK = {"CLEAR": 0, "LOW": 1, "MEDIUM": 2, "HIGH": 3}
RANK_BAND = {v: k for k, v in BAND_RANK.items()}

# Anything the Neo4j driver raises when the server is down, refuses
# auth, or the query fails. Routers translate these into 503.
NEO4J_ERRORS = (neo4j_exc.DriverError, neo4j_exc.Neo4jError, OSError)


class StartupError(RuntimeError):
    """A required artefact is missing or unusable."""


# --- investigation jobs -----------------------------------------------------
@dataclass
class Job:
    job_id: str
    txn_id: int
    status: str = "queued"
    narrative: str | None = None
    evidence: dict | None = None
    error: str | None = None
    started_at: datetime = field(default_factory=datetime.now)
    finished_at: datetime | None = None


@dataclass
class AskJob:
    job_id: str
    question: str
    context: dict
    status: str = "queued"
    answer: str | None = None
    trace: list = field(default_factory=list)
    rounds: int | None = None
    error: str | None = None
    started_at: datetime = field(default_factory=datetime.now)
    finished_at: datetime | None = None


@dataclass
class AppState:
    started_at: float = field(default_factory=time.time)
    ready: bool = False
    load_error: str | None = None

    X: pd.DataFrame | None = None            # test-period feature matrix
    raw: pd.DataFrame | None = None          # transactions_clean (full)
    fused: pd.DataFrame | None = None
    model: object = None
    cols: list[str] | None = None
    iforest: dict | None = None             # None = model file absent
    iforest_error: str | None = None
    score_ref: np.ndarray | None = None     # sorted test-period model scores, for /predict percentiles
    explainer: object = None
    tools: ToolBox | None = None

    alerts: pd.DataFrame | None = None       # list view, same index as X
    txn_index: pd.Series | None = None       # txn_id -> X.index
    raw_index: pd.Series | None = None       # txn_id -> raw.index
    account_risk: pd.DataFrame | None = None # account -> worst band etc.
    stats: schemas.StatsResponse | None = None
    rows_total: int = 0

    # find_cycles() in ml.graph.queries can take ~30s on a busy account,
    # so graph-backed responses are memoised (bounded, insertion-evicted).
    cache: "OrderedDict[tuple, object]" = field(default_factory=OrderedDict)
    cache_lock: threading.Lock = field(default_factory=threading.Lock)

    jobs: dict[int, Job] = field(default_factory=dict)
    ask_jobs: "OrderedDict[str, AskJob]" = field(default_factory=OrderedDict)
    jobs_lock: threading.Lock = field(default_factory=threading.Lock)
    executor: ThreadPoolExecutor = field(
        default_factory=lambda: ThreadPoolExecutor(max_workers=2,
                                                   thread_name_prefix="investigate"))

    @property
    def uptime(self) -> float:
        return time.time() - self.started_at

    def cached(self, key: tuple):
        with self.cache_lock:
            return self.cache.get(key)

    def remember(self, key: tuple, value, max_items: int = 512):
        with self.cache_lock:
            self.cache[key] = value
            while len(self.cache) > max_items:
                self.cache.popitem(last=False)


# --- loading ----------------------------------------------------------------
def load_state(state: AppState) -> None:
    """Populate `state` in place. Raises StartupError on missing artefacts."""
    missing = [p for p in (xgbm.MODEL_PATH, xgbm.COLS_PATH, RAW_PATH)
               if not p.exists()]
    if missing:
        raise StartupError("missing artefacts: " + ", ".join(map(str, missing))
                           + " -- run ml.scripts.build_features then "
                             "ml.scripts.train")

    t0 = time.perf_counter()
    try:
        X_all = build.load()          # raises FileNotFoundError with a hint
    except FileNotFoundError as e:
        raise StartupError(str(e)) from e
    state.rows_total = len(X_all)

    cutoff = X_all["timestamp"].quantile(TEST_QUANTILE)
    X = X_all[X_all["timestamp"] > cutoff].copy()
    del X_all
    gc.collect()
    log.info("test period: %s rows after %s  (%.1fs)",
             f"{len(X):,}", cutoff, time.perf_counter() - t0)

    raw = pd.read_parquet(RAW_PATH)

    try:
        model, cols = xgbm.load()
    except Exception as e:            # corrupt json, xgboost version drift
        raise StartupError(f"could not load model: {e}") from e
    absent = [c for c in cols if c not in X.columns]
    if absent:
        raise StartupError(f"feature matrix lacks model columns: {absent[:5]}")

    t1 = time.perf_counter()
    fused = fusion.fuse(X, xgbm.predict(model, X[cols]))
    log.info("scored + fused in %.1fs", time.perf_counter() - t1)

    # Anomaly model is optional: it is evidence, so a missing file must
    # not take the queue down.
    try:
        bundle = iforest.load()
        fused = fusion.with_anomaly(fused, iforest.score(bundle, X))
        state.iforest = bundle
    except FileNotFoundError as e:
        state.iforest_error = str(e)
        log.warning("isolation forest not loaded: %s", e)
    except Exception as e:
        state.iforest_error = f"{type(e).__name__}: {e}"
        log.warning("isolation forest failed: %s", e)

    explainer = explain.make_explainer(model)

    state.X, state.raw, state.fused = X, raw, fused
    state.score_ref = np.sort(fused["model_score"].to_numpy())
    state.model, state.cols, state.explainer = model, cols, explainer
    state.tools = ToolBox(X, raw, fused, model, cols, explainer)

    state.txn_index = pd.Series(X.index, index=X["txn_id"].values)
    state.raw_index = pd.Series(raw.index, index=raw["txn_id"].values)
    state.alerts = _alert_frame(X, fused)
    state.account_risk = _account_risk(state.alerts)
    state.stats = _stats(state.alerts)
    state.ready = True
    log.info("ready in %.1fs", time.perf_counter() - t0)


def _alert_frame(X: pd.DataFrame, fused: pd.DataFrame) -> pd.DataFrame:
    a = X[["txn_id", "from_id", "to_id", "amount_usd", "timestamp",
           "is_laundering"]].copy()
    for c in ("risk_score", "band", "action", "n_rules", "escalated",
              "model_pct", "anomaly_pct"):
        if c in fused.columns:
            a[c] = fused[c].values
    a["date"] = a["timestamp"].dt.date
    return a


def _account_risk(a: pd.DataFrame) -> pd.DataFrame:
    cols = ["risk_score", "band"]
    long = pd.concat([
        a[["from_id"] + cols].rename(columns={"from_id": "account"}),
        a[["to_id"] + cols].rename(columns={"to_id": "account"}),
    ])
    long["rank"] = long["band"].map(BAND_RANK)
    long["is_alert"] = long["rank"] > 0
    g = long.groupby("account").agg(
        n_scored_txns=("risk_score", "size"),
        n_alerts=("is_alert", "sum"),
        max_risk_score=("risk_score", "max"),
        worst_rank=("rank", "max"))
    g["worst_band"] = g["worst_rank"].map(RANK_BAND)
    return g.drop(columns="worst_rank")


def _stats(a: pd.DataFrame) -> schemas.StatsResponse:
    n = len(a)
    pos = int(a["is_laundering"].sum())
    bands = []
    for band in ("HIGH", "MEDIUM", "LOW", "CLEAR"):
        m = a["band"] == band
        c = int(m.sum())
        p = int(a.loc[m, "is_laundering"].sum())
        bands.append(schemas.BandStat(
            band=band, count=c, share=c / n if n else 0.0, positives=p,
            precision=(p / c) if c else None))

    alerts = a[a["band"] != "CLEAR"]
    daily = (alerts.groupby(["date", "band"]).size().unstack(fill_value=0)
             .reindex(columns=["HIGH", "MEDIUM", "LOW"], fill_value=0))
    daily["total"] = daily.sum(axis=1)
    daily_rows = [schemas.DailyVolume(date=d, **{k: int(v) for k, v in r.items()})
                  for d, r in daily.sort_index().iterrows()]

    return schemas.StatsResponse(
        rows_scored=n, n_positives=pos, base_rate=pos / n if n else 0.0,
        alert_count=len(alerts),
        period_start=a["timestamp"].min().to_pydatetime(),
        period_end=a["timestamp"].max().to_pydatetime(),
        bands=bands, daily_alerts=daily_rows)


# --- neo4j ------------------------------------------------------------------
def neo4j_status(timeout: float = 3.0) -> schemas.Neo4jStatus:
    """Cheap connectivity probe with a short timeout, for /health and for
    failing fast before queueing an investigation."""
    uri = config.neo4j_uri()
    t0 = time.perf_counter()
    try:
        with GraphDatabase.driver(
                uri, auth=(config.neo4j_user(), config.neo4j_password()),
                connection_timeout=timeout) as d:
            d.verify_connectivity()
        return schemas.Neo4jStatus(
            reachable=True, uri=uri,
            latency_ms=round((time.perf_counter() - t0) * 1000, 1))
    except Exception as e:
        return schemas.Neo4jStatus(reachable=False, uri=uri,
                                   error=f"{type(e).__name__}: {e}")


def neo4j_unavailable(e: Exception) -> HTTPException:
    return HTTPException(
        status_code=503,
        detail=f"Neo4j unavailable at {config.neo4j_uri()}: "
               f"{type(e).__name__}: {e}")


# --- request dependency -----------------------------------------------------
def get_state(request: Request) -> AppState:
    state: AppState = request.app.state.aml
    if state.ready:
        return state
    if state.load_error:
        raise HTTPException(
            status_code=503,
            detail=f"pipeline failed to load: {state.load_error}")
    raise HTTPException(status_code=503, detail="pipeline still loading")


# --- serialisation helpers --------------------------------------------------
def native(v):
    """numpy / pandas scalar -> plain Python, NaN/NaT -> None."""
    if v is None or v is pd.NaT:
        return None
    if isinstance(v, pd.Timestamp):
        return v.to_pydatetime()
    if isinstance(v, np.generic):
        v = v.item()
    if isinstance(v, float) and math.isnan(v):
        return None
    return v


def deep_native(obj):
    """Recursively apply native() -- for tool evidence dicts."""
    if isinstance(obj, dict):
        return {str(k): deep_native(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [deep_native(v) for v in obj]
    if isinstance(obj, pd.DataFrame):
        return records(obj)
    return native(obj)


def records(df: pd.DataFrame) -> list[dict]:
    return [{k: native(v) for k, v in r.items()} for r in df.to_dict("records")]


def new_job_id() -> str:
    return uuid.uuid4().hex[:12]
