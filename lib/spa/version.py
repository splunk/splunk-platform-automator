"""Installed SPA version from SPA_HOME/VERSION. GitHub compare is spa version check."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from spa.install_kind import classify_install_kind


def read_local_version(spa_home: Path) -> str:
    """Return the stripped VERSION file for this framework tree."""
    return (Path(spa_home) / "VERSION").read_text(encoding="utf-8").strip()


def local_payload(spa_home: Path, spa_bin: Optional[str] = None) -> Dict[str, Any]:
    home = Path(spa_home).resolve()
    return {
        "version": read_local_version(home),
        "spa_home": str(home),
        "install_kind": classify_install_kind(home, spa_bin),
    }


def format_version_text(data: Dict[str, Any]) -> str:
    return "spa %s\n" % (data.get("version") or "")


def local_version(spa_home: Path, spa_bin: Optional[str] = None):
    from spa.api import CommandResult

    try:
        data = local_payload(spa_home, spa_bin)
    except OSError as exc:
        return CommandResult(ok=False, error=str(exc), code=1)
    if not data["version"]:
        return CommandResult(
            ok=False,
            error="VERSION is empty in %s" % spa_home,
            code=1,
        )
    return CommandResult(ok=True, data=data)
