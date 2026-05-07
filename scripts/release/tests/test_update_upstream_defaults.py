#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import unittest
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


if __name__ == "__main__":
    unittest.main()
