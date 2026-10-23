"""Guest packages the common role installs before Ansible's acl check."""

from pathlib import Path

import pytest

from spa.aws import _ami_item_from_image, describe_ami

pytestmark = pytest.mark.local

ROOT = Path(__file__).resolve().parents[1]


def test_common_role_unions_acl_and_policykit_before_the_check():
    text = (ROOT / "ansible" / "roles" / "common" / "tasks" / "main.yml").read_text(encoding="utf-8")
    required = text.split("Call Check Ansible requirements", 1)[0]
    assert "'acl'" in required
    assert "policykit-1" in required
    assert "polkit" in required
    assert "os_family'] == 'Debian'" in required
    assert "splunk_use_policykit" in required
    assert "unique" in required
    assert "packages | default([])" in required
    check = text.split("Call Check Ansible requirements", 1)[1]
    assert "check_ansible_requirements.yml" in check


def test_ami_lookup_returns_name_and_description():
    image = {
        "ImageId": "ami-0443f7d10da53831f",
        "Name": "RHEL-10.0.0_HVM-20260812-x86_64-0-Hourly2-GP3",
        "Description": "Provided by Red Hat, Inc.",
        "Architecture": "x86_64",
        "CreationDate": "2026-08-12T00:00:00.000Z",
        "State": "available",
    }
    listed = _ami_item_from_image(image)
    assert listed["name"].startswith("RHEL-10")
    assert listed["description"] == "Provided by Red Hat, Inc."

    class _Images:
        def describe_images(self, ImageIds):
            found = dict(image)
            found["ImageId"] = ImageIds[0]
            return {"Images": [found]}

    class _Session:
        def client(self, name, region_name):
            assert name == "ec2"
            assert region_name == "eu-central-1"
            return _Images()

    described = describe_ami(_Session(), "eu-central-1", image["ImageId"])
    assert described["ok"] is True
    assert described["name"] == listed["name"]
    assert described["description"] == listed["description"]


def test_shipped_aws_provider_comments_the_ami():
    text = (ROOT / "examples" / "providers" / "aws.yml").read_text(encoding="utf-8")
    assert 'ami_id: "ami-0443f7d10da53831f" # RHEL 10 hourly (eu-central-1). Does not include acl or PolicyKit.' in text


def test_init_copies_the_provider_ami_comment(tmp_path):
    from spa.init import write_composed_config

    dest = tmp_path / "config" / "splunk_config.yml"
    write_composed_config(dest, ROOT, "single_node", "aws")
    text = dest.read_text(encoding="utf-8")
    assert "ami-0443f7d10da53831f" in text
    assert "# RHEL 10 hourly (eu-central-1). Does not include acl or PolicyKit." in text


def _ami_config(tmp_path, body: str):
    path = tmp_path / "config" / "splunk_config.yml"
    path.parent.mkdir(parents=True)
    path.write_text(body, encoding="utf-8")
    return path


def test_config_set_comments_a_described_ami(tmp_path, monkeypatch):
    from spa.config_edit import config_set

    path = _ami_config(
        tmp_path,
        "plugin: splunk-platform-automator\n"
        "terraform:\n"
        "  aws:\n"
        "    region: eu-central-1\n"
        '    ami_id: "ami-0443f7d10da53831f" # RHEL 10 hourly (eu-central-1). Does not include acl or PolicyKit.\n',
    )
    monkeypatch.setattr(
        "spa.aws.ami_comment_for_config",
        lambda region, ami_id: "RHEL-9.4 (eu-central-1). Provided by Red Hat, Inc.",
    )
    result = config_set(path, ROOT, "terraform.aws.ami_id", "ami-0abc123", validate=False)
    text = path.read_text(encoding="utf-8")
    assert result["warnings"] == []
    assert "ami-0abc123" in text
    assert "# RHEL-9.4 (eu-central-1). Provided by Red Hat, Inc." in text
    assert "Does not include acl" not in text


def test_config_set_drops_a_stale_ami_comment_without_aws(tmp_path, monkeypatch):
    from spa.config_edit import config_set

    path = _ami_config(
        tmp_path,
        "plugin: splunk-platform-automator\n"
        "terraform:\n"
        "  aws:\n"
        "    region: eu-central-1\n"
        '    ami_id: "ami-0443f7d10da53831f" # RHEL 10 hourly (eu-central-1). Does not include acl or PolicyKit.\n',
    )
    monkeypatch.setattr("spa.aws.ami_comment_for_config", lambda region, ami_id: None)
    result = config_set(path, ROOT, "terraform.aws.ami_id", "ami-0abc123", validate=False)
    text = path.read_text(encoding="utf-8")
    assert "ami-0abc123" in text
    assert "Does not include acl" not in text
    assert any("without an image comment" in warning for warning in result["warnings"])


def test_ami_comment_for_config_uses_the_described_image(monkeypatch):
    from spa.aws import ami_comment_for_config

    monkeypatch.setattr("spa.aws.boto3", object())
    monkeypatch.setattr("spa.aws._session", lambda region: object())
    monkeypatch.setattr(
        "spa.aws.describe_ami",
        lambda session, region, ami_id: {
            "ok": True,
            "name": "RHEL-10.0.0_HVM-20260812-x86_64-0-Hourly2-GP3",
            "description": "Provided by Red Hat, Inc.",
        },
    )
    assert ami_comment_for_config("eu-central-1", "ami-0443f7d10da53831f") == (
        "RHEL-10.0.0_HVM-20260812-x86_64-0-Hourly2-GP3 (eu-central-1). "
        "Provided by Red Hat, Inc."
    )


def test_ami_comment_for_config_is_empty_when_describe_fails(monkeypatch):
    from spa.aws import ami_comment_for_config

    monkeypatch.setattr("spa.aws.boto3", object())
    monkeypatch.setattr("spa.aws._session", lambda region: (_ for _ in ()).throw(OSError("down")))
    assert ami_comment_for_config("eu-central-1", "ami-0443f7d10da53831f") is None


def test_ami_explain_shows_how_to_find_a_redhat_image():
    from spa.config_tree import explain_config

    description = explain_config("terraform.aws.ami_id")["description"]
    assert "spa aws --region eu-central-1 --latest-ami --os rhel" in description
    assert "spa aws list amis --region eu-central-1 --os rhel" in description
    assert "comment" in description.lower()
