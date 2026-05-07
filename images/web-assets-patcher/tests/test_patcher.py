import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from patcher import (
    PatcherError,
    build_runtime_config,
    normalize_subpath,
    patch_assets,
    inject_favicon_link,
    patch_graph_drive_server_url,
    patch_signed_url_hash_path,
)


HTML_INDEX = """<!doctype html>
<html>
  <head>
    <meta charset="utf-8">
    <title>ownCloud</title>
  </head>
  <body>
    <script type="module" src="./js/index.mjs"></script>
  </body>
</html>
"""

HTML_CALLBACK = """<!doctype html>
<html>
  <head>
    <title>Callback</title>
  </head>
  <body>
    <script>
      window.onload = function () {
        const base = document.querySelector('base')
        const path = base ? new URL(base.href).pathname.split('/') : [...window.location.pathname.split('/').slice(0, -1), 'index.html#']
        const url = new URL([...path, 'web-oidc-callback'].filter(Boolean).join('/'), window.location.origin)
        window.location.href = url.href + window.location.search
      }
    </script>
  </body>
</html>
"""

HTML_SILENT_REDIRECT = """<!doctype html>
<html>
  <head>
    <title>Silent Redirect</title>
  </head>
  <body>
    <script>
      window.onload = function () {
        const base = document.querySelector('base')
        const path = base ? new URL(base.href).pathname.split('/') : [...window.location.pathname.split('/').slice(0, -1), 'index.html#']
        const url = new URL([...path, 'web-oidc-silent-redirect'].filter(Boolean).join('/'), window.location.origin)
        window.location.href = url.href + window.location.search
      }
    </script>
  </body>
</html>
"""


class PatcherTests(unittest.TestCase):
    def make_dist(self, root: Path) -> Path:
        src = root / "src"
        (src / "js").mkdir(parents=True)
        (src / "themes" / "owncloud").mkdir(parents=True)
        (src / "js" / "index.mjs").write_text(
            'fetch("/config.json"); import("/js/chunks/demo.mjs");',
            encoding="utf-8",
        )
        (src / "index.html").write_text(HTML_INDEX, encoding="utf-8")
        (src / "index.html.gz").write_text("stale", encoding="utf-8")
        (src / "oidc-callback.html").write_text(HTML_CALLBACK, encoding="utf-8")
        (src / "oidc-silent-redirect.html").write_text(HTML_SILENT_REDIRECT, encoding="utf-8")
        (src / "themes" / "owncloud" / "theme.json").write_text("{}", encoding="utf-8")
        return src

    def test_normalize_subpath(self):
        self.assertEqual(normalize_subpath(""), "/")
        self.assertEqual(normalize_subpath("/"), "/")
        self.assertEqual(normalize_subpath("/ocis/"), "/ocis")
        self.assertEqual(normalize_subpath("/foo//bar/"), "/foo/bar")
        with self.assertRaises(PatcherError):
            normalize_subpath("ocis")
        with self.assertRaises(PatcherError):
            normalize_subpath("/ocis?x=1")

    def test_patch_assets_injects_base_and_generates_config(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            src = self.make_dist(tmp)
            dst = tmp / "dst"
            config_out = tmp / "config" / "config.json"

            summary = patch_assets(
                src_dir=src,
                dst_dir=dst,
                config_out=config_out,
                public_url="https://example.com/ocis",
                subpath="/ocis",
                theme_path="/themes/owncloud/theme.json",
                oidc_authority="https://example.com/ocis",
                oidc_metadata_url="https://example.com/ocis/.well-known/openid-configuration",
                oidc_client_id="web",
                oidc_scope="openid profile email",
                apps=["files"],
                options={"contextHelpersReadMore": True},
                extra_config={"openIdConnect": {"prompt": "login"}, "custom": {"enabled": True}},
                patch_absolute_urls=False,
            )

            patched_index = (dst / "index.html").read_text(encoding="utf-8")
            patched_callback = (dst / "oidc-callback.html").read_text(encoding="utf-8")
            patched_silent_redirect = (dst / "oidc-silent-redirect.html").read_text(encoding="utf-8")
            self.assertIn('<base href="/ocis/">', patched_index)
            self.assertIn('<link rel="icon" href="/ocis/img/owncloud-app-icon.png" type="image/png">', patched_index)
            self.assertFalse((dst / "index.html.gz").exists())
            self.assertIn("new URL('/ocis/web-oidc-callback'", patched_callback)
            self.assertNotIn("document.querySelector('base')", patched_callback)
            self.assertIn("new URL('/ocis/web-oidc-silent-redirect'", patched_silent_redirect)
            self.assertNotIn("document.querySelector('base')", patched_silent_redirect)

            config = json.loads(config_out.read_text(encoding="utf-8"))
            self.assertEqual(config["server"], "https://example.com/ocis")
            self.assertEqual(config["theme"], "https://example.com/ocis/themes/owncloud/theme.json")
            self.assertEqual(
                config["openIdConnect"]["metadata_url"],
                "https://example.com/ocis/.well-known/openid-configuration",
            )
            self.assertEqual(config["openIdConnect"]["prompt"], "login")
            self.assertTrue(config["custom"]["enabled"])
            self.assertEqual(summary["patched_html"], ["index.html", "oidc-callback.html", "oidc-silent-redirect.html"])

    def test_patch_absolute_urls_only_when_enabled(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            src = self.make_dist(tmp)
            dst = tmp / "dst"

            patch_assets(
                src_dir=src,
                dst_dir=dst,
                config_out=tmp / "config.json",
                public_url="https://example.com/ocis",
                subpath="/ocis",
                theme_path="/themes/owncloud/theme.json",
                oidc_authority="https://example.com/ocis",
                oidc_metadata_url="https://example.com/ocis/.well-known/openid-configuration",
                oidc_client_id="web",
                oidc_scope="openid profile email",
                apps=["files"],
                options={"contextHelpersReadMore": True},
                extra_config={},
                patch_absolute_urls=True,
            )

            script = (dst / "js" / "index.mjs").read_text(encoding="utf-8")
            self.assertIn('fetch("/ocis/config.json")', script)
            self.assertIn('import("/ocis/js/chunks/demo.mjs")', script)

    def test_inject_favicon_link_replaces_existing_icon(self):
        source = '<html><head><link rel="shortcut icon" href="/favicon.ico"></head><body></body></html>'

        patched = inject_favicon_link(source, "/ocis")

        self.assertIn('<link rel="icon" href="/ocis/img/owncloud-app-icon.png" type="image/png">', patched)
        self.assertNotIn('/favicon.ico', patched)

    def test_patch_signed_url_hash_path_keeps_public_url_intact(self):
        source = (
            'async signUrl({url:e,username:n,publicToken:r,publicLinkPassword:s}){'
            'const o=new URL(e);'
            'o.searchParams.set("OC-Credential",n),o.searchParams.set("OC-Date",new Date().toISOString()),'
            'o.searchParams.set("OC-Expires",this.TTL.toString()),o.searchParams.set("OC-Verb","GET");'
            'const i=await this.createHashedKey(o.toString(),r,s);'
            'return o.searchParams.set("OC-Algo","PBKDF2/".concat(this.ITERATION_COUNT,"-SHA512")),'
            'o.searchParams.set("OC-Signature",i),o.toString()}'
        )

        patched, count = patch_signed_url_hash_path(source, "/ocis")

        self.assertEqual(count, 1)
        self.assertIn("new URL(this.baseURI).pathname", patched)
        self.assertIn("createHashedKey(__ocisSignedUrlForHash.toString(),r,s)", patched)
        self.assertIn("o.toString()", patched)

    def test_patch_graph_drive_server_url_keeps_subpath(self):
        source = 'const or=t=>new URL(t.webUrl).origin,O0=({axiosClient:t,config:e})=>{}'

        patched, count = patch_graph_drive_server_url(source, "/ocis")

        self.assertEqual(count, 1)
        self.assertIn("new URL(document.baseURI).pathname", patched)
        self.assertIn('or=t=>{', patched)
        self.assertIn('__ocisDriveWebUrl.origin+(__ocisBasePath&&__ocisBasePath!=="/"?__ocisBasePath:"")', patched)

    def test_requires_index_and_js(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            src = tmp / "src"
            src.mkdir()
            with self.assertRaises(PatcherError):
                patch_assets(
                    src_dir=src,
                    dst_dir=tmp / "dst",
                    config_out=tmp / "config.json",
                    public_url="https://example.com",
                    subpath="/",
                    theme_path="/themes/owncloud/theme.json",
                    oidc_authority="https://example.com",
                    oidc_metadata_url="https://example.com/.well-known/openid-configuration",
                    oidc_client_id="web",
                    oidc_scope="openid profile email",
                    apps=["files"],
                    options={"contextHelpersReadMore": True},
                    extra_config={},
                    patch_absolute_urls=False,
                )

    def test_runtime_config_uses_public_url_override(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            env = {
                "SRC_DIST": str(tmp / "src"),
                "DST_DIST": str(tmp / "dst"),
                "WEB_CONFIG_OUT": str(tmp / "config.json"),
                "BASE_URL": "https://example.com",
                "SUBPATH": "/ocis",
                "PUBLIC_URL": "https://cdn.example.com/custom",
            }
            original = {}
            for key, value in env.items():
                original[key] = os.environ.get(key)
                os.environ[key] = value
            try:
                runtime = build_runtime_config(type("Args", (), {"src": None, "dst": None, "config_out": None, "base_url": None, "subpath": None, "public_url": None, "oidc_authority": None, "oidc_metadata_url": None, "oidc_client_id": None, "oidc_scope": None, "theme_path": None, "apps_json": None, "options_json": None, "extra_config_json": None, "patch_absolute_urls": None})())
                self.assertEqual(runtime["public_url"], "https://cdn.example.com/custom")
                self.assertEqual(runtime["oidc_authority"], "https://cdn.example.com/custom")
            finally:
                for key, value in original.items():
                    if value is None:
                        os.environ.pop(key, None)
                    else:
                        os.environ[key] = value


if __name__ == "__main__":
    unittest.main()
