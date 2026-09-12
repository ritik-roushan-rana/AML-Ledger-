"""Natural-language questions answered by the tool-using agent.

Same 202 + poll shape as /investigate: a question can trigger several
graph queries (find_cycles alone can take 30s), so it never blocks the
request thread.
"""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse

from ml import config
from ml.agent import ask as ask_mod

from backend import deps, schemas

router = APIRouter(prefix="/api/ask", tags=["ask"])

MAX_JOBS = 200


def _resp(job: deps.AskJob) -> schemas.AskResponse:
    return schemas.AskResponse(
        job_id=job.job_id, status=job.status, question=job.question,
        answer=job.answer, trace=job.trace, rounds=job.rounds, error=job.error,
        started_at=job.started_at, finished_at=job.finished_at,
        poll_url=f"/api/ask/{job.job_id}")


def _run(state: deps.AppState, job: deps.AskJob) -> None:
    job.status = "running"
    try:
        # append live so the poller sees each call as it happens
        out = ask_mod.ask(state.tools, job.question, job.context or None,
                          on_call=lambda e: job.trace.append(deps.deep_native(e)))
        job.answer, job.rounds = out["answer"], out["rounds"]
        job.status = "done"
    except Exception as e:
        job.error = f"{type(e).__name__}: {e}"
        job.status = "failed"
    finally:
        job.finished_at = datetime.now()


@router.post("", response_model=schemas.AskResponse, status_code=202,
             responses={503: {"model": schemas.ErrorResponse}})
def ask(req: schemas.AskRequest, state: deps.AppState = Depends(deps.get_state)):
    key = config.gemini_key()
    if not key or key == "your_key_here":
        raise HTTPException(503, "GEMINI_API_KEY not configured -- the ask agent needs an LLM")

    context = {}
    if req.txn_id is not None:
        context["txn_id"] = req.txn_id
    if req.account_id:
        context["account_id"] = req.account_id

    job = deps.AskJob(job_id=deps.new_job_id(), question=req.question.strip(),
                      context=context)
    with state.jobs_lock:
        state.ask_jobs[job.job_id] = job
        while len(state.ask_jobs) > MAX_JOBS:
            state.ask_jobs.popitem(last=False)
    state.executor.submit(_run, state, job)
    return _resp(job)


@router.get("/{job_id}", response_model=schemas.AskResponse)
def ask_status(job_id: str, state: deps.AppState = Depends(deps.get_state)):
    job = state.ask_jobs.get(job_id)
    if job is None:
        raise HTTPException(404, f"no ask job {job_id}")
    return JSONResponse(status_code=200, content=_resp(job).model_dump(mode="json"))
