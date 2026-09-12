# Architecture

## Data flow

```
data/raw/HI-Small_Trans.csv (5.08 M txns)          data/raw/HI-Small_Patterns.txt (370 labelled groups)
          │                                                      │
     ml/data.py  clean · composite account ids · FX → USD        ml/patterns.py  typology profiles → rule thresholds
          │
     ml/features/  transaction (stateless) · behavioral (rolling, past-only) · graph (previous bucket only)
          │
     data/processed/features.parquet   5,078,336 rows × 78 features + ids + label
          │
   ┌──────┴───────────────────────┬───────────────────────────┐
 ml/models/xgb              ml/models/rules              ml/models/iforest
 supervised booster         9 typology rules             unsupervised, 43 behavioural cols
 → probability, percentile  → fired flags, rule_score    → anomaly percentile
   └──────┬───────────────────────┴───────────────────────────┘
     ml/models/fusion.py
       band   = percentile ≥ 99.9 HIGH · ≥ 99 MEDIUM · ≥ 95 LOW · else CLEAR
       escalate one band when ≥ 2 of {cycle, fan_in, gather_scatter, amount_band} fire
       action = REPORT / REVIEW / MONITOR / NONE
       anomaly_pct attached as evidence (never changes band)
          │
   ┌──────┴──────────────┬────────────────────────┐
 ml/explain (SHAP)   ml/graph (Neo4j)        ml/agent/tools.ToolBox  (13 tools wrapping the above)
   └──────┬──────────────┴────────────────────────┘
     ml/agent/agent.py   gather() → fixed evidence set → narrate() (Gemini, prose only)
     ml/agent/ask.py     LLM chooses tools, answers, returns an auditable trace
     ml/agent/report.py  markdown case file
          │
     backend/  FastAPI — loads everything once at startup, serves JSON
          │
     frontend/  React — queue · case file · account network · overview · ask
```

## Why the score is shaped like this

**Percentile, not probability.** XGBoost is trained with `scale_pos_weight ≈ 1000`. That makes ranking good (PR-AUC 0.374 vs 0.002 base rate) but probabilities meaningless — the top decile averages p = 0.16 against an actual 1.8 % positive rate. Bands are therefore cut on percentile rank.

**Rules do not rank.** Rules-only PR-AUC is 0.004. Blending them into the score drops XGBoost from 0.374 to 0.189, because 95 % of rows share a near-zero model score and the rules then dominate ordering. So rules do two things only: escalate a band when ≥ 2 precise rules co-fire (precision at the margin), and provide the sentences an investigator reads.

**Isolation Forest is evidence.** Alone it scores PR-AUC 0.002 — random. It answers a different question ("is this behaviour unusual regardless of label?") which matters for typologies the supervised model never saw, so it is shown as a percentile and never fused.

**Leakage discipline.** Behavioural windows cover `[t − window, t)` excluding the current row; graph features are built from the *previous* time bucket only; the train/val/test split is by row quantile (70 / 85 %) because the dataset has a thin calendar tail that would otherwise produce a 74-row test set.

**LLM writes prose only.** Every figure in a narrative or answer comes from a tool result. See [agent.md](agent.md).

## Runtime shape

- **Backend state is loaded once** in a FastAPI lifespan handler (`backend/deps.py`): test-period matrix (761,635 rows), raw transactions, booster, SHAP explainer, fused frame, Isolation Forest, precomputed stats and per-account risk. ~10 s on a laptop.
- **Long work is a job.** `/investigate` and `/ask` return 202 with a job id and are polled; they run on a small thread pool so a 30 s Cypher query never blocks the queue.
- **Failure is partial, not total.** A missing model file or unreachable Neo4j is reported by `/health`; only the endpoints that need the missing piece return 503.
- **Neo4j holds a subset**: alerted accounts plus one hop of neighbours, not all 5 M transactions.
