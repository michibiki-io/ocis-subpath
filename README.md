# oCIS Subpath project

This repository provides a subpath adapter for serving ownCloud Infinite Scale and ownCloud Web at URLs such as `https://example.com/ocis/`.

## Run the compose stack

```bash
cp compose/.env.example compose/.env
./scripts/compose/up.sh
```

The local stack is exposed at `https://ocis.local:9200/ocis`.

## Render or install the Helm chart

```bash
helm lint charts/ocis-subpath
helm template ocis charts/ocis-subpath \
  --set ocis.baseUrl=https://example.com \
  --set ocis.subpath=/ocis \
  --set ocis.existingSecret=ocis-secrets
```

Chart-specific details are documented in [charts/ocis-subpath/README.md](/home/staratlas@ad.michibiki.io/workspace/ocis-web-assets-patcher/charts/ocis-subpath/README.md).

## Validation and E2E

The canonical E2E flow runs the Helm chart on kind. Validation flows, Playwright usage, troubleshooting, and implementation notes are documented in [docs/e2e.md](/home/staratlas@ad.michibiki.io/workspace/ocis-web-assets-patcher/docs/e2e.md).

## Release

Release streams are split by artifact:

- patched oCIS backend image: `ocis/v8.0.1-subpath.1`
- ownCloud Web assets patcher image: `patcher/web-v12.3.3-subpath.1`
- Helm chart: `chart/v0.2.0`

The upstream tracking workflow opens an issue and a draft PR when `owncloud/ocis` or `owncloud/web` moves. Generated PRs get `release-on-merge` by default; closing the PR discards the proposed version changes, while merging it publishes the release artifacts. Release details are documented in [docs/release.md](/home/staratlas@ad.michibiki.io/workspace/ocis-web-assets-patcher/docs/release.md).
