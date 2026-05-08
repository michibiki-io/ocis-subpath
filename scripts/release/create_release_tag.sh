#!/usr/bin/env bash
set -euo pipefail

: "${GIT_TAG:?GIT_TAG is required}"
: "${GITHUB_SHA:?GITHUB_SHA is required}"

git fetch --force --tags origin

if git rev-parse -q --verify "refs/tags/${GIT_TAG}" >/dev/null; then
  tagged_commit="$(git rev-list -n 1 "${GIT_TAG}")"
  if [ "${tagged_commit}" = "${GITHUB_SHA}" ]; then
    echo "Tag already exists on this commit: ${GIT_TAG}"
    exit 0
  fi

  if [ -z "${GH_TOKEN:-}" ] || ! command -v gh >/dev/null 2>&1; then
    echo "Refusing to reuse ${GIT_TAG}; it points to ${tagged_commit}, not ${GITHUB_SHA}" >&2
    echo "Set GH_TOKEN and provide gh to verify whether the stale tag has a GitHub Release." >&2
    exit 1
  fi

  if gh release view "${GIT_TAG}" >/dev/null 2>&1; then
    echo "Refusing to reuse ${GIT_TAG}; it already has a GitHub Release and points to ${tagged_commit}, not ${GITHUB_SHA}" >&2
    exit 1
  fi

  echo "::warning::Replacing stale tag without a GitHub Release: ${GIT_TAG} (${tagged_commit} -> ${GITHUB_SHA})"
  git tag -d "${GIT_TAG}" >/dev/null
  git push origin ":refs/tags/${GIT_TAG}"
fi

git config user.name "github-actions[bot]"
git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
git tag -a "${GIT_TAG}" "${GITHUB_SHA}" -m "Release ${GIT_TAG}"
git push origin "refs/tags/${GIT_TAG}"
