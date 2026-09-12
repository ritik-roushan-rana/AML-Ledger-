"""python -m ml.scripts.load_graph"""
import pandas as pd

from ml import config
from ml.features import build
from ml.graph import loader
from ml.models import fusion
from ml.models import xgb as xgbm

log = config.get_logger("load_graph")


def main():
    print("starting...")
    try:
        with loader.driver() as d:
            d.verify_connectivity()
        log.info("neo4j reachable")
    except Exception as e:
        raise SystemExit(f"\nCannot reach Neo4j: {e}\n"
                         "Start it:  neo4j start\n"
                         "Set pass:  export NEO4J_PASSWORD=...\n")

    X = build.load()
    raw = pd.read_parquet(config.DATA_PROCESSED / "transactions_clean.parquet")
    te = X[X["timestamp"] > X["timestamp"].quantile(0.85)]

    model, cols = xgbm.load()
    fused = fusion.fuse(te, xgbm.predict(model, te[cols]))

    alerted = fused["band"].isin(["HIGH", "MEDIUM"])
    accts = set(te.loc[alerted, "from_id"]) | set(te.loc[alerted, "to_id"])
    log.info("%s alerted accounts", f"{len(accts):,}")

    scoped = loader.scope(raw, accts)
    loader.load(scoped)
    print(f"\nloaded {len(scoped):,} transactions into Neo4j")


if __name__ == "__main__":
    main()