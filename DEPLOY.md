# Deployment Guide

Stack: **Railway** (backend) · **Neo4j AuraDB** (graph DB) · **Vercel** (frontend)

---

## 1. Neo4j AuraDB (do this first, you need the URI)

1. Go to [console.neo4j.io](https://console.neo4j.io) → **New Instance** → Free tier
2. Download the generated credentials file — it contains your URI, username, and password
3. Note the connection URI — it looks like `neo4j+s://xxxxxxxx.databases.neo4j.io`
4. Once the instance is running, load your graph data from your local machine:

```bash
# set your AuraDB creds in .env first, then:
NEO4J_URI=neo4j+s://xxxxxxxx.databases.neo4j.io \
NEO4J_USER=neo4j \
NEO4J_PASSWORD=your-aura-password \
.venv/bin/python -m ml.scripts.load_graph
```

---

## 2. Backend on Railway

### 2a. Commit model files and push

The model files are small enough to commit (models/ is now unblocked in .gitignore):

```bash
git add models/xgb.json models/xgb_columns.json models/iforest.joblib
git add requirements.txt railway.toml Dockerfile backend/main.py .gitignore
git commit -m "chore: add deployment config"
git push
```

### 2b. Create Railway project

1. Go to [railway.app](https://railway.app) → **New Project** → **Deploy from GitHub repo**
2. Select your repo — Railway will detect the `Dockerfile` automatically
3. Set these environment variables in Railway → **Variables**:

| Variable | Value |
|---|---|
| `NEO4J_URI` | `neo4j+s://xxxxxxxx.databases.neo4j.io` |
| `NEO4J_USER` | `neo4j` |
| `NEO4J_PASSWORD` | your AuraDB password |
| `GEMINI_API_KEY` | your Gemini key (or leave blank to disable LLM) |
| `GEMINI_MODEL` | `gemini-2.0-flash` |
| `ALLOWED_ORIGIN` | your Vercel URL (fill in after step 3, e.g. `https://aml-ledger.vercel.app`) |

### 2c. Mount the data volume

The two large parquet files (`features.parquet` 1.2 GB, `transactions_clean.parquet` 298 MB) are too large for git. You need to upload them to a Railway volume:

1. In your Railway service → **Volumes** → **Add Volume**
2. Mount path: `/app/data/processed`
3. Upload the files using the Railway CLI:

```bash
npm install -g @railway/cli
railway login
railway link          # link to your project
railway volume cp data/processed/features.parquet /app/data/processed/features.parquet
railway volume cp data/processed/transactions_clean.parquet /app/data/processed/transactions_clean.parquet
```

> **Alternative:** If you prefer not to use volumes, you can also use any S3-compatible storage (e.g. Cloudflare R2 free tier) and add a small download step to the Dockerfile's CMD. See the note at the bottom of this file.

### 2d. Deploy

Railway deploys automatically on push. Watch the build logs — startup takes ~30–60s while models load.

Check: `https://your-railway-url.up.railway.app/api/health`

---

## 3. Frontend on Vercel

1. Go to [vercel.com/new](https://vercel.com/new) → Import your GitHub repo
2. Set **Root Directory** to `frontend`
3. Add one environment variable:

| Variable | Value |
|---|---|
| `VITE_API_BASE` | `https://your-railway-url.up.railway.app` |

4. Click **Deploy** — Vercel runs `npm run build` automatically

5. Once deployed, copy your Vercel URL (e.g. `https://aml-ledger.vercel.app`) and paste it into the Railway `ALLOWED_ORIGIN` variable, then redeploy the backend.

---

## Verification checklist

- [ ] `GET /api/health` returns `200` with `model: true`
- [ ] `GET /api/health` shows `neo4j.reachable: true`
- [ ] Frontend loads at the Vercel URL
- [ ] Alert queue populates on `/`
- [ ] Account graph renders on `/accounts/:id` (confirms Neo4j)
- [ ] `/ask` returns an answer (confirms Gemini key)

---

## Optional: S3 approach for large parquet files

If Railway volumes feel heavy, an alternative is to store the parquets in Cloudflare R2 (free for 10 GB) and download them at container startup:

```dockerfile
# Add to Dockerfile CMD, before uvicorn:
CMD ["sh", "-c", "python -c \"import boto3; ...\" && uvicorn backend.main:app ..."]
```

Or add a `startup.sh` script that pulls from R2 using `rclone` or `aws s3 cp` before starting uvicorn. The `/api/health` endpoint will return `503` until the files are in place, which is safe — the app won't crash.

---

## Local dev (unchanged)

```bash
.venv/bin/uvicorn backend.main:app --reload --port 8000
cd frontend && npm run dev
```
