"""Unsupervised anomaly model. Gets numeric behavioral features only.

Role: EVIDENCE, not ranking. Rules-only and IF-only both rank far worse
than XGBoost on PR-AUC, so the anomaly score never moves a band. It
answers a different question for the investigator -- "is this account's
behaviour unusual regardless of what the label says" -- which matters
precisely when a typology the supervised model never saw shows up.

Score is converted to a 0->1 percentile against the training
distribution so it reads the same way as model_pct.
"""
import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest

from ml import config

log = config.get_logger("models.iforest")

MODEL_PATH = config.MODELS / "iforest.joblib"

# Fit on a sample: IsolationForest is O(n) at predict but the fit on 3.5M
# rows is pointless -- 256-sample trees saturate long before that.
FIT_SAMPLE = 500_000


def train(X_tr: pd.DataFrame, cols: list[str], seed: int = 0) -> dict:
    Xs = X_tr[cols]
    if len(Xs) > FIT_SAMPLE:
        Xs = Xs.sample(FIT_SAMPLE, random_state=seed)
    Xs = Xs.fillna(0.0).astype("float32")

    log.info("fitting on %s rows x %d behavioral features", f"{len(Xs):,}", len(cols))
    model = IsolationForest(
        n_estimators=200, max_samples=256, contamination="auto",
        n_jobs=-1, random_state=seed,
    )
    model.fit(Xs)

    # Reference distribution for the percentile transform. Higher raw
    # value = more anomalous, so negate sklearn's "normality" score.
    raw = -model.score_samples(Xs)
    ref = np.sort(raw)
    return {"model": model, "cols": cols, "ref": ref}


def score(bundle: dict, X: pd.DataFrame) -> np.ndarray:
    """0 -> 1, fraction of the training sample less anomalous than this row."""
    Xs = X[bundle["cols"]].fillna(0.0).astype("float32")
    raw = -bundle["model"].score_samples(Xs)
    return np.searchsorted(bundle["ref"], raw, side="right") / len(bundle["ref"])


def save(bundle: dict) -> None:
    joblib.dump(bundle, MODEL_PATH)
    log.info("saved %s", MODEL_PATH.name)


def load() -> dict:
    if not MODEL_PATH.exists():
        raise FileNotFoundError("run: python -m ml.scripts.train_iforest")
    return joblib.load(MODEL_PATH)
