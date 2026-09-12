"""python -m ml.scripts.evaluate"""
import pandas as pd

from ml import config, evaluation
from ml.features import build
from ml.models import xgb as xgbm

log = config.get_logger("evaluate")


def main():
    X = build.load()
    model, cols = xgbm.load()

    te = X[X["timestamp"] > X["timestamp"].quantile(0.85)]
    y = te["is_laundering"]
    p = xgbm.predict(model, te[cols])

    evaluation.print_report(evaluation.report(y, p),
                            "XGBoost -- held-out test period")

    b = evaluation.baseline_amount_band(te, y)
    print(f"\nbaseline rule (amount 9k-20k)")
    print(f"  {b['n_flagged']:,} alerts   precision {b['precision']:.2%}   "
          f"recall {b['recall']:.1%}")

    print("\nalert volume by threshold")
    print(evaluation.alert_volume(p).to_string(index=False))

    print("\ncalibration (mean_score should track actual_rate)")
    print(evaluation.score_distribution(y, p).to_string())

    pat_path = config.DATA_PROCESSED / "patterns.parquet"
    if pat_path.exists():
        pat = pd.read_parquet(pat_path)
        print("\nrecall by typology (top 1000 alerts)")
        print(evaluation.per_typology(te, p, pat).to_string(index=False))


if __name__ == "__main__":
    main()