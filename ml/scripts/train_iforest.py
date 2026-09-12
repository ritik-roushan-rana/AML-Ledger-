"""python -m ml.scripts.train_iforest

Same row-quantile split as ml.scripts.train so the anomaly reference
distribution is built on the training period only.
"""
from ml import config, evaluation
from ml.features import build
from ml.models import iforest

log = config.get_logger("train_iforest")


def main():
    X = build.load()
    cols = build.split_by_family(X)["isolation_forest"]
    ts = X["timestamp"]
    tr = X[ts <= ts.quantile(0.70)]
    te = X[ts > ts.quantile(0.85)]

    bundle = iforest.train(tr, cols)
    iforest.save(bundle)

    s = iforest.score(bundle, te)
    evaluation.print_report(evaluation.report(te.is_laundering, s),
                            "Isolation Forest -- held-out test period (evidence only)")


if __name__ == "__main__":
    main()
