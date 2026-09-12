"""python -m ml.scripts.checks.rules"""
import pandas as pd

from ml import config, evaluation
from ml.features import build
from ml.models import rules

X = build.load()
te = X[X["timestamp"] > X["timestamp"].quantile(0.85)]
y = te["is_laundering"]
base = y.mean()

r = rules.evaluate(te)

print(f"\nrows {len(te):,}  positives {y.sum():,}  base {base:.4%}\n")
print(f"{'rule':22s} {'fired':>9s} {'caught':>7s} {'prec':>8s} {'lift':>7s}")
print("-" * 58)
for c in rules.DESCRIPTIONS:
    if c not in r.columns:
        continue
    m = r[c].values
    if m.sum() == 0:
        print(f"{c:22s} {'never':>9s}")
        continue
    print(f"{c:22s} {m.sum():>9,} {int(y[m].sum()):>7,} "
          f"{y[m].mean():>8.2%} {y[m].mean()/base:>7.2f}")

print("\nrule_score as a ranker")
evaluation.print_report(evaluation.report(y, r["rule_score"].values),
                        "Rules only")

print("\nscore distribution")
print(y.groupby(r["rule_score"]).agg(["size", "mean"]).head(15).to_string())