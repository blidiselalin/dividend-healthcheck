# Deploy DividendScope on Google Cloud (free trial)

Use a **Compute Engine VM** with a **persistent boot disk**. Your ChromaDB (`vectordb/`) and SQLite (`portfolio.db`) live on disk and survive reboots.

**Do not set** `DIVIDENDSCOPE_CLOUD=true` on GCP — that mode is only for Streamlit Community Cloud. Use:

```bash
DIVIDENDSCOPE_DATA_DIR=/data
```

(Docker Compose sets this automatically.)

---

## Before you start

1. [Google Cloud Console](https://console.cloud.google.com/) — sign in and accept the **$300 free trial** (90 days).
2. **Billing → Budgets & alerts** — create a budget (e.g. $10) with email alerts so you notice spend before the trial ends.
3. This guide uses about **$8–15/month** for an `e2-small` VM (2 vCPU, 2 GB RAM) if left running 24/7 — covered by trial credits.

---

## Step 1 — Create a project

1. Top bar → **Select project** → **New project**.
2. Name: `dividendscope` → **Create**.
3. Select that project.

---

## Step 2 — Enable Compute Engine

1. **APIs & Services** → **Library** → search **Compute Engine API** → **Enable**.

---

## Step 3 — Create a VM

1. **Compute Engine** → **VM instances** → **Create instance**.

| Setting | Value |
|--------|--------|
| Name | `dividendscope` |
| Region | `us-central1` (or any you prefer) |
| Zone | Any |
| Machine type | **e2-small** (2 vCPU, 2 GB) — minimum for ChromaDB |
| Boot disk | **Ubuntu 22.04 LTS**, **30–50 GB** Balanced persistent disk |
| Firewall | Check **Allow HTTP traffic** (we add 8501 next) |

2. **Create**.

3. **VPC network** → **Firewall** → **Create firewall rule**:

| Field | Value |
|-------|--------|
| Name | `allow-streamlit-8501` |
| Targets | All instances in the network (or use network tag `streamlit` on the VM) |
| Source IPv4 | `0.0.0.0/0` (or your home IP for more security) |
| Protocols | tcp **8501** |

4. On the VM row, note the **External IP** (e.g. `34.x.x.x`).

Optional: **VPC network** → **IP addresses** → **Reserve** static external IP and attach it to the VM so the URL does not change after stop/start.

---

## Step 4 — SSH into the VM

Console → VM → **SSH** → **Open in browser terminal**.

Or from your Mac:

```bash
gcloud compute ssh dividendscope --zone=us-central1-a
```

(Install [Google Cloud SDK](https://cloud.google.com/sdk/docs/install) and run `gcloud init` if you use the CLI.)

---

## Step 5 — Install Docker and clone the app

On the VM:

```bash
curl -fsSL https://raw.githubusercontent.com/blidiselalin/dividend-healthcheck/main/deploy/gcp/vm-bootstrap.sh -o vm-bootstrap.sh
chmod +x vm-bootstrap.sh
./vm-bootstrap.sh
```

**Log out and SSH in again** (so `docker` group applies):

```bash
exit
# reconnect via SSH
cd ~/dividend-healthcheck
```

---

## Step 6 — Start the app

```bash
cd ~/dividend-healthcheck
docker compose up -d --build
docker compose ps
```

Streamlit listens on **`127.0.0.1:8501`** only (not public `:8501`). **Caddy** on the VM serves **HTTPS** on 443 and proxies to that port.

Production URL (DuckDNS example):

```text
https://pulse-dividend.duckdns.org
```

Manual run (same flags as `docker compose`; image must be built first):

```bash
./deploy/gcp/docker-run.sh
```

Or:

```bash
docker compose build
docker run -d --name dividendscope --restart unless-stopped \
  -p 127.0.0.1:8501:8501 \
  -e DIVIDENDSCOPE_DATA_DIR=/data \
  -v dividendscope-persistent-data:/data \
  dividend-healthcheck-dividendscope \
  streamlit run app.py --server.port=8501 --server.address=0.0.0.0 \
  --server.enableCORS=false --server.enableXsrfProtection=false
```

Direct IP (debug only, if firewall allows **8501**): `http://EXTERNAL_IP:8501`

### Persistent data (vector DB + SQLite)

Data is stored in Docker volume **`dividendscope-persistent-data`** (mounted at **`/data`** in the container):

| Path | Contents | Who sees it |
|------|----------|-------------|
| `/data/vectordb` | **Shared S&P library** — ChromaDB with historical prices, dividends, fundamentals | **All users** (read-only for the app) |
| `/data/users/<id>/portfolio.db` | That user's holdings, journal, deposits | **That user only** |
| `/data/portfolio.db` | Legacy single-user SQLite (optional; admin restore only) | Owner/admin migration |

Populate the shared library once on the VM (survives rebuilds):

```bash
./scripts/update_cloud_docker.sh --ingest
# or manually:
docker compose exec -T dividendscope python ingest_data.py --ensure-sp500
docker compose exec -T dividendscope python ingest_data.py --enrich-existing
```

Sidebar shows **Shared S&P library: N tickers · S&P X/500** when ingest completed.

### Hourly market refresh (cron)

After the shared library exists, install an hourly job on the VM to refresh live prices and gradually re-enrich stale symbols (avoids hammering yfinance in one shot):

```bash
cd ~/dividend-healthcheck
chmod +x scripts/hourly_market_refresh.sh scripts/install_hourly_cron.sh
./scripts/install_hourly_cron.sh
```

This adds `0 * * * *` (every hour). Logs: `logs/hourly-market.log`.

Manual run:

```bash
./scripts/hourly_market_refresh.sh
# or inside the container:
docker compose exec -T dividendscope python ingest_data.py --hourly-update
```

Each run: **refresh all prices** → add up to **5** missing S&P tickers → **enrich up to 40** documents older than 7 days (or quality &lt; 55%).

Survives **restart**, **`docker compose up --build`**, and **VM reboot**.

**Never run** `docker compose down -v` — `-v` deletes the volume and wipes the DB.

```bash
./scripts/docker_volume_status.sh   # list vectordb size
```

### Migrate your local portfolio to the cloud (one user, multi-user safe)

Holdings live in **SQLite** (`portfolio.db`). With Google sign-in, each **registered** account has:

| Store | Path |
|--------|------|
| Account registry | `/data/users.db` (email → user id) |
| That user's portfolio | `/data/users/<user-id>/portfolio.db` |

Other users on the same VM keep their own folders — migration **never** writes to all `/data/users/*`.

#### Procedure when other users already exist

1. **Register on the cloud** (creates your row in `users.db` and folder `/data/users/<id>/`):
   - Open **https://pulse-dividend.duckdns.org**
   - Sign in with the **same Google account** as on your Mac
   - Sign out is optional; you only need one successful login

2. **Migrate** — from your **Mac** *or* **on the GCP VM** (same script):

**Option A — from the VM** (recommended if you SSH there often):

```bash
# Once from Mac: copy portfolio.db to the VM
scp ~/.dividendscope/data/portfolio.db YOU@VM_IP:~/portfolio.db

# On the VM (SSH / browser terminal):
cd ~/dividend-healthcheck
git pull
chmod +x scripts/migrate_portfolio_to_cloud.sh
./scripts/migrate_portfolio_to_cloud.sh --on-vm --list-users
./scripts/migrate_portfolio_to_cloud.sh --on-vm --local ~/portfolio.db --email you@gmail.com --dry-run
./scripts/migrate_portfolio_to_cloud.sh --on-vm --local ~/portfolio.db --email you@gmail.com --sync-portfolio --yes
```

No `deploy.env` needed with `--on-vm`.

**Option B — from your Mac** (configure `deploy.env` with GCP or `SSH_HOST`):

```bash
cp deploy.env.example deploy.env
chmod +x scripts/migrate_portfolio_to_cloud.sh
./scripts/migrate_portfolio_to_cloud.sh --list-users
./scripts/migrate_portfolio_to_cloud.sh --email you@gmail.com --dry-run
./scripts/migrate_portfolio_to_cloud.sh --email you@gmail.com --sync-portfolio --yes
```

3. **Sign in again** on the cloud app — holdings should match local.

**Admin sidebar** (Users table) shows **User id** for each registered account if you prefer `--user-id` instead of `--email`.

Local DB default: `~/.dividendscope/data/portfolio.db`

#### Safety

- **`--email`** resolves exactly one user from `users.db` (recommended when several people use the app)
- **`--user-id`** from the `REG` line in `--list-users` if you already know the folder name
- **`--legacy-only`** updates only `/data/portfolio.db` (does not touch `/data/users/*`; admin first-login copy only)
- Backs up target as `portfolio.db.bak.<timestamp>` before replace
- Aborts if **that user's** cloud file has more holdings than local (`--force` to override)

Optional in `deploy.env`: `MIGRATE_EMAIL=you@gmail.com`

#### Manual copy on the VM (one path only)

```bash
# Get <user-id> from: docker exec dividendscope sqlite3 /data/users.db \
#   "SELECT id, email FROM users;"
docker cp ~/portfolio.db dividendscope:/data/users/<only-your-user-id>/portfolio.db
docker compose restart dividendscope
```

---

## Step 7 — Build the database (first time, ~15–25 min)

Run inside the container (writes to volume `dividendscope-persistent-data` → `/data`):

```bash
docker exec -it dividendscope python ingest_data.py --enrich
docker exec -it dividendscope python ingest_data.py --sync-portfolio
```

Or from the project directory: `docker compose exec dividendscope python ingest_data.py --enrich`

Restart is optional; refresh the browser. Sidebar should show **Vector DB (N stocks)**.

Check data on disk:

```bash
docker compose exec dividendscope ls -la /data
docker compose exec dividendscope ls -la /data/vectordb
```

---

## Step 8 — Update from your Mac (no VM login)

```bash
cp deploy.env.example deploy.env
# Set SSH_HOST=you@EXTERNAL_IP  or  GCP_INSTANCE + GCP_ZONE + GCP_PROJECT

./scripts/deploy_from_local.sh --sync-portfolio
```

Rsyncs your local repo to the VM, rebuilds Docker, keeps `/data`. Use `./scripts/deploy_from_local.sh --git --sync-portfolio` to pull from GitHub on the VM instead.

---

## Step 9 — Update on the VM (SSH)

On the VM (keeps volume `dividendscope-persistent-data` → `/data`):

```bash
cd ~/dividend-healthcheck
git pull
./scripts/update_cloud_docker.sh --sync-portfolio
```

Or manually:

```bash
cd ~/dividend-healthcheck
git pull
docker compose build --pull
docker compose up -d
docker compose exec -T dividendscope python ingest_data.py --sync-portfolio
```

First time on a VM without the script yet:

```bash
cd ~/dividend-healthcheck
git pull
chmod +x scripts/update_cloud_docker.sh
./scripts/update_cloud_docker.sh --sync-portfolio
```

---

## Step 10 — Useful commands

```bash
# Logs (auth, portfolio hydrate/reload, vector DB init → stdout)
docker compose logs -f dividendscope
# More detail: set DIVIDENDSCOPE_LOG_LEVEL=DEBUG in docker-compose.yml

# Restart after git pull (same as update script)
git pull
docker compose up -d --build

# Stop VM from console to save credits (disk kept)
# Compute Engine → VM → Stop

# Start again → same disk, same data
```

---

## Custom domain — DNS → GCP VM → Streamlit

Use a **hostname** (e.g. `app.yourdomain.com`) instead of `http://34.x.x.x:8501`. Google sign-in needs **HTTPS** in production.

### A. Reserve a static IP (required)

If the VM IP changes, DNS breaks.

1. **VPC network** → **IP addresses** → **Reserve static external**.
2. Name: `motion-app-ip` → region same as VM → **Reserve**.
3. **Compute Engine** → **VM instances** → your VM → **Edit** → **Network interfaces** → set **External IP** to the reserved address.
4. Note the IP (e.g. `34.123.45.67`).

### B. Create DNS records

Pick **one** DNS provider (registrar, Cloudflare, or **Google Cloud DNS**).

#### Option 1 — Registrar or Cloudflare (simplest)

At your domain host (Namecheap, GoDaddy, Cloudflare, etc.):

| Type | Name / Host | Value | TTL |
|------|-------------|--------|-----|
| **A** | `app` (for `app.yourdomain.com`) | `34.123.45.67` (static IP) | 300 |

- Apex `yourdomain.com` → use **A** with name `@` (same IP).
- **www** → **CNAME** to `app.yourdomain.com` if you want both.

Wait 5–30 minutes, then check:

```bash
dig +short app.yourdomain.com
# should print your static IP
```

#### Option 2 — Google Cloud DNS

1. **Network services** → **Cloud DNS** → **Create zone**.
2. Zone type **Public**, DNS name: `yourdomain.com.`
3. **Create record set** → Type **A**, DNS name `app.yourdomain.com.`, IPv4 = static IP.
4. Cloud DNS shows **NS** nameservers (4 lines). At your **domain registrar**, replace nameservers with those NS records (delegation).
5. Propagation can take up to 48 hours (often much faster).

### C. Firewall for HTTPS

**VPC network** → **Firewall** → create (or extend) rules:

| Name | Ports | Source |
|------|-------|--------|
| `allow-http-80` | tcp **80** | `0.0.0.0/0` |
| `allow-https-443` | tcp **443** | `0.0.0.0/0` |

Keep **8501** only if you still want direct IP access; for production, prefer **only 80/443** via Caddy.

### D. HTTPS reverse proxy (Caddy on the VM)

SSH to the VM (Streamlit must already run on `localhost:8501` via Docker):

```bash
cd ~/dividend-healthcheck
export DOMAIN=app.yourdomain.com
chmod +x deploy/gcp/setup-https-caddy.sh
sudo DOMAIN="$DOMAIN" ./deploy/gcp/setup-https-caddy.sh
```

Open **https://app.yourdomain.com** (no `:8501`).

### E. Google OAuth redirect (required for login)

1. [Google Cloud Console](https://console.cloud.google.com/) → **APIs & Services** → **Credentials** → your **OAuth 2.0 Web client**.
2. **Authorized redirect URIs** → add:

   ```text
   https://app.yourdomain.com/oauth2callback
   ```

3. On the VM, edit secrets (not in git):

   ```toml
   [auth]
   redirect_uri = "https://app.yourdomain.com/oauth2callback"
   ```

4. Rebuild/restart so Streamlit picks up secrets:

   ```bash
   docker compose up -d --build
   ```

### F. Quick checklist

| Step | Done when |
|------|-----------|
| Static IP reserved & attached to VM | IP unchanged after VM stop/start |
| DNS A record | `dig +short app.yourdomain.com` = static IP |
| Firewall 80, 443 | `curl -I https://app.yourdomain.com` returns 200/302 |
| Caddy running | `sudo systemctl status caddy` active |
| OAuth redirect | Google login completes without redirect mismatch |

### Alternative — Cloudflare only (no Caddy)

1. Add site in Cloudflare, DNS **A** `app` → VM static IP (orange cloud **Proxied**).
2. **SSL/TLS** → **Full** (or **Full (strict)** if you install a cert on the VM).
3. Still run Caddy on the VM for origin TLS, or use Cloudflare → `http://VM_IP:8501` (not recommended; use Caddy on 443).

---

## HTTPS (reference)

Streamlit in Docker listens on **8501** (HTTP). Caddy terminates TLS on **443** and proxies to `localhost:8501`.

Manual Caddyfile (`/etc/caddy/Caddyfile`):

```text
app.yourdomain.com {
    reverse_proxy localhost:8501
}
```

---

## Cost tips (trial)

| Action | Why |
|--------|-----|
| **Stop** the VM when not using it | You pay mostly for disk while stopped; much less than running 24/7 |
| Use **e2-small**, not larger | Enough for this app |
| Set a **billing budget** | Email before credits run out |
| **Delete** the VM + disk when done | Avoid charges after trial |

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `container name "/dividendscope" is already in use` | `docker rm -f dividendscope` then `docker compose up -d --build` (data volume is kept) |
| Page does not load | Firewall rule tcp **8501**; VM running; `docker compose ps` |
| Out of memory | Use **e2-small** or **e2-medium** |
| Empty vector DB | Run ingest commands in Step 7 |
| Permission denied (docker) | Log out/in after `vm-bootstrap.sh` |
| App slow first load | Normal during ingest; wait for Step 7 to finish |

---

## Alternative: run without Docker

```bash
sudo apt-get update && sudo apt-get install -y python3.12-venv git
git clone https://github.com/blidiselalin/dividend-healthcheck.git
cd dividend-healthcheck
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export DIVIDENDSCOPE_DATA_DIR=$HOME/dividendscope-data
mkdir -p "$DIVIDENDSCOPE_DATA_DIR"
python ingest_data.py --enrich
python ingest_data.py --sync-portfolio
streamlit run app.py --server.port 8501 --server.address 0.0.0.0
```

Data persists under `$HOME/dividendscope-data` on the VM boot disk.
