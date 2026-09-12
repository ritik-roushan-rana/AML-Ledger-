"""python -m ml.scripts.checks.graph_timing"""
import time

import pandas as pd

from ml import config
from ml.features import graph

df = pd.read_parquet(config.DATA_PROCESSED / "transactions_clean.parquet")
df = df.iloc[::5].head(600_000)

t0 = time.time()
f = graph.build(df, bucket_hours=24)
print(f"\nbuilt in {time.time() - t0:.0f}s")

y = df["is_laundering"].reindex(f.index)
base = y.mean()
print(f"rows {len(f):,}  positives {y.sum():,}  base {base:.4%}\n")

for c in ["g_chain_depth", "g_cycle_len", "g_recip", "g_two_hop_back",
          "g_same_comm", "g_triangle"]:
    shown = False
    for t in [1, 2, 3, 4]:
        m = f[c] >= t
        if m.sum() > 50:
            print(f"{c:16s} >={t}  n={m.sum():>8,}  pos={int(y[m].sum()):>4,}"
                  f"  lift={y[m].mean()/base:>6.2f}")
            shown = True
    if not shown:
        print(f"{c:16s} too sparse")
    print()