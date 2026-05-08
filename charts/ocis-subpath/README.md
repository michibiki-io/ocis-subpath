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
- Chart releases use independent Helm SemVer. Backend and patcher image tags are versioned separately and set through `values.yaml`.

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
```

## Known limitations

- ownCloud Web upstream changes can require patcher or test updates.
- If root-absolute asset requests appear, inspect E2E failures before enabling targeted patching.
- `ocis.existingSecret` is not enforced by the chart schema because templating should still work with example values.
