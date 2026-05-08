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

cat > "${TMP_DIR}/group.yaml" <<'YAML'
ocis:
  roleAssignment:
    enabled: true
    driver: oidc
    mode: group
    groupClaim: groups
    groupMapping:
      admin:
        - Domain Admins
      user:
        - Employees
YAML

helm template ocis "${CHART_DIR}" -f "${TMP_DIR}/group.yaml" > "${TMP_DIR}/group.out"
assert_contains "${TMP_DIR}/group.out" "driver: oidc"
assert_contains "${TMP_DIR}/group.out" 'role_claim: "groups"'
assert_contains "${TMP_DIR}/group.out" "role_name: admin"
assert_contains "${TMP_DIR}/group.out" 'claim_value: "Domain Admins"'
assert_contains "${TMP_DIR}/group.out" "role_name: user"
assert_contains "${TMP_DIR}/group.out" 'claim_value: "Employees"'
assert_contains "${TMP_DIR}/group.out" "PROXY_ROLE_ASSIGNMENT_DRIVER"
assert_contains "${TMP_DIR}/group.out" "/etc/ocis/proxy.yaml"

cat > "${TMP_DIR}/user.yaml" <<'YAML'
ocis:
  roleAssignment:
    enabled: true
    driver: oidc
    mode: user
    userClaim: preferred_username
    userMapping:
      admin:
        - alice
      user:
        - bob
YAML

helm template ocis "${CHART_DIR}" -f "${TMP_DIR}/user.yaml" > "${TMP_DIR}/user.out"
assert_contains "${TMP_DIR}/user.out" "driver: oidc"
assert_contains "${TMP_DIR}/user.out" 'role_claim: "preferred_username"'
assert_contains "${TMP_DIR}/user.out" "role_name: admin"
assert_contains "${TMP_DIR}/user.out" 'claim_value: "alice"'
assert_contains "${TMP_DIR}/user.out" "role_name: user"
assert_contains "${TMP_DIR}/user.out" 'claim_value: "bob"'
assert_contains "${TMP_DIR}/user.out" "PROXY_ROLE_ASSIGNMENT_DRIVER"
assert_contains "${TMP_DIR}/user.out" "/etc/ocis/proxy.yaml"

cat > "${TMP_DIR}/disabled.yaml" <<'YAML'
ocis:
  roleAssignment:
    enabled: false
YAML

helm template ocis "${CHART_DIR}" -f "${TMP_DIR}/disabled.yaml" > "${TMP_DIR}/disabled.out"
assert_not_contains "${TMP_DIR}/disabled.out" "ocis-ocis-subpath-proxy"
assert_not_contains "${TMP_DIR}/disabled.out" "proxy-config"
assert_not_contains "${TMP_DIR}/disabled.out" "PROXY_ROLE_ASSIGNMENT_DRIVER"
assert_not_contains "${TMP_DIR}/disabled.out" "/etc/ocis/proxy.yaml"

echo "role assignment helm template checks passed"
