"""python -m ml.scripts.build_features"""
import time

import pandas as pd

from ml import config
from ml.features import build

log = config.get_logger("build_features")


def main():
    t0 = time.time()
    df = pd.read_parquet(config.DATA_PROCESSED / "transactions_clean.parquet")
    log.info("loaded %s rows", f"{len(df):,}")

    X = build.build_matrix(df)
    build.save(X)

    fams = build.split_by_family(X)
    print(f"\n{'=' * 52}")
    print(f"rows          {X.shape[0]:>12,}")
    print(f"features      {len(fams['xgboost']):>12}")
    for k in ["transaction", "behavioral", "graph"]:
        print(f"  {k:<12}{len(fams[k]):>12}")
    print(f"iforest cols  {len(fams['isolation_forest']):>12}")
    print(f"positives     {int(X['is_laundering'].sum()):>12,} "
          f"({X['is_laundering'].mean():.4%})")
    print(f"elapsed       {(time.time() - t0) / 60:>10.1f} min")
    print("=" * 52)


if __name__ == "__main__":
    main()