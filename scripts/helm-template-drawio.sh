#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CHART_DIR="${ROOT_DIR}/charts/ocis-subpath"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "${TMP_DIR}"' EXIT

assert_contains() {
  local file="$1"
  local expected="$2"
  if ! grep -Fq -- "${expected}" "${file}"; then
    echo "expected ${file} to contain: ${expected}" >&2
    exit 1
  fi
}

assert_not_contains() {
  local file="$1"
  local unexpected="$2"
  if grep -Fq -- "${unexpected}" "${file}"; then
    echo "expected ${file} not to contain: ${unexpected}" >&2
    exit 1
  fi
}

helm template ocis "${CHART_DIR}" > "${TMP_DIR}/disabled.out"
assert_not_contains "${TMP_DIR}/disabled.out" "WEB_DRAWIO_CONFIG_JSON"
assert_not_contains "${TMP_DIR}/disabled.out" "drawio/drawio.js"
assert_not_contains "${TMP_DIR}/disabled.out" "https://embed.diagrams.net"

cat > "${TMP_DIR}/public.yaml" <<'YAML'
drawio:
  enabled: true
  editorUrl: "https://embed.diagrams.net/"
YAML
helm template ocis "${CHART_DIR}" -f "${TMP_DIR}/public.yaml" > "${TMP_DIR}/public.out"
assert_contains "${TMP_DIR}/public.out" "WEB_DRAWIO_CONFIG_JSON"
assert_contains "${TMP_DIR}/public.out" "drawio/drawio.js"
assert_contains "${TMP_DIR}/public.out" "https://embed.diagrams.net"
assert_contains "${TMP_DIR}/public.out" "drawio.svg"

cat > "${TMP_DIR}/self-hosted.yaml" <<'YAML'
drawio:
  enabled: true
  editorUrl: "https://drawio.example.com/"
YAML
helm template ocis "${CHART_DIR}" -f "${TMP_DIR}/self-hosted.yaml" > "${TMP_DIR}/self-hosted.out"
assert_contains "${TMP_DIR}/self-hosted.out" "WEB_DRAWIO_CONFIG_JSON"
assert_contains "${TMP_DIR}/self-hosted.out" "https://drawio.example.com"
assert_not_contains "${TMP_DIR}/self-hosted.out" "https://embed.diagrams.net"

echo "drawio helm template checks passed"
