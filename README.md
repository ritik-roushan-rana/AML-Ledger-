# AML Ledger

> Explainable anti-money-laundering detection and alert triage — from raw transactions to a ranked queue, graph evidence, SHAP explanations, and LLM-written investigation reports.

![Python](https://img.shields.io/badge/Python-3.11-3776AB?style=flat-square&logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.141-009688?style=flat-square&logo=fastapi&logoColor=white)
![React](https://img.shields.io/badge/React-19-61DAFB?style=flat-square&logo=react&logoColor=black)
![Neo4j](https://img.shields.io/badge/Neo4j-6.3-008CC1?style=flat-square&logo=neo4j&logoColor=white)
![XGBoost](https://img.shields.io/badge/XGBoost-3.2-FF6600?style=flat-square)

Built on the **IBM AML synthetic dataset** — 5.08 M transactions, 370 labelled laundering groups. Python ML pipeline · Neo4j graph · FastAPI · React triage console.

---

## Results

Held-out test period · 761,635 transactions · 0.205 % laundering rate

| Band | Alerts | Precision | vs. Base Rate |
|---|---|---|---|
| **HIGH** | 819 | **60.1 %** | 293× |
| MEDIUM | 6,953 | 6.1 % | 30× |
| LOW | 30,310 | 1.1 % | 5× |
| CLEAR | 723,553 | 0.04 % | — |

XGBoost PR-AUC **0.374** against a 0.002 random baseline.

---

## Screenshots

**Risk overview** — headline metrics, alert volume per day, precision by band, top HIGH alerts. Every panel is tagged with the engine that produced it.

![Risk overview](docs/screenshots/overview.png)

**Account network** — 2-hop Neo4j neighbourhood; node colour = worst band, size = degree, dashed red = labelled laundering edge.

![Account network](docs/screenshots/network.png)

**Investigation agent** — the LLM chose `risk_lookup → rule_check → shap_explanation`, answered in 2.4 s, full tool trace shown.

![Ask the agent](docs/screenshots/ask.png)

---

## What It Does

A compliance analyst opens the **queue** and sees transactions ranked by risk, each with a band (HIGH / MEDIUM / LOW / CLEAR) and a recommended action (REPORT / REVIEW / MONITOR / NONE).

Clicking a transaction opens a **case file**:

- **Why it was flagged** — six plain-English SHAP drivers ("receiver received from 9 distinct accounts in 96 h")
- **Typology rules** that fired — fan-in, cycle, structuring, and more — with descriptions
- **Money flow** around both accounts in the last 96 h, with the alerted transfer highlighted
- **Neo4j network** of both parties and their counterparties
- **LLM investigation** — one click narrates the evidence into a structured report
- **SAR-draft report** — full markdown case file, ready to export

From any account, analysts can explore the full **transaction graph** (1 or 2 hops, cycles, shared-counterparty rings). The **Ask** page takes free-text questions — the LLM picks tools, runs them, and shows its work.

Every number in the UI is tagged with its source: `NEO4J` `XGBOOST` `SHAP` `RULES` `LLM` `FEATURE STORE`.

---

## Architecture

```
data/raw/HI-Small_Trans.csv (5.08 M txns)
          │
     ml/data.py   clean · composite account ids · FX → USD
          │
     ml/features/
       transaction.py    stateless per-row features
       behavioral.py     rolling windows [t−w, t), no leakage
       graph.py          previous bucket only
          │
     data/processed/features.parquet   5,078,336 rows × 78 features
          │
   ┌──────┴──────────────────┬───────────────────────────────┐
 ml/models/xgb.py      ml/models/rules.py         ml/models/iforest.py
 supervised booster    9 typology rules            unsupervised anomaly
 → score, percentile   → flags, evidence           → anomaly percentile
   └──────┬──────────────────┴───────────────────────────────┘
     ml/models/fusion.py
       band    HIGH (≥99.9th) · MEDIUM (≥99th) · LOW (≥95th) · CLEAR
       escalate one band when ≥2 high-precision rules co-fire
       anomaly_pct attached as evidence, never changes the band
          │
   ┌──────┴──────────────┬─────────────────────────┐
 ml/explain.py        ml/graph/               ml/agent/tools.py
 SHAP TreeExplainer   Neo4j queries           ToolBox — 13 tools
   └──────┬──────────────┴─────────────────────────┘
     ml/agent/agent.py    gather() fixed evidence → narrate() via Gemini
     ml/agent/ask.py      LLM picks tools → answer + auditable trace
     ml/agent/report.py   markdown case file assembly
          │
     backend/  FastAPI — loads once at startup, 202+poll for slow work
          │
     frontend/ React — queue · case file · account graph · overview · ask
```

---

## How the Risk Score Works

**1. XGBoost ranks, not classifies.** Trained with `scale_pos_weight ≈ 1000`, the model gives excellent ranking (PR-AUC 0.374) but uncalibrated probabilities. Bands are cut on the **percentile rank**, never the raw probability.

**2. Rules escalate and explain — they don't rank.** Rules-only PR-AUC is 0.004. Blending them into the score drops XGBoost's PR-AUC from 0.374 to 0.189. Rules do two things only: bump a transaction one band when ≥ 2 high-precision rules co-fire, and supply readable evidence sentences.

**3. Isolation Forest is evidence only.** PR-AUC 0.002 alone. It answers "is this behaviour unusual regardless of the label?" — shown as an anomaly percentile in the case file, never fused into the band.

**4. No leakage.** Behavioural windows cover `[t − w, t)` excluding the current row. Graph features use only the previous 24 h bucket. Train / val / test split is by row quantile (70 / 85 / 100 %), not calendar date.

**5. The LLM writes prose only.** Every figure in a narrative comes from a tool result. A hallucinated amount in a suspicious-activity report is a compliance failure, not a cosmetic bug.

---

## Models & Evaluation

| Model | PR-AUC | Role |
|---|---|---|
| XGBoost | **0.374** | ranks the queue |
| Rules only | 0.004 | escalation + evidence |
| Isolation Forest only | 0.002 | evidence |

### Typology Rules

| Rule | Condition | Weight | Lift |
|---|---|---|---|
| fan_in | ≥ 8 distinct sources in 96 h | 8 | 8.5× |
| amount_band | $9,000 – $20,000 | 6 | 6.2× |
| gather_scatter | ≥ 7 sources in 192 h and ≥ 2 destinations | 6 | 5.9× |
| cycle | funds return to sender | 4 | — |
| structuring | $9,000 – $9,999 (just under threshold) | 3 | 2.7× |
| weekend | outside business week | 2 | 1.6× |
| fan_out | ≥ 7 destinations in 96 h | 1 | 1.4× |
| stack | layering chain ≥ 5 hops | 1 | 1.2× |
| scatter_gather | ≥ 8 destinations and ≥ 2 sources | — | shown, not scored |

### Features — 78 columns

| Family | Examples | Leakage rule |
|---|---|---|
| **Transaction** | amount bands, cross-bank, cross-currency, hour, format | stateless |
| **Behavioural** | rolling counts/sums/counterparties over 24 h / 96 h / 192 h | window `[t−w, t)` |
| **Graph** | degree, PageRank, community, chain depth, cycle length | previous bucket only |

---

## Graph Layer (Neo4j)

Only alerted accounts and one hop of neighbours are loaded — not all 5 M transactions.

**Schema:** `(:Account {id})-[:SENT {txn_id, amount, timestamp, is_laundering}]->(:Account)`

| Query | What it finds |
|---|---|
| `connected_accounts` | direct counterparties, both directions |
| `money_flow` | where funds went, up to N hops |
| `find_cycles` | money returning to the sender — the layering signature |
| `shortest_path` | how two accounts are connected |
| `fraud_ring` | accounts sharing ≥ 3 counterparties — possible coordinated ring |
| `account_summary` | totals sent / received |

`find_cycles` on a hub account takes ~30 s (cached after first call).

---

## Investigation Agents (LLM)

Both modes share `ml/agent/tools.py::ToolBox` — 13 thin wrappers over the pipeline. The agent owns no detection logic; the same functions serve the CLI, the report, and the LLM.

**Investigate** (`agent.py`) — not autonomous. `gather()` runs a fixed evidence set, `narrate()` gives Gemini one shot at prose over it (temperature 0.2). Reproducible and auditable. Falls back to a deterministic template if no API key is set.

**Ask** (`ask.py`) — autonomous tool use. Tool specs become Gemini function declarations; a manual loop executes each requested tool, records `{tool, args, result, ms}`, feeds results back, and stops when the model answers or after 8 rounds. Full trace shown in the UI (temperature 0.1).

**Prompt rules** (`prompts.py`): use only given figures · say plainly when evidence is absent · describe behaviour, never assert guilt · name typologies when evidence supports it · no hallucinated amounts.

---

## API Reference

Base path: `/api` · Interactive docs: `http://localhost:8000/docs`

| Method | Path | Description |
|---|---|---|
| GET | `/health` | Model / Neo4j / LLM status — never 503s |
| GET | `/stats` | Band counts, precision, daily volumes, base rate |
| GET | `/alerts` | Paginated queue — `band`, `min_score`, `page`, `sort` params |
| GET | `/alerts/{id}` | Full case: risk, rules, SHAP drivers, money flow, counterparties |
| GET | `/alerts/{id}/report` | Markdown SAR-draft report |
| POST/GET | `/alerts/{id}/investigate` | 202 → poll; `?force=true` re-runs |
| POST/GET | `/ask` · `/ask/{job_id}` | Free-text question → answer + tool trace |
| GET | `/accounts/{id}` | Activity, worst band, graph neighbours |
| GET | `/accounts/{id}/graph` | Nodes + edges for visualisation (`hops=1\|2`) |
| GET | `/transactions/{id}` | Raw transaction with band if scored |
| POST | `/predict` | Score ad-hoc transaction ids or feature rows |

---

## Frontend

React 19 · Vite · TypeScript · Tailwind 4 · TanStack Query 5 · react-router 7

| Route | Screen |
|---|---|
| `/` | **Queue** — band cards toggle filters, sortable paginated table, state in URL |
| `/alerts/:id` | **Case file** — score, SHAP bars, rules, money flow, mini-graph, narrative, SAR tab |
| `/accounts/:id` | **Account network** — force-directed graph, counterparties, cycles, peers |
| `/overview` | **Risk overview** — stat tiles, daily chart, precision by band, top HIGH |
| `/ask` | **Investigation agent** — question, live job progress, answer + tool trace |

Light and dark themes (follows OS by default, toggle in header). Every panel shows a source tag so the origin of each number is always visible.

---

## Repository Layout

```
ml/                     ML pipeline (importable)
  data.py               load + clean raw CSV
  features/             transaction · behavioral · graph · build
  models/               xgb · rules · iforest · fusion
  graph/                Neo4j loader + Cypher queries
  agent/                tools · agent · ask · report · prompts
  scripts/              build_features · train · train_iforest · load_graph
                        score · evaluate · investigate · run_eda
backend/                FastAPI (main · deps · schemas · routers/)
frontend/               React app (src/api · src/components · src/pages · src/lib)
configs/                config.yaml · rules.yaml · features.yaml
data/raw/               HI-Small_Trans.csv · HI-Small_Patterns.txt   ← not committed
data/processed/         features.parquet · transactions_clean.parquet ← generated
models/                 xgb.json · xgb_columns.json · iforest.joblib  ← generated
```

---

## Setup

**Requirements:** Python 3.11 · Node 20+ · Neo4j 5 on `bolt://localhost:7687` · Gemini API key (optional)

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env            # fill NEO4J_PASSWORD and GEMINI_API_KEY
cd frontend && npm install && cd ..
```

Place `HI-Small_Trans.csv` and `HI-Small_Patterns.txt` in `data/raw/`, then build the artefacts once:

```bash
.venv/bin/python -m ml.scripts.build_features   # ~2 GB parquet, several minutes
.venv/bin/python -m ml.scripts.train            # models/xgb.json
.venv/bin/python -m ml.scripts.train_iforest    # models/iforest.joblib
.venv/bin/python -m ml.scripts.load_graph       # alerted accounts → Neo4j
```

---

## Running

```bash
# Terminal 1 — backend (loads pipeline once, ~10 s)
.venv/bin/uvicorn backend.main:app --reload --port 8000

# Terminal 2 — frontend
cd frontend && npm run dev
```

Open **http://localhost:5173**. Check **http://localhost:8000/api/health** for system status.

**CLI equivalents:**

```bash
.venv/bin/python -m ml.scripts.score --top 5
.venv/bin/python -m ml.scripts.investigate --txn 4565663
.venv/bin/python -m ml.scripts.evaluate
```

---

## Configuration

| File | Controls |
|---|---|
| `.env` | `NEO4J_URI` · `NEO4J_PASSWORD` · `GEMINI_API_KEY` · `GEMINI_MODEL` |
| `configs/config.yaml` | Dataset filenames, FX-to-USD table |
| `configs/rules.yaml` | Amount bands, rolling windows, rule thresholds and weights |
| `ml/models/fusion.py` | Band cut-offs (99.9 / 99 / 95th percentile), escalation logic |

Thresholds are committed — they are part of the methodology. Secrets never are.

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| `Address already in use` | `lsof -ti :8000 \| xargs kill -9` — a Ctrl+Z'd process ignores plain `kill` |
| Vite refuses port 5174 | `strictPort` is on; free 5173 instead |
| Header shows *Degraded · neo4j* | Neo4j down or wrong password. Queue and case file still work; graph views return 503 |
| `/accounts/{id}` takes ~30 s | `find_cycles` on a hub account — cached after first call |
| Ask returns 503 | `GEMINI_API_KEY` missing in `.env` |
| `pipeline failed to load` | Run the setup scripts; the error message lists the missing paths |

---

## Caveats

- **Synthetic data.** Thresholds reflect the IBM generator, not real banking behaviour. Re-derive on real data before any operational use.
- **Labels are shown in the UI** (`ground_truth_label`, precision figures) for evaluation purposes. Remove before deployment.
- **`/predict` needs a full feature row.** Scoring a raw new transaction requires rebuilding behavioural and graph features against history — not exposed.
- **Single process.** State is ~2–3 GB in memory; run one worker. Job results are lost on restart.
- **This is a prioritisation aid on synthetic data, not a determination of wrongdoing.**
