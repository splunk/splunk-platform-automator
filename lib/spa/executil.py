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


def resolve_venv_dir(paths: SpaPaths) -> Optional[Path]:
    explicit = (os.environ.get("SPA_VENV_DIR") or "").strip()
    if explicit:
        return Path(explicit).expanduser().resolve()
    env_venv = paths.spa_env_dir / ".venv"
    if (env_venv / "bin" / "activate").is_file():
        return env_venv
    home_venv = paths.spa_home / ".venv"
    if (home_venv / "bin" / "activate").is_file():
        return home_venv
    return None


def tool_path(paths: SpaPaths, name: str) -> str:
    venv = resolve_venv_dir(paths)
    if venv is not None:
        candidate = venv / "bin" / name
        if candidate.is_file():
            return str(candidate)
    found = shutil.which(name)
    return found or name
