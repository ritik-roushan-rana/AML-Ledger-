"""Raw transaction lookup over the full 5M-row table (not just the
scored test period). Where a row IS in the test period its band is
attached so the UI can link through to the alert."""
import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Query

from backend import deps, schemas
from backend.deps import native

router = APIRouter(prefix="/api/transactions", tags=["transactions"])

RAW_COLS = ["txn_id", "timestamp", "from_id", "to_id", "from_bank", "to_bank",
            "amount_usd", "amount_paid", "currency_paid", "amount_received",
            "currency_received", "payment_format", "is_cross_bank",
            "is_cross_currency", "is_self_loop"]


def _to_model(state: deps.AppState, r: pd.Series) -> schemas.RawTransaction:
    d = {k: native(r[k]) for k in RAW_COLS if k in r.index}
    for k in ("from_bank", "to_bank"):
        if d.get(k) is not None:
            d[k] = str(d[k])
    for k in ("is_cross_bank", "is_cross_currency", "is_self_loop"):
        if d.get(k) is not None:
            d[k] = bool(d[k])
    tid = d["txn_id"]
    scored = tid in state.txn_index.index
    if scored:
        f = state.fused.loc[state.txn_index.at[tid]]
        d.update(risk_score=float(f["risk_score"]), band=f["band"])
    return schemas.RawTransaction(scored=scored, **d)


@router.get("", response_model=schemas.TransactionPage)
def list_transactions(
    account: str = Query(..., description="account id as sender or receiver"),
    direction: str = Query("both", pattern="^(both|sent|received)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    state: deps.AppState = Depends(deps.get_state),
):
    raw = state.raw
    if direction == "sent":
        m = raw["from_id"] == account
    elif direction == "received":
        m = raw["to_id"] == account
    else:
        m = (raw["from_id"] == account) | (raw["to_id"] == account)
    sel = raw[m].sort_values("timestamp", ascending=False)
    total = len(sel)
    if total == 0:
        raise HTTPException(404, f"no transactions for account {account}")
    chunk = sel.iloc[(page - 1) * page_size:page * page_size]
    return schemas.TransactionPage(
        items=[_to_model(state, r) for _, r in chunk.iterrows()],
        total=total, page=page, page_size=page_size,
        pages=max(1, -(-total // page_size)))


@router.get("/{txn_id}", response_model=schemas.RawTransaction)
def get_transaction(txn_id: int, state: deps.AppState = Depends(deps.get_state)):
    try:
        r = state.raw.loc[state.raw_index.at[txn_id]]
    except KeyError:
        raise HTTPException(404, f"txn {txn_id} not found")
    return _to_model(state, r)
