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
- This chart mounts an oCIS proxy CSP config by default. It keeps the upstream defaults, adds `data:` to `font-src` so PDF previews can load embedded `data:font/woff2` fonts, and automatically merges external OIDC origins into `connect-src`.
- Recommended production deployment remains a dedicated subdomain when possible.
- `traefik.enabled=true` renders Traefik `IngressRoute` and middleware resources. Traefik CRDs must be installed before applying the chart.
- The chart routes Web fallback, frontend APIs, IDP, discovery, backend API, and capabilities paths separately when using the builtin IDP. Subpath prefixes are stripped from backend API, frontend API, and capabilities requests before they reach their services.
- Set `ocis.oidc.external.enabled=true` with `ocis.oidc.issuer` or `ocis.oidc.authority` to use an external IDP. In that mode the chart does not render builtin IDP `IngressRoute` resources or the IDP `Service`.
- When external OIDC is enabled, the origins from `ocis.oidc.issuer`, `ocis.oidc.authority`, and `ocis.oidc.metadataUrl` are added to `ocis.csp.directives.connect-src` even when `connect-src` is explicitly set in values.
- `deploymentStrategy.type` defaults to `Recreate` because `persistence.data` and `persistence.config` are enabled by default and use `ReadWriteOnce` PVCs.
- Chart releases use independent Helm SemVer. Backend and patcher image tags are versioned separately and set through `values.yaml`.

## Deployment strategy and RWO PVCs

The chart renders `spec.strategy.type: Recreate` by default. This avoids creating a second oCIS pod during upgrades while the old pod is still using the default `ReadWriteOnce` `ocis-data` and `ocis-config` PVCs. Without this setting, Kubernetes defaults Deployments to `RollingUpdate`, which can trigger Multi-Attach errors on storage backends that enforce single-node attachment. For upgrades from chart versions that did not render `spec.strategy`, the chart also renders `rollingUpdate: null` with `Recreate` so Helm removes any live default `rollingUpdate` field during the migration.

```yaml
deploymentStrategy:
  type: Recreate
```

If your deployment does not use `ReadWriteOnce` persistence, or your storage and application topology can safely tolerate concurrent pods, you can opt back into rolling updates:

```yaml
deploymentStrategy:
  type: RollingUpdate
  rollingUpdate:
    maxSurge: 1
    maxUnavailable: 0
```

## Markdown images and CSP

Relative Markdown images that point to files beside the Markdown document are handled by the patched Web assets and loaded through the subpath WebDAV route.

External Markdown images are controlled by `ocis.csp.directives.img-src`. The default policy does not allow arbitrary remote image origins. Add only the required origins, for example:

```yaml
ocis:
  csp:
    directives:
      img-src:
        - "'self'"
        - "data:"
        - "blob:"
        - "https://commonmark.org/"
```

## Draw.io integration

The chart can generate a static ownCloud Web editor app for `.drawio` and `.drawio.svg` files. It uses diagrams.net embed mode: the editor UI runs in an iframe, while ownCloud Web still loads and saves the file content through oCIS.

The integration is disabled by default:

```yaml
drawio:
  enabled: false
```

For a public diagrams.net proof of concept:

```yaml
drawio:
  enabled: true
  editorUrl: "https://embed.diagrams.net/"
```

To use a self-hosted draw.io server, deploy that server separately and point the chart at its URL:

```yaml
drawio:
  enabled: true
  editorUrl: "https://drawio.example.com/"
```

When `drawio.enabled=true`, the chart passes a draw.io config block to the web assets patcher. The patcher writes `drawio/drawio.js`, adds it to `config.json` as an `external_apps` entry, and patches ownCloud Web's compound extension list so files ending in `.drawio.svg` are not treated as generic `.svg` files. When `drawio.csp.enabled=true`, the origin of `drawio.editorUrl` is added to `frame-src`; no broad `connect-src` rule is added by default.

The chart does not render an `app-registry.yaml` override for draw.io. The static Web app registers its own file extensions in ownCloud Web, and avoiding an App Registry YAML snippet prevents accidental replacement of oCIS' built-in MIME type defaults.

`webAssetsPatcher.extraConfig` is merged after generated chart config. If you set `extraConfig.external_apps`, it replaces the generated `external_apps` list; include the draw.io entry there if you still want this integration.

Security notes:

- With the public default, the diagrams.net editor application is loaded from `https://embed.diagrams.net`.
- Diagram data is saved back to oCIS, but the diagram content is handled in the browser by JavaScript from the editor origin.
- For high-sensitivity environments, use a self-hosted draw.io server and set `drawio.editorUrl` to that origin.

Known limitations:

- `.drawio.png` is not supported by this chart.
- The integration relies on the normal ownCloud Web save flow and does not implement collaborative editing or merge conflict resolution inside draw.io.
- Export formats such as PDF can involve diagrams.net-side conversion depending on editor configuration; validate those workflows before enabling them for sensitive content.

## External OIDC example

```yaml
ocis:
  baseUrl: https://michibiki.io
  subpath: /ocis
  oidc:
    external:
      enabled: true
    issuer: https://sso.michibiki.io
    metadataUrl: https://sso.michibiki.io/.well-known/openid-configuration
    authority: https://sso.michibiki.io
```

With `traefik.enabled=true`, `/ocis/app/list`, `/ocis/app/*`, and `/ocis/archiver/*` are routed to the frontend service on port `9140` with a higher priority than the Web fallback route. The rendered CSP includes `https://sso.michibiki.io` in `connect-src`.

## OIDC role assignment

oCIS role assignment from OIDC claims can be enabled with `ocis.roleAssignment.enabled=true`. The chart renders an oCIS `proxy.yaml` config and mounts it at `/etc/ocis/proxy.yaml`.

Current oCIS proxy role assignment supports one OIDC claim per mapper. Use `mode` to choose which values are rendered:

- `group`: use `groupClaim` and `groupMapping`
- `user`: use `userClaim` and `userMapping`
- `auto`: use `groupMapping` when it has entries, otherwise use `userMapping`

Generated role mappings are always ordered as `admin`, `spaceadmin`, `user`, then `guest`. oCIS assigns the first matching role, so this gives the effective priority `admin > spaceadmin > user > guest`.

```yaml
ocis:
  roleAssignment:
    enabled: true
    driver: oidc
    mode: group
    groupClaim: groups
    groupMapping:
      admin:
        - Domain Admins
        - Enterprise Admins
      spaceadmin:
        - ocisSpaceAdmin
      user:
        - ocisUser
      guest:
        - ocisGuest
    userClaim: preferred_username
    userMapping:
      admin:
        - admin@example.com
        - alice
      spaceadmin: []
      user:
        - bob
      guest: []
```

If both `groupMapping` and `userMapping` are configured, only the mapping selected by `mode` is rendered because oCIS accepts a single role claim in this config. The chart sets `PROXY_ROLE_ASSIGNMENT_DRIVER` automatically when role assignment is enabled. Values from `ocis.env` are rendered after chart-generated env vars; setting the same env var there is treated as an explicit override and can change oCIS behavior.

## Validation

```bash
helm lint charts/ocis-subpath
helm template ocis charts/ocis-subpath -f charts/ocis-subpath/values.yaml
make helm-template-role-assignment
make helm-template-drawio
```

## Known limitations

- ownCloud Web upstream changes can require patcher or test updates.
- If root-absolute asset requests appear, inspect E2E failures before enabling targeted patching.
- `ocis.existingSecret` is not enforced by the chart schema because templating should still work with example values.
