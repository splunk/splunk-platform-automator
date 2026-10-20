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


def test_retired_list_flags_exit_before_any_aws_call(monkeypatch, capsys):
    def _boom(*_args, **_kwargs):
        raise AssertionError("AWS session must not be created")

    monkeypatch.setattr(aws, "_session", _boom)
    for flag, kind in (
        ("--list-regions", "regions"),
        ("--list-amis", "amis"),
        ("--list-instance-types", "instance-types"),
        ("--list-key-pairs", "key-pairs"),
        ("--list-security-groups", "security-groups"),
    ):
        with pytest.raises(SystemExit) as excinfo:
            aws.main([flag])
        assert excinfo.value.code == 2
        captured = capsys.readouterr()
        assert captured.out == ""
        assert "Listing %s is: spa aws list %s" % (kind, kind) in captured.err


def test_list_kind_parsers_scope_flags_and_skip_aws_without_region(monkeypatch, capsys):
    def _boom(*_args, **_kwargs):
        raise AssertionError("AWS session must not be created")

    monkeypatch.setattr(aws, "_session", _boom)
    listed = aws.build_parser().parse_args(["list", "regions", "--json"])
    assert listed.aws_list_kind == "regions"
    assert listed.json is True
    amis = aws.build_parser().parse_args(
        ["list", "amis", "--region", "eu-central-1", "--name-filter", "custom*", "--json"]
    )
    assert amis.region == "eu-central-1"
    assert amis.name_filter == "custom*"
    assert amis.json is True
    inherited = aws.build_parser().parse_args(
        ["--region", "eu-central-1", "list", "instance-types", "--family", "t3"]
    )
    assert inherited.region == "eu-central-1"
    assert inherited.family == "t3"
    code = aws.main(["list", "amis"])
    assert code == 2
    assert "--region is required for spa aws list amis" in capsys.readouterr().err
    with pytest.raises(SystemExit) as family:
        aws.build_parser().parse_args(["list", "amis", "--region", "eu-central-1", "--family", "t3"])
    assert family.value.code == 2


def test_parse_security_groups():
    assert aws.parse_security_groups(None) is None
    assert aws.parse_security_groups("") is None
    assert aws.parse_security_groups("Splunk_Basic, extra ; other") == ["Splunk_Basic", "extra", "other"]
