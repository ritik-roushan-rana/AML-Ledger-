"""python -m ml.scripts.checks.features"""
import pandas as pd

from ml import config
from ml.features import transaction

df = pd.read_parquet(config.DATA_PROCESSED / "transactions_clean.parquet")
f = transaction.build(df)
y = df["is_laundering"]
base = y.mean()

print(f"\nrows {len(f):,}   features {f.shape[1]}   base rate {base:.4%}\n")

flags = ["in_suspicious_band", "in_tight_band", "above_ceiling",
         "near_10k_below", "near_1k_below", "is_offhours", "is_weekend",
         "is_cross_currency", "is_cross_bank", "is_self_loop"]
print(f"{'feature':22s} {'n_flagged':>10s} {'rate':>9s} {'lift':>7s}")
print("-" * 52)
for c in flags:
    if c not in f.columns:
        print(f"{c:22s} {'(dropped)':>10s}")
        continue
    m = f[c] == 1
    if not m.any():
        print(f"{c:22s} {'0':>10s}       --      --")
        continue
    r = y[m].mean()
    print(f"{c:22s} {m.sum():>10,} {r:>9.4%} {r/base:>7.2f}")

print("\nlaundering rate by amount decile (USD)")
dec = pd.qcut(f["amount_usd"], 10, labels=False, duplicates="drop")
print(y.groupby(dec).agg(["size", "mean"]).assign(
    lift=lambda d: (d["mean"] / base).round(2)).to_string())

print(f"\nfeature columns ({f.shape[1]}):")
print("  " + ", ".join(f.columns))


print("\nrisk by amount bucket (USD)")
bins = [0, 1000, 3000, 5000, 7000, 9000, 11000, 13000, 15000, 20000, 30000, 1e12]
b = pd.cut(f["amount_usd"], bins)
t = y.groupby(b, observed=True).agg(["size", "mean"])
t["lift"] = (t["mean"] / base).round(2)
t["pos"] = (t["size"] * t["mean"]).round().astype(int)
print(t.to_string())

hi_risk = t[t["lift"] >= 2.0]
if len(hi_risk):
    edges = [iv for iv in hi_risk.index]
    print(f"\nsuggested band: {edges[0].left:,.0f} -> {edges[-1].right:,.0f}")
    covered = hi_risk["pos"].sum() / y.sum()
    vol = hi_risk["size"].sum() / len(y)
    print(f"  catches {covered:.1%} of laundering in {vol:.1%} of transactions")