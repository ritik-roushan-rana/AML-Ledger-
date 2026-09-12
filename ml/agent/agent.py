"""Investigation agent: gathers evidence via tools, then narrates it.

Deliberately NOT autonomous tool-calling. The evidence set for an AML
alert is known in advance, so it is gathered deterministically and the
LLM gets one shot at narration. That makes output reproducible and
auditable -- both requirements in a regulated setting.

The LLM writes PROSE ONLY. Every figure comes from the tool layer; a
hallucinated amount in a suspicious activity report is a compliance
failure, not a cosmetic bug.
"""
import json

from ml import config
from ml.agent import prompts

log = config.get_logger("agent")


def gather(tools, txn_id: int) -> dict:
    """Run every relevant tool. This IS the tool layer in action."""
    txn = tools.transaction_search(txn_id)
    if "error" in txn:
        raise ValueError(txn["error"])

    sender, receiver = txn["from"], txn["to"]
    ev = {
        "transaction": txn,
        "risk": tools.risk_lookup(txn_id),
        "model": tools.xgboost_prediction(txn_id),
        "anomaly": tools.anomaly_detection(txn_id),
        "rules": tools.rule_check(txn_id),
        "shap": tools.shap_explanation(txn_id),
        "sender": tools.aggregation(sender),
        "receiver": tools.aggregation(receiver),
        "graph": {
            "receiver_counterparties": tools.graph_search(receiver, limit=10),
            "receiver_summary": tools.account_lookup(receiver),
            "cycles": tools.find_cycles(receiver),
            "ring": tools.community_detection(receiver),
        },
    }
    log.info("gathered evidence for txn %s", txn_id)
    return ev


def _fmt(obj) -> str:
    return json.dumps(obj, indent=2, default=str)


def narrate(evidence: dict, model: str = None) -> str:
    """Call Gemini. Falls back to a deterministic template if unavailable."""
    key = config.gemini_key()
    model = model or config.gemini_model()

    if not key or key == "your_key_here":
        log.warning("GEMINI_API_KEY not set -- using template fallback")
        return _fallback(evidence)

    user = prompts.USER_TEMPLATE.format(
        transaction=_fmt(evidence["transaction"]),
        risk=_fmt(evidence["risk"]),
        model=_fmt(evidence.get("model", {})),
        anomaly=_fmt(evidence.get("anomaly", {})),
        rules=_fmt(evidence["rules"]),
        shap=_fmt(evidence["shap"]),
        sender=_fmt(evidence["sender"]),
        receiver=_fmt(evidence["receiver"]),
        graph=_fmt(evidence["graph"]),
    )

    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=key)
        resp = client.models.generate_content(
            model=model,
            contents=user,
            config=types.GenerateContentConfig(
                system_instruction=prompts.SYSTEM,
                max_output_tokens=1200,
                temperature=0.2,   # low: an audit trail must be reproducible
            ),
        )
        log.info("narrated via %s", model)
        return resp.text.strip()
    except Exception as e:
        log.warning("gemini call failed (%s) -- using fallback", e)
        return _fallback(evidence)


def _fallback(ev: dict) -> str:
    """Deterministic narrative when no LLM is available. The demo must not
    depend on a network call."""
    t, r = ev["transaction"], ev["risk"]
    rcv = ev["receiver"]
    fired = ev["rules"].get("descriptions", [])

    lines = [
        f"A payment of ${t['amount_usd']:,.2f} moved from {t['from']} to "
        f"{t['to']} on {t['timestamp'][:16]}. The system scored it "
        f"{r['risk_score']:.1f} of 100, placing it in the {r['band']} band "
        f"(top {100 - r['model_percentile']:.2f}% of all scored transactions)."
    ]

    if rcv.get("total_received"):
        ratio = rcv.get("total_sent", 0) / max(rcv["total_received"], 1)
        lines.append(
            f"The receiving account has taken in ${rcv['total_received']:,.0f} "
            f"across {rcv['n_received']} payments from "
            f"{rcv['distinct_sources']} distinct sources, while forwarding "
            f"${rcv.get('total_sent', 0):,.0f}. "
            + ("Funds are being retained rather than moved on, which is "
               "consistent with a collection account at the end of a gather "
               "pattern." if ratio < 0.1 else
               "Inflow and outflow are broadly balanced, consistent with a "
               "pass-through or intermediary role."))

    if fired:
        lines.append("Deterministic checks triggered: " + "; ".join(fired) + ".")

    an = ev.get("anomaly", {})
    if an.get("unusual"):
        lines.append(f"Independently of the supervised model, the account's "
                     f"behaviour sits in the top {100 - an['anomaly_percentile']:.1f}% "
                     "most unusual seen during training.")

    drivers = [d["reason"] for d in ev["shap"][:3]]
    if drivers:
        lines.append("The model weighted most heavily: " +
                     "; ".join(drivers) + ".")

    if ev["graph"]["cycles"]:
        lines.append(f"Graph traversal found {len(ev['graph']['cycles'])} "
                     "path(s) returning funds to the originating account, "
                     "consistent with cycling.")

    lines.append(f"Recommended action: {r['action']}. This is a prioritisation "
                 "aid and warrants review by a human investigator before any "
                 "determination is made.")
    return "\n\n".join(lines)