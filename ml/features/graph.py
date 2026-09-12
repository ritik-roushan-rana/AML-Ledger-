"""Graph-structural features. Multi-hop only.

Simple degree/fan-in/fan-out is already covered by behavioral.py --
do not rebuild it here. This file computes what a per-account rolling
window cannot see: paths, cycles, and community structure.

Per-typology evaluation showed the model catches fan-in at 53% and
fan-out at 49% but STACK at 18% and CYCLE at 21%. Those two are
multi-hop structures, which is what g_chain_depth and g_cycle_len
are here to detect.

Leakage rule: the graph for a transaction at time t is built only from
edges in the PREVIOUS time bucket, so a transaction can never see its
own edge or anything after it.
"""
import networkx as nx
import numpy as np
import pandas as pd

from ml import config

log = config.get_logger("features.graph")

COLS = ["g_in_deg", "g_out_deg", "g_pagerank", "g_in_deg_dst",
        "g_out_deg_dst", "g_pagerank_dst", "g_comm_size", "g_same_comm",
        "g_recip", "g_two_hop_back", "g_triangle", "g_chain_depth",
        "g_cycle_len"]


def build(df: pd.DataFrame, bucket_hours: int = 24) -> pd.DataFrame:
    """One graph per time bucket, features assigned to the NEXT bucket."""
    df = df.sort_values("timestamp")
    f = pd.DataFrame(index=df.index, dtype="float64")
    for c in COLS:
        f[c] = 0.0

    t0 = df["timestamp"].min()
    bucket = (((df["timestamp"] - t0).dt.total_seconds()
               // (bucket_hours * 3600)).astype("int32"))
    n_buckets = int(bucket.max()) + 1
    log.info("%d buckets of %dh", n_buckets, bucket_hours)

    for b in range(1, n_buckets):
        past = df[bucket == b - 1]
        cur_idx = df.index[bucket == b]
        if past.empty or len(cur_idx) == 0:
            continue

        G = nx.DiGraph()
        agg = past.groupby(["from_id", "to_id"])["amount_usd"].agg(["size", "sum"])
        G.add_weighted_edges_from(
            (u, v, float(r["sum"])) for (u, v), r in agg.iterrows())
        if G.number_of_nodes() == 0:
            continue

        indeg = dict(G.in_degree())
        outdeg = dict(G.out_degree())
        pr = nx.pagerank(G, alpha=0.85, max_iter=30, tol=1e-4)

        U = G.to_undirected()
        comm_of, comm_size = _communities(U)
        tri = nx.triangles(U)

        cur = df.loc[cur_idx]
        src, dst = cur["from_id"], cur["to_id"]

        f.loc[cur_idx, "g_in_deg"] = src.map(indeg).fillna(0).values
        f.loc[cur_idx, "g_out_deg"] = src.map(outdeg).fillna(0).values
        f.loc[cur_idx, "g_pagerank"] = src.map(pr).fillna(0).values
        f.loc[cur_idx, "g_in_deg_dst"] = dst.map(indeg).fillna(0).values
        f.loc[cur_idx, "g_out_deg_dst"] = dst.map(outdeg).fillna(0).values
        f.loc[cur_idx, "g_pagerank_dst"] = dst.map(pr).fillna(0).values
        f.loc[cur_idx, "g_triangle"] = src.map(tri).fillna(0).values

        cs, cd = src.map(comm_of), dst.map(comm_of)
        f.loc[cur_idx, "g_comm_size"] = cs.map(comm_size).fillna(0).values
        f.loc[cur_idx, "g_same_comm"] = (cs.notna() & (cs == cd)).astype(float).values

        edges = set(G.edges())
        f.loc[cur_idx, "g_recip"] = [
            1.0 if (v, u) in edges else 0.0 for u, v in zip(src, dst)]
        f.loc[cur_idx, "g_two_hop_back"] = [
            _two_hop(G, v, u) for u, v in zip(src, dst)]

        depth, cyc = _path_features(G, src.values, dst.values)
        f.loc[cur_idx, "g_chain_depth"] = depth
        f.loc[cur_idx, "g_cycle_len"] = cyc

        if b % 5 == 0:
            log.info("bucket %d/%d", b, n_buckets)

    f["g_deg_ratio"] = (f["g_out_deg"] /
                        f["g_in_deg"].replace(0, np.nan)).fillna(0).clip(upper=50)
    f["g_pr_ratio"] = (f["g_pagerank_dst"] /
                       f["g_pagerank"].replace(0, np.nan)).fillna(0).clip(upper=50)

    log.info("graph features: %d columns", f.shape[1])
    return f


# --------------------------------------------------------------------------
def _communities(U):
    """Connected components as a cheap stand-in for community detection."""
    comm_of, comm_size = {}, {}
    for i, comp in enumerate(nx.connected_components(U)):
        comm_size[i] = len(comp)
        for node in comp:
            comm_of[node] = i
    return comm_of, comm_size


def _two_hop(G, a, b) -> float:
    """Is there a path a -> x -> b? Capped for speed."""
    if a not in G or b not in G:
        return 0.0
    succ = G._succ.get(a, {})
    if len(succ) > 200:
        return 0.0
    pred = G._pred.get(b, {})
    return 1.0 if succ.keys() & pred.keys() else 0.0


def _chain_depth(G, node, max_depth=6) -> int:
    """Longest forward chain from this node. Detects STACK / layering.

    Iterative BFS rather than recursion -- a dense node would blow the
    stack otherwise. Returns hop count, capped at max_depth.
    """
    if node not in G:
        return 0
    frontier, seen, depth = {node}, {node}, 0
    for _ in range(max_depth):
        nxt = set()
        for n in frontier:
            succ = G._succ.get(n, {})
            if len(succ) > 50:
                continue
            nxt |= set(succ) - seen
        if not nxt:
            break
        seen |= nxt
        frontier = nxt
        depth += 1
    return depth


def _on_cycle(G, u, v, max_hops=6) -> float:
    """Is there a path v -> ... -> u? That closes a CYCLE through this edge.

    Returns the hop count of the return path, 0 if none found.
    """
    if u not in G or v not in G:
        return 0.0
    frontier, seen = {v}, {v}
    for hop in range(max_hops):
        nxt = set()
        for n in frontier:
            succ = G._succ.get(n, {})
            if len(succ) > 100:
                continue
            if u in succ:
                return float(hop + 1)
            nxt |= set(succ) - seen
        if not nxt:
            break
        seen |= nxt
        frontier = nxt
    return 0.0


def _path_features(G, src, dst):
    """(chain_depth, cycle_len) for every row in the current bucket."""
    depth_cache, cyc_cache = {}, {}
    depths, cycles = [], []
    for u, v in zip(src, dst):
        if v not in depth_cache:
            depth_cache[v] = _chain_depth(G, v)
        depths.append(depth_cache[v])

        key = (u, v)
        if key not in cyc_cache:
            cyc_cache[key] = _on_cycle(G, u, v)
        cycles.append(cyc_cache[key])
    return np.array(depths, dtype=float), np.array(cycles, dtype=float)