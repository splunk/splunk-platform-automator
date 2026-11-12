"""Shared helpers for spa CLI tests (no agent envelope, PYTHONPATH=lib)."""

from __future__ import annotations

import ast
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


def worker_local_dir(base: Path) -> Path:
    """Per-xdist-worker subdirectory so parallel tests do not share temp files."""
    worker = os.environ.get("PYTEST_XDIST_WORKER") or "master"
    return Path(base) / worker


def xdist_group_name(params: Mapping) -> Optional[str]:
    """xdist loadgroup name so related parametrized tests share a worker."""
    if "config_file" in params:
        return os.path.splitext(str(params["config_file"]))[0]
    scenario = params.get("scenario_scope_result")
    if scenario:
        return f"app_scope_{scenario}"
    return None


_MARK_KEYWORDS = frozenset({"and", "or", "not"})
_MARKER_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
LOCAL_JOB_MARKEXPRS = (
    "local and cli",
    "local and ansible",
    "local and not cli and not ansible",
)
PLAYBOOK_SPAWNING_MODULES = (
    "test_app_scope_scenarios.py",
    "test_app_deployment.py",
    "test_spa_jsonl_callback.py",
    "test_env_scaffold.py",
)


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


def matching_local_job_markexprs(markers: Sequence[str]) -> tuple[str, ...]:
    """CI local-job expressions that would select a node with these markers."""
    from _pytest.mark.expression import Expression

    enabled = set(markers)
    if "local" not in enabled:
        return ()
    hits = []
    for expr in LOCAL_JOB_MARKEXPRS:
        compiled = Expression.compile(expr)

        def matches(name: str, /, enabled: set[str] = enabled, **kwargs: object) -> bool:
            return not kwargs and name in enabled

        if compiled.evaluate(matches):
            hits.append(expr)
    return tuple(hits)


def module_pytestmark_names(path: Path) -> set[str]:
    """Marker names assigned to module-level pytestmark in a test file."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: set[str] = set()
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if not any(isinstance(target, ast.Name) and target.id == "pytestmark" for target in node.targets):
            continue
        names.update(_pytest_mark_names(node.value))
    return names


def _pytest_mark_names(node: ast.AST) -> set[str]:
    if isinstance(node, ast.List):
        names: set[str] = set()
        for elt in node.elts:
            names.update(_pytest_mark_names(elt))
        return names
    if isinstance(node, ast.Call):
        return _pytest_mark_names(node.func)
    if (
        isinstance(node, ast.Attribute)
        and node.attr
        and isinstance(node.value, ast.Attribute)
        and node.value.attr == "mark"
    ):
        return {node.attr}
    return set()


# Only pytest.mark.aws tests (manual) may reach AWS or CCM. Everything else
# runs without credentials so a missed mock fails instead of creating hosts.
LIVE_CLOUD_ENV_VARS = (
    "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY",
    "AWS_SESSION_TOKEN",
    "AWS_SECURITY_TOKEN",
    "AWS_PROFILE",
    "AWS_DEFAULT_PROFILE",
    "AWS_ROLE_ARN",
    "AWS_WEB_IDENTITY_TOKEN_FILE",
    "AWS_CONTAINER_CREDENTIALS_RELATIVE_URI",
    "AWS_CONTAINER_CREDENTIALS_FULL_URI",
    "AWS_CONTAINER_AUTHORIZATION_TOKEN",
    "CCM_TOKEN",
)
NO_LIVE_CLOUD_ENV: Mapping[str, str] = {
    "AWS_SHARED_CREDENTIALS_FILE": os.devnull,
    "AWS_CONFIG_FILE": os.devnull,
    "AWS_EC2_METADATA_DISABLED": "true",
}


def strip_live_cloud(env) -> None:
    for name in LIVE_CLOUD_ENV_VARS:
        env.pop(name, None)
    env.update(NO_LIVE_CLOUD_ENV)


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
    for name in ("org_s2_indexer_indexes", "org_cluster_manager_base"):
        (software / "ps" / name).mkdir(parents=True, exist_ok=True)
    return software


def spa_env(extra: Optional[Mapping[str, str]] = None) -> dict:
    env = os.environ.copy()
    for name in (*AGENT_ENV_VARS, *INHERITED_PATH_VARS):
        env.pop(name, None)
    strip_live_cloud(env)
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
    migrating = "--from" in argv or "--migrate" in argv
    composing = "--example" in argv or "--architecture" in argv
    if "--provider" not in argv and (composing or not migrating):
        argv[0:0] = ["--provider", "aws"]
    return run_spa(["init", *argv], env=env, cwd=cwd, extra_env=extra_env)
