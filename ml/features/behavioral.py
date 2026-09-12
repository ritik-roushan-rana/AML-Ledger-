"""Account-level rolling features, computed strictly on PAST transactions.

Leakage rule: for a transaction at time t, every aggregate covers
[t - window, t). The current row is EXCLUDED. Break this and your
PR-AUC will look excellent and mean nothing.

Windows come from patterns.py: typologies complete in 24-192 hours.
"""
import numpy as np
import pandas as pd

from ml import config

log = config.get_logger("features.behavioral")


def build(df: pd.DataFrame) -> pd.DataFrame:
    cfg = config.load("rules")
    w = cfg["windows_hours"]
    windows = [w["fast"], w["standard"], w["slow"]]

    df = df.sort_values("timestamp")
    f = pd.DataFrame(index=df.index)

    for side, key in [("out", "from_id"), ("in", "to_id")]:
        for hours in windows:
            r = _rolling(df, key, hours)
            p = f"{side}_{hours}h"
            f[f"{p}_count"] = r["count"]
            f[f"{p}_sum"] = r["sum"]
            f[f"{p}_mean"] = r["mean"]
            f[f"{p}_max"] = r["max"]
            f[f"{p}_ncp"] = r["ncp"]
            log.info("done %s", p)

    # Is this amount unusual for this account lately?
    for h in windows:
        m = f[f"out_{h}h_mean"]
        f[f"amt_vs_mean_{h}h"] = (
            df["amount_usd"] / m.replace(0, np.nan)).fillna(1.0).clip(upper=100)

    # Mule signature: money in then straight back out -> ratio near 1.
    for h in windows:
        i, o = f[f"in_{h}h_sum"], f[f"out_{h}h_sum"]
        f[f"io_ratio_{h}h"] = (o / i.replace(0, np.nan)).fillna(0).clip(upper=10)
        f[f"io_balance_{h}h"] = ((o - i).abs() /
                                 (o + i).replace(0, np.nan)).fillna(1.0)

    # Burst detection.
    prev_out = df.groupby("from_id")["timestamp"].shift(1)
    f["hrs_since_prev_out"] = ((df["timestamp"] - prev_out)
                               .dt.total_seconds().div(3600)
                               .fillna(9999).clip(upper=9999))
    prev_in = df.groupby("to_id")["timestamp"].shift(1)
    f["hrs_since_prev_in"] = ((df["timestamp"] - prev_in)
                              .dt.total_seconds().div(3600)
                              .fillna(9999).clip(upper=9999))

    # No history at all is different from a history of zeros.
    f["is_new_sender"] = f["out_192h_count"].eq(0).astype("int8")
    f["is_new_receiver"] = f["in_192h_count"].eq(0).astype("int8")

    f = f.reindex(df.index)
    log.info("behavioral features: %d columns", f.shape[1])
    return f


def _rolling(df: pd.DataFrame, key: str, hours: int) -> pd.DataFrame:
    """Time-window aggregates per account, EXCLUDING the current row."""
    n = len(df)
    cnt = np.zeros(n)
    tot = np.zeros(n)
    mx = np.zeros(n)
    ncp = np.zeros(n)

    cp_col = "to_id" if key == "from_id" else "from_id"
    win = np.timedelta64(hours, "h")
    pos = {ix: i for i, ix in enumerate(df.index)}

    for _, g in df.groupby(key, sort=False):
        k = len(g)
        if k == 1:
            continue
        t = g["timestamp"].values
        a = g["amount_usd"].values
        cp = pd.factorize(g[cp_col])[0]
        rows = [pos[ix] for ix in g.index]

        lo = np.searchsorted(t, t - win, side="left")
        idx = np.arange(k)
        # end bound is idx (not idx+1) -> current row excluded
        c = idx - lo
        cs = np.concatenate([[0.0], np.cumsum(a)])
        s = cs[idx] - cs[lo]

        for j in range(k):
            r = rows[j]
            cnt[r] = c[j]
            tot[r] = s[j]
            if c[j] > 0:
                sl = slice(lo[j], j)
                mx[r] = a[sl].max()
                ncp[r] = np.unique(cp[sl]).size

    mean = np.where(cnt > 0, tot / np.maximum(cnt, 1), 0.0)
    return pd.DataFrame({"count": cnt, "sum": tot, "mean": mean,
                         "max": mx, "ncp": ncp}, index=df.index)