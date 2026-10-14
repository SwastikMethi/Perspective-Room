#!/usr/bin/env bash
# Regenerate code from the one public contract: handoff/contracts/openapi.yaml.
# Backend Pydantic models -> backend/app/domain/api.py  (override with API_OUT=path)
# Frontend TS types       -> frontend/src/api/schema.d.ts (when frontend deps are installed;
#                            skipped with API_ONLY=1)
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
spec="$root/handoff/contracts/openapi.yaml"
out="${API_OUT:-app/domain/api.py}"

cd "$root/backend"
uv run datamodel-codegen \
  --input "$spec" --input-file-type openapi \
  --output "$out" \
  --output-model-type pydantic_v2.BaseModel \
  --use-annotated --field-constraints --use-union-operator --use-standard-collections \
  --strict-nullable --enum-field-as-literal all --extra-fields forbid --collapse-root-models \
  --output-datetime-class AwareDatetime \
  --type-mappings "string+uri=string" \
  --target-python-version 3.12 --disable-timestamp --formatters builtin \
  --custom-file-header "# GENERATED from handoff/contracts/openapi.yaml by scripts/gen_contracts.sh - do not edit."
uv run ruff format -q --config pyproject.toml "$out"

if [ -z "${API_ONLY:-}" ] && [ -d "$root/frontend/node_modules" ]; then
  (cd "$root/frontend" && npx openapi-typescript "$spec" -o src/api/schema.d.ts)
fi
