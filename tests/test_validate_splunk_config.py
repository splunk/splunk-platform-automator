"""Smoke checks for bin/validate_splunk_config.sh (no inventory/AWS)."""

import os
import subprocess

import pytest

pytestmark = pytest.mark.local

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(PROJECT_ROOT, "bin", "validate_splunk_config.sh")


def test_validate_script_bash_syntax():
    result = subprocess.run(["bash", "-n", SCRIPT], cwd=PROJECT_ROOT)
    assert result.returncode == 0


def test_validate_script_missing_config_fails():
    result = subprocess.run(
        [SCRIPT, os.path.join(PROJECT_ROOT, "does-not-exist.yml")],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "not found" in (result.stderr + result.stdout).lower()
