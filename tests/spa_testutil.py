"""Shared helpers for spa CLI tests (no agent envelope, PYTHONPATH=lib)."""

from __future__ import annotations

import itertools
import os
import re
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

INHERITED_PATH_VARS = (
    "SPA_HOME",
    "SPA_ENV_DIR",
    "SPA_VENV_DIR",
    "SPA_SOFTWARE_DIR",
    "SPA_BASECONFIG_DIR",
    "SPA_APPS_DIR",
    "SPLUNK_CONFIG_FILE",
    "ANSIBLE_CONFIG",
    "ANSIBLE_INVENTORY",
    "ANSIBLE_ROLES_PATH",
    "ANSIBLE_INVENTORY_PLUGINS",
    "ANSIBLE_LOOKUP_PLUGINS",
    "ANSIBLE_VARS_PLUGINS",
    "ANSIBLE_CACHE_PLUGIN_CONNECTION",
)


_MARK_KEYWORDS = frozenset({"and", "or", "not"})
_MARKER_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def satisfy_env_lookups(monkeypatch, start_dir: Optional[Path] = None) -> None:
    """Set empty config lookups to a placeholder so later command gates can run."""
    from spa.paths import resolve_spa_paths
    from spa.preflight import env_lookup_readiness, load_config_mapping

    paths = resolve_spa_paths(start_dir=start_dir)
    config_path = Path(paths.config_file)
    if not config_path.is_file():
        return
    for row in env_lookup_readiness(load_config_mapping(config_path)):
        if row["state"] != "set":
            monkeypatch.setenv(row["name"], "spa-test-value")


def selects_local_tests(markexpr: str) -> bool:
    """True when -m selects a test carrying the local marker."""
    from _pytest.mark.expression import Expression

    if "local" not in _MARKER_NAME.findall(markexpr):
        return False
    expression = Expression.compile(markexpr)
    others = list(dict.fromkeys(
        name
        for name in _MARKER_NAME.findall(markexpr)
        if name not in _MARK_KEYWORDS and name != "local"
    ))
    for bits in itertools.product((False, True), repeat=len(others)):
        enabled = {"local", *(name for name, bit in zip(others, bits) if bit)}

        def matches(name: str, /, enabled: set[str] = enabled, **kwargs: object) -> bool:
            return not kwargs and name in enabled

        if expression.evaluate(matches):
            return True
    return False


_THROWAWAY_XDG: Optional[str] = None
DEFAULT_SUBPROCESS_ENV: Mapping[str, str] = {}


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
    for name in (*AGENT_ENV_VARS, *INHERITED_PATH_VARS):
        env.pop(name, None)
    env["PYTHONPATH"] = str(LIB) + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    # Never let spa write the operator's ~/.config/spa (paths.yml, environments.yml).
    env.setdefault("XDG_CONFIG_HOME", _throwaway_xdg_config_home())
    if extra:
        env.update(extra)
    return env


def run_spa(args: Sequence[str], env=None, cwd=None, extra_env=None, stdin=None):
    full = spa_env(DEFAULT_SUBPROCESS_ENV)
    if extra_env:
        full.update(extra_env)
    if env:
        full.update(env)
    return subprocess.run(
        [sys.executable, str(SPA), *args],
        cwd=cwd or PROJECT_ROOT,
        capture_output=True,
        text=True,
        env=full,
        input=stdin,
    )


def run_spa_init(args: Sequence[str], env=None, cwd=None, extra_env=None):
    """Run spa init. Tests pass --provider aws unless they pass one, since init requires a provider."""
    argv = list(args)
    if "--skip-doctor" not in argv:
        argv.insert(0, "--skip-doctor")
    if "--provider" not in argv:
        argv[0:0] = ["--provider", "aws"]
    return run_spa(["init", *argv], env=env, cwd=cwd, extra_env=extra_env)
