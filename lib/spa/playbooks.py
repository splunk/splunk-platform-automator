"""Resolve and run Ansible playbooks for `spa run` / provision / deploy / destroy."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import subprocess

import yaml

from spa.executil import apply_paths_env, tool_path
from spa.paths import SpaPaths, load_spa_yml, resolve_spa_paths

METADATA_SCHEMA = 1
CATEGORIES = frozenset({"deployment", "operations", "upgrade", "verification", "infrastructure"})
RISKS = frozenset({"read-only", "mutating", "destructive"})

# 2.x / pre-3.0 stems → 3.0 names. Catalog lists the new stem only.
LEGACY_STEMS = {
    "start_splunk": "splunk_start",
    "stop_splunk": "splunk_stop",
    "restart_splunk": "splunk_restart",
    "run_splunk_command": "splunk_cli",
    "call_splunk_rest": "splunk_rest",
    "install_splunk": "splunk_install",
    "remove_splunk": "splunk_remove",
    "enable_splunkweb": "splunk_web_enable",
    "disable_stop_splunkweb": "splunk_web_disable",
    "add_splunk_license": "splunk_license",
    "backup_splunk_etc": "splunk_backup_etc",
    "cleanup_backup_dir": "splunk_backup_cleanup",
    "update_splunk_certs_web": "splunk_certs_web",
    "update_splunk_certs_inputs": "splunk_certs_inputs",
    "setup_splunk_roles": "splunk_setup_roles",
    "setup_splunk_conf": "splunk_setup_conf",
    "upgrade_splunk_shc_rolling": "upgrade_shc_rolling",
    "upgrade_splunk_idxc_rolling": "upgrade_idxc_rolling",
    "upgrade_splunk_dist_env": "upgrade_distributed",
    "provision_terraform_aws": "aws_provision",
    "destroy_terraform_aws": "aws_destroy",
    "wait_for_terraform_aws_hosts": "aws_wait_hosts",
    "deploy_splunk_apps": "splunk_apps_deploy",
    "remove_splunk_apps": "splunk_apps_remove",
    "run_apps_playbook": "splunk_apps_playbook_run",
    "install_ssh_keys": "ssh_keys",
    "test_ansible_prereqs": "ansible_check",
}


class PlaybookError(Exception):
    pass


class MetadataError(PlaybookError):
    """The # spa-run: comment block is missing required fields or invalid."""


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


def _stem_of(raw: str) -> str:
    name = Path(raw.strip()).name
    if name.endswith(".yml") or name.endswith(".yaml"):
        return Path(name).stem
    return name


def rewrite_legacy_name(raw: str) -> Tuple[str, Optional[str]]:
    """Map a pre-3.0 stem or ansible/<old>.yml path to the current name."""
    stripped = raw.strip()
    stem = _stem_of(stripped)
    new_stem = LEGACY_STEMS.get(stem)
    if not new_stem:
        return stripped, None
    path = Path(stripped)
    suffix = path.suffix if path.suffix in {".yml", ".yaml"} else ""
    if len(path.parts) > 1:
        rewritten = str(path.with_name(new_stem + (suffix or path.suffix)))
        if not suffix and not path.suffix:
            rewritten = str(Path(*path.parts[:-1]) / new_stem)
        return rewritten, stem
    return new_stem + suffix, stem


def parse_playbook_metadata(path: Path) -> Optional[Dict[str, Any]]:
    """Parse the leading # spa-run: YAML comment. None if the block is absent."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise MetadataError("Cannot read %s: %s" % (path, exc)) from exc
    block = _spa_run_comment_yaml(text)
    if block is None:
        return None
    try:
        loaded = yaml.safe_load(block)
    except yaml.YAMLError as exc:
        raise MetadataError("Invalid spa-run metadata in %s: %s" % (path, exc)) from exc
    if not isinstance(loaded, dict) or "spa-run" not in loaded:
        raise MetadataError("spa-run metadata in %s must be a mapping under spa-run:" % path)
    data = loaded["spa-run"]
    if not isinstance(data, dict):
        raise MetadataError("spa-run metadata in %s must be a mapping" % path)
    return _validate_metadata(data, path)


def _spa_run_comment_yaml(text: str) -> Optional[str]:
    lines = text.splitlines()
    index = 0
    if lines and lines[0].strip() == "---":
        index = 1
    body: List[str] = []
    in_block = False
    for line in lines[index:]:
        if line.strip() == "":
            if in_block:
                body.append("")
            continue
        if not line.lstrip().startswith("#"):
            break
        rest = line.lstrip()[1:]
        if rest.startswith(" "):
            rest = rest[1:]
        if not in_block:
            if rest.strip().startswith("spa-run:"):
                in_block = True
                body.append("spa-run:")
                after = rest.split("spa-run:", 1)[1]
                if after.strip():
                    body.append(after)
            continue
        if rest.startswith(" ") or rest.startswith("\t") or rest.strip() == "":
            body.append(rest)
            continue
        break
    if not in_block:
        return None
    return "\n".join(body)


def _validate_metadata(data: Dict[str, Any], path: Path) -> Dict[str, Any]:
    schema = data.get("schema")
    if schema != METADATA_SCHEMA:
        raise MetadataError(
            "%s: spa-run schema must be %s, got %r" % (path, METADATA_SCHEMA, schema)
        )
    summary = data.get("summary")
    description = data.get("description")
    category = data.get("category")
    risk = data.get("risk")
    if not isinstance(summary, str) or not summary.strip():
        raise MetadataError("%s: spa-run.summary is required" % path)
    if not isinstance(description, str) or not description.strip():
        raise MetadataError("%s: spa-run.description is required" % path)
    if category not in CATEGORIES:
        raise MetadataError(
            "%s: spa-run.category must be one of %s" % (path, ", ".join(sorted(CATEGORIES)))
        )
    if risk not in RISKS:
        raise MetadataError("%s: spa-run.risk must be one of %s" % (path, ", ".join(sorted(RISKS))))
    out: Dict[str, Any] = {
        "schema": schema,
        "summary": summary.strip(),
        "description": description.strip(),
        "category": category,
        "risk": risk,
    }
    requires = data.get("requires")
    if requires is not None:
        if not isinstance(requires, list) or not all(isinstance(item, str) for item in requires):
            raise MetadataError("%s: spa-run.requires must be a list of strings" % path)
        out["requires"] = requires
    inputs = data.get("inputs")
    if inputs is not None:
        if not isinstance(inputs, list):
            raise MetadataError("%s: spa-run.inputs must be a list" % path)
        out["inputs"] = inputs
    examples = data.get("examples")
    if examples is not None:
        if not isinstance(examples, list) or not all(isinstance(item, str) for item in examples):
            raise MetadataError("%s: spa-run.examples must be a list of strings" % path)
        out["examples"] = examples
    return out


def _row_from_stem(stem: str, source: str, path: Path, require_meta: bool) -> Dict[str, Any]:
    row: Dict[str, Any] = {"name": stem, "source": source, "path": str(path)}
    meta = parse_playbook_metadata(path)
    if meta is None:
        row["metadata"] = None
        row["missing"] = True
        if require_meta:
            raise MetadataError("Missing # spa-run: metadata in %s" % path)
        return row
    row["missing"] = False
    row["metadata"] = meta
    row["summary"] = meta["summary"]
    row["category"] = meta["category"]
    row["risk"] = meta["risk"]
    return row


def catalog(paths: SpaPaths, extra_dir: Optional[str] = None) -> List[Dict[str, Any]]:
    extra = [extra_dir] if extra_dir else None
    rows = []
    for stem, source, path in list_framework_stems(paths.spa_home):
        rows.append(_row_from_stem(stem, source, path, require_meta=True))
    for stem, source, path in list_env_stems(paths.spa_env_dir, extra):
        rows.append(_row_from_stem(stem, source, path, require_meta=False))
    return rows


def describe(
    name: str,
    paths: Optional[SpaPaths] = None,
    extra_dir: Optional[str] = None,
) -> Dict[str, Any]:
    """Resolve a playbook and return metadata without running Ansible."""
    paths = paths or resolve_spa_paths()
    path, renamed_from, canonical = resolve_named(name, paths, extra_dir=extra_dir)
    source = "env"
    try:
        path.resolve().relative_to((paths.spa_home / "ansible" / "verification").resolve())
        source = "verification"
    except ValueError:
        try:
            path.resolve().relative_to((paths.spa_home / "ansible").resolve())
            source = "ansible"
        except ValueError:
            source = "env"
    require = source in {"ansible", "verification"}
    row = _row_from_stem(canonical, source, path, require_meta=require)
    if renamed_from:
        row["renamed_from"] = renamed_from
        row["use"] = canonical
    return row


def resolve_named(
    name: str,
    paths: Optional[SpaPaths] = None,
    extra_dir: Optional[str] = None,
) -> Tuple[Path, Optional[str], str]:
    """Return (path, legacy_stem_or_None, canonical_stem)."""
    paths = paths or resolve_spa_paths()
    rewritten, renamed_from = rewrite_legacy_name(name)
    found = _resolve_path(rewritten, paths, extra_dir=extra_dir)
    return found, renamed_from, _catalog_name(found, paths)


def _catalog_name(path: Path, paths: SpaPaths) -> str:
    ansible = (paths.spa_home / "ansible").resolve()
    resolved = path.resolve()
    try:
        rel = resolved.relative_to(ansible)
    except ValueError:
        try:
            rel = resolved.relative_to(paths.spa_env_dir.resolve())
            return str(rel.with_suffix(""))
        except ValueError:
            return path.stem
    if rel.parent.name == "verification" or str(rel).startswith("verification/"):
        return "verification/" + rel.stem
    return rel.stem


def resolve(name: str, paths: Optional[SpaPaths] = None, extra_dir: Optional[str] = None) -> Path:
    found, _renamed, _canonical = resolve_named(name, paths, extra_dir=extra_dir)
    return found


def _resolve_path(name: str, paths: SpaPaths, extra_dir: Optional[str] = None) -> Path:
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


def run_playbook(
    playbook: Path,
    paths: SpaPaths,
    extra: Optional[List[str]] = None,
    on_progress: Optional[Callable[[Dict[str, str]], None]] = None,
) -> int:
    apply_paths_env(paths)
    cmd = [tool_path(paths, "ansible-playbook"), str(playbook)]
    if extra:
        cmd.extend(extra)
    if on_progress is None:
        return subprocess.run(cmd, cwd=str(paths.spa_home)).returncode
    proc = subprocess.Popen(
        cmd,
        cwd=str(paths.spa_home),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    assert proc.stdout is not None
    for line in proc.stdout:
        on_progress({"type": "line", "stream": "stdout", "line": line.rstrip("\n")})
    return proc.wait()
