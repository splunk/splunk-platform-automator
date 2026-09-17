"""Shared helpers for spa CLI tests (no agent envelope, PYTHONPATH=lib)."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Mapping, Optional, Sequence

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SPA = PROJECT_ROOT / "bin" / "spa"
LIB = PROJECT_ROOT / "lib"

AGENT_ENV_VARS = (
    "SPA_AGENT",
    "CLAUDECODE",
    "CLAUDE_CODE",
    "CURSOR_AGENT",
    "CURSOR_TRACE_ID",
    "CODEX_THREAD_ID",
)


_THROWAWAY_XDG: Optional[str] = None


def _throwaway_xdg_config_home() -> str:
    """Fallback user config dir when the caller did not isolate one."""
    global _THROWAWAY_XDG
    if _THROWAWAY_XDG is None:
        _THROWAWAY_XDG = tempfile.mkdtemp(prefix="spa-test-xdg-")
    return _THROWAWAY_XDG


def write_min_env(root: Path) -> Path:
    """Empty env dir with .spa.yml pointing at this checkout (not clone-equal)."""
    env = Path(root)
    env.mkdir(parents=True, exist_ok=True)
    (env / ".spa.yml").write_text("spa_home: %s\n" % PROJECT_ROOT, encoding="utf-8")
    (env / "config").mkdir(exist_ok=True)
    (env / "inventory").mkdir(exist_ok=True)
    return env


def min_env_vars(root: Path) -> dict:
    dest = write_min_env(root)
    return {
        "SPA_HOME": str(PROJECT_ROOT),
        "SPA_ENV_DIR": str(dest),
    }


def seed_software_dir(root: Path) -> Path:
    """Minimal PS baseconfig layout so controller-data checks pass in tests."""
    software = Path(root) / "Software"
    for name in ("org_ds_secure_server", "org_cluster_manager_base"):
        (software / "ps" / name).mkdir(parents=True, exist_ok=True)
    return software


def spa_env(extra: Optional[Mapping[str, str]] = None) -> dict:
    env = os.environ.copy()
    for name in AGENT_ENV_VARS:
        env.pop(name, None)
    env["PYTHONPATH"] = str(LIB) + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    # Never let spa write the operator's ~/.config/spa (paths.yml, environments.yml).
    env.setdefault("XDG_CONFIG_HOME", _throwaway_xdg_config_home())
    if extra:
        env.update(extra)
    return env


def run_spa(args: Sequence[str], env=None, cwd=None, extra_env=None):
    full = spa_env(extra_env)
    if env:
        full.update(env)
    return subprocess.run(
        [sys.executable, str(SPA), *args],
        cwd=cwd or PROJECT_ROOT,
        capture_output=True,
        text=True,
        env=full,
    )


def run_spa_init(args: Sequence[str], env=None, cwd=None, extra_env=None):
    argv = list(args)
    if "--skip-doctor" not in argv:
        argv.insert(0, "--skip-doctor")
    return run_spa(["init", *argv], env=env, cwd=cwd, extra_env=extra_env)
