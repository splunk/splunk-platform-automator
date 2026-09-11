"""Cup-style agent detection and JSON envelope."""

from __future__ import annotations

import json
import os
import sys
from typing import Any, Dict, Optional


AGENT_ENV_VARS = (
    "SPA_AGENT",
    "CLAUDECODE",
    "CLAUDE_CODE",
    "CURSOR_AGENT",
    "CURSOR_TRACE_ID",
    "CODEX_THREAD_ID",
)


def detect_agent() -> bool:
    for name in AGENT_ENV_VARS:
        if (os.environ.get(name) or "").strip():
            return True
    return False


def agent_mode(force_agent: bool = False, force_human: bool = False) -> bool:
    if force_human:
        return False
    if force_agent:
        return True
    return detect_agent()


def envelope(ok: bool, data: Any = None, error: Optional[str] = None) -> Dict[str, Any]:
    payload: Dict[str, Any] = {"ok": ok}
    if data is not None:
        payload["data"] = data
    if error:
        payload["error"] = error
    return payload


def emit(ok: bool, data: Any = None, error: Optional[str] = None, as_agent: bool = False) -> None:
    if as_agent:
        sys.stdout.write(json.dumps(envelope(ok, data, error), indent=2, default=str) + "\n")
        return
    if error:
        print(error, file=sys.stderr)
    elif data is not None and not isinstance(data, str):
        print(json.dumps(data, indent=2, default=str))
    elif isinstance(data, str):
        print(data)


COMMAND_SCHEMA = {
    "name": "spa",
    "commands": [
        {"name": "init", "summary": "Scaffold or migrate an env dir"},
        {"name": "validate", "summary": "Validate splunk_config.yml"},
        {"name": "doctor", "summary": "Host prerequisite checks"},
        {"name": "env", "summary": "Print export statements for direnv"},
        {"name": "provision", "summary": "Terraform AWS provision playbook"},
        {"name": "deploy", "summary": "Deploy Splunk (deploy_site.yml)"},
        {"name": "destroy", "summary": "Destroy AWS hosts"},
        {"name": "shell", "summary": "SSH/SCP using inventory"},
        {"name": "aws", "summary": "AWS discovery for terraform.aws"},
        {"name": "licenses", "summary": "License file discovery"},
        {"name": "run", "summary": "Run an ansible playbook by stem"},
        {"name": "agent schema", "summary": "This schema"},
    ],
}
