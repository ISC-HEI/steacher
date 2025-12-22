#!/bin/bash
# backup db and app

TS=$(date +%F_%H-%M-%S)

# backup app, saved just on this machine
zip -r        ~/dev/manual_backup_db/app_$TS.zip .

# backup db
docker compose exec -T db pg_dump -U steacher_admin steacher_prod > ~/dev/manual_backup_db/db_$TS.sql
wormhole send ~/dev/manual_backup_db/db_$TS.sql

