#!/usr/bin/env bash
set -Eeuo pipefail

# Canonical E2E wrapper: provision kind + Traefik + chart, then run smoke and Playwright.

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
source "${ROOT_DIR}/scripts/e2e/common.sh"

CLUSTER_NAME="${CLUSTER_NAME:-ocis-subpath-e2e}"
NAMESPACE="${NAMESPACE:-ocis-subpath-e2e}"
RELEASE_NAME="${RELEASE_NAME:-ocis-subpath}"
TRAEFIK_NAMESPACE="${TRAEFIK_NAMESPACE:-traefik}"
TRAEFIK_RELEASE_NAME="${TRAEFIK_RELEASE_NAME:-traefik}"
PUBLIC_DNS_NAME="${PUBLIC_DNS_NAME:-127.0.0.1.sslip.io}"
INGRESS_HOST="${INGRESS_HOST:-${PUBLIC_DNS_NAME}}"
LOCAL_PORT="${LOCAL_PORT:-32443}"
if [ -z "${HOST_BIND_ADDRESS+x}" ]; then
  if [ "${INGRESS_HOST}" = "127.0.0.1.sslip.io" ]; then
    HOST_BIND_ADDRESS="127.0.0.1"
  else
    HOST_BIND_ADDRESS="0.0.0.0"
  fi
fi
HOST_ACCESS_ADDRESS="${HOST_ACCESS_ADDRESS:-}"
KEEP_CLUSTER="${KEEP_CLUSTER:-false}"
KEEP_ON_FAILURE="${KEEP_ON_FAILURE:-true}"
KUBECONFIG_PATH="${KUBECONFIG_PATH:-${ROOT_DIR}/.tmp/kind-${CLUSTER_NAME}.kubeconfig}"
KIND_CONFIG_PATH="${KIND_CONFIG_PATH:-${ROOT_DIR}/.tmp/kind-${CLUSTER_NAME}.yaml}"
TMP_DIR="${ROOT_DIR}/.tmp"

PATCHER_IMAGE_REPOSITORY="${PATCHER_IMAGE_REPOSITORY:-ocis-web-assets-patcher}"
PATCHER_IMAGE_TAG="${PATCHER_IMAGE_TAG:-e2e}"
PATCHER_IMAGE_NAME="${PATCHER_IMAGE_NAME:-${PATCHER_IMAGE_REPOSITORY}:${PATCHER_IMAGE_TAG}}"
PATCHER_IMAGE_PULL_POLICY="${PATCHER_IMAGE_PULL_POLICY:-IfNotPresent}"
OCIS_IMAGE_REPOSITORY="${OCIS_IMAGE_REPOSITORY:-ocis-subpath}"
OCIS_IMAGE_TAG="${OCIS_IMAGE_TAG:-8.0.1-e2e}"
OCIS_IMAGE_NAME="${OCIS_IMAGE_NAME:-${OCIS_IMAGE_REPOSITORY}:${OCIS_IMAGE_TAG}}"
OCIS_IMAGE_PULL_POLICY="${OCIS_IMAGE_PULL_POLICY:-IfNotPresent}"
E2E_USERNAME="${E2E_USERNAME:-admin}"
E2E_PASSWORD="${E2E_PASSWORD:-admin}"
SUBPATH="$(e2e_subpath)"

log() {
  echo "[e2e-helm-kind] $*"
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "[e2e-helm-kind] required command not found: $1" >&2
    exit 1
  }
}

kctl() {
  kubectl --kubeconfig "${KUBECONFIG_PATH}" "$@"
}

hctl() {
  helm --kubeconfig "${KUBECONFIG_PATH}" "$@"
}

validate_node_port() {
  local port="$1"

  if ! [[ "${port}" =~ ^[0-9]+$ ]] || [ "${port}" -lt 30000 ] || [ "${port}" -gt 32767 ]; then
    echo "[e2e-helm-kind] LOCAL_PORT must be a Kubernetes NodePort in the 30000-32767 range." >&2
    return 1
  fi
}

cluster_has_host_port_mapping() {
  local binding

  binding="$(docker port "${CLUSTER_NAME}-control-plane" "${LOCAL_PORT}/tcp" 2>/dev/null || true)"
  [ -n "${binding}" ] || return 1

  printf '%s\n' "${binding}" | awk -v expected="${HOST_BIND_ADDRESS}:${LOCAL_PORT}" '$0 == expected { found = 1 } END { exit(found ? 0 : 1) }'
}

print_debug_info() {
  log "collecting debug information..."

  if [ -f "${KUBECONFIG_PATH}" ]; then
    kctl -n "${NAMESPACE}" get all || true
    kctl -n "${NAMESPACE}" get events --sort-by=.lastTimestamp || true
    kctl -n "${NAMESPACE}" describe pods || true
    kctl -n "${NAMESPACE}" logs deploy/"${RELEASE_NAME}" --all-containers=true || true
    hctl status "${RELEASE_NAME}" -n "${NAMESPACE}" || true
    kctl -n "${TRAEFIK_NAMESPACE}" get all || true
    kctl -n "${TRAEFIK_NAMESPACE}" logs deploy/"${TRAEFIK_RELEASE_NAME}" --all-containers=true || true
  fi

}

cleanup() {
  local exit_code=$?
  local keep_resources="false"

  set +e

  if [ "${exit_code}" -ne 0 ]; then
    print_debug_info
    if [ "${KEEP_ON_FAILURE}" = "true" ]; then
      keep_resources="true"
      log "KEEP_ON_FAILURE=true. keeping kind cluster for debugging: ${CLUSTER_NAME}"
    fi
  fi

  if [ "${KEEP_CLUSTER}" = "true" ]; then
    keep_resources="true"
    log "KEEP_CLUSTER=true. keeping kind cluster: ${CLUSTER_NAME}"
  fi

  if [ "${keep_resources}" = "true" ]; then
    log "dedicated kubeconfig: ${KUBECONFIG_PATH}"
    log "inspect with: kubectl --kubeconfig ${KUBECONFIG_PATH} -n ${NAMESPACE} get all"
    exit "${exit_code}"
  fi

  if kind get clusters | grep -qx "${CLUSTER_NAME}"; then
    log "deleting kind cluster: ${CLUSTER_NAME}"
    kind delete cluster --name "${CLUSTER_NAME}" >/dev/null 2>&1 || true
  fi

  if [ -f "${KUBECONFIG_PATH}" ]; then
    log "removing dedicated kubeconfig: ${KUBECONFIG_PATH}"
    rm -f "${KUBECONFIG_PATH}" || true
  fi

  exit "${exit_code}"
}

trap cleanup EXIT

require_command docker
require_command kind
require_command kubectl
require_command helm
require_command curl

cd "${ROOT_DIR}"
mkdir -p "${TMP_DIR}"

validate_node_port "${LOCAL_PORT}"
BASE_URL="https://${INGRESS_HOST}:${LOCAL_PORT}${SUBPATH}"

log "running helm lint..."
helm lint charts/ocis-subpath

log "building patcher image for kind..."
IMAGE_NAME="${PATCHER_IMAGE_NAME}" "${ROOT_DIR}/scripts/build-patcher-image.sh"

log "building patched oCIS image for kind..."
docker build -t "${OCIS_IMAGE_NAME}" "${ROOT_DIR}/images/ocis-subpath"

if kind get clusters | grep -qx "${CLUSTER_NAME}"; then
  log "kind cluster already exists: ${CLUSTER_NAME}"
  if ! cluster_has_host_port_mapping; then
    echo "[e2e-helm-kind] existing kind cluster does not expose ${HOST_BIND_ADDRESS}:${LOCAL_PORT}." >&2
    echo "[e2e-helm-kind] recreate it with: kind delete cluster --name ${CLUSTER_NAME}" >&2
    exit 1
  fi
  kind get kubeconfig --name "${CLUSTER_NAME}" > "${KUBECONFIG_PATH}"
else
  log "creating kind cluster: ${CLUSTER_NAME} with ${HOST_BIND_ADDRESS}:${LOCAL_PORT} bound to the host"
  cat >"${KIND_CONFIG_PATH}" <<EOF
kind: Cluster
apiVersion: kind.x-k8s.io/v1alpha4
nodes:
  - role: control-plane
    extraPortMappings:
      - containerPort: ${LOCAL_PORT}
        hostPort: ${LOCAL_PORT}
        listenAddress: "${HOST_BIND_ADDRESS}"
        protocol: TCP
EOF
  kind create cluster --name "${CLUSTER_NAME}" --kubeconfig "${KUBECONFIG_PATH}" --config "${KIND_CONFIG_PATH}"
fi

KIND_NODE_IP="$(kctl get nodes -o jsonpath='{.items[0].status.addresses[?(@.type=="InternalIP")].address}')"
if [ -z "${KIND_NODE_IP}" ]; then
  echo "[e2e-helm-kind] failed to resolve kind node internal IP" >&2
  exit 1
fi
if [ -n "${HOST_ACCESS_ADDRESS}" ]; then
  CURL_RESOLVE="${INGRESS_HOST}:${LOCAL_PORT}:${HOST_ACCESS_ADDRESS}"
  log "using https://${INGRESS_HOST}:${LOCAL_PORT}${SUBPATH} via forced host mapping ${HOST_ACCESS_ADDRESS}:${LOCAL_PORT}"
else
  CURL_RESOLVE=""
  log "using https://${INGRESS_HOST}:${LOCAL_PORT}${SUBPATH} via DNS"
fi

log "loading patcher image into kind..."
kind load docker-image "${PATCHER_IMAGE_NAME}" --name "${CLUSTER_NAME}"

log "loading patched oCIS image into kind..."
kind load docker-image "${OCIS_IMAGE_NAME}" --name "${CLUSTER_NAME}"

log "installing Traefik..."
kctl get namespace "${TRAEFIK_NAMESPACE}" >/dev/null 2>&1 || kctl create namespace "${TRAEFIK_NAMESPACE}"
hctl repo add traefik https://traefik.github.io/charts >/dev/null 2>&1 || true
hctl repo update traefik >/dev/null
hctl upgrade --install "${TRAEFIK_RELEASE_NAME}" traefik/traefik \
  --namespace "${TRAEFIK_NAMESPACE}" \
  --wait \
  --timeout 10m \
  --set service.spec.type=NodePort \
  --set "ports.websecure.nodePort=${LOCAL_PORT}"

log "preparing namespace..."
kctl get namespace "${NAMESPACE}" >/dev/null 2>&1 || kctl create namespace "${NAMESPACE}"

log "creating fixed oCIS secret for login coverage..."
kctl -n "${NAMESPACE}" create secret generic ocis-e2e-secrets \
  --from-literal=admin-password="${E2E_PASSWORD}" \
  --from-literal=jwt-secret=insecure-dev-jwt-secret-change-me \
  --from-literal=transfer-secret=insecure-dev-transfer-secret-change-me \
  --from-literal=machine-auth-api-key=insecure-dev-machine-auth-key-change-me \
  --dry-run=client -o yaml | kctl apply -f -

log "installing Helm release..."
hctl upgrade --install "${RELEASE_NAME}" charts/ocis-subpath \
  --namespace "${NAMESPACE}" \
  --wait \
  --timeout 10m \
  --set "ocis.baseUrl=https://${INGRESS_HOST}:${LOCAL_PORT}" \
  --set "ocis.subpath=${SUBPATH}" \
  --set "image.repository=${OCIS_IMAGE_REPOSITORY}" \
  --set "image.tag=${OCIS_IMAGE_TAG}" \
  --set "image.pullPolicy=${OCIS_IMAGE_PULL_POLICY}" \
  --set "ocis.insecure=true" \
  --set "ocis.existingSecret=ocis-e2e-secrets" \
  --set "ocis.proxyTls=false" \
  --set "ocis.generatedSecrets.enabled=false" \
  --set "ocis.oidc.rewriteWellknown=true" \
  --set "persistence.data.enabled=false" \
  --set "persistence.config.enabled=false" \
  --set "persistence.webAssets.enabled=false" \
  --set-json "hostAliases=[{\"ip\":\"${KIND_NODE_IP}\",\"hostnames\":[\"${INGRESS_HOST}\"]}]" \
  --set "webAssetsPatcher.image.repository=${PATCHER_IMAGE_REPOSITORY}" \
  --set "webAssetsPatcher.image.tag=${PATCHER_IMAGE_TAG}" \
  --set "webAssetsPatcher.image.pullPolicy=${PATCHER_IMAGE_PULL_POLICY}" \
  --set "webAssetsPatcher.patchAbsoluteUrls=true" \
  --set "ingress.enabled=true" \
  --set-json 'ingress.entryPoints=["websecure"]' \
  --set "ingress.hosts[0].host=${INGRESS_HOST}" \
  --set-json 'ingress.tls={}' \
  --set-json 'webAssetsPatcher.apps=["files","preview","pdf-viewer","search","text-editor","admin-settings","epub-reader"]'

log "waiting for deployment rollout..."
kctl -n "${NAMESPACE}" rollout status deploy/"${RELEASE_NAME}" --timeout=10m

for _ in $(seq 1 30); do
  curl_args=(-kfsS)
  if [ -n "${CURL_RESOLVE}" ]; then
    curl_args+=(--resolve "${CURL_RESOLVE}")
  fi
  if curl "${curl_args[@]}" "${BASE_URL}/config.json" >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

log "running HTTP smoke..."
CURL_RESOLVE="${CURL_RESOLVE}" "${ROOT_DIR}/scripts/e2e/smoke.sh" "${BASE_URL}"

log "running Playwright E2E..."
E2E_BASE_URL="${BASE_URL}" \
E2E_SUBPATH="${SUBPATH}" \
E2E_USERNAME="${E2E_USERNAME}" \
E2E_PASSWORD="${E2E_PASSWORD}" \
E2E_EXTRA_HOSTS="${HOST_ACCESS_ADDRESS:+${INGRESS_HOST}:${HOST_ACCESS_ADDRESS}}" \
"${ROOT_DIR}/scripts/e2e/shell.sh" -lc './scripts/e2e/run.sh'

log "helm kind e2e completed"
