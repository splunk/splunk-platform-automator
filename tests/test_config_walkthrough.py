"""The clustered ITSI walkthrough documents the unset-lookup error."""

from __future__ import annotations

import os
import re
import subprocess
import sys

import pytest

from spa_testutil import LIB, PROJECT_ROOT

pytestmark = pytest.mark.local

_TEXT = re.compile(r"```text\n(.*?)```", re.S)


def _walkthrough() -> str:
    return (PROJECT_ROOT / "docs" / "config-walkthrough.md").read_text(encoding="utf-8")


def test_walkthrough_documents_the_unset_lookup_error():
    """The documented error is produced without changing this process environment."""
    documented = _TEXT.search(_walkthrough()).group(1).strip()
    script = """
import os
for name in ("SPLUNK_IDXC_PASSWORD", "SPLUNK_ADMIN_PASSWORD", "SPLUNK_SHC_PASSWORD"):
    os.environ.pop(name, None)
from spa.preflight import unresolved_env_message
print(unresolved_env_message({
    "splunk_defaults": {"splunk_admin_password": "{{ lookup('env', 'SPLUNK_ADMIN_PASSWORD') }}"},
    "splunk_idxclusters": [{"idxc_password": "{{ lookup('env', 'SPLUNK_IDXC_PASSWORD') }}"}],
    "splunk_shclusters": [{"shc_password": "{{ lookup('env', 'SPLUNK_SHC_PASSWORD') }}"}],
}))
"""
    child_env = {
        "PATH": os.environ.get("PATH", ""),
        "PYTHONPATH": str(LIB),
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        env=child_env,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == documented
    assert "SPLUNK_ADMIN_PASSWORD" in _walkthrough()
    assert "SPLUNKBASE_USERNAME" in _walkthrough()
    assert "SPLUNKBASE_PASSWORD" in _walkthrough()
