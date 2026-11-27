#!/usr/bin/env python3
"""Count essinstaller2.log ERROR lines since SPA's last essinstall stamp.

Read the current log only (rotated .1 files are ignored). Lines whose leading
timestamp is YYYY-MM-DD HH:MM:SS (optional ,mmm / .mmm) set the clock;
continuation lines inherit the previous time. ERROR lines at or after the
stamp are counted. Stamp missing or no parseable timestamps: count the whole
file (scope=whole_file). Missing log: MISSING.

Prints:
  MISSING
or:
  <count>
  scope=whole_file   (fallback only)
  <last redacted ERROR line>
"""

from __future__ import annotations

import argparse
import os
import re
import sys

TS_RE = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})(?:[,.]\d+)?")
AUTH_RE = re.compile(r"(?i)\bauth\S*")
ADMIN_RE = re.compile(r"(?i)\badmin:\S*")


def redact(line: str) -> str:
    return ADMIN_RE.sub("admin:***", AUTH_RE.sub("***", line))


def _stamp_value(since_file: str) -> str:
    if not since_file or not os.path.isfile(since_file):
        return ""
    try:
        raw = open(since_file, encoding="utf-8", errors="replace").read().strip()
    except OSError:
        return ""
    if not raw:
        return ""
    first = raw.splitlines()[0].strip()
    match = TS_RE.match(first)
    return match.group(1) if match else first[:19]


def scan_installer_log(log_path: str, since_file: str = "") -> dict[str, object]:
    if not log_path or not os.path.isfile(log_path):
        return {"status": "MISSING", "count": 0, "scope": "", "last_error": ""}
    try:
        text = open(log_path, encoding="utf-8", errors="replace").read()
    except OSError:
        return {"status": "MISSING", "count": 0, "scope": "", "last_error": ""}

    stamp = _stamp_value(since_file)
    current_ts = ""
    parsed_any = False
    timed: list[tuple[str, str]] = []
    for raw in text.splitlines():
        line = raw.rstrip("\n")
        match = TS_RE.match(line)
        if match:
            current_ts = match.group(1)
            parsed_any = True
        if "ERROR" not in line:
            continue
        timed.append((current_ts, line))

    if not stamp or not parsed_any:
        scope = "whole_file"
        selected = [line for _ts, line in timed]
    else:
        scope = "since_stamp"
        selected = [line for ts, line in timed if ts and ts >= stamp]

    last = redact(selected[-1]) if selected else ""
    return {
        "status": "ok",
        "count": len(selected),
        "scope": scope,
        "last_error": last,
    }


def format_scan_output(result: dict[str, object]) -> str:
    if result.get("status") == "MISSING":
        return "MISSING\n"
    lines = [str(int(result.get("count") or 0))]
    if result.get("scope") == "whole_file":
        lines.append("scope=whole_file")
    last = str(result.get("last_error") or "")
    if last:
        lines.append(last)
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--log", default="", help="Path to essinstaller2.log")
    parser.add_argument(
        "--since-file",
        default="",
        help="Path to SPA es_essinstall_started stamp (YYYY-MM-DD HH:MM:SS)",
    )
    args = parser.parse_args(argv)
    result = scan_installer_log(args.log, args.since_file)
    sys.stdout.write(format_scan_output(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
