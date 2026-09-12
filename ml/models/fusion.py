"""Combine model score and rule score into a triage decision.

Design note: this is NOT a weighted blend. Rules-only PR-AUC is 0.017
against the model's 0.374, so averaging them would degrade ranking.
Instead:

    model percentile  -> determines the band        (ranking)
    rules             -> can ESCALATE one band      (precision at margin)
    rules             -> supply the evidence text   (explanation)

Model probabilities are badly calibrated (scale_pos_weight=1244 puts the
top decile at mean 0.16 against an actual rate of 0.018), so bands come
from percentile rank, never from raw probability.
"""
import numpy as np
import pandas as pd

from ml import config
from ml.models import rules as rules_mod

log = config.get_logger("models.fusion")

BANDS = {"HIGH": 99.9, "MEDIUM": 99.0, "LOW": 95.0}

# Rules precise enough to justify moving a transaction up a band.
ESCALATING = {"cycle", "fan_in", "gather_scatter", "amount_band"}
ESCALATE_MIN = 2          # this many must fire together


def fuse(X: pd.DataFrame, model_score: np.ndarray) -> pd.DataFrame:
    r = rules_mod.evaluate(X)

    pct = pd.Series(model_score, index=X.index).rank(pct=True) * 100
    out = pd.DataFrame(index=X.index)
    out["model_score"] = model_score
    out["model_pct"] = pct
    out["rule_score"] = r["rule_score"]
    out["n_rules"] = r["n_rules_fired"]

        # Percentile carries the ranking. The rule nudge is deliberately
    # small -- it separates ties, it does not reorder the queue. A large
    # nudge drops PR-AUC from 0.374 to 0.189 because 95% of rows share a
    # near-zero model score and the rules then dominate the ordering.
    out["risk_score"] = np.clip(
        pct + r["rule_score_norm"] * 0.05, 0, 100).round(4)

    band = np.select(
        [pct >= BANDS["HIGH"], pct >= BANDS["MEDIUM"], pct >= BANDS["LOW"]],
        ["HIGH", "MEDIUM", "LOW"], default="CLEAR")

    esc = r[list(ESCALATING & set(r.columns))].sum(axis=1) >= ESCALATE_MIN
    out["escalated"] = esc.values
    band = np.where(esc & (band == "MEDIUM"), "HIGH",
           np.where(esc & (band == "LOW"), "MEDIUM", band))
    out["band"] = band

    out["action"] = pd.Series(band, index=X.index).map({
        "HIGH": "REPORT", "MEDIUM": "REVIEW",
        "LOW": "MONITOR", "CLEAR": "NONE"})

    out = pd.concat([out, r[list(rules_mod.DESCRIPTIONS)]], axis=1)
    log.info("bands: %s", pd.Series(band).value_counts().to_dict())
    return out


def with_anomaly(fused: pd.DataFrame, anomaly: np.ndarray) -> pd.DataFrame:
    """Attach the Isolation Forest percentile as EVIDENCE. Deliberately
    does not touch risk_score or band -- IF-only PR-AUC is 0.002, so
    letting it reorder the queue would be strictly worse. It is there so
    the report and the LLM can say "behaviour is in the top X% most
    unusual" independently of the supervised model."""
    out = fused.copy()
    out["anomaly_pct"] = np.round(np.asarray(anomaly, dtype=float) * 100, 3)
    return out


def alerts(fused: pd.DataFrame, min_band: str = "MEDIUM") -> pd.DataFrame:
    order = ["CLEAR", "LOW", "MEDIUM", "HIGH"]
    keep = order[order.index(min_band):]
    return fused[fused["band"].isin(keep)].sort_values(
        "risk_score", ascending=False)