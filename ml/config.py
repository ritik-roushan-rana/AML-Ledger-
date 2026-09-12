"""Central config + path resolution. Import this, never hardcode a path.

Split of responsibility:
  .env          -> secrets and machine-specific connection details
  configs/*.yaml -> thresholds and parameters, committed to git because
                    they are part of the methodology a reviewer needs
"""
import logging
import os
from pathlib import Path

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env", override=True)

DATA_RAW = ROOT / "data" / "raw"
DATA_PROCESSED = ROOT / "data" / "processed"
DATA_GRAPH = ROOT / "data" / "graph"
MODELS = ROOT / "models"
OUT_FIGURES = ROOT / "outputs" / "figures"
OUT_ALERTS = ROOT / "outputs" / "alerts"
OUT_REPORTS = ROOT / "outputs" / "reports"

for _d in (DATA_PROCESSED, DATA_GRAPH, MODELS, OUT_FIGURES, OUT_ALERTS,
           OUT_REPORTS):
    _d.mkdir(parents=True, exist_ok=True)


def load(name: str = "config") -> dict:
    path = ROOT / "configs" / f"{name}.yaml"
    with open(path) as f:
        return yaml.safe_load(f) or {}


# --- secrets, from .env only -------------------------------------------
def neo4j_uri() -> str:
    return os.environ.get("NEO4J_URI", "bolt://localhost:7687")


def neo4j_user() -> str:
    return os.environ.get("NEO4J_USER", "neo4j")


def neo4j_password() -> str:
    return os.environ.get("NEO4J_PASSWORD", "")


def gemini_key() -> str:
    return os.environ.get("GEMINI_API_KEY", "")


def gemini_model() -> str:
    return os.environ.get("GEMINI_MODEL", "gemini-3.5-flash-lite")


def get_logger(name: str) -> logging.Logger:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-7s %(name)s  %(message)s",
        datefmt="%H:%M:%S",
    )
    return logging.getLogger(name)


CFG = load()