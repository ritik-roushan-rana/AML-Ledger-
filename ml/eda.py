"""EDA as a pipeline, not a notebook.

Every section returns a dict of findings. Those merge into
outputs/eda_summary.json, which feeds configs/rules.yaml and
configs/features.yaml -- so thresholds are evidence-based, not guessed.
"""
import json

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from ml import config

log = config.get_logger("eda")
FIG = config.OUT_FIGURES


def _save(fig, name):
    fig.tight_layout()
    fig.savefig(FIG / f"{name}.png", dpi=120)
    plt.close(fig)


def overview(df: pd.DataFrame) -> dict:
    n_pos = int(df["is_laundering"].sum())
    accounts = pd.concat([df["from_id"], df["to_id"]]).nunique()
    out = {
        "n_transactions": len(df),
        "n_accounts": int(accounts),
        "n_banks": int(pd.concat([df["from_bank"], df["to_bank"]]).nunique()),
        "n_laundering": n_pos,
        "positive_rate": round(float(df["is_laundering"].mean()), 6),
        "imbalance_ratio": round((len(df) - n_pos) / max(n_pos, 1), 1),
        "date_min": str(df["timestamp"].min()),
        "date_max": str(df["timestamp"].max()),
        "null_counts": {c: int(v) for c, v in df.isna().sum().items() if v},
    }
    log.info("1 in %s transactions is laundering", f"{out['imbalance_ratio']:,.0f}")
    return out


def amounts(df: pd.DataFrame) -> dict:
    """Percentiles drive the structuring / large-amount rule thresholds."""
    qs = [0.5, 0.75, 0.9, 0.95, 0.99, 0.999]
    legit = df.loc[df.is_laundering == 0, "amount_usd"]
    illicit = df.loc[df.is_laundering == 1, "amount_usd"]

    fig, ax = plt.subplots(figsize=(7, 4))
    bins = np.logspace(0, 8, 60)
    ax.hist(legit.clip(1), bins=bins, alpha=.6, density=True, label="legit")
    ax.hist(illicit.clip(1), bins=bins, alpha=.6, density=True, label="laundering")
    ax.set_xscale("log"); ax.set_xlabel("amount (USD, log)"); ax.legend()
    ax.set_title("Amount distribution by label")
    _save(fig, "amount_distribution")

    round_1k = df["amount_usd"].mod(1000).eq(0)
    return {
        "legit_percentiles": {str(q): round(float(legit.quantile(q)), 2) for q in qs},
        "illicit_percentiles": {str(q): round(float(illicit.quantile(q)), 2) for q in qs},
        "suggested_large_amount_threshold": round(float(legit.quantile(0.99)), 2),
        "round_1k_share_legit": round(float(round_1k[df.is_laundering == 0].mean()), 4),
        "round_1k_share_illicit": round(float(round_1k[df.is_laundering == 1].mean()), 4),
    }


def temporal(df: pd.DataFrame) -> dict:
    """Decides the train/val/test cut dates."""
    daily = df.set_index("timestamp").resample("D").agg(
        n=("txn_id", "size"), pos=("is_laundering", "sum"))

    fig, ax = plt.subplots(2, 1, figsize=(8, 5), sharex=True)
    ax[0].plot(daily.index, daily["n"]); ax[0].set_ylabel("transactions")
    ax[1].plot(daily.index, daily["pos"], color="crimson"); ax[1].set_ylabel("laundering")
    ax[0].set_title("Volume over time")
    _save(fig, "volume_over_time")

    hour = df.groupby(df["timestamp"].dt.hour)["is_laundering"].agg(["size", "mean"])
    fig, ax = plt.subplots(figsize=(7, 3.5))
    ax.bar(hour.index, hour["mean"])
    ax.set_xlabel("hour of day"); ax.set_ylabel("laundering rate")
    _save(fig, "hour_of_day")

    ts = df["timestamp"]
    span = ts.max() - ts.min()
    return {
        "n_days": int(daily.shape[0]),
        "median_daily_volume": int(daily["n"].median()),
        "suggested_train_end": str((ts.min() + span * 0.70).floor("D")),
        "suggested_val_end": str((ts.min() + span * 0.85).floor("D")),
        "laundering_rate_by_hour": {int(h): round(float(v), 6)
                                    for h, v in hour["mean"].items()},
    }


def categoricals(df: pd.DataFrame) -> dict:
    """Payment format and currency are strong, cheap features."""
    res = {}
    for col in ["payment_format", "currency_paid"]:
        g = df.groupby(col)["is_laundering"].agg(["size", "mean"])
        g = g.sort_values("mean", ascending=False)
        res[f"{col}_risk"] = {str(k): {"n": int(r["size"]),
                                       "rate": round(float(r["mean"]), 6)}
                              for k, r in g.iterrows()}
        fig, ax = plt.subplots(figsize=(7, 3.5))
        ax.barh(g.index.astype(str), g["mean"])
        ax.set_xlabel("laundering rate"); ax.set_title(f"Risk by {col}")
        _save(fig, f"risk_by_{col}")

    res["cross_currency_lift"] = _lift(df, "is_cross_currency")
    res["cross_bank_lift"] = _lift(df, "is_cross_bank")
    res["self_loop_lift"] = _lift(df, "is_self_loop")
    return res


def _lift(df, flag):
    base = df["is_laundering"].mean()
    sub = df.loc[df[flag], "is_laundering"].mean() if df[flag].any() else 0.0
    return round(float(sub / base) if base else 0.0, 3)


def accounts(df: pd.DataFrame) -> dict:
    """Account activity percentiles size the behavioral rolling windows."""
    sent = df.groupby("from_id").agg(n_sent=("txn_id", "size"),
                                     usd_sent=("amount_usd", "sum"),
                                     n_dest=("to_id", "nunique"))
    recv = df.groupby("to_id").agg(n_recv=("txn_id", "size"),
                                   usd_recv=("amount_usd", "sum"),
                                   n_src=("from_id", "nunique"))
    acct = sent.join(recv, how="outer").fillna(0)
    acct["degree"] = acct["n_dest"] + acct["n_src"]

    fig, ax = plt.subplots(figsize=(7, 4))
    ax.hist(acct["degree"].clip(1), bins=np.logspace(0, 3, 50))
    ax.set_xscale("log"); ax.set_yscale("log")
    ax.set_xlabel("degree (unique counterparties)"); ax.set_ylabel("accounts")
    ax.set_title("Degree distribution")
    _save(fig, "degree_distribution")

    acct.to_parquet(config.DATA_PROCESSED / "account_activity.parquet")
    total = acct[["n_sent", "n_recv"]].sum(1)
    return {
        "txns_per_account_p50": float(total.quantile(.5)),
        "txns_per_account_p95": float(total.quantile(.95)),
        "degree_p95": float(acct["degree"].quantile(.95)),
        "degree_p99": float(acct["degree"].quantile(.99)),
        "suggested_fan_out_threshold": int(acct["n_dest"].quantile(.99)),
        "suggested_fan_in_threshold": int(acct["n_src"].quantile(.99)),
        "share_single_txn_accounts": round(float((total == 1).mean()), 4),
    }


def run(df: pd.DataFrame) -> dict:
    summary = {
        "overview": overview(df),
        "amounts": amounts(df),
        "temporal": temporal(df),
        "categoricals": categoricals(df),
        "accounts": accounts(df),
    }
    path = config.ROOT / "outputs" / "eda_summary.json"
    path.write_text(json.dumps(summary, indent=2, default=str))
    log.info("wrote %s and %d figures", path.name, len(list(FIG.glob('*.png'))))
    return summary