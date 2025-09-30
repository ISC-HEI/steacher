# New Relic Monitoring for Redis and PostgreSQL

## Overview

This specification describes how to add comprehensive New Relic monitoring for Redis and PostgreSQL to the Steacher project. The current setup already has New Relic Python APM and Infrastructure agent running.

## Current State

- ✅ New Relic Python APM monitors Django application (via `newrelic.ini`)
- ✅ New Relic Infrastructure agent runs as separate container with host monitoring
- ✅ PostgreSQL queries already partially monitored through Python APM
- ⏳ Redis will be monitored through Python APM once Django Channels is implemented
- ❌ No dedicated infrastructure-level monitoring for PostgreSQL/Redis

## Implementation Plan

### 1. Create Integration Configuration Directory

Create the following directory structure:
```
newrelic-infra/
└── integrations.d/
    ├── postgresql-config.yml
    └── redis-config.yml
```

### 2. PostgreSQL Integration Configuration

Create `newrelic-infra/integrations.d/postgresql-config.yml`:

```yaml
integrations:
  - name: nri-postgresql
    env:
      USERNAME: steacher_admin
      PASSWORD: ${POSTGRES_PASSWORD}
      HOSTNAME: db
      PORT: 5432
      DATABASE: steacher_prod
      COLLECTION_LIST: '["postgres", "steacher_prod"]'
      COLLECT_DB_LOCK_METRICS: true
      COLLECT_BLOAT_METRICS: true
      TIMEOUT: 10
    interval: 15s
    labels:
      env: production
      role: database
```

### 3. Redis Integration Configuration

Create `newrelic-infra/integrations.d/redis-config.yml`:

```yaml
integrations:
  - name: nri-redis
    env:
      HOSTNAME: redis
      PORT: 6379
      KEYS_LIMIT: 30
      TIMEOUT: 10
    interval: 15s
    labels:
      env: production
      role: cache
```

### 4. Update Docker Compose

Modify the `newrelic_infra` service in `docker-compose.yml` to mount the integration configs:

```yaml
newrelic_infra:
  image: newrelic/infrastructure:latest
  # ... existing configuration ...
  volumes:
    # ... existing volumes ...
    - ./newrelic-infra/integrations.d:/etc/newrelic-infra/integrations.d:ro
```

### 5. Environment Variables

Ensure these are set in `.env.production`:
- `NEW_RELIC_LICENSE_KEY` (already configured)
- `POSTGRES_PASSWORD` (already configured, used by PostgreSQL integration)

### 6. Update DEPLOY.md

Add this section to `DEPLOY.md` after the Redis section:

```markdown
# Database Monitoring with New Relic

New Relic monitors PostgreSQL and Redis through infrastructure integrations in addition to APM-level monitoring.

## What's Monitored

### PostgreSQL
- Connection statistics and pool metrics
- Query performance and execution plans (via APM)
- Table and index bloat metrics
- Lock metrics and deadlock detection
- Database size and transaction rates

### Redis
- Memory usage and key statistics
- Hit/miss ratios and eviction rates
- Connection counts and command statistics
- Persistence and replication metrics

## Verification

Check that integrations are working:

```bash
# Check integration logs
docker compose logs newrelic_infra | grep -i "postgresql\|redis"

# View integration status
docker compose exec newrelic_infra cat /var/log/newrelic-infra/newrelic-infra.log | grep integration

# Test connectivity from New Relic container
docker compose exec newrelic_infra nc -zv db 5432
docker compose exec newrelic_infra nc -zv redis 6379
```

## New Relic Dashboard

After deployment, check the New Relic UI:
1. Go to Infrastructure > Hosts
2. Click on your host (steacher1)
3. Navigate to Integrations tab
4. Verify PostgreSQL and Redis integrations show green status
5. Check Infrastructure > Third-party services for database metrics

## Troubleshooting

### PostgreSQL Integration Issues
- Verify `POSTGRES_PASSWORD` environment variable is set
- Check PostgreSQL user permissions: `GRANT SELECT ON pg_stat_database TO steacher_admin;`
- Ensure PostgreSQL accepts connections from `newrelic_infra` container

### Redis Integration Issues
- Verify Redis is accessible on port 6379
- Check Redis configuration allows connections from Docker network
- Ensure no Redis authentication is blocking access

### General Integration Issues
- Check container logs: `docker compose logs newrelic_infra`
- Verify integration config files are mounted correctly
- Test network connectivity between containers
```

### 7. Deployment Steps

1. Create the integration config files
2. Update `docker-compose.yml` with the volume mount
3. Restart the New Relic Infrastructure container:
   ```bash
   docker compose up -d --no-deps newrelic_infra
   ```
4. Verify integrations are loaded:
   ```bash
   docker compose logs newrelic_infra | grep -i "postgresql\|redis"
   ```

## Expected Metrics

### PostgreSQL Metrics
- `postgresql.connections.used`
- `postgresql.database.size`
- `postgresql.table.size`
- `postgresql.index.size`
- `postgresql.bgwriter.checkpoints`
- `postgresql.locks.total`

### Redis Metrics
- `redis.keyspace.keys`
- `redis.keyspace.expires`
- `redis.memory.used`
- `redis.stats.hits`
- `redis.stats.misses`
- `redis.clients.connected`

## Cost Considerations

- **Free Tier**: 100 GB/month data ingestion
- **Estimated Usage**: ~5-10 GB/month for both integrations (educational platform)
- **Cost if Exceeded**: $0.35/GB beyond free tier
- **Recommendation**: Monitor data usage in New Relic UI

## Benefits

1. **Proactive Monitoring**: Detect performance issues before they impact users
2. **Capacity Planning**: Understand growth patterns and resource usage
3. **Troubleshooting**: Correlate application performance with database metrics
4. **Alerting**: Set up alerts for critical thresholds (high connections, low memory, etc.)
5. **Historical Analysis**: Track performance trends over time

## Implementation Priority

- **Low Priority**: Current APM monitoring covers basic database performance
- **Implement When**: Database performance becomes a concern or capacity planning is needed
- **Estimated Time**: 1-2 hours including testing and verification