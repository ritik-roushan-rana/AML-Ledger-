"""python -m ml.scripts.run_patterns"""
from ml import patterns

df = patterns.parse()
prof = patterns.profile(df)

print("\nTransactions per pattern type")
print(df["pattern"].value_counts().to_string())
print("\nPer-typology profile (medians)")
print(prof.to_string())
print("\n--- threshold candidates for configs/rules.yaml ---")
for p in ["FAN-OUT", "FAN-IN", "SCATTER-GATHER", "GATHER-SCATTER", "CYCLE", "STACK"]:
    if p in prof.index:
        r = prof.loc[p]
        print(f"{p:16s} recv_med={r.receivers_med:>5}  "
              f"recv_p25={r.receivers_p25:>5}  span_h={r.span_h_med:>7}")