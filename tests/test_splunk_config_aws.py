"""Pure-function tests for spa.aws (no live AWS)."""

import json
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
        assert "Listing %s is: spa aws %s list" % (kind, kind) in captured.err


def test_list_kind_parsers_scope_flags_and_skip_aws_without_region(monkeypatch, capsys, tmp_path):
    def _boom(*_args, **_kwargs):
        raise AssertionError("AWS session must not be created")

    monkeypatch.setattr(aws, "_session", _boom)
    listed = aws.build_parser().parse_args(["regions", "list", "--json"])
    assert listed.aws_list_kind == "regions"
    assert listed.json is True
    amis = aws.build_parser().parse_args(
        ["amis", "list", "--region", "eu-central-1", "--name-filter", "custom*", "--json"]
    )
    assert amis.region == "eu-central-1"
    assert amis.name_filter == "custom*"
    assert amis.json is True
    inherited = aws.build_parser().parse_args(
        ["--region", "eu-central-1", "instance-types", "list", "--family", "t3"]
    )
    assert inherited.region == "eu-central-1"
    assert inherited.family == "t3"
    _aws_config(monkeypatch, tmp_path)
    code = aws.main(["amis", "list"])
    assert code == 2
    assert "--region is required for spa aws amis list" in capsys.readouterr().err
    with pytest.raises(SystemExit) as family:
        aws.build_parser().parse_args(["amis", "list", "--region", "eu-central-1", "--family", "t3"])
    assert family.value.code == 2


def _aws_config(monkeypatch, tmp_path, region=None):
    path = tmp_path / "config"
    path.write_text("[default]\nregion = %s\n" % region if region else "")
    monkeypatch.setenv("AWS_CONFIG_FILE", str(path))
    monkeypatch.setenv("AWS_SHARED_CREDENTIALS_FILE", str(tmp_path / "credentials"))
    for name in ("AWS_REGION", "AWS_DEFAULT_REGION", "AWS_PROFILE", "AWS_DEFAULT_PROFILE"):
        monkeypatch.delenv(name, raising=False)


class _FakeRegions:
    def describe_regions(self, AllRegions=False):
        return {
            "Regions": [
                {"RegionName": "us-east-1", "Endpoint": "ec2.us-east-1.amazonaws.com"},
                {"RegionName": "eu-central-1", "Endpoint": "ec2.eu-central-1.amazonaws.com"},
            ]
        }


class _FakeRegionSession:
    def client(self, service, region_name=None):
        return _FakeRegions()


def test_list_regions_marks_the_region_from_the_aws_config(monkeypatch, capsys, tmp_path):
    _aws_config(monkeypatch, tmp_path, "eu-central-1")
    monkeypatch.setattr(aws, "_session", lambda region=None: _FakeRegionSession())

    assert aws.main(["regions", "list"]) == 0
    captured = capsys.readouterr()
    assert captured.out.startswith("{") is False
    assert "Using region eu-central-1 from ~/.aws/config (profile default)." in captured.err
    assert "Using region" not in captured.out
    assert "eu-central-1  selected" in captured.out
    assert "us-east-1" in captured.out

    assert aws.main(["regions", "list", "--json"]) == 0
    captured = capsys.readouterr()
    assert "Using region" not in captured.err
    assert captured.err == ""
    payload = json.loads(captured.out)
    assert payload["region"] == "eu-central-1"
    assert payload["region_source"] == "aws-config"
    assert payload["profile"] == "default"
    assert [item for item in payload["items"] if item.get("selected")] == [
        {
            "name": "eu-central-1",
            "endpoint": "ec2.eu-central-1.amazonaws.com",
            "selected": True,
        }
    ]

    assert aws.main(["regions", "list"], as_agent=True) == 0
    captured = capsys.readouterr()
    assert captured.err == ""
    assert json.loads(captured.out)["region_source"] == "aws-config"


def test_config_region_does_not_require_boto3(monkeypatch, tmp_path):
    _aws_config(monkeypatch, tmp_path, "eu-central-1")
    monkeypatch.setattr(aws, "boto3", None)
    resolved = aws.resolve_region()
    assert resolved.region == "eu-central-1"
    assert resolved.source == "aws-config"
    assert resolved.profile == "default"

    named = tmp_path / "named"
    named.write_text("[profile lab]\nregion = us-west-2\n", encoding="utf-8")
    monkeypatch.setenv("AWS_CONFIG_FILE", str(named))
    monkeypatch.setenv("AWS_PROFILE", "lab")
    resolved = aws.resolve_region()
    assert resolved.region == "us-west-2"
    assert resolved.source == "aws-config"
    assert resolved.profile == "lab"


def test_list_regions_uses_aws_default_region(monkeypatch, capsys, tmp_path):
    _aws_config(monkeypatch, tmp_path, "eu-central-1")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-west-2")
    monkeypatch.setattr(aws, "_session", lambda region=None: _FakeRegionSession())

    assert aws.main(["regions", "list"]) == 0
    captured = capsys.readouterr()
    assert "Using region us-west-2 from AWS_DEFAULT_REGION." in captured.err
    assert "Using region" not in captured.out

    assert aws.main(["regions", "list", "--json"]) == 0
    captured = capsys.readouterr()
    assert captured.err == ""
    payload = json.loads(captured.out)
    assert payload["region"] == "us-west-2"
    assert payload["region_source"] == "AWS_DEFAULT_REGION"
    assert "Using region" not in captured.out


def test_regional_aws_command_uses_the_config_region_and_names_the_source(monkeypatch, capsys, tmp_path):
    _aws_config(monkeypatch, tmp_path, "eu-central-1")
    seen = {}

    def fake_list(session, region, name_filter=None, owners=None, max_results=15):
        seen["region"] = region
        return {"ok": True, "region": region, "items": []}

    monkeypatch.setattr(aws, "list_amis", fake_list)
    monkeypatch.setattr(aws, "_session", lambda region=None: object())

    assert aws.main(["amis", "list"]) == 0
    captured = capsys.readouterr()
    assert seen["region"] == "eu-central-1"
    assert "Using region eu-central-1 from ~/.aws/config (profile default)." in captured.err
    assert "Using region" not in captured.out
    assert captured.out.startswith("{") is False

    assert aws.main(["amis", "list", "--json"]) == 0
    captured = capsys.readouterr()
    assert captured.err == ""
    payload = json.loads(captured.out)
    assert payload["region_source"] == "aws-config"
    assert payload["profile"] == "default"
    assert "Using region" not in captured.out

    assert aws.main(["amis", "list", "--region", "us-west-2"]) == 0
    captured = capsys.readouterr()
    assert seen["region"] == "us-west-2"
    assert "Using region us-west-2 from --region." in captured.err
    assert "Using region" not in captured.out
    assert captured.out.startswith("{") is False

    monkeypatch.setenv("AWS_REGION", "us-east-1")
    assert aws.main(["amis", "list", "--json"]) == 0
    captured = capsys.readouterr()
    assert seen["region"] == "us-east-1"
    assert captured.err == ""
    payload = json.loads(captured.out)
    assert payload["region_source"] == "AWS_REGION"
    assert "Using region" not in captured.out


def test_aws_json_error_redacts_secrets(monkeypatch, capsys):
    secret = "AKIA0000000000000000"
    monkeypatch.setattr(aws, "_session", lambda region=None: object())
    monkeypatch.setattr(aws, "check_auth", lambda _session: {"ok": False, "error": "denied " + secret})

    assert aws.main(["--check-auth", "--json"]) == 1
    captured = capsys.readouterr()
    assert captured.err == ""
    assert secret not in captured.out
    assert "***" in captured.out


def test_parse_security_groups():
    assert aws.parse_security_groups(None) is None
    assert aws.parse_security_groups("") is None
    assert aws.parse_security_groups("Splunk_Basic, extra ; other") == ["Splunk_Basic", "extra", "other"]


class _FakeValidateSts:
    def get_caller_identity(self):
        return {"Account": "000000000000", "Arn": "arn:aws:iam::000000000000:user/example"}


class _FakeValidateEc2:
    def describe_security_groups(self):
        return {
            "SecurityGroups": [
                {
                    "GroupId": "sg-lab",
                    "GroupName": "lab",
                    "Description": "lab",
                    "IpPermissions": [{"IpProtocol": "-1", "IpRanges": [{"CidrIp": "10.0.0.0/8"}]}],
                }
            ]
        }


class _FakeValidateSession:
    def client(self, service, region_name=None):
        if service == "sts":
            return _FakeValidateSts()
        return _FakeValidateEc2()


class _WorldOpenEc2(_FakeValidateEc2):
    def describe_security_groups(self):
        return {
            "SecurityGroups": [
                {
                    "GroupId": "sg-lab",
                    "GroupName": "lab",
                    "Description": "lab",
                    "IpPermissions": [
                        {
                            "IpProtocol": "tcp",
                            "FromPort": 22,
                            "ToPort": 22,
                            "IpRanges": [{"CidrIp": "0.0.0.0/0"}],
                        },
                        {
                            "IpProtocol": "tcp",
                            "FromPort": 8000,
                            "ToPort": 8089,
                            "IpRanges": [{"CidrIp": "0.0.0.0/0"}],
                        },
                    ],
                }
            ]
        }


class _WorldOpenSession(_FakeValidateSession):
    def client(self, service, region_name=None):
        if service == "sts":
            return _FakeValidateSts()
        return _WorldOpenEc2()


def test_aws_validate_warns_when_a_group_is_open_to_the_world(monkeypatch, capsys):
    monkeypatch.setattr(aws, "_session", lambda region=None: _WorldOpenSession())

    assert aws.main(
        ["--region", "eu-central-1", "--validate", "--security-groups", "lab"],
        as_agent=True,
    ) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["checks"]["security_groups"] == {"ok": True}
    assert payload["warnings"] == [
        "security group lab allows 0.0.0.0/0 to ports 22, 8000, 8088, 8089"
    ]
    assert "IpPermissions" not in json.dumps(payload)

    assert aws.main(["--region", "eu-central-1", "--validate", "--security-groups", "lab"]) == 0
    human = capsys.readouterr()
    assert "Warning: security group lab allows 0.0.0.0/0 to ports 22, 8000, 8088, 8089" in human.out
    assert human.out.startswith("{") is False


def test_agent_aws_validate_is_one_ok_per_check(monkeypatch, capsys):
    monkeypatch.setattr(aws, "_session", lambda region=None: _FakeValidateSession())

    assert aws.main(["--region", "eu-central-1", "--validate", "--security-groups", "lab"]) == 0
    human = capsys.readouterr()
    assert human.out.startswith("{") is False
    assert "security_groups: ok" in human.out

    assert aws.main(
        ["--region", "eu-central-1", "--validate", "--security-groups", "lab"],
        as_agent=True,
    ) == 0
    present = json.loads(capsys.readouterr().out)
    assert present["checks"]["auth"] == {"ok": True}
    assert present["checks"]["security_groups"] == {"ok": True}
    assert "ami" not in present["checks"]
    assert "warnings" not in present
    present_text = json.dumps(present)
    assert "IpPermissions" not in present_text
    assert '"items"' not in present_text
    assert '"group_id"' not in present_text

    assert aws.main(
        ["--region", "eu-central-1", "--validate", "--security-groups", "lab,missing"],
        as_agent=True,
    ) == 1
    missing = json.loads(capsys.readouterr().out)
    assert missing["ok"] is False
    assert missing["checks"]["security_groups"] == {"ok": False}
    missing_text = json.dumps(missing)
    assert "IpPermissions" not in missing_text
    assert '"items"' not in missing_text
    assert '"group_id"' not in missing_text

    assert aws.main(
        ["--region", "eu-central-1", "--validate", "--security-groups", "lab", "--details"],
        as_agent=True,
    ) == 0
    detailed = json.loads(capsys.readouterr().out)
    assert detailed["checks"]["security_groups"]["items"][0]["group_id"] == "sg-lab"
    assert "IpPermissions" not in json.dumps(detailed)


def test_environment_config_region_beats_aws_environment_variables(monkeypatch, capsys, tmp_path):
    _aws_config(monkeypatch, tmp_path, "eu-central-1")
    monkeypatch.setenv("AWS_REGION", "us-east-1")
    seen = {}

    def fake_list(session, region, name_filter=None, owners=None, max_results=15):
        seen["region"] = region
        return {"ok": True, "region": region, "items": []}

    monkeypatch.setattr(aws, "list_amis", fake_list)
    monkeypatch.setattr(aws, "_session", lambda region=None: object())

    assert aws.main(["amis", "list"], environment_region="eu-west-1") == 0
    captured = capsys.readouterr()
    assert seen["region"] == "eu-west-1"
    assert "Using region eu-west-1 from terraform.aws.region in the environment config." in captured.err

    assert aws.main(["amis", "list", "--json"], environment_region="eu-west-1") == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["region_source"] == "terraform.aws.region"

    assert aws.main(["amis", "list", "--region", "us-west-2"], environment_region="eu-west-1") == 0
    assert seen["region"] == "us-west-2"


def test_environment_config_region_is_read_from_terraform_aws(tmp_path):
    config = tmp_path / "splunk_config.yml"
    config.write_text("terraform:\n  aws:\n    region: eu-west-1\n", encoding="utf-8")
    assert aws.environment_config_region(config) == "eu-west-1"

    config.write_text("terraform:\n  aws:\n    ami_id: ami-016793dd57ccbf03f\n", encoding="utf-8")
    assert aws.environment_config_region(config) is None
    assert aws.environment_config_region(tmp_path / "missing.yml") is None
