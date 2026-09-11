"""Resolve and run Ansible playbooks for `spa run` / provision / deploy / destroy."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional, Tuple

import subprocess

from spa.executil import apply_paths_env, tool_path
from spa.paths import SpaPaths, load_spa_yml, resolve_spa_paths


class PlaybookError(Exception):
    pass


def _safe_under(root: Path, candidate: Path) -> bool:
    try:
        candidate.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _yml(path: Path) -> Optional[Path]:
    for suffix in (".yml", ".yaml"):
        probe = path if path.suffix in {".yml", ".yaml"} else path.with_suffix(suffix)
        if probe.is_file():
            return probe
    if path.is_file():
        return path
    return None


def list_framework_stems(home: Path) -> List[Tuple[str, str, Path]]:
    """Return (stem, source, path) for ansible/*.yml and verification/*.yml."""
    items: List[Tuple[str, str, Path]] = []
    ansible_dir = home / "ansible"
    if ansible_dir.is_dir():
        for path in sorted(ansible_dir.glob("*.yml")):
            items.append((path.stem, "ansible", path))
        ver = ansible_dir / "verification"
        if ver.is_dir():
            for path in sorted(ver.glob("*.yml")):
                items.append(("verification/" + path.stem, "verification", path))
    return items


def list_env_stems(env_dir: Path, extra_dirs: Optional[List[str]] = None) -> List[Tuple[str, str, Path]]:
    items: List[Tuple[str, str, Path]] = []
    dirs = extra_dirs or []
    yml = env_dir / ".spa.yml"
    if yml.is_file():
        data = load_spa_yml(yml)
        configured = data.get("playbook_dirs") or []
        if isinstance(configured, str):
            configured = [configured]
        dirs = list(dirs) + [str(d) for d in configured]
    seen = set()
    for name in dirs:
        name = name.strip().strip("/")
        if not name or name in seen:
            continue
        seen.add(name)
        folder = (env_dir / name).resolve()
        if not _safe_under(env_dir, folder) or not folder.is_dir():
            continue
        for path in sorted(folder.glob("*.yml")):
            items.append((name + "/" + path.stem, "env", path))
    return items


def catalog(paths: SpaPaths, extra_dir: Optional[str] = None) -> List[Dict[str, str]]:
    extra = [extra_dir] if extra_dir else None
    rows = []
    for stem, source, path in list_framework_stems(paths.spa_home) + list_env_stems(
        paths.spa_env_dir, extra
    ):
        rows.append({"name": stem, "source": source, "path": str(path)})
    return rows


def resolve(name: str, paths: Optional[SpaPaths] = None, extra_dir: Optional[str] = None) -> Path:
    paths = paths or resolve_spa_paths()
    raw = name.strip()
    if raw.endswith(".yml") or raw.endswith(".yaml"):
        stem_path = Path(raw)
    else:
        stem_path = Path(raw)

    if stem_path.is_absolute():
        found = _yml(stem_path)
        if found:
            home_ansible = (paths.spa_home / "ansible").resolve()
            if _safe_under(home_ansible, found) or _safe_under(paths.spa_env_dir, found):
                return found
        raise PlaybookError("Playbook not allowed or not found: %s" % name)

    parts = Path(raw).parts
    if parts and parts[0] == "ansible":
        found = _yml(paths.spa_home / raw)
        if found and _safe_under(paths.spa_home / "ansible", found):
            return found
        raise PlaybookError("Unknown playbook: %s" % name)

    if parts and parts[0] == "verification":
        found = _yml(paths.spa_home / "ansible" / Path(*parts))
        if found:
            return found
        raise PlaybookError("Unknown playbook: %s" % name)

    if extra_dir and "/" not in raw and raw not in (".", ".."):
        found = _yml(paths.spa_env_dir / extra_dir / Path(raw).name)
        if found and _safe_under(paths.spa_env_dir, found):
            return found

    if "/" in raw:
        if ".." in parts:
            raise PlaybookError("Path escape is not allowed: %s" % name)
        found = _yml(paths.spa_env_dir / raw)
        if found and _safe_under(paths.spa_env_dir, found):
            return found
        raise PlaybookError("Unknown playbook: %s" % name)

    found = _yml(paths.spa_home / "ansible" / Path(raw).name)
    if found and found.parent == (paths.spa_home / "ansible"):
        return found
    raise PlaybookError("Unknown playbook: %s" % name)


def run_playbook(playbook: Path, paths: SpaPaths, extra: Optional[List[str]] = None) -> int:
    apply_paths_env(paths)
    cmd = [tool_path(paths, "ansible-playbook"), str(playbook)]
    if extra:
        cmd.extend(extra)
    return subprocess.run(cmd, cwd=str(paths.spa_home)).returncode
