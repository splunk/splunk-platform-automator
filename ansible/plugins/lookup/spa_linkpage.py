"""Configured license rows and CCM TTL for the architecture host page."""

from __future__ import annotations

import sys
from pathlib import Path

from ansible.plugins.lookup import LookupBase

_ROOT = Path(__file__).resolve().parents[3]
_LIB = _ROOT / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from spa.linkpage import snapshot_extras


class LookupModule(LookupBase):
    def run(self, terms, variables=None, **kwargs):
        extras = snapshot_extras()
        term = str((terms or ["all"])[0] or "all")
        if term == "licenses":
            return list(extras.get("linkpage_licenses") or [])
        if term in ("ccm_ttl", "linkpage_ccm_ttl"):
            return [extras.get("linkpage_ccm_ttl") or ""]
        return [extras]
