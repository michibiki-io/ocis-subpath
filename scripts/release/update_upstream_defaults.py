#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from sync_chart_defaults import parse_release_yaml, replace_once, require_release_value, sync_chart_defaults

OCIS_TAG_PATTERN = re.compile(r"^(?P<version>[0-9]+\.[0-9]+\.[0-9]+)-subpath\.(?P<revision>[0-9]+)$")
WEB_TAG_PATTERN = re.compile(r"^web-v?(?P<version>[0-9]+\.[0-9]+\.[0-9]+)-subpath\.(?P<revision>[0-9]+)$")


def normalize_ref(value: str, label: str) -> str:
    value = value.strip()
    if re.fullmatch(r"\d+\.\d+\.\d+", value):
        value = f"v{value}"
    if not re.fullmatch(r"v\d+\.\d+\.\d+", value):
        raise SystemExit(f"{label} must look like v8.0.1")
    return value


def ocis_ref_from_tag(tag: str) -> str:
    match = OCIS_TAG_PATTERN.match(tag)
    return f"v{match.group('version')}" if match else ""


def web_ref_from_tag(tag: str) -> str:
    match = WEB_TAG_PATTERN.match(tag)
    return f"v{match.group('version')}" if match else ""


def next_ocis_tag_for_ref(latest_ref: str, current_ref: str, current_tag: str) -> str:
    if latest_ref == current_ref and current_tag:
        return current_tag
    return f"{latest_ref.removeprefix('v')}-subpath.1"


def next_web_tag_for_ref(latest_ref: str, current_ref: str, current_tag: str) -> str:
    if latest_ref == current_ref and current_tag:
        return current_tag
    return f"web-v{latest_ref.removeprefix('v')}-subpath.1"


def write_outputs(values: dict[str, str]) -> None:
    output_path = os.getenv("GITHUB_OUTPUT")
    lines = [f"{key}={value}" for key, value in values.items()]
    if output_path:
        with open(output_path, "a", encoding="utf-8") as fh:
            fh.write("\n".join(lines))
            fh.write("\n")
    print("\n".join(lines))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ocis-ref", required=True)
    parser.add_argument("--web-ref", required=True)
    args = parser.parse_args()

    latest_ocis_ref = normalize_ref(args.ocis_ref, "ocis ref")
    latest_web_ref = normalize_ref(args.web_ref, "web ref")

    values_path = ROOT / "charts/ocis-subpath/values.yaml"
    chart_path = ROOT / "charts/ocis-subpath/Chart.yaml"
    dockerfile_path = ROOT / "images/ocis-subpath/Dockerfile"
    build_script_path = ROOT / "scripts/build-patcher-image.sh"
    e2e_doc_path = ROOT / "docs/e2e.md"
    release_path = ROOT / "release.yaml"

    release_data = parse_release_yaml(release_path)
    current_ocis_tag = require_release_value(release_data, "ocis", "imageTag")
    current_patcher_tag = require_release_value(release_data, "patcher", "imageTag")
    current_ocis_ref = normalize_ref(require_release_value(release_data, "ocis", "upstreamRef"), "release ocis upstreamRef")
    current_web_ref = normalize_ref(require_release_value(release_data, "web", "upstreamRef"), "release web upstreamRef")
    next_ocis_tag = next_ocis_tag_for_ref(latest_ocis_ref, current_ocis_ref, current_ocis_tag)
    next_web_tag = next_web_tag_for_ref(latest_web_ref, current_web_ref, current_patcher_tag)

    upstream_changed = latest_ocis_ref != current_ocis_ref or latest_web_ref != current_web_ref

    if upstream_changed and release_path.exists():
        release = release_path.read_text(encoding="utf-8")
        release = replace_once(r"^  upstreamRef: v[0-9]+\.[0-9]+\.[0-9]+$", f"  upstreamRef: {latest_ocis_ref}", release, "release ocis upstreamRef")
        release = replace_once(r"^  imageTag: [0-9]+\.[0-9]+\.[0-9]+-subpath\.[0-9]+$", f"  imageTag: {next_ocis_tag}", release, "release ocis imageTag")
        release = replace_once(r"(?ms)(^web:\n  upstreamRef: )v[0-9]+\.[0-9]+\.[0-9]+", lambda match: f"{match.group(1)}{latest_web_ref}", release, "release web upstreamRef")
        release = replace_once(r"(?ms)(^patcher:\n(?:  .*\n)*?  imageTag: )web-v[0-9]+\.[0-9]+\.[0-9]+-subpath\.[0-9]+", lambda match: f"{match.group(1)}{next_web_tag}", release, "release patcher imageTag")
        release_path.write_text(release, encoding="utf-8")

    sync_result = sync_chart_defaults(release_path, values_path, chart_path)
    changed = upstream_changed or sync_result["changed"] == "true"
    if not changed:
        write_outputs(
            {
                "changed": "false",
                "current_ocis_ref": current_ocis_ref,
                "current_web_ref": current_web_ref,
                "next_ocis_tag": current_ocis_tag,
                "next_web_tag": current_patcher_tag,
            }
        )
        return 0

    if upstream_changed:
        dockerfile = dockerfile_path.read_text(encoding="utf-8")
        dockerfile = replace_once(r"^ARG OCIS_REF=.*$", f"ARG OCIS_REF={latest_ocis_ref}", dockerfile, "Dockerfile OCIS_REF")
        dockerfile_path.write_text(dockerfile, encoding="utf-8")

        build_script = build_script_path.read_text(encoding="utf-8")
        build_script = replace_once(
            r'^OWNCLOUD_WEB_REF="\$\{OWNCLOUD_WEB_REF:-[^}]+\}"$',
            f'OWNCLOUD_WEB_REF="${{OWNCLOUD_WEB_REF:-{latest_web_ref}}}"',
            build_script,
            "OWNCLOUD_WEB_REF",
        )
        build_script = replace_once(
            r'^IMAGE_NAME="\$\{IMAGE_NAME:-ocis-web-assets-patcher:[^}]+\}"$',
            f'IMAGE_NAME="${{IMAGE_NAME:-ocis-web-assets-patcher:{next_web_tag}}}"',
            build_script,
            "IMAGE_NAME",
        )
        build_script_path.write_text(build_script, encoding="utf-8")

        if e2e_doc_path.exists():
            e2e_doc = e2e_doc_path.read_text(encoding="utf-8")
            e2e_doc = re.sub(
                r"ocis-web-assets-patcher:web-v[0-9]+\.[0-9]+\.[0-9]+-subpath\.[0-9]+",
                f"ocis-web-assets-patcher:{next_web_tag}",
                e2e_doc,
            )
            e2e_doc_path.write_text(e2e_doc, encoding="utf-8")

    write_outputs(
        {
            "changed": "true",
            "current_ocis_ref": current_ocis_ref,
            "current_web_ref": current_web_ref,
            "next_ocis_tag": next_ocis_tag,
            "next_web_tag": next_web_tag,
            "next_chart_version": sync_result["chart_version"],
        }
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
