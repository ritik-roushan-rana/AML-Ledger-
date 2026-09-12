"""Fetch surrounding context for one transaction."""
import pandas as pd


def money_flow(df, txn, hours=96, limit=15):
    """Transactions touching either account in the window."""
    lo = txn["timestamp"] - pd.Timedelta(hours=hours)
    hi = txn["timestamp"] + pd.Timedelta(hours=1)
    accts = {txn["from_id"], txn["to_id"]}
    m = (df["timestamp"].between(lo, hi) &
         (df["from_id"].isin(accts) | df["to_id"].isin(accts)))
    return df[m].sort_values("timestamp").head(limit)


def counterparties(df, txn, hours=96, limit=10):
    """Who the two accounts dealt with, and in which direction."""
    flow = money_flow(df, txn, hours, limit=10_000)
    accts = {txn["from_id"], txn["to_id"]}
    rows = []
    for _, r in flow.iterrows():
        for a, b, role in [(r["from_id"], r["to_id"], "received from"),
                           (r["to_id"], r["from_id"], "paid to")]:
            if a in accts and b not in accts:
                rows.append({"account": b, "amount": r["amount_usd"],
                             "role": role})
    if not rows:
        return pd.DataFrame(columns=["account", "n", "total", "role"])
    g = pd.DataFrame(rows).groupby(["account", "role"]).agg(
        n=("amount", "size"), total=("amount", "sum")).reset_index()
    return g.sort_values("total", ascending=False).head(limit)