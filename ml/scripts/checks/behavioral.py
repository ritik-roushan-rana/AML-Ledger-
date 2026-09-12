"""python -m ml.scripts.checks.behavioral"""
import pandas as pd

from ml import config

path = config.DATA_PROCESSED / "features.parquet"
if not path.exists():
    raise SystemExit("run  python -m ml.scripts.build_features  first")

X = pd.read_parquet(path)
y = X["is_laundering"]
base = y.mean()

print(f"\nrows {len(X):,}  positives {y.sum():,}  base {base:.4%}\n")


def lift_table(col, thresholds, label):
    print(label)
    q = X[col]
    for t in thresholds:
        m = q >= t
        if m.any():
            print(f"  >={t:3d}  n={m.sum():>9,}  pos={int(y[m].sum()):>6,}"
                  f"  lift={y[m].mean()/base:>6.2f}")
    print()


lift_table("out_96h_ncp", [1, 2, 4, 7, 10, 15],
           "fan-out proxy: unique destinations in 96h")
lift_table("in_96h_ncp", [1, 2, 4, 8, 12, 16],
           "fan-in proxy: unique sources in 96h")
lift_table("out_24h_count", [1, 3, 5, 10, 20],
           "velocity: outgoing txns in 24h")
lift_table("in_192h_ncp", [4, 8, 12],
           "slow gather: unique sources in 192h")

print("mule signature: io_ratio_96h in [0.8, 1.2] with prior inflow")
m = X["io_ratio_96h"].between(0.8, 1.2) & (X["in_96h_count"] > 0)
print(f"  n={m.sum():,}  pos={int(y[m].sum()):,}  lift={y[m].mean()/base:.2f}\n"
      if m.any() else "  none\n")

print("pass-through: money out within 24h of money in")
m = (X["hrs_since_prev_in"] < 24) & (X["out_24h_count"] > 0)
print(f"  n={m.sum():,}  pos={int(y[m].sum()):,}  lift={y[m].mean()/base:.2f}\n"
      if m.any() else "  none\n")

print("burst: <1h since previous outgoing")
m = X["hrs_since_prev_out"] < 1
print(f"  n={m.sum():,}  pos={int(y[m].sum()):,}  lift={y[m].mean()/base:.2f}\n"
      if m.any() else "  none\n")

print("rule-out features (low lift is the point)")
for c in ["is_new_sender", "is_new_receiver", "above_ceiling", "is_self_loop"]:
    m = X[c] == 1
    print(f"  {c:16s} n={m.sum():>9,}  lift={y[m].mean()/base:>6.2f}")

print("\ncombined: tight band AND fan-out >= 7")
m = (X["in_tight_band"] == 1) & (X["out_96h_ncp"] >= 7)
print(f"  n={m.sum():,}  pos={int(y[m].sum()):,}  lift={y[m].mean()/base:.2f}"
      f"  recall={y[m].sum()/y.sum():.1%}" if m.any() else "  none")