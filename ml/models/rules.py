"""Deterministic typology rules.

Runs on the FEATURE MATRIX, not raw transactions -- the behavioral and
graph columns already encode the counterparty counts, time windows and
path structures each rule needs.

Thresholds come from configs/rules.yaml, derived from the 370 labelled
pattern groups in HI-Small_Patterns.txt. Weights come from measured lift
on the held-out test period.

Rules are NOT here to beat XGBoost -- rules-only PR-AUC is 0.004 versus
the model's 0.374. They exist because an investigator can read "account
received from 11 distinct sources in 96h" and act on it, whereas
"probability 0.87" is not evidence.
"""
import numpy as np
import pandas as pd

from ml import config

log = config.get_logger("models.rules")

DESCRIPTIONS = {
    "fan_in": "account received funds from an unusual number of sources",
    "amount_band": "amount in the 9k-20k high-risk band",
    "gather_scatter": "funds accumulated from many sources then redistributed",
    "cycle": "funds returned to the originating account",
    "structuring": "amount placed just below a reporting threshold",
    "weekend": "executed outside the normal business week",
    "fan_out": "sender distributed funds to an unusual number of accounts",
    "stack": "transaction sits in a long layering chain",
    "scatter_gather": "funds dispersed then reconsolidated",
}


def evaluate(X: pd.DataFrame) -> pd.DataFrame:
    """One boolean column per rule, plus a weighted rule_score."""
    cfg = config.load("rules")
    r = pd.DataFrame(index=X.index)

    # --- fan-in: many sources into one account (lift 8.48) -------------
    r["fan_in"] = X["in_96h_ncp"] >= cfg["fan_in"]["min_sources"]

    # --- amount band (lift 6.22) ---------------------------------------
    r["amount_band"] = X["in_tight_band"] == 1

    # --- gather-scatter: slow inflow then outflow (lift 5.86) ----------
    gs = cfg["gather_scatter"]
    r["gather_scatter"] = ((X["in_192h_ncp"] >= gs["min_intermediaries"]) &
                           (X["out_192h_ncp"] >= 2))

    # --- cycle: money returns to origin --------------------------------
    if "g_cycle_len" in X.columns:
        r["cycle"] = X["g_cycle_len"] >= cfg["cycle"]["min_hops"]
    else:
        r["cycle"] = X["g_recip"] > 0

    # --- structuring: parked just under a threshold (lift 2.69) --------
    r["structuring"] = X["near_10k_below"] == 1

    # --- weekend (lift 1.63) -------------------------------------------
    r["weekend"] = X["is_weekend"] == 1

    # --- fan-out: one sender, many destinations (lift 1.43) ------------
    r["fan_out"] = X["out_96h_ncp"] >= cfg["fan_out"]["min_destinations"]

    # --- stack: long layering chain ------------------------------------
    if "g_chain_depth" in X.columns:
        r["stack"] = X["g_chain_depth"] >= cfg["stack"]["min_chain_depth"]
    else:
        r["stack"] = False

    # --- scatter-gather: fast spread then reconsolidation --------------
    sg = cfg["scatter_gather"]
    r["scatter_gather"] = ((X["out_96h_ncp"] >= sg["min_intermediaries"]) &
                           (X["in_96h_ncp"] >= 2))

    # --- weighted score -------------------------------------------------
    w = cfg["scoring"]["weights"]
    score = np.zeros(len(X), dtype=float)
    for rule, weight in w.items():
        if rule in r.columns and weight:
            score += r[rule].astype(float).values * weight

    # Hard rule-out: nothing above 20k launders in this dataset.
    if "above_ceiling" in X.columns:
        score = np.where(X["above_ceiling"].values == 1, 0.0, score)

    r["rule_score"] = score
    r["rule_score_norm"] = np.clip(score / cfg["scoring"]["max_score"], 0, 1)
    r["n_rules_fired"] = r[list(DESCRIPTIONS)].sum(axis=1).astype(int)

    log.info("rules fired on %s of %s rows",
             f"{(score > 0).sum():,}", f"{len(X):,}")
    return r


def triggered_names(row: pd.Series) -> list[str]:
    """Which rules fired for one transaction. Feeds the report."""
    return [c for c in DESCRIPTIONS if c in row.index and bool(row[c])]


def evidence_lines(row: pd.Series) -> list[str]:
    """Plain-English findings for the investigation report."""
    return [DESCRIPTIONS[c] for c in triggered_names(row)]