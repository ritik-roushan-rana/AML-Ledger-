"""SHAP explanations: why THIS transaction was flagged.

TreeExplainer on XGBoost is exact, so single-alert explanations need no
sampling. The LABELS map turns column names into sentences an analyst
can read -- "out_96h_ncp" means nothing to an investigator, "sender paid
9 distinct accounts in 96h" means everything.
"""
import numpy as np
import pandas as pd
import shap

from ml import config

log = config.get_logger("explain")

LABELS = {
    "in_suspicious_band": "amount sits in the 3k-20k risk band",
    "in_tight_band": "amount sits in the 9k-20k high-risk band",
    "band_distance": "distance from the centre of the risk band",
    "above_ceiling": "amount above the 20k ceiling",
    "amount_usd": "transaction amount",
    "log_amount": "transaction amount",
    "near_10k_below": "amount just below 10,000",
    "near_1k_below": "amount just below a round thousand",
    "is_self_loop": "transfer between the same account",
    "is_cross_bank": "transfer crosses banks",
    "is_cross_currency": "currency conversion involved",
    "is_weekend": "weekend transaction",
    "is_offhours": "outside business hours",
    "hour": "hour of day",
    "dayofweek": "day of week",
    "amount_gap_ratio": "gap between amount sent and received",
    "hrs_since_prev_out": "hours since sender's previous payment",
    "hrs_since_prev_in": "hours since receiver's previous deposit",
    "is_new_sender": "sender has no recent history",
    "is_new_receiver": "receiver has no recent history",
    "g_recip": "receiver has already paid the sender back",
    "g_same_comm": "both accounts sit in the same cluster",
    "g_comm_size": "size of the account cluster",
    "g_triangle": "sender sits in a closed triangle of accounts",
    "g_chain_depth": "length of the forward payment chain",
    "g_cycle_len": "hops in the cycle back to the sender",
    "g_pagerank": "sender's centrality in the network",
    "g_out_deg": "sender's outgoing connections",
    "g_in_deg_dst": "receiver's incoming connections",
    "g_deg_ratio": "ratio of sender's outgoing to incoming links",
    "g_pagerank_dst": "receiver's centrality in the network",
    "currency_paid": "currency sent",
    "currency_received": "currency received",
}

_STATS = {"ncp": "distinct counterparties", "count": "transactions",
          "sum": "total value", "mean": "average amount", "max": "largest amount"}

def label(col: str) -> str:
    if col in LABELS:
        return LABELS[col]

    for pre, who in [("out_", "sender"), ("in_", "receiver")]:
        if col.startswith(pre):
            hrs, _, stat = col[len(pre):].partition("_")
            out = pre == "out_"
            phrases = {
                "ncp": f"{'paid' if out else 'received from'} distinct accounts",
                "count": f"{'made' if out else 'received'} payments",
                "sum": f"total {'sent' if out else 'received'}",
                "mean": f"average payment {'sent' if out else 'received'}",
                "max": f"largest payment {'sent' if out else 'received'}",
            }
            if stat in phrases:
                return f"{who} {phrases[stat]} in the last {hrs}"
            break

    if col.startswith("io_ratio"):
        return "ratio of money out to money in"
    if col.startswith("io_balance"):
        return "imbalance between money in and money out"
    if col.startswith("amt_vs_mean"):
        return "amount relative to this account's usual"
    return col.replace("_", " ")


def make_explainer(model):
    return shap.TreeExplainer(model)

def explain_one(explainer, row: pd.DataFrame, top: int = 6) -> list[dict]:
    """One transaction -> ranked drivers, strongest absolute impact first."""
    raw_row = row
    row_num = _numeric(row)
    sv = explainer.shap_values(row_num)
    if isinstance(sv, list):
        sv = sv[1]
    vals = np.asarray(sv).ravel()

    out = [{"feature": c, "label": label(c), "shap": float(v), "value": raw}
           for c, v, raw in zip(raw_row.columns, vals, raw_row.iloc[0].values)]
    out.sort(key=lambda d: -abs(d["shap"]))
    strong = [d for d in out if d["shap"] > 0][:top]
    return strong


def format_drivers(drivers: list[dict]) -> str:
    """Markdown bullets for the report."""
    lines = []
    for d in drivers:
        v = d["value"]
        v = f"{v:,.2f}".rstrip("0").rstrip(".") if isinstance(
            v, (int, float, np.number)) else str(v)
        sign = "increases risk" if d["shap"] > 0 else "reduces risk"
        lines.append(f"- {d['label']} = **{v}** — {sign} ({d['shap']:+.3f})")
    return "\n".join(lines)


def global_importance(explainer, X: pd.DataFrame, sample: int = 20_000):
    """Mean |SHAP| across a sample. What the model relies on overall."""
    Xs = _numeric(X.sample(min(sample, len(X)), random_state=0))
    sv = explainer.shap_values(Xs)
    if isinstance(sv, list):
        sv = sv[1]
    s = pd.Series(np.abs(sv).mean(axis=0), index=Xs.columns)
    s = s.sort_values(ascending=False)
    return pd.DataFrame({"feature": s.index,
                         "meaning": [label(c) for c in s.index],
                         "mean_abs_shap": s.values.round(5)})

def _numeric(X: pd.DataFrame) -> pd.DataFrame:
    """SHAP builds its own DMatrix without enable_categorical, so
    category dtypes must be cast to their integer codes first."""
    X = X.copy()
    for c in X.columns:
        if isinstance(X[c].dtype, pd.CategoricalDtype):
            X[c] = X[c].cat.codes.astype("int32")
    return X