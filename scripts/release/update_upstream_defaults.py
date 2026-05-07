#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import re
from pathlib import Path
from typing import Callable


ROOT = Path(__file__).resolve().parents[2]
OCIS_TAG_PATTERN = re.compile(r"^(?P<version>[0-9]+\.[0-9]+\.[0-9]+)-subpath\.(?P<revision>[0-9]+)$")
WEB_TAG_PATTERN = re.compile(r"^web-v?(?P<version>[0-9]+\.[0-9]+\.[0-9]+)-subpath\.(?P<revision>[0-9]+)$")


def normalize_ref(value: str, label: str) -> str:
    value = value.strip()
    if re.fullmatch(r"\d+\.\d+\.\d+", value):
        value = f"v{value}"
    if not re.fullmatch(r"v\d+\.\d+\.\d+", value):
        raise SystemExit(f"{label} must look like v8.0.1")
    return value


def replace_once(pattern: str, replacement: str | Callable[[re.Match[str]], str], text: str, label: str) -> str:
    repl = replacement if callable(replacement) else lambda _match: replacement
    next_text, count = re.subn(pattern, repl, text, count=1, flags=re.MULTILINE)
    if count != 1:
        raise SystemExit(f"failed to update {label}")
    return next_text


def yaml_scalar_value(line: str) -> str:
    value = line.split(":", 1)[1].strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def read_values_tags(text: str) -> tuple[str, str]:
    root_image_tag = ""
    patcher_image_tag = ""
    in_root_image = False
    in_patcher = False
    in_patcher_image = False

    for line in text.splitlines():
        if line and not line.startswith(" "):
            in_root_image = line == "image:"
            in_patcher = line == "webAssetsPatcher:"
            in_patcher_image = False
            continue

        if in_root_image and line.startswith("  tag:"):
            root_image_tag = yaml_scalar_value(line)
            in_root_image = False
            continue

        if in_patcher:
            if line == "  image:":
                in_patcher_image = True
                continue
            if in_patcher_image and line.startswith("    tag:"):
                patcher_image_tag = yaml_scalar_value(line)
                in_patcher_image = False
                continue

    return root_image_tag, patcher_image_tag


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


def update_values_tags(text: str, ocis_tag: str, patcher_tag: str) -> str:
    lines = text.splitlines(keepends=True)
    in_root_image = False
    in_patcher = False
    in_patcher_image = False
    updated_root = False
    updated_patcher = False

    for index, line in enumerate(lines):
        stripped_newline = "\n" if line.endswith("\n") else ""
        body = line[:-1] if stripped_newline else line

        if body and not body.startswith(" "):
            in_root_image = body == "image:"
            in_patcher = body == "webAssetsPatcher:"
            in_patcher_image = False
            continue

        if in_root_image and body.startswith("  tag:"):
            lines[index] = f'  tag: "{ocis_tag}"{stripped_newline}'
            in_root_image = False
            updated_root = True
            continue

        if in_patcher:
            if body == "  image:":
                in_patcher_image = True
                continue
            if in_patcher_image and body.startswith("    tag:"):
                lines[index] = f'    tag: "{patcher_tag}"{stripped_newline}'
                in_patcher_image = False
                updated_patcher = True
                continue

    if not updated_root:
        raise SystemExit("failed to update backend image tag")
    if not updated_patcher:
        raise SystemExit("failed to update patcher image tag")
    return "".join(lines)


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

    values = values_path.read_text(encoding="utf-8")
    current_ocis_tag, current_patcher_tag = read_values_tags(values)
    current_ocis_ref = ocis_ref_from_tag(current_ocis_tag)
    current_web_ref = web_ref_from_tag(current_patcher_tag)
    next_ocis_tag = next_ocis_tag_for_ref(latest_ocis_ref, current_ocis_ref, current_ocis_tag)
    next_web_tag = next_web_tag_for_ref(latest_web_ref, current_web_ref, current_patcher_tag)

    changed = latest_ocis_ref != current_ocis_ref or latest_web_ref != current_web_ref
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

    values = update_values_tags(values, next_ocis_tag, next_web_tag)
    values_path.write_text(values, encoding="utf-8")

    chart = chart_path.read_text(encoding="utf-8")
    version_match = re.search(r'^version:\s*"?([0-9]+)\.([0-9]+)\.([0-9]+)"?\s*$', chart, flags=re.MULTILINE)
    if not version_match:
        raise SystemExit("failed to read chart version")
    major, minor, patch = map(int, version_match.groups())
    next_chart_version = f"{major}.{minor}.{patch + 1}"
    chart = replace_once(r'^version:\s*"?[0-9]+\.[0-9]+\.[0-9]+"?', f"version: {next_chart_version}", chart, "chart version")
    chart = replace_once(r'^appVersion:\s*"?[^"\n]+"?', f'appVersion: "ocis-{next_ocis_tag}"', chart, "chart appVersion")
    chart_path.write_text(chart, encoding="utf-8")

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

    if release_path.exists():
        release = release_path.read_text(encoding="utf-8")
        release = replace_once(r"^  upstreamRef: v[0-9]+\.[0-9]+\.[0-9]+$", f"  upstreamRef: {latest_ocis_ref}", release, "release ocis upstreamRef")
        release = replace_once(r"^  imageTag: [0-9]+\.[0-9]+\.[0-9]+-subpath\.[0-9]+$", f"  imageTag: {next_ocis_tag}", release, "release ocis imageTag")
        release = replace_once(r"(?ms)(^web:\n  upstreamRef: )v[0-9]+\.[0-9]+\.[0-9]+", lambda match: f"{match.group(1)}{latest_web_ref}", release, "release web upstreamRef")
        release = replace_once(r"(?ms)(^patcher:\n(?:  .*\n)*?  imageTag: )web-v[0-9]+\.[0-9]+\.[0-9]+-subpath\.[0-9]+", lambda match: f"{match.group(1)}{next_web_tag}", release, "release patcher imageTag")
        release = replace_once(r"(?ms)(^chart:\n  version: )[0-9]+\.[0-9]+\.[0-9]+", lambda match: f"{match.group(1)}{next_chart_version}", release, "release chart version")
        release = replace_once(r"(?ms)(^chart:\n(?:  .*\n)*?  appVersion: )ocis-[0-9]+\.[0-9]+\.[0-9]+-subpath\.[0-9]+", lambda match: f"{match.group(1)}ocis-{next_ocis_tag}", release, "release chart appVersion")
        release_path.write_text(release, encoding="utf-8")

    write_outputs(
        {
            "changed": "true",
            "current_ocis_ref": current_ocis_ref,
            "current_web_ref": current_web_ref,
            "next_ocis_tag": next_ocis_tag,
            "next_web_tag": next_web_tag,
            "next_chart_version": next_chart_version,
        }
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
