#!/usr/bin/env bash
# Back up the Compose database to backups/<UTC time>.dump (pg_dump custom format, run inside `db`).
# Backups contain your ideas; they stay in backups/, which git ignores.
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p backups
out="backups/$(date -u +%Y%m%dT%H%M%SZ).dump"
docker compose exec -T db sh -c 'pg_dump -Fc -U "$POSTGRES_USER" -d "$POSTGRES_DB"' > "$out"
if [ ! -s "$out" ]; then
  rm -f "$out"
  echo "backup failed: the dump is empty" >&2
  exit 1
fi
echo "wrote $out ($(wc -c < "$out" | tr -d ' ') bytes)"
