# ocis-subpath Helm chart

This chart is an adapter for an unsupported or experimental deployment pattern: serving oCIS and ownCloud Web from a preserved subpath such as `https://example.com/ocis`.

## Required values

- `ocis.baseUrl`
- `ocis.subpath`
- `ocis.existingSecret` or `ocis.generatedSecrets.enabled=true`

## Example

```bash
helm template ocis charts/ocis-subpath \
  --set ocis.baseUrl=https://example.com \
  --set ocis.subpath=/ocis \
  --set ocis.existingSecret=ocis-secrets
```

## Notes

- This chart uses `WEB_ASSET_CORE_PATH` and `WEB_UI_CONFIG_FILE` for custom Web assets and runtime JSON config.
- This chart mounts an oCIS proxy CSP config by default. It keeps the upstream defaults and adds `data:` to `font-src` so PDF previews can load embedded `data:font/woff2` fonts.
- Recommended production deployment remains a dedicated subdomain when possible.
- `ingress.enabled=true` renders Traefik `IngressRoute` and middleware resources. Traefik CRDs must be installed before applying the chart.
- The chart routes Web, IDP, discovery, API, and capabilities paths separately. Only backend API paths are stripped before they reach the oCIS proxy.
- Chart releases use independent Helm SemVer. Backend and patcher image tags are versioned separately and set through `values.yaml`.

## Validation

```bash
helm lint charts/ocis-subpath
helm template ocis charts/ocis-subpath -f charts/ocis-subpath/values.yaml
```

## Known limitations

- ownCloud Web upstream changes can require patcher or test updates.
- If root-absolute asset requests appear, inspect E2E failures before enabling targeted patching.
- `ocis.existingSecret` is not enforced by the chart schema because templating should still work with example values.
