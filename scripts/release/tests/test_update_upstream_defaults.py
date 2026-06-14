#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import contextlib
import io
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "update_upstream_defaults.py"
SPEC = importlib.util.spec_from_file_location("update_upstream_defaults", MODULE_PATH)
assert SPEC and SPEC.loader
update_upstream_defaults = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(update_upstream_defaults)


class UpdateUpstreamDefaultsTests(unittest.TestCase):
    def test_next_tags_preserve_ocis_revision_when_only_web_moves(self) -> None:
        self.assertEqual(
            update_upstream_defaults.next_ocis_tag_for_ref(
                "v8.0.1",
                "v8.0.1",
                "8.0.1-subpath.2",
            ),
            "8.0.1-subpath.2",
        )
        self.assertEqual(
            update_upstream_defaults.next_web_tag_for_ref(
                "v12.3.4",
                "v12.3.3",
                "web-v12.3.3-subpath.7",
            ),
            "web-v12.3.4-subpath.1",
        )

    def test_next_tags_preserve_web_revision_when_only_ocis_moves(self) -> None:
        self.assertEqual(
            update_upstream_defaults.next_ocis_tag_for_ref(
                "v8.0.2",
                "v8.0.1",
                "8.0.1-subpath.2",
            ),
            "8.0.2-subpath.1",
        )
        self.assertEqual(
            update_upstream_defaults.next_web_tag_for_ref(
                "v12.3.3",
                "v12.3.3",
                "web-v12.3.3-subpath.7",
            ),
            "web-v12.3.3-subpath.7",
        )

    def test_refs_are_read_from_current_tags(self) -> None:
        self.assertEqual(update_upstream_defaults.ocis_ref_from_tag("8.0.1-subpath.2"), "v8.0.1")
        self.assertEqual(update_upstream_defaults.web_ref_from_tag("web-v12.3.3-subpath.7"), "v12.3.3")

    def test_main_repairs_chart_default_drift_without_upstream_movement(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "charts/ocis-subpath").mkdir(parents=True)
            (root / "images/ocis-subpath").mkdir(parents=True)
            (root / "scripts").mkdir()
            (root / "release.yaml").write_text(
                """\
release:
  mode: auto
ocis:
  upstreamRef: v8.0.4
  imageTag: 8.0.4-subpath.1
  repo: https://github.com/owncloud/ocis.git
web:
  upstreamRef: v12.4.0
  repo: https://github.com/owncloud/web.git
patcher:
  imageTag: web-v12.4.0-subpath.4
""",
                encoding="utf-8",
            )
            (root / "charts/ocis-subpath/values.yaml").write_text(
                """\
image:
  tag: "8.0.4-subpath.1"
webAssetsPatcher:
  image:
    tag: "web-v12.4.0-subpath.3"
""",
                encoding="utf-8",
            )
            (root / "charts/ocis-subpath/Chart.yaml").write_text(
                """\
apiVersion: v2
name: ocis-subpath
version: 0.2.5
appVersion: "ocis-8.0.4-subpath.1"
""",
                encoding="utf-8",
            )

            output = io.StringIO()
            with (
                mock.patch.object(update_upstream_defaults, "ROOT", root),
                mock.patch.object(
                    sys,
                    "argv",
                    ["update_upstream_defaults.py", "--ocis-ref", "v8.0.4", "--web-ref", "v12.4.0"],
                ),
                contextlib.redirect_stdout(output),
            ):
                self.assertEqual(update_upstream_defaults.main(), 0)

            self.assertIn("changed=true", output.getvalue())
            self.assertIn(
                '    tag: "web-v12.4.0-subpath.4"',
                (root / "charts/ocis-subpath/values.yaml").read_text(encoding="utf-8"),
            )
            self.assertIn("version: 0.2.6", (root / "charts/ocis-subpath/Chart.yaml").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
