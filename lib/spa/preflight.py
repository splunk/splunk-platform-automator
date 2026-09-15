"""Controller-side Software / baseconfig / local-apps checks for validate and deploy."""

from __future__ import annotations

import glob
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from spa.paths import DEFAULT_APPS_REL, DEFAULT_SOFTWARE_REL, SpaPaths, parse_flat_yaml, resolve_shared_data_dir

BASECONFIG_MARKERS = ("org_ds_secure_server", "org_cluster_manager_base")
_HINT_SOFTWARE = "Point once with: spa init --software-dir DIR ENV"
_HINT_APPS = "Point once with: spa init --apps-dir DIR ENV"
_DEFAULTS = {
    "SPA_SOFTWARE_DIR": ("../Software", "Software"),
    "SPA_BASECONFIG_DIR": ("../Software", "Software"),
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


def _defaultish(configured: Any, env_var: str) -> bool:
    if not configured:
        return True
    value = str(configured).strip()
    if "{{" in value:
        return True
    return value in _DEFAULTS.get(env_var, ())


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
    default_rel = DEFAULT_APPS_REL if home_leaf == "apps" else DEFAULT_SOFTWARE_REL
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
        source = app.get("source") or "local"
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
        paths, dirs.get("splunk_baseconfig_dir"), "SPA_BASECONFIG_DIR", "Software", paths.baseconfig_dir
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
            hint=_HINT_SOFTWARE,
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
                "(need */org_ds_secure_server and */org_cluster_manager_base)."
                % baseconfig_dir
            ),
            hint=_HINT_SOFTWARE,
            missing=tuple(str(baseconfig_dir / "*" / marker) for marker in BASECONFIG_MARKERS),
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
    )


def controller_data_error(state: ControllerDataState) -> str:
    if state.hint:
        return "%s\n%s" % (state.reason, state.hint)
    return state.reason
