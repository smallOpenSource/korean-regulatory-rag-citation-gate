# RUN-13 — Idempotency Keys 24h TTL Sweep

**Owner**: Operations (deploy slot to be filled by ops engineer)
**Cross-reference**: ADR-011 §Status — production rollout dependency
**Script**: `scripts/cron/idempotency_keys_ttl_sweep.py`
**Cadence**: hourly (default); TTL = 24 hours (override via `IDEMPOTENCY_TTL_HOURS`)

## Purpose

The Idempotency-Key middleware (ADR-011) persists per-request dedup
rows in the `idempotency_keys` table. Without periodic cleanup the
table grows unbounded; rows older than 24 hours are no longer needed
because the TTL window has elapsed (the contract guarantees only that
identical replays within 24h hit the cache).

The sweep is a single `DELETE FROM idempotency_keys WHERE created_at <
now() - make_interval(hours => $1)` call. It is safe to run repeatedly
and on multiple hosts — `DELETE` is naturally idempotent at the row
level.

## systemd unit (illustrative; operator deploys via configuration management)

```ini
# /etc/systemd/system/idempotency-keys-ttl-sweep.service
[Unit]
Description=WMAH idempotency_keys 24h TTL sweep
Wants=idempotency-keys-ttl-sweep.timer

[Service]
Type=oneshot
User=wmah
EnvironmentFile=/etc/wmah/idempotency-sweep.env
WorkingDirectory=/opt/wmah
ExecStart=/opt/wmah/.venv/bin/python /opt/wmah/scripts/cron/idempotency_keys_ttl_sweep.py
StandardOutput=journal
StandardError=journal
```

```ini
# /etc/systemd/system/idempotency-keys-ttl-sweep.timer
[Unit]
Description=Hourly trigger for idempotency_keys TTL sweep
Requires=idempotency-keys-ttl-sweep.service

[Timer]
OnBootSec=15min
OnUnitActiveSec=1h
AccuracySec=5min
Persistent=true

[Install]
WantedBy=timers.target
```

```bash
# /etc/wmah/idempotency-sweep.env  (mode 0600, owned by root:wmah)
DATABASE_URL=postgresql://...
IDEMPOTENCY_TTL_HOURS=24
```

## Install + enable

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now idempotency-keys-ttl-sweep.timer
sudo systemctl status idempotency-keys-ttl-sweep.timer
```

## Verification

```bash
# Last run output (journald)
journalctl -u idempotency-keys-ttl-sweep.service -n 50 --no-pager

# Confirm timer is armed
systemctl list-timers idempotency-keys-ttl-sweep.timer --all

# Manual one-shot (useful on first install)
sudo systemctl start idempotency-keys-ttl-sweep.service

# Row-count sanity check (after first sweep on a populated table)
psql "$DATABASE_URL" -c "
  SELECT
    count(*) AS total,
    count(*) FILTER (WHERE created_at < now() - interval '24 hours') AS expired
  FROM idempotency_keys;
"
# Expected: expired = 0 immediately after a successful sweep
```

## Monitoring + alert thresholds

| Signal | Threshold | Action |
|---|---|---|
| Journal `deleted=N ttl_hours=24` log line | absent for > 90 min | page on-call: "TTL sweep timer not firing" |
| Journal `DEPRECATION` or `OperationalError` | any | page on-call: "TTL sweep DB connectivity broken" |
| `idempotency_keys` row count | > 50000 | warn: sweep is firing but DELETE is not catching up (audit retry behaviour, raise IDEMPOTENCY_TTL_HOURS, or shorten the sweep cadence) |
| Sweep duration (last journal entry) | > 10s | warn: index missing on `created_at`; rebuild `idempotency_keys_created_at_idx` |

Suggested Prometheus rule (Grafana-friendly):

```yaml
- alert: IdempotencyKeysTtlSweepStale
  expr: time() - node_systemd_timer_last_trigger_seconds{name="idempotency-keys-ttl-sweep.timer"} > 5400
  for: 5m
  labels:
    severity: warning
  annotations:
    summary: "RUN-13 idempotency_keys TTL sweep has not fired in >90 min"
    runbook: https://internal/wmah/runbooks/RUN-13
```

## Failure modes + recovery

- **DATABASE_URL unset**: script logs `aborted` and exits 1; systemd marks
  service `failed`. Recovery: ensure `/etc/wmah/idempotency-sweep.env`
  loads cleanly.
- **Patroni leader churn during DELETE**: script logs `Patroni unreachable`
  and exits 1; next hourly trigger picks up; no data corruption (DELETE
  on missing rows is no-op). No manual intervention needed unless 3
  consecutive failures.
- **Long-running DELETE blocks other writes**: the index on
  `created_at` makes the DELETE plan use an index scan; on a healthy
  table the sweep completes in <500ms. If it exceeds 10s, the table is
  pathologically large — escalate to ops + temporarily raise TTL to
  reduce sweep impact while investigating.

## Rollout sequence (when ops slots this in)

1. Land this runbook + systemd unit/timer files in the configuration-
   management repo.
2. Deploy to staging first; observe the journal for at least 24 hours.
3. Verify per-sweep `deleted=N` counts are non-zero (proves the sweep
   is actually running, not just succeeding on an empty table).
4. Promote to production with the alerts above active.
5. Update ADR-011 §Status to reference this runbook as DEPLOYED with the
   commit hash that flipped the status.
