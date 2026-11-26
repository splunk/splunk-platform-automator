#!/usr/bin/env python3
"""List SA-/DA- app names and indexes.conf stanzas from an ES .spl/.tgz.

ES 8.x ships SA-/DA- under SplunkEnterpriseSecuritySuite (often install/),
not as top-level tar members. Walk nested paths and nested .spl/.tgz members.
Prints one JSON object: {"apps": [...], "indexes": [...]} (no secrets).
"""

from __future__ import annotations

import argparse
import io
import json
import os
import re
import sys
import tarfile

APPCONF_RE = re.compile(r"(?:^|/)((?:SA|DA)-[^/]+)/default/app\.conf$")
INDEXES_RE = re.compile(r"(?:^|/)((?:SA|DA)-[^/]+)/default/indexes\.conf$")
NESTED_ARCHIVE_RE = re.compile(r"\.(spl|tgz|tar\.gz)$", re.IGNORECASE)
NESTED_APP_NAME_RE = re.compile(r"(?:^|/)((?:SA|DA)-[^/]+)\.(spl|tgz|tar\.gz)$", re.IGNORECASE)
VERSION_SUFFIX_RE = re.compile(r"[-_]\d+\.\d+.*$")
SKIP_STANZAS = frozenset({"default"})
SKIP_PREFIXES = ("volume:", "source::", "host::")
MAX_DEPTH = 3


def canonical_sa_da_name(name: str) -> str:
    """Map nested ES 8.x archive stems (SA-Foo-8.8.0-build) to installed folder names."""
    return VERSION_SUFFIX_RE.sub("", name)


def _collect_index_stanzas(handle, names: set[str]) -> None:
    for line in handle.read().decode("utf-8", "replace").splitlines():
        stripped = line.strip()
        if not (stripped.startswith("[") and stripped.endswith("]")):
            continue
        stanza = stripped[1:-1].strip()
        if not stanza or stanza in SKIP_STANZAS or stanza.startswith(SKIP_PREFIXES):
            continue
        names.add(stanza)


def _open_nested(data: bytes):
    for mode in ("r:gz", "r:bz2", "r:"):
        try:
            return tarfile.open(fileobj=io.BytesIO(data), mode=mode)
        except tarfile.TarError:
            continue
    return None


def walk_archive(tf: tarfile.TarFile, apps: set[str], indexes: set[str], depth: int = 0) -> None:
    if depth > MAX_DEPTH:
        return
    for member in tf.getmembers():
        name = member.name.replace("\\", "/")
        match = APPCONF_RE.search(name)
        if match:
            apps.add(canonical_sa_da_name(match.group(1)))
        match = INDEXES_RE.search(name)
        if match:
            handle = tf.extractfile(member)
            if handle is not None:
                _collect_index_stanzas(handle, indexes)
        if not member.isfile() or depth >= MAX_DEPTH:
            continue
        nested_name = NESTED_APP_NAME_RE.search(name)
        if nested_name:
            apps.add(canonical_sa_da_name(nested_name.group(1)))
        if not NESTED_ARCHIVE_RE.search(name):
            continue
        handle = tf.extractfile(member)
        if handle is None:
            continue
        inner = _open_nested(handle.read())
        if inner is None:
            continue
        try:
            walk_archive(inner, apps, indexes, depth + 1)
        finally:
            inner.close()


def inventory_from_archive(archive: str) -> dict[str, list[str]]:
    apps: set[str] = set()
    indexes: set[str] = set()
    if archive and os.path.isfile(archive):
        try:
            with tarfile.open(archive, "r:*") as handle:
                walk_archive(handle, apps, indexes)
        except tarfile.TarError:
            pass
    return {"apps": sorted(apps), "indexes": sorted(indexes)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--archive",
        default=os.environ.get("SPA_ES_ARCHIVE", ""),
        help="Path to the ES .spl/.tgz (or SPA_ES_ARCHIVE)",
    )
    args = parser.parse_args(argv)
    json.dump(inventory_from_archive(args.archive), sys.stdout, separators=(",", ":"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
