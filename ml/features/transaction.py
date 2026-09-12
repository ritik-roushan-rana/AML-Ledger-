"""Per-transaction features. One row in, one row out.

Deliberately stateless: nothing here looks at other transactions, so
there is no leakage risk and no train/test asymmetry. Anything needing
history belongs in behavioral.py; anything needing structure, graph.py.

Roundness features were tested and dropped: round amounts in this
dataset launder at ~1/12th the base rate, i.e. the classic structuring
tell is absent from the IBM generator.
"""
import numpy as np
import pandas as pd

from ml import config

log = config.get_logger("features.transaction")


def build(df: pd.DataFrame) -> pd.DataFrame:
    """Returns a frame indexed like df, containing only feature columns."""
    cfg = config.load("rules")
    a = cfg["amount"]
    f = pd.DataFrame(index=df.index)

    amt = df["amount_usd"]              # comparable across currencies
    paid = df["amount_paid"].round(2)   # what the sender actually chose

    # --- amount ------------------------------------------------------
    f["amount_usd"] = amt
    f["log_amount"] = np.log1p(amt)

    # Risk climbs to 20k then falls off a cliff. Both bands given to the
    # model so it can pick its own precision/recall trade-off.
    lo, hi = a["band_low"], a["band_high"]
    f["in_suspicious_band"] = amt.between(lo, hi).astype("int8")
    f["band_distance"] = (amt - (lo + hi) / 2).abs() / ((hi - lo) / 2)

    tlo, thi = a["band_tight_low"], a["band_tight_high"]
    f["in_tight_band"] = amt.between(tlo, thi).astype("int8")

    # Nothing above the ceiling launders -- this rules alerts OUT.
    f["above_ceiling"] = amt.gt(a["hard_ceiling"]).astype("int8")

    # --- just-under thresholds (original currency) ---------------------
    f["near_10k_below"] = paid.between(9000, 9999).astype("int8")
    f["near_1k_below"] = paid.mod(1000).between(900, 999).astype("int8")

    # --- currency / routing -------------------------------------------
    f["is_cross_currency"] = df["is_cross_currency"].astype("int8")
    f["is_cross_bank"] = df["is_cross_bank"].astype("int8")
    f["is_self_loop"] = df["is_self_loop"].astype("int8")

    recv = df["amount_received"] * df["currency_received"].map(
        config.CFG["fx_to_usd"]).fillna(1.0)
    f["amount_gap_ratio"] = ((amt - recv).abs() / amt.clip(lower=1)).clip(upper=1)

    # --- time ----------------------------------------------------------
    ts = df["timestamp"]
    hour = ts.dt.hour
    f["hour"] = hour.astype("int8")
    f["dayofweek"] = ts.dt.dayofweek.astype("int8")
    f["is_weekend"] = ts.dt.dayofweek.ge(5).astype("int8")
    f["is_offhours"] = (~hour.between(7, 19)).astype("int8")
    f["hour_sin"] = np.sin(2 * np.pi * hour / 24)
    f["hour_cos"] = np.cos(2 * np.pi * hour / 24)

    # payment_format EXCLUDED: Wire and Reinvestment have zero labelled
    # laundering across 653k rows -- a generator artifact. A model using
    # it learns to ignore wire transfers, which is unusable in production.
    for col in ["currency_paid", "currency_received"]:
        f[col] = df[col].astype("category")
        
    log.info("transaction features: %d columns", f.shape[1])
    return f