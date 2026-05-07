#!/usr/bin/env bash
set -euo pipefail

# Low-level Playwright container launcher.
# High-level environment setup belongs in helm-kind.sh or another caller.

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
source "${ROOT_DIR}/scripts/e2e/common.sh"

subpath="$(e2e_subpath)"
base_url="$(e2e_base_url "${subpath}")"

env_file_args=()
if [[ -f "${ROOT_DIR}/dev/.env" ]]; then
  env_file_args+=(--env-file "${ROOT_DIR}/dev/.env")
fi

e2e_env_args=()
if [[ -n "${E2E_USERNAME:-}" ]]; then
  e2e_env_args+=(-e "E2E_USERNAME=${E2E_USERNAME}")
fi
if [[ -n "${E2E_PASSWORD:-}" ]]; then
  e2e_env_args+=(-e "E2E_PASSWORD=${E2E_PASSWORD}")
fi
if [[ -n "${E2E_SCENARIO_PASSWORD:-}" ]]; then
  e2e_env_args+=(-e "E2E_SCENARIO_PASSWORD=${E2E_SCENARIO_PASSWORD}")
fi

extra_host_args=()
if [[ -n "${E2E_EXTRA_HOSTS:-}" ]]; then
  while IFS= read -r host_mapping; do
    [[ -z "${host_mapping}" ]] && continue
    extra_host_args+=(--add-host "${host_mapping}")
  done < <(printf '%s\n' "${E2E_EXTRA_HOSTS}" | tr ',' '\n')
fi

container_cmd=(bash)
if [[ "$#" -gt 0 ]]; then
  container_cmd+=( "$@" )
fi

docker run --rm \
  "${env_file_args[@]}" \
  "${e2e_env_args[@]}" \
  "${extra_host_args[@]}" \
  -e LOCAL_UID="$(id -u)" \
  -e LOCAL_GID="$(id -g)" \
  --network host \
  -e "E2E_SUBPATH=${subpath}" \
  -e "E2E_BASE_URL=${base_url}" \
  -v "${ROOT_DIR}:/workspace" \
  -w /workspace \
  michibiki/playwright:v1.59.1-noble-jpn.2 \
  "${container_cmd[@]}"
