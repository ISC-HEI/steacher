#!/bin/bash
# Backup Metabase H2 database
# Similar to the PostgreSQL backup pattern in DEPLOY.md

set -e

# Create backup directory if it doesn't exist
BACKUP_DIR=~/dev/manual_backup_metabase
mkdir -p "$BACKUP_DIR"

# Generate timestamp
TS=$(date +%F_%H-%M-%S)

# Stop Metabase to ensure clean backup (H2 requires this)
echo "Stopping Metabase container..."
docker compose stop metabase

# Copy H2 database files (H2 creates multiple files: .mv.db, .trace.db, etc.)
echo "Backing up Metabase H2 database..."
docker compose cp metabase:/metabase-data/metabase.db.mv.db "$BACKUP_DIR/metabase_$TS.mv.db"

# Also backup the trace file if it exists
if docker compose exec metabase test -f /metabase-data/metabase.db.trace.db 2>/dev/null; then
    docker compose cp metabase:/metabase-data/metabase.db.trace.db "$BACKUP_DIR/metabase_$TS.trace.db"
fi

# Restart Metabase
echo "Restarting Metabase container..."
docker compose start metabase

echo "Backup complete: $BACKUP_DIR/metabase_$TS.mv.db"
echo ""
echo "To send via wormhole, run:"
echo "wormhole send $BACKUP_DIR/metabase_$TS.mv.db"
