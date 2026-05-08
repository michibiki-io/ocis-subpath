#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def parse_release_yaml(path: Path) -> dict[str, dict[str, str]]:
    data: dict[str, dict[str, str]] = {}
    current = ""
    for raw_line in path.read_text(encoding="utf-8").splitlines():
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


def parse_release_yaml_text(text: str) -> dict[str, dict[str, str]]:
    tmp = Path(os.getenv("RUNNER_TEMP", "/tmp")) / "release-yaml-parse.tmp"
    tmp.write_text(text, encoding="utf-8")
    try:
        return parse_release_yaml(tmp)
    finally:
        tmp.unlink(missing_ok=True)


def parse_chart_metadata_text(text: str) -> tuple[str, str]:
    version = ""
    app_version = ""
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if line.startswith("version:"):
            version = line.split(":", 1)[1].strip().strip('"').strip("'")
        if line.startswith("appVersion:"):
            app_version = line.split(":", 1)[1].strip().strip('"').strip("'")

    if not version:
        raise SystemExit("missing Chart.yaml value: version")
    if not app_version:
        raise SystemExit("missing Chart.yaml value: appVersion")
    return version, app_version


def chart_metadata(path: Path | None = None) -> tuple[str, str]:
    return parse_chart_metadata_text((path or ROOT / "charts/ocis-subpath/Chart.yaml").read_text(encoding="utf-8"))


def require(data: dict[str, dict[str, str]], section: str, key: str) -> str:
    value = data.get(section, {}).get(key, "")
    if not value:
        raise SystemExit(f"missing release.yaml value: {section}.{key}")
    return value


def bool_value(data: dict[str, dict[str, str]], section: str, key: str, default: bool) -> str:
    value = data.get(section, {}).get(key, "")
    if value == "":
        return "true" if default else "false"
    normalized = value.lower()
    if normalized in {"true", "yes", "1", "on"}:
        return "true"
    if normalized in {"false", "no", "0", "off"}:
        return "false"
    raise SystemExit(f"invalid boolean release.yaml value: {section}.{key}")


def bool_or_auto(data: dict[str, dict[str, str]], section: str, key: str) -> str:
    value = data.get(section, {}).get(key, "")
    if value == "":
        return "auto"
    normalized = value.lower()
    if normalized == "auto":
        return "auto"
    if normalized in {"true", "yes", "1", "on"}:
        return "true"
    if normalized in {"false", "no", "0", "off"}:
        return "false"
    raise SystemExit(f"invalid boolean release.yaml value: {section}.{key}")


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def changed_files(base_sha: str, head_sha: str) -> list[str]:
    if not base_sha or not head_sha:
        return []
    output = git("diff", "--name-only", f"{base_sha}..{head_sha}")
    return [line for line in output.splitlines() if line]


def release_yaml_at(sha: str) -> dict[str, dict[str, str]] | None:
    if not sha:
        return None
    try:
        text = git("show", f"{sha}:release.yaml")
    except subprocess.CalledProcessError:
        return None
    return parse_release_yaml_text(text)


def chart_metadata_at(sha: str) -> tuple[str, str] | None:
    if not sha:
        return None
    try:
        text = git("show", f"{sha}:charts/ocis-subpath/Chart.yaml")
    except subprocess.CalledProcessError:
        return None
    return parse_chart_metadata_text(text)


def tag_exists(tag: str) -> bool:
    try:
        git("rev-parse", "-q", "--verify", f"refs/tags/{tag}")
    except subprocess.CalledProcessError:
        return False
    return True


def github_release_exists(tag: str) -> bool | None:
    repo = os.getenv("GITHUB_REPOSITORY", "")
    token = os.getenv("GITHUB_TOKEN", "")
    if not repo or not token:
        return None

    api_url = os.getenv("GITHUB_API_URL", "https://api.github.com").rstrip("/")
    encoded_tag = urllib.parse.quote(tag, safe="")
    request = urllib.request.Request(
        f"{api_url}/repos/{repo}/releases/tags/{encoded_tag}",
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=15):
            return True
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return False
        raise


def release_artifact_exists(tag: str) -> bool:
    release_exists = github_release_exists(tag)
    if release_exists is not None:
        return release_exists
    return tag_exists(tag)


def section_changed(
    current: dict[str, dict[str, str]],
    previous: dict[str, dict[str, str]] | None,
    section: str,
    keys: set[str],
) -> bool:
    if previous is None:
        return False
    return any(current.get(section, {}).get(key, "") != previous.get(section, {}).get(key, "") for key in keys)


def matches_any(path: str, prefixes: tuple[str, ...], exact: tuple[str, ...] = ()) -> bool:
    return path in exact or any(path.startswith(prefix) for prefix in prefixes)


def auto_targets(
    current: dict[str, dict[str, str]],
    previous: dict[str, dict[str, str]] | None,
    files: list[str],
    missing_releases: dict[str, bool] | None = None,
    chart_changed: bool = False,
) -> dict[str, str]:
    missing_releases = missing_releases or {}
    ocis = any(matches_any(path, ("images/ocis-subpath/",), ()) for path in files)
    ocis = ocis or section_changed(current, previous, "ocis", {"upstreamRef", "imageTag", "repo"})
    ocis = ocis or missing_releases.get("ocis", False)

    patcher = any(
        matches_any(path, ("images/web-assets-patcher/",), ("scripts/build-patcher-image.sh",))
        for path in files
    )
    patcher = patcher or section_changed(current, previous, "web", {"upstreamRef", "repo"})
    patcher = patcher or section_changed(current, previous, "patcher", {"imageTag"})
    patcher = patcher or missing_releases.get("patcher", False)

    chart = any(matches_any(path, ("charts/ocis-subpath/",), ()) for path in files)
    chart = chart or section_changed(current, previous, "chart", {"version", "appVersion"})
    chart = chart or chart_changed
    chart = chart or missing_releases.get("chart", False)

    return {
        "release_ocis": "true" if ocis else "false",
        "release_patcher": "true" if patcher else "false",
        "release_chart": "true" if chart else "false",
    }


def resolve_targets(
    current: dict[str, dict[str, str]],
    previous: dict[str, dict[str, str]] | None,
    files: list[str],
    has_diff_context: bool,
    missing_releases: dict[str, bool] | None = None,
    chart_changed: bool = False,
) -> dict[str, str]:
    if not has_diff_context:
        return {
            "release_ocis": bool_value(current, "release", "ocis", True),
            "release_patcher": bool_value(current, "release", "patcher", True),
            "release_chart": bool_value(current, "release", "chart", True),
        }

    computed = auto_targets(current, previous, files, missing_releases, chart_changed)
    overrides = {
        "release_ocis": bool_or_auto(current, "release", "ocis"),
        "release_patcher": bool_or_auto(current, "release", "patcher"),
        "release_chart": bool_or_auto(current, "release", "chart"),
    }
    return {key: computed[key] if override == "auto" else override for key, override in overrides.items()}


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
    parser.add_argument("--file", default=str(ROOT / "release.yaml"))
    parser.add_argument("--base-sha", default="")
    parser.add_argument("--head-sha", default="")
    args = parser.parse_args()

    data = parse_release_yaml(Path(args.file))
    files = changed_files(args.base_sha, args.head_sha)
    previous = release_yaml_at(args.base_sha) if args.base_sha else None
    current_chart_version, current_chart_app_version = chart_metadata()
    previous_chart = chart_metadata_at(args.base_sha) if args.base_sha else None
    chart_changed = previous_chart is not None and previous_chart != (current_chart_version, current_chart_app_version)
    ocis_image_tag = require(data, "ocis", "imageTag")
    patcher_image_tag = require(data, "patcher", "imageTag")
    ocis_git_tag = f"ocis/v{ocis_image_tag}"
    patcher_git_tag = f"patcher/{patcher_image_tag}"
    chart_git_tag = f"chart/v{current_chart_version}"
    missing_releases = {
        "ocis": not release_artifact_exists(ocis_git_tag),
        "patcher": not release_artifact_exists(patcher_git_tag),
        "chart": not release_artifact_exists(chart_git_tag),
    }
    targets = resolve_targets(data, previous, files, bool(args.base_sha and args.head_sha), missing_releases, chart_changed)

    write_outputs(
        {
            **targets,
            "ocis_ref": require(data, "ocis", "upstreamRef"),
            "ocis_repo": data.get("ocis", {}).get("repo", "https://github.com/owncloud/ocis.git"),
            "ocis_image_tag": ocis_image_tag,
            "ocis_git_tag": ocis_git_tag,
            "web_ref": require(data, "web", "upstreamRef"),
            "web_repo": data.get("web", {}).get("repo", "https://github.com/owncloud/web.git"),
            "patcher_image_tag": patcher_image_tag,
            "patcher_git_tag": patcher_git_tag,
            "chart_version": current_chart_version,
            "chart_app_version": current_chart_app_version,
            "chart_git_tag": chart_git_tag,
        }
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
