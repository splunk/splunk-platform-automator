#!/usr/bin/env python3
"""Resolve SPA_HOME, SPA_ENV_DIR, and related paths (Distribution M2).

Contract
--------
SPA_HOME
    Framework root: ansible/, terraform/aws modules, skills/, bin/, ansible.cfg.
SPA_ENV_DIR
    Env root: config/splunk_config.yml, optional .spa.yml, inventory/hosts,
    Terraform state (tfvars, .terraform, tfstate).

Unset both (and no .spa.yml) still resolves to the git clone for ansible-playbook
and path resolution. ``spa`` operator commands refuse that clone-equal layout:
SPA_HOME is the framework only; config and state live in SPA_ENV_DIR.

SPLUNK_CONFIG_FILE still wins for the YAML path.

Resolution order
----------------
1. Environment: SPA_HOME, SPA_ENV_DIR, SPLUNK_CONFIG_FILE
2. .spa.yml walking up from the start directory
   (``spa_home``, optional ``software_dir`` / ``baseconfig_dir`` / ``apps_dir``; lab = that dir)
3. ``~/.config/spa/paths.yml`` (controller Software / baseconfig / apps; not secrets)
4. The git clone that contains this module (or ansible.cfg + ansible/ + bin/)

This module is importable from the inventory plugin and runnable:

  python3 ansible/plugins/inventory/spa_paths.py --json
  python3 ansible/plugins/inventory/spa_paths.py --export
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, Optional

SPA_YML_NAME = ".spa.yml"
DEFAULT_SOFTWARE_REL = "../Software"
DEFAULT_APPS_REL = "../apps"


def _err(message: str) -> None:
    print(message, file=sys.stderr)


def is_spa_home(path: Path) -> bool:
    """True if path looks like a framework checkout or install prefix."""
    root = Path(path)
    return (
        (root / "ansible.cfg").is_file()
        and (root / "ansible").is_dir()
        and (root / "bin").is_dir()
    )


class EnvDirRequired(RuntimeError):
    """spa was pointed at the framework prefix instead of an env dir."""


ENV_DIR_REQUIRED_HINT = (
    "spa requires an environment directory, not the framework prefix (clone or install).\n"
    "Create one:  spa init --example cm_2idxc_sh_uf_aws.yml ~/envs/my-env\n"
    "Then:        cd ~/envs/my-env\n"
    "             # direnv loads SPA_*; otherwise: eval \"$(spa env --export)\""
)


def is_framework_as_env(paths: SpaPaths) -> bool:
    """True when the resolved env dir is the framework tree (clone-equal)."""
    try:
        home = paths.spa_home.resolve()
        env = paths.spa_env_dir.resolve()
    except OSError:
        return False
    return home == env and is_spa_home(home)


def env_dir_required_error(paths: SpaPaths) -> Optional[str]:
    """Message when spa must not run clone-equal; None if the env dir is OK."""
    if is_framework_as_env(paths):
        return ENV_DIR_REQUIRED_HINT
    return None


def clone_root_from_this_file() -> Path:
    """Framework root when this file lives at lib/spa/paths.py."""
    here = Path(__file__).resolve()
    # spa → lib → root
    candidate = here.parents[2]
    if is_spa_home(candidate):
        return candidate
    # inventory plugin wrapper: ansible/plugins/inventory/spa_paths.py
    if len(here.parents) >= 4:
        alt = here.parents[3]
        if is_spa_home(alt):
            return alt
    return candidate


def find_spa_yml(start: Optional[Path] = None) -> Optional[Path]:
    """Walk from start (default: cwd) toward filesystem root for .spa.yml."""
    current = (start or Path.cwd()).resolve()
    if current.is_file():
        current = current.parent
    for directory in [current, *current.parents]:
        candidate = directory / SPA_YML_NAME
        if candidate.is_file():
            return candidate
    return None


def parse_flat_yaml(text: str) -> Dict[str, Any]:
    """Top-level ``key: value`` scalars only. Used when PyYAML is unavailable.

    ``spa`` runs under the system interpreter until the venv exists, so this
    fallback must read every pointer key, not just ``spa_home``.
    """
    data: Dict[str, Any] = {}
    for line in text.splitlines():
        if line[:1] in (" ", "\t", "-") or ":" not in line:
            continue
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        key, _, value = stripped.partition(":")
        key = key.strip()
        value = value.split(" #", 1)[0].strip().strip("'\"")
        if key and value:
            data[key] = value
    return data


def load_spa_yml(path: Path) -> Dict[str, Any]:
    """Load .spa.yml. PyYAML if present; otherwise a flat key/value reader."""
    text = path.read_text(encoding="utf-8")
    try:
        import yaml
    except ImportError:
        yaml = None  # type: ignore
    if yaml is not None:
        data = yaml.safe_load(text) or {}
        if not isinstance(data, dict):
            raise ValueError("%s must be a mapping" % path)
        return data
    return parse_flat_yaml(text)


def _expand(path: str, relative_to: Path) -> Path:
    expanded = Path(os.path.expanduser(path))
    if not expanded.is_absolute():
        expanded = relative_to / expanded
    return expanded.resolve()


def xdg_config_home(environ: Optional[Dict[str, str]] = None) -> Path:
    """XDG Base Directory Spec: ignore a relative XDG_CONFIG_HOME."""
    env = environ if environ is not None else os.environ
    raw = (env.get("XDG_CONFIG_HOME") or "").strip()
    if raw.startswith("/"):
        return Path(raw)
    home = (env.get("HOME") or "").strip()
    if not home:
        if environ is not None:
            return Path("/nonexistent-spa-xdg-config")
        home = str(Path.home())
    return Path(home) / ".config"


def user_spa_config_dir(environ: Optional[Dict[str, str]] = None) -> Path:
    return xdg_config_home(environ) / "spa"


def user_paths_yml(environ: Optional[Dict[str, str]] = None) -> Path:
    return user_spa_config_dir(environ) / "paths.yml"


def load_user_paths(environ: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    """Controller-level Software / baseconfig / apps pointers. Not secrets."""
    path = user_paths_yml(environ)
    if not path.is_file():
        return {}
    try:
        data = load_spa_yml(path)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def save_user_paths(
    *,
    software_dir: Optional[str] = None,
    baseconfig_dir: Optional[str] = None,
    apps_dir: Optional[str] = None,
    environ: Optional[Dict[str, str]] = None,
    relative_to: Optional[Path] = None,
) -> Path:
    """Create/update ~/.config/spa/paths.yml. Dir is created on first write."""
    env = environ if environ is not None else os.environ
    start = (relative_to or Path.cwd()).resolve()
    data = dict(load_user_paths(env))
    if software_dir:
        data["software_dir"] = str(_expand(software_dir, start))
        if not baseconfig_dir:
            data["baseconfig_dir"] = data["software_dir"]
    if baseconfig_dir:
        data["baseconfig_dir"] = str(_expand(baseconfig_dir, start))
    if apps_dir:
        data["apps_dir"] = str(_expand(apps_dir, start))
    path = user_paths_yml(env)
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Splunk Platform Automator controller paths (not secrets).",
        "# Installers and PS baseconfig stay out of SPA_HOME so install.sh --force cannot delete them.",
    ]
    for key in ("software_dir", "baseconfig_dir", "apps_dir"):
        value = data.get(key)
        if value:
            lines.append("%s: %s" % (key, value))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _user_path_for_leaf(user: Dict[str, Any], env_var: str, home_leaf: str) -> Optional[str]:
    if home_leaf == "apps" or env_var == "SPA_APPS_DIR":
        value = user.get("apps_dir") or user.get("spa_apps_dir")
        return str(value) if value else None
    if env_var == "SPA_BASECONFIG_DIR":
        value = (
            user.get("baseconfig_dir")
            or user.get("software_dir")
            or user.get("spa_software_dir")
        )
        return str(value) if value else None
    value = user.get("software_dir") or user.get("spa_software_dir")
    return str(value) if value else None


def resolve_shared_data_dir(
    spa_home: Path,
    spa_env_dir: Path,
    configured: str = DEFAULT_SOFTWARE_REL,
    env_var: str = "SPA_SOFTWARE_DIR",
    yml_value: Optional[str] = None,
    environ: Optional[Dict[str, str]] = None,
    start_dir: Optional[Path] = None,
    home_leaf: str = "Software",
) -> Path:
    """Resolve Software / baseconfig / local apps.

    Order: env override, absolute configured path, env ``.spa.yml`` value,
    ``~/.config/spa/paths.yml``, then the first existing directory among
    env-relative, SPA_HOME-relative, and ``$SPA_HOME/<home_leaf>``. If none
    exist, return the env-relative path (the documented default) so errors stay
    specific.
    """
    env = environ if environ is not None else os.environ
    start = (start_dir or Path.cwd()).resolve()
    override = (env.get(env_var) or "").strip()
    if override:
        return _expand(override, start)

    default_rel = DEFAULT_APPS_REL if home_leaf == "apps" else DEFAULT_SOFTWARE_REL
    configured = (configured or default_rel).strip()
    if configured and os.path.isabs(os.path.expanduser(configured)):
        return _expand(configured, start)

    if yml_value:
        return _expand(str(yml_value), spa_env_dir)

    user_value = _user_path_for_leaf(load_user_paths(env), env_var, home_leaf)
    if user_value:
        return _expand(user_value, start)

    rel = configured or default_rel
    candidates = [
        (spa_env_dir / rel).resolve(),
        (spa_home / rel).resolve(),
        (spa_home / home_leaf).resolve(),
    ]
    seen = []
    for candidate in candidates:
        if candidate in seen:
            continue
        seen.append(candidate)
        if candidate.is_dir():
            return candidate
    return candidates[0]


@dataclass(frozen=True)
class SpaPaths:
    spa_home: Path
    spa_env_dir: Path
    config_file: Path
    inventory_dir: Path
    terraform_modules_dir: Path
    terraform_state_dir: Path
    roots_differ: bool
    spa_yml: Optional[Path]
    software_dir: Path
    baseconfig_dir: Path
    apps_dir: Path

    def as_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        for key, value in list(data.items()):
            if isinstance(value, Path):
                data[key] = str(value)
            elif value is None:
                data[key] = None
        return data

    def ansible_inventory(self) -> str:
        """ANSIBLE_INVENTORY value that prefers the env over the clone config."""
        parts = [str(self.config_file)]
        aws_ec2 = self.config_file.parent / "aws_ec2.yml"
        if aws_ec2.is_file():
            parts.append(str(aws_ec2))
        parts.append(str(self.inventory_dir))
        return ",".join(parts)

    def export_env(self) -> Dict[str, str]:
        """Environment overlay for validate, spa shell, and ansible-playbook."""
        return {
            "SPA_HOME": str(self.spa_home),
            "SPA_ENV_DIR": str(self.spa_env_dir),
            "SPLUNK_CONFIG_FILE": str(self.config_file),
            "ANSIBLE_CONFIG": str(self.spa_home / "ansible.cfg"),
            "ANSIBLE_INVENTORY": self.ansible_inventory(),
            "ANSIBLE_ROLES_PATH": str(self.spa_home / "ansible" / "roles"),
            "ANSIBLE_INVENTORY_PLUGINS": str(self.spa_home / "ansible" / "plugins" / "inventory"),
            "ANSIBLE_LOOKUP_PLUGINS": str(self.spa_home / "ansible" / "plugins" / "lookup"),
            "SPA_SOFTWARE_DIR": str(self.software_dir),
            "SPA_BASECONFIG_DIR": str(self.baseconfig_dir),
            "SPA_APPS_DIR": str(self.apps_dir),
        }


def resolve_spa_paths(
    start_dir: Optional[Path] = None,
    environ: Optional[Dict[str, str]] = None,
    clone_root: Optional[Path] = None,
) -> SpaPaths:
    """Resolve the path contract. ``environ`` defaults to os.environ."""
    env = environ if environ is not None else os.environ
    start = Path(start_dir) if start_dir is not None else Path.cwd()
    start = start.resolve()
    clone = Path(clone_root) if clone_root is not None else clone_root_from_this_file()
    clone = clone.resolve()

    env_home = (env.get("SPA_HOME") or "").strip()
    env_dir = (env.get("SPA_ENV_DIR") or "").strip()
    env_config = (env.get("SPLUNK_CONFIG_FILE") or "").strip()

    spa_yml_path = None
    spa_yml_data: Dict[str, Any] = {}
    # Prefer an explicit env dir's .spa.yml, then walk from start.
    if env_dir:
        explicit_yml = _expand(env_dir, start) / SPA_YML_NAME
        if explicit_yml.is_file():
            spa_yml_path = explicit_yml
    if spa_yml_path is None:
        spa_yml_path = find_spa_yml(start)
    if spa_yml_path is not None:
        spa_yml_data = load_spa_yml(spa_yml_path)

    if env_home:
        spa_home = _expand(env_home, start)
    elif spa_yml_data.get("spa_home"):
        spa_home = _expand(str(spa_yml_data["spa_home"]), spa_yml_path.parent)
    else:
        spa_home = clone

    if env_dir:
        spa_env_dir = _expand(env_dir, start)
    elif spa_yml_path is not None:
        spa_env_dir = spa_yml_path.parent.resolve()
    else:
        spa_env_dir = spa_home

    if env_config:
        config_file = _expand(env_config, start)
    else:
        config_file = (spa_env_dir / "config" / "splunk_config.yml").resolve()

    inventory_dir = (spa_env_dir / "inventory").resolve()
    terraform_modules_dir = (spa_home / "terraform" / "aws").resolve()
    # Equal roots: keep writing into terraform/aws/ (in-repo envs do not move).
    terraform_state_dir = (spa_env_dir / "terraform" / "aws").resolve()
    roots_differ = spa_home != spa_env_dir

    software_dir = resolve_shared_data_dir(
        spa_home,
        spa_env_dir,
        configured=DEFAULT_SOFTWARE_REL,
        env_var="SPA_SOFTWARE_DIR",
        yml_value=spa_yml_data.get("software_dir") or spa_yml_data.get("spa_software_dir"),
        environ=env,
        start_dir=start,
        home_leaf="Software",
    )
    baseconfig_dir = resolve_shared_data_dir(
        spa_home,
        spa_env_dir,
        configured=DEFAULT_SOFTWARE_REL,
        env_var="SPA_BASECONFIG_DIR",
        yml_value=spa_yml_data.get("baseconfig_dir") or spa_yml_data.get("software_dir") or spa_yml_data.get("spa_software_dir"),
        environ=env,
        start_dir=start,
        home_leaf="Software",
    )
    apps_dir = resolve_shared_data_dir(
        spa_home,
        spa_env_dir,
        configured=DEFAULT_APPS_REL,
        env_var="SPA_APPS_DIR",
        yml_value=spa_yml_data.get("apps_dir") or spa_yml_data.get("spa_apps_dir"),
        environ=env,
        start_dir=start,
        home_leaf="apps",
    )

    return SpaPaths(
        spa_home=spa_home,
        spa_env_dir=spa_env_dir,
        config_file=config_file,
        inventory_dir=inventory_dir,
        terraform_modules_dir=terraform_modules_dir,
        terraform_state_dir=terraform_state_dir,
        roots_differ=roots_differ,
        spa_yml=spa_yml_path.resolve() if spa_yml_path is not None else None,
        software_dir=software_dir,
        baseconfig_dir=baseconfig_dir,
        apps_dir=apps_dir,
    )


def format_export(paths: SpaPaths) -> str:
    lines = []
    for key, value in paths.export_env().items():
        lines.append("export %s=%s" % (key, _shell_quote(value)))
    return "\n".join(lines) + "\n"


def _shell_quote(value: str) -> str:
    return "'" + value.replace("'", "'\"'\"'") + "'"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Resolve SPA_HOME / SPA_ENV_DIR / SPLUNK_CONFIG_FILE (Distribution M2)"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print resolved paths as JSON",
    )
    parser.add_argument(
        "--export",
        action="store_true",
        help="Print bash export statements (eval this)",
    )
    parser.add_argument(
        "--start-dir",
        help="Directory to start .spa.yml walk from (default: cwd)",
    )
    return parser


def main(argv: Optional[list] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    start = Path(args.start_dir).resolve() if args.start_dir else None
    try:
        paths = resolve_spa_paths(start_dir=start)
    except Exception as exc:
        _err(str(exc))
        return 1
    if args.export:
        sys.stdout.write(format_export(paths))
        return 0
    print(json.dumps(paths.as_dict(), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
