"""Assemble the full feature matrix from all three families.

Importable by both the CLI script and (later) the backend, so scoring a
single live transaction uses exactly the same code path as training.
"""
import pandas as pd

from ml import config
from ml.features import behavioral, graph, transaction

log = config.get_logger("features.build")

ID_COLS = ["txn_id", "from_id", "to_id", "timestamp"]
LABEL_COL = "is_laundering"

GRAPH_BUCKET_HOURS = 24


def build_matrix(df: pd.DataFrame, with_graph: bool = True) -> pd.DataFrame:
    """Transactions in -> features + ids + label out."""
    parts, meta = [], {}

    tx = transaction.build(df)
    parts.append(tx)
    meta["transaction"] = tx.shape[1]

    bh = behavioral.build(df).reindex(df.index)
    parts.append(bh)
    meta["behavioral"] = bh.shape[1]

    if with_graph:
        gr = graph.build(df, bucket_hours=GRAPH_BUCKET_HOURS).reindex(df.index)
        parts.append(gr)
        meta["graph"] = gr.shape[1]

    X = pd.concat(parts, axis=1)

    for c in ID_COLS:
        X[c] = df[c].values
    X[LABEL_COL] = df[LABEL_COL].values

    log.info("matrix: %s rows x %d features %s",
             f"{len(X):,}", sum(meta.values()), meta)
    return X


def feature_columns(X: pd.DataFrame) -> list[str]:
    """Everything that is NOT an id or the label. Use this, never X.columns."""
    return [c for c in X.columns if c not in ID_COLS + [LABEL_COL]]


def split_by_family(X: pd.DataFrame) -> dict[str, list[str]]:
    """Which columns feed which model.

    XGBoost gets everything. Isolation Forest gets numeric behavioral
    only -- it is unsupervised and categoricals would dominate the
    distance metric.
    """
    feats = feature_columns(X)
    behav = [c for c in feats if c.startswith(("out_", "io_", "amt_vs_",
                                               "hrs_since_", "is_new_"))
             or (c.startswith("in_") and c[3:4].isdigit())]
    graph_c = [c for c in feats if c.startswith("g_")]
    txn = [c for c in feats if c not in behav + graph_c]
    numeric_behav = [c for c in behav
                     if pd.api.types.is_numeric_dtype(X[c])]
    return {
        "xgboost": feats,
        "isolation_forest": numeric_behav,
        "transaction": txn,
        "behavioral": behav,
        "graph": graph_c,
    }


def save(X: pd.DataFrame) -> None:
    out = config.DATA_PROCESSED / "features.parquet"
    X.to_parquet(out)
    log.info("wrote %s", out.name)


def load() -> pd.DataFrame:
    path = config.DATA_PROCESSED / "features.parquet"
    if not path.exists():
        raise FileNotFoundError("run: python -m ml.scripts.build_features")
    return pd.read_parquet(path)