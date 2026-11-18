"""Splunk Platform Automator library.

The `spa` CLI and a future GUI use `open_session` / `LocalSpaSession`.
Skills and agents must call `bin/spa`, not this package.
"""

from spa.api import (
    SCHEMA_VERSION,
    CommandResult,
    LocalSpaSession,
    RemoteSessionNotImplemented,
    SpaSession,
    open_session,
)

__all__ = [
    "SCHEMA_VERSION",
    "CommandResult",
    "LocalSpaSession",
    "RemoteSessionNotImplemented",
    "SpaSession",
    "open_session",
    "paths",
]
