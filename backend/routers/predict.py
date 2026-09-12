"""Score on demand.

Two modes:
  txn_ids  -> look up rows already scored at startup (cheap, exact)
  features -> one ad-hoc feature row through the same xgb + rules +
              iforest path. Band comes from the row's percentile against
              the test-period score distribution, so it means the same
              thing as the queue's band.
"""
import numpy as np
import pandas as pd
from fastapi import APIRouter, Depends, HTTPException

from ml.features import build
from ml.models import fusion, iforest
from ml.models import rules as rules_mod
from ml.models import xgb as xgbm

from backend import deps, schemas
from backend.deps import native

router = APIRouter(prefix="/api", tags=["predict"])


def _band(pct: float, fired: list[str]) -> tuple[str, str]:
    b = fusion.BANDS
    band = ("HIGH" if pct >= b["HIGH"] else "MEDIUM" if pct >= b["MEDIUM"]
            else "LOW" if pct >= b["LOW"] else "CLEAR")
    if len(set(fired) & fusion.ESCALATING) >= fusion.ESCALATE_MIN:
        band = {"MEDIUM": "HIGH", "LOW": "MEDIUM"}.get(band, band)
    action = {"HIGH": "REPORT", "MEDIUM": "REVIEW", "LOW": "MONITOR", "CLEAR": "NONE"}[band]
    return band, action


def _scored(state: deps.AppState, txn_id: int) -> schemas.Prediction | None:
    try:
        idx = state.txn_index.at[txn_id]
    except KeyError:
        return None
    f = state.fused.loc[idx]
    fired = [c for c in rules_mod.DESCRIPTIONS if c in f.index and bool(f[c])]
    return schemas.Prediction(
        txn_id=txn_id, model_score=float(f["model_score"]),
        model_pct=float(f["model_pct"]), anomaly_pct=native(f.get("anomaly_pct")),
        band=f["band"], action=f["action"], rules_fired=fired,
        n_rules=int(f["n_rules"]), source="scored")


def _ad_hoc(state: deps.AppState, features: dict) -> schemas.Prediction:
    X = state.X
    allowed = set(build.feature_columns(X))
    unknown = [k for k in features if k not in allowed]
    if unknown:
        raise HTTPException(422, f"not feature columns: {unknown[:10]}")
    missing = [c for c in state.cols if c not in features]
    if len(missing) > len(state.cols) // 2:
        raise HTTPException(422, f"too few features supplied; missing e.g. {missing[:8]}")

    # Unsupplied columns stay NaN -- xgboost routes missing values natively.
    row = pd.DataFrame([features]).reindex(columns=X.columns)
    for c in features:               # match training dtypes, esp. categoricals
        if features[c] is None:
            continue
        try:
            row[c] = row[c].astype(X[c].dtype)
        except (ValueError, TypeError):
            raise HTTPException(422, f"bad value for {c}: {features[c]!r}")

    p = float(xgbm.predict(state.model, row[state.cols])[0])
    pct = float(np.searchsorted(state.score_ref, p, side="right") / len(state.score_ref) * 100)

    r = rules_mod.evaluate(row).iloc[0]
    fired = [c for c in rules_mod.DESCRIPTIONS if bool(r[c])]
    band, action = _band(pct, fired)

    anomaly = None
    if state.iforest is not None:
        anomaly = float(iforest.score(state.iforest, row)[0] * 100)

    return schemas.Prediction(
        model_score=p, model_pct=round(pct, 3), anomaly_pct=anomaly,
        band=band, action=action, rules_fired=fired, n_rules=len(fired),
        source="ad_hoc")


@router.post("/predict", response_model=schemas.PredictResponse)
def predict(req: schemas.PredictRequest,
            state: deps.AppState = Depends(deps.get_state)):
    if (req.txn_ids is None) == (req.features is None):
        raise HTTPException(422, "provide exactly one of txn_ids or features")

    if req.features is not None:
        return schemas.PredictResponse(predictions=[_ad_hoc(state, req.features)])

    preds, missing = [], []
    for t in req.txn_ids:
        p = _scored(state, t)
        (preds if p else missing).append(p if p else t)
    return schemas.PredictResponse(predictions=preds, missing=missing)
