# Operations

## Requirements

- Python 3.11, Node 20+
- Neo4j 5 on `bolt://localhost:7687` (only needed for graph views and the agents)
- Gemini API key (optional: without it narratives use the template fallback and `/ask` returns 503)
- ~4 GB free disk for `data/processed`, ~3 GB RAM for the backend

## First-time setup

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env                 # NEO4J_PASSWORD, GEMINI_API_KEY, optionally GEMINI_MODEL
cd frontend && npm install && cd ..

# put HI-Small_Trans.csv + HI-Small_Patterns.txt in data/raw/, then:
.venv/bin/python -m ml.scripts.build_features   # ~2 GB parquet, several minutes
.venv/bin/python -m ml.scripts.train
.venv/bin/python -m ml.scripts.train_iforest
.venv/bin/python -m ml.scripts.load_graph       # needs Neo4j running
```

`.env` is read with `override=True`, so it wins over shell variables.

## Run

```bash
.venv/bin/uvicorn backend.main:app --reload --port 8000
cd frontend && npm run dev
```

Open `http://localhost:5173`. Check `http://localhost:8000/api/health` if the header pill isn't green.

`.claude/launch.json` defines both servers for the Claude desktop app's preview.

## Startup behaviour

`backend/deps.py::load_state` runs once in the lifespan handler: loads `features.parquet`, keeps rows after the 85 % timestamp quantile, loads the booster + Isolation Forest, scores and fuses, builds the SHAP explainer and `ToolBox`, precomputes stats and per-account risk. ~7–10 s on a laptop.

If it fails, the app still starts: `/health` shows `status: "error"` and `load_error`; everything else returns 503. Missing `iforest.joblib` is *not* fatal (anomaly fields are just null).

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `Address already in use` on 8000 or 5173 | A server is already running — usually the one you want. `lsof -ti :8000 \| xargs kill -9` if it's stale. **Ctrl+Z suspends a process and keeps the port; use Ctrl+C.** |
| Vite starts on 5174 | It won't: `strictPort` is on because the backend CORS list is pinned to 5173. Free 5173 instead. |
| Header pill says *Degraded · neo4j* | Neo4j down or wrong password. Queue/detail/report still work; account graph, mini-graph, investigate and ask return 503. `neo4j start`, check `NEO4J_PASSWORD`. |
| `/accounts/{id}` takes ~30 s | `find_cycles` (`SENT*2..6`) on a hub account. Cached after the first call. Lower `max_hops` in `ml/graph/queries.py` if needed. |
| `/accounts/{id}/graph` 404s | Only alerted accounts + one hop are loaded into Neo4j (`loader.scope`). |
| Investigate returns the same text after "Re-run" | Results are cached per txn; the UI sends `?force=true` on re-run, a raw POST does not. |
| Ask returns 503 | `GEMINI_API_KEY` missing or literally `your_key_here`. |
| `pipeline failed to load: missing artefacts` | Run the setup scripts above; the message lists the missing paths. |
| Stale frontend after editing `hooks.ts` | HMR can log "change in the order of Hooks" when a hook gains state mid-session; a page reload clears it. |

## Where things are written

| Path | Contents | Committed? |
|---|---|---|
| `data/processed/` | `features.parquet`, `transactions_clean.parquet`, `account_activity.parquet`, `patterns.parquet` | no |
| `models/` | `xgb.json`, `xgb_columns.json`, `iforest.joblib` | no |
| `outputs/` | EDA summary + figures, CLI-generated reports | no |
| `configs/` | thresholds and FX table — part of the methodology | yes |

## Housekeeping

- Ground-truth labels are exposed (`ground_truth_label`, precision figures) for evaluation. Strip them before showing this to anyone who could act on it.
- Job results (`investigate`, `ask`) live in process memory; a restart forgets them.
- The backend is single-process; run one uvicorn worker (the state is 2–3 GB).
