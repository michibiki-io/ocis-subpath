#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
source "${ROOT_DIR}/scripts/e2e/common.sh"

SUBPATH="$(normalize_subpath "${COMPOSE_SUBPATH:-/ocis}")"
ORIGIN="${COMPOSE_BASE_ORIGIN:-https://ocis.local:9200}"
if [[ -n "${COMPOSE_PUBLIC_URL:-}" ]]; then
  PUBLIC_URL="${COMPOSE_PUBLIC_URL%/}"
elif [[ "${SUBPATH}" == "/" ]]; then
  PUBLIC_URL="${ORIGIN%/}"
else
  PUBLIC_URL="${ORIGIN%/}${SUBPATH}"
fi

CONFIG_URL="${PUBLIC_URL%/}/config.json"
DISCOVERY_URL="${PUBLIC_URL%/}/.well-known/openid-configuration"
TRAEFIK_DYNAMIC_CONFIG="${TRAEFIK_DYNAMIC_CONFIG:-${ROOT_DIR}/compose/.generated/traefik-dynamic.yml}"

export OCIS_SUBPATH="${SUBPATH}"
export OCIS_PUBLIC_URL="${PUBLIC_URL}"
export OCIS_OIDC_AUTHORITY="${OCIS_OIDC_AUTHORITY:-${PUBLIC_URL}}"
export OCIS_OIDC_METADATA_URL="${OCIS_OIDC_METADATA_URL:-${DISCOVERY_URL}}"
export TRAEFIK_DYNAMIC_CONFIG

render_traefik_dynamic_config "${SUBPATH}" "${TRAEFIK_DYNAMIC_CONFIG}" "${ROOT_DIR}/compose/traefik-dynamic.yml.template"

docker compose -f "${ROOT_DIR}/compose/docker-compose.yml" up --build --force-recreate -d

curl_args=(-kfsS)
if [[ "${PUBLIC_URL}" == https://ocis.local:* ]]; then
  curl_args+=(--resolve "ocis.local:9200:127.0.0.1")
fi

for _ in $(seq 1 60); do
  if curl "${curl_args[@]}" "${CONFIG_URL}" | tr -d '[:space:]' | grep -q "\"server\":\"${PUBLIC_URL}\"" \
    && curl "${curl_args[@]}" "${DISCOVERY_URL}" | tr -d '[:space:]' | grep -q "\"issuer\":\"${PUBLIC_URL}\""; then
    echo "oCIS compose stack is ready: ${PUBLIC_URL}"
    echo "Config: ${CONFIG_URL}"
    echo "OIDC: ${DISCOVERY_URL}"
    exit 0
  fi
  sleep 2
done

echo "Timed out waiting for compose oCIS at ${PUBLIC_URL}" >&2
exit 1
