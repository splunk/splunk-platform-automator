"""Smoke checks for spa validate (no inventory/AWS)."""

import pytest

from spa_testutil import PROJECT_ROOT, run_spa

pytestmark = pytest.mark.local


def test_validate_help():
    result = run_spa(["validate", "--help"])
    assert result.returncode == 0
    assert "splunk_config" in result.stdout.lower() or "validate" in result.stdout.lower()


def test_validate_rejects_a_positional_config_file():
    result = run_spa(["validate", "splunk_config.yml"])
    assert result.returncode == 2
    assert "unrecognized arguments" in result.stderr


def test_validate_missing_config_fails():
    result = run_spa(["validate", "--config", str(PROJECT_ROOT / "does-not-exist.yml")])
    assert result.returncode != 0
    assert "not found" in (result.stderr + result.stdout).lower()
