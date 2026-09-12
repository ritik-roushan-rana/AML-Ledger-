"""python -m ml.scripts.investigate --top 3"""
import argparse

import pandas as pd

from ml import config, explain
from ml.agent import agent, context, report
from ml.agent.tools import ToolBox
from ml.features import build
from ml.models import fusion, iforest
from ml.models import xgb as xgbm

log = config.get_logger("investigate")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--top", type=int, default=3)
    p.add_argument("--txn", type=int)
    args = p.parse_args()

    X = build.load()
    raw = pd.read_parquet(config.DATA_PROCESSED / "transactions_clean.parquet")
    te = X[X["timestamp"] > X["timestamp"].quantile(0.85)]

    model, cols = xgbm.load()
    fused = fusion.fuse(te, xgbm.predict(model, te[cols]))
    if iforest.MODEL_PATH.exists():
        fused = fusion.with_anomaly(fused, iforest.score(iforest.load(), te))
    ex = explain.make_explainer(model)
    tools = ToolBox(te, raw, fused, model, cols, ex)

    if args.txn is not None:
        ids = [args.txn]
    else:
        idx = fused.sort_values("risk_score", ascending=False).head(args.top).index
        ids = [int(v) for v in te.loc[idx, "txn_id"]]

    for txn_id in ids:
        ev = agent.gather(tools, txn_id)
        narrative = agent.narrate(ev)

        idx = te.index[te["txn_id"] == txn_id][0]
        txn = te.loc[idx]
        md = report.build(txn, fused.loc[idx],
                          explain.explain_one(ex, te.loc[[idx], cols]),
                          context.money_flow(raw, txn),
                          context.counterparties(raw, txn))
        md = md.replace("## 1. Why this was flagged",
                        f"## Investigator summary\n\n{narrative}\n\n"
                        "## 1. Why this was flagged")

        path = config.OUT_REPORTS / f"AML-{txn_id:08d}.md"
        path.write_text(md)
        print(f"\n{'=' * 60}\n{path.name}  label={txn['is_laundering']}\n")
        print(narrative)


if __name__ == "__main__":
    main()