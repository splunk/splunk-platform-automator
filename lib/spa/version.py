"""Installed SPA version from SPA_HOME/VERSION, and GitHub compare for spa version check."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from spa.install_kind import classify_install_kind

DEFAULT_REPO = "splunk/splunk-platform-automator"
AUTH_ERROR = (
    "set --from FILE, or run gh auth login / set GITHUB_TOKEN to download a release."
)


class VersionError(RuntimeError):
    """GitHub latest-release resolution failed (offline or unauthenticated)."""


def read_local_version(spa_home: Path) -> str:
    """Return the stripped VERSION file for this framework tree."""
    return (Path(spa_home) / "VERSION").read_text(encoding="utf-8").strip()


def local_payload(spa_home: Path, spa_bin: Optional[str] = None) -> Dict[str, Any]:
    home = Path(spa_home).resolve()
    return {
        "version": read_local_version(home),
        "spa_home": str(home),
        "install_kind": classify_install_kind(home, spa_bin),
    }


def normalize_tag(tag: str) -> str:
    text = (tag or "").strip()
    if text[:1] in {"v", "V"}:
        return text[1:]
    return text


def format_version_text(data: Dict[str, Any]) -> str:
    version = data.get("version") or ""
    if "latest" not in data:
        return "spa %s\n" % version
    if data.get("outdated"):
        return "spa %s (latest is %s)\n" % (version, data.get("latest") or "")
    return "spa %s (up to date)\n" % version


def local_version(spa_home: Path, spa_bin: Optional[str] = None):
    from spa.api import CommandResult

    try:
        data = local_payload(spa_home, spa_bin)
    except OSError as exc:
        return CommandResult(ok=False, error=str(exc), code=1)
    if not data["version"]:
        return CommandResult(
            ok=False,
            error="VERSION is empty in %s" % spa_home,
            code=1,
        )
    return CommandResult(ok=True, data=data)


def _version_key(text: str) -> tuple:
    bits = []
    for part in normalize_tag(text).split("."):
        try:
            bits.append(int(part))
        except ValueError:
            bits.append(0)
    while len(bits) < 3:
        bits.append(0)
    return tuple(bits)


def _release_url(repo: str, tag: str) -> str:
    return "https://github.com/%s/releases/tag/%s" % (repo, tag)


def gh_ok() -> bool:
    if not shutil.which("gh"):
        return False
    try:
        result = subprocess.run(
            ["gh", "auth", "status", "-h", "github.com"],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return False
    return result.returncode == 0


def fetch_latest_release() -> Dict[str, str]:
    """Resolve GitHub latest tag the same way install.sh does (gh, else GITHUB_TOKEN)."""
    repo = (os.environ.get("SPA_REPO") or "").strip() or DEFAULT_REPO
    if gh_ok():
        try:
            result = subprocess.run(
                [
                    "gh",
                    "release",
                    "view",
                    "--repo",
                    repo,
                    "--json",
                    "tagName",
                    "-q",
                    ".tagName",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
        except OSError as exc:
            raise VersionError(AUTH_ERROR) from exc
        tag = (result.stdout or "").strip()
        if result.returncode != 0 or not tag:
            raise VersionError(AUTH_ERROR)
        return {"tag": tag, "url": _release_url(repo, tag)}
    token = (os.environ.get("GITHUB_TOKEN") or "").strip()
    if not token:
        raise VersionError(AUTH_ERROR)
    request = urllib.request.Request(
        "https://api.github.com/repos/%s/releases/latest" % repo,
        headers={
            "Authorization": "Bearer %s" % token,
            "Accept": "application/vnd.github+json",
            "User-Agent": "spa",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (OSError, ValueError, urllib.error.URLError) as exc:
        raise VersionError(AUTH_ERROR) from exc
    if not isinstance(payload, dict):
        raise VersionError(AUTH_ERROR)
    tag = str(payload.get("tag_name") or "").strip()
    if not tag:
        raise VersionError(AUTH_ERROR)
    url = str(payload.get("html_url") or "").strip() or _release_url(repo, tag)
    return {"tag": tag, "url": url}


def check_version(
    spa_home: Path,
    spa_bin: Optional[str] = None,
    fetch: Optional[Callable[..., Dict[str, str]]] = None,
):
    from spa.api import CommandResult
    from spa.next_steps import item

    try:
        local = local_payload(spa_home, spa_bin)
    except OSError as exc:
        return CommandResult(ok=False, error=str(exc), code=1)
    version = normalize_tag(local["version"])
    if not version:
        return CommandResult(
            ok=False,
            error="VERSION is empty in %s" % spa_home,
            code=1,
        )
    try:
        release = fetch() if fetch is not None else fetch_latest_release()
    except VersionError as exc:
        return CommandResult(ok=False, error=str(exc), code=1)
    tag = str((release or {}).get("tag") or "")
    latest = normalize_tag(tag)
    if not latest:
        return CommandResult(ok=False, error=AUTH_ERROR, code=1)
    outdated = _version_key(latest) > _version_key(version)
    data: Dict[str, Any] = {
        "version": version,
        "latest": latest,
        "outdated": outdated,
        "release_url": str((release or {}).get("url") or _release_url(DEFAULT_REPO, tag or latest)),
        "install_kind": local["install_kind"],
    }
    if outdated:
        data["next"] = [
            item(
                "self_update",
                "Update SPA from GitHub Releases?",
                "spa self update --yes",
            )
        ]
    return CommandResult(ok=True, data=data)
