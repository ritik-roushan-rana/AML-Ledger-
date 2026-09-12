# AML Ledger

**Explainable anti-money-laundering detection and alert triage** — from raw transactions to a ranked alert queue, graph evidence, SHAP explanations, and LLM-written investigation reports that can only cite figures produced by tools.

Built on the IBM AML synthetic dataset (HI-Small, 5.08 M transactions). Python ML pipeline · Neo4j graph · FastAPI backend · React triage console.

**Held-out test period (761,635 transactions, 0.205 % laundering):**
XGBoost PR-AUC **0.374** · HIGH band = 819 alerts at **60 % precision** (293× the base rate) · MEDIUM 6 % · LOW 1 %.

---

## Contents

1. [Screenshots](#screenshots)
2. [What it does](#what-it-does)
3. [Architecture](#architecture)
4. [How the risk score works](#how-the-risk-score-works)
5. [The ML pipeline](#the-ml-pipeline)
6. [Graph layer (Neo4j)](#graph-layer-neo4j)
7. [Explainability (SHAP)](#explainability-shap)
8. [Investigation agents (LLM)](#investigation-agents-llm)
9. [Backend (FastAPI)](#backend-fastapi)
10. [Frontend (React)](#frontend-react)
11. [Repository layout](#repository-layout)
12. [Setup](#setup)
13. [Running](#running)
14. [Configuration](#configuration)
15. [Troubleshooting](#troubleshooting)
16. [Known limits & caveats](#known-limits--caveats)

---

## Screenshots

**Risk overview** — headline metrics, alert volume per day, precision by band, top HIGH alerts. Every panel is tagged with the engine that produced it.

![Risk overview](docs/screenshots/overview.png)

**Account network** — 2-hop Neo4j neighbourhood; node colour = worst band, size = degree, dashed red = labelled laundering edge.

![Account network](docs/screenshots/network.png)

**Investigation agent** — the LLM chose `risk_lookup → rule_check → shap_explanation`, answered in 2.4 s, and every call is in the execution trace.

![Ask the agent](docs/screenshots/ask.png)

---

## What it does

A compliance analyst opens the **queue** and sees transactions ranked by risk, with a band (HIGH / MEDIUM / LOW / CLEAR) and a recommended action (REPORT / REVIEW / MONITOR / NONE). Clicking one opens a **case file**:

- *why* the model flagged it — six plain-English SHAP drivers ("receiver received from 9 distinct accounts in the last 96 h")
- which deterministic **typology rules** fired (fan-in, cycle, structuring…) with descriptions
- the **money flow** around both accounts in the last 96 h, with the alerted transfer highlighted
- a **Neo4j network** of both parties and their counterparties
- a button that runs an **LLM investigation** and writes a narrative from gathered evidence
- a generated **SAR-draft report** in markdown

From any account they can open its full **transaction graph** (1 or 2 hops, cycles back to itself, shared-counterparty rings), and from anywhere they can **ask the agent** a free-text question — the LLM picks which tools to call, including graph queries, and shows its work.

Every number in the UI is tagged with its source (`NEO4J`, `XGBOOST`, `SHAP`, `RULES`, `LLM`, `FEATURE STORE`), so an analyst — or an auditor — can see where it came from.

---

## Architecture

```
data/raw/HI-Small_Trans.csv (5.08 M txns)        data/raw/HI-Small_Patterns.txt (370 labelled groups)
          │                                                      │
     ml/data.py   clean · composite account ids · FX → USD       ml/patterns.py   typology profiles → rule thresholds
          │
     ml/features/   transaction (stateless) · behavioural (rolling, past-only) · graph (previous bucket only)
          │
     data/processed/features.parquet      5,078,336 rows × 78 features + ids + label
          │
   ┌──────┴────────────────────────┬─────────────────────────────┐
 ml/models/xgb.py            ml/models/rules.py            ml/models/iforest.py
 supervised booster          9 typology rules              unsupervised (43 behavioural cols)
 → probability, percentile   → fired flags, rule_score     → anomaly percentile
   └──────┬────────────────────────┴─────────────────────────────┘
     ml/models/fusion.py
       band    = percentile ≥ 99.9 → HIGH · ≥ 99 → MEDIUM · ≥ 95 → LOW · else CLEAR
       escalate one band when ≥ 2 of {cycle, fan_in, gather_scatter, amount_band} co-fire
       action  = REPORT / REVIEW / MONITOR / NONE
       anomaly_pct attached as evidence — never changes the band
          │
   ┌──────┴──────────────┬──────────────────────────┐
 ml/explain.py (SHAP)   ml/graph/ (Neo4j)          ml/agent/tools.py  ToolBox — 13 tools wrapping all of the above
   └──────┬──────────────┴──────────────────────────┘
     ml/agent/agent.py   gather() fixed evidence set → narrate() Gemini, prose only
     ml/agent/ask.py     LLM chooses tools → answer + auditable trace
     ml/agent/report.py  markdown case file
          │
     backend/   FastAPI — loads everything once at startup, serves JSON, 202+poll for slow work
          │
     frontend/  React — queue · case file · account network · overview · ask
```

---

## How the risk score works

This is the part worth understanding; the rest is plumbing.

**1. XGBoost ranks.** The booster is trained with `scale_pos_weight ≈ 1000` (the class ratio). That gives excellent ranking (PR-AUC 0.374 against a 0.002 random baseline) but useless probabilities — the top decile averages p = 0.16 against an actual 1.8 % positive rate. So **bands are cut on the percentile rank of the score**, never on the raw probability.

**2. Rules escalate and explain — they do not rank.** Rules-only PR-AUC is 0.004. If you blend them into the score, XGBoost's PR-AUC drops from 0.374 to 0.189, because 95 % of rows share a near-zero model score and the rules then dominate the ordering. Rules therefore do exactly two things: bump a transaction up one band when ≥ 2 high-precision rules fire together, and supply the sentences an investigator reads ("account received funds from an unusual number of sources"). A tiny nudge (`+0.05 × rule_score_norm`) breaks ties without reordering.

**3. Isolation Forest is evidence, not score.** Alone it scores PR-AUC 0.002 — random. But it answers a different question ("is this account's behaviour unusual regardless of what the label says?"), which is what matters for a typology the supervised model never saw. It is shown as an anomaly percentile in the case file, the report and the agent's evidence, and never fused.

**4. No leakage.** Behavioural windows cover `[t − w, t)` and exclude the current row. Graph features are built only from the *previous* 24 h bucket. The train / validation / test split is by row quantile (≤ 70 % / 70–85 % / > 85 %), not calendar date — the dataset has a thin tail running to Sep 18 that would otherwise leave a 74-row test set.

**5. The LLM writes prose only.** Every figure in a narrative or answer comes from a tool result. A hallucinated amount in a suspicious-activity report is a compliance failure, not a cosmetic bug.

---

## The ML pipeline

### Data (`ml/data.py`)

Two traps the loader handles: account numbers are unique only *within* a bank, so ids become `bank-account` composites; and paid/received amounts differ across currencies, so everything is normalised to USD with the FX table in `configs/config.yaml`.

### Features — 78 columns (`ml/features/`)

| Family | Examples | Leakage rule |
|---|---|---|
| **Transaction** (`transaction.py`) | amount bands (3k–20k, 9k–20k), just-below-10k, cross-bank, cross-currency, hour, weekday, currency, payment format | stateless — one row in, one row out |
| **Behavioural** (`behavioral.py`) | per-account counts / sums / distinct counterparties over 24 h, 96 h, 192 h; hours since previous in/out; new-sender / new-receiver; in-out ratio | window `[t − w, t)`, current row excluded |
| **Graph** (`graph.py`) | degree, PageRank, community size, same-community, triangles, `g_chain_depth` (layering), `g_cycle_len`, reciprocity | built from the previous time bucket only |

Roundness features ("just under a round thousand") were tested and dropped: in this generator round amounts launder at ~1/12 the base rate.

### Models (`ml/models/`)

**XGBoost** — `binary:logistic`, depth 6, learning rate 0.05, subsample 0.8, early stopping on validation PR-AUC. All 78 features.

**Rules** — nine deterministic checks on the feature matrix. Thresholds were derived from the 370 labelled pattern groups; weights are proportional to *measured* lift on the test period (`configs/rules.yaml`):

| Rule | Condition | Weight | Lift |
|---|---|---|---|
| fan_in | ≥ 8 distinct sources in 96 h | 8 | 8.5× |
| amount_band | 9,000 ≤ amount ≤ 20,000 | 6 | 6.2× |
| gather_scatter | ≥ 7 sources in 192 h and ≥ 2 destinations | 6 | 5.9× |
| cycle | funds return to sender (`g_cycle_len ≥ 2`) | 4 | — |
| structuring | 9,000–9,999 (just under a reporting threshold) | 3 | 2.7× |
| weekend | outside the business week | 2 | 1.6× |
| fan_out | ≥ 7 destinations in 96 h | 1 | 1.4× |
| stack | layering chain ≥ 5 hops | 1 | 1.2× |
| scatter_gather | ≥ 8 destinations and ≥ 2 sources | 0 | 0.9× (shown, not scored) |

Anything above $20k is hard-ruled out — nothing above that ceiling launders in this dataset. A "rapid pass-through" rule was tried and removed (lift 0.10, anti-correlated).

**Isolation Forest** — 200 trees × 256 samples, fit on 500k training rows over the 43 numeric behavioural columns; raw score converted to a percentile against the training distribution.

### Evaluation (`ml/evaluation.py`)

Accuracy is meaningless at a 0.2 % positive rate (predicting "never" scores 99.8 %). Reported instead: PR-AUC, ROC-AUC, and precision / recall at fixed alert budgets (100 / 500 / 1,000 / 5,000 alerts) — i.e. "if an analyst reviews 1,000 a day, how many are real?"

| Model | PR-AUC | Role |
|---|---|---|
| XGBoost | **0.374** | ranks the queue |
| Rules only | 0.004 | escalation + evidence |
| Isolation Forest only | 0.002 | evidence |

| Band | Alerts | Positives | Precision |
|---|---|---|---|
| HIGH | 819 | 492 | 60.1 % |
| MEDIUM | 6,953 | 427 | 6.1 % |
| LOW | 30,310 | 346 | 1.1 % |
| CLEAR | 723,553 | 296 | 0.04 % |

---

## Graph layer (Neo4j)

`ml/graph/loader.py` loads **alerted accounts plus one hop of neighbours** — not all 5 M transactions, since the investigation layer never queries the other 99 %. Schema: `(:Account {id})-[:SENT {txn_id, amount, timestamp, is_laundering}]->(:Account)`.

`ml/graph/queries.py` answers the questions an investigator asks:

| Function | Cypher idea | Used by |
|---|---|---|
| `connected_accounts` | direct counterparties, both directions, totals | account page, agent |
| `money_flow` | `SENT*1..N` from an account, summed along the path | agent |
| `find_cycles` | `SENT*2..6` back to the same account | account page, investigate, ask |
| `shortest_path` | shortest `SENT` path between two accounts | ask |
| `fraud_ring` | accounts sharing ≥ 3 counterparties | account page, agent |
| `account_summary` | totals sent / received | agent |

The backend adds one more query for visualisation: a hop-by-hop BFS (one query per level, capped) followed by all `SENT` edges among the collected nodes — so a hub account cannot blow up the traversal.

`find_cycles` on a busy account takes ~30 s; the backend caches account responses after the first call.

---

## Explainability (SHAP)

`ml/explain.py` uses `shap.TreeExplainer` — exact for tree ensembles, so single-alert explanations need no sampling. The important part is `LABELS`: a map from column names to sentences, because `out_96h_ncp` means nothing to an investigator and "sender paid 9 distinct accounts in 96 h" means everything. The case file shows the top six positive drivers as bars; the report lists them as bullets with signed impact.

---

## Investigation agents (LLM)

Both modes share `ml/agent/tools.py::ToolBox` — 13 thin wrappers over the modules above (`transaction_search`, `account_lookup`, `aggregation`, `risk_lookup`, `xgboost_prediction`, `anomaly_detection`, `rule_check`, `shap_explanation`, `graph_search`, `path_analysis`, `money_flow`, `find_cycles`, `community_detection`). The agent owns no detection logic; the same functions serve the CLI, the report and the LLM.

**Investigate** (`ml/agent/agent.py`) — deliberately *not* autonomous. `gather()` runs a fixed evidence set (transaction, risk, model, anomaly, rules, SHAP, both parties' activity, receiver's counterparties / cycles / ring) and `narrate()` gives Gemini one shot at prose over it, temperature 0.2. Reproducible and auditable, which a regulated setting needs. If no API key is set or the call fails, a deterministic template narrative is produced from the same evidence — the demo never depends on a network call.

**Ask** (`ml/agent/ask.py`) — autonomous tool use. The 13 tool specs become Gemini function declarations; a manual loop (automatic calling disabled) executes each requested tool on `ToolBox`, records `{tool, args, result, ms}`, feeds the result back, and stops when the model answers or after 8 rounds. Tool names are validated against the spec list, tool errors become results rather than crashes, and the full trace is returned and shown in the UI. Temperature 0.1 — tool paths can differ between runs, which is why Investigate exists for the reproducible case.

Prompt rules for both (`ml/agent/prompts.py`): use only the figures given; say plainly when evidence is absent; describe behaviour, never assert guilt ("consistent with", "warrants review"); name the typology when the evidence supports it; no headings or bullet lists.

`ml/agent/report.py` assembles the markdown case file — why flagged / money flow / connected accounts / risk factors / supporting evidence / recommended action — and the narrative is spliced in as an "Investigator summary" once it exists.

---

## Backend (FastAPI)

`backend/main.py` · `deps.py` · `schemas.py` · `routers/{health, stats, alerts, accounts, transactions, predict, ask}.py`

**Startup** (`deps.load_state`, in a lifespan handler, once): read `features.parquet`, keep rows after the 85 % timestamp quantile (761,635), load the booster and Isolation Forest, score and fuse, build the SHAP explainer and `ToolBox`, precompute stats and per-account risk. ~10 s. If anything fails the server still starts — `/health` reports the error and only affected endpoints return 503. A missing `iforest.joblib` just leaves anomaly fields null.

**Slow work is a job.** `/investigate` and `/ask` return `202` with a job id and are polled; they run on a small thread pool so a 30 s Cypher query never blocks the queue. Investigate results are cached per transaction; the ask trace fills in live as each tool completes.

**Endpoints** (base `/api`, interactive docs at `/docs`):

| Method | Path | Returns |
|---|---|---|
| GET | `/health` | model / anomaly model / Neo4j / LLM status, rows scored — never 503s |
| GET | `/stats` | band counts & precision, alerts per day, base rate |
| GET | `/alerts?band=&min_score=&page=&page_size=&sort=` | paginated queue; `band` repeatable; default excludes CLEAR; `sort=-risk_score` style |
| GET | `/alerts/{id}` | transaction, risk (incl. anomaly pct), rules fired, SHAP drivers, 96 h money flow, counterparties, activity |
| GET | `/alerts/{id}/report` | markdown case report |
| POST / GET | `/alerts/{id}/investigate` | 202 + job → poll; `?force=true` re-runs; 503 if Neo4j down |
| POST | `/ask` `{question, txn_id?, account_id?}` · GET `/ask/{job_id}` | 202 + job → answer + tool trace; 503 if no LLM key |
| GET | `/accounts/{id}` | activity, worst band, Neo4j counterparties / cycles / ring (`graph_available:false` if Neo4j down); cached, `?refresh=true` |
| GET | `/accounts/{id}/graph?hops=1\|2&limit=` | nodes (band, alerts) + edges (amount, band, `is_laundering`) |
| GET | `/transactions?account=&direction=` · `/transactions/{id}` | raw rows over all 5 M transactions, with band when scored |
| POST | `/predict` `{txn_ids:[…]}` or `{features:{…}}` | score, percentile, band, rules, anomaly — ad-hoc rows go through the same xgb + rules + IF path |

Errors are `{"detail": "…"}`. 404 for ids outside the scored period, 422 for bad input, 503 for a missing dependency. CORS is open to `localhost:5173`.

---

## Frontend (React)

React 19 · Vite · TypeScript · Tailwind 4 · TanStack Query 5 · react-router 7 · react-force-graph-2d · react-markdown. Design tokens are from a Google Stitch export ("AML Ledger"): `#F7F8FA` canvas, white 12 px cards, Inter + JetBrains Mono, pill badges, `#2563EB` primary — with a full dark palette.

| Route | Screen |
|---|---|
| `/` | **Queue** — band cards toggle filters; sortable, paginated table; filters / sort / page live in the URL |
| `/alerts/:id` | **Case file** — score, anomaly percentile, disposition, pattern rules; Detail / SAR-draft tabs; sticky module rail; SHAP bars, rules, money flow, counterparties, Neo4j mini-graph, investigator narrative |
| `/accounts/:id?hops=1\|2` | **Account network** — alerts / outflow / inflow, force-directed graph with zoom, counterparties, cycles, shared-counterparty peers |
| `/overview` | **Risk overview** — stat tiles, alerts-per-day chart (log / linear / table), precision by band, top-10 HIGH |
| `/ask?txn=&account=` | **Investigation agent** — question, context chip, live job bar, answer + numbered tool trace with expandable JSON |

How it's built:

- `src/api/` — `types.ts` mirrors `backend/schemas.py`; `client.ts` wraps fetch into `ApiError(status, detail)`; `hooks.ts` holds the TanStack hooks, including the POST → poll pattern for jobs.
- `src/components/ui.tsx` — `Card`, `Stat`, `BandPill`, `SourceTag`, `Button`, `ErrorBox`, `Empty`, `Skeleton`, `Kv`. Everything else composes these.
- **Tokens** — every colour is a semantic Tailwind token (`bg-card`, `text-muted`, `border-high-line`…) declared in `src/index.css` and overridden under `.dark`. The band → class map lives in one place (`lib/format.ts`).
- **Dark mode** — class strategy; header toggle; preference in `localStorage`, otherwise follows the OS and reacts to changes; canvas / SVG colours come from `lib/theme.tsx::chartColors`.
- **Loading & errors** — skeletons for content, spinners only inside long-running buttons; 4xx is never retried; every fetch failure renders a visible error box with retry.
- **Source tags** — pass `sources={['neo4j', 'shap']}` to a `Card` and it shows the origin chips in its header.

---

## Repository layout

```
ml/                     pipeline (importable package)
  data.py               load + clean raw csv
  patterns.py           parse Patterns.txt → typology profiles
  eda.py  evaluation.py explain.py
  features/             transaction.py · behavioral.py · graph.py · build.py
  models/               xgb.py · rules.py · iforest.py · fusion.py
  graph/                loader.py (Neo4j load) · queries.py (Cypher)
  agent/                tools.py · agent.py · ask.py · report.py · prompts.py · context.py
  scripts/              build_features · train · train_iforest · load_graph · score · evaluate · investigate · run_eda · run_patterns
  scripts/checks/       dev sanity checks (not part of the pipeline)
backend/                FastAPI app (main.py · deps.py · schemas.py · routers/)
frontend/               React app (src/api · src/components · src/pages · src/lib)
configs/                config.yaml (dataset, FX) · rules.yaml (thresholds, weights) · features.yaml
docs/                   longer write-ups per area + screenshots/
data/raw/               HI-Small_Trans.csv · HI-Small_Patterns.txt        (not committed)
data/processed/         features.parquet · transactions_clean.parquet …   (generated)
models/                 xgb.json · xgb_columns.json · iforest.joblib       (generated)
outputs/                EDA figures · CLI-generated reports                (generated)
```

---

## Setup

**Requirements:** Python 3.11 · Node 20+ · Neo4j 5 on `bolt://localhost:7687` (needed for graph views and the agents) · a Gemini API key (optional — without it narratives use the template fallback and `/ask` is disabled).

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env            # NEO4J_PASSWORD · GEMINI_API_KEY · optionally GEMINI_MODEL
cd frontend && npm install && cd ..
```

Put `HI-Small_Trans.csv` and `HI-Small_Patterns.txt` in `data/raw/`, then build the artefacts (once):

```bash
.venv/bin/python -m ml.scripts.build_features   # features.parquet, ~2 GB, several minutes
.venv/bin/python -m ml.scripts.train            # models/xgb.json + test report
.venv/bin/python -m ml.scripts.train_iforest    # models/iforest.joblib
.venv/bin/python -m ml.scripts.load_graph       # alerted neighbourhoods → Neo4j (Neo4j must be running)
```

---

## Running

Two processes, from the project root:

```bash
.venv/bin/uvicorn backend.main:app --reload --port 8000     # loads the pipeline once, ~10 s
```

```bash
cd frontend && npm run dev                                   # http://localhost:5173
```

Open http://localhost:5173. The header pill shows system status; `http://localhost:8000/api/health` gives the detail. Stop servers with **Ctrl+C** — Ctrl+Z only suspends and keeps the port.

CLI equivalents without the UI:

```bash
.venv/bin/python -m ml.scripts.score --top 5                 # top alerts
.venv/bin/python -m ml.scripts.investigate --txn 4565663     # narrative + report → outputs/reports/
.venv/bin/python -m ml.scripts.evaluate                      # metrics on the held-out period
```

---

## Configuration

| Where | What |
|---|---|
| `.env` | `NEO4J_URI` `NEO4J_USER` `NEO4J_PASSWORD` `GEMINI_API_KEY` `GEMINI_MODEL` — secrets and machine-specific details; read with `override=True` |
| `configs/config.yaml` | dataset filenames, FX-to-USD table, Neo4j defaults |
| `configs/rules.yaml` | amount bands, structuring window, rolling windows (24 / 96 / 192 h), per-rule thresholds, scoring weights, `max_score` |
| `ml/models/fusion.py` | band cut-offs (`99.9 / 99 / 95`), escalating rule set, escalation minimum |
| `frontend/.env` | `VITE_API_BASE` (default `http://localhost:8000`) |

Thresholds are committed because they are part of the methodology a reviewer needs; secrets never are.

---

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `Address already in use` on 8000 or 5173 | A server is already running — usually the one you want. If it's stale: `lsof -ti :8000 \| xargs kill -9`. A Ctrl+Z'd process ignores plain `kill`. |
| Vite refuses to move to 5174 | `strictPort` is on because backend CORS is pinned to 5173. Free 5173 instead. |
| Header says *Degraded · neo4j* | Neo4j down or wrong password. Queue, case file and report still work; account graph, mini-graph, investigate and ask return 503. |
| `/accounts/{id}` takes ~30 s | `find_cycles` (`SENT*2..6`) on a hub account. Cached afterwards; lower `max_hops` in `ml/graph/queries.py` if needed. |
| `/accounts/{id}/graph` 404s | Only alerted accounts + one hop are in Neo4j. |
| Ask returns 503 | `GEMINI_API_KEY` missing or still `your_key_here`. |
| `pipeline failed to load: missing artefacts` | Run the setup scripts; the message lists the missing paths. |

---

## Known limits & caveats

- **Synthetic data.** Thresholds (e.g. the $20k ceiling, the absence of round-amount structuring) reflect the IBM generator, not real banking behaviour. Re-derive them on real data.
- **Ground-truth labels are shown** in the UI (`ground_truth_label`, precision figures) for evaluation. Strip them before anyone could act on this.
- **`/predict` needs a full feature row.** Scoring a brand-new raw transaction requires rebuilding its behavioural and graph features against history; that path is not exposed.
- **Job results live in process memory** and are lost on restart. The backend is single-process (state is ~2–3 GB); run one worker.
- **This is a prioritisation aid**, not a determination of wrongdoing. Every report says so.

Longer write-ups per area are in [`docs/`](docs/README.md).
