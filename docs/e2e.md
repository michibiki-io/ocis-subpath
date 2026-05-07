# E2E and Validation

## Overview

This document covers the canonical Helm-on-kind E2E flow, Playwright execution, compose dev startup, and troubleshooting.

## Architecture

```text
owncloud/web source
  -> image build clones upstream and runs pnpm build
  -> final patcher image ships only dist + Python patcher
  -> initContainer or one-shot compose service copies dist
  -> patcher injects <base href="/ocis/"> and writes config.json
  -> oCIS serves patched assets via WEB_ASSET_CORE_PATH
  -> oCIS reads generated Web config via WEB_UI_CONFIG_FILE
```

## Why runtime Node build is avoided

- Kubernetes runtime stays lightweight and deterministic.
- Production pods do not need Node, pnpm, git, or Vite.
- Subpath changes are injected through env and a small Python patch step instead of rebuilding frontend assets.

## Why a subpath-specific image is not required

- The built ownCloud Web bundle stays portable.
- The patcher image is versioned by upstream ownCloud Web ref, not by deployment URL.
- `BASE_URL`, `SUBPATH`, `PUBLIC_URL`, and OIDC settings are injected at runtime through Helm values or container env.

## Build the patcher image

```bash
OWNCLOUD_WEB_REF=v12.3.3 \
IMAGE_NAME=ocis-web-assets-patcher:web-v12.3.3-subpath.1 \
./scripts/build-patcher-image.sh
```

## Compose Dev Startup

Compose is kept as a lightweight local startup path for manual inspection. It is not the canonical E2E environment.

The local compose stack is exposed at `https://ocis.local:9200/ocis` by default.

- The compose dev stack uses `Traefik -> oCIS`.
- HTTPS is terminated at Traefik.
- Web UI traffic is sent to the oCIS proxy on `:9200`.
- Embedded IDP discovery and auth traffic is sent to the IDP listener on `:9130`.
- Targeted absolute-URL patching is enabled so allowlisted root-absolute asset requests are rewritten to the configured subpath.
- The `external` web app is omitted because its app-provider discovery path returns invalid data in this local adapter setup and causes the Web UI to fall back to `Missing or invalid config`.

```bash
COMPOSE_SUBPATH=/ocis ./scripts/compose/up.sh
./scripts/compose/down.sh
```

## E2E structure

- `scripts/e2e/smoke.sh`: shared HTTP smoke checks against an already reachable base URL.
- `scripts/e2e/shell.sh`: low-level Playwright container launcher.
- `scripts/e2e/run.sh`: low-level Playwright test runner executed inside that container.
- `scripts/e2e/helm-kind.sh`: canonical E2E entrypoint. It provisions kind + Traefik + chart, runs `smoke.sh`, then runs Playwright.

Compose is intentionally outside the canonical E2E path to avoid duplicating Kubernetes routing behavior in a second test harness.

## Run Playwright with the required container form

```bash
docker run --rm \
  -e LOCAL_UID=$(id -u) \
  -e LOCAL_GID=$(id -g) \
  --add-host ocis.local:127.0.0.1 \
  --network host \
  -e E2E_BASE_URL=https://ocis.local:9200/ocis \
  -v "$PWD:/workspace" \
  -w /workspace \
  michibiki/playwright:v1.59.1-noble-jpn.2 \
  bash
```

Inside the container:

```bash
./scripts/e2e/run.sh
```

Optional login coverage can be enabled by creating `dev/.env` with:

```dotenv
E2E_USERNAME=admin
E2E_PASSWORD=admin
```

`./scripts/e2e/shell.sh` will load `dev/.env` automatically when it exists. The target environment must already be running.

## Run the Canonical E2E Flow

```bash
KEEP_ON_FAILURE=false ./scripts/e2e/helm-kind.sh
```

The kind flow exposes Traefik through a NodePort bound on the host. By default the Web UI is reachable at:

```text
https://127.0.0.1.sslip.io:32443/ocis
```

If you have a DNS name that resolves to the host IP, pass it with `PUBLIC_DNS_NAME`:

```bash
PUBLIC_DNS_NAME=ocis.dev.example.test KEEP_CLUSTER=true ./scripts/e2e/helm-kind.sh
```

With a custom `PUBLIC_DNS_NAME`, the host bind defaults to `0.0.0.0` so the DNS name can reach the kind NodePort. With the default `127.0.0.1.sslip.io`, the host bind defaults to `127.0.0.1`.

`HOST_ACCESS_ADDRESS` is only needed when the E2E runner must override DNS resolution, for example:

```bash
PUBLIC_DNS_NAME=ocis.dev.example.test HOST_ACCESS_ADDRESS=192.168.0.88 KEEP_CLUSTER=true ./scripts/e2e/helm-kind.sh
```

`INGRESS_HOST` can still be used as a lower-level override. `LOCAL_PORT` defaults to `32443` and must stay in Kubernetes' NodePort range (`30000-32767`). Changing `HOST_BIND_ADDRESS` or `LOCAL_PORT` requires recreating the kind cluster because kind port mappings are fixed at cluster creation.

Make targets expose the same structure:

```bash
make e2e
make e2e-helm-kind
make e2e-runner
```

## Troubleshooting

- Blank screen: run the Playwright suite and inspect `tests/e2e/playwright-report` for asset failures or JavaScript errors.
- `/ocis/config.json` returns HTML: verify both `WEB_HTTP_ROOT=/ocis` and `PROXY_HTTP_ROOT=/ocis` are set.
- `/ocis/.well-known/openid-configuration` returns HTML: verify the subpath well-known route forwards to the IDP listener on `:9130`.
- `/signin/*` or `/konnect/*` returns 404 during login: verify `IDP_HTTP_ADDR=0.0.0.0:9130` is set so Traefik can reach the embedded IDP.
- `/config.json` requested without subpath: verify `<base href="/ocis/">` exists in the patched `index.html` and check for root-absolute upstream changes before enabling targeted patching.
- `/js/...` requested without subpath: inspect the Playwright suspicious-request assertions and only then enable `webAssetsPatcher.patchAbsoluteUrls`.
- OIDC issuer mismatch: keep `PROXY_OIDC_ISSUER`, `OCIS_OIDC_ISSUER`, `WEB_OIDC_AUTHORITY`, and the generated `openIdConnect.authority` aligned.
- Ingress rewrite stripping subpath: remove rewrite rules that drop `/ocis` before the request reaches oCIS.
- Stale `.gz` files after HTML patch: the patcher deletes `.gz` and `.br` siblings for modified HTML files to avoid serving stale compressed content.
- Shared volume permissions: keep the chart `runAsUser`, `runAsGroup`, and `fsGroup` aligned with the non-root patcher user.

## Known limitations

- ownCloud Web upstream changes can introduce new root-absolute requests that require targeted allowlist patching.
- The implementation intentionally avoids broad JS/CSS rewrite rules.
- Compose defaults use weak secrets for local manual startup only. Production should provide real secrets through `ocis.existingSecret`.

## Security

- Production secrets are not autogenerated by default.
- The patcher final image contains no Node, pnpm, or git.
- Runtime containers are configured to run as non-root where possible.

## License

The patcher code in this repository is Apache-2.0 unless stated otherwise. The patcher image redistributes built ownCloud Web assets and preserves upstream license notices under `/licenses`; review ownCloud Web's AGPL licensing implications before redistributing images externally.
