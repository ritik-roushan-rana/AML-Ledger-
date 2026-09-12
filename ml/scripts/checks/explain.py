"""python -m ml.scripts.checks.explain"""
from ml import config, explain
from ml.features import build
from ml.models import fusion
from ml.models import xgb as xgbm

X = build.load()
te = X[X["timestamp"] > X["timestamp"].quantile(0.85)]
model, cols = xgbm.load()
p = xgbm.predict(model, te[cols])
f = fusion.fuse(te, p)

ex = explain.make_explainer(model)

print("\nglobal importance (mean |SHAP|)")
print(explain.global_importance(ex, te[cols]).head(15).to_string(index=False))

top = f.sort_values("risk_score", ascending=False).head(3)
for i, (idx, row) in enumerate(top.iterrows(), 1):
    t = te.loc[idx]
    print(f"\n{'=' * 60}")
    print(f"ALERT {i}   {row['band']}   risk {row['risk_score']:.2f}   "
          f"action {row['action']}")
    print(f"{t['from_id']} -> {t['to_id']}   "
          f"${t['amount_usd']:,.0f}   {t['timestamp']}")
    print(f"actual label: {t['is_laundering']}")
    print("\nwhy flagged:")
    print(explain.format_drivers(explain.explain_one(ex, te.loc[[idx], cols])))