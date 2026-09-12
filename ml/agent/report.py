"""Investigation report: assembles fusion + rules + SHAP into a case file.

Six sections, as specified in the architecture:
  why flagged / money flow / connected accounts / risk factors /
  supporting evidence / recommended action

Everything here is assembly. No new logic -- the detection decisions were
made upstream, and this file's only job is to make them readable.
"""
from datetime import datetime

import pandas as pd

from ml import config, explain
from ml.models import rules as rules_mod

log = config.get_logger("agent.report")

ACTION_TEXT = {
    "REPORT": "File a Suspicious Activity Report. Escalate to the MLRO.",
    "REVIEW": "Assign to an analyst for manual review within 48 hours.",
    "MONITOR": "No immediate action. Flag both accounts for 30-day watch.",
    "NONE": "No action required.",
}

# Measured precision per band on the held-out test period.
BAND_PRECISION = {"HIGH": "60%", "MEDIUM": "6%", "LOW": "1%", "CLEAR": "<1%"}


def build(txn, fused_row, drivers, flow, counterparties) -> str:
    """All inputs pre-computed. Returns markdown."""
    parts = [
        f"# Investigation report — {fused_row['band']} risk",
        "",
        f"**Case ID** `AML-{int(txn['txn_id']):08d}`  ",
        f"**Generated** {datetime.now():%Y-%m-%d %H:%M}  ",
        f"**Risk score** {fused_row['risk_score']:.1f} / 100  ",
        f"**Recommended action** {fused_row['action']}",
        "",
        "## Transaction",
        "",
        "| | |",
        "|---|---|",
        f"| Sender | `{txn['from_id']}` |",
        f"| Receiver | `{txn['to_id']}` |",
        f"| Amount | ${txn['amount_usd']:,.2f} |",
        f"| Timestamp | {txn['timestamp']:%Y-%m-%d %H:%M} |",
        f"| Cross-bank | {'yes' if txn['is_cross_bank'] else 'no'} |",
        "",
        "## 1. Why this was flagged",
        "",
        explain.format_drivers(drivers),
        "",
        "## 2. Money flow",
        "",
        _flow_section(txn, flow),
        "",
        "## 3. Connected accounts",
        "",
        _counterparty_section(counterparties),
        "",
        "## 4. Risk factors",
        "",
        _risk_section(txn, fused_row),
        "",
        "## 5. Supporting evidence",
        "",
        _evidence_section(fused_row),
        "",
        "## 6. Recommended action",
        "",
        f"**{fused_row['action']}** — {ACTION_TEXT[fused_row['action']]}",
        "",
        _caveat(fused_row["band"]),
    ]
    return "\n".join(parts)


# --------------------------------------------------------------------------
def _flow_section(txn, flow) -> str:
    if flow is None or flow.empty:
        return "_No prior activity for either account in the lookback window._"
    lines = ["| Time | From | To | Amount | Direction |",
             "|---|---|---|---|---|"]
    accts = {txn["from_id"], txn["to_id"]}
    for _, r in flow.iterrows():
        d = "in" if r["to_id"] in accts else "out"
        star = " **<-- this**" if r["txn_id"] == txn["txn_id"] else ""
        lines.append(f"| {r['timestamp']:%m-%d %H:%M} | `{r['from_id'][:16]}` | "
                     f"`{r['to_id'][:16]}` | ${r['amount_usd']:,.0f} | {d}{star} |")
    return "\n".join(lines)


def _counterparty_section(cp) -> str:
    if cp is None or cp.empty:
        return "_No counterparties in the lookback window._"
    lines = ["| Account | Payments | Total value | Role |", "|---|---|---|---|"]
    for _, r in cp.iterrows():
        lines.append(f"| `{r['account']}` | {int(r['n'])} | "
                     f"${r['total']:,.0f} | {r['role']} |")
    return "\n".join(lines)


def _risk_section(txn, fr) -> str:
    rows = [
        ("Model percentile", f"top {100 - fr['model_pct']:.2f}%"),
        ("Rules triggered", f"{int(fr['n_rules'])} of 9"),
        ("Rule score", f"{fr['rule_score']:.0f}"),
        ("Escalated by rules", "yes" if fr["escalated"] else "no"),
        *([("Behavioural anomaly",
            f"top {100 - fr['anomaly_pct']:.1f}% (Isolation Forest)")]
          if "anomaly_pct" in fr.index and pd.notna(fr["anomaly_pct"]) else []),
        ("Sender's recent activity",
         f"{int(txn['out_96h_count'])} payments to "
         f"{int(txn['out_96h_ncp'])} accounts in 96h"),
        ("Receiver's recent activity",
         f"{int(txn['in_96h_count'])} deposits from "
         f"{int(txn['in_96h_ncp'])} sources in 96h"),
    ]
    if txn.get("g_cycle_len", 0) > 0:
        rows.append(("Cycle detected",
                     f"funds return to sender in {int(txn['g_cycle_len'])} hops"))
    if txn.get("g_chain_depth", 0) >= 4:
        rows.append(("Layering chain",
                     f"{int(txn['g_chain_depth'])} hops forward"))
    return "\n".join(["| Factor | Value |", "|---|---|"] +
                     [f"| {k} | {v} |" for k, v in rows])


def _evidence_section(fr) -> str:
    fired = [c for c in rules_mod.DESCRIPTIONS
             if c in fr.index and bool(fr[c])]
    if not fired:
        return ("_No deterministic rules triggered. This alert rests on the "
                "model score alone and warrants closer analyst scrutiny._")
    return "\n".join(f"- **{c.replace('_', ' ')}** — "
                     f"{rules_mod.DESCRIPTIONS[c]}" for c in fired)


def _caveat(band: str) -> str:
    prec = BAND_PRECISION.get(band, "n/a")
    return (
        "---\n"
        "_Generated by an automated triage system. Model precision in the "
        f"{band} band is {prec} on held-out data. This is a prioritisation "
        "aid, not a determination of wrongdoing._"
    )