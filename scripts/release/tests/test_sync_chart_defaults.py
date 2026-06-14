#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import tempfile
import unittest
from unittest import mock
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "sync_chart_defaults.py"
SPEC = importlib.util.spec_from_file_location("sync_chart_defaults", MODULE_PATH)
assert SPEC and SPEC.loader
sync_chart_defaults = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(sync_chart_defaults)


RELEASE_YAML = """\
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
"""

VALUES_YAML = """\
replicaCount: 1

image:
  repository: ghcr.io/michibiki-io/ocis-subpath
  tag: "8.0.4-subpath.1"
  pullPolicy: IfNotPresent

webAssetsPatcher:
  enabled: true
  image:
    repository: ghcr.io/michibiki-io/ocis-web-assets-patcher
    tag: "web-v12.4.0-subpath.3"
    pullPolicy: IfNotPresent
"""

CHART_YAML = """\
apiVersion: v2
name: ocis-subpath
version: 0.2.5
appVersion: "ocis-8.0.4-subpath.1"
"""


class SyncChartDefaultsTests(unittest.TestCase):
    def write_fixture(self, root: Path, values: str = VALUES_YAML, chart: str = CHART_YAML) -> tuple[Path, Path, Path]:
        release_path = root / "release.yaml"
        values_path = root / "values.yaml"
        chart_path = root / "Chart.yaml"
        release_path.write_text(RELEASE_YAML, encoding="utf-8")
        values_path.write_text(values, encoding="utf-8")
        chart_path.write_text(chart, encoding="utf-8")
        return release_path, values_path, chart_path

    def test_check_fails_when_values_drift_from_release_yaml(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            release_path, values_path, chart_path = self.write_fixture(Path(tmp))

            with self.assertRaises(SystemExit) as raised:
                sync_chart_defaults.sync_chart_defaults(
                    release_path,
                    values_path,
                    chart_path,
                    check=True,
                )

            self.assertIn("webAssetsPatcher.image.tag", str(raised.exception))

    def test_sync_updates_values_and_bumps_chart_patch_version(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            release_path, values_path, chart_path = self.write_fixture(Path(tmp))

            result = sync_chart_defaults.sync_chart_defaults(release_path, values_path, chart_path)

            self.assertEqual(result["changed"], "true")
            self.assertEqual(result["chart_version"], "0.2.6")
            self.assertIn('    tag: "web-v12.4.0-subpath.4"', values_path.read_text(encoding="utf-8"))
            self.assertIn("version: 0.2.6", chart_path.read_text(encoding="utf-8"))

    def test_sync_does_not_bump_when_defaults_already_match(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            release_path, values_path, chart_path = self.write_fixture(
                Path(tmp),
                values=VALUES_YAML.replace("web-v12.4.0-subpath.3", "web-v12.4.0-subpath.4"),
            )

            result = sync_chart_defaults.sync_chart_defaults(release_path, values_path, chart_path)

            self.assertEqual(result["changed"], "false")
            self.assertEqual(result["chart_version"], "0.2.5")
            self.assertIn("version: 0.2.5", chart_path.read_text(encoding="utf-8"))

    def test_app_version_drift_is_checked_and_synced(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            release_path, values_path, chart_path = self.write_fixture(
                Path(tmp),
                values=VALUES_YAML.replace("web-v12.4.0-subpath.3", "web-v12.4.0-subpath.4"),
                chart=CHART_YAML.replace("ocis-8.0.4-subpath.1", "ocis-8.0.3-subpath.1"),
            )

            with self.assertRaises(SystemExit) as raised:
                sync_chart_defaults.sync_chart_defaults(
                    release_path,
                    values_path,
                    chart_path,
                    check=True,
                )
            self.assertIn("Chart.yaml appVersion", str(raised.exception))

            result = sync_chart_defaults.sync_chart_defaults(release_path, values_path, chart_path)
            self.assertEqual(result["chart_version"], "0.2.6")
            self.assertIn('appVersion: "ocis-8.0.4-subpath.1"', chart_path.read_text(encoding="utf-8"))

    def test_base_check_requires_chart_version_change_when_defaults_change(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            _release_path, values_path, chart_path = self.write_fixture(
                Path(tmp),
                values=VALUES_YAML.replace("web-v12.4.0-subpath.3", "web-v12.4.0-subpath.4"),
            )

            def fake_git_show(_ref: str, path: Path) -> str:
                return VALUES_YAML if path == values_path else CHART_YAML

            with mock.patch.object(sync_chart_defaults, "git_show", side_effect=fake_git_show):
                mismatches = sync_chart_defaults.chart_version_mismatches_for_base(
                    "base-sha",
                    values_path,
                    chart_path,
                )

            self.assertEqual(
                mismatches,
                [
                    "charts/ocis-subpath/Chart.yaml version must change when chart default image tags or appVersion change"
                ],
            )


if __name__ == "__main__":
    unittest.main()
