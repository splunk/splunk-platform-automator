"""How this spa binary was installed: prefix wrapper, git clone, or unknown."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Optional

InstallKind = str


def installer_wrapper_home(text: str) -> Optional[Path]:
    """SPA_HOME from an install.sh PATH wrapper, or None."""
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("export SPA_HOME="):
            continue
        raw = stripped[len("export SPA_HOME=") :]
        if len(raw) >= 2 and raw[0] == "'" and raw.endswith("'"):
            return Path(raw[1:-1].replace("'\\''", "'")).expanduser()
        if len(raw) >= 2 and raw[0] == '"' and raw.endswith('"'):
            return Path(raw[1:-1]).expanduser()
        if raw:
            return Path(raw).expanduser()
    return None


def installer_wrapper_targets(spa_bin: str, spa_home: Path) -> bool:
    """True when PATH spa is the install.sh wrapper for this SPA_HOME."""
    path = Path(spa_bin)
    try:
        if not path.is_file() or path.stat().st_size > 8192:
            return False
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    home = installer_wrapper_home(text)
    if home is None or "$SPA_HOME/bin/spa" not in text:
        return False
    try:
        return home.resolve() == spa_home.resolve()
    except OSError:
        return False


def _is_git_checkout(spa_home: Path) -> bool:
    """True when SPA_HOME is a git clone or worktree (`.git` file or directory)."""
    try:
        return (spa_home / ".git").exists()
    except OSError:
        return False


def _resolved_path_spa(spa_bin: Optional[str]) -> Optional[Path]:
    if spa_bin is None:
        found = shutil.which("spa")
        if not found:
            return None
        spa_bin = found
    try:
        return Path(spa_bin).resolve()
    except OSError:
        return None


def classify_install_kind(spa_home: Path, spa_bin: Optional[str] = None) -> InstallKind:
    """Return prefix, clone, or unknown from resolved SPA_HOME and PATH spa.

    Clone is checked first so an install.sh wrapper whose SPA_HOME is a git
    tree is never treated as a prefix. A symlink or hardlink to ``bin/spa``
    is never a prefix.
    """
    try:
        home = Path(spa_home).resolve()
    except OSError:
        return "unknown"
    path_spa = _resolved_path_spa(spa_bin)
    try:
        home_bin = (home / "bin" / "spa").resolve()
    except OSError:
        home_bin = home / "bin" / "spa"
    path_is_home_bin = path_spa is not None and path_spa == home_bin
    if _is_git_checkout(home):
        return "clone"
    if path_is_home_bin:
        return "unknown"
    if spa_bin is None:
        which = shutil.which("spa")
    else:
        which = spa_bin
    if which and installer_wrapper_targets(which, home):
        return "prefix"
    return "unknown"
