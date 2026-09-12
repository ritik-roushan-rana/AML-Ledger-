"""Load and clean the IBM AML transaction file.

Two traps this module exists to handle:
  1. "Account" is only unique WITHIN a bank -> build composite keys.
  2. Amount Paid != Amount Received across currencies -> normalise.
"""
import pandas as pd

from ml import config

log = config.get_logger("data")

RENAME = {
    "Timestamp": "timestamp",
    "From Bank": "from_bank",
    "Account": "from_account",
    "To Bank": "to_bank",
    "Account.1": "to_account",
    "Amount Received": "amount_received",
    "Receiving Currency": "currency_received",
    "Amount Paid": "amount_paid",
    "Payment Currency": "currency_paid",
    "Payment Format": "payment_format",
    "Is Laundering": "is_laundering",
}


def load_raw(nrows: int | None = None) -> pd.DataFrame:
    path = config.DATA_RAW / config.CFG["dataset"]["transactions"]
    if not path.exists():
        raise FileNotFoundError(f"Put the IBM csv at {path}")
    df = pd.read_csv(path, nrows=nrows).rename(columns=RENAME)
    missing = set(RENAME.values()) - set(df.columns)
    if missing:
        raise ValueError(f"Unexpected columns, missing: {sorted(missing)}")
    log.info("loaded %s rows from %s", f"{len(df):,}", path.name)
    return df


def clean(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    df["timestamp"] = pd.to_datetime(df["timestamp"], format="%Y/%m/%d %H:%M",
                                     errors="coerce")
    bad = df["timestamp"].isna().sum()
    if bad:
        log.warning("dropping %d rows with unparseable timestamps", bad)
        df = df.dropna(subset=["timestamp"])

    df["from_id"] = df["from_bank"].astype(str) + "-" + df["from_account"].astype(str)
    df["to_id"] = df["to_bank"].astype(str) + "-" + df["to_account"].astype(str)

    fx = config.CFG["fx_to_usd"]
    unknown = set(df["currency_paid"].unique()) - set(fx)
    if unknown:
        log.warning("no fx rate for %s -- treated as 1.0", sorted(unknown))
    df["amount_usd"] = df["amount_paid"] * df["currency_paid"].map(fx).fillna(1.0)

    df["is_cross_currency"] = df["currency_paid"] != df["currency_received"]
    df["is_cross_bank"] = df["from_bank"] != df["to_bank"]
    df["is_self_loop"] = df["from_id"] == df["to_id"]

    before = len(df)
    df = df.drop_duplicates()
    if before != len(df):
        log.info("dropped %d exact duplicate rows", before - len(df))

    df = df.sort_values("timestamp").reset_index(drop=True)
    df["txn_id"] = df.index
    log.info("clean: %s rows, %s accounts, %.4f%% laundering",
             f"{len(df):,}",
             f"{pd.concat([df.from_id, df.to_id]).nunique():,}",
             100 * df["is_laundering"].mean())
    return df


def time_split(df: pd.DataFrame, train_end: str, val_end: str):
    """Chronological split. Never shuffle -- graph features leak backwards."""
    train = df[df["timestamp"] <= train_end]
    val = df[(df["timestamp"] > train_end) & (df["timestamp"] <= val_end)]
    test = df[df["timestamp"] > val_end]
    log.info("split -> train %s | val %s | test %s",
             f"{len(train):,}", f"{len(val):,}", f"{len(test):,}")
    return train, val, test