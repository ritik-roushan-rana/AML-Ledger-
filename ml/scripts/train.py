"""Train the supervised model and evaluate on a held-out time period.

    python -m ml.scripts.train
    python -m ml.scripts.train --drop payment_format --tag nopf

Split is by ROW QUANTILE, not calendar date: the IBM file has a thin
tail of transactions running to Sept 18 while 99.9% of the data ends
Sept 10, so a date-based split silently produces a 74-row test set.
"""
import argparse

from ml import config, evaluation
from ml.features import build
from ml.models import xgb as xgbm

log = config.get_logger("train")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--drop", nargs="*", default=[],
                   help="feature columns to exclude, e.g. --drop payment_format")
    p.add_argument("--tag", default="",
                   help="suffix for the saved model file, e.g. --tag nopf")
    args = p.parse_args()

    X = build.load()
    cols = build.split_by_family(X)["xgboost"]
    if args.drop:
        cols = [c for c in cols if c not in args.drop]
        log.info("dropped %s -> %d features", args.drop, len(cols))

    ts = X["timestamp"]
    t1 = ts.quantile(0.70)
    t2 = ts.quantile(0.85)

    tr = X[ts <= t1]
    va = X[(ts > t1) & (ts <= t2)]
    te = X[ts > t2]

    log.info("cut points: %s | %s", t1, t2)
    log.info("train %s | val %s | test %s",
             f"{len(tr):,}", f"{len(va):,}", f"{len(te):,}")
    log.info("positives  %d / %d / %d",
             tr.is_laundering.sum(), va.is_laundering.sum(),
             te.is_laundering.sum())

    model = xgbm.train(tr[cols], tr.is_laundering,
                       va[cols], va.is_laundering)

    if args.tag:
        xgbm.MODEL_PATH = config.MODELS / f"xgb_{args.tag}.json"
        xgbm.COLS_PATH = config.MODELS / f"xgb_{args.tag}_columns.json"
    xgbm.save(model, cols)

    pred = xgbm.predict(model, te[cols])
    title = "XGBoost -- held-out test period"
    if args.drop:
        title += f"  (without {', '.join(args.drop)})"
    evaluation.print_report(evaluation.report(te.is_laundering, pred), title)

    b = evaluation.baseline_amount_band(te, te.is_laundering)
    print(f"\nbaseline (amount 9k-20k): {b['n_flagged']:,} alerts, "
          f"precision {b['precision']:.2%}, recall {b['recall']:.1%}")

    print("\ntop features by gain")
    print(xgbm.importance(model).to_string())


if __name__ == "__main__":
    main()