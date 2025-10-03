# New Relic PostgreSQL Monitoring Setup

This guide walks you through setting up New Relic Database Monitoring (DBM) for the Steacher PostgreSQL database.

## Overview

We're configuring the New Relic Infrastructure agent to monitor PostgreSQL with full Database Monitoring capabilities, including:
- Query performance analysis
- Connection pool metrics
- Table and index statistics
- Database locks and bloat metrics

## Prerequisites

- New Relic account with Full Platform User access (included in free tier)
- PostgreSQL running in Docker (via docker-compose)
- Access to .env.production file

## Step 1: Create PostgreSQL Monitoring User

1. **Connect to your PostgreSQL container:**
   ```bash
   docker exec -it steacher_project-db-1 psql -U $POSTGRES_USER -d steacher
   ```

2. **Run the SQL script:**
   ```bash
   docker exec -i steacher_project-db-1 psql -U $POSTGRES_USER -d steacher < setup_newrelic_db_user.sql
   ```
   
   **Before running**, edit `setup_newrelic_db_user.sql` and replace `CHANGE_THIS_PASSWORD` with a strong password.

3. **Verify the user was created:**
   ```bash
   docker exec -it steacher_project-db-1 psql -U $POSTGRES_USER -d steacher -c "\du newrelic"
   ```

## Step 2: Update .env.production

Add the following line to your `.env.production` file:

```bash
NRIA_POSTGRESQL_PASSWORD=your_secure_password_here
```

Replace `your_secure_password_here` with the password you used in Step 1.

## Step 3: Deploy the Changes

The following files have been created/updated:
- ✅ `newrelic-infra/integrations.d/postgresql-config.yml` - Integration config
- ✅ `docker-compose.yml` - Updated newrelic_infra service
- ✅ `setup_newrelic_db_user.sql` - Database user creation script

**Deploy the changes:**

```bash
# Restart the services
docker-compose up -d

# Check that the infra agent is running and connected to backend network
docker-compose ps newrelic_infra

# Verify the agent can reach PostgreSQL
docker exec steacher_project-newrelic_infra-1 nc -zv db 5432
```

## Step 4: Verify Monitoring is Working

1. **Check New Relic Infrastructure agent logs:**
   ```bash
   docker-compose logs newrelic_infra | grep -i postgres
   ```

   You should see messages indicating the PostgreSQL integration is running.

2. **Check New Relic UI** (after ~5 minutes):
   - Go to https://one.newrelic.com/
   - Navigate to Infrastructure > Hosts
   - Select your host (steacher1)
   - Look for PostgreSQL data under "Integrations"

3. **Access Database Monitoring:**
   - Go to https://one.newrelic.com/databases
   - You should see your `steacher` database listed
   - Click into it to see query performance, connections, etc.

## Troubleshooting

### Integration not appearing in New Relic UI

1. **Check agent logs:**
   ```bash
   docker-compose logs newrelic_infra | tail -100
   ```

2. **Verify connectivity:**
   ```bash
   docker exec steacher_project-newrelic_infra-1 nc -zv db 5432
   ```

3. **Test PostgreSQL credentials:**
   ```bash
   docker exec -it steacher_project-db-1 psql -U newrelic -d steacher -c "SELECT 1;"
   ```

### "Permission denied" errors

The `newrelic` user may need additional permissions. Re-run the SQL script or grant specific permissions:

```sql
GRANT pg_monitor TO newrelic;
```

### Agent container can't reach database

Verify the newrelic_infra container is on the backend network:

```bash
docker inspect steacher_project-newrelic_infra-1 | grep -A 10 Networks
```

You should see `backend` listed.

## Configuration Details

### Integration Config (`postgresql-config.yml`)

Key settings:
- **HOSTNAME**: `db` (Docker service name)
- **PORT**: `5432` (default PostgreSQL port)
- **USERNAME**: `newrelic` (monitoring user)
- **PASSWORD**: Pulled from environment variable
- **DATABASE**: `steacher` (your application database)
- **ENABLE_SSL**: `false` (not needed within Docker network)

### Network Architecture

```
┌──────────────────────────────────────────────┐
│  Docker Compose - Backend Network           │
│  (internal: true - no internet access)       │
│                                               │
│  ┌──────────────┐         ┌──────────────┐  │
│  │ newrelic_    │ ───────>│ db           │  │
│  │ infra        │  :5432  │ (postgres)   │  │
│  └──────────────┘         └──────────────┘  │
│                                               │
└──────────────────────────────────────────────┘
        │
        │ sends metrics
        ▼
   New Relic Cloud
```

## Data Volume Estimate

Expected data ingestion for PostgreSQL monitoring:
- **Small DB** (~10-50 queries/minute): ~10-20 MB/month
- **Medium DB** (~100-500 queries/minute): ~50-100 MB/month
- **Large DB** (1000+ queries/minute): ~200-500 MB/month

Your Steacher platform likely falls in the **small to medium** range, well within the 100GB free tier limit.

## Security Notes

- The `newrelic` user has **read-only** access to stats and system tables
- Cannot modify data or schema
- Cannot create/drop databases or tables
- Password stored in .env.production (should be .gitignore'd)
- Backend network is internal-only (no internet access)

## Next Steps

Once PostgreSQL monitoring is working, you can add Redis monitoring following a similar pattern.

For Redis, you would:
1. Create `newrelic-infra/integrations.d/redis-config.yml`
2. Add Redis to the backend network (or it might already be accessible)
3. Update docker-compose.yml if needed

Let me know if you'd like me to set that up as well!

