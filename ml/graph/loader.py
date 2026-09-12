"""Load accounts and transactions into Neo4j.

Only alerted accounts and their neighbourhoods go in -- loading all 5M
transactions is unnecessary, since the investigation layer never queries
the other 99%.
"""
import pandas as pd
from neo4j import GraphDatabase

from ml import config

log = config.get_logger("graph.loader")

SCHEMA = [
    "CREATE CONSTRAINT acct_id IF NOT EXISTS "
    "FOR (a:Account) REQUIRE a.id IS UNIQUE",
    "CREATE INDEX txn_time IF NOT EXISTS "
    "FOR ()-[t:SENT]-() ON (t.timestamp)",
    "CREATE INDEX txn_id IF NOT EXISTS "
    "FOR ()-[t:SENT]-() ON (t.txn_id)",
]

# AuraDB free tier has a ~2.8 GB transaction memory cap.
# Smaller batches with explicit commits keep each transaction well under it.
ACCT_BATCH = 1000
EDGE_BATCH = 500


def driver():
    return GraphDatabase.driver(
        config.neo4j_uri(),
        auth=(config.neo4j_user(), config.neo4j_password()))


def _run_schema(s, stmt: str) -> None:
    """Run a schema statement, ignoring 'already exists' errors."""
    try:
        s.run(stmt).consume()   # .consume() discards results without buffering
    except Exception as e:
        if "already exists" in str(e).lower() or "equivalent" in str(e).lower():
            pass
        else:
            raise


def load(df: pd.DataFrame, wipe: bool = True) -> None:
    with driver() as d:
        with d.session() as s:
            if wipe:
                # delete in batches to avoid OOM on large graphs
                log.info("wiping existing graph ...")
                while True:
                    result = s.run(
                        "MATCH (n) WITH n LIMIT 10000 DETACH DELETE n RETURN count(n) AS c"
                    )
                    deleted = result.single()["c"]
                    if deleted == 0:
                        break
                    log.info("  deleted %s nodes", f"{deleted:,}")
                log.info("wiped existing graph")

            for stmt in SCHEMA:
                _run_schema(s, stmt)

        # ── accounts ──────────────────────────────────────────────────────
        accts = pd.concat([df["from_id"], df["to_id"]]).unique().tolist()
        for i in range(0, len(accts), ACCT_BATCH):
            batch = accts[i:i + ACCT_BATCH]
            with d.session() as s:
                s.run(
                    "UNWIND $ids AS id MERGE (:Account {id: id})",
                    ids=batch,
                ).consume()
        log.info("merged %s accounts", f"{len(accts):,}")

        # ── edges ─────────────────────────────────────────────────────────
        rows = df[["txn_id", "from_id", "to_id", "amount_usd",
                   "timestamp", "is_laundering"]].copy()
        rows["timestamp"] = rows["timestamp"].astype(str)
        recs = rows.to_dict("records")

        for i in range(0, len(recs), EDGE_BATCH):
            batch = recs[i:i + EDGE_BATCH]
            with d.session() as s:
                s.run("""
                    UNWIND $rows AS r
                    MATCH (a:Account {id: r.from_id})
                    MATCH (b:Account {id: r.to_id})
                    CREATE (a)-[:SENT {
                        txn_id: r.txn_id, amount: r.amount_usd,
                        timestamp: r.timestamp, is_laundering: r.is_laundering
                    }]->(b)
                """, rows=batch).consume()
            if i and i % 50000 == 0:
                log.info("  %s edges", f"{i:,}")
        log.info("created %s transactions", f"{len(recs):,}")


def scope(df: pd.DataFrame, alert_accounts: set, hours: int = 192):
    """Alerted accounts plus one hop of counterparties."""
    m = df["from_id"].isin(alert_accounts) | df["to_id"].isin(alert_accounts)
    neigh = set(df.loc[m, "from_id"]) | set(df.loc[m, "to_id"])
    m2 = df["from_id"].isin(neigh) | df["to_id"].isin(neigh)
    out = df[m2]
    log.info("scoped to %s txns across %s accounts",
             f"{len(out):,}", f"{len(neigh):,}")
    return out