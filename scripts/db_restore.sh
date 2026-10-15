#!/usr/bin/env bash
# Restore a dump made by scripts/db_backup.sh. This REPLACES the chats, folders and Lab data in the
# local Compose database, so it asks for a typed confirmation. The app is paused meanwhile.
set -euo pipefail
cd "$(dirname "$0")/.."
file="${1:?usage: scripts/db_restore.sh backups/<file>.dump}"
if [ ! -s "$file" ]; then
  echo "no such dump: $file" >&2
  exit 1
fi
echo "This replaces ALL data in the local database with $file."
read -r -p "Type 'restore' to continue: " answer
if [ "$answer" != "restore" ]; then
  echo "Not restored."
  exit 1
fi
running="$(docker compose ps -q --status running app 2>/dev/null || true)"
[ -n "$running" ] && docker compose stop app
docker compose exec -T db sh -c \
  'pg_restore --clean --if-exists --no-owner -U "$POSTGRES_USER" -d "$POSTGRES_DB"' < "$file"
[ -n "$running" ] && docker compose start app
echo "restored $file"
