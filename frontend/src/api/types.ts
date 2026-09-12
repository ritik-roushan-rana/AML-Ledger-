// Mirrors backend/schemas.py. Keep in sync by hand -- there is no codegen.

export type Band = 'HIGH' | 'MEDIUM' | 'LOW' | 'CLEAR'
export type Action = 'REPORT' | 'REVIEW' | 'MONITOR' | 'NONE'
export type JobStatus = 'queued' | 'running' | 'done' | 'failed'

export interface Neo4jStatus { reachable: boolean; uri: string; latency_ms: number | null; error: string | null }

export interface Health {
  status: 'ok' | 'degraded' | 'error'
  model_loaded: boolean
  load_error: string | null
  anomaly_model_loaded: boolean
  anomaly_model_error: string | null
  neo4j: Neo4jStatus
  llm_configured: boolean
  rows_scored: number
  rows_total: number
  period_start: string | null
  period_end: string | null
  uptime_seconds: number
}

export interface BandStat { band: Band; count: number; share: number; positives: number; precision: number | null }
export interface DailyVolume { date: string; total: number; HIGH: number; MEDIUM: number; LOW: number }

export interface Stats {
  rows_scored: number
  n_positives: number
  base_rate: number
  alert_count: number
  period_start: string
  period_end: string
  bands: BandStat[]
  daily_alerts: DailyVolume[]
}

export interface AlertSummary {
  txn_id: number; from_id: string; to_id: string; amount_usd: number; timestamp: string
  risk_score: number; band: Band; action: Action; n_rules: number
}
export interface AlertPage { items: AlertSummary[]; total: number; page: number; page_size: number; pages: number }

export type SortField = 'risk_score' | 'timestamp' | 'amount_usd' | 'n_rules' | 'txn_id'
export interface AlertQuery { band?: Band[]; min_score?: number; page: number; page_size: number; sort: SortField; desc: boolean }

export interface Transaction {
  txn_id: number; from_id: string; to_id: string; amount_usd: number; timestamp: string
  is_cross_bank: boolean; is_cross_currency: boolean | null; is_self_loop: boolean | null
  from_bank: string | null; to_bank: string | null
  currency_paid: string | null; currency_received: string | null
  amount_paid: number | null; amount_received: number | null; payment_format: string | null
}

export interface Risk {
  risk_score: number; band: Band; action: Action; model_score: number; model_pct: number
  rule_score: number; n_rules: number; escalated: boolean
  anomaly_pct: number | null; ground_truth_label: number | null
}

export interface RuleFired { name: string; description: string }
export interface ShapDriver { feature: string; label: string; shap: number; value: number | string | null }
export interface FlowRow { txn_id: number; timestamp: string; from_id: string; to_id: string; amount_usd: number; direction: 'in' | 'out'; is_this: boolean }
export interface Counterparty { account: string; n: number; total: number; role: string }
export interface Activity {
  sender_96h_payments: number; sender_96h_counterparties: number
  receiver_96h_deposits: number; receiver_96h_sources: number
  cycle_len: number | null; chain_depth: number | null
}

export interface AlertDetail {
  transaction: Transaction; risk: Risk; rules_fired: RuleFired[]; shap_drivers: ShapDriver[]
  money_flow: FlowRow[]; counterparties: Counterparty[]; activity: Activity
}

export interface Report { txn_id: number; case_id: string; band: Band; generated_at: string; markdown: string }

export interface Investigation {
  txn_id: number; job_id: string; status: JobStatus; narrative: string | null
  evidence: Record<string, unknown> | null; error: string | null
  started_at: string; finished_at: string | null; poll_url: string
}

export interface GraphNode { id: string; hop: number; is_root: boolean; n_scored_txns: number; n_alerts: number; max_risk_score: number | null; worst_band: Band | null }
export interface GraphEdge { source: string; target: string; txn_id: number | null; amount: number; timestamp: string | null; risk_score: number | null; band: Band | null; is_laundering: boolean | null }
export interface AccountGraph { account_id: string; hops: number; nodes: GraphNode[]; edges: GraphEdge[]; truncated: boolean }

export interface AccountActivity { n_sent: number; n_received: number; total_sent: number; total_received: number; distinct_destinations: number; distinct_sources: number }
export interface AccountRisk { n_scored_txns: number; n_alerts: number; max_risk_score: number | null; worst_band: Band | null }
export interface Account {
  account_id: string; activity: AccountActivity; risk: AccountRisk
  graph_available: boolean; graph_error: string | null
  graph_summary: { n_sent: number | null; n_received: number | null; total_sent: number | null; total_received: number | null } | null
  counterparties: { account: string; n_txns: number; total: number; direction: string }[]
  cycles: { hops: number; path: string[]; total: number }[]
  ring: { account: string; shared_cp: number }[]
}

export interface ToolCall { tool: string; args: Record<string, unknown>; result: unknown; ms: number }
export interface AskResponse {
  job_id: string; status: JobStatus; question: string; answer: string | null; trace: ToolCall[]
  rounds: number | null; error: string | null; started_at: string; finished_at: string | null; poll_url: string
}
