"""Parse HI-Small_Patterns.txt into a typology table.

File structure:
    BEGIN LAUNDERING ATTEMPT - FAN-OUT
    <csv rows, same columns as Trans.csv, no header>
    END LAUNDERING ATTEMPT - FAN-OUT

These transactions are ALREADY labelled 1 in Trans.csv.
Use this for rule tuning and evaluation ONLY -- never as a feature.

Bank IDs here are zero-padded ("021174") while read_csv strips them to
ints ("21174"), so lstrip("0") is required for the keys to join.
"""
import re

import pandas as pd

from ml import config

log = config.get_logger("patterns")

BEGIN = re.compile(r"BEGIN LAUNDERING ATTEMPT\s*-\s*(.+)", re.I)
END = re.compile(r"END LAUNDERING ATTEMPT", re.I)

COLS = ["timestamp", "from_bank", "from_account", "to_bank", "to_account",
        "amount_received", "currency_received", "amount_paid",
        "currency_paid", "payment_format", "is_laundering"]


def parse() -> pd.DataFrame:
    """One row per transaction, tagged with its pattern type and group id."""
    path = config.DATA_RAW / config.CFG["dataset"]["patterns"]
    if not path.exists():
        raise FileNotFoundError(f"Put the patterns file at {path}")

    rows, current, group = [], None, -1
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            m = BEGIN.search(line)
            if m:
                # "FAN-OUT:  MAX 16-DEGREE FAN-OUT" -> "FAN-OUT"
                current = m.group(1).strip().upper().split(":")[0].strip()
                group += 1
                continue
            if END.search(line):
                current = None
                continue
            if current is None:
                continue
            parts = line.split(",")
            if len(parts) != len(COLS):
                continue
            rows.append(parts + [current, group])

    df = pd.DataFrame(rows, columns=COLS + ["pattern", "group_id"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], format="%Y/%m/%d %H:%M",
                                     errors="coerce")
    for c in ["amount_paid", "amount_received"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")

    # lstrip("0") so "021174" matches the int-parsed "21174" from the csv
    df["from_id"] = (df["from_bank"].astype(str).str.strip().str.lstrip("0") +
                     "-" + df["from_account"].astype(str).str.strip())
    df["to_id"] = (df["to_bank"].astype(str).str.strip().str.lstrip("0") +
                   "-" + df["to_account"].astype(str).str.strip())

    fx = config.CFG["fx_to_usd"]
    df["amount_usd"] = df["amount_paid"] * df["currency_paid"].map(fx).fillna(1.0)

    log.info("parsed %s txns across %s groups, %s pattern types",
             f"{len(df):,}", f"{df.group_id.nunique():,}", df.pattern.nunique())
    df.to_parquet(config.DATA_PROCESSED / "patterns.parquet")
    return df


def profile(df: pd.DataFrame) -> pd.DataFrame:
    """Per-typology stats. THIS is what sets the rule thresholds."""
    g = df.groupby("group_id").agg(
        pattern=("pattern", "first"),
        n_txn=("amount_usd", "size"),
        n_senders=("from_id", "nunique"),
        n_receivers=("to_id", "nunique"),
        total_usd=("amount_usd", "sum"),
        median_usd=("amount_usd", "median"),
        span_hours=("timestamp", lambda s: (s.max() - s.min()).total_seconds() / 3600),
    )
    return g.groupby("pattern").agg(
        groups=("n_txn", "size"),
        txn_med=("n_txn", "median"),
        senders_med=("n_senders", "median"),
        receivers_med=("n_receivers", "median"),
        receivers_p25=("n_receivers", lambda s: s.quantile(.25)),
        usd_med=("median_usd", "median"),
        span_h_med=("span_hours", "median"),
    ).round(2).sort_values("groups", ascending=False)