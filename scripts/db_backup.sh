#!/usr/bin/env bash
# Back up the Compose database to backups/<UTC time>.dump (pg_dump custom format, run inside `db`).
# Backups contain your ideas; they stay in backups/, which git ignores.
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p backups
out="backups/$(date -u +%Y%m%dT%H%M%SZ).dump"
# Written under a temporary name, renamed only when pg_dump succeeds: no partial dump looks valid.
tmp="$out.partial"
trap 'rm -f "$tmp"' EXIT
if ! docker compose exec -T db sh -c 'pg_dump -Fc -U "$POSTGRES_USER" -d "$POSTGRES_DB"' > "$tmp"; then
  echo "backup failed: pg_dump did not finish; nothing was written" >&2
  exit 1
fi
if [ ! -s "$tmp" ]; then
  echo "backup failed: the dump is empty" >&2
  exit 1
fi
mv "$tmp" "$out"
echo "wrote $out ($(wc -c < "$out" | tr -d ' ') bytes)"
