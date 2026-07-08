## Disaster recovery runbook

### Targets

| Metric | Target | Current setup |
|--------|--------|---------------|
| **RPO** (max data loss) | 24 hours | Daily backup timer (`nexus-backup.timer`) |
| **RTO** (max downtime) | 2 hours | Manual restore from local backups on VM |

Tighten RPO by increasing backup frequency or adding S3 offsite sync (`./scripts/backup.sh --s3-bucket`).

### Backup schedule

- **Timer:** daily (~00:00–00:30 GMT with randomized delay)
- **Retention:** 14 days (`BACKUP_RETENTION_DAYS`)
- **Location:** `~/voice-agents/backups/`

Artifacts per run:

- `nexus-sqlite-<timestamp>.db`
- `nexus-chroma-<timestamp>.tar.gz`
- `nexus-config-<timestamp>.tar.gz`

### Verify backups

```bash
ls -lah ~/voice-agents/backups/
sudo systemctl status nexus-backup.timer
sudo journalctl -u nexus-backup.service -n 20 --no-pager
```

### Non-destructive restore drill

```bash
cd ~/voice-agents
./scripts/restore-drill.sh
```

Restores the latest backup into `/tmp/nexus-restore-drill-*` and validates SQLite integrity. **Does not touch production.**

### Full production restore

**Use only when production data is lost or corrupted.**

1. **Stop Nexus**
   ```bash
   sudo systemctl stop nexus
   ```

2. **Pick a backup timestamp**
   ```bash
   ls ~/voice-agents/backups/
   ```

3. **Restore SQLite**
   ```bash
   cp -f ~/voice-agents/backups/nexus-sqlite-TIMESTAMP.db ~/voice-agents/data/nexus.db
   chmod 600 ~/voice-agents/data/nexus.db
   ```

4. **Restore Chroma**
   ```bash
   rm -rf ~/voice-agents/data/chroma
   tar xzf ~/voice-agents/backups/nexus-chroma-TIMESTAMP.tar.gz -C ~/voice-agents/data
   ```

5. **Restore config** (if secrets were lost)
   ```bash
   tar xzf ~/voice-agents/backups/nexus-config-TIMESTAMP.tar.gz -C ~/voice-agents
   ```

6. **Start and verify**
   ```bash
   sudo systemctl start nexus
   sleep 10
   curl -s http://127.0.0.1:8001/api/v1/health
   curl -sI https://your-domain.com/api/v1/health
   ```

7. **Smoke test:** sign in, send a chat message, confirm KB search works.

### Incident checklist

- [ ] Confirm outage (UptimeRobot alert or user report)
- [ ] Check `journalctl -u nexus` and Caddy logs
- [ ] If data corruption: stop service, restore from latest good backup
- [ ] If VM lost: reprovision VM, restore DNS, deploy app, restore backups
- [ ] Post-incident: document root cause, update runbook

### Offsite backups (recommended)

```bash
BACKUP_DIR=~/voice-agents/backups ./scripts/backup.sh --s3-bucket your-bucket
```

Add to cron or extend `nexus-backup.service` with S3 upload after local backup.
