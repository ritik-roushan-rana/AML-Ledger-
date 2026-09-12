"""Tool layer for the investigation agent.

Every tool is a thin wrapper over an existing module -- the agent owns
no detection logic. That separation matters: the same functions serve
the CLI, the report builder, and the LLM, so there is one implementation
of "what does this account look like" rather than three.
"""
import json

import pandas as pd

from ml import config, explain
from ml.agent import context
from ml.graph import queries
from ml.models import rules as rules_mod

log = config.get_logger("agent.tools")


class ToolBox:
    """Holds the loaded artifacts so tools stay cheap to call."""

    def __init__(self, X, raw, fused, model, cols, explainer):
        self.X, self.raw, self.fused = X, raw, fused
        self.model, self.cols, self.explainer = model, cols, explainer

    # --- transaction / account lookup ---------------------------------
    def transaction_search(self, txn_id: int) -> dict:
        m = self.X["txn_id"] == txn_id
        if not m.any():
            return {"error": f"txn {txn_id} not found"}
        t = self.X[m].iloc[0]
        return {"txn_id": int(t["txn_id"]), "from": t["from_id"],
                "to": t["to_id"], "amount_usd": round(float(t["amount_usd"]), 2),
                "timestamp": str(t["timestamp"]),
                "cross_bank": bool(t["is_cross_bank"])}

    def account_lookup(self, account: str) -> dict:
        return queries.account_summary(account)

    def aggregation(self, account: str, hours: int = 96) -> dict:
        m = ((self.raw["from_id"] == account) | (self.raw["to_id"] == account))
        d = self.raw[m]
        if d.empty:
            return {"error": "no activity"}
        sent = d[d["from_id"] == account]
        recv = d[d["to_id"] == account]
        return {
            "n_sent": len(sent), "n_received": len(recv),
            "total_sent": round(float(sent["amount_usd"].sum()), 2),
            "total_received": round(float(recv["amount_usd"].sum()), 2),
            "distinct_destinations": int(sent["to_id"].nunique()),
            "distinct_sources": int(recv["from_id"].nunique()),
        }

    # --- scoring -------------------------------------------------------
    def risk_lookup(self, txn_id: int) -> dict:
        idx = self.X.index[self.X["txn_id"] == txn_id]
        if not len(idx) or idx[0] not in self.fused.index:
            return {"error": "not scored"}
        f = self.fused.loc[idx[0]]
        return {"risk_score": round(float(f["risk_score"]), 2),
                "band": f["band"], "action": f["action"],
                "model_percentile": round(float(f["model_pct"]), 3),
                "rules_fired": int(f["n_rules"]),
                "escalated": bool(f["escalated"])}

    def xgboost_prediction(self, txn_id: int) -> dict:
        """Raw supervised output. Kept separate from risk_lookup because
        the probability is uncalibrated and must not be read as a rate."""
        idx = self.X.index[self.X["txn_id"] == txn_id]
        if not len(idx) or idx[0] not in self.fused.index:
            return {"error": "not scored"}
        f = self.fused.loc[idx[0]]
        return {"probability": round(float(f["model_score"]), 4),
                "percentile": round(float(f["model_pct"]), 3),
                "note": "probability is uncalibrated; rank by percentile"}

    def anomaly_detection(self, txn_id: int) -> dict:
        """Isolation Forest percentile on behavioral features. Evidence
        only -- does not feed the band."""
        idx = self.X.index[self.X["txn_id"] == txn_id]
        if not len(idx) or "anomaly_pct" not in self.fused.columns:
            return {"error": "no anomaly score"}
        pct = float(self.fused.loc[idx[0], "anomaly_pct"])
        return {"anomaly_percentile": round(pct, 2),
                "unusual": pct >= 99.0,
                "basis": "behavioral features vs training-period accounts"}

    def rule_check(self, txn_id: int) -> dict:
        idx = self.X.index[self.X["txn_id"] == txn_id]
        if not len(idx):
            return {"error": "not found"}
        f = self.fused.loc[idx[0]]
        fired = [c for c in rules_mod.DESCRIPTIONS if bool(f.get(c, False))]
        return {"fired": fired,
                "descriptions": [rules_mod.DESCRIPTIONS[c] for c in fired]}

    def shap_explanation(self, txn_id: int, top: int = 6) -> list[dict]:
        idx = self.X.index[self.X["txn_id"] == txn_id]
        if not len(idx):
            return [{"error": "not found"}]
        d = explain.explain_one(self.explainer, self.X.loc[[idx[0]], self.cols], top)
        return [{"reason": x["label"], "value": _fmt(x["value"]),
                 "impact": round(x["shap"], 3)} for x in d]

    # --- graph ----------------------------------------------------------
    def graph_search(self, account: str, limit: int = 15) -> list[dict]:
        return queries.connected_accounts(account, limit).to_dict("records")

    def path_analysis(self, a: str, b: str) -> list[dict]:
        return queries.shortest_path(a, b).to_dict("records")

    def money_flow(self, account: str, hops: int = 2) -> list[dict]:
        return queries.money_flow(account, hops).to_dict("records")

    def find_cycles(self, account: str) -> list[dict]:
        return queries.find_cycles(account).to_dict("records")

    def community_detection(self, account: str) -> list[dict]:
        return queries.fraud_ring(account).to_dict("records")


def _fmt(v):
    if isinstance(v, (int, float)):
        return round(float(v), 2)
    return str(v)


SPECS = [
    ("transaction_search", "Look up one transaction by txn_id.",
     {"txn_id": "integer"}),
    ("account_lookup", "Totals sent and received for an account.",
     {"account": "string"}),
    ("aggregation", "Counts and distinct counterparties for an account.",
     {"account": "string", "hours": "integer"}),
    ("risk_lookup", "Risk score, band and action for a transaction.",
     {"txn_id": "integer"}),
    ("xgboost_prediction", "Raw supervised model probability and percentile.",
     {"txn_id": "integer"}),
    ("anomaly_detection", "Isolation Forest anomaly percentile (evidence only).",
     {"txn_id": "integer"}),
    ("rule_check", "Which deterministic rules fired.", {"txn_id": "integer"}),
    ("shap_explanation", "Top model drivers for a transaction.",
     {"txn_id": "integer", "top": "integer"}),
    ("graph_search", "Direct counterparties from the graph.",
     {"account": "string", "limit": "integer"}),
    ("path_analysis", "Shortest path between two accounts.",
     {"a": "string", "b": "string"}),
    ("money_flow", "Where funds travelled, up to N hops.",
     {"account": "string", "hops": "integer"}),
    ("find_cycles", "Paths returning to the same account.",
     {"account": "string"}),
    ("community_detection", "Accounts sharing counterparties.",
     {"account": "string"}),
]