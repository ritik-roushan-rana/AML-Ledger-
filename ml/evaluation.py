"""Metrics that matter at a 0.1% positive rate.

Accuracy is useless here -- predicting "never" scores 99.9%. What a bank
cares about is precision at a fixed alert budget: if an analyst reviews
1,000 transactions a day, how many are real?
"""
import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, roc_auc_score

from ml import config

log = config.get_logger("evaluation")


def report(y_true, y_score, alert_budgets=(100, 500, 1000, 5000)) -> dict:
    y_true = np.asarray(y_true)
    y_score = np.asarray(y_score)
    n_pos = int(y_true.sum())

    out = {
        "n": len(y_true),
        "positives": n_pos,
        "base_rate": float(y_true.mean()),
        "pr_auc": float(average_precision_score(y_true, y_score)),
        "roc_auc": float(roc_auc_score(y_true, y_score)),
        "at_k": {},
    }
    out["lift_over_random"] = out["pr_auc"] / out["base_rate"]

    order = np.argsort(-y_score)
    for k in alert_budgets:
        if k > len(y_true):
            continue
        top = y_true[order[:k]]
        out["at_k"][k] = {
            "precision": float(top.mean()),
            "recall": float(top.sum() / max(n_pos, 1)),
            "caught": int(top.sum()),
        }
    return out


def print_report(r: dict, title: str = "") -> None:
    print(f"\n{'=' * 56}")
    if title:
        print(title)
    print(f"rows {r['n']:,}   positives {r['positives']:,}   "
          f"base {r['base_rate']:.4%}")
    print(f"PR-AUC  {r['pr_auc']:.4f}   ({r['lift_over_random']:.0f}x random)")
    print(f"ROC-AUC {r['roc_auc']:.4f}")
    print(f"\n{'alerts':>8} {'precision':>10} {'recall':>8} {'caught':>8}")
    for k, v in r["at_k"].items():
        print(f"{k:>8,} {v['precision']:>10.2%} {v['recall']:>8.1%} "
              f"{v['caught']:>8,}")
    print("=" * 56)


def baseline_amount_band(X, y, lo=9000, hi=20000) -> dict:
    """The rule the model must beat."""
    m = X["amount_usd"].between(lo, hi)
    return {"n_flagged": int(m.sum()),
            "precision": float(y[m].mean()),
            "recall": float(y[m].sum() / y.sum())}


def _join_key(ts, a, b) -> pd.Series:
    """Normalised key. Both sides must be built the same way."""
    return (pd.to_datetime(ts).dt.strftime("%Y-%m-%d %H:%M") + "|" +
            a.astype(str).str.strip() + "|" + b.astype(str).str.strip())


def per_typology(X_test, y_score, patterns_df, k: int = 1000) -> pd.DataFrame:
    """Recall broken down by laundering scheme.

    'We catch 82% of fan-out but 41% of stacking' tells a bank where the
    system is blind. One aggregate recall number does not.
    """
    pat = dict(zip(
        _join_key(patterns_df["timestamp"], patterns_df["from_id"],
                  patterns_df["to_id"]),
        patterns_df["pattern"]))
    typ = _join_key(X_test["timestamp"], X_test["from_id"],
                    X_test["to_id"]).map(pat)

    order = np.argsort(-np.asarray(y_score))
    flagged = np.zeros(len(X_test), dtype=bool)
    flagged[order[:k]] = True

    log.info("matched %s of %s test rows to a typology",
             f"{typ.notna().sum():,}", f"{len(X_test):,}")

    rows = []
    for name in typ.dropna().unique():
        idx = (typ == name).values
        n = int(idx.sum())
        caught = int(flagged[idx].sum())
        rows.append({"pattern": name, "n_in_test": n, "caught": caught,
                     "recall": round(caught / n, 3) if n else 0.0})

    if not rows:
        return pd.DataFrame(columns=["pattern", "n_in_test", "caught", "recall"])
    return pd.DataFrame(rows).sort_values("recall", ascending=False)


def alert_volume(y_score, thresholds=(0.5, 0.7, 0.9, 0.95, 0.99), days=2.3):
    """How many analysts would this need? The question a bank actually asks."""
    rows = []
    for t in thresholds:
        n = int((np.asarray(y_score) >= t).sum())
        rows.append({"threshold": t, "alerts": n,
                     "per_day": round(n / days),
                     "analyst_hours": round(n / days * 0.5, 1)})
    return pd.DataFrame(rows)


def score_distribution(y_true, y_score, bins=10) -> pd.DataFrame:
    """Calibration check: does a 0.9 score mean 90% likely?"""
    q = pd.qcut(pd.Series(y_score), bins, labels=False, duplicates="drop")
    df = pd.DataFrame({"bin": q.values, "y": np.asarray(y_true),
                       "score": np.asarray(y_score)})
    return df.groupby("bin").agg(
        n=("y", "size"), mean_score=("score", "mean"),
        actual_rate=("y", "mean")).round(4)