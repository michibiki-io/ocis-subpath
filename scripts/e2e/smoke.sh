#!/usr/bin/env bash
set -Eeuo pipefail

# Shared HTTP-level smoke checks. Callers are responsible for preparing a reachable BASE_URL.

BASE_URL="${1:-http://127.0.0.1:19200/ocis}"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
source "${ROOT_DIR}/scripts/e2e/common.sh"

SUBPATH="$(subpath_from_url "${BASE_URL}")"
if [[ "${SUBPATH}" == "/" ]]; then
  EXPECTED_BASE_HREF="/"
else
  EXPECTED_BASE_HREF="${SUBPATH}/"
fi

CURL_ARGS=()
if [[ "${BASE_URL}" == https://* ]]; then
  CURL_ARGS+=(-k)
fi
if [ -n "${CURL_RESOLVE:-}" ]; then
  CURL_ARGS+=(--resolve "${CURL_RESOLVE}")
fi

log() {
  echo "[e2e-smoke] $*"
}

fail_with_response() {
  local label="$1"
  local url="$2"

  echo "[e2e-smoke] ${label} failed: ${url}" >&2
  curl "${CURL_ARGS[@]}" -i -fsS "${url}" || true
  exit 1
}

json_assert() {
  local file_path="$1"
  local base_url="$2"
  local mode="$3"

  python3 - "$file_path" "$base_url" "$mode" <<'PY'
import json
import sys

path, base_url, mode = sys.argv[1:4]
with open(path, "r", encoding="utf-8") as fh:
    body = json.load(fh)

if mode == "config":
    assert body["server"] == base_url, body
    assert body["theme"].startswith(f"{base_url}/themes/"), body
    assert body["openIdConnect"]["metadata_url"] == f"{base_url}/.well-known/openid-configuration", body
    assert body["openIdConnect"]["authority"] == base_url, body
    assert body["openIdConnect"]["client_id"], body
    assert isinstance(body["apps"], list) and body["apps"], body
elif mode == "discovery":
    assert body["issuer"] == base_url, body
    assert body["authorization_endpoint"], body
    assert body["token_endpoint"], body
    assert body["jwks_uri"], body
else:
    raise AssertionError(f"unsupported mode: {mode}")
PY
}

origin_url() {
  python3 - "$BASE_URL" "$1" <<'PY'
import sys
from urllib.parse import urlsplit

base_url, path = sys.argv[1:3]
parts = urlsplit(base_url)
print(f"{parts.scheme}://{parts.netloc}{path}")
PY
}

assert_root_path_denied() {
  local path="$1"
  local target
  local status

  target="$(origin_url "${path}")"
  status="$(curl "${CURL_ARGS[@]}" -o /dev/null -sS -w "%{http_code}" "${target}" || true)"
  case "${status}" in
    2*|3*)
      echo "[e2e-smoke] root path must not be served: ${target} returned ${status}" >&2
      exit 1
      ;;
  esac
}

ROOT_URL="${BASE_URL%/}/"
CONFIG_URL="${BASE_URL%/}/config.json"
DISCOVERY_URL="${BASE_URL%/}/.well-known/openid-configuration"
HEALTH_URL="${BASE_URL%/}/healthz"
DEEP_LINK_URL="${BASE_URL%/}/files/spaces/personal"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "${TMP_DIR}"' EXIT

CONFIG_JSON="${TMP_DIR}/config.json"
DISCOVERY_JSON="${TMP_DIR}/discovery.json"
ROOT_HTML="${TMP_DIR}/root.html"
DEEP_LINK_HTML="${TMP_DIR}/deep-link.html"

log "BASE_URL=${BASE_URL}"
log "waiting for subpath config..."
for i in $(seq 1 60); do
  if curl "${CURL_ARGS[@]}" -fsS "${CONFIG_URL}" -o "${CONFIG_JSON}"; then
    break
  fi

  if [ "${i}" -eq 60 ]; then
    fail_with_response "config endpoint" "${CONFIG_URL}"
  fi

  sleep 2
done

log "checking health endpoint..."
curl "${CURL_ARGS[@]}" -fsS "${HEALTH_URL}" >/dev/null || fail_with_response "health endpoint" "${HEALTH_URL}"

log "validating config.json..."
json_assert "${CONFIG_JSON}" "${BASE_URL}" "config"

log "validating OIDC discovery..."
curl "${CURL_ARGS[@]}" -fsS "${DISCOVERY_URL}" -o "${DISCOVERY_JSON}" || fail_with_response "OIDC discovery" "${DISCOVERY_URL}"
json_assert "${DISCOVERY_JSON}" "${BASE_URL}" "discovery"

log "checking Web UI root..."
curl "${CURL_ARGS[@]}" -fsS "${ROOT_URL}" -o "${ROOT_HTML}" || fail_with_response "Web UI root" "${ROOT_URL}"
grep -Eqi "<base[[:space:]][^>]*href=\"${EXPECTED_BASE_HREF}\"" "${ROOT_HTML}" || {
  echo "[e2e-smoke] expected a ${EXPECTED_BASE_HREF} base href in root HTML" >&2
  cat "${ROOT_HTML}" >&2
  exit 1
}
grep -Eqi 'ownCloud|Log in|Login|Username|Password|Files' "${ROOT_HTML}" || {
  echo "[e2e-smoke] root HTML did not look like ownCloud Web" >&2
  cat "${ROOT_HTML}" >&2
  exit 1
}

log "checking deep link..."
curl "${CURL_ARGS[@]}" -fsS "${DEEP_LINK_URL}" -o "${DEEP_LINK_HTML}" || fail_with_response "deep link" "${DEEP_LINK_URL}"
grep -qi '404 page not found' "${DEEP_LINK_HTML}" && {
  echo "[e2e-smoke] deep link returned 404 page" >&2
  cat "${DEEP_LINK_HTML}" >&2
  exit 1
}
grep -Eqi 'ownCloud|Log in|Login|Username|Password|Files' "${DEEP_LINK_HTML}" || {
  echo "[e2e-smoke] deep link HTML did not look like ownCloud Web" >&2
  cat "${DEEP_LINK_HTML}" >&2
  exit 1
}

log "checking root paths are denied..."
for root_path in \
  "/" \
  "/config.json" \
  "/oidc-callback.html" \
  "/oidc-silent-redirect.html" \
  "/manifest.json" \
  "/robots.txt" \
  "/js/" \
  "/themes/owncloud/theme.json" \
  "/graph/v1.0/me" \
  "/api/v0/settings/values" \
  "/dav/spaces" \
  "/data" \
  "/remote.php/dav" \
  "/ocs/v2.php/cloud/capabilities" \
  "/thumbnails" \
  "/.well-known/openid-configuration" \
  "/signin" \
  "/konnect"
do
  assert_root_path_denied "${root_path}"
done

log "smoke test completed"
