# Case API — Operations Runbook

Common failure modes, diagnosis steps, and remediation actions.

---

## Table of Contents

1. [Rate Limit Exceeded (429)](#rate-limit-exceeded-429)
2. [Token Expired / Invalid (401)](#token-expired--invalid-401)
3. [Ingestion Cursor Stuck](#ingestion-cursor-stuck)
4. [Redis Unavailable](#redis-unavailable)
5. [Database Connection Pool Exhausted](#database-connection-pool-exhausted)
6. [Ingestion Duplicate Storm](#ingestion-duplicate-storm)
7. [Slow Metrics Queries](#slow-metrics-queries)
8. [Vault Decryption Failure](#vault-decryption-failure)

---

## Rate Limit Exceeded (429)

**Symptom**: API returns `429 Too Many Requests` with `Retry-After` header.

**Diagnosis**:
```bash
# Check current rate limit config (default: 60 req/60s per IP)
curl -s http://localhost:8000/healthz -v 2>&1 | grep X-RateLimit

# Check Redis for rate-limit keys
redis-cli KEYS "rl:*"
redis-cli ZCARD "rl:<client-ip>"
```

**Remediation**:
- **Temporary**: Increase the rate limit in `app/middleware/rate_limit.py` or via environment variable.
- **Client-side**: Implement exponential backoff; honour `Retry-After` header.
- **Redis down**: Rate limiter falls back to in-memory dict — limits are per-worker, not global. Restart Redis.

**Prevention**: Monitor `http_errors_total{status=429}` in `/obs/metrics`.

---

## Token Expired / Invalid (401)

**Symptom**: API returns `401 Unauthorized` with detail "Token has expired" or "Invalid token".

**Diagnosis**:
```bash
# Decode the JWT (without verification) to inspect claims
python3 -c "
import jwt, sys
token = sys.argv[1]
print(jwt.decode(token, options={'verify_signature': False}))
" "<paste-token-here>"
```

**Common causes**:
| Cause | Detail message | Fix |
|-------|---------------|-----|
| Expired access token | "Token has expired" | Client must call `POST /auth/refresh` with refresh token |
| Expired refresh token | "Invalid refresh token" | User must re-login |
| Wrong secret key | "Invalid token" | Ensure `API_SECRET_KEY` matches across deployments |
| Using refresh token as access | "Invalid token type" | Client bug — send the access token, not refresh |

**Remediation**:
- Token refresh: `POST /auth/refresh {"refresh_token": "..."}` → new access + refresh pair.
- Secret key rotation: Deploy new `API_SECRET_KEY`. All existing tokens become invalid — users must re-login.

---

## Ingestion Cursor Stuck

**Symptom**: Ingestion jobs run but no new `raw_event` rows appear. The `ingestion_events_total` counter stops incrementing while `ingestion_duplicates_total` keeps climbing.

**Diagnosis**:
```bash
# Check latest ingested events
psql -c "SELECT source, MAX(occurred_at), COUNT(*) FROM raw_event GROUP BY source;"

# Check for errors on recent events
psql -c "SELECT id, source, entity_id, error FROM raw_event WHERE error IS NOT NULL ORDER BY received_at DESC LIMIT 10;"

# Check observability metrics
curl -s http://localhost:8000/obs/metrics | python3 -m json.tool
```

**Common causes**:
1. **Source API pagination cursor is invalid** — the external API changed its cursor format or the cursor expired.
2. **Content hash collision** — all incoming payloads are identical (e.g. polling a resource that hasn't changed).
3. **Source token revoked** — the Jira/GitLab token was rotated but our vault still has the old one.

**Remediation**:
1. Reset the cursor: delete the cursor key from Redis (`redis-cli DEL "cursor:<source>"`) and re-trigger ingestion.
2. Verify the source token: `SELECT source, label, created_at FROM source_token WHERE source='jira';` — if stale, rotate via `POST /connectors`.
3. Manual backfill: Use the seed script or direct API calls to re-ingest missing events.

---

## Redis Unavailable

**Symptom**: Cache misses on every request. Logs show `"Redis read failed"` or `"Redis write failed"`. Rate limiter falls back to in-memory mode.

**Diagnosis**:
```bash
redis-cli ping  # Should return PONG
docker compose logs redis
```

**Impact**:
- Metrics caching disabled — every `/metrics` call hits the database.
- Rate limiting is per-worker instead of global.
- Application continues to function (all Redis calls have fallback paths).

**Remediation**:
```bash
# Restart Redis
docker compose restart redis

# If data is corrupted
docker compose down redis && docker compose up -d redis
```

---

## Database Connection Pool Exhausted

**Symptom**: Requests hang or return 500. Logs show `"QueuePool limit reached"`.

**Diagnosis**:
```bash
# Check active connections
psql -c "SELECT count(*) FROM pg_stat_activity WHERE datname='case_db';"

# Check pool config (default: pool_size=5, max_overflow=10)
grep pool_size apps/api/app/db.py
```

**Remediation**:
- **Immediate**: Restart the API service to reset the pool.
- **Tune**: Increase `pool_size` and `max_overflow` in `app/db.py`.
- **Investigate**: Look for long-running queries: `SELECT pid, now() - query_start AS duration, query FROM pg_stat_activity WHERE state = 'active' ORDER BY duration DESC;`

---

## Ingestion Duplicate Storm

**Symptom**: `ingestion_duplicates_total` spikes in `/obs/metrics`. No new data is being created despite successful API calls.

**Diagnosis**:
```bash
# Check duplicate rate
curl -s http://localhost:8000/obs/metrics | python3 -c "
import json, sys
d = json.load(sys.stdin)
dupes = d.get('counters', {}).get('ingestion_duplicates_total', {})
events = d.get('counters', {}).get('ingestion_events_total', {})
print('Duplicates:', dupes)
print('Events:', events)
"
```

**Common causes**:
- Webhook replay from Jira/GitLab (retrying after timeout).
- Polling job re-fetching already-processed pages.
- Source system sending identical payloads for different events (rare).

**Remediation**: This is expected behaviour — the idempotency layer is working correctly. High duplicate rate is informational, not an error. Investigate the source if the rate is unexpectedly high.

---

## Slow Metrics Queries

**Symptom**: `/metrics` endpoint responds slowly (>2s). `http_request_duration_ms` p95 for `/metrics` is high.

**Diagnosis**:
```bash
# Check Redis cache hit rate
curl -s http://localhost:8000/obs/metrics | python3 -c "
import json, sys
d = json.load(sys.stdin)
hist = d.get('histograms', {}).get('http_request_duration_ms', {})
for k, v in hist.items():
    if '/metrics' in k:
        print(f'{k}: p50={v[\"p50\"]}ms p95={v[\"p95\"]}ms count={v[\"count\"]}')"
```

**Remediation**:
- **Check Redis**: If down, queries bypass cache and hit DB directly. Fix Redis first.
- **Invalidate stale cache**: `redis-cli KEYS "case:*" | xargs redis-cli DEL`
- **Add indexes**: If a specific query is slow, check `EXPLAIN ANALYZE` in psql.
- **Reduce TTL**: Default is 300s. Lower it if stale data is acceptable for shorter periods.

---

## Vault Decryption Failure

**Symptom**: `POST /connectors` or ingestion jobs fail with "Decryption failed" or garbled token values.

**Diagnosis**:
```bash
# Check if encryption key matches
echo $VAULT_ENCRYPTION_KEY | wc -c  # Should be 64 hex chars + newline = 65

# Check if previous key is set (for rotation)
echo $VAULT_ENCRYPTION_KEY_PREVIOUS | wc -c
```

**Common causes**:
- `VAULT_ENCRYPTION_KEY` was changed without setting `VAULT_ENCRYPTION_KEY_PREVIOUS`.
- Key is malformed (not 64 hex characters).

**Remediation**:
1. Set `VAULT_ENCRYPTION_KEY_PREVIOUS` to the old key.
2. Re-encrypt all tokens: run a migration script that decrypts with the old key and re-encrypts with the new one.
3. If the old key is lost: all stored tokens are unrecoverable. Users must re-connect their sources via `POST /connectors`.

---

## Quick Reference: Observability Endpoints

| Endpoint | Purpose |
|----------|---------|
| `GET /healthz` | Liveness check (always returns 200 if process is up) |
| `GET /obs/metrics` | JSON counters, histograms, gauges for all app metrics |
| `GET /metrics` | Dashboard business metrics (velocity, burndown, effort) |

## Key Metrics to Monitor

| Metric | Type | Alert threshold |
|--------|------|----------------|
| `http_requests_total` | Counter | N/A (informational) |
| `http_errors_total{status=5xx}` | Counter | > 10/min |
| `http_request_duration_ms` | Histogram | p95 > 2000ms |
| `ingestion_events_total` | Counter | 0 for > 15min (stalled) |
| `ingestion_duplicates_total` | Counter | > 90% of events (cursor stuck) |
| `ingestion_duration_ms` | Histogram | p99 > 5000ms |
