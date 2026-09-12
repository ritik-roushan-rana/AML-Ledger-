"""Supervised model. Gets the full feature matrix.

Trained with scale_pos_weight ~= 980 (the imbalance ratio), evaluated on
PR-AUC and precision@k. Accuracy is meaningless at 0.1% positives.
"""
import json

import numpy as np
import pandas as pd
import xgboost as xgb

from ml import config
from ml.features import build

log = config.get_logger("models.xgb")

MODEL_PATH = config.MODELS / "xgb.json"
COLS_PATH = config.MODELS / "xgb_columns.json"


def train(X_tr, y_tr, X_va, y_va, params: dict | None = None):
    ratio = float((y_tr == 0).sum() / max((y_tr == 1).sum(), 1))
    p = {
        "objective": "binary:logistic",
        "eval_metric": "aucpr",
        "max_depth": 6,
        "learning_rate": 0.05,
        "subsample": 0.8,
        "colsample_bytree": 0.8,
        "min_child_weight": 5,
        "scale_pos_weight": ratio,
        "tree_method": "hist",
        "n_jobs": -1,
    }
    if params:
        p.update(params)

    log.info("training on %s rows, %s positives, scale_pos_weight=%.0f",
             f"{len(X_tr):,}", f"{int(y_tr.sum()):,}", ratio)

    dtr = xgb.DMatrix(X_tr, y_tr, enable_categorical=True)
    dva = xgb.DMatrix(X_va, y_va, enable_categorical=True)

    model = xgb.train(
        p, dtr, num_boost_round=1500,
        evals=[(dtr, "train"), (dva, "val")],
        early_stopping_rounds=80, verbose_eval=50,
    )
    log.info("best iteration %d, val aucpr %.4f",
             model.best_iteration, model.best_score)
    return model


def predict(model, X) -> np.ndarray:
    d = xgb.DMatrix(X, enable_categorical=True)
    return model.predict(d, iteration_range=(0, model.best_iteration + 1))


def save(model, columns: list[str]) -> None:
    model.save_model(MODEL_PATH)
    COLS_PATH.write_text(json.dumps(columns))
    log.info("saved %s", MODEL_PATH.name)


def load():
    model = xgb.Booster()
    model.load_model(MODEL_PATH)
    return model, json.loads(COLS_PATH.read_text())


def importance(model, top: int = 25) -> pd.Series:
    g = model.get_score(importance_type="gain")
    return pd.Series(g).sort_values(ascending=False).head(top)