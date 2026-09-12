"""Account summary and graph neighbourhood.

The pandas half (activity, worst band) never needs Neo4j. The graph half
degrades: /accounts/{id} returns graph_available=false with the error,
/accounts/{id}/graph returns 503 because it has nothing else to offer.
"""
from fastapi import APIRouter, Depends, HTTPException, Query

from ml.graph import loader

from backend import deps, schemas
from backend.deps import native

router = APIRouter(prefix="/api/accounts", tags=["accounts"])


def _known(state: deps.AppState, account_id: str) -> bool:
    return (account_id in state.account_risk.index
            or (state.raw["from_id"] == account_id).any()
            or (state.raw["to_id"] == account_id).any())


def _risk(state: deps.AppState, account_id: str) -> schemas.AccountRisk:
    if account_id not in state.account_risk.index:
        return schemas.AccountRisk(n_scored_txns=0, n_alerts=0)
    r = state.account_risk.loc[account_id]
    return schemas.AccountRisk(
        n_scored_txns=int(r["n_scored_txns"]), n_alerts=int(r["n_alerts"]),
        max_risk_score=native(r["max_risk_score"]), worst_band=r["worst_band"])


@router.get("/{account_id}", response_model=schemas.AccountResponse)
def account(account_id: str,
            refresh: bool = Query(False, description="bypass the response cache"),
            state: deps.AppState = Depends(deps.get_state)):
    if not _known(state, account_id):
        raise HTTPException(404, f"account {account_id} not found")
    key = ("account", account_id)
    if not refresh and (hit := state.cached(key)) and hit.graph_available:
        return hit

    agg = state.tools.aggregation(account_id)
    if "error" in agg:
        agg = dict(n_sent=0, n_received=0, total_sent=0.0, total_received=0.0,
                   distinct_destinations=0, distinct_sources=0)

    resp = schemas.AccountResponse(
        account_id=account_id,
        activity=schemas.AccountActivity(**agg),
        risk=_risk(state, account_id),
        graph_available=True)

    tools = state.tools
    try:
        summ = tools.account_lookup(account_id)
        resp.graph_summary = schemas.GraphSummary(
            **{k: native(v) for k, v in summ.items()})
        resp.counterparties = [schemas.GraphCounterparty(**r)
                               for r in deps.deep_native(tools.graph_search(account_id, 25))]
        resp.cycles = [schemas.Cycle(**r)
                       for r in deps.deep_native(tools.find_cycles(account_id))]
        resp.ring = [schemas.RingPeer(**r)
                     for r in deps.deep_native(tools.community_detection(account_id))]
    except deps.NEO4J_ERRORS as e:
        resp.graph_available = False
        resp.graph_error = f"{type(e).__name__}: {e}"
    state.remember(key, resp)
    return resp


# --- neighbourhood for visualisation ----------------------------------------
_FRONTIER = """
    MATCH (a:Account)-[r:SENT]-(b:Account)
    WHERE a.id IN $ids AND NOT b.id IN $seen
    WITH b, count(r) AS n
    ORDER BY n DESC LIMIT $limit
    RETURN b.id AS id
"""
_EDGES = """
    MATCH (x:Account)-[r:SENT]->(y:Account)
    WHERE x.id IN $ids AND y.id IN $ids
    RETURN x.id AS source, y.id AS target, r.txn_id AS txn_id,
           r.amount AS amount, r.timestamp AS timestamp,
           r.is_laundering AS is_laundering
    ORDER BY r.amount DESC LIMIT $limit
"""


def _neighbourhood(account_id: str, hops: int, limit: int):
    """Breadth-first, one query per hop so a hub cannot blow up the
    traversal; then every SENT edge among the collected node set."""
    with loader.driver() as d, d.session() as s:
        if not s.run("MATCH (a:Account {id: $id}) RETURN 1 LIMIT 1",
                     id=account_id).single():
            return None
        hop_of = {account_id: 0}
        frontier = [account_id]
        truncated = False
        for h in range(1, hops + 1):
            budget = limit - (len(hop_of) - 1)
            if budget <= 0 or not frontier:
                truncated = truncated or budget <= 0
                break
            rows = s.run(_FRONTIER, ids=frontier, seen=list(hop_of),
                         limit=budget + 1).data()
            if len(rows) > budget:
                truncated, rows = True, rows[:budget]
            frontier = [r["id"] for r in rows]
            hop_of.update({i: h for i in frontier})

        edge_cap = limit * 20
        edges = s.run(_EDGES, ids=list(hop_of), limit=edge_cap + 1).data()
        if len(edges) > edge_cap:
            truncated, edges = True, edges[:edge_cap]
    return hop_of, edges, truncated


@router.get("/{account_id}/graph", response_model=schemas.GraphResponse)
def account_graph(
    account_id: str,
    hops: int = Query(1, ge=1, le=2),
    limit: int = Query(50, ge=1, le=500, description="max neighbour nodes"),
    refresh: bool = Query(False, description="bypass the response cache"),
    state: deps.AppState = Depends(deps.get_state),
):
    key = ("graph", account_id, hops, limit)
    if not refresh and (hit := state.cached(key)):
        return hit
    try:
        found = _neighbourhood(account_id, hops, limit)
    except deps.NEO4J_ERRORS as e:
        raise deps.neo4j_unavailable(e)
    if found is None:
        raise HTTPException(404, f"account {account_id} not in the graph "
                                 "(only alerted neighbourhoods are loaded)")
    hop_of, raw_edges, truncated = found

    ar = state.account_risk
    nodes = []
    for nid, hop in hop_of.items():
        n = schemas.GraphNode(id=nid, hop=hop, is_root=hop == 0)
        if nid in ar.index:
            r = ar.loc[nid]
            n.n_scored_txns = int(r["n_scored_txns"])
            n.n_alerts = int(r["n_alerts"])
            n.max_risk_score = native(r["max_risk_score"])
            n.worst_band = r["worst_band"]
        nodes.append(n)

    fused, tix = state.fused, state.txn_index
    edges = []
    for e in raw_edges:
        tid = native(e.get("txn_id"))
        ge = schemas.GraphEdge(source=e["source"], target=e["target"],
                               txn_id=int(tid) if tid is not None else None,
                               amount=float(e["amount"] or 0.0),
                               timestamp=None if e.get("timestamp") is None
                               else str(e["timestamp"]),
                               is_laundering=None if e.get("is_laundering") is None
                               else bool(e["is_laundering"]))
        if tid is not None and tid in tix.index:
            f = fused.loc[tix.at[tid]]
            ge.risk_score, ge.band = float(f["risk_score"]), f["band"]
        edges.append(ge)

    resp = schemas.GraphResponse(account_id=account_id, hops=hops,
                                 nodes=nodes, edges=edges, truncated=truncated)
    state.remember(key, resp)
    return resp
