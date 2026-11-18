"""Controller-side Software / baseconfig / local-apps checks for validate and deploy."""

from __future__ import annotations

import glob
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from spa.paths import (
    DEFAULT_APPS_REL,
    DEFAULT_BASECONFIG_REL,
    DEFAULT_SOFTWARE_REL,
    SpaPaths,
    parse_flat_yaml,
    resolve_shared_data_dir,
)

ENTERPRISE_DOWNLOAD = "https://www.splunk.com/en_us/download/splunk-enterprise.html"
FORWARDER_DOWNLOAD = "https://www.splunk.com/en_us/download/universal-forwarder.html"
_ARCHIVE_VERSION = re.compile(r".*-([0-9]+\.[0-9]+[\.]*[0-9]*[\.]*[0-9]*)-.*")
_GUEST_TARBALL_ARCH = {
    "aarch64": "arm64",
    "arm64": "arm64",
    "x86_64": "amd64",
    "amd64": "amd64",
}

BASECONFIG_MARKERS = ("org_s2_indexer_indexes", "org_cluster_manager_base")
_HINT_SOFTWARE = "Point once with: spa init --software-dir DIR ENV"
_HINT_BASECONFIG = "Point once with: spa init --baseconfig-dir DIR ENV"
_HINT_APPS = "Point once with: spa init --apps-dir DIR ENV"
_DEFAULTS = {
    "SPA_SOFTWARE_DIR": ("../Software", "Software"),
    "SPA_BASECONFIG_DIR": ("../baseconfigs", "baseconfigs"),
    "SPA_APPS_DIR": ("../apps", "apps"),
}


@dataclass(frozen=True)
class ControllerDataState:
    ok: bool
    reason: str = ""
    hint: str = ""
    missing: Tuple[str, ...] = ()
    software_dir: str = ""
    baseconfig_dir: str = ""
    apps_dir: str = ""
    # apps_dir is only inspected when the config has source: local apps.
    apps_checked: bool = False


def _defaultish(configured: Any, env_var: str) -> bool:
    if not configured:
        return True
    value = str(configured).strip()
    if "{{" in value:
        return True
    return value in _DEFAULTS.get(env_var, ())


def _secret_resolver():
    plugin = Path(__file__).resolve().parents[2] / "ansible" / "plugins" / "inventory"
    plugin_dir = str(plugin)
    if plugin_dir not in sys.path:
        sys.path.insert(0, plugin_dir)
    import secret_resolver

    return secret_resolver


def env_lookup_readiness(config: Any) -> List[Dict[str, str]]:
    """Sorted environment-lookup status. Values are never included."""
    return _secret_resolver().env_lookup_readiness(config)


def unresolved_env_message(config: Any) -> Optional[str]:
    """Error naming every missing or empty lookup, or None when all are set."""
    return _secret_resolver().unresolved_env_message(config)


def env_reference_lines(config: Any) -> List[str]:
    """Non-failing readiness summary. An empty config returns no lines."""
    rows = env_lookup_readiness(config)
    if not rows:
        return []
    return ["Environment references:"] + [
        "  %s: %s" % (row["name"], row["state"]) for row in rows
    ]


def load_config_mapping(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        return {}
    text = path.read_text(encoding="utf-8")
    try:
        import yaml
    except ImportError:
        data = parse_flat_yaml(text)
        return data if isinstance(data, dict) else {}
    data = yaml.safe_load(text) or {}
    return data if isinstance(data, dict) else {}


def _effective_dir(
    paths: SpaPaths,
    configured: Any,
    env_var: str,
    home_leaf: str,
    fallback: Path,
) -> Path:
    if _defaultish(configured, env_var):
        return fallback
    if home_leaf == "apps":
        default_rel = DEFAULT_APPS_REL
    elif home_leaf == "baseconfigs":
        default_rel = DEFAULT_BASECONFIG_REL
    else:
        default_rel = DEFAULT_SOFTWARE_REL
    return resolve_shared_data_dir(
        paths.spa_home,
        paths.spa_env_dir,
        configured=str(configured).strip() or default_rel,
        env_var=env_var,
        home_leaf=home_leaf,
    )


def _local_apps(config: Dict[str, Any]) -> List[Dict[str, Any]]:
    dep = config.get("splunk_app_deployment") or {}
    if not isinstance(dep, dict):
        return []
    found: List[Dict[str, Any]] = []
    for app in list(dep.get("apps") or []) + list(dep.get("host_specific_apps") or []):
        if not isinstance(app, dict):
            continue
        source = app.get("source") or "splunkbase"
        if source != "local":
            continue
        found.append(app)
    return found


def local_app_source_path(app: Dict[str, Any], repo: Path) -> Path:
    local_path = app.get("local_path")
    if local_path:
        expanded = Path(os.path.expanduser(str(local_path)))
        if expanded.is_absolute():
            return expanded
        return (repo / expanded).resolve()
    rel = app.get("path") or app.get("name") or ""
    expanded = Path(os.path.expanduser(str(rel)))
    if expanded.is_absolute():
        return expanded
    return (repo / expanded).resolve()


def _has_baseconfig_apps(baseconfig_dir: Path) -> bool:
    root = str(baseconfig_dir)
    for marker in BASECONFIG_MARKERS:
        if not glob.glob(os.path.join(root, "*", marker)):
            return False
    return True


def splunk_archive_glob(arch_type: str, version: str, architecture: str) -> str:
    """Filename glob for one installer type, version, and tarball suffix."""
    search_version = "*" if version == "latest" else version
    if arch_type == "windowsforwarder":
        return "splunkforwarder-%s-*-x64-release.msi" % search_version
    return "%s-%s-*-?inux-%s.tgz" % (arch_type, search_version, architecture)


def archive_download_url(arch_type: str) -> str:
    if arch_type in ("splunkforwarder", "windowsforwarder"):
        return FORWARDER_DOWNLOAD
    return ENTERPRISE_DOWNLOAD


def missing_archive_reason(
    arch_type: str,
    version: str,
    architecture: str,
    software_dir: str,
) -> str:
    pattern = splunk_archive_glob(arch_type, version, architecture)
    return (
        "No archive found matching '%s' for Splunk version %s architecture %s in %s. "
        "The build number is in the filename and cannot be guessed. Download from %s"
        % (pattern, version, architecture, software_dir, archive_download_url(arch_type))
    )


def guest_tarball_architecture(machine: str) -> str:
    """Map a live uname (aarch64 / x86_64) to the tarball suffix."""
    return _GUEST_TARBALL_ARCH.get(str(machine or "").strip(), "")


def _role_arch_type(role: str) -> Optional[str]:
    if not role:
        return None
    if role == "universal_forwarder":
        return "splunkforwarder"
    if role == "universal_forwarder_windows":
        return "windowsforwarder"
    return "splunk"


def _named_environment(config: Dict[str, Any], host: Dict[str, Any]) -> Dict[str, Any]:
    environments = config.get("splunk_environments") or []
    if not isinstance(environments, list):
        return {}
    defaults = config.get("splunk_defaults") or {}
    default_name = "splk"
    if isinstance(defaults, dict) and defaults.get("splunk_env_name"):
        default_name = str(defaults["splunk_env_name"])
    named = host.get("splunk_env")
    wanted = str(named) if named and str(named) != default_name else default_name
    for environment in environments:
        if not isinstance(environment, dict):
            continue
        if str(environment.get("splunk_env_name") or "") != wanted:
            continue
        return environment
    return {}


def _host_version(host: Dict[str, Any], environment: Dict[str, Any], defaults: Dict[str, Any]) -> str:
    if host.get("splunk_version"):
        return str(host["splunk_version"])
    if environment.get("splunk_version"):
        return str(environment["splunk_version"])
    if defaults.get("splunk_version"):
        return str(defaults["splunk_version"])
    return "latest"


def _host_architecture(host: Dict[str, Any], environment: Dict[str, Any], defaults: Dict[str, Any]) -> str:
    if host.get("splunk_architecture"):
        return str(host["splunk_architecture"])
    if environment.get("splunk_architecture"):
        return str(environment["splunk_architecture"])
    if defaults.get("splunk_architecture"):
        return str(defaults["splunk_architecture"])
    return "amd64"


def required_splunk_archives(config: Dict[str, Any]) -> Tuple[Tuple[str, str, str], ...]:
    """One (arch_type, version, architecture) per distinct installer the config uses."""
    defaults = config.get("splunk_defaults") if isinstance(config.get("splunk_defaults"), dict) else {}
    seen = []
    found = set()
    for host in config.get("splunk_hosts") or []:
        if not isinstance(host, dict):
            continue
        environment = _named_environment(config, host)
        version = _host_version(host, environment, defaults)
        architecture = _host_architecture(host, environment, defaults)
        for role in host.get("roles") or []:
            arch_type = _role_arch_type(str(role))
            if not arch_type:
                continue
            key = (arch_type, version, architecture)
            if key in found:
                continue
            found.add(key)
            seen.append(key)
    return tuple(seen)


def _version_sort_key(text: str) -> Tuple[int, ...]:
    parts: List[int] = []
    for piece in str(text).split("."):
        if piece.isdigit():
            parts.append(int(piece))
        else:
            break
    return tuple(parts)


def newest_archive_version(paths: Iterable[str]) -> Optional[str]:
    versions: List[str] = []
    for path in paths:
        match = _ARCHIVE_VERSION.match(os.path.basename(path))
        if match:
            versions.append(match.group(1))
    if not versions:
        return None
    return max(versions, key=_version_sort_key)


def software_archive_error(
    software_dir: Path,
    config: Dict[str, Any],
    architecture_override: Optional[str] = None,
) -> Optional[str]:
    """Missing-file or latest-version-alignment reason, or None when Software is ok."""
    specs = required_splunk_archives(config)
    directory = str(software_dir)
    latest_resolved: List[Tuple[str, str]] = []
    for arch_type, version, architecture in specs:
        suffix = architecture_override or architecture
        pattern = splunk_archive_glob(arch_type, version, suffix)
        matches = glob.glob(os.path.join(directory, pattern))
        if not matches:
            return missing_archive_reason(arch_type, version, suffix, directory)
        if version == "latest":
            resolved = newest_archive_version(matches)
            if resolved:
                latest_resolved.append((arch_type, resolved))
    unique_latest = {resolved for _, resolved in latest_resolved}
    if len(latest_resolved) > 1 and len(unique_latest) > 1:
        parts = ", ".join("%s %s" % (arch_type, resolved) for arch_type, resolved in latest_resolved)
        return "latest archive versions do not match: %s" % parts
    return None


def guest_mismatch_archive_reason(
    software_dir: Path,
    config: Dict[str, Any],
    rows: Sequence[dict],
) -> Optional[str]:
    """Missing-archive note for the live guest suffix after an architecture mismatch."""
    notes: List[str] = []
    seen = set()
    for row in rows:
        if row.get("ok"):
            continue
        suffix = guest_tarball_architecture(str(row.get("architecture") or ""))
        if not suffix or suffix in seen:
            continue
        seen.add(suffix)
        error = software_archive_error(software_dir, config, architecture_override=suffix)
        if error:
            notes.append(error)
    return "\n".join(notes) if notes else None


def check_controller_data(
    paths: SpaPaths,
    config: Optional[Dict[str, Any]] = None,
) -> ControllerDataState:
    """Fail when Software, PS baseconfig apps, or local app sources are missing."""
    cfg = config if config is not None else load_config_mapping(Path(paths.config_file))
    dirs = cfg.get("splunk_dirs") if isinstance(cfg.get("splunk_dirs"), dict) else {}
    dep = cfg.get("splunk_app_deployment") if isinstance(cfg.get("splunk_app_deployment"), dict) else {}

    software_dir = _effective_dir(
        paths, dirs.get("splunk_software_dir"), "SPA_SOFTWARE_DIR", "Software", paths.software_dir
    )
    baseconfig_dir = _effective_dir(
        paths, dirs.get("splunk_baseconfig_dir"), "SPA_BASECONFIG_DIR", "baseconfigs", paths.baseconfig_dir
    )
    apps_dir = _effective_dir(
        paths, dep.get("local_app_repo_path"), "SPA_APPS_DIR", "apps", paths.apps_dir
    )

    if not software_dir.is_dir():
        return ControllerDataState(
            ok=False,
            reason="Software directory not found: %s" % software_dir,
            hint=_HINT_SOFTWARE,
            missing=(str(software_dir),),
            software_dir=str(software_dir),
            baseconfig_dir=str(baseconfig_dir),
            apps_dir=str(apps_dir),
        )
    if not baseconfig_dir.is_dir():
        return ControllerDataState(
            ok=False,
            reason="Baseconfig directory not found: %s" % baseconfig_dir,
            hint=_HINT_BASECONFIG,
            missing=(str(baseconfig_dir),),
            software_dir=str(software_dir),
            baseconfig_dir=str(baseconfig_dir),
            apps_dir=str(apps_dir),
        )
    if not _has_baseconfig_apps(baseconfig_dir):
        return ControllerDataState(
            ok=False,
            reason=(
                "Cannot find Splunk baseconfig apps in %s "
                "(need */org_s2_indexer_indexes and */org_cluster_manager_base)."
                % baseconfig_dir
            ),
            hint=_HINT_BASECONFIG,
            missing=tuple(str(baseconfig_dir / "*" / marker) for marker in BASECONFIG_MARKERS),
            software_dir=str(software_dir),
            baseconfig_dir=str(baseconfig_dir),
            apps_dir=str(apps_dir),
        )

    archive_error = software_archive_error(software_dir, cfg)
    if archive_error:
        return ControllerDataState(
            ok=False,
            reason=archive_error,
            software_dir=str(software_dir),
            baseconfig_dir=str(baseconfig_dir),
            apps_dir=str(apps_dir),
        )

    local_apps = _local_apps(cfg)
    if not local_apps:
        return ControllerDataState(
            ok=True,
            software_dir=str(software_dir),
            baseconfig_dir=str(baseconfig_dir),
            apps_dir=str(apps_dir),
        )

    if not apps_dir.is_dir():
        names = sorted({str(app.get("name") or app.get("path") or "?") for app in local_apps})
        return ControllerDataState(
            ok=False,
            reason=(
                "Local apps are configured (%s) but apps directory not found: %s"
                % (", ".join(names), apps_dir)
            ),
            hint=_HINT_APPS,
            missing=(str(apps_dir),),
            software_dir=str(software_dir),
            baseconfig_dir=str(baseconfig_dir),
            apps_dir=str(apps_dir),
        )

    missing: List[str] = []
    seen = set()
    for app in local_apps:
        source = local_app_source_path(app, apps_dir)
        key = str(source)
        if key in seen:
            continue
        seen.add(key)
        if not source.exists():
            missing.append(key)
    if missing:
        return ControllerDataState(
            ok=False,
            reason="Local app source not found: %s" % ", ".join(missing),
            hint="Place each source: local app under %s (name or path from config)." % apps_dir,
            missing=tuple(missing),
            software_dir=str(software_dir),
            baseconfig_dir=str(baseconfig_dir),
            apps_dir=str(apps_dir),
        )
    return ControllerDataState(
        ok=True,
        software_dir=str(software_dir),
        baseconfig_dir=str(baseconfig_dir),
        apps_dir=str(apps_dir),
        apps_checked=True,
    )


def controller_data_error(state: ControllerDataState) -> str:
    if state.hint:
        return "%s\n%s" % (state.reason, state.hint)
    return state.reason
