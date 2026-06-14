#!/usr/bin/env python3
"""Patch ownCloud Web assets for subpath hosting."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


DEFAULT_APPS = [
    "files",
    "preview",
    "pdf-viewer",
    "search",
    "text-editor",
    "external",
    "admin-settings",
    "epub-reader",
]
DEFAULT_OPTIONS = {"contextHelpersReadMore": True}
HTML_FILES = ("index.html", "oidc-callback.html", "oidc-silent-redirect.html")
ABSOLUTE_URL_PATTERNS = (
    "/config.json",
    "/themes/",
    "/fonts/",
    "/icons/",
    "/js/",
)
RELATIVE_URL_PATTERNS = (
    "config.json",
    "manifest.json",
    "robots.txt",
    "themes/",
    "fonts/",
    "icons/",
    "img/",
    "assets/",
    "js/",
)
OIDC_REDIRECT_TARGETS = {
    "oidc-callback.html": "web-oidc-callback",
    "oidc-silent-redirect.html": "web-oidc-silent-redirect",
}
SIGNED_URL_HASH_PATTERN = re.compile(
    r"const (?P<signature>[A-Za-z_$][A-Za-z0-9_$]*)=await this\.createHashedKey"
    r"\((?P<url>[A-Za-z_$][A-Za-z0-9_$]*)\.toString\(\),"
    r"(?P<public_token>[A-Za-z_$][A-Za-z0-9_$]*),(?P<password>[A-Za-z_$][A-Za-z0-9_$]*)\);"
    r"return (?P=url)\.searchParams\.set\(\"OC-Algo\",(?P<algorithm>"
    r"`PBKDF2/\$\{this\.ITERATION_COUNT\}-SHA512`|"
    r"\"PBKDF2/\"\.concat\(this\.ITERATION_COUNT,\"-SHA512\"\)"
    r")\),(?P=url)\.searchParams\.set\(\"OC-Signature\",(?P=signature)\),(?P=url)\.toString\(\)"
)
GRAPH_DRIVE_SERVER_URL_PATTERN = re.compile(r"(?P<name>[A-Za-z_$][A-Za-z0-9_$]*)=t=>new URL\(t\.webUrl\)\.origin")
WEBDAV_REMOTE_BASE_PATH_PATTERN = re.compile(
    r"const (?P<decoded>[A-Za-z_$][A-Za-z0-9_$]*)=decodeURIComponent\((?P<href>[A-Za-z_$][A-Za-z0-9_$]*)\),"
    r"(?P<prefix>[A-Za-z_$][A-Za-z0-9_$]*)=(?P<path_module>[A-Za-z_$][A-Za-z0-9_$]*)\.normalize"
    r"\((?P=path_module)\.join\((?P<remote_base>[A-Za-z_$][A-Za-z0-9_$]*),\"dav\"\)\);"
    r"return (?P=href)\?\.startsWith\((?P=prefix)\)\?"
    r"(?P<url_join>[A-Za-z_$][A-Za-z0-9_$]*)\((?P=decoded)\.replace\((?P=prefix),\"\"\),"
    r"\{leadingSlash:!0,trailingSlash:!1\}\):(?P=decoded)"
)
MARKDOWN_IMAGE_RENDERER_PATTERN = re.compile(
    r"(?P<prefix>__name:\"TextEditor\".*?setup\((?P<props>[A-Za-z_$][A-Za-z0-9_$]*)\)"
    r"\{.*?markdownItConfig\((?P<md>[A-Za-z_$][A-Za-z0-9_$]*)\)\{)"
    r"(?P=md)\.renderer\.rules\.link_open=function\("
    r"(?P<tokens>[A-Za-z_$][A-Za-z0-9_$]*),(?P<idx>[A-Za-z_$][A-Za-z0-9_$]*),"
    r"(?P<options>[A-Za-z_$][A-Za-z0-9_$]*),(?P<env>[A-Za-z_$][A-Za-z0-9_$]*),"
    r"(?P<self>[A-Za-z_$][A-Za-z0-9_$]*)\)\{"
    r"const (?P<token>[A-Za-z_$][A-Za-z0-9_$]*)=(?P=tokens)\[(?P=idx)\];"
    r"return (?P=token)\.attrGet\(\"href\"\)&&\((?P=token)\.attrSet\(\"target\",\"_blank\"\),"
    r"(?P=token)\.attrSet\(\"rel\",\"noopener noreferrer\"\)\),"
    r"(?P=self)\.renderToken\((?P=tokens),(?P=idx),(?P=options)\)\}",
    re.DOTALL,
)


class PatcherError(RuntimeError):
    """Raised when patching fails."""


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--src")
    parser.add_argument("--dst")
    parser.add_argument("--config-out")
    parser.add_argument("--base-url")
    parser.add_argument("--subpath")
    parser.add_argument("--public-url")
    parser.add_argument("--oidc-authority")
    parser.add_argument("--oidc-metadata-url")
    parser.add_argument("--oidc-client-id")
    parser.add_argument("--oidc-scope")
    parser.add_argument("--theme-path")
    parser.add_argument("--apps-json")
    parser.add_argument("--options-json")
    parser.add_argument("--extra-config-json")
    parser.add_argument("--patch-absolute-urls", action="store_true", default=None)
    return parser.parse_args(argv)


def env_or_value(value: str | None, env_name: str, default: str | None = None) -> str | None:
    if value is not None:
        return value
    return os.environ.get(env_name, default)


def env_or_json(value: str | None, env_name: str, default: Any) -> Any:
    raw = env_or_value(value, env_name)
    if raw is None:
        return deepcopy(default)
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise PatcherError(f"{env_name} must be valid JSON: {exc}") from exc


def parse_bool(value: str | None) -> bool:
    if value is None:
        return False
    return value.strip().lower() in {"1", "true", "yes", "on"}


def normalize_subpath(raw_subpath: str | None) -> str:
    if raw_subpath in (None, "", "/"):
        return "/"
    parsed = urlparse(raw_subpath)
    if parsed.query or parsed.fragment:
        raise PatcherError("subpath must not contain query string or fragment")
    subpath = parsed.path
    if not subpath.startswith("/"):
        raise PatcherError("subpath must start with '/'")
    normalized = re.sub(r"/{2,}", "/", subpath.rstrip("/"))
    return normalized or "/"


def validate_url(name: str, raw_url: str | None, *, allow_path: bool) -> str | None:
    if raw_url in (None, ""):
        return None
    parsed = urlparse(raw_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise PatcherError(f"{name} must be an absolute http(s) URL")
    if not allow_path and parsed.path not in ("", "/"):
        raise PatcherError(f"{name} must not include a path")
    if parsed.params or parsed.query or parsed.fragment:
        raise PatcherError(f"{name} must not include params, query, or fragment")
    path = parsed.path.rstrip("/") if allow_path else ""
    return parsed._replace(path=path, params="", query="", fragment="").geturl()


def join_url(base_url: str, suffix: str) -> str:
    if not suffix.startswith("/"):
        raise PatcherError(f"path must start with '/': {suffix}")
    return f"{base_url.rstrip('/')}{suffix}"


def deep_merge(base: Any, override: Any) -> Any:
    if isinstance(base, dict) and isinstance(override, dict):
        merged = dict(base)
        for key, value in override.items():
            merged[key] = deep_merge(merged.get(key), value) if key in merged else value
        return merged
    return override


def inject_base_href(html: str, base_href: str) -> str:
    base_tag = f'<base href="{base_href}">'
    if base_href != "/":
        expected_base = json.dumps(base_href)
        base_tag = f"""<script>
      ;(() => {{
        const expectedBase = {expected_base}
        for (const base of Array.from(document.head.querySelectorAll('base[href]'))) {{
          const pathname = new URL(base.href).pathname
          if (base.getAttribute('href') !== expectedBase && pathname !== expectedBase) {{
            base.setAttribute('href', expectedBase)
          }}
        }}
      }})()
    </script>
    {base_tag}"""
    existing_base = re.compile(r"<base\b[^>]*>", re.IGNORECASE)
    if existing_base.search(html):
        return existing_base.sub(base_tag, html, count=1)

    head_tag = re.compile(r"(<head\b[^>]*>)", re.IGNORECASE)
    if not head_tag.search(html):
        raise PatcherError("HTML document is missing a <head> element")
    return head_tag.sub(rf"\1\n    {base_tag}", html, count=1)


def inject_favicon_link(html: str, subpath: str) -> str:
    href = "/img/owncloud-app-icon.png" if subpath == "/" else f"{subpath}/img/owncloud-app-icon.png"
    link_tag = f'<link rel="icon" href="{href}" type="image/png">'
    existing_icon = re.compile(
        r"<link\b(?=[^>]*\brel=[\"'][^\"']*\b(?:shortcut\s+)?icon\b[^\"']*[\"'])[^>]*>",
        re.IGNORECASE,
    )
    if existing_icon.search(html):
        return existing_icon.sub(link_tag, html, count=1)

    head_close = re.compile(r"(</head\s*>)", re.IGNORECASE)
    if not head_close.search(html):
        raise PatcherError("HTML document is missing a closing </head> element")
    return head_close.sub(rf"    {link_tag}\n  \1", html, count=1)


def patch_allowlisted_absolute_urls(content: str, subpath: str) -> tuple[str, int]:
    if subpath == "/":
        return content, 0

    patched = content
    changes = 0
    prefix = subpath.rstrip("/")
    for pattern in ABSOLUTE_URL_PATTERNS:
        replacement = f"{prefix}{pattern}"
        regex = re.compile(rf'(?P<delim>["\'(=\s]){re.escape(pattern)}')
        patched, count = regex.subn(rf"\g<delim>{replacement}", patched)
        changes += count
    return patched, changes


def patch_allowlisted_relative_urls(content: str, subpath: str) -> tuple[str, int]:
    if subpath == "/":
        return content, 0

    patched = content
    changes = 0
    prefix = subpath.rstrip("/")
    for pattern in RELATIVE_URL_PATTERNS:
        regex = re.compile(rf'(?P<delim>["\'(=:\s])(?P<dot>\./)?{re.escape(pattern)}')
        patched, count = regex.subn(rf"\g<delim>{prefix}/{pattern}", patched)
        changes += count
    return patched, changes


def patch_oidc_redirect_html(html: str, subpath: str, target_path: str) -> str:
    script_pattern = re.compile(
        r"<script>\s*window\.onload = function \(\) \{.*?web-oidc-(?:callback|silent-redirect).*?</script>",
        re.IGNORECASE | re.DOTALL,
    )
    target_url_path = f"/{target_path}" if subpath == "/" else f"{subpath}/{target_path}"
    replacement = f"""<script>
  window.onload = function () {{
    const url = new URL('{target_url_path}', window.location.origin)
    window.location.replace(url.href + window.location.search)
  }}
</script>"""
    return script_pattern.sub(replacement, html, count=1)


def patch_signed_url_hash_path(content: str, subpath: str) -> tuple[str, int]:
    if subpath == "/":
        return content, 0

    def replacement(match: re.Match[str]) -> str:
        signature = match.group("signature")
        url = match.group("url")
        public_token = match.group("public_token")
        password = match.group("password")
        algorithm = match.group("algorithm")
        return (
            f"const __ocisSignedUrlForHash=new URL({url}.toString()),"
            '__ocisSubpathForHash=new URL(this.baseURI).pathname.replace(/\\/$/,"");'
            "__ocisSubpathForHash&&__ocisSubpathForHash!==\"/\"&&"
            "__ocisSignedUrlForHash.pathname.startsWith(__ocisSubpathForHash+\"/\")&&"
            "(__ocisSignedUrlForHash.pathname=__ocisSignedUrlForHash.pathname.slice(__ocisSubpathForHash.length)||\"/\");"
            f"const {signature}=await this.createHashedKey("
            f"__ocisSignedUrlForHash.toString(),{public_token},{password});"
            f'return {url}.searchParams.set("OC-Algo",{algorithm}),'
            f'{url}.searchParams.set("OC-Signature",{signature}),{url}.toString()'
        )

    return SIGNED_URL_HASH_PATTERN.subn(replacement, content)


def patch_graph_drive_server_url(content: str, subpath: str) -> tuple[str, int]:
    if subpath == "/":
        return content, 0

    def replacement(match: re.Match[str]) -> str:
        name = match.group("name")
        return (
            f"{name}=t=>{{"
            "const __ocisDriveWebUrl=new URL(t.webUrl),"
            '__ocisBasePath=new URL(document.baseURI).pathname.replace(/\\/$/,"");'
            'return __ocisDriveWebUrl.origin+(__ocisBasePath&&__ocisBasePath!=="/"?__ocisBasePath:"")'
            "}"
        )

    return GRAPH_DRIVE_SERVER_URL_PATTERN.subn(replacement, content)


def patch_webdav_remote_base_path(content: str, subpath: str) -> tuple[str, int]:
    if subpath == "/":
        return content, 0

    def replacement(match: re.Match[str]) -> str:
        decoded = match.group("decoded")
        href = match.group("href")
        prefix = match.group("prefix")
        path_module = match.group("path_module")
        remote_base = match.group("remote_base")
        url_join = match.group("url_join")
        options = "{leadingSlash:!0,trailingSlash:!1}"
        return (
            f'const __ocisDavPrefix="/dav",'
            f'{decoded}=decodeURIComponent({href}),'
            f'{prefix}={path_module}.normalize({path_module}.join({remote_base},"dav"));'
            f"return {href}?.startsWith({prefix})?"
            f'{url_join}({decoded}.replace({prefix},""),{options}):'
            f"{href}?.startsWith(__ocisDavPrefix)?"
            f'{url_join}({decoded}.replace(__ocisDavPrefix,""),{options}):'
            f"{decoded}"
        )

    return WEBDAV_REMOTE_BASE_PATH_PATTERN.subn(replacement, content)


def patch_markdown_image_sources(content: str, subpath: str, oidc_client_id: str = "web") -> tuple[str, int]:
    if subpath == "/":
        return content, 0

    def replacement(match: re.Match[str]) -> str:
        prefix = match.group("prefix")
        props = match.group("props")
        md = match.group("md")
        tokens = match.group("tokens")
        idx = match.group("idx")
        options = match.group("options")
        env = match.group("env")
        self_name = match.group("self")
        token = match.group("token")
        original_link_renderer = match.group(0)[len(prefix) :]
        js_oidc_client_id = json.dumps(oidc_client_id)
        image_renderer = (
            'const __ocisMarkdownImagePlaceholder="data:image/gif;base64,R0lGODlhAQABAAAAACw=",'
            f"__ocisMarkdownImageClientId={js_oidc_client_id},"
            f"__ocisDefaultMarkdownImageRenderer={md}.renderer.rules.image,"
            '__ocisEncodeMarkdownImagePath=t=>t.split("/").map((e,n)=>{'
            'if(n===0&&e==="")return"";'
            'try{e=decodeURIComponent(e)}catch{}'
            'return encodeURIComponent(e)'
            '}).join("/"),'
            '__ocisMarkdownImageAccessToken=()=>{'
            'try{for(let t=0;t<localStorage.length;t++){'
            'const e=localStorage.key(t);'
            'if(e?.startsWith("oc_oAuth.user:")&&e.endsWith(`:${__ocisMarkdownImageClientId}`)){'
            'const n=JSON.parse(localStorage.getItem(e)||"{}");'
            'return n.access_token||n.accessToken||""'
            "}}}catch{}return\"\"},"
            "__ocisPublicMarkdownRoute=()=>{"
            "try{"
            'const t=new URL(document.baseURI).pathname.replace(/\\/$/,""),'
            'e=t&&location.pathname.startsWith(`${t}/`)?location.pathname.slice(t.length):location.pathname,'
            'n=e.match(/^\\/(?:text-editor|preview)\\/public\\/([^/]+)(?:\\/(.*))?$/);'
            'if(!n)return null;'
            'const r=decodeURIComponent(n[1]);'
            'return{token:r,webDavPath:`/public-files/${encodeURIComponent(r)}${n[2]?`/${n[2]}`:""}`}'
            '}catch{return null}'
            "},"
            "__ocisPublicMarkdownPassword=t=>{"
            "try{"
            'const e=sessionStorage.getItem(`oc.publicLink.${t}.password`);'
            'if(!e)return"";'
            'try{return decodeURIComponent(escape(atob(e)))}catch{return atob(e)}'
            '}catch{return""}'
            "},"
            "__ocisMarkdownImageRequestHeaders=()=>{"
            "const t=__ocisPublicMarkdownRoute();"
            'if(t){const e={"public-token":t.token},n=__ocisPublicMarkdownPassword(t.token);'
            'return n&&(e.Authorization=`Basic ${btoa(unescape(encodeURIComponent(`public:${n}`)))}`),e}'
            "const e=__ocisMarkdownImageAccessToken();"
            'return e?{Authorization:`Bearer ${e}`}:{}}'
            ","
            '__ocisMarkdownImageCache=window.__ocisMarkdownImageCache||'
            "(window.__ocisMarkdownImageCache=new Map),"
            '__ocisLoadMarkdownImage=async t=>{'
            'const e=t.getAttribute("data-ocis-markdown-image-src");'
            'if(!e||t.getAttribute("data-ocis-markdown-image-state")==="loaded"||'
            't.getAttribute("data-ocis-markdown-image-state")==="loading")return;'
            't.setAttribute("data-ocis-markdown-image-state","loading");'
            "try{"
            'let n=__ocisMarkdownImageCache.get(e);'
            "if(!n){"
            "const r=__ocisMarkdownImageRequestHeaders(),"
            'i=await fetch(e,{credentials:"same-origin",headers:r});'
            'if(!i.ok)throw new Error(`Markdown image request failed: ${i.status}`);'
            "n=URL.createObjectURL(await i.blob()),__ocisMarkdownImageCache.set(e,n)"
            "}"
            't.src=n,t.setAttribute("data-ocis-markdown-image-state","loaded")'
            "}catch(n){console.error(n),t.setAttribute(\"data-ocis-markdown-image-state\",\"error\")}"
            "},"
            '__ocisProcessMarkdownImages=()=>document.querySelectorAll('
            '"img[data-ocis-markdown-image-src]").forEach(__ocisLoadMarkdownImage),'
            "__ocisStartMarkdownImageLoader=()=>{"
            "if(!window.__ocisMarkdownImageObserver&&document.body){"
            "window.__ocisMarkdownImageObserver=new MutationObserver(__ocisProcessMarkdownImages),"
            'window.__ocisMarkdownImageObserver.observe(document.body,{childList:!0,subtree:!0})'
            "}"
            "setTimeout(__ocisProcessMarkdownImages,0)"
            "},"
            "__ocisPublicMarkdownWebDavPath=()=>{"
            'const t=__ocisPublicMarkdownRoute();'
            'return t?.webDavPath||""'
            "},"
            "__ocisResolveMarkdownImageSrc=__ocisSrc=>{"
            'if(!__ocisSrc||/^[?#]/.test(__ocisSrc)||/^[a-z][a-z0-9+.-]*:/i.test(__ocisSrc)||'
            '__ocisSrc.startsWith("//")||__ocisSrc.startsWith("/"))return"";'
            f"const e=__ocisPublicMarkdownWebDavPath()||{props}.resource?.webDavPath;"
            'if(!e)return"";'
            "try{"
            'const n=String(e).startsWith("/")?String(e):`/${e}`,'
            'r=new URL(String(__ocisSrc),`https://ocis.invalid${n.replace(/\\/[^/]*$/,"/")}`),'
            'i=new URL(document.baseURI).pathname.replace(/\\/$/,"");'
            'return`${i&&i!=="/"?i:""}/dav${__ocisEncodeMarkdownImagePath(r.pathname)}${r.search}${r.hash}`'
            '}catch{return""}'
            "};"
            f"{md}.renderer.rules.image=function({tokens},{idx},{options},{env},{self_name}){{"
            f"const {token}={tokens}[{idx}],__ocisMarkdownImageSrc={token}.attrGet(\"src\"),"
            "__ocisResolvedMarkdownImageSrc=__ocisResolveMarkdownImageSrc(__ocisMarkdownImageSrc);"
            f"return __ocisResolvedMarkdownImageSrc&&({token}.attrSet(\"data-ocis-markdown-image-src\","
            f"__ocisResolvedMarkdownImageSrc),{token}.attrSet(\"src\",__ocisMarkdownImagePlaceholder),"
            "__ocisStartMarkdownImageLoader()),"
            f"__ocisDefaultMarkdownImageRenderer?__ocisDefaultMarkdownImageRenderer.call(this,{tokens},{idx},{options},{env},{self_name}):"
            f"{self_name}.renderToken({tokens},{idx},{options})"
            "},"
        )
        return f"{prefix}{image_renderer}{original_link_renderer}"

    return MARKDOWN_IMAGE_RENDERER_PATTERN.subn(replacement, content)


def remove_precompressed_variants(path: Path) -> list[str]:
    removed: list[str] = []
    for suffix in (".gz", ".br"):
        candidate = Path(f"{path}{suffix}")
        if candidate.exists():
            candidate.unlink()
            removed.append(candidate.name)
    return removed


def build_config(
    public_url: str,
    theme_path: str,
    oidc_authority: str,
    oidc_metadata_url: str,
    oidc_client_id: str,
    oidc_scope: str,
    apps: Any,
    options: Any,
    extra_config: Any,
) -> dict[str, Any]:
    if not isinstance(apps, list) or not apps:
        raise PatcherError("apps must be a non-empty JSON array")
    if not isinstance(options, dict):
        raise PatcherError("options must be a JSON object")
    if not isinstance(extra_config, dict):
        raise PatcherError("extra config must be a JSON object")

    base_config: dict[str, Any] = {
        "server": public_url,
        "theme": join_url(public_url, theme_path),
        "openIdConnect": {
            "metadata_url": oidc_metadata_url,
            "authority": oidc_authority,
            "client_id": oidc_client_id,
            "response_type": "code",
            "scope": oidc_scope,
        },
        "apps": apps,
        "options": options,
    }
    return deep_merge(base_config, extra_config)


def ensure_smoke_checks(dst_dir: Path) -> None:
    if not (dst_dir / "index.html").is_file():
        raise PatcherError("patched dist is missing index.html")
    if not (dst_dir / "js").is_dir():
        raise PatcherError("patched dist is missing js/ directory")


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def patch_assets(
    src_dir: Path,
    dst_dir: Path,
    config_out: Path,
    public_url: str,
    subpath: str,
    theme_path: str,
    oidc_authority: str,
    oidc_metadata_url: str,
    oidc_client_id: str,
    oidc_scope: str,
    apps: Any,
    options: Any,
    extra_config: Any,
    patch_absolute_urls: bool,
) -> dict[str, Any]:
    if not src_dir.is_dir():
        raise PatcherError(f"source dist does not exist: {src_dir}")

    if dst_dir.exists():
        shutil.rmtree(dst_dir)
    shutil.copytree(src_dir, dst_dir)

    base_href = "/" if subpath == "/" else f"{subpath}/"
    patched_html: list[str] = []
    removed_variants: list[str] = []
    absolute_url_changes = 0
    relative_url_changes = 0
    signed_url_hash_changes = 0
    graph_drive_server_url_changes = 0
    webdav_remote_base_path_changes = 0
    markdown_image_source_changes = 0

    for html_name in HTML_FILES:
        html_path = dst_dir / html_name
        if not html_path.exists():
            continue
        html = html_path.read_text(encoding="utf-8")
        patched = inject_base_href(html, base_href)
        if html_name == "index.html":
            patched = inject_favicon_link(patched, subpath)
        redirect_target = OIDC_REDIRECT_TARGETS.get(html_name)
        if redirect_target:
            patched = patch_oidc_redirect_html(patched, subpath, redirect_target)
        if patch_absolute_urls:
            patched, count = patch_allowlisted_absolute_urls(patched, subpath)
            absolute_url_changes += count
        patched, count = patch_allowlisted_relative_urls(patched, subpath)
        relative_url_changes += count
        html_path.write_text(patched, encoding="utf-8")
        patched_html.append(html_name)
        removed_variants.extend(remove_precompressed_variants(html_path))

    if patch_absolute_urls:
        for suffix in (".js", ".mjs", ".css"):
            for asset_path in dst_dir.rglob(f"*{suffix}"):
                content = asset_path.read_text(encoding="utf-8")
                patched, count = patch_allowlisted_absolute_urls(content, subpath)
                if count:
                    absolute_url_changes += count
                if patched != content:
                    asset_path.write_text(patched, encoding="utf-8")
                    removed_variants.extend(remove_precompressed_variants(asset_path))

        for asset_path in dst_dir.rglob("*.json"):
            content = asset_path.read_text(encoding="utf-8")
            patched, count = patch_allowlisted_absolute_urls(content, subpath)
            if count:
                absolute_url_changes += count
            patched, count = patch_allowlisted_relative_urls(patched, subpath)
            if count:
                relative_url_changes += count
            if patched != content:
                asset_path.write_text(patched, encoding="utf-8")
                removed_variants.extend(remove_precompressed_variants(asset_path))

    for suffix in (".js", ".mjs"):
        for asset_path in dst_dir.rglob(f"*{suffix}"):
            content = asset_path.read_text(encoding="utf-8")
            patched, count = patch_signed_url_hash_path(content, subpath)
            if count:
                signed_url_hash_changes += count
            patched, count = patch_graph_drive_server_url(patched, subpath)
            if count:
                graph_drive_server_url_changes += count
            patched, count = patch_webdav_remote_base_path(patched, subpath)
            if count:
                webdav_remote_base_path_changes += count
            patched, count = patch_markdown_image_sources(patched, subpath, oidc_client_id)
            if count:
                markdown_image_source_changes += count
            if patched != content:
                asset_path.write_text(patched, encoding="utf-8")
                removed_variants.extend(remove_precompressed_variants(asset_path))

    ensure_smoke_checks(dst_dir)

    config_payload = build_config(
        public_url=public_url,
        theme_path=theme_path,
        oidc_authority=oidc_authority,
        oidc_metadata_url=oidc_metadata_url,
        oidc_client_id=oidc_client_id,
        oidc_scope=oidc_scope,
        apps=apps,
        options=options,
        extra_config=extra_config,
    )
    write_json(config_out, config_payload)

    return {
        "src": str(src_dir),
        "dst": str(dst_dir),
        "config_out": str(config_out),
        "server_url": public_url,
        "public_url": public_url,
        "subpath": subpath,
        "patched_html": patched_html,
        "removed_precompressed": removed_variants,
        "patched_absolute_url_references": absolute_url_changes,
        "patched_relative_url_references": relative_url_changes,
        "patched_signed_url_hash_references": signed_url_hash_changes,
        "patched_graph_drive_server_url_references": graph_drive_server_url_changes,
        "patched_webdav_remote_base_path_references": webdav_remote_base_path_changes,
        "patched_markdown_image_source_references": markdown_image_source_changes,
    }


def build_runtime_config(args: argparse.Namespace) -> dict[str, Any]:
    src = env_or_value(args.src, "SRC_DIST", "/input/dist")
    dst = env_or_value(args.dst, "DST_DIST", "/web-assets/dist")
    config_out = env_or_value(args.config_out, "WEB_CONFIG_OUT", "/web-config/config.json")
    base_url = validate_url("base_url", env_or_value(args.base_url, "BASE_URL"), allow_path=False)
    subpath = normalize_subpath(env_or_value(args.subpath, "SUBPATH", "/"))
    public_url = validate_url("public_url", env_or_value(args.public_url, "PUBLIC_URL"), allow_path=True)
    if public_url is None:
        if base_url is None:
            raise PatcherError("either BASE_URL or PUBLIC_URL must be set")
        public_url = base_url if subpath == "/" else f"{base_url}{subpath}"

    oidc_authority = validate_url(
        "oidc_authority",
        env_or_value(args.oidc_authority, "OIDC_AUTHORITY", public_url),
        allow_path=True,
    )
    oidc_metadata_url = validate_url(
        "oidc_metadata_url",
        env_or_value(args.oidc_metadata_url, "OIDC_METADATA_URL", f"{public_url}/.well-known/openid-configuration"),
        allow_path=True,
    )
    theme_path = env_or_value(args.theme_path, "THEME_PATH", "/themes/owncloud/theme.json")
    if theme_path is None or not theme_path.startswith("/"):
        raise PatcherError("theme path must start with '/'")

    patch_absolute_urls = (
        parse_bool(os.environ.get("PATCH_ABSOLUTE_URLS"))
        if args.patch_absolute_urls is None
        else args.patch_absolute_urls
    )

    return {
        "src_dir": Path(src),
        "dst_dir": Path(dst),
        "config_out": Path(config_out),
        "public_url": public_url,
        "subpath": subpath,
        "theme_path": theme_path,
        "oidc_authority": oidc_authority,
        "oidc_metadata_url": oidc_metadata_url,
        "oidc_client_id": env_or_value(args.oidc_client_id, "OIDC_CLIENT_ID", "web"),
        "oidc_scope": env_or_value(args.oidc_scope, "OIDC_SCOPE", "openid profile email"),
        "apps": env_or_json(args.apps_json, "WEB_APPS_JSON", DEFAULT_APPS),
        "options": env_or_json(args.options_json, "WEB_OPTIONS_JSON", DEFAULT_OPTIONS),
        "extra_config": env_or_json(args.extra_config_json, "WEB_EXTRA_CONFIG_JSON", {}),
        "patch_absolute_urls": patch_absolute_urls,
    }


def main(argv: list[str] | None = None) -> int:
    try:
        args = parse_args(argv)
        runtime = build_runtime_config(args)
        summary = patch_assets(**runtime)
        print(json.dumps(summary, indent=2, sort_keys=True))
        return 0
    except PatcherError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
