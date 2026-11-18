#!/usr/bin/env python3
"""Ansible inventory plugin shim — implementation lives in lib/spa/paths.py."""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[3]
_LIB = _ROOT / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from spa.paths import *  # noqa: F401,F403
from spa.paths import main

if __name__ == "__main__":
    raise SystemExit(main())
