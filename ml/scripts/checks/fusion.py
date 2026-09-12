"""python -m ml.scripts.checks.fusion"""
import pandas as pd

from ml import config, evaluation
from ml.features import build
from ml.models import fusion
from ml.models import xgb as xgbm

X = build.load()
te = X[X["timestamp"] > X["timestamp"].quantile(0.85)]
y = te["is_laundering"]
base = y.mean()

model, cols = xgbm.load()
p = xgbm.predict(model, te[cols])

f = fusion.fuse(te, p)

print(f"\nrows {len(te):,}  positives {y.sum():,}  base {base:.4%}\n")
print(f"{'band':10s} {'n':>9s} {'caught':>8s} {'prec':>8s} {'recall':>8s} {'lift':>8s}")
print("-" * 56)
for b in ["HIGH", "MEDIUM", "LOW", "CLEAR"]:
    m = (f["band"] == b).values
    if m.sum():
        print(f"{b:10s} {m.sum():>9,} {int(y[m].sum()):>8,} "
              f"{y[m].mean():>8.2%} {y[m].sum()/y.sum():>8.1%} "
              f"{y[m].mean()/base:>8.1f}")

print(f"\nescalated by rules: {f['escalated'].sum():,} transactions")
m = f["escalated"].values
if m.sum():
    print(f"  precision among escalated: {y[m].mean():.2%} "
          f"(lift {y[m].mean()/base:.1f})")

print("\nfused risk_score as a ranker")
evaluation.print_report(evaluation.report(y, f["risk_score"].values),
                        "Fused (model percentile + rule nudge)")

print("\nmodel alone, for comparison")
evaluation.print_report(evaluation.report(y, p), "XGBoost only")