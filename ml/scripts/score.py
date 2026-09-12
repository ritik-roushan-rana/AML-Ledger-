"""Generate investigation reports for the top alerts.

    python -m ml.scripts.score --top 5
    python -m ml.scripts.score --txn 4211
"""
import argparse

import pandas as pd

from ml import config, explain
from ml.agent import context, report
from ml.features import build
from ml.models import fusion
from ml.models import xgb as xgbm

log = config.get_logger("score")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--top", type=int, default=5)
    p.add_argument("--txn", type=int)
    args = p.parse_args()

    X = build.load()
    raw = pd.read_parquet(config.DATA_PROCESSED / "transactions_clean.parquet")
    te = X[X["timestamp"] > X["timestamp"].quantile(0.85)]

    model, cols = xgbm.load()
    pred = xgbm.predict(model, te[cols])
    fused = fusion.fuse(te, pred)
    ex = explain.make_explainer(model)

    if args.txn is not None:
        picks = te.index[te["txn_id"] == args.txn]
    else:
        picks = fused.sort_values("risk_score", ascending=False).head(args.top).index

    written = []
    for idx in picks:
        txn = te.loc[idx]
        drivers = explain.explain_one(ex, te.loc[[idx], cols])
        flow = context.money_flow(raw, txn)
        cp = context.counterparties(raw, txn)
        md = report.build(txn, fused.loc[idx], drivers, flow, cp)

        path = config.OUT_REPORTS / f"AML-{int(txn['txn_id']):08d}.md"
        path.write_text(md)
        written.append(path)
        log.info("%s  %s  risk %.1f  label=%d", path.name,
                 fused.loc[idx, "band"], fused.loc[idx, "risk_score"],
                 txn["is_laundering"])

    print(f"\nwrote {len(written)} reports to {config.OUT_REPORTS}")
    if written:
        print(f"\n--- preview: {written[0].name} ---\n")
        print(written[0].read_text())


if __name__ == "__main__":
    main()