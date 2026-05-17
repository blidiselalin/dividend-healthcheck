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

Open in your browser:

```text
http://EXTERNAL_IP:8501
```

Replace `EXTERNAL_IP` with the VM’s external IP.

### Persistent data (vector DB + SQLite)

Data is stored in Docker volume **`dividendscope-persistent-data`** (mounted at **`/data`** in the container):

| Path | Contents |
|------|----------|
| `/data/vectordb` | ChromaDB |
| `/data/portfolio.db` | SQLite portfolio data |

Survives **restart**, **`docker compose up --build`**, and **VM reboot**.

**Never run** `docker compose down -v` — `-v` deletes the volume and wipes the DB.

```bash
./scripts/docker_volume_status.sh   # list vectordb size
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

## Step 8 — Update after a new release (rebuild Docker image)

On the VM (keeps volume `motion_dividendscope-persistent-data` / `/data`):

```bash
cd ~/motion_dividend-healthcheck
```

Use `~/dividend-healthcheck` if that is your clone path.

```bash
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

## Step 9 — Useful commands

```bash
# Logs
docker compose logs -f

# Restart after git pull (same as update script)
git pull
docker compose up -d --build

# Stop VM from console to save credits (disk kept)
# Compute Engine → VM → Stop

# Start again → same disk, same data
```

---

## HTTPS (optional)

Streamlit on port 8501 is **HTTP only**. For HTTPS:

1. Point a domain A-record to the VM external IP.
2. Install Caddy on the VM and reverse-proxy to `localhost:8501`, or put **Cloudflare** in front.

Simple Caddy example (`/etc/caddy/Caddyfile`):

```text
yourdomain.com {
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
