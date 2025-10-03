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

1. **Set a password for the newrelic user:**

Edit `setup_newrelic_db_user.sql` and replace `CHANGE_THIS_PASSWORD` with a strong password.

2. **Run the SQL script:**

   **Important:** Make sure you did change the password on step 1.

   ```bash
   docker exec -i steacher_app-db-1 psql -U $POSTGRES_USER -d steacher_prod < specs/done/251003_pg_newrelic_monitoring/setup_newrelic_db_user.sql
   ```
   

3. **Verify the user was created:**
   ```bash
   docker exec -it steacher_app-db-1 psql -U $POSTGRES_USER -d steacher_prod -c "\du newrelic"
   ```

## Step 2: Update .env.production

Add the following line to your `.env.production` file:

```bash
NRIA_POSTGRESQL_PASSWORD=your_secure_password_here
```

Replace `your_secure_password_here` with the password you used in Step 1.

## Step 3: Deploy the Changes

**Deploy the changes:**

```bash
# Restart the services
docker compose up -d

# Check that the infra agent is running and connected to backend network
docker compose ps newrelic_infra

# Verify the agent can reach PostgreSQL
docker exec steacher_app-newrelic_infra-1 nc -zv db 5432
# will return
# db (172.xxx.xxx.xxx) open
```

## Step 4: Verify Monitoring is Working

1. **Check New Relic Infrastructure agent logs:**
   ```bash
   docker compose logs newrelic_infra | grep -i postgres
   ```

   You should see messages indicating the PostgreSQL integration is running.

2. **Check New Relic UI** (after ~5 minutes):
   - Go to https://one.newrelic.com/
   - Navigate to Infrastructure > Hosts
   - Select your host (steacher1)
   - Look for PostgreSQL data under "Integrations"

3. **Access Database Monitoring:**
   - Go to https://one.newrelic.com/databases
   - You should see your `steacher_prod` database listed
   - Click into it to see query performance, connections, etc.

## Security Notes

- The `newrelic` user has **read-only** access to stats and system tables
- Cannot modify data or schema
- Cannot create/drop databases or tables
- Password stored in .env.production (should be .gitignore'd)
- Backend network is internal-only (no internet access)

