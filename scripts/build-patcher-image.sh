#!/usr/bin/env bash
set -euo pipefail

OWNCLOUD_WEB_REF="${OWNCLOUD_WEB_REF:-v12.3.3}"
OWNCLOUD_WEB_REPO="${OWNCLOUD_WEB_REPO:-https://github.com/owncloud/web.git}"
NODE_IMAGE="${NODE_IMAGE:-node:24-alpine}"
IMAGE_NAME="${IMAGE_NAME:-ocis-web-assets-patcher:web-v12.3.3-subpath.1}"

docker build \
  -f images/web-assets-patcher/Dockerfile \
  --build-arg "OWNCLOUD_WEB_REF=${OWNCLOUD_WEB_REF}" \
  --build-arg "OWNCLOUD_WEB_REPO=${OWNCLOUD_WEB_REPO}" \
  --build-arg "NODE_IMAGE=${NODE_IMAGE}" \
  -t "${IMAGE_NAME}" \
  images/web-assets-patcher
