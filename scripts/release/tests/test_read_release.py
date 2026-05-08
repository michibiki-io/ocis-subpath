#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


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
            "version": "0.1.0",
            "imageTag": "web-v12.3.3-subpath.1",
        },
        "chart": {
            "version": "0.1.0",
            "appVersion": "ocis-8.0.1-subpath.1",
        },
    }
    for section, values in (overrides or {}).items():
        data.setdefault(section, {}).update(values)
    return data


class ReadReleaseTests(unittest.TestCase):
    def test_missing_release_tags_are_auto_release_targets(self) -> None:
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

    def test_existing_release_tags_allow_unchanged_targets_to_skip(self) -> None:
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

    def test_explicit_false_override_suppresses_missing_tag_release(self) -> None:
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


if __name__ == "__main__":
    unittest.main()
