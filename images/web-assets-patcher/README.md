# web-assets-patcher

`web-assets-patcher` builds portable ownCloud Web assets once, then adapts them at runtime for an oCIS subpath deployment.

## Image behavior

- Build stage clones `owncloud/web` at `OWNCLOUD_WEB_REF`, installs dependencies with Corepack/pnpm, and runs `pnpm build`.
- Final stage contains only Python, the built dist bundle under `/input/dist`, upstream license notices under `/licenses`, and the patcher entrypoint.
- Runtime patching injects `<base href="...">` into HTML files and generates a standalone Web UI config JSON for `WEB_UI_CONFIG_FILE`.

## Runtime environment

- `SRC_DIST` default: `/input/dist`
- `DST_DIST` default: `/web-assets/dist`
- `WEB_CONFIG_OUT` default: `/web-config/config.json`
- `BASE_URL` or `PUBLIC_URL` must be set
- `SUBPATH` default: `/`
- `OIDC_AUTHORITY` and `OIDC_METADATA_URL` default from `PUBLIC_URL`

## Test

```bash
python -m unittest discover -s images/web-assets-patcher/tests
```
