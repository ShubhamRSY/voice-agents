# Production VM recovery (Oracle + Docker)

Use this when **yournexus.duckdns.org** times out, shows `ERR_TIMED_OUT`, or the console says *Cannot reach server*.

**Server path:** `/opt/nexus/project`  
**SSH user:** `opc`  
**SSH key (local Mac):** `/Users/disastershubz/Downloads/ssh-key-2026-07-08.key`  
**Public IP:** `141.148.93.29` (update DuckDNS if it changes after reboot)

---

## Quick recovery (on the VM)

```bash
cd /opt/nexus/project
bash scripts/recover-production.sh
```

This script:

1. Creates/enables **2GB swap** if none exists (reduces OOM freezes on 1GB VMs)
2. Stops and **disables system Caddy** (avoids port 80 conflict with Docker Caddy)
3. Sets `GUNICORN_WORKERS=1` for 1GB RAM
4. `git pull` + recreate stack (**skips GHCR image pull by default** — `docker pull` OOMs 1GB VMs)
5. Recreates Docker Caddy if ports 80/443 were not mapped
6. Verifies health inside Nexus and through port 80

To pull a new image (needs free RAM / larger shape):

```bash
SKIP_PULL=0 bash scripts/recover-production.sh
```

Docker Compose sets **memory limits** per container (Nexus 512m, Postgres 256m, Redis 128m, Caddy 64m). `src`/`static`/`config` are bind-mounted so `git pull` + recreate applies code without rebuilding.

After recovery, from your Mac:

```bash
BASE_URL=https://yournexus.duckdns.org bash scripts/pre-launch-check.sh
```

### If SSH times out after a failed CI deploy

`docker compose pull` on a 1GB VM often freezes the host. From **Oracle Cloud Console → Reboot instance**, then SSH and run recovery with `SKIP_PULL=1` (default).

---

## Manual steps (one-time SSH from your Mac)

### 1. SSH in

```bash
chmod 600 /Users/disastershubz/Downloads/ssh-key-2026-07-08.key
ssh -i /Users/disastershubz/Downloads/ssh-key-2026-07-08.key opc@141.148.93.29
```

### 2. Recover stack

```bash
cd /opt/nexus/project
bash scripts/recover-production.sh
```

### 3. Browser test

- https://yournexus.duckdns.org/landing  
- https://yournexus.duckdns.org/api/v1/health  

Hard refresh: **Cmd+Shift+R**

---

## Common failures

### Port 80 already in use (`address already in use`)

**Cause:** Systemd **Caddy** and **Docker Caddy** both try to bind port 80.

```bash
sudo systemctl stop caddy
sudo systemctl disable caddy
docker compose -f deploy/docker/docker-compose.yml rm -sf caddy
docker compose -f deploy/docker/docker-compose.yml up -d caddy
docker port docker-caddy-1   # must show 80 and 443
```

### `docker port docker-caddy-1` is empty

Caddy container started while port 80 was busy — recreate it (commands above).

### VM frozen / site timeout

1. Oracle Console → **Stop** instance → **Start**
2. Update DuckDNS if public IP changed
3. Run `bash scripts/recover-production.sh`

### 1GB RAM OOM

In `config/environment/.env` on the VM:

```bash
GUNICORN_WORKERS=1
```

Optional swap (once per VM):

```bash
sudo fallocate -l 2G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```

**Long-term:** migrate to **VM.Standard.A1.Flex** with **2 OCPU + 12 GB** (Always Free).

---

## Verify

| Check | Command |
|-------|---------|
| Nexus (inside container) | `docker exec docker-nexus-1 python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health').read().decode())"` |
| Caddy edge | `curl -s http://127.0.0.1/api/v1/health` |
| All containers | `docker compose -f deploy/docker/docker-compose.yml ps` |

---

## Do not run on the VM

- `docker compose build` (1GB RAM — use `docker compose pull nexus` only)
- Plain `ssh opc@IP` without `-i` key path (Permission denied)
