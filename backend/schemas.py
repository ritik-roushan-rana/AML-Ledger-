"""Pydantic response models. Every endpoint returns one of these.

Kept deliberately flat -- the frontend consumes them directly, so the
shapes here are the API contract.
"""
from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

Band = Literal["HIGH", "MEDIUM", "LOW", "CLEAR"]
Action = Literal["REPORT", "REVIEW", "MONITOR", "NONE"]
JobStatus = Literal["queued", "running", "done", "failed"]


# --- health / stats ---------------------------------------------------------
class Neo4jStatus(BaseModel):
    reachable: bool
    uri: str
    latency_ms: float | None = None
    error: str | None = None


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded", "error"]
    model_loaded: bool
    load_error: str | None = None
    anomaly_model_loaded: bool = False
    anomaly_model_error: str | None = None
    neo4j: Neo4jStatus
    llm_configured: bool
    rows_scored: int
    rows_total: int
    period_start: datetime | None = None
    period_end: datetime | None = None
    uptime_seconds: float


class BandStat(BaseModel):
    band: Band
    count: int
    share: float = Field(description="fraction of scored rows in this band")
    positives: int
    precision: float | None = Field(
        description="labelled-positive rate within the band (None if empty)")


class DailyVolume(BaseModel):
    date: date
    total: int
    HIGH: int
    MEDIUM: int
    LOW: int


class StatsResponse(BaseModel):
    rows_scored: int
    n_positives: int
    base_rate: float
    alert_count: int = Field(description="rows in HIGH/MEDIUM/LOW")
    period_start: datetime
    period_end: datetime
    bands: list[BandStat]
    daily_alerts: list[DailyVolume]


# --- alerts -----------------------------------------------------------------
class AlertSummary(BaseModel):
    txn_id: int
    from_id: str
    to_id: str
    amount_usd: float
    timestamp: datetime
    risk_score: float
    band: Band
    action: Action
    n_rules: int


class AlertPage(BaseModel):
    items: list[AlertSummary]
    total: int
    page: int
    page_size: int
    pages: int


class Transaction(BaseModel):
    txn_id: int
    from_id: str
    to_id: str
    amount_usd: float
    timestamp: datetime
    is_cross_bank: bool
    is_cross_currency: bool | None = None
    is_self_loop: bool | None = None
    from_bank: str | None = None
    to_bank: str | None = None
    currency_paid: str | None = None
    currency_received: str | None = None
    amount_paid: float | None = None
    amount_received: float | None = None
    payment_format: str | None = None


class Risk(BaseModel):
    risk_score: float
    band: Band
    action: Action
    model_score: float
    model_pct: float
    rule_score: float
    n_rules: int
    escalated: bool
    anomaly_pct: float | None = Field(
        default=None, description="Isolation Forest percentile, evidence only")
    ground_truth_label: int | None = Field(
        default=None, description="is_laundering from the dataset, for evaluation only")


class RuleFired(BaseModel):
    name: str
    description: str


class ShapDriver(BaseModel):
    feature: str
    label: str
    shap: float
    value: float | str | None = None


class FlowRow(BaseModel):
    txn_id: int
    timestamp: datetime
    from_id: str
    to_id: str
    amount_usd: float
    direction: Literal["in", "out"]
    is_this: bool


class Counterparty(BaseModel):
    account: str
    n: int
    total: float
    role: str


class Activity(BaseModel):
    sender_96h_payments: int
    sender_96h_counterparties: int
    receiver_96h_deposits: int
    receiver_96h_sources: int
    cycle_len: int | None = None
    chain_depth: int | None = None


class AlertDetail(BaseModel):
    transaction: Transaction
    risk: Risk
    rules_fired: list[RuleFired]
    shap_drivers: list[ShapDriver]
    money_flow: list[FlowRow]
    counterparties: list[Counterparty]
    activity: Activity


class ReportResponse(BaseModel):
    txn_id: int
    case_id: str
    band: Band
    generated_at: datetime
    markdown: str


class InvestigateResponse(BaseModel):
    txn_id: int
    job_id: str
    status: JobStatus
    narrative: str | None = None
    evidence: dict[str, Any] | None = None
    error: str | None = None
    started_at: datetime
    finished_at: datetime | None = None
    poll_url: str


# --- accounts ---------------------------------------------------------------
class AccountActivity(BaseModel):
    n_sent: int
    n_received: int
    total_sent: float
    total_received: float
    distinct_destinations: int
    distinct_sources: int


class AccountRisk(BaseModel):
    n_scored_txns: int
    n_alerts: int
    max_risk_score: float | None = None
    worst_band: Band | None = None


class GraphSummary(BaseModel):
    n_sent: int | None = None
    n_received: int | None = None
    total_sent: float | None = None
    total_received: float | None = None


class GraphCounterparty(BaseModel):
    account: str
    n_txns: int
    total: float
    direction: str


class Cycle(BaseModel):
    hops: int
    path: list[str]
    total: float


class RingPeer(BaseModel):
    account: str
    shared_cp: int


class AccountResponse(BaseModel):
    account_id: str
    activity: AccountActivity
    risk: AccountRisk
    graph_available: bool
    graph_error: str | None = None
    graph_summary: GraphSummary | None = None
    counterparties: list[GraphCounterparty] = []
    cycles: list[Cycle] = []
    ring: list[RingPeer] = []


class GraphNode(BaseModel):
    id: str
    hop: int
    is_root: bool
    n_scored_txns: int = 0
    n_alerts: int = 0
    max_risk_score: float | None = None
    worst_band: Band | None = None


class GraphEdge(BaseModel):
    source: str
    target: str
    txn_id: int | None = None
    amount: float
    timestamp: str | None = None
    risk_score: float | None = None
    band: Band | None = None
    is_laundering: bool | None = Field(
        default=None, description="dataset label stored on the graph edge")


class GraphResponse(BaseModel):
    account_id: str
    hops: int
    nodes: list[GraphNode]
    edges: list[GraphEdge]
    truncated: bool


# --- predict / transactions ------------------------------------------------
class PredictRequest(BaseModel):
    """Either a list of already-scored txn_ids, or one raw feature row
    (column -> value, same columns as the training matrix)."""
    txn_ids: list[int] | None = Field(default=None, max_length=1000)
    features: dict[str, float | int | str | None] | None = None


class Prediction(BaseModel):
    txn_id: int | None = None
    model_score: float
    model_pct: float
    anomaly_pct: float | None = None
    band: Band
    action: Action
    rules_fired: list[str]
    n_rules: int
    source: Literal["scored", "ad_hoc"]


class PredictResponse(BaseModel):
    predictions: list[Prediction]
    missing: list[int] = []


class RawTransaction(BaseModel):
    txn_id: int
    timestamp: datetime
    from_id: str
    to_id: str
    from_bank: str | None = None
    to_bank: str | None = None
    amount_usd: float
    amount_paid: float | None = None
    currency_paid: str | None = None
    amount_received: float | None = None
    currency_received: str | None = None
    payment_format: str | None = None
    is_cross_bank: bool | None = None
    is_cross_currency: bool | None = None
    is_self_loop: bool | None = None
    scored: bool = Field(description="inside the test period, so has a risk band")
    risk_score: float | None = None
    band: Band | None = None


class TransactionPage(BaseModel):
    items: list[RawTransaction]
    total: int
    page: int
    page_size: int
    pages: int


# --- ask (agentic Q&A) --------------------------------------------------------
class AskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=2000)
    txn_id: int | None = Field(default=None, description="optional focus transaction")
    account_id: str | None = Field(default=None, description="optional focus account")


class ToolCall(BaseModel):
    tool: str
    args: dict[str, Any]
    result: Any
    ms: int


class AskResponse(BaseModel):
    job_id: str
    status: JobStatus
    question: str
    answer: str | None = None
    trace: list[ToolCall] = []
    rounds: int | None = None
    error: str | None = None
    started_at: datetime
    finished_at: datetime | None = None
    poll_url: str


class ErrorResponse(BaseModel):
    detail: str
