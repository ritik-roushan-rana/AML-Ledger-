# ── Stage 1: build deps ───────────────────────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /app

# system libs needed by pyarrow / scipy / shap
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install --no-cache-dir --prefix=/install -r requirements.txt


# ── Stage 2: runtime ──────────────────────────────────────────────────────
FROM python:3.11-slim

WORKDIR /app

# copy installed packages from builder
COPY --from=builder /install /usr/local

# copy source code and committed artefacts
# (model files are committed; parquet files come from a Railway volume)
COPY backend/   ./backend/
COPY ml/        ./ml/
COPY configs/   ./configs/
COPY models/    ./models/

# data/processed is NOT in git (too large).
# Railway mounts a volume at /app/data/processed — we just ensure the
# directory exists so the app can start without the mount (returns 503
# from /api/health until the volume is attached and populated).
RUN mkdir -p data/processed data/raw data/graph outputs/figures outputs/alerts outputs/reports

# never run as root
RUN useradd -m appuser && chown -R appuser /app
USER appuser

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

EXPOSE 8000

CMD ["sh", "-c", "uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
