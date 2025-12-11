#!/bin/bash
# Restore Metabase H2 database from backup

set -e

if [ -z "$1" ]; then
    echo "Usage: $0 <backup_file.mv.db>"
    echo ""
    echo "Example:"
    echo "  $0 ~/dev/manual_backup_metabase/metabase_2024-12-11_15-30-00.mv.db"
    exit 1
fi

BACKUP_FILE="$1"

if [ ! -f "$BACKUP_FILE" ]; then
    echo "Error: Backup file not found: $BACKUP_FILE"
    exit 1
fi

echo "WARNING: This will replace the current Metabase database!"
echo "Backup file: $BACKUP_FILE"
read -p "Continue? (yes/no): " CONFIRM

if [ "$CONFIRM" != "yes" ]; then
    echo "Restore cancelled."
    exit 0
fi

# Stop Metabase
echo "Stopping Metabase container..."
docker compose stop metabase

# Copy backup into container
echo "Restoring database..."
docker compose cp "$BACKUP_FILE" metabase:/metabase-data/metabase.db.mv.db

# Restart Metabase
echo "Starting Metabase container..."
docker compose start metabase

echo "Restore complete. Metabase should be available at https://steacher.org/analytics in a moment."
