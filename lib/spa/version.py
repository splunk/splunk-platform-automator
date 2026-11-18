"""Installed SPA version from SPA_HOME/VERSION, GitHub compare, and prefix self-update."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Sequence, Tuple

from spa.install_kind import classify_install_kind, installer_wrapper_home

DEFAULT_REPO = "splunk/splunk-platform-automator"
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
USER_CONTENT_DIRS = (
    ("Software", "--software-dir"),
    ("Baseconfigs", "--baseconfig-dir"),
    ("Apps", "--apps-dir"),
    ("Envs", "--env-dir"),
)
INSTALL_TAIL_LINES = 20
InstallRunner = Callable[[Sequence[str]], Tuple[int, str]]


class VersionError(RuntimeError):
    """GitHub latest-release resolution failed (offline or rate-limited)."""


def offline_error(repo: str) -> str:
    return (
        "Could not reach GitHub releases for %s (offline or rate limit). "
        "Retry spa version check later; set GITHUB_TOKEN to raise the API rate limit." % repo
    )


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


def fetch_latest_release() -> Dict[str, str]:
    """Resolve GitHub latest tag the same way install.sh does (curl/API; GITHUB_TOKEN optional)."""
    repo = (os.environ.get("SPA_REPO") or "").strip() or DEFAULT_REPO
    error = offline_error(repo)
    request = urllib.request.Request(
        "https://api.github.com/repos/%s/releases/latest" % repo,
        headers={"Accept": "application/vnd.github+json", "User-Agent": "spa"},
    )
    token = (os.environ.get("GITHUB_TOKEN") or "").strip()
    if token:
        # Unredirected: urllib copies ordinary headers onto redirect targets.
        request.add_unredirected_header("Authorization", "Bearer %s" % token)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (OSError, ValueError, urllib.error.URLError) as exc:
        raise VersionError(error) from exc
    if not isinstance(payload, dict):
        raise VersionError(error)
    tag = str(payload.get("tag_name") or "").strip()
    if not tag:
        raise VersionError(error)
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
        repo = (os.environ.get("SPA_REPO") or "").strip() or DEFAULT_REPO
        return CommandResult(ok=False, error=offline_error(repo), code=1)
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


def _install_runner(argv: Sequence[str], *, agent: bool = False) -> Tuple[int, str]:
    """Run install.sh. Humans see it live on stderr; agents get the captured output."""
    if agent:
        result = subprocess.run(
            list(argv),
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        return result.returncode, result.stdout or ""
    sys.stdout.flush()
    sys.stderr.flush()
    # stdout goes to fd 2 so the version line stays the only thing on stdout.
    result = subprocess.run(list(argv), check=False, stdout=2)
    return result.returncode, ""


def _bootstrap_command() -> str:
    repo = (os.environ.get("SPA_REPO") or "").strip() or DEFAULT_REPO
    return (
        "curl -fsSL https://github.com/%s/releases/latest/download/install.sh "
        "| sh -s -- --force" % repo
    )


def _user_content_error(spa_home: Path) -> Optional[str]:
    # Match case-insensitively: older layouts used baseconfigs/ and apps/, and Linux is case-sensitive.
    try:
        entries = sorted(entry.name for entry in Path(spa_home).iterdir())
    except OSError:
        entries = []
    for name, flag in USER_CONTENT_DIRS:
        for entry in entries:
            if entry.lower() != name.lower():
                continue
            path = Path(spa_home) / entry
            return (
                "%s is inside SPA_HOME; spa self update replaces SPA_HOME and would delete it.\n"
                "Move it outside SPA_HOME and point spa at it with "
                "spa environment set %s DIR, then rerun spa self update."
                % (path, flag)
            )
    return None


def _install_failed_error(rc: int, output: str, spa_home: Path) -> str:
    from spa.runlog import redact

    lines = ["install.sh --force failed (exit %s)." % rc]
    tail = (output or "").rstrip("\n").splitlines()[-INSTALL_TAIL_LINES:]
    if tail:
        lines.append(str(redact("\n".join(tail))))
    if not (Path(spa_home) / "bin" / "spa").exists():
        lines.append(
            "%s is incomplete. Reinstall SPA with: %s" % (spa_home, _bootstrap_command())
        )
    return "\n".join(lines)


def _preload_result_modules() -> None:
    """Import everything the result and render path needs before SPA_HOME is replaced."""
    import spa.api  # noqa: F401
    import spa.confirm  # noqa: F401
    import spa.next_steps  # noqa: F401
    import spa.paths  # noqa: F401
    import spa.runlog  # noqa: F401
    import spa.skills  # noqa: F401


def _wrapper_bindir(spa_bin: Optional[str]) -> Optional[str]:
    path = spa_bin
    if not path:
        path = shutil.which("spa")
    if not path:
        return None
    return str(Path(path).expanduser().parent)


def _wrapper_prefix(spa_bin: Optional[str]) -> Optional[str]:
    """SPA_HOME exactly as the install.sh wrapper wrote it, so install.sh rewrites the same path."""
    path = spa_bin or shutil.which("spa")
    if not path:
        return None
    try:
        text = Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    home = installer_wrapper_home(text)
    return str(home) if home is not None else None


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
    from_file: Optional[str] = None,
    confirm: bool = False,
    agent: bool = False,
    runner: Optional[InstallRunner] = None,
    skills_update: Optional[Callable[..., Dict[str, Any]]] = None,
    config_dir: Optional[Path] = None,
    home: Optional[Path] = None,
):
    """Replace a prefix install with the prefix's own install.sh, then refresh recorded skills."""
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
    content_error = _user_content_error(spa_home)
    if content_error:
        return CommandResult(ok=False, error=content_error, code=1)
    install_sh = Path(spa_home) / "install.sh"
    if not install_sh.is_file():
        return CommandResult(
            ok=False,
            error="%s is missing. Reinstall SPA with: %s" % (install_sh, _bootstrap_command()),
            code=1,
        )
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
    resolved_home = str(Path(spa_home).resolve())
    prefix = _wrapper_prefix(spa_bin) or resolved_home
    _preload_result_modules()
    tmp = Path(tempfile.mkdtemp(prefix="spa-self-update-"))
    try:
        script_path = tmp / "install.sh"
        try:
            shutil.copy2(install_sh, script_path)
        except OSError as exc:
            return CommandResult(ok=False, error=str(exc), code=1)
        script_path.chmod(0o755)
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
        if from_file:
            argv.extend(["--from", os.path.abspath(os.path.expanduser(from_file))])
        run = runner or (lambda command: _install_runner(command, agent=agent))
        rc, output = run(argv)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    if rc != 0:
        return CommandResult(
            ok=False,
            error=_install_failed_error(rc, output, Path(spa_home)),
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
            "removed": list((skills_data or {}).get("removed") or []),
            "platforms": list((skills_data or {}).get("platforms") or []),
        }
    except (SkillsError, OSError) as exc:
        skills_error = True
        skills_payload = {"error": str(exc)}
    recorded = bool(skills_payload.get("platforms"))
    data: Dict[str, Any] = {
        "version": new_version,
        "previous": previous,
        "spa_home": resolved_home,
        "install_kind": kind,
        "skills": skills_payload,
        "next": _self_update_next(skills_error=skills_error, recorded=recorded),
    }
    return CommandResult(ok=True, data=data)
