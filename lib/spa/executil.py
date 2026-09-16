"""Apply resolved paths and locate ansible-playbook in the active venv."""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Dict, Optional

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


def venv_is_usable(path: Path) -> bool:
    return (path / "bin" / "activate").is_file()


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
        if candidate.is_dir() and not venv_is_usable(candidate):
            lines.append("Incomplete venv: %s (no bin/activate)" % candidate)
    lines.append("Create it:   %s --create" % (paths.spa_home / "bin" / "spa_venv.sh"))
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
