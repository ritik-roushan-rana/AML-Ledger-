# Investigation agent

Two modes share one tool layer (`ml/agent/tools.py::ToolBox`). Both follow the same rule: **the LLM writes prose; every figure comes from a tool result.** A hallucinated amount in a suspicious-activity report is a compliance failure, not a cosmetic bug.

## ToolBox (13 tools)

| Tool | Backed by | Returns |
|---|---|---|
| `transaction_search(txn_id)` | feature matrix | parties, amount, time, cross-bank |
| `account_lookup(account)` | Neo4j | totals sent / received |
| `aggregation(account)` | raw transactions | counts, totals, distinct counterparties |
| `risk_lookup(txn_id)` | fusion | risk score, band, action, percentile, escalated |
| `xgboost_prediction(txn_id)` | XGBoost | raw probability + percentile (with a "do not read as a rate" note) |
| `anomaly_detection(txn_id)` | Isolation Forest | anomaly percentile, `unusual` flag |
| `rule_check(txn_id)` | rules | fired rules + descriptions |
| `shap_explanation(txn_id)` | SHAP | top drivers as plain-English reasons |
| `graph_search(account)` | Neo4j | direct counterparties |
| `path_analysis(a, b)` | Neo4j | shortest SENT path |
| `money_flow(account, hops)` | Neo4j | where funds travelled |
| `find_cycles(account)` | Neo4j | paths returning to the account (`SENT*2..6`, can take ~30 s) |
| `community_detection(account)` | Neo4j | accounts sharing ≥ 3 counterparties |

`SPECS` in the same file declares each tool's parameters; `ask.py` converts them to Gemini function declarations.

## Mode 1 — Investigate (deterministic evidence)

`agent.gather(tools, txn_id)` runs a **fixed** set of tools (transaction, risk, model, anomaly, rules, SHAP, sender/receiver aggregation, receiver counterparties/summary/cycles/ring) and `agent.narrate(evidence)` gives the LLM one shot at prose over that evidence. Deliberately not autonomous: the evidence set for an AML alert is known in advance, so gathering it deterministically makes output reproducible and auditable.

Prompt rules (`ml/agent/prompts.py`): use only the given figures; say when evidence is absent; describe behaviour, never assert guilt ("consistent with", "warrants review"); name the typology when supported; six paragraphs max, no headings; temperature 0.2.

If `GEMINI_API_KEY` is unset or the call fails, `_fallback()` produces a template narrative from the same evidence — the demo never depends on a network call.

`report.build(...)` assembles the markdown case file (why flagged / money flow / connected accounts / risk factors / evidence / action) and the backend splices the narrative in as "Investigator summary" once it exists.

## Mode 2 — Ask (autonomous tool use)

`ask.ask(tools, question, context)` runs a manual function-calling loop:

1. Send the question (+ optional `txn_id` / `account_id` context) with all 13 tool declarations; automatic function calling is **disabled** so the loop controls execution.
2. For each `function_call` the model returns, execute it on `ToolBox`, record `{tool, args, result, ms}`, and send the result back.
3. Stop when the model returns text, or after `MAX_ROUNDS = 8`.

Guard-rails: tool names are validated against `SPECS` (nothing else is reachable); tool exceptions become `{"error": …}` results rather than crashing the loop; temperature 0.1; the system prompt forbids un-sourced figures and asks for a closing "tools relied on" line. The full trace is returned and shown in the UI, so an answer can be checked call by call.

Because temperature is not zero, the tool path can differ between runs of the same question. When reproducibility matters more than flexibility, use Investigate.

## Backend surface

| Endpoint | Behaviour |
|---|---|
| `POST /api/alerts/{id}/investigate` | 202 + job; cached per txn (200 on repeat); `?force=true` re-runs; 503 immediately if Neo4j is down |
| `GET /api/alerts/{id}/investigate` | poll |
| `POST /api/ask` | 202 + job; 503 if no LLM key |
| `GET /api/ask/{job_id}` | poll; `trace` fills in live as tools complete |

Jobs run on a 2-worker thread pool in `backend/deps.py`; results are kept in memory (last 200 ask jobs).
