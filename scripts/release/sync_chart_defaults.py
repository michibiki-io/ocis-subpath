#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import re
import subprocess
from pathlib import Path
from typing import Callable


ROOT = Path(__file__).resolve().parents[2]
VERSION_PATTERN = re.compile(r"^([0-9]+)\.([0-9]+)\.([0-9]+)$")


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


def parse_release_yaml_text(text: str) -> dict[str, dict[str, str]]:
    data: dict[str, dict[str, str]] = {}
    current = ""
    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        if not line or line.lstrip().startswith("#"):
            continue
        if not line.startswith(" ") and line.endswith(":"):
            current = line[:-1]
            data[current] = {}
            continue
        if current and line.startswith("  ") and ":" in line:
            key, value = line.strip().split(":", 1)
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
                value = value[1:-1]
            data[current][key] = value
            continue
        raise SystemExit(f"unsupported release.yaml line: {raw_line}")
    return data


def parse_release_yaml(path: Path) -> dict[str, dict[str, str]]:
    return parse_release_yaml_text(path.read_text(encoding="utf-8"))


def require_release_value(data: dict[str, dict[str, str]], section: str, key: str) -> str:
    value = data.get(section, {}).get(key, "")
    if not value:
        raise SystemExit(f"missing release.yaml value: {section}.{key}")
    return value


def release_default_tags(data: dict[str, dict[str, str]]) -> tuple[str, str, str]:
    ocis_tag = require_release_value(data, "ocis", "imageTag")
    patcher_tag = require_release_value(data, "patcher", "imageTag")
    return ocis_tag, patcher_tag, f"ocis-{ocis_tag}"


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

    if not root_image_tag:
        raise SystemExit("missing charts/ocis-subpath/values.yaml value: image.tag")
    if not patcher_image_tag:
        raise SystemExit("missing charts/ocis-subpath/values.yaml value: webAssetsPatcher.image.tag")
    return root_image_tag, patcher_image_tag


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


def read_chart_metadata(text: str) -> tuple[str, str]:
    version = ""
    app_version = ""
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if line.startswith("version:"):
            version = line.split(":", 1)[1].strip().strip('"').strip("'")
        if line.startswith("appVersion:"):
            app_version = line.split(":", 1)[1].strip().strip('"').strip("'")

    if not version:
        raise SystemExit("missing charts/ocis-subpath/Chart.yaml value: version")
    if not app_version:
        raise SystemExit("missing charts/ocis-subpath/Chart.yaml value: appVersion")
    return version, app_version


def bump_patch_version(version: str) -> str:
    match = VERSION_PATTERN.match(version)
    if not match:
        raise SystemExit("chart version must look like 0.2.0")
    major, minor, patch = map(int, match.groups())
    return f"{major}.{minor}.{patch + 1}"


def update_chart_metadata(text: str, version: str, app_version: str) -> str:
    text = replace_once(r'^version:\s*"?[0-9]+\.[0-9]+\.[0-9]+"?', f"version: {version}", text, "chart version")
    return replace_once(r'^appVersion:\s*"?[^"\n]+"?', f'appVersion: "{app_version}"', text, "chart appVersion")


def chart_default_mismatches(
    release_data: dict[str, dict[str, str]],
    values_text: str,
    chart_text: str,
) -> list[str]:
    release_ocis_tag, release_patcher_tag, expected_app_version = release_default_tags(release_data)
    values_ocis_tag, values_patcher_tag = read_values_tags(values_text)
    _chart_version, chart_app_version = read_chart_metadata(chart_text)
    mismatches: list[str] = []

    if values_ocis_tag != release_ocis_tag:
        mismatches.append(
            "charts/ocis-subpath/values.yaml image.tag "
            f"is {values_ocis_tag!r}, but release.yaml ocis.imageTag is {release_ocis_tag!r}"
        )
    if values_patcher_tag != release_patcher_tag:
        mismatches.append(
            "charts/ocis-subpath/values.yaml webAssetsPatcher.image.tag "
            f"is {values_patcher_tag!r}, but release.yaml patcher.imageTag is {release_patcher_tag!r}"
        )
    if chart_app_version != expected_app_version:
        mismatches.append(
            "charts/ocis-subpath/Chart.yaml appVersion "
            f"is {chart_app_version!r}, but expected {expected_app_version!r}"
        )
    return mismatches


def git_show(ref: str, path: Path) -> str:
    repo_path = str(path.resolve().relative_to(ROOT))
    return subprocess.check_output(["git", "show", f"{ref}:{repo_path}"], cwd=ROOT, text=True)


def default_state(values_text: str, chart_text: str) -> tuple[str, str, str]:
    values_ocis_tag, values_patcher_tag = read_values_tags(values_text)
    _chart_version, chart_app_version = read_chart_metadata(chart_text)
    return values_ocis_tag, values_patcher_tag, chart_app_version


def chart_version_mismatches_for_base(base_ref: str, values_path: Path, chart_path: Path) -> list[str]:
    if not base_ref:
        return []

    try:
        base_values = git_show(base_ref, values_path)
        base_chart = git_show(base_ref, chart_path)
    except (subprocess.CalledProcessError, ValueError):
        return []

    current_values = values_path.read_text(encoding="utf-8")
    current_chart = chart_path.read_text(encoding="utf-8")
    base_version, _base_app_version = read_chart_metadata(base_chart)
    current_version, _current_app_version = read_chart_metadata(current_chart)

    if default_state(base_values, base_chart) != default_state(current_values, current_chart) and current_version == base_version:
        return [
            "charts/ocis-subpath/Chart.yaml version must change when chart default image tags or appVersion change"
        ]
    return []


def format_mismatches(mismatches: list[str]) -> str:
    return "release.yaml and Helm chart defaults are out of sync:\n" + "\n".join(
        f"- {mismatch}" for mismatch in mismatches
    )


def sync_chart_defaults(
    release_path: Path,
    values_path: Path,
    chart_path: Path,
    *,
    check: bool = False,
    base_ref: str = "",
) -> dict[str, str]:
    release_data = parse_release_yaml(release_path)
    release_ocis_tag, release_patcher_tag, expected_app_version = release_default_tags(release_data)
    values_text = values_path.read_text(encoding="utf-8")
    chart_text = chart_path.read_text(encoding="utf-8")
    current_chart_version, current_app_version = read_chart_metadata(chart_text)
    mismatches = chart_default_mismatches(release_data, values_text, chart_text)
    if check:
        mismatches.extend(chart_version_mismatches_for_base(base_ref, values_path, chart_path))
        if mismatches:
            raise SystemExit(format_mismatches(mismatches))

    changed = bool(mismatches)
    next_chart_version = current_chart_version
    if changed and not check:
        values_path.write_text(update_values_tags(values_text, release_ocis_tag, release_patcher_tag), encoding="utf-8")
        next_chart_version = bump_patch_version(current_chart_version)
        chart_path.write_text(
            update_chart_metadata(chart_text, next_chart_version, expected_app_version),
            encoding="utf-8",
        )
        current_app_version = expected_app_version

    return {
        "changed": "true" if changed else "false",
        "ocis_image_tag": release_ocis_tag,
        "patcher_image_tag": release_patcher_tag,
        "chart_version": next_chart_version,
        "chart_app_version": current_app_version,
    }


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
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--base-ref", default="")
    parser.add_argument("--release-yaml", default=str(ROOT / "release.yaml"))
    parser.add_argument("--values-yaml", default=str(ROOT / "charts/ocis-subpath/values.yaml"))
    parser.add_argument("--chart-yaml", default=str(ROOT / "charts/ocis-subpath/Chart.yaml"))
    args = parser.parse_args()

    result = sync_chart_defaults(
        Path(args.release_yaml).resolve(),
        Path(args.values_yaml).resolve(),
        Path(args.chart_yaml).resolve(),
        check=args.check,
        base_ref=args.base_ref,
    )
    write_outputs(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
