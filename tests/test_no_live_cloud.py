"""Non-aws tests never see live cloud credentials, so they cannot create hosts."""

import os
import subprocess
import sys

import pytest

from spa_testutil import LIVE_CLOUD_ENV_VARS, spa_env

pytestmark = [pytest.mark.local, pytest.mark.cli]


def test_in_process_tests_have_no_cloud_credentials():
    for name in LIVE_CLOUD_ENV_VARS:
        assert name not in os.environ, name
    assert os.environ["AWS_SHARED_CREDENTIALS_FILE"] == os.devnull
    assert os.environ["AWS_CONFIG_FILE"] == os.devnull
    assert os.environ["AWS_EC2_METADATA_DISABLED"] == "true"


def test_subprocess_spa_env_has_no_cloud_credentials(monkeypatch):
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "AKIAEXAMPLE")
    monkeypatch.setenv("AWS_PROFILE", "operator")
    monkeypatch.setenv("CCM_TOKEN", "example")
    monkeypatch.setenv("AWS_CONFIG_FILE", "/tmp/operator-aws-config")
    env = spa_env()
    for name in LIVE_CLOUD_ENV_VARS:
        assert name not in env, name
    assert env["AWS_SHARED_CREDENTIALS_FILE"] == os.devnull
    assert env["AWS_CONFIG_FILE"] == os.devnull
    assert env["AWS_EC2_METADATA_DISABLED"] == "true"


def test_boto3_finds_no_credentials():
    pytest.importorskip("boto3")
    probe = (
        "import boto3, sys; "
        "sys.exit(0 if boto3.session.Session().get_credentials() is None else 1)"
    )
    result = subprocess.run([sys.executable, "-c", probe], env=spa_env(), timeout=60)
    assert result.returncode == 0
