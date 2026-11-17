"""Installed SPA version from SPA_HOME/VERSION, GitHub compare, and prefix self-update."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Sequence

from spa.install_kind import classify_install_kind

DEFAULT_REPO = "splunk/splunk-platform-automator"
AUTH_ERROR = (
    "set --from FILE, or run gh auth login / set GITHUB_TOKEN to download a release."
)
CLONE_ERROR = (
    "This SPA install is a git checkout (install_kind=clone). "
    "spa self update replaces a prefix and would delete .git.\n"
    "Update with git pull, then spa venv upgrade --shared --yes "
    "(or spa venv rebuild --shared --yes) and spa skills update."
)
UNKNOWN_ERROR = (
    "This SPA install is not a prefix wrapper (install_kind=unknown). "
    "Run spa doctor."
)
InstallRunner = Callable[[Sequence[str]], int]


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
    previous = data.get("previous")
    if previous:
        return "spa %s (was %s)\n" % (version, previous)
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


def _install_runner(argv: Sequence[str], *, agent: bool = False) -> int:
    """Run install.sh. Agent mode captures stdio so the JSON envelope stays alone."""
    result = subprocess.run(list(argv), check=False, capture_output=True, text=True)
    if not agent:
        import sys

        if result.stdout:
            sys.stderr.write(result.stdout)
        if result.stderr:
            sys.stderr.write(result.stderr)
    return result.returncode


def _release_tag(version: Optional[str]) -> str:
    text = (version or "").strip()
    if not text:
        return ""
    if text[:1] in {"v", "V"}:
        return "v" + text[1:]
    return "v" + text


def fetch_install_script(dest_dir: Path, version: Optional[str] = None) -> Path:
    """Download the chosen release's install.sh into dest_dir."""
    repo = (os.environ.get("SPA_REPO") or "").strip() or DEFAULT_REPO
    dest = Path(dest_dir) / "install.sh"
    tag = _release_tag(version)
    if gh_ok():
        if not tag:
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
        try:
            result = subprocess.run(
                [
                    "gh",
                    "release",
                    "download",
                    tag,
                    "--repo",
                    repo,
                    "--pattern",
                    "install.sh",
                    "-D",
                    str(dest_dir),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
        except OSError as exc:
            raise VersionError(AUTH_ERROR) from exc
        if result.returncode != 0 or not dest.is_file():
            raise VersionError(AUTH_ERROR)
        dest.chmod(0o755)
        return dest
    token = (os.environ.get("GITHUB_TOKEN") or "").strip()
    if not token:
        raise VersionError(AUTH_ERROR)
    if tag:
        url = "https://github.com/%s/releases/download/%s/install.sh" % (repo, tag)
    else:
        url = "https://github.com/%s/releases/latest/download/install.sh" % repo
    request = urllib.request.Request(
        url,
        headers={
            "Authorization": "Bearer %s" % token,
            "Accept": "application/octet-stream",
            "User-Agent": "spa",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            dest.write_bytes(response.read())
    except (OSError, urllib.error.URLError) as exc:
        raise VersionError(AUTH_ERROR) from exc
    dest.chmod(0o755)
    return dest


def _wrapper_bindir(spa_bin: Optional[str]) -> Optional[str]:
    path = spa_bin
    if not path:
        path = shutil.which("spa")
    if not path:
        return None
    return str(Path(path).expanduser().parent)


def _self_update_next(*, skills_error: bool, recorded: bool):
    from spa.next_steps import item

    if skills_error:
        return [
            item(
                "skills_update",
                "Refresh recorded IDE skill copies from the new prefix?",
                "spa skills update",
            )
        ]
    rows = []
    if not recorded:
        rows.append(
            item(
                "skills_install",
                "Install SPA skills into an IDE?",
                "spa skills install",
            )
        )
    rows.append(
        item(
            "doctor",
            "Check this controller after the prefix replace?",
            "spa doctor",
        )
    )
    return rows


def self_update(
    spa_home: Path,
    *,
    spa_bin: Optional[str] = None,
    version: Optional[str] = None,
    confirm: bool = False,
    agent: bool = False,
    runner: Optional[InstallRunner] = None,
    script: Optional[Path] = None,
    skills_update: Optional[Callable[..., Dict[str, Any]]] = None,
    config_dir: Optional[Path] = None,
    home: Optional[Path] = None,
):
    """Replace a prefix install from GitHub Releases, then refresh recorded skills."""
    from spa.api import CommandResult
    from spa.confirm import ConfirmationError, ConfirmationUsageError, ensure_confirmed
    from spa.skills import SkillsError, update_skills as default_skills_update

    try:
        previous = read_local_version(spa_home)
        kind = classify_install_kind(spa_home, spa_bin)
    except OSError as exc:
        return CommandResult(ok=False, error=str(exc), code=1)
    if kind == "clone":
        return CommandResult(ok=False, error=CLONE_ERROR, code=1)
    if kind != "prefix":
        return CommandResult(ok=False, error=UNKNOWN_ERROR, code=1)
    try:
        ensure_confirmed(
            "spa self update",
            confirm=confirm,
            agent=agent,
            risk="self_update",
        )
    except ConfirmationUsageError as exc:
        return CommandResult(ok=False, error=str(exc), code=2)
    except ConfirmationError as exc:
        return CommandResult(ok=False, error=str(exc), code=1)
    bindir = _wrapper_bindir(spa_bin)
    if not bindir:
        return CommandResult(ok=False, error=UNKNOWN_ERROR, code=1)
    prefix = str(Path(spa_home).resolve())
    tmp = None
    script_path = Path(script) if script is not None else None
    try:
        if script_path is None:
            tmp = Path(tempfile.mkdtemp(prefix="spa-self-update-"))
            try:
                script_path = fetch_install_script(tmp, version)
            except VersionError as exc:
                return CommandResult(ok=False, error=str(exc), code=1)
        argv = [
            str(script_path),
            "--force",
            "--prefix",
            prefix,
            "--bindir",
            bindir,
        ]
        if version:
            argv.extend(["--version", str(version)])
        run = runner or (lambda command: _install_runner(command, agent=agent))
        rc = run(argv)
    finally:
        if tmp is not None:
            shutil.rmtree(tmp, ignore_errors=True)
    if rc != 0:
        return CommandResult(
            ok=False,
            error="install.sh --force failed (exit %s)" % rc,
            code=1,
        )
    try:
        new_version = read_local_version(spa_home)
    except OSError as exc:
        return CommandResult(ok=False, error=str(exc), code=1)
    updater = skills_update if skills_update is not None else default_skills_update
    skills_error = False
    skills_payload: Dict[str, Any]
    try:
        skills_data = updater(
            source=Path(spa_home) / "skills" / "spa",
            home=Path(home) if home is not None else Path(os.environ.get("HOME") or str(Path.home())),
            environ=os.environ,
            config_dir=config_dir,
        )
        skills_payload = {
            "updated": list((skills_data or {}).get("updated") or []),
            "unchanged": list((skills_data or {}).get("unchanged") or []),
            "platforms": list((skills_data or {}).get("platforms") or []),
        }
    except (SkillsError, OSError) as exc:
        skills_error = True
        skills_payload = {"error": str(exc)}
    recorded = bool(skills_payload.get("platforms"))
    data: Dict[str, Any] = {
        "version": new_version,
        "previous": previous,
        "spa_home": prefix,
        "install_kind": kind,
        "skills": skills_payload,
        "next": _self_update_next(skills_error=skills_error, recorded=recorded),
    }
    return CommandResult(ok=True, data=data)
