"""Session-level confirmation for mutating SPA operations.

Humans get an explicit Proceed? [y/N] that names the command and risk.
Agents and a GUI never call input(); they pass confirm=True (--yes).
Skills still invoke bin/spa only.
"""

from __future__ import annotations

import sys
from typing import Optional, Sequence


class ConfirmationError(Exception):
    """Caller declined, or agent/GUI omitted --yes / confirm=True."""


LIFECYCLE_RISK = {
    "provision": "mutating",
    "destroy": "destructive",
    "deploy": "mutating",
    "suspend": "mutating",
    "resume": "mutating",
}


def requires_confirmation(*, risk: Optional[str] = None, missing_metadata: bool = False) -> bool:
    """True unless first-party metadata says the playbook is read-only."""
    if missing_metadata or not risk:
        return True
    return risk != "read-only"


def prompt_text(label: str, *, risk: Optional[str] = None) -> str:
    """Human confirmation question. Default is no ([y/N])."""
    if risk == "destructive":
        consequence = "will permanently remove or uninstall resources"
    elif risk == "mutating":
        consequence = "will change hosts or configuration"
    else:
        consequence = "may change hosts (no playbook metadata)"
    return "%s %s. Proceed? [y/N] " % (label, consequence)


def ensure_confirmed(
    label: str,
    *,
    confirm: bool,
    agent: bool,
    details: Optional[Sequence[str]] = None,
    risk: Optional[str] = None,
) -> None:
    """No-op if confirm; fail in agent mode; otherwise prompt on stderr/stdin."""
    if confirm:
        return
    if agent:
        raise ConfirmationError("%s requires -y/--yes in agent mode." % label)
    for line in details or ():
        print(line, file=sys.stderr)
    answer = input(prompt_text(label, risk=risk))
    if answer.strip().lower() not in {"y", "yes"}:
        raise ConfirmationError("%s cancelled." % label)
