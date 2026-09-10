#!/usr/bin/env python3
"""Extract one Keep-a-Changelog version section from CHANGELOG.md."""

from __future__ import annotations

import re
import sys
from pathlib import Path


def extract_notes(changelog: str, version: str) -> str:
    heading = re.compile(
        rf"^## \[{re.escape(version)}\](?:\([^)]*\))?(?:\s+-.*)?\s*$",
        re.MULTILINE,
    )
    match = heading.search(changelog)
    if not match:
        raise ValueError(f"No changelog section for version {version}")
    start = match.end()
    nxt = re.search(r"^## \[", changelog[start:], re.MULTILINE)
    body = changelog[start : start + nxt.start() if nxt else None].strip()
    if not body:
        raise ValueError(f"Changelog section for {version} is empty")
    return body


def main() -> int:
    if len(sys.argv) != 2 or sys.argv[1] in ("-h", "--help"):
        print(f"Usage: {sys.argv[0]} X.Y.Z", file=sys.stderr)
        return 2
    version = sys.argv[1]
    changelog = Path(__file__).resolve().parent.parent / "CHANGELOG.md"
    try:
        print(extract_notes(changelog.read_text(encoding="utf-8"), version))
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
