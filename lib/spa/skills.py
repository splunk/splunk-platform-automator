"""Install and remove SPA agent skills in user IDE directories.

Canonical packages live under ``$SPA_HOME/skills/spa/``. Install links each
package into the user skill directory for the chosen IDE. Detection follows
cup: an explicit platform, then ``SPA_SKILLS_PLATFORMS``, then one agent
environment variable, one IDE binary on ``PATH``, or one existing skill
directory.
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import yaml


class SkillsError(Exception):
    """Usage or detection failure. ``code`` 2 is a usage error."""

    def __init__(self, message: str, code: int = 2) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class PlatformSpec:
    name: str
    aliases: Tuple[str, ...]
    user_skills: str
    path_bins: Tuple[str, ...]
    env_vars: Tuple[str, ...]


PLATFORMS: Tuple[PlatformSpec, ...] = (
    PlatformSpec("claude-code", ("claude",), ".claude/skills", ("claude",), ("CLAUDECODE", "CLAUDE_CODE")),
    PlatformSpec("cursor", (), ".cursor/skills", ("cursor",), ("CURSOR_AGENT",)),
    PlatformSpec("codex", (), ".codex/skills", ("codex",), ("CODEX", "OPENAI_CODEX")),
    PlatformSpec("opencode", (), ".config/opencode/skills", ("opencode",), ("OPENCODE",)),
    PlatformSpec("windsurf", (), ".windsurf/skills", ("windsurf",), ("WINDSURF_AGENT",)),
    PlatformSpec("gemini-code", ("gemini",), ".gemini/skills", (), ("GEMINI_CODE_ASSIST",)),
    PlatformSpec("pi", ("pi-dev",), ".pi/agent/skills", (), ("PI_CODING_AGENT",)),
    PlatformSpec("antigravity", ("agy",), ".gemini/config/skills", ("agy",), ("ANTIGRAVITY",)),
)

# First truthy variable wins. Names that are not install platforms fall through
# to PATH and skill directories, matching cup.
_ENV_DETECTORS: Tuple[Tuple[str, Tuple[str, ...]], ...] = (
    ("claude-code", ("CLAUDECODE", "CLAUDE_CODE")),
    ("cursor", ("CURSOR_AGENT",)),
    ("codex", ("CODEX", "OPENAI_CODEX")),
    ("opencode", ("OPENCODE",)),
    ("aider", ("AIDER",)),
    ("cline", ("CLINE",)),
    ("windsurf", ("WINDSURF_AGENT",)),
    ("github-copilot", ("GITHUB_COPILOT",)),
    ("amazon-q", ("AMAZON_Q", "AWS_Q_DEVELOPER")),
    ("gemini-code", ("GEMINI_CODE_ASSIST",)),
    ("antigravity", ("ANTIGRAVITY",)),
    ("sourcegraph-cody", ("SRC_CODY",)),
    ("pi", ("PI_CODING_AGENT",)),
    ("generic-agent", ("AGENT",)),
)

_ENV_PLATFORMS = "SPA_SKILLS_PLATFORMS"


def lookup_platform(name: str) -> Optional[PlatformSpec]:
    key = (name or "").strip().lower()
    if not key:
        return None
    for spec in PLATFORMS:
        if key == spec.name or key in spec.aliases:
            return spec
    return None


def supported_platform_list() -> str:
    parts = []
    for spec in PLATFORMS:
        if spec.aliases:
            parts.append("%s (%s)" % (spec.name, ", ".join(spec.aliases)))
        else:
            parts.append(spec.name)
    return ", ".join(parts)


def discover_packages(source: Path) -> List[str]:
    """Child directories of ``source`` that contain ``SKILL.md``."""
    if not source.is_dir():
        return []
    names = []
    for child in sorted(source.iterdir(), key=lambda path: path.name):
        if child.name.startswith(".") or child.name in {".", ".."}:
            continue
        if not child.is_dir():
            continue
        if (child / "SKILL.md").is_file():
            names.append(child.name)
    return names


def install_skills(
    *,
    source: Path,
    home: Path,
    platform: Optional[str] = None,
    name: Optional[str] = None,
    all_packages: bool = False,
    environ: Optional[Dict[str, str]] = None,
    path_env: Optional[str] = None,
    config_dir: Optional[Path] = None,
) -> dict:
    packages = _select_packages(source, name=name, all_packages=all_packages)
    env = environ if environ is not None else os.environ
    platforms, via = resolve_platforms(platform, home=home, environ=env, path_env=_path_value(env, path_env))
    copies = _load_copies(_skills_yml(config_dir, env))
    replaced = []
    for plat in platforms:
        root = _skills_root(home, plat)
        root.mkdir(parents=True, exist_ok=True)
        for package in packages:
            dest = root / package
            if _place_package(source / package, dest, copies):
                replaced.append(package)
    _save_copies(_skills_yml(config_dir, env), copies)
    return {
        "action": "install",
        "platforms": platforms,
        "detectedVia": via,
        "installed": list(packages),
        "replaced": replaced,
    }


def remove_skills(
    *,
    source: Path,
    home: Path,
    platform: Optional[str] = None,
    name: Optional[str] = None,
    all_packages: bool = False,
    environ: Optional[Dict[str, str]] = None,
    path_env: Optional[str] = None,
    config_dir: Optional[Path] = None,
) -> dict:
    packages = _select_packages(source, name=name, all_packages=all_packages)
    env = environ if environ is not None else os.environ
    platforms, via = resolve_platforms(platform, home=home, environ=env, path_env=_path_value(env, path_env))
    record = _skills_yml(config_dir, env)
    copies = _load_copies(record)
    removed = []
    for plat in platforms:
        root = _skills_root(home, plat)
        for package in packages:
            dest = root / package
            if _delete_package(dest, copies) and package not in removed:
                removed.append(package)
    _save_copies(record, copies)
    return {
        "action": "remove",
        "platforms": platforms,
        "detectedVia": via,
        "removed": removed,
    }


def resolve_platforms(
    platform: Optional[str],
    *,
    home: Path,
    environ: Dict[str, str],
    path_env: str,
) -> Tuple[List[str], str]:
    raw = (platform or "").strip()
    if raw:
        names = _parse_platform_list(raw, source="argument")
        if not names:
            raise SkillsError(
                "unknown platform: '%s'. Supported: %s, or `all`." % (raw, supported_platform_list()),
                code=2,
            )
        return names, "explicit"

    from_env = _platforms_from_env(environ.get(_ENV_PLATFORMS))
    if from_env is not None:
        return from_env, "env_platforms"

    agent = _agent_platform(environ)
    if agent:
        return [agent], "env"

    path_hits = _path_hits(path_env)
    if len(path_hits) == 1:
        return path_hits, "path"
    dir_hits = _dir_hits(home)
    if len(dir_hits) == 1:
        return dir_hits, "skills_dir"
    raise _detect_error(path_hits, dir_hits)


def format_skills_text(data: dict) -> str:
    platforms = ", ".join(data.get("platforms") or [])
    via = data.get("detectedVia") or ""
    if data.get("action") == "install":
        names = ", ".join(data.get("installed") or []) or "nothing"
        return "Installed %s on %s (%s)\n" % (names, platforms, via)
    names = ", ".join(data.get("removed") or []) or "nothing"
    return "Removed %s on %s (%s)\n" % (names, platforms, via)


def _select_packages(source: Path, *, name: Optional[str], all_packages: bool) -> List[str]:
    if name and all_packages:
        raise SkillsError("pass --name or --all, not both.", code=2)
    found = discover_packages(source)
    if not found:
        raise SkillsError("no SPA skills found under %s" % source, code=1)
    if name:
        if name not in found:
            raise SkillsError(
                "unknown skill '%s'. Packages: %s." % (name, ", ".join(found)),
                code=2,
            )
        return [name]
    return found


def _platforms_from_env(raw: Optional[str]) -> Optional[List[str]]:
    if raw is None or not raw.strip():
        return None
    names = _parse_platform_list(raw, source=_ENV_PLATFORMS)
    if not names:
        return None
    return sorted(names)


def _parse_platform_list(raw: str, *, source: str) -> List[str]:
    """Split a comma-separated platform list. ``all`` means every platform."""
    text = raw.strip()
    if text.lower() == "all" or any(part.strip().lower() == "all" for part in text.split(",")):
        return [spec.name for spec in PLATFORMS]
    names: List[str] = []
    for part in text.split(","):
        part = part.strip()
        if not part:
            continue
        spec = lookup_platform(part)
        if spec is None:
            if source == _ENV_PLATFORMS:
                raise SkillsError(
                    "unknown platform in %s: '%s'. Supported: %s."
                    % (_ENV_PLATFORMS, part, supported_platform_list()),
                    code=2,
                )
            raise SkillsError(
                "unknown platform: '%s'. Supported: %s, or `all`." % (part, supported_platform_list()),
                code=2,
            )
        if spec.name not in names:
            names.append(spec.name)
    return names


def _agent_platform(environ: Dict[str, str]) -> Optional[str]:
    for name, keys in _ENV_DETECTORS:
        if any(_truthy(environ.get(key)) for key in keys):
            spec = lookup_platform(name)
            return spec.name if spec is not None else None
    return None


def _truthy(value: Optional[str]) -> bool:
    if value is None:
        return False
    return value.strip().lower() in {"1", "true", "yes"}


def _path_value(environ: Dict[str, str], path_env: Optional[str]) -> str:
    if path_env is not None:
        return path_env
    return environ.get("PATH") or ""


def _path_hits(path_env: str) -> List[str]:
    directories = [part for part in path_env.split(os.pathsep) if part]
    hits = []
    for spec in PLATFORMS:
        if spec.path_bins and _find_bin(directories, spec.path_bins):
            hits.append(spec.name)
    return hits


def _find_bin(directories: Sequence[str], names: Iterable[str]) -> bool:
    for directory in directories:
        for name in names:
            candidate = Path(directory) / name
            if candidate.is_file():
                return True
            if os.name == "nt" and (Path(directory) / ("%s.exe" % name)).is_file():
                return True
    return False


def _dir_hits(home: Path) -> List[str]:
    hits = []
    for spec in PLATFORMS:
        if _has_skill_content(_join(home, spec.user_skills)):
            hits.append(spec.name)
    return hits


def _has_skill_content(root: Path) -> bool:
    if not root.is_dir():
        return False
    if (root / "SKILL.md").is_file():
        return True
    try:
        children = list(root.iterdir())
    except OSError:
        return False
    for child in children:
        if (child / "SKILL.md").is_file():
            return True
    return False


def _detect_error(path_hits: Sequence[str], dir_hits: Sequence[str]) -> SkillsError:
    parts = ["could not auto-detect AI assistant platform."]
    if len(path_hits) > 1:
        parts.append("Multiple IDE CLIs on PATH: %s." % ", ".join(path_hits))
    if len(dir_hits) > 1:
        parts.append("Multiple installed skill directories found: %s." % ", ".join(dir_hits))
    detected: List[str] = []
    for name in list(path_hits) + list(dir_hits):
        if name not in detected:
            detected.append(name)
    if detected:
        parts.append("Install per IDE:")
        for name in detected:
            parts.append("spa skills install %s" % name)
        parts.append("Or in this shell: export %s=%s" % (_ENV_PLATFORMS, ",".join(detected)))
    parts.append("Specify a platform explicitly: %s, or `all`." % supported_platform_list())
    return SkillsError(" ".join(parts), code=2)


def _skills_root(home: Path, platform: str) -> Path:
    spec = lookup_platform(platform)
    if spec is None:
        raise SkillsError("unknown platform: '%s'." % platform, code=2)
    return _join(home, spec.user_skills)


def _join(home: Path, relative: str) -> Path:
    dest = home
    for part in relative.split("/"):
        if part:
            dest = dest / part
    return dest


def _place_package(source: Path, dest: Path, copies: set) -> bool:
    """Link ``source`` at ``dest``. Return True when an existing path was replaced."""
    replaced = False
    if dest.is_symlink():
        try:
            same = dest.resolve() == source.resolve()
        except OSError:
            same = False
        if same:
            copies.discard(str(dest))
            return False
        dest.unlink()
        replaced = True
    elif dest.exists():
        if dest.is_dir():
            shutil.rmtree(dest)
        else:
            dest.unlink()
        replaced = True
    try:
        os.symlink(str(source.resolve()), str(dest), target_is_directory=True)
    except OSError:
        shutil.copytree(source, dest)
        copies.add(str(dest))
        return replaced
    copies.discard(str(dest))
    return replaced


def _delete_package(dest: Path, copies: set) -> bool:
    """Delete one package path. A symlink is unlinked and not followed."""
    if dest.is_symlink():
        dest.unlink()
        copies.discard(str(dest))
        return True
    if not dest.exists():
        copies.discard(str(dest))
        return False
    if dest.is_dir():
        shutil.rmtree(dest)
    else:
        dest.unlink()
    copies.discard(str(dest))
    return True


def _skills_yml(config_dir: Optional[Path], environ: Dict[str, str]) -> Path:
    if config_dir is not None:
        return Path(config_dir) / "skills.yml"
    from spa.paths import user_spa_config_dir

    return user_spa_config_dir(environ) / "skills.yml"


def _load_copies(path: Path) -> set:
    if not path.is_file():
        return set()
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return set()
    if not isinstance(data, dict):
        return set()
    items = data.get("copies") or []
    if not isinstance(items, list):
        return set()
    return {str(item) for item in items if item}


def _save_copies(path: Path, copies: set) -> None:
    if not copies:
        if path.is_file():
            path.unlink()
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "copies": sorted(copies),
    }
    text = yaml.safe_dump(payload, sort_keys=False)
    path.write_text("# SPA skill copies. Not secrets.\n" + text, encoding="utf-8")
