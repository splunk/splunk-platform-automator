"""User-level environment registry, default env parent, and default provider.

Not secrets. Files live under ``${XDG_CONFIG_HOME:-~/.config}/spa/``.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from spa.paths import (
    _expand,
    is_spa_home,
    load_spa_yml,
    save_user_paths,
    user_paths_yml,
    user_spa_config_dir,
    load_user_paths,
)

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None  # type: ignore

DEFAULT_ENV_PARENT_NAME = "Splunk-Platform-Automator"
DEFAULT_PROVIDER = "aws"
PROVIDER_ALIASES = {
    "aws": "aws",
    "terraform": "aws",
    "terraform.aws": "aws",
    "virtualbox": "virtualbox",
    "vbox": "virtualbox",
    "vb": "virtualbox",
}


class RegistryError(Exception):
    def __init__(self, message: str, code: int = 1):
        super().__init__(message)
        self.code = code


def builtin_env_parent(environ: Optional[Dict[str, str]] = None) -> Path:
    env = environ if environ is not None else os.environ
    home = (env.get("HOME") or "").strip() or str(Path.home())
    return (Path(home) / DEFAULT_ENV_PARENT_NAME).resolve()


def default_env_parent(
    environ: Optional[Dict[str, str]] = None,
    *,
    relative_to: Optional[Path] = None,
) -> Path:
    """Parent for name-only ``spa environment init NAME``.

    Order: ``SPA_ENV_PARENT``, ``paths.yml`` ``env_dir``, then
    ``~/Splunk-Platform-Automator``.
    """
    env = environ if environ is not None else os.environ
    start = (relative_to or Path.cwd()).resolve()
    override = (env.get("SPA_ENV_PARENT") or "").strip()
    if override:
        return _expand(override, start)
    user = load_user_paths(env)
    stored = (user.get("env_dir") or "").strip()
    if stored:
        return _expand(stored, start)
    return builtin_env_parent(env)


def is_builtin_env_parent(path: Path, environ: Optional[Dict[str, str]] = None) -> bool:
    try:
        return path.resolve() == builtin_env_parent(environ)
    except OSError:
        return False


def user_environments_yml(environ: Optional[Dict[str, str]] = None) -> Path:
    return user_spa_config_dir(environ) / "environments.yml"


def user_providers_yml(environ: Optional[Dict[str, str]] = None) -> Path:
    return user_spa_config_dir(environ) / "providers.yml"


def _dump_yaml(data: Dict[str, Any]) -> str:
    if yaml is None:
        raise RegistryError("PyYAML is required to write spa user config")
    return yaml.safe_dump(data, default_flow_style=False, sort_keys=False)


def _load_mapping(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        return {}
    if yaml is None:
        try:
            data = load_spa_yml(path)
        except (OSError, ValueError):
            return {}
        return data if isinstance(data, dict) else {}
    try:
        loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _unquote(value: str) -> str:
    text = value.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "'\"":
        return text[1:-1]
    return text


def _read_environments_file(path: Path) -> Dict[str, Any]:
    """Read environments.yml, also without PyYAML (nested, so load_spa_yml cannot)."""
    if yaml is not None:
        return _load_mapping(path)
    if not path.is_file():
        return {}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return {}
    out: Dict[str, Any] = {}
    envs: Dict[str, Dict[str, str]] = {}
    in_envs = False
    current: Optional[str] = None
    for raw in lines:
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip())
        if indent == 0:
            in_envs = False
            current = None
            key, sep, value = stripped.partition(":")
            if not sep:
                continue
            if key.strip() == "environments":
                in_envs = value.strip() in ("", "{}")
                continue
            out[key.strip()] = _unquote(value)
            continue
        if not in_envs:
            continue
        key, sep, value = stripped.partition(":")
        if not sep:
            continue
        if not value.strip():
            current = _unquote(key)
            envs[current] = {}
        elif current is not None and key.strip() == "path":
            envs[current]["path"] = _unquote(value)
    out["environments"] = envs
    return out


def _dump_environments(payload: Dict[str, Any]) -> str:
    """Emit environments.yml without PyYAML so every interpreter agrees."""
    lines = []
    default = (payload.get("default") or "").strip()
    if default:
        lines.append("default: %s" % _quote(default))
    envs: Dict[str, Any] = payload.get("environments") or {}
    if not envs:
        lines.append("environments: {}")
        return "\n".join(lines) + "\n"
    lines.append("environments:")
    for name in sorted(envs):
        lines.append("  %s:" % _quote(name))
        lines.append("    path: %s" % _quote(str((envs[name] or {}).get("path") or "")))
    return "\n".join(lines) + "\n"


def _quote(value: str) -> str:
    return '"%s"' % value.replace("\\", "\\\\").replace('"', '\\"')


def load_environments(environ: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    data = _read_environments_file(user_environments_yml(environ))
    envs = data.get("environments")
    if not isinstance(envs, dict):
        envs = {}
    default = data.get("default")
    return {
        "default": str(default).strip() if default else "",
        "environments": {
            str(name): {"path": str((row or {}).get("path") or "")}
            for name, row in envs.items()
            if str(name).strip()
        },
    }


def save_environments(data: Dict[str, Any], environ: Optional[Dict[str, str]] = None) -> Path:
    path = user_environments_yml(environ)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload: Dict[str, Any] = {}
    default = (data.get("default") or "").strip()
    if default:
        payload["default"] = default
    payload["environments"] = data.get("environments") or {}
    header = "# Splunk Platform Automator registered environments (not secrets).\n"
    path.write_text(header + _dump_environments(payload), encoding="utf-8")
    return path


def canonicalize_provider(value: Optional[str]) -> str:
    raw = (value or "").strip().lower()
    if not raw:
        return DEFAULT_PROVIDER
    if raw not in PROVIDER_ALIASES:
        raise RegistryError(
            "Unknown provider %r (use aws or virtualbox)" % value
        )
    return PROVIDER_ALIASES[raw]


def load_default_provider(environ: Optional[Dict[str, str]] = None) -> str:
    data = _load_mapping(user_providers_yml(environ))
    raw = data.get("default")
    if not raw:
        return DEFAULT_PROVIDER
    try:
        return canonicalize_provider(str(raw))
    except RegistryError:
        return DEFAULT_PROVIDER


def set_default_provider(value: str, environ: Optional[Dict[str, str]] = None) -> Optional[Path]:
    canon = canonicalize_provider(value)
    path = user_providers_yml(environ)
    if canon == DEFAULT_PROVIDER:
        if path.is_file():
            path.unlink()
        return None
    path.parent.mkdir(parents=True, exist_ok=True)
    body = (
        "# Splunk Platform Automator default provider (not secrets).\n"
        "# Omit this file when the default is aws.\n"
        + _dump_yaml({"default": canon})
    )
    path.write_text(body, encoding="utf-8")
    return path


def set_default_env_dir(
    value: str,
    environ: Optional[Dict[str, str]] = None,
    *,
    relative_to: Optional[Path] = None,
) -> Path:
    env = environ if environ is not None else os.environ
    start = (relative_to or Path.cwd()).resolve()
    dest = _expand(value, start)
    if is_builtin_env_parent(dest, env):
        data = dict(load_user_paths(env))
        data.pop("env_dir", None)
        path = user_paths_yml(env)
        path.parent.mkdir(parents=True, exist_ok=True)
        lines = [
            "# Splunk Platform Automator controller paths (not secrets).",
            "# Installers and PS baseconfig stay out of SPA_HOME so install.sh --force cannot delete them.",
        ]
        for key in ("software_dir", "baseconfig_dir", "apps_dir"):
            stored = data.get(key)
            if stored:
                lines.append("%s: %s" % (key, stored))
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return path
    return save_user_paths(env_dir=str(dest), environ=env, relative_to=start)


def set_default_environment(
    name: str,
    environ: Optional[Dict[str, str]] = None,
) -> Path:
    ident = (name or "").strip()
    data = load_environments(environ)
    row = (data.get("environments") or {}).get(ident)
    if not row:
        raise RegistryError("Unknown environment %r (spa environment list)" % name)
    raw = (row.get("path") or "").strip()
    if not raw or not Path(raw).expanduser().is_dir():
        raise RegistryError(
            "Environment %r is registered but its directory is missing (%s)"
            % (ident, raw or "no path")
        )
    data["default"] = ident
    return save_environments(data, environ)


def is_path_dest(value: str) -> bool:
    text = (value or "").strip()
    if not text:
        return False
    if text in {".", ".."}:
        return True
    if text.startswith(("~", "/", "./", "../")):
        return True
    if os.path.isabs(os.path.expanduser(text)):
        return True
    return "/" in text or "\\" in text


def resolve_init_dest(
    positional: Optional[str],
    *,
    env_dir_flag: Optional[str] = None,
    name: Optional[str] = None,
    force: bool = False,
    environ: Optional[Dict[str, str]] = None,
    relative_to: Optional[Path] = None,
) -> Tuple[Path, str, bool]:
    """Return (dest, registry_name, wrote_env_dir_key).

    The third value is always False: init never persists ``env_dir``.
    With ``force`` and a bare name, prefer an existing env at the default
    parent, ``cwd/NAME``, or cwd itself so ``spa env init NAME --force``
    registers an old lab.
    """
    env = environ if environ is not None else os.environ
    start = (relative_to or Path.cwd()).resolve()
    flag = (env_dir_flag or "").strip()
    registry = (name or "").strip()
    pos = (positional or "").strip()

    if flag and pos:
        raise RegistryError(
            "spa environment init: pass --env-dir PARENT --name NAME, or a dest path, not both"
        )
    if flag:
        if not registry:
            raise RegistryError("spa environment init --env-dir requires --name")
        dest = _expand(flag, start) / registry
        return dest, registry, False
    if not pos:
        raise RegistryError(
            "spa environment init: give a name, a dest path, or --env-dir PARENT --name NAME"
        )
    if is_path_dest(pos):
        dest = _expand(pos, start)
        return dest, registry or dest.name, False
    ident = registry or pos
    parent_dest = default_env_parent(env, relative_to=start) / pos
    if force:
        for candidate in (parent_dest, start / pos, start):
            if looks_like_env_dir(candidate) and not is_spa_home(candidate):
                return candidate.resolve(), ident, False
    return parent_dest, ident, False


def lookup_env_path(
    selector: str,
    *,
    environ: Optional[Dict[str, str]] = None,
    relative_to: Optional[Path] = None,
) -> Path:
    env = environ if environ is not None else os.environ
    start = (relative_to or Path.cwd()).resolve()
    text = (selector or "").strip()
    if not text:
        raise RegistryError("Empty environment selector")
    if is_path_dest(text):
        return _expand(text, start)
    expanded = _expand(text, start)
    if expanded.is_dir():
        return expanded
    data = load_environments(env)
    row = (data.get("environments") or {}).get(text)
    if row and row.get("path"):
        return Path(row["path"]).expanduser().resolve()
    raise RegistryError("Unknown environment %r (spa environment list)" % selector)


def registry_default_path(environ: Optional[Dict[str, str]] = None) -> Optional[Path]:
    data = load_environments(environ)
    name = (data.get("default") or "").strip()
    if not name:
        return None
    row = (data.get("environments") or {}).get(name) or {}
    raw = (row.get("path") or "").strip()
    if not raw:
        return None
    path = Path(raw).expanduser()
    if not path.is_dir():
        # Stale entry (deleted dir): fall back instead of pointing spa at a dead path.
        return None
    return path.resolve()


def register_environment(
    name: str,
    dest: Path,
    environ: Optional[Dict[str, str]] = None,
    *,
    replace: bool = False,
) -> None:
    ident = (name or "").strip()
    if not ident:
        raise RegistryError("Environment name is empty")
    if "/" in ident or ident in {".", ".."}:
        raise RegistryError("Environment name must be a single path segment")
    resolved = dest.resolve()
    data = load_environments(environ)
    envs: Dict[str, Any] = dict(data.get("environments") or {})
    existing = envs.get(ident)
    if existing and not replace:
        old = Path(existing.get("path") or "").expanduser()
        try:
            same = old.resolve() == resolved
        except OSError:
            same = False
        if not same and old.exists():
            raise RegistryError(
                "Environment %r is already registered at %s" % (ident, existing.get("path"))
            )
    envs[ident] = {"path": str(resolved)}
    data["environments"] = envs
    if not (data.get("default") or "").strip():
        data["default"] = ident
    save_environments(data, environ)


def list_environments(environ: Optional[Dict[str, str]] = None) -> List[Dict[str, Any]]:
    data = load_environments(environ)
    default = (data.get("default") or "").strip()
    rows = []
    for name, row in sorted((data.get("environments") or {}).items()):
        path = (row or {}).get("path") or ""
        rows.append(
            {
                "name": name,
                "path": path,
                "default": name == default,
                "exists": Path(path).expanduser().is_dir() if path else False,
            }
        )
    return rows


def looks_like_env_dir(path: Path) -> bool:
    return (path / ".spa.yml").is_file() or (path / "config" / "splunk_config.yml").is_file()


def _inventory_has_hosts(path: Path) -> bool:
    hosts = path / "inventory" / "hosts"
    if not hosts.is_file():
        return False
    for line in hosts.read_text(encoding="utf-8", errors="replace").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith(("#", ";")):
            continue
        if stripped.startswith("["):
            continue
        return True
    return False


def _terraform_state_present(path: Path) -> bool:
    state = path / "terraform" / "aws" / "terraform.tfstate"
    if not state.is_file():
        return False
    try:
        text = state.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    if '"resources"' not in text:
        return state.stat().st_size > 2
    return '"resources": []' not in text.replace(" ", "")


def _vagrant_machines_present(path: Path) -> bool:
    machines = path / ".vagrant" / "machines"
    if not machines.is_dir():
        return False
    try:
        return any(machines.iterdir())
    except OSError:
        return False


def looks_deployed(path: Path) -> bool:
    return _inventory_has_hosts(path) or _terraform_state_present(path) or _vagrant_machines_present(path)


def _protected_paths(environ: Optional[Dict[str, str]] = None) -> List[Path]:
    env = environ if environ is not None else os.environ
    home = Path(env.get("HOME") or str(Path.home())).resolve()
    out = [home, Path("/")]
    try:
        out.append(default_env_parent(env))
    except OSError:
        pass
    try:
        out.append(builtin_env_parent(env))
    except OSError:
        pass
    return out


def remove_environment(
    name: str,
    *,
    confirm: bool,
    force: bool,
    environ: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    if not confirm:
        raise RegistryError("spa environment remove requires --yes")
    ident = (name or "").strip()
    data = load_environments(environ)
    envs: Dict[str, Any] = dict(data.get("environments") or {})
    row = envs.get(ident)
    dest: Optional[Path] = None
    if row and row.get("path"):
        dest = Path(row["path"]).expanduser()
    elif is_path_dest(ident):
        dest = _expand(ident, Path.cwd())
        ident = dest.name
        for key, item in list(envs.items()):
            try:
                if Path(item.get("path") or "").expanduser().resolve() == dest.resolve():
                    ident = key
                    break
            except OSError:
                continue
    if dest is None:
        raise RegistryError("Unknown environment %r (spa environment list)" % name)

    resolved = dest.resolve()
    for protected in _protected_paths(environ):
        try:
            if resolved == protected.resolve():
                raise RegistryError("Refusing to delete %s" % resolved)
        except OSError:
            continue
    if not looks_like_env_dir(dest) and ident not in envs:
        raise RegistryError("%s does not look like an SPA environment" % dest)
    if looks_deployed(dest) and not force:
        raise RegistryError(
            "Environment %s looks deployed (inventory, Terraform state, or VirtualBox machines).\n"
            "Run spa destroy --yes in that env first, or spa environment remove %s --yes --force\n"
            "(deletes the local dir only; cloud/VMs are not destroyed)."
            % (ident, ident)
        )
    if dest.exists():
        shutil.rmtree(dest)
    envs.pop(ident, None)
    data["environments"] = envs
    if (data.get("default") or "") == ident:
        data["default"] = next(iter(sorted(envs)), "")
    save_environments(data, environ)
    return {"name": ident, "path": str(resolved), "deleted": True}
