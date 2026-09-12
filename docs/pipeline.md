# ML pipeline

## Dataset

IBM AML synthetic dataset, **HI-Small** variant: 5,078,336 transactions, 0.10 % labelled laundering overall (0.205 % in the test window). `HI-Small_Patterns.txt` lists 370 labelled laundering groups by typology (fan-in, fan-out, cycle, stack, scatter-gather, gather-scatter, bipartite) and was used to *derive* rule thresholds, not to train the model.

Two traps `ml/data.py` handles: account numbers are unique only within a bank (composite `bank-account` ids), and amounts differ across currencies (normalised to USD with the FX table in `configs/config.yaml`).

## Features (78)

| Family | File | Examples | Leakage rule |
|---|---|---|---|
| Transaction | `features/transaction.py` | amount bands (3k–20k, 9k–20k), just-below-10k, cross-bank, cross-currency, hour, weekday, currency, format | stateless — one row in, one row out |
| Behavioural | `features/behavioral.py` | per-account counts / sums / distinct counterparties over 24 h, 96 h, 192 h windows; hours since previous in/out; new-sender / new-receiver; in/out ratio | window is `[t − w, t)`, current row excluded |
| Graph | `features/graph.py` | degree, PageRank, community size, same-community, triangle, `g_chain_depth`, `g_cycle_len`, reciprocity | graph built from the previous 24 h bucket only |

Roundness features were tested and dropped: round amounts launder at ~1/12 the base rate in this generator.

## Models

**XGBoost** (`models/xgb.py`) — `binary:logistic`, depth 6, lr 0.05, `scale_pos_weight` = negative/positive ratio, early stopping on validation PR-AUC. All 78 features.

**Rules** (`models/rules.py`, thresholds in `configs/rules.yaml`) — nine deterministic typology checks evaluated on the feature matrix. Weights are proportional to measured lift on the test period:

| Rule | Condition | Weight (lift) |
|---|---|---|
| fan_in | ≥ 8 distinct sources in 96 h | 8 (8.5×) |
| amount_band | 9k ≤ amount ≤ 20k | 6 (6.2×) |
| gather_scatter | ≥ 7 sources in 192 h and ≥ 2 destinations | 6 (5.9×) |
| cycle | `g_cycle_len` ≥ 2 | 4 |
| structuring | 9,000–9,999 | 3 (2.7×) |
| weekend | | 2 (1.6×) |
| fan_out | ≥ 7 destinations in 96 h | 1 (1.4×) |
| stack | `g_chain_depth` ≥ 5 | 1 (1.2×) |
| scatter_gather | ≥ 8 destinations and ≥ 2 sources | 0 (0.9×, shown only) |

Amounts above 20k are hard-ruled out (nothing above the ceiling launders in this dataset).

**Isolation Forest** (`models/iforest.py`) — 200 trees, 256-sample, fit on 500k training rows over the 43 numeric behavioural columns; output converted to a percentile against the training distribution.

**Fusion** (`models/fusion.py`) — see [architecture.md](architecture.md#why-the-score-is-shaped-like-this).

## Split & evaluation

Row-quantile split on timestamp: train ≤ 70 %, validation 70–85 %, **test > 85 % (761,635 rows, 1,561 positives)**. `ml/evaluation.py` reports PR-AUC, ROC-AUC and precision/recall at fixed alert budgets — accuracy is meaningless at this base rate.

| | PR-AUC | Notes |
|---|---|---|
| XGBoost | **0.374** | ranks the queue |
| Rules only | 0.004 | evidence + escalation |
| Isolation Forest only | 0.002 | evidence |
| Amount-band baseline | — | the "9k–20k" heuristic a bank might start from |

Per-band precision on the test period (what the UI shows):

| Band | Alerts | Positives | Precision |
|---|---|---|---|
| HIGH | 819 | 492 | 60.1 % |
| MEDIUM | 6,953 | 427 | 6.1 % |
| LOW | 30,310 | 346 | 1.1 % |
| CLEAR | 723,553 | 296 | 0.04 % |

## Explainability

`ml/explain.py` uses SHAP `TreeExplainer` (exact for trees). `LABELS` maps column names to sentences (`out_96h_ncp` → "sender paid distinct accounts in the last 96h"), because a feature name is not evidence an analyst can act on.

## Scripts

```
python -m ml.scripts.build_features     # raw csv → features.parquet (~2 GB)
python -m ml.scripts.train              # XGBoost → models/xgb.json (+ test report)
python -m ml.scripts.train_iforest      # → models/iforest.joblib
python -m ml.scripts.load_graph         # alerted neighbourhoods → Neo4j
python -m ml.scripts.evaluate           # metrics on the held-out period
python -m ml.scripts.score --top 5      # print top alerts
python -m ml.scripts.investigate --txn 4565663   # full narrative + report to outputs/reports/
python -m ml.scripts.run_eda            # outputs/eda_summary.json + figures
python -m ml.scripts.run_patterns       # typology profiles from Patterns.txt
python -m ml.scripts.checks.<name>      # dev sanity checks (rules, fusion, explain, graph…)
```
