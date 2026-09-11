"""Pure-function tests for spa.aws (no live AWS)."""

import os
import sys

import pytest

pytestmark = pytest.mark.local

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lib"))

from spa import aws  # noqa: E402


@pytest.mark.parametrize(
    "ami,description,expected",
    [
        ("ubuntu/images/hvm-ssd/ubuntu-noble", "", "ubuntu"),
        ("debian-12-amd64", "Official Debian", "admin"),
        ("RHEL-10.0", "", "ec2-user"),
        ("al2023-ami", "", "ec2-user"),
    ],
)
def test_suggest_ssh_username(ami, description, expected):
    assert aws.suggest_ssh_username(ami, description) == expected


@pytest.mark.parametrize(
    "key,expected",
    [
        ("al2023", "amazon_linux"),
        ("ubuntu2404", "ubuntu"),
        ("rhel10", "rhel"),
        ("rhel", "rhel"),
        ("unknown_os", "unknown_os"),
    ],
)
def test_normalize_os_key(key, expected):
    assert aws.normalize_os_key(key) == expected


def test_valid_os_keys_and_rank():
    keys = aws.valid_os_keys()
    assert keys == ["rhel", "ubuntu", "amazon_linux", "debian"]
    assert aws.os_preference_rank("rhel") == 1
    assert aws.os_preference_rank("al2023") == 3
    assert aws.os_preference_rank("nope") is None


def test_discover_amazon_linux_ssm_path():
    names = [
        "/aws/service/ami-amazon-linux-latest/al2022-ami-kernel-default-x86_64",
        "/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64",
        "/aws/service/ami-amazon-linux-latest/amzn2-ami-hvm-x86_64-gp2",
    ]
    assert aws.discover_amazon_linux_ssm_path(names).endswith("al2023-ami-kernel-default-x86_64")
    assert aws.discover_amazon_linux_ssm_path([]) is None


def test_discover_ubuntu_ssm_path_prefers_latest_lts_gp3():
    names = [
        "/aws/service/canonical/ubuntu/server/22.04/stable/current/amd64/hvm/ebs-gp3/ami-id",
        "/aws/service/canonical/ubuntu/server/24.04/stable/current/amd64/hvm/ebs-gp2/ami-id",
        "/aws/service/canonical/ubuntu/server/24.04/stable/current/amd64/hvm/ebs-gp3/ami-id",
    ]
    chosen = aws.discover_ubuntu_ssm_path(names)
    assert "24.04" in chosen
    assert "ebs-gp3" in chosen
    assert aws.discover_ubuntu_ssm_path([]) is None


def test_parse_security_groups():
    assert aws.parse_security_groups(None) is None
    assert aws.parse_security_groups("") is None
    assert aws.parse_security_groups("Splunk_Basic, extra ; other") == ["Splunk_Basic", "extra", "other"]
