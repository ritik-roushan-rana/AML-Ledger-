"""Cypher queries for the investigation layer.

Each function answers one question an investigator asks. All return
plain dicts/DataFrames so the agent's tool layer can serialise them.
"""
import pandas as pd

from ml import config
from ml.graph.loader import driver

log = config.get_logger("graph.queries")


def _run(cypher: str, **params) -> pd.DataFrame:
    with driver() as d, d.session() as s:
        return pd.DataFrame([r.data() for r in s.run(cypher, **params)])


def money_flow(account: str, hops: int = 2, limit: int = 50) -> pd.DataFrame:
    """Where did money go from here, and how far."""
    return _run(f"""
        MATCH p = (a:Account {{id: $acct}})-[:SENT*1..{hops}]->(b:Account)
        WITH b, length(p) AS hops,
             reduce(s = 0.0, r IN relationships(p) | s + r.amount) AS total
        RETURN b.id AS account, hops, total
        ORDER BY total DESC LIMIT $limit
    """, acct=account, limit=limit)


def connected_accounts(account: str, limit: int = 25) -> pd.DataFrame:
    """Direct counterparties, both directions."""
    return _run("""
        MATCH (a:Account {id: $acct})-[r:SENT]-(b:Account)
        RETURN b.id AS account,
               count(r) AS n_txns,
               sum(r.amount) AS total,
               CASE WHEN startNode(r).id = $acct THEN 'paid to'
                    ELSE 'received from' END AS direction
        ORDER BY total DESC LIMIT $limit
    """, acct=account, limit=limit)


def find_cycles(account: str, max_hops: int = 6) -> pd.DataFrame:
    """Does money return to this account? The layering signature."""
    return _run(f"""
        MATCH p = (a:Account {{id: $acct}})-[:SENT*2..{max_hops}]->(a)
        WITH p, length(p) AS hops,
             [n IN nodes(p) | n.id] AS path,
             reduce(s = 0.0, r IN relationships(p) | s + r.amount) AS total
        RETURN hops, path, total
        ORDER BY hops LIMIT 10
    """, acct=account)


def shortest_path(a: str, b: str, max_hops: int = 6) -> pd.DataFrame:
    """How are two accounts linked?"""
    return _run(f"""
        MATCH p = shortestPath(
            (x:Account {{id: $a}})-[:SENT*1..{max_hops}]->(y:Account {{id: $b}}))
        RETURN length(p) AS hops, [n IN nodes(p) | n.id] AS path,
               reduce(s = 0.0, r IN relationships(p) | s + r.amount) AS total
    """, a=a, b=b)


def fraud_ring(account: str, min_size: int = 3) -> pd.DataFrame:
    """Accounts sharing counterparties with this one -- possible ring."""
    return _run("""
        MATCH (a:Account {id: $acct})-[:SENT]-(shared:Account)-[:SENT]-(peer:Account)
        WHERE peer.id <> $acct
        WITH peer, count(DISTINCT shared) AS shared_cp
        WHERE shared_cp >= $min_size
        RETURN peer.id AS account, shared_cp
        ORDER BY shared_cp DESC LIMIT 20
    """, acct=account, min_size=min_size)


def account_summary(account: str) -> dict:
    df = _run("""
        MATCH (a:Account {id: $acct})
        OPTIONAL MATCH (a)-[out:SENT]->()
        OPTIONAL MATCH ()-[inc:SENT]->(a)
        RETURN count(DISTINCT out) AS n_sent,
               count(DISTINCT inc) AS n_received,
               sum(DISTINCT out.amount) AS total_sent,
               sum(DISTINCT inc.amount) AS total_received
    """, acct=account)
    return df.iloc[0].to_dict() if len(df) else {}