#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import unittest
from unittest import mock
from pathlib import Path
from urllib.error import HTTPError


MODULE_PATH = Path(__file__).resolve().parents[1] / "read_release.py"
SPEC = importlib.util.spec_from_file_location("read_release", MODULE_PATH)
assert SPEC and SPEC.loader
read_release = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(read_release)


def release_data(overrides: dict[str, dict[str, str]] | None = None) -> dict[str, dict[str, str]]:
    data = {
        "release": {"mode": "auto"},
        "ocis": {
            "upstreamRef": "v8.0.1",
            "imageTag": "8.0.1-subpath.1",
            "repo": "https://github.com/owncloud/ocis.git",
        },
        "web": {
            "upstreamRef": "v12.3.3",
            "repo": "https://github.com/owncloud/web.git",
        },
        "patcher": {
            "imageTag": "web-v12.3.3-subpath.1",
        },
    }
    for section, values in (overrides or {}).items():
        data.setdefault(section, {}).update(values)
    return data


class ReadReleaseTests(unittest.TestCase):
    def test_missing_releases_are_auto_release_targets(self) -> None:
        current = release_data()
        targets = read_release.resolve_targets(
            current,
            current,
            [],
            True,
            {"ocis": True, "patcher": True, "chart": True},
        )

        self.assertEqual(
            targets,
            {
                "release_ocis": "true",
                "release_patcher": "true",
                "release_chart": "true",
            },
        )

    def test_existing_releases_allow_unchanged_targets_to_skip(self) -> None:
        current = release_data()
        targets = read_release.resolve_targets(
            current,
            current,
            [],
            True,
            {"ocis": False, "patcher": False, "chart": False},
        )

        self.assertEqual(
            targets,
            {
                "release_ocis": "false",
                "release_patcher": "false",
                "release_chart": "false",
            },
        )

    def test_explicit_false_override_suppresses_missing_release(self) -> None:
        current = release_data({"release": {"ocis": "false", "patcher": "auto", "chart": "auto"}})
        targets = read_release.resolve_targets(
            current,
            current,
            [],
            True,
            {"ocis": True, "patcher": True, "chart": True},
        )

        self.assertEqual(targets["release_ocis"], "false")
        self.assertEqual(targets["release_patcher"], "true")
        self.assertEqual(targets["release_chart"], "true")

    def test_chart_metadata_is_read_from_chart_yaml_text(self) -> None:
        self.assertEqual(
            read_release.parse_chart_metadata_text('version: 0.2.0\nappVersion: "ocis-8.0.1-subpath.1"\n'),
            ("0.2.0", "ocis-8.0.1-subpath.1"),
        )

    @mock.patch.dict(
        read_release.os.environ,
        {"GITHUB_REPOSITORY": "michibiki-io/ocis-subpath", "GITHUB_TOKEN": "token"},
        clear=True,
    )
    @mock.patch.object(read_release.urllib.request, "urlopen")
    def test_github_release_exists_checks_encoded_release_tag(self, urlopen: mock.Mock) -> None:
        urlopen.return_value.__enter__.return_value = object()

        self.assertTrue(read_release.github_release_exists("ocis/v8.0.1-subpath.1"))

        request = urlopen.call_args.args[0]
        self.assertIn("/releases/tags/ocis%2Fv8.0.1-subpath.1", request.full_url)

    @mock.patch.dict(
        read_release.os.environ,
        {"GITHUB_REPOSITORY": "michibiki-io/ocis-subpath", "GITHUB_TOKEN": "token"},
        clear=True,
    )
    @mock.patch.object(read_release.urllib.request, "urlopen")
    def test_github_release_missing_returns_false(self, urlopen: mock.Mock) -> None:
        urlopen.side_effect = HTTPError("https://api.github.test", 404, "not found", {}, None)

        self.assertFalse(read_release.github_release_exists("ocis/v8.0.1-subpath.1"))

    @mock.patch.dict(read_release.os.environ, {}, clear=True)
    @mock.patch.object(read_release, "tag_exists", return_value=True)
    def test_release_artifact_falls_back_to_git_tag_without_github_context(
        self,
        tag_exists: mock.Mock,
    ) -> None:
        self.assertTrue(read_release.release_artifact_exists("ocis/v8.0.1-subpath.1"))
        tag_exists.assert_called_once_with("ocis/v8.0.1-subpath.1")


if __name__ == "__main__":
    unittest.main()
