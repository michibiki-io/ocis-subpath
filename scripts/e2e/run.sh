#!/usr/bin/env bash
set -euo pipefail

# Low-level Playwright test runner that executes inside the container started by shell.sh.

if [[ -f /workspace/dev/.env ]] && [[ -z "${E2E_USERNAME:-}" || -z "${E2E_PASSWORD:-}" ]]; then
  set -a
  # shellcheck disable=SC1091
  source /workspace/dev/.env
  set +a
fi

cd /workspace/tests/e2e
export npm_config_cache="${PWD}/.npm-cache"

if [[ ! -d node_modules ]]; then
  npm install --no-fund --no-audit
fi

npx playwright test
