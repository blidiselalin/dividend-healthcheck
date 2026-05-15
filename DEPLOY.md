# Deploy DividendScope online (free)

The easiest free host for this app is **[Streamlit Community Cloud](https://streamlit.io/cloud)** (public URL, connects to GitHub).

## Prerequisites

1. Code pushed to a **public** GitHub repository (or private with Streamlit Teams).
2. Main entry file: `app.py` at the repository root.
3. Dependencies: `requirements.txt` at the repository root.

This repo is already wired for cloud:

- `DIVIDENDSCOPE_CLOUD` / Streamlit host detection → uses `./data` instead of `~/.motion/dividendscope`
- Lighter cold start (no full yfinance enrich on boot)
- Portfolio risk scan is **manual** on cloud (sidebar button) so the app does not time out

## Step 1 — Push to GitHub

```bash
git add app.py config.py requirements.txt .streamlit/ DEPLOY.md .python-version
git commit -m "Add Streamlit Community Cloud deployment config"
git push origin main
```

If your default branch is `master`, use that name in Streamlit instead of `main`.

## Step 2 — Create the Streamlit app

1. Sign in at [https://share.streamlit.io](https://share.streamlit.io) with GitHub.
2. Click **Create app**.
3. Select repository: `blidiselalin/dividend-healthcheck` (or your fork).
4. **Branch:** `main` (or `master`).
5. **Main file path:** `app.py`.
6. **App URL:** choose a subdomain, e.g. `dividendscope.streamlit.app`.

## Step 3 — Secrets (recommended)

In the app → **Settings** → **Secrets**, paste:

```toml
DIVIDENDSCOPE_CLOUD = "true"
DIVIDENDSCOPE_DATA_DIR = "data"
```

Save. The app will redeploy automatically.

## Step 4 — First use after deploy

| Feature | On cloud |
|--------|----------|
| Single Stock / Kings | Works via yfinance when vector DB is empty |
| Portfolio Details | Click **Run portfolio scan (~1–2 min)** in the sidebar first |
| Vector DB | Ephemeral — resets when the app sleeps; re-run ingest locally and export if you need a persistent DB in git |

To pre-fill the vector DB in the cloud (optional, advanced):

1. Locally: `python ingest_data.py --enrich` then `python ingest_data.py --sync-portfolio`
2. Zip `data/vectordb` (keep under ~100 MB for GitHub)
3. Commit under `data/vectordb` in the repo (remove `data/` from `.gitignore` for that folder only) and redeploy

## Troubleshooting

| Issue | Fix |
|-------|-----|
| Build fails on ChromaDB | Ensure `requirements.txt` is at repo root; Python **3.12** (`.python-version`) |
| App spins then errors | Check **Manage app → Logs** |
| Portfolio tab empty | Run sidebar **Run portfolio scan** |
| Slow first load | Normal — cloud uses live APIs until vector DB is bundled |

## Other free options

| Platform | Notes |
|----------|--------|
| [Render](https://render.com) | Free web service; sleeps after inactivity; add a `Dockerfile` if needed |
| [Hugging Face Spaces](https://huggingface.co/spaces) | Streamlit SDK; similar ephemeral storage |

Streamlit Community Cloud remains the best fit for this project.
