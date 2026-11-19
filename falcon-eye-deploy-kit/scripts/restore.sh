#!/usr/bin/env bash
# Restore a backup:  bash scripts/restore.sh backups/falconeye_YYYYMMDD_HHMMSS.sql.gz
# WARNING: this replaces the current database contents.
set -euo pipefail
cd "$(dirname "$0")/.."
[ -f "${1:-}" ] || { echo "Usage: $0 <backup.sql.gz>"; exit 1; }
read -r -p "This overwrites the live database. Type YES to continue: " answer
[ "$answer" = "YES" ] || exit 1
docker compose -f docker-compose.prod.yml exec -T db \
  sh -c 'psql -U "$POSTGRES_USER" -d postgres -c "DROP DATABASE IF EXISTS \"$POSTGRES_DB\"" -c "CREATE DATABASE \"$POSTGRES_DB\""'
gunzip -c "$1" | docker compose -f docker-compose.prod.yml exec -T db \
  sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"'
echo "Restored from $1"
