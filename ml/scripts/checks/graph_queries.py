"""python -m ml.scripts.checks.graph_queries"""
import pandas as pd

from ml import config
from ml.features import build
from ml.graph import queries
from ml.models import fusion
from ml.models import xgb as xgbm

X = build.load()
te = X[X["timestamp"] > X["timestamp"].quantile(0.85)]
model, cols = xgbm.load()
f = fusion.fuse(te, xgbm.predict(model, te[cols]))

top = f.sort_values("risk_score", ascending=False).head(1).index[0]
txn = te.loc[top]
acct = txn["to_id"]

print(f"\ninvestigating receiver {acct}")
print(f"(from alert: {txn['from_id']} -> {txn['to_id']}, "
      f"${txn['amount_usd']:,.0f}, label={txn['is_laundering']})\n")

print("--- account summary ---")
print(queries.account_summary(acct), "\n")

print("--- connected accounts ---")
print(queries.connected_accounts(acct, limit=10).to_string(index=False), "\n")

print("--- money flow (2 hops) ---")
print(queries.money_flow(acct, hops=2, limit=10).to_string(index=False), "\n")

print("--- cycles ---")
c = queries.find_cycles(acct)
print(c.to_string(index=False) if len(c) else "none found", "\n")

print("--- possible ring (shared counterparties) ---")
r = queries.fraud_ring(acct)
print(r.to_string(index=False) if len(r) else "none found")