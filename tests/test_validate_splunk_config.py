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


def test_aws_validate_argv_uses_named_action():
    from spa.validate import aws_validate_argv

    assert aws_validate_argv(
        {
            "region": "eu-central-1",
            "ami_id": "ami-abc",
            "key_name": "k",
            "instance_type": "t3.medium",
            "security_group_names": ["sg1", "sg2"],
        }
    ) == [
        "validate",
        "--region",
        "eu-central-1",
        "--ami-id",
        "ami-abc",
        "--key-name",
        "k",
        "--instance-type",
        "t3.medium",
        "--security-groups",
        "sg1,sg2",
    ]
