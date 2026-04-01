#!/usr/bin/env bash
set -euo pipefail

PIDS=()
cleanup() {
  for pid in "${PIDS[@]}"; do
    kill "$pid" 2>/dev/null || true
  done
}
trap cleanup EXIT

if [ -f .venv/bin/activate ]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
else
  echo "Warning: .venv/bin/activate not found; continuing without venv."
fi

uvicorn src.api.app:create_app --factory --reload --port 8420 &
PIDS+=("$!")

if [ -f frontend/package.json ]; then
  (cd frontend && npm run dev) &
  PIDS+=("$!")
fi

wait
