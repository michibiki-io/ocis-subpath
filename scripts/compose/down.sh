#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

extra_args=()
if [[ "${1:-}" == "--volumes" ]]; then
  extra_args+=(--volumes)
fi

docker compose -f "${ROOT_DIR}/compose/docker-compose.yml" down "${extra_args[@]}"
