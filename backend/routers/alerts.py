"""Alert queue, detail, report and LLM investigation.

Detail and report are pure pandas over the preloaded frames (no Neo4j).
Investigate goes through agent.gather, which does hit the graph, so it
is queued on a thread and polled -- the POST returns 202 immediately.
"""
from datetime import datetime
from typing import Literal

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse

from ml import explain
from ml.agent import agent, context, report
from ml.models import rules as rules_mod

from backend import deps, schemas
from backend.deps import native

router = APIRouter(prefix="/api/alerts", tags=["alerts"])

SORT_FIELDS = {"risk_score", "timestamp", "amount_usd", "n_rules", "txn_id"}


# --- helpers ----------------------------------------------------------------
def _row_index(state: deps.AppState, txn_id: int):
    try:
        return state.txn_index.at[txn_id]
    except KeyError:
        raise HTTPException(404, f"txn {txn_id} not in the scored test period")


def _parts(state: deps.AppState, txn_id: int):
    """Everything detail and report both need, computed once per call."""
    idx = _row_index(state, txn_id)
    txn = state.X.loc[idx]
    fr = state.fused.loc[idx]
    drivers = explain.explain_one(state.explainer, state.X.loc[[idx], state.cols])
    flow = context.money_flow(state.raw, txn)
    cps = context.counterparties(state.raw, txn)
    return txn, fr, drivers, flow, cps


def _transaction(state: deps.AppState, txn: pd.Series) -> schemas.Transaction:
    t = {
        "txn_id": int(txn["txn_id"]), "from_id": txn["from_id"],
        "to_id": txn["to_id"], "amount_usd": float(txn["amount_usd"]),
        "timestamp": native(txn["timestamp"]),
        "is_cross_bank": bool(txn["is_cross_bank"]),
    }
    # Currencies, banks and payment format live only in the raw table.
    try:
        r = state.raw.loc[state.raw_index.at[t["txn_id"]]]
    except KeyError:
        return schemas.Transaction(**t)
    for k in ("from_bank", "to_bank", "currency_paid", "currency_received",
              "payment_format"):
        if k in r.index:
            t[k] = None if native(r[k]) is None else str(r[k])
    for k in ("amount_paid", "amount_received"):
        if k in r.index:
            t[k] = native(r[k])
    for k in ("is_cross_currency", "is_self_loop"):
        if k in r.index:
            t[k] = bool(r[k])
    return schemas.Transaction(**t)


def _flow_rows(txn: pd.Series, flow: pd.DataFrame) -> list[schemas.FlowRow]:
    accts = {txn["from_id"], txn["to_id"]}
    return [schemas.FlowRow(
        txn_id=int(r["txn_id"]), timestamp=native(r["timestamp"]),
        from_id=r["from_id"], to_id=r["to_id"],
        amount_usd=float(r["amount_usd"]),
        direction="in" if r["to_id"] in accts else "out",
        is_this=int(r["txn_id"]) == int(txn["txn_id"]),
    ) for _, r in flow.iterrows()]


# --- endpoints --------------------------------------------------------------
@router.get("", response_model=schemas.AlertPage)
def list_alerts(
    band: list[schemas.Band] | None = Query(
        None, description="repeatable; default = every band except CLEAR"),
    min_score: float | None = Query(None, ge=0, le=100),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    sort: str = Query("-risk_score",
                      description=f"one of {sorted(SORT_FIELDS)}, '-' prefix for desc"),
    state: deps.AppState = Depends(deps.get_state),
):
    desc = sort.startswith("-")
    key = sort.lstrip("-+")
    if key not in SORT_FIELDS:
        raise HTTPException(422, f"sort must be one of {sorted(SORT_FIELDS)}")

    a = state.alerts
    mask = a["band"].isin(band) if band else a["band"] != "CLEAR"
    if min_score is not None:
        mask &= a["risk_score"] >= min_score
    sel = a[mask].sort_values([key, "txn_id"], ascending=[not desc, True])

    total = len(sel)
    start = (page - 1) * page_size
    chunk = sel.iloc[start:start + page_size]
    items = [schemas.AlertSummary(
        txn_id=int(r.txn_id), from_id=r.from_id, to_id=r.to_id,
        amount_usd=float(r.amount_usd), timestamp=native(r.timestamp),
        risk_score=float(r.risk_score), band=r.band, action=r.action,
        n_rules=int(r.n_rules)) for r in chunk.itertuples()]
    return schemas.AlertPage(items=items, total=total, page=page,
                             page_size=page_size,
                             pages=max(1, -(-total // page_size)))


@router.get("/{txn_id}", response_model=schemas.AlertDetail)
def alert_detail(txn_id: int, state: deps.AppState = Depends(deps.get_state)):
    txn, fr, drivers, flow, cps = _parts(state, txn_id)

    fired = [schemas.RuleFired(name=c, description=d)
             for c, d in rules_mod.DESCRIPTIONS.items()
             if c in fr.index and bool(fr[c])]

    def _opt_int(col):
        v = native(txn.get(col))
        return int(v) if v is not None else None

    return schemas.AlertDetail(
        transaction=_transaction(state, txn),
        risk=schemas.Risk(
            risk_score=float(fr["risk_score"]), band=fr["band"],
            action=fr["action"], model_score=float(fr["model_score"]),
            model_pct=float(fr["model_pct"]), rule_score=float(fr["rule_score"]),
            n_rules=int(fr["n_rules"]), escalated=bool(fr["escalated"]),
            anomaly_pct=native(fr.get("anomaly_pct")),
            ground_truth_label=_opt_int("is_laundering")),
        rules_fired=fired,
        shap_drivers=[schemas.ShapDriver(
            feature=d["feature"], label=d["label"], shap=d["shap"],
            value=native(d["value"]) if isinstance(
                native(d["value"]), (int, float, str, type(None)))
            else str(d["value"])) for d in drivers],
        money_flow=_flow_rows(txn, flow),
        counterparties=[schemas.Counterparty(
            account=r["account"], n=int(r["n"]), total=float(r["total"]),
            role=r["role"]) for _, r in cps.iterrows()],
        activity=schemas.Activity(
            sender_96h_payments=int(txn["out_96h_count"]),
            sender_96h_counterparties=int(txn["out_96h_ncp"]),
            receiver_96h_deposits=int(txn["in_96h_count"]),
            receiver_96h_sources=int(txn["in_96h_ncp"]),
            cycle_len=_opt_int("g_cycle_len"),
            chain_depth=_opt_int("g_chain_depth")),
    )


@router.get("/{txn_id}/report", response_model=schemas.ReportResponse)
def alert_report(txn_id: int, state: deps.AppState = Depends(deps.get_state)):
    txn, fr, drivers, flow, cps = _parts(state, txn_id)
    md = report.build(txn, fr, drivers, flow, cps)
    # Splice in the narrative if an investigation has already run, same
    # as ml.scripts.investigate does for the CLI reports.
    job = state.jobs.get(txn_id)
    if job and job.status == "done" and job.narrative:
        md = md.replace("## 1. Why this was flagged",
                        f"## Investigator summary\n\n{job.narrative}\n\n"
                        "## 1. Why this was flagged")
    return schemas.ReportResponse(
        txn_id=txn_id, case_id=f"AML-{txn_id:08d}", band=fr["band"],
        generated_at=datetime.now(), markdown=md)


# --- investigation jobs -----------------------------------------------------
def _job_response(job: deps.Job) -> schemas.InvestigateResponse:
    return schemas.InvestigateResponse(
        txn_id=job.txn_id, job_id=job.job_id, status=job.status,
        narrative=job.narrative, evidence=job.evidence, error=job.error,
        started_at=job.started_at, finished_at=job.finished_at,
        poll_url=f"/api/alerts/{job.txn_id}/investigate")


def _run_job(state: deps.AppState, job: deps.Job) -> None:
    job.status = "running"
    try:
        ev = agent.gather(state.tools, job.txn_id)
        job.narrative = agent.narrate(ev)
        job.evidence = deps.deep_native(ev)
        job.status = "done"
    except Exception as e:           # surfaced to the poller, never lost
        job.error = f"{type(e).__name__}: {e}"
        job.status = "failed"
    finally:
        job.finished_at = datetime.now()


@router.post("/{txn_id}/investigate", response_model=schemas.InvestigateResponse,
             status_code=202,
             responses={200: {"model": schemas.InvestigateResponse,
                              "description": "already investigated"},
                        503: {"model": schemas.ErrorResponse}})
def investigate(txn_id: int, force: bool = Query(
                    False, description="re-run even if a result is cached"),
                state: deps.AppState = Depends(deps.get_state)):
    """Queue agent.gather + agent.narrate. Returns 202 with a poll URL,
    or 200 with the cached result if this alert was already narrated."""
    _row_index(state, txn_id)

    with state.jobs_lock:
        job = state.jobs.get(txn_id)
        if job and not force:
            if job.status == "done":
                return JSONResponse(status_code=200,
                                    content=_job_response(job).model_dump(mode="json"))
            if job.status in ("queued", "running"):
                return _job_response(job)              # still 202
        # gather() needs the graph; fail fast rather than queue a dead job
        neo = deps.neo4j_status()
        if not neo.reachable:
            raise HTTPException(503, f"Neo4j unavailable: {neo.error}")
        job = deps.Job(job_id=deps.new_job_id(), txn_id=txn_id)
        state.jobs[txn_id] = job
        state.executor.submit(_run_job, state, job)
    return _job_response(job)


@router.get("/{txn_id}/investigate", response_model=schemas.InvestigateResponse)
def investigate_status(txn_id: int,
                       state: deps.AppState = Depends(deps.get_state)):
    job = state.jobs.get(txn_id)
    if job is None:
        raise HTTPException(404, f"no investigation queued for txn {txn_id}; POST first")
    return _job_response(job)
