#!/usr/bin/env bash

normalize_subpath() {
  local raw="${1:-/ocis}"
  if [[ -z "${raw}" || "${raw}" == "/" ]]; then
    printf '/'
    return
  fi

  raw="/${raw#/}"
  while [[ "${raw}" == *"//"* ]]; do
    raw="${raw//\/\//\/}"
  done
  raw="${raw%/}"

  if [[ -z "${raw}" ]]; then
    printf '/'
  else
    printf '%s' "${raw}"
  fi
}

e2e_subpath() {
  if [[ -n "${E2E_SUBPATH:-}" ]]; then
    normalize_subpath "${E2E_SUBPATH}"
  elif [[ -n "${E2E_BASE_URL:-}" ]]; then
    subpath_from_url "${E2E_BASE_URL}"
  else
    normalize_subpath "/ocis"
  fi
}

e2e_base_url() {
  local subpath="${1:-$(e2e_subpath)}"
  local origin="${E2E_BASE_ORIGIN:-https://ocis.local:9200}"

  if [[ -n "${E2E_BASE_URL:-}" ]]; then
    printf '%s' "${E2E_BASE_URL%/}"
  elif [[ "${subpath}" == "/" ]]; then
    printf '%s' "${origin%/}"
  else
    printf '%s%s' "${origin%/}" "${subpath}"
  fi
}

subpath_from_url() {
  local url="${1}"
  local without_scheme="${url#*://}"
  local path="${without_scheme#*/}"

  if [[ "${path}" == "${without_scheme}" ]]; then
    printf '/'
    return
  fi

  path="/${path%%\?*}"
  path="${path%%#*}"
  normalize_subpath "${path}"
}

render_traefik_dynamic_config() {
  local subpath="${1}"
  local output="${2}"
  local template="${3}"
  local escaped_subpath

  mkdir -p "$(dirname "${output}")"
  escaped_subpath="$(printf '%s' "${subpath}" | sed 's/[\/&]/\\&/g')"
  sed "s/__SUBPATH__/${escaped_subpath}/g" "${template}" > "${output}"
}
