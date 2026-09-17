"""Apply resolved paths and locate ansible-playbook in the active venv."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import threading
from functools import lru_cache
from importlib.util import find_spec
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from spa.paths import SpaPaths


def apply_paths_env(paths: SpaPaths, overwrite: bool = False) -> Dict[str, str]:
    exported = paths.export_env()
    for key, value in exported.items():
        if overwrite:
            os.environ[key] = value
        else:
            os.environ.setdefault(key, value)
    lib = str(paths.spa_home / "lib")
    py_path = os.environ.get("PYTHONPATH", "")
    if lib not in py_path.split(os.pathsep):
        os.environ["PYTHONPATH"] = lib + (os.pathsep + py_path if py_path else "")
    venv = resolve_venv_dir(paths)
    if venv is not None:
        collections = venv.parent / ".collections"
        if collections.is_dir():
            os.environ.setdefault("ANSIBLE_COLLECTIONS_PATH", str(collections))
    return exported


class ToolNotFound(RuntimeError):
    """A required binary is not installed (venv tool or host tool)."""


HOST_TOOLS = frozenset({"vagrant", "terraform", "VBoxManage"})


SPA_VENV_MODULES = ("yaml", "pydantic")


def venv_python(path: Path) -> Optional[Path]:
    for name in ("python3", "python"):
        candidate = path / "bin" / name
        if candidate.is_file():
            return candidate
    return None


@lru_cache(maxsize=None)
def _imports_spa_modules(python: str) -> bool:
    probe = "import %s" % ", ".join(SPA_VENV_MODULES)
    try:
        return subprocess.run([python, "-c", probe], capture_output=True).returncode == 0
    except OSError:
        return False


def venv_has_requirements(path: Path) -> bool:
    """A venv is only usable if it can import what spa and its subprocesses need.

    An activatable venv with a half-finished install (interrupted pip, or a
    leftover from another checkout pinned through SPA_VENV_DIR) would otherwise
    be selected for python3 / ansible and fail with ModuleNotFoundError. The
    site-packages check keeps the common case free of a subprocess; anything
    unusual (--system-site-packages, odd layouts) falls back to importing.
    """
    python = venv_python(path)
    if python is None:
        return False
    for site_packages in (path / "lib").glob("python*/site-packages"):
        if all((site_packages / name).is_dir() for name in SPA_VENV_MODULES):
            return True
    return _imports_spa_modules(str(python))


def venv_is_usable(path: Path) -> bool:
    if not (path / "bin" / "activate").is_file():
        return False
    return venv_has_requirements(path)


def venv_candidates(paths: SpaPaths) -> list:
    candidates = []
    explicit = (os.environ.get("SPA_VENV_DIR") or "").strip()
    if explicit:
        candidates.append(Path(explicit).expanduser().resolve())
    candidates.append(paths.spa_env_dir / ".venv")
    candidates.append(paths.spa_home / ".venv")
    seen = set()
    unique = []
    for candidate in candidates:
        if candidate not in seen:
            seen.add(candidate)
            unique.append(candidate)
    return unique


def resolve_venv_dir(paths: SpaPaths) -> Optional[Path]:
    """First *usable* venv: SPA_VENV_DIR, then the env, then SPA_HOME.

    A directory without bin/activate is a half-created venv. Skip it instead of
    pinning every later lookup to something broken.
    """
    for candidate in venv_candidates(paths):
        if venv_is_usable(candidate):
            return candidate
    return None


# Requirements.txt distributions, keyed by the module spa actually imports, so a
# ModuleNotFoundError can be reported as a venv problem instead of a traceback.
REQUIREMENT_DISTRIBUTIONS = {
    "yaml": "PyYAML",
    "pydantic": "pydantic",
    "jmespath": "jmespath",
    "lxml": "lxml",
    "boto3": "boto3",
    "ansible": "ansible",
}


def _candidate_state(candidate: Path) -> str:
    if not candidate.is_dir():
        return "not created"
    if not (candidate / "bin" / "activate").is_file():
        return "incomplete (no bin/activate)"
    if not venv_has_requirements(candidate):
        return "cannot import %s" % " / ".join(SPA_VENV_MODULES)
    return "ok"


def venv_setup_message(paths: SpaPaths, missing: Sequence[str]) -> str:
    """Explain which venv spa looked for and the exact command that fixes it."""
    names = [REQUIREMENT_DISTRIBUTIONS.get(name, name) for name in missing]
    lines = [
        "spa cannot run this command: %s %s not installed for %s."
        % (
            ", ".join(names),
            "is" if len(names) == 1 else "are",
            sys.executable or "this interpreter",
        ),
        "Ansible, Pydantic, and PyYAML come from the SPA venv, not the system Python.",
        "Venvs spa checked:",
    ]
    usable = None
    existing = None
    for candidate in venv_candidates(paths):
        state = _candidate_state(candidate)
        if state == "ok" and usable is None:
            usable = candidate
        elif state != "not created" and existing is None:
            existing = candidate
        lines.append("  %s  (%s)" % (candidate, state))
    target = usable or existing
    scope = "--shared"
    if target is not None and target == paths.spa_env_dir / ".venv":
        scope = "--environment"
    if usable is not None:
        # Compare venv roots, not interpreters: every venv's bin/python3 is a
        # symlink to the same base python, so realpath() would call them equal.
        running_on_it = Path(sys.prefix).resolve() == usable.resolve()
        if running_on_it:
            # That venv runs spa but is missing a lazily imported requirement.
            lines.append("Install requirements: spa venv %s --reinstall --yes" % scope)
        else:
            lines.append("That venv can run spa, but spa started on another interpreter.")
            lines.append("Run it through: %s" % (paths.spa_home / "bin" / "spa"))
    elif existing is not None:
        lines.append("Repair it:   spa venv %s --rebuild --yes" % scope)
    else:
        lines.append("Create it:   spa venv %s --create --yes" % scope)
    lines.append("Then check:  spa doctor")
    return "\n".join(lines)


def missing_spa_modules() -> list:
    """Required modules this interpreter cannot import (cheap: no imports)."""
    missing = []
    for name in SPA_VENV_MODULES:
        try:
            if find_spec(name) is None:
                missing.append(name)
        except (ImportError, ValueError):
            missing.append(name)
    return missing


def venv_required_error(paths: SpaPaths) -> Optional[str]:
    """Message when this interpreter cannot satisfy spa's venv requirements."""
    missing = missing_spa_modules()
    if not missing:
        return None
    return venv_setup_message(paths, missing)


def _missing_host_tool_message(name: str) -> str:
    """Vagrant/Terraform live on PATH, never in the SPA Python venv."""
    lines = [
        "%s is not on PATH." % name,
        "It is a host program, not part of the SPA Python venv.",
    ]
    if name == "vagrant":
        from spa.doctor import _vagrant_install_hint

        lines.append("Install:  %s" % _vagrant_install_hint())
    elif name == "terraform":
        from spa.doctor import _terraform_install_hint

        lines.append("Install:  %s" % _terraform_install_hint())
    elif name == "VBoxManage":
        from spa.doctor import _virtualbox_install_hint

        lines.append("Install:  %s" % _virtualbox_install_hint())
    lines.append("Then:     spa doctor")
    return "\n".join(lines)


def _missing_tool_message(paths: SpaPaths, name: str, venv: Optional[Path]) -> str:
    if name in HOST_TOOLS:
        return _missing_host_tool_message(name)
    lines = ["%s not found (not in a venv, not on PATH)." % name]
    if venv is not None:
        lines.append("Active venv: %s" % venv)
    for candidate in venv_candidates(paths):
        if not candidate.is_dir() or venv_is_usable(candidate):
            continue
        if (candidate / "bin" / "activate").is_file():
            lines.append(
                "Unusable venv: %s (cannot import %s)"
                % (candidate, " / ".join(SPA_VENV_MODULES))
            )
        else:
            lines.append("Incomplete venv: %s (no bin/activate)" % candidate)
    lines.append("Create it:   spa venv --shared --create --yes")
    lines.append("Repair it:   spa venv --shared --rebuild --yes")
    lines.append("Then check:  spa doctor")
    return "\n".join(lines)


def tool_path(paths: SpaPaths, name: str, required: bool = True) -> str:
    venv = None
    if name not in HOST_TOOLS:
        venv = resolve_venv_dir(paths)
        if venv is not None:
            candidate = venv / "bin" / name
            if candidate.is_file():
                return str(candidate)
    found = shutil.which(name)
    if found:
        return found
    if not required:
        return name
    raise ToolNotFound(_missing_tool_message(paths, name, venv))


VENV_PROGRESS_PREFIXES = (
    "Creating virtual environment",
    "Rebuilding virtual environment",
    "Recreating incomplete virtual environment",
    "Installing pip",
    "Installing packages",
    "Upgrading packages",
    "Installing Ansible collections",
    "Updating Ansible collections",
    "Ansible collections already installed",
)


def venv_progress_line(line: str) -> Optional[str]:
    """Map a spa_venv.sh progress/ready line to the human step, or None."""
    text = (line or "").strip()
    if not text:
        return None
    if text.startswith("Virtual environment ready:"):
        return text
    for prefix in VENV_PROGRESS_PREFIXES:
        if text == prefix or text.startswith(prefix):
            return prefix if text == prefix else (
                prefix + "..." if not text.endswith("...") else text
            )
    return None


def run_venv_script(
    cmd: Sequence[str],
    on_step: Optional[Callable[[str], None]] = None,
) -> Tuple[int, str, str, List[str]]:
    """Run spa_venv.sh, streaming progress steps while capturing the full log.

    Returns (returncode, stdout, log, progress). pip output stays in *log*;
    *stdout* is the success line (or --path result).
    """
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    env["PIP_PROGRESS_BAR"] = "off"
    proc = subprocess.Popen(
        list(cmd),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
        bufsize=1,
    )
    log_chunks: List[str] = []
    stdout_chunks: List[str] = []
    progress: List[str] = []
    lock = threading.Lock()

    def _handle(line: str, from_stdout: bool) -> None:
        with lock:
            log_chunks.append(line)
            text = line.strip()
            if from_stdout and text and (
                text.startswith("Virtual environment ready:") or " " not in text
            ):
                stdout_chunks.append(line)
            step = venv_progress_line(line)
            if step and step not in progress:
                progress.append(step)
                if on_step is not None:
                    on_step(step)

    def _read_stderr() -> None:
        assert proc.stderr is not None
        for line in proc.stderr:
            _handle(line, False)

    reader = threading.Thread(target=_read_stderr)
    reader.start()
    assert proc.stdout is not None
    for line in proc.stdout:
        _handle(line, True)
    reader.join()
    code = proc.wait()
    return code, "".join(stdout_chunks), "".join(log_chunks), progress
