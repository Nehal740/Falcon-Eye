#!/usr/bin/env bash
# Daily PostgreSQL backup. Run from the project folder. Keeps the last 14 backups.
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p backups
file="backups/falconeye_$(date +%Y%m%d_%H%M%S).sql.gz"
docker compose -f docker-compose.prod.yml exec -T db \
  sh -c 'pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB"' | gzip > "$file"
ls -1t backups/falconeye_*.sql.gz | tail -n +15 | xargs -r rm --
echo "Backup written: $file"
