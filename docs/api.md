# API reference

Base URL `http://localhost:8000/api`. All responses are JSON (Pydantic models in `backend/schemas.py`). Errors are `{"detail": "..."}`. Interactive docs: `http://localhost:8000/docs`.

CORS is open to `http://localhost:5173` and `http://127.0.0.1:5173`.

## Status codes you will see

| Code | Meaning |
|---|---|
| 200 | ok |
| 202 | job accepted — poll the `poll_url` in the body |
| 404 | txn / account / job not found (txn ids outside the scored test period 404) |
| 422 | bad query or body |
| 503 | pipeline not loaded, Neo4j unreachable, or LLM not configured — `/health` says which |

## GET /health

Never 503s; this is what you call to find out *why* things are down.

```json
{"status":"ok","model_loaded":true,"load_error":null,"anomaly_model_loaded":true,"anomaly_model_error":null,
 "neo4j":{"reachable":true,"uri":"bolt://localhost:7687","latency_ms":2.4,"error":null},
 "llm_configured":true,"rows_scored":761635,"rows_total":5078336,
 "period_start":"2022-09-09T03:17:00","period_end":"2022-09-18T16:18:00","uptime_seconds":11.9}
```

## GET /stats

Precomputed at startup.

```json
{"rows_scored":761635,"n_positives":1561,"base_rate":0.00205,"alert_count":38082,
 "period_start":"…","period_end":"…",
 "bands":[{"band":"HIGH","count":819,"share":0.00108,"positives":492,"precision":0.6007}, …],
 "daily_alerts":[{"date":"2022-09-09","total":30143,"HIGH":328,"MEDIUM":4844,"LOW":24971}, …]}
```

## GET /alerts

| Param | Default | Notes |
|---|---|---|
| `band` | all except CLEAR | repeatable: `band=HIGH&band=MEDIUM` |
| `min_score` | — | 0–100 |
| `page`, `page_size` | 1, 50 | max 500 |
| `sort` | `-risk_score` | `risk_score` `timestamp` `amount_usd` `n_rules` `txn_id`; `-` prefix = descending |

```json
{"items":[{"txn_id":4565663,"from_id":"33739-80C7F3EF0","to_id":"11-800924840","amount_usd":5641.78,
           "timestamp":"2022-09-09T12:36:00","risk_score":100.0,"band":"HIGH","action":"REPORT","n_rules":3}],
 "total":38082,"page":1,"page_size":50,"pages":762}
```

## GET /alerts/{txn_id}

```json
{"transaction":{"txn_id":4565663,"from_id":"…","to_id":"…","amount_usd":5641.78,"timestamp":"…","is_cross_bank":true,
                "from_bank":"33739","to_bank":"11","currency_paid":"Euro","currency_received":"Euro",
                "amount_paid":5223.87,"amount_received":5223.87,"payment_format":"ACH", …},
 "risk":{"risk_score":100.0,"band":"HIGH","action":"REPORT","model_score":0.9996,"model_pct":99.986,
         "rule_score":15.0,"n_rules":3,"escalated":true,"anomaly_pct":94.713,"ground_truth_label":1},
 "rules_fired":[{"name":"fan_in","description":"account received funds from an unusual number of sources"}, …],
 "shap_drivers":[{"feature":"hrs_since_prev_out","label":"hours since sender's previous payment","shap":2.088,"value":0.0}, …],
 "money_flow":[{"txn_id":…,"timestamp":"…","from_id":"…","to_id":"…","amount_usd":…,"direction":"in","is_this":false}, …],
 "counterparties":[{"account":"…","n":8,"total":19323.8,"role":"paid to"}, …],
 "activity":{"sender_96h_payments":1,"sender_96h_counterparties":1,"receiver_96h_deposits":9,"receiver_96h_sources":9,"cycle_len":null,"chain_depth":5}}
```

`money_flow` and `counterparties` are computed over the raw transactions (96 h window) — no Neo4j needed.

## GET /alerts/{txn_id}/report

`{"txn_id":…,"case_id":"AML-04565663","band":"HIGH","generated_at":"…","markdown":"# Investigation report — HIGH risk\n…"}`

## POST /alerts/{txn_id}/investigate · GET same path

See [agent.md](agent.md#backend-surface). Body on both:

```json
{"txn_id":4565663,"job_id":"bd41be4867be","status":"done","narrative":"…","evidence":{…},"error":null,
 "started_at":"…","finished_at":"…","poll_url":"/api/alerts/4565663/investigate"}
```

`status` ∈ `queued | running | done | failed`.

## POST /ask · GET /ask/{job_id}

Request `{"question":"Does money sent by 11-800924840 come back to it?","txn_id":null,"account_id":"11-800924840"}`.

```json
{"job_id":"3f8a210bf933","status":"done","question":"…","answer":"…","rounds":2,"error":null,
 "trace":[{"tool":"find_cycles","args":{"account":"11-800924840"},"result":[…],"ms":30529}, …],
 "started_at":"…","finished_at":"…","poll_url":"/api/ask/3f8a210bf933"}
```

## GET /accounts/{account_id}

Pandas half always works; graph half degrades with `graph_available:false` + `graph_error`. Responses are cached per account (`?refresh=true` bypasses) because `find_cycles` can take ~30 s.

```json
{"account_id":"11-800924840",
 "activity":{"n_sent":77,"n_received":22,"total_sent":152831.02,"total_received":84810241.51,"distinct_destinations":11,"distinct_sources":16},
 "risk":{"n_scored_txns":32,"n_alerts":17,"max_risk_score":100.0,"worst_band":"HIGH"},
 "graph_available":true,"graph_error":null,
 "graph_summary":{"n_sent":77,"n_received":22,"total_sent":122576.4,"total_received":84810241.5},
 "counterparties":[{"account":"…","n_txns":1,"total":84547311.7,"direction":"received from"}, …],
 "cycles":[{"hops":2,"path":["11-800924840","…","11-800924840"],"total":7857.69}, …],
 "ring":[{"account":"…","shared_cp":3}]}
```

## GET /accounts/{account_id}/graph

`hops` = 1 | 2 (default 1), `limit` = max neighbour nodes (default 50, max 500). BFS one Cypher query per hop, then all `SENT` edges among the node set (capped at `limit × 20`). 404 if the account is not in the (subset) graph.

```json
{"account_id":"…","hops":2,"truncated":true,
 "nodes":[{"id":"…","hop":0,"is_root":true,"n_scored_txns":32,"n_alerts":17,"max_risk_score":100.0,"worst_band":"HIGH"}, …],
 "edges":[{"source":"…","target":"…","txn_id":3754764,"amount":84547311.7,"timestamp":"2022-09-08 00:28:00","risk_score":null,"band":null,"is_laundering":false}, …]}
```

`band`/`risk_score` are null for edges outside the scored test period.

## GET /transactions?account=&direction=&page=&page_size= · GET /transactions/{txn_id}

Raw rows over all 5 M transactions, newest first. `direction` ∈ `both | sent | received`. Each row carries `scored` and, when true, `risk_score` + `band`.

## POST /predict

Exactly one of:

- `{"txn_ids":[4565663, 4419778]}` → cached scores; unknown ids listed in `missing`.
- `{"features":{…}}` → one ad-hoc feature row (same column names as the training matrix; unsupplied columns are NaN, at least half must be present). Scored through XGBoost + rules + Isolation Forest; band from the percentile against the test-period distribution.

```json
{"predictions":[{"txn_id":4565663,"model_score":0.9996,"model_pct":99.986,"anomaly_pct":94.71,"band":"HIGH","action":"REPORT",
                 "rules_fired":["fan_in","gather_scatter","stack"],"n_rules":3,"source":"scored"}],"missing":[]}
```
