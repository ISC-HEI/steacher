# Metabase BI Setup for Steacher

This directory contains the configuration for running Metabase as a business intelligence tool for the Steacher platform.

## Overview

- **Access URL**: `https://steacher.org/analytics`
- **Database**: Embedded H2 (for Metabase metadata)
- **Data Source**: PostgreSQL `steacher_prod` database (read-only access)
- **Authentication**: Metabase's built-in user management

## Initial Setup

### 1. Create Read-Only PostgreSQL User

Run this command **once** before starting Metabase:

```bash
# Connect to the PostgreSQL container and run the SQL script
docker compose exec -T db psql -U steacher_admin steacher_prod < bi/create_readonly_user.sql
```

**Important**: Edit `bi/create_readonly_user.sql` and replace `CHANGE_THIS_PASSWORD` with a strong password before running the command.

### 2. Start Metabase

The Metabase service is already configured in the main `docker-compose.yml`. Start it with:

```bash
docker compose up -d metabase
```

Or restart all services:

```bash
docker compose up -d
```

### 3. Initial Metabase Configuration

1. Navigate to `https://steacher.org/analytics`
2. Follow the setup wizard to create your admin account
3. When prompted to add a database, configure:
   - **Database type**: PostgreSQL
   - **Name**: `Steacher Production` (or any name you prefer)
   - **Host**: `db` (Docker internal hostname)
   - **Port**: `5432`
   - **Database name**: `steacher_prod`
   - **Username**: `metabase_readonly`
   - **Password**: (the password you set in step 1)

## Backup and Restore

Metabase stores its dashboards, questions, and configurations in an H2 database. This data is persisted in a Docker volume and should be backed up regularly.

### Backup Metabase

```bash
./bi/backup_metabase.sh
```

This will:
- Stop Metabase temporarily
- Copy the H2 database file to `~/dev/manual_backup_metabase/`
- Restart Metabase
- Provide a command to send the backup via wormhole

### Restore Metabase

```bash
./bi/restore_metabase.sh ~/dev/manual_backup_metabase/metabase_2024-12-11_15-30-00.mv.db
```

⚠️ **Warning**: This will replace your current Metabase configuration!

## Architecture

### Security

- **Read-Only Access**: The `metabase_readonly` PostgreSQL user can only SELECT data, preventing accidental modifications
- **No Host Exposure**: Metabase container doesn't expose ports to the host; only accessible via nginx proxy
- **HTTPS Only**: All traffic goes through nginx with Let's Encrypt SSL
- **Built-in Auth**: Metabase has its own user management system

### Network Setup

- Metabase runs on Docker networks: `backend` (to access PostgreSQL) and `frontend` (to be proxied by nginx)
- Accessible only at `https://steacher.org/analytics` via nginx reverse proxy
- The `db` service is on an internal network with no outbound access

### Data Persistence

- Metabase metadata (dashboards, questions, users): Docker volume `metabase_data`
- Source data: Read-only access to `steacher_prod` PostgreSQL database

## Maintenance

### View Logs

```bash
docker compose logs -f metabase
```

### Restart Metabase

```bash
docker compose restart metabase
```

### Update Metabase

```bash
docker compose pull metabase
docker compose up -d metabase
```

### Access Container Shell (for debugging)

```bash
docker compose exec metabase bash
```

## Troubleshooting

### Metabase won't start

Check logs for errors:
```bash
docker compose logs metabase
```

### Can't connect to database

1. Verify the read-only user exists:
   ```bash
   docker compose exec db psql -U steacher_admin steacher_prod -c "\du metabase_readonly"
   ```

2. Test connection from Metabase container:
   ```bash
   docker compose exec metabase curl -v telnet://db:5432
   ```

### 502 Bad Gateway at /analytics

1. Check if Metabase is running:
   ```bash
   docker compose ps metabase
   ```

2. Verify nginx can reach Metabase:
   ```bash
   docker compose exec proxy curl -v http://metabase:3000/
   ```

3. Reload nginx configuration:
   ```bash
   docker compose exec proxy nginx -s reload
   ```

### Forgot Metabase admin password

You can reset it by accessing the H2 database directly, but it's easier to restore from a backup or start fresh by removing the volume:

```bash
docker compose down metabase
docker volume rm steacher_project_metabase_data
docker compose up -d metabase
```

⚠️ **Warning**: This will delete all dashboards and configurations!

## Files in this Directory

- `create_readonly_user.sql`: SQL script to create the read-only PostgreSQL user
- `backup_metabase.sh`: Script to backup Metabase H2 database
- `restore_metabase.sh`: Script to restore Metabase from backup
- `README.md`: This file

## Related Configuration Files

- `/docker-compose.yml`: Metabase service definition
- `/nginx/nginx.conf`: Nginx reverse proxy configuration for `/analytics` location
