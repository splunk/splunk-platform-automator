"""External / BYO SSH hosts."""

import json
import os
import sys

import yaml

import pytest
from pydantic import ValidationError

pytestmark = [pytest.mark.local, pytest.mark.cli]

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "ansible", "plugins", "inventory"))

from schema import SplunkConfig  # noqa: E402
from spa.providers.classify import classify_hostnames  # noqa: E402

_PASSWORD = "{{ lookup('env', 'SPLUNK_ADMIN_PASSWORD') }}"


def _with_password(config):
    """SplunkConfig requires an admin password before other checks run."""
    merged = dict(config)
    merged["splunk_defaults"] = {"splunk_admin_password": _PASSWORD}
    return merged


def test_classify_puts_external_names_only_in_the_external_list():
    managed, external = classify_hostnames({
        "terraform": {"aws": {"region": "eu-central-1"}},
        "splunk_hosts": [
            {"name": "idx1", "roles": ["indexer"]},
            {"name": "byo1", "external": None, "roles": ["search_head"]},
            {"list": ["byo2", "byo3"], "external": {}, "roles": ["indexer"]},
        ]
    })
    assert managed == ["idx1"]
    assert external == ["byo1", "byo2", "byo3"]


def test_bare_external_covers_every_host():
    managed, external = classify_hostnames({
        "external": None,
        "splunk_hosts": [
            {"name": "shidx", "roles": ["indexer", "search_head"]},
        ],
    })
    assert managed == []
    assert external == ["shidx"]


def test_external_host_does_not_store_ssh_in_the_config_and_rejects_a_password():
    secret = "not-a-real-password"
    cfg = SplunkConfig.model_validate(_with_password({
        "plugin": "splunk-platform-automator",
        "external": None,
        "splunk_hosts": [{
            "name": "byo1",
            "roles": ["search_head"],
        }],
    }))
    assert cfg.external is not None
    assert cfg.splunk_hosts[0].name == "byo1"
    with pytest.raises(ValidationError) as exc:
        SplunkConfig.model_validate(_with_password({
            "plugin": "splunk-platform-automator",
            "external": {},
            "splunk_hosts": [{
                "name": "byo1",
                "roles": ["search_head"],
                "ansible_ssh_pass": secret,
            }],
        }))
    text = str(exc.value)
    assert "passwords are not accepted" in text
    assert secret not in text


def test_password_keys_are_rejected_without_changing_the_callers_document():
    secret = "not-a-real-password"
    documents = [
        {
            "plugin": "splunk-platform-automator",
            "custom": {"ansible_password": secret},
            "splunk_hosts": [{"name": "idx1", "roles": ["indexer"]}],
        },
        {
            "plugin": "splunk-platform-automator",
            "splunk_hosts": [{
                "name": "idx1",
                "roles": ["indexer"],
                "ansible_become_password": secret,
            }],
        },
        {
            "plugin": "splunk-platform-automator",
            "splunk_hosts": [{
                "name": "idx1",
                "roles": ["indexer"],
                "custom": {"ansible_ssh_password": secret},
            }],
        },
    ]
    for document in documents:
        with pytest.raises(ValidationError) as exc:
            SplunkConfig.model_validate(_with_password(document))
        text = str(exc.value)
        assert "passwords are not accepted" in text
        assert secret not in text


def test_external_host_may_omit_roles():
    cfg = SplunkConfig.model_validate(_with_password({
        "plugin": "splunk-platform-automator",
        "external": {},
        "splunk_hosts": [{
            "name": "util1",
            "external": {},
            "ansible_host": "10.0.0.9",
            "ansible_user": "splunk",
            "ansible_ssh_private_key_file": "~/.ssh/id_ed25519",
        }],
    }))
    assert cfg.splunk_hosts[0].roles in (None, [])


def test_list_cannot_be_external_and_external_only_rejects_terraform():
    with pytest.raises(ValidationError, match="external requires name"):
        SplunkConfig.model_validate(_with_password({
            "plugin": "splunk-platform-automator",
            "external": {},
            "splunk_hosts": [{
                "list": ["a"],
                "external": {},
                "roles": ["indexer"],
                "ansible_host": "10.0.0.1",
                "ansible_user": "splunk",
                "ansible_ssh_private_key_file": "~/.ssh/id_ed25519",
            }],
        }))
    with pytest.raises(ValidationError, match="an external-only env cannot also set terraform"):
        SplunkConfig.model_validate(_with_password({
            "plugin": "splunk-platform-automator",
            "external": {},
            "terraform": {"aws": {}},
            "splunk_hosts": [{
                "name": "byo1",
                "external": {},
                "roles": ["search_head"],
                "ansible_host": "10.0.0.1",
                "ansible_user": "splunk",
                "ansible_ssh_private_key_file": "~/.ssh/id_ed25519",
            }],
        }))


def test_mixed_env_allows_external_host_without_root_external():
    cfg = SplunkConfig.model_validate(_with_password({
        "plugin": "splunk-platform-automator",
        "terraform": {"aws": {"region": "eu-central-1"}},
        "splunk_hosts": [
            {"name": "idx1", "roles": ["indexer"]},
            {
                "name": "byo1",
                "external": {},
                "roles": ["search_head"],
                "ansible_host": "10.0.0.8",
                "ansible_user": "splunk",
                "ansible_ssh_private_key_file": "~/.ssh/id_ed25519",
            },
        ],
    }))
    assert cfg.splunk_hosts[1].external is not None
    assert cfg.external is None


def _paths(tmp_path, config):
    from dataclasses import replace

    from spa.paths import resolve_spa_paths
    from spa_testutil import PROJECT_ROOT

    config_path = tmp_path / "config" / "splunk_config.yml"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(config)
    base = resolve_spa_paths(start_dir=PROJECT_ROOT)
    return replace(
        base,
        spa_env_dir=tmp_path,
        config_file=config_path,
        inventory_dir=tmp_path / "inventory",
        terraform_state_dir=tmp_path / "terraform" / "aws",
        roots_differ=True,
    )


def test_detect_provider_selects_external_without_terraform(tmp_path):
    from spa.providers import detect_provider

    paths = _paths(tmp_path, "external: {}\nsplunk_hosts: []\n")
    selection = detect_provider(paths)
    assert selection.name == "external"
    assert selection.config == {}


def test_aws_wins_when_external_is_also_present(tmp_path):
    from spa.providers import detect_provider

    paths = _paths(tmp_path, "external: {}\nterraform:\n  aws: {}\n")
    assert detect_provider(paths).name == "aws"


def test_init_provider_external_without_example_is_not_virtualbox(tmp_path):
    from spa_testutil import run_spa_init

    dest = tmp_path / "env"
    result = run_spa_init(["--provider", "external", str(dest)])
    assert result.returncode == 0, result.stderr + result.stdout
    text = (dest / "config" / "splunk_config.yml").read_text(encoding="utf-8")
    assert "\nexternal:\n\n" in text
    assert "provider:" not in text
    assert "virtualbox:" not in text
    host = yaml.safe_load(text)["splunk_hosts"][0]
    assert "external" not in host


def test_init_external_stamps_hosts_and_does_not_require_terraform(tmp_path):
    from spa_testutil import run_spa_init

    dest = tmp_path / "env"
    result = run_spa_init([
        "--example", "single_node", "--provider", "external",
        "--skip-doctor", str(dest),
    ])
    assert result.returncode == 0, result.stderr
    text = (dest / "config" / "splunk_config.yml").read_text(encoding="utf-8")
    assert "\nexternal:\n\n" in text
    assert "provider:" not in text
    assert "terraform:" not in text
    host = yaml.safe_load(text)["splunk_hosts"][0]
    assert "external" not in host
    assert not (dest / "terraform" / "aws").exists()


def test_external_only_requires_root_external_block():
    with pytest.raises(ValidationError, match="external hosts require a root external: block"):
        SplunkConfig.model_validate(_with_password({
            "plugin": "splunk-platform-automator",
            "splunk_hosts": [{
                "name": "byo1",
                "external": {},
                "roles": ["search_head"],
                "ansible_host": "10.0.0.1",
                "ansible_user": "splunk",
                "ansible_ssh_private_key_file": "~/.ssh/id_ed25519",
            }],
        }))


def test_external_os_mask_is_off_unless_the_host_sets_it():
    import importlib.util

    from spa_testutil import PROJECT_ROOT

    plugin_path = PROJECT_ROOT / "ansible" / "plugins" / "inventory" / "splunk-platform-automator.py"
    spec = importlib.util.spec_from_file_location("spa_inventory_plugin", plugin_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.external_os_mask({"external": {}, "os": {"disable_selinux": True}}) == {
        "set_hostname": False,
        "update_hosts_file": False,
        "disable_apparmor": False,
        "splunk_user_create": False,
        "splunk_group_create": False,
    }
    assert module.external_os_mask({"name": "idx1"}) == {}


def test_inventory_sets_ansible_host_and_does_not_mask_managed_hosts():
    import importlib.util

    from spa_testutil import PROJECT_ROOT

    plugin_path = PROJECT_ROOT / "ansible" / "plugins" / "inventory" / "splunk-platform-automator.py"
    spec = importlib.util.spec_from_file_location("spa_inventory_plugin_hosts", plugin_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    class _Inventory:
        def __init__(self):
            self.hosts = {}

        def set_variable(self, host, key, value):
            self.hosts.setdefault(host, {})[key] = value

    inventory = _Inventory()
    external = {
        "name": "byo1",
        "external": {},
        "ansible_host": "10.1.1.1",
        "custom": {"ansible_host": "10.9.9.9"},
        "os": {"disable_selinux": True},
    }
    managed = {"name": "idx1", "custom": {"ansible_host": "10.9.9.9"}}
    module.publish_host_vars(inventory, "byo1", external)
    module.publish_host_vars(inventory, "idx1", managed)
    assert inventory.hosts["byo1"]["ansible_host"] == "10.1.1.1"
    assert inventory.hosts["byo1"]["disable_selinux"] is True
    assert inventory.hosts["byo1"]["set_hostname"] is False
    assert "disable_selinux" not in inventory.hosts["idx1"]
    assert inventory.hosts["idx1"]["ansible_host"] == "10.9.9.9"


def test_tfvars_omits_external_hosts():
    from ansible.parsing.dataloader import DataLoader
    from ansible.template import Templar, trust_as_template

    from spa_testutil import PROJECT_ROOT

    text = (PROJECT_ROOT / "template" / "terraform_aws.tfvars.j2").read_text(encoding="utf-8")
    aws = {
        "region": "eu-central-1",
        "ami_id": "ami-example",
        "key_name": "aws_key",
        "ssh_private_key_file": "~/.ssh/aws_key.pem",
        "security_group_names": ["Splunk_Basic"],
        "instance_type": "t3.medium",
    }
    templar = Templar(
        loader=DataLoader(),
        variables={
            "terraform": {"aws": aws},
            "default_config": {"terraform": {"aws": aws}},
            "os": {"remote_command": ""},
            "splunk_hosts": [
                {"name": "idx1", "roles": ["indexer"]},
                {"name": "byo1", "external": {}, "roles": ["search_head"]},
            ],
        },
    )
    rendered = templar.template(trust_as_template(text))
    assert "idx1" in rendered
    assert "byo1" not in rendered


def test_vagrantfile_skips_external_hosts_before_the_ip_increment():
    from spa_testutil import PROJECT_ROOT

    text = (PROJECT_ROOT / "Vagrantfile").read_text(encoding="utf-8")
    skip = "next if splunk_host.key?('external')"
    assert skip in text
    assert text.index(skip) < text.index("start_num += 1")


def _external_paths(tmp_path, host, key):
    config = (
        "external: {}\n"
        "splunk_hosts:\n"
        "  - name: %s\n"
        "    external:\n"
        "    roles: [search_head]\n"
        "    ansible_host: 10.0.0.8\n"
        "    ansible_user: splunk\n"
        "    ansible_ssh_private_key_file: %s\n"
    ) % (host, key)
    return _paths(tmp_path, config)


def test_probe_uses_batchmode_without_reading_the_key(tmp_path):
    from spa.providers.external import probe_ssh

    key = tmp_path / "id_ed25519"
    key.write_text("not-read\n")
    seen = []

    def run(argv):
        seen.append(list(argv))
        return 0

    probe_ssh("10.0.0.8", "splunk", str(key), 22, run)
    assert seen == [[
        "ssh", "-i", str(key), "-p", "22", "-o", "BatchMode=yes", "-o",
        "StrictHostKeyChecking=accept-new", "-o", "ConnectTimeout=10",
        "splunk@10.0.0.8", "true",
    ]]
    assert "sudo" not in seen[0]
    assert "not-read" not in " ".join(seen[0])


def test_failed_probe_does_not_write_inventory(tmp_path):
    from spa.providers import ProviderError
    from spa.providers.external import Provider

    key = tmp_path / "id_ed25519"
    key.write_text("not-read")
    hosts = tmp_path / "inventory" / "hosts"
    hosts.parent.mkdir()
    from spa.providers.external import inventory_line

    hosts.write_text(
        'keepme ansible_host="10.0.0.1"\n%s\n' % inventory_line("byo1", "10.0.0.8", "splunk", str(key), 22)
    )
    before = hosts.read_bytes()
    paths = _external_paths(tmp_path, host="byo1", key=str(key))

    def run(argv):
        return 1

    provider = Provider(paths, {}, run=run)
    with pytest.raises(ProviderError, match="ssh failed for splunk@10.0.0.8"):
        provider.provision([])
    assert hosts.read_bytes() == before


def test_external_suspend_and_destroy_do_not_call_ssh(tmp_path):
    from spa.providers import ProviderError
    from spa.providers.external import Provider

    key = tmp_path / "id_ed25519"
    key.write_text("not-read")
    paths = _external_paths(tmp_path, host="byo1", key=str(key))

    def run(argv):
        raise AssertionError("ssh must not run")

    provider = Provider(paths, {}, run=run)
    with pytest.raises(ProviderError, match="SPA does not own power for external hosts: byo1"):
        provider.suspend()
    result = provider.destroy([])
    text = paths.config_file.read_text(encoding="utf-8")
    assert "name: byo1" in text or "name: byo1" in text.replace("'", "")
    assert "ansible_host" not in text
    assert result["unregistered"] == ["byo1"]
    assert result["note"] == "Those machines were not shut down."


def _fake_ssh(tmp_path, code=0):
    bindir = tmp_path / "bin"
    bindir.mkdir(parents=True)
    ssh = bindir / "ssh"
    ssh.write_text("#!/bin/sh\nexit %d\n" % code)
    ssh.chmod(0o755)
    return str(bindir) + os.pathsep + os.environ.get("PATH", "")


def _external_env(tmp_path):
    from spa_testutil import PROJECT_ROOT, run_spa_init

    dest = tmp_path / "lab"
    result = run_spa_init(
        ["--example", "single_node", "--provider", "external", str(dest)],
        env={"SPA_HOME": str(PROJECT_ROOT)},
    )
    assert result.returncode == 0, result.stderr
    return dest


def _cli_env(dest, path):
    from spa_testutil import PROJECT_ROOT

    return {"SPA_HOME": str(PROJECT_ROOT), "SPA_ENV_DIR": str(dest), "PATH": path}


def test_register_writes_inventory_and_agent_json_hides_the_key_body(tmp_path):
    from spa_testutil import run_spa

    key = tmp_path / "id_ed25519"
    marker = "key-body-not-for-output\n"
    key.write_text(marker)
    dest = _external_env(tmp_path)
    result = run_spa(
        [
            "--agent", "hosts", "register", "byo1",
            "--address", "10.0.0.8", "--user", "splunk",
            "--key", str(key), "--role", "search_head", "--yes",
        ],
        env=_cli_env(dest, _fake_ssh(tmp_path)),
    )
    payload = json.loads(result.stdout)
    assert result.returncode == 0, result.stderr
    assert payload["data"]["key"] == "set"
    assert payload["data"]["ansible_ssh_private_key_file"] == str(key)
    assert marker not in result.stdout
    assert marker not in result.stderr
    listed = (dest / "inventory" / "hosts").read_text(encoding="utf-8")
    assert 'ansible_user="splunk"' in listed
    assert "ansible_port" not in listed
    config_text = (dest / "config" / "splunk_config.yml").read_text(encoding="utf-8")
    assert "ansible_host" not in config_text
    assert "ansible_user" not in config_text
    assert "ansible_ssh_private_key_file" not in config_text


def test_register_human_line_and_failed_probe_leaves_files(tmp_path):
    from spa_testutil import run_spa

    key = tmp_path / "id_ed25519"
    key.write_text("not-read")
    dest = _external_env(tmp_path)
    config_before = (dest / "config" / "splunk_config.yml").read_bytes()
    inventory_before = (dest / "inventory" / "hosts").read_bytes()
    failed = run_spa(
        [
            "--no-agent", "hosts", "register", "byo1",
            "--address", "10.0.0.8", "--user", "splunk",
            "--key", str(key), "--yes",
        ],
        env=_cli_env(dest, _fake_ssh(tmp_path, code=1)),
    )
    assert failed.returncode == 1
    assert "ssh failed for splunk@10.0.0.8" in failed.stderr
    assert (dest / "config" / "splunk_config.yml").read_bytes() == config_before
    assert (dest / "inventory" / "hosts").read_bytes() == inventory_before
    ok = run_spa(
        [
            "--no-agent", "hosts", "register", "byo1",
            "--address", "10.0.0.8", "--user", "splunk",
            "--key", str(key), "--yes",
        ],
        env=_cli_env(dest, _fake_ssh(tmp_path / "okssh", code=0)),
    )
    assert ok.returncode == 0, ok.stderr
    assert ok.stdout.strip() == "registered byo1 ansible_host=10.0.0.8 user=splunk key=set"


def test_register_refuses_a_managed_name(tmp_path):
    from spa_testutil import PROJECT_ROOT, run_spa, run_spa_init

    dest = tmp_path / "aws-lab"
    init = run_spa_init(
        ["--example", "single_node", "--provider", "aws", str(dest)],
        env={"SPA_HOME": str(PROJECT_ROOT)},
    )
    assert init.returncode == 0, init.stderr
    key = tmp_path / "id_ed25519"
    key.write_text("not-read")
    result = run_spa(
        [
            "--no-agent", "hosts", "register", "shidx",
            "--address", "10.0.0.8", "--user", "splunk",
            "--key", str(key), "--yes",
        ],
        env=_cli_env(dest, _fake_ssh(tmp_path)),
    )
    assert result.returncode == 1
    assert "shidx is managed by aws. SPA does not take over a managed host." in result.stderr
    added = run_spa(
        [
            "--no-agent", "hosts", "register", "byo1",
            "--address", "10.0.0.8", "--user", "splunk",
            "--key", str(key), "--role", "search_head", "--yes",
        ],
        env=_cli_env(dest, _fake_ssh(tmp_path / "okssh")),
    )
    assert added.returncode == 0, added.stderr
    text = (dest / "config" / "splunk_config.yml").read_text(encoding="utf-8")
    assert "name: byo1" in text
    assert "ansible_host" not in text
    listed = (dest / "inventory" / "hosts").read_text(encoding="utf-8")
    assert 'byo1 ansible_host="10.0.0.8"' in listed
    import yaml

    cfg = yaml.safe_load(text)
    byo = next(host for host in cfg["splunk_hosts"] if host.get("name") == "byo1")
    assert "external" in byo


def test_register_without_role_and_unregister_last_host(tmp_path):
    from spa_testutil import run_spa

    key = tmp_path / "id_ed25519"
    key.write_text("not-read")
    dest = _external_env(tmp_path)
    env = _cli_env(dest, _fake_ssh(tmp_path))
    added = run_spa(
        [
            "--agent", "hosts", "register", "util1",
            "--address", "10.0.0.9", "--user", "splunk",
            "--key", str(key), "--yes",
        ],
        env=env,
    )
    assert added.returncode == 0, added.stderr
    import yaml

    cfg = yaml.safe_load((dest / "config" / "splunk_config.yml").read_text())
    util = next(host for host in cfg["splunk_hosts"] if host.get("name") == "util1")
    assert not util.get("roles")
    before = (dest / "config" / "splunk_config.yml").read_bytes()
    missing = run_spa(["--no-agent", "hosts", "unregister", "shidx", "--yes"], env=env)
    assert missing.returncode == 1
    assert "shidx has no SSH inventory line" in missing.stderr
    assert (dest / "config" / "splunk_config.yml").read_bytes() == before
    removed = run_spa(["--no-agent", "hosts", "unregister", "util1", "--yes"], env=env)
    assert removed.returncode == 0, removed.stderr
    assert (dest / "config" / "splunk_config.yml").read_bytes() == before
    listed = (dest / "inventory" / "hosts").read_text(encoding="utf-8")
    assert "util1" not in listed
    cfg = yaml.safe_load((dest / "config" / "splunk_config.yml").read_text())
    assert {host.get("name") for host in cfg["splunk_hosts"]} == {"shidx", "util1"}


def test_deploy_ping_failure_does_not_start_the_playbook(tmp_path, monkeypatch):
    from dataclasses import replace

    from spa.api import LocalSpaSession
    from spa.paths import resolve_spa_paths
    from spa_testutil import PROJECT_ROOT, seed_software_dir

    config = tmp_path / "config" / "splunk_config.yml"
    config.parent.mkdir()
    config.write_text(
        "external: {}\n"
        "splunk_hosts:\n"
        "  - name: byo1\n"
        "    external:\n"
        "    ansible_host: 10.0.0.8\n"
        "    ansible_user: splunk\n"
        "    ansible_ssh_private_key_file: /tmp/key\n"
    )
    inventory = tmp_path / "inventory"
    inventory.mkdir()
    (inventory / "hosts").write_text('byo1 ansible_host="10.0.0.8"\n')
    software = seed_software_dir(tmp_path)
    base = resolve_spa_paths(start_dir=PROJECT_ROOT)
    paths = replace(
        base,
        spa_env_dir=tmp_path,
        config_file=config,
        inventory_dir=inventory,
        roots_differ=True,
        software_dir=software,
        baseconfig_dir=software,
    )
    called = []
    monkeypatch.setattr("spa.playbooks.run_playbook", lambda *a, **k: called.append(True) or 0)
    monkeypatch.setattr("spa.playbooks.resolve", lambda *a, **k: "deploy_site.yml")

    def fail_ping(*_args, **_kwargs):
        from spa.hosts import HostsError

        raise HostsError("Ansible ping failed for byo1. Passwordless sudo to root is required.")

    monkeypatch.setattr("spa.hosts.ping_hosts", fail_ping)
    monkeypatch.setattr("spa.api.apply_paths_env", lambda *a, **k: {})
    result = LocalSpaSession(paths=paths).deploy(confirm=True)
    assert result.ok is False
    assert result.code == 1
    assert "Ansible ping failed for byo1" in result.error
    assert not called


def test_deploy_logs_the_host_check(tmp_path, monkeypatch, capsys):
    from dataclasses import replace

    from pathlib import Path

    from spa.api import LocalSpaSession
    from spa.paths import resolve_spa_paths
    from spa_testutil import PROJECT_ROOT, seed_software_dir

    config = tmp_path / "config" / "splunk_config.yml"
    config.parent.mkdir()
    config.write_text(
        "external: {}\n"
        "splunk_hosts:\n"
        "  - name: byo1\n"
        "    external:\n"
        "    ansible_host: 10.0.0.8\n"
        "    ansible_user: splunk\n"
        "    ansible_ssh_private_key_file: /tmp/key\n"
    )
    inventory = tmp_path / "inventory"
    inventory.mkdir()
    (inventory / "hosts").write_text('byo1 ansible_host="10.0.0.8"\n')
    software = seed_software_dir(tmp_path)
    base = resolve_spa_paths(start_dir=PROJECT_ROOT)
    paths = replace(
        base,
        spa_env_dir=tmp_path,
        config_file=config,
        inventory_dir=inventory,
        roots_differ=True,
        software_dir=software,
        baseconfig_dir=software,
    )
    monkeypatch.setattr("spa.playbooks.run_playbook", lambda *a, **k: 0)
    monkeypatch.setattr("spa.playbooks.resolve", lambda *a, **k: "deploy_site.yml")
    monkeypatch.setattr(
        "spa.hosts.ping_hosts",
        lambda *a, **k: {
            "hosts": [{"name": "byo1", "ok": True, "ssh": True, "become": True, "message": ""}]
        },
    )
    monkeypatch.setattr("spa.api.apply_paths_env", lambda *a, **k: {})
    result = LocalSpaSession(paths=paths).deploy(confirm=True)
    assert result.ok, result.error
    captured = capsys.readouterr()
    assert "Host check" in captured.err
    assert "SSH ok, sudo ok" in captured.err
    logged = Path(result.data["log"]).read_text(encoding="utf-8")
    assert '"phase": "host_check"' in logged
    assert "byo1" in logged
    assert "SSH ok, sudo ok" in logged


def test_deploy_architecture_mismatch_does_not_blame_ssh(tmp_path, monkeypatch, capsys):
    from dataclasses import replace

    from spa.api import LocalSpaSession
    from spa.paths import resolve_spa_paths
    from spa_testutil import PROJECT_ROOT, seed_software_dir

    config = tmp_path / "config" / "splunk_config.yml"
    config.parent.mkdir()
    config.write_text(
        "external: {}\n"
        "splunk_defaults:\n"
        "  splunk_architecture: arm64\n"
        "splunk_hosts:\n"
        "  - name: shidx\n"
        "    roles: [search_head]\n"
    )
    inventory = tmp_path / "inventory"
    inventory.mkdir()
    (inventory / "hosts").write_text('shidx ansible_host="10.0.0.8"\n')
    software = seed_software_dir(tmp_path)
    base = resolve_spa_paths(start_dir=PROJECT_ROOT)
    paths = replace(
        base,
        spa_env_dir=tmp_path,
        config_file=config,
        inventory_dir=inventory,
        roots_differ=True,
        software_dir=software,
        baseconfig_dir=software,
    )
    called = []
    monkeypatch.setattr("spa.playbooks.run_playbook", lambda *a, **k: called.append(True) or 0)
    monkeypatch.setattr("spa.playbooks.resolve", lambda *a, **k: "deploy_site.yml")
    monkeypatch.setattr(
        "spa.shell.ansible_ping",
        lambda *a, **k: (
            [{"name": "shidx", "ok": True, "ssh": True, "become": True, "message": ""}],
            None,
        ),
    )
    monkeypatch.setattr(
        "spa.shell.ansible_architecture",
        lambda *a, **k: ({"shidx": "x86_64"}, None),
    )
    monkeypatch.setattr("spa.api.apply_paths_env", lambda *a, **k: {})
    result = LocalSpaSession(paths=paths).deploy(confirm=True)
    assert result.ok is False
    assert "SSH" not in (result.error or "")
    assert "sudo" not in (result.error or "")
    captured = capsys.readouterr()
    assert "SSH" not in captured.err
    assert "sudo" not in captured.err
    assert "Architecture" in captured.err
    assert "shidx" in captured.err
    assert "config arm64, host x86_64" in captured.err
    assert not called


def test_deploy_prints_the_architecture_mismatch_once(tmp_path, monkeypatch, capsys):
    from spa.cli import main
    from spa_testutil import PROJECT_ROOT, seed_software_dir

    config = tmp_path / "config" / "splunk_config.yml"
    config.parent.mkdir()
    config.write_text(
        "external: {}\n"
        "splunk_defaults:\n"
        "  splunk_architecture: arm64\n"
        "splunk_hosts:\n"
        "  - name: shidx\n"
        "    roles: [search_head]\n"
    )
    inventory = tmp_path / "inventory"
    inventory.mkdir()
    (inventory / "hosts").write_text('shidx ansible_host="10.0.0.8"\n')
    software = seed_software_dir(tmp_path)
    monkeypatch.setenv("SPA_HOME", str(PROJECT_ROOT))
    monkeypatch.setenv("SPA_ENV_DIR", str(tmp_path))
    monkeypatch.setenv("SPLUNK_CONFIG_FILE", str(config))
    monkeypatch.setenv("SPA_SOFTWARE_DIR", str(software))
    monkeypatch.setenv("SPA_BASECONFIG_DIR", str(software))
    monkeypatch.setattr("spa.playbooks.run_playbook", lambda *a, **k: 0)
    monkeypatch.setattr("spa.playbooks.resolve", lambda *a, **k: "deploy_site.yml")
    monkeypatch.setattr(
        "spa.shell.ansible_ping",
        lambda *a, **k: (
            [{"name": "shidx", "ok": True, "ssh": True, "become": True, "message": ""}],
            None,
        ),
    )
    monkeypatch.setattr(
        "spa.shell.ansible_architecture",
        lambda *a, **k: ({"shidx": "x86_64"}, None),
    )
    monkeypatch.setattr("spa.api.apply_paths_env", lambda *a, **k: {})
    code = main(["--no-agent", "deploy", "--yes"])
    assert code == 1
    captured = capsys.readouterr()
    assert captured.err.count("config arm64, host x86_64") == 1


def test_ping_hosts_uses_become_and_does_not_write(tmp_path):
    from spa.hosts import ping_hosts

    key = tmp_path / "id_ed25519"
    key.write_text("not-read")
    paths = _external_paths(tmp_path, host="byo1", key=str(key))
    hosts = paths.inventory_dir / "hosts"
    hosts.parent.mkdir(parents=True, exist_ok=True)
    hosts.write_text('byo1 ansible_host="10.0.0.8"\n')
    before = hosts.read_bytes()
    seen = []

    def run(argv, tree):
        seen.append(list(argv))
        module = argv[argv.index("-m") + 1]
        with open(os.path.join(tree, "byo1"), "w", encoding="utf-8") as handle:
            if module == "ping":
                handle.write('{"ping": "pong"}')
            else:
                handle.write('{"ansible_facts": {"ansible_architecture": "x86_64"}}')
        return 0

    data = ping_hosts(paths, ["byo1"], run)
    assert "-b" in seen[0]
    assert seen[0][seen[0].index("--become-user") + 1] == "root"
    assert "--tree" in seen[0]
    assert "-b" not in seen[1]
    assert "setup" in seen[1]
    assert data["hosts"] == [
        {
            "name": "byo1",
            "ok": True,
            "ssh": True,
            "become": True,
            "message": "",
            "expected_architecture": "amd64",
            "architecture": "x86_64",
        }
    ]
    assert hosts.read_bytes() == before


def test_hosts_check_fails_when_architecture_does_not_match(tmp_path):
    from spa.hosts import HostsError, ping_hosts

    paths = _paths(
        tmp_path,
        "external: {}\n"
        "splunk_defaults:\n"
        "  splunk_architecture: arm64\n"
        "splunk_hosts:\n"
        "  - name: byo1\n"
        "    roles: [search_head]\n",
    )
    hosts = paths.inventory_dir / "hosts"
    hosts.parent.mkdir(parents=True, exist_ok=True)
    hosts.write_text('byo1 ansible_host="10.0.0.8"\n')

    def run(argv, tree):
        module = argv[argv.index("-m") + 1]
        with open(os.path.join(tree, "byo1"), "w", encoding="utf-8") as handle:
            if module == "ping":
                handle.write('{"ping": "pong"}')
            else:
                handle.write('{"ansible_facts": {"ansible_architecture": "x86_64"}}')
        return 0

    with pytest.raises(
        HostsError, match="byo1 architecture mismatch: config arm64, host x86_64"
    ):
        ping_hosts(paths, ["byo1"], run)


def test_hosts_check_uses_the_host_architecture_override(tmp_path):
    from spa.hosts import ping_hosts

    paths = _paths(
        tmp_path,
        "external: {}\n"
        "splunk_defaults:\n"
        "  splunk_architecture: arm64\n"
        "splunk_hosts:\n"
        "  - name: byo1\n"
        "    splunk_architecture: amd64\n"
        "    roles: [search_head]\n",
    )
    hosts = paths.inventory_dir / "hosts"
    hosts.parent.mkdir(parents=True, exist_ok=True)
    hosts.write_text('byo1 ansible_host="10.0.0.8"\n')

    def run(argv, tree):
        module = argv[argv.index("-m") + 1]
        with open(os.path.join(tree, "byo1"), "w", encoding="utf-8") as handle:
            if module == "ping":
                handle.write('{"ping": "pong"}')
            else:
                handle.write('{"ansible_facts": {"ansible_architecture": "x86_64"}}')
        return 0

    data = ping_hosts(paths, ["byo1"], run)
    assert data["hosts"][0]["ok"] is True
    assert data["hosts"][0]["expected_architecture"] == "amd64"
    assert data["hosts"][0]["architecture"] == "x86_64"


def test_hosts_check_uses_architecture_on_a_listed_host_block(tmp_path):
    from spa.hosts import HostsError, ping_hosts

    paths = _paths(
        tmp_path,
        "terraform:\n"
        "  aws:\n"
        "    region: eu-central-1\n"
        "splunk_defaults:\n"
        "  splunk_architecture: amd64\n"
        "splunk_hosts:\n"
        "  - list: [idx1]\n"
        "    splunk_architecture: arm64\n"
        "    roles: [indexer]\n",
    )
    hosts = paths.inventory_dir / "hosts"
    hosts.parent.mkdir(parents=True, exist_ok=True)
    hosts.write_text('idx1 ansible_host="10.0.0.8"\n')

    def run(argv, tree):
        module = argv[argv.index("-m") + 1]
        with open(os.path.join(tree, "idx1"), "w", encoding="utf-8") as handle:
            if module == "ping":
                handle.write('{"ping": "pong"}')
            else:
                handle.write('{"ansible_facts": {"ansible_architecture": "x86_64"}}')
        return 0

    with pytest.raises(
        HostsError, match="idx1 architecture mismatch: config arm64, host x86_64"
    ):
        ping_hosts(paths, ["idx1"], run)


def _ping_paths(tmp_path):
    key = tmp_path / "id_ed25519"
    key.write_text("not-read")
    paths = _external_paths(tmp_path, host="byo1", key=str(key))
    hosts = paths.inventory_dir / "hosts"
    hosts.parent.mkdir(parents=True, exist_ok=True)
    hosts.write_text('byo1 ansible_host="10.0.0.8"\n')
    return paths


def test_become_ping_reports_ssh_ok_when_sudo_fails(tmp_path, capsys):
    from spa.hosts import HostsError, ping_hosts

    def run(argv, tree):
        with open(os.path.join(tree, "byo1"), "w", encoding="utf-8") as handle:
            handle.write('{"failed": true, "msg": "Missing sudo password"}')
        return 2

    with pytest.raises(HostsError, match="SSH works for byo1, but passwordless sudo to root failed") as exc:
        ping_hosts(_ping_paths(tmp_path), ["byo1"], run)
    assert "Missing sudo password" in str(exc.value)
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""


def test_become_ping_reports_ssh_failure_without_blaming_sudo(tmp_path, capsys):
    from spa.hosts import HostsError, ping_hosts

    def run(argv, tree):
        with open(os.path.join(tree, "byo1"), "w", encoding="utf-8") as handle:
            handle.write('{"unreachable": true, "msg": "Connection refused"}')
        return 4

    with pytest.raises(HostsError, match="SSH failed for byo1") as exc:
        ping_hosts(_ping_paths(tmp_path), ["byo1"], run)
    assert "passwordless sudo" not in str(exc.value)
    assert "Connection refused" in str(exc.value)
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""


def test_status_ping_uses_the_same_call_without_become(tmp_path, monkeypatch):
    from spa import shell as shell_mod

    seen = {}

    def fake(hosts, paths=None, become=False, run=None):
        seen["become"] = become
        seen["hosts"] = list(hosts)
        return [
            {"name": "idx1", "ok": True, "ssh": True, "become": None, "message": ""},
            {"name": "idx2", "ok": False, "ssh": False, "become": None, "message": "timed out"},
        ], None

    monkeypatch.setattr(shell_mod, "ansible_ping", fake)
    status = shell_mod.check_ansible_status(["idx1", "idx2"])
    assert seen["become"] is False
    assert status == {"idx1": "Success", "idx2": "Unreachable"}


def _mixed_paths(tmp_path):
    config = (
        "terraform:\n"
        "  aws:\n"
        "    region: eu-central-1\n"
        "splunk_hosts:\n"
        "  - name: idx1\n"
        "    roles: [indexer]\n"
        "  - name: byo1\n"
        "    external:\n"
        "    roles: [search_head]\n"
        "    ansible_host: 10.0.0.8\n"
        "    ansible_user: splunk\n"
        "    ansible_ssh_private_key_file: /tmp/key\n"
    )
    return _paths(tmp_path, config)


def _write_named_inventory(paths, rows):
    paths.inventory_dir.mkdir(parents=True, exist_ok=True)
    lines = ["%s %s" % (name, body) for name, body in rows.items()]
    (paths.inventory_dir / "hosts").write_text("\n".join(lines) + "\n")


def _write_index_state(paths, index_keys):
    paths.terraform_state_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "resources": [
            {
                "type": "aws_instance",
                "name": "splunk",
                "instances": [{"index_key": name} for name in index_keys],
            }
        ]
    }
    (paths.terraform_state_dir / "terraform.tfstate").write_text(json.dumps(payload))


def _ready_session(paths, monkeypatch):
    from spa.api import LocalSpaSession

    monkeypatch.setattr("spa.executil.venv_required_error", lambda _paths: None)
    monkeypatch.setattr("spa.api.apply_paths_env", lambda *a, **k: {})
    return LocalSpaSession(paths=paths)


def test_mixed_destroy_does_not_target_external_names(tmp_path, monkeypatch):
    targeted = []

    def fake_destroy(self, extra, **kwargs):
        targeted.extend(extra)
        hosts = self.paths.inventory_dir / "hosts"
        if hosts.exists():
            hosts.unlink()
        return 0

    monkeypatch.setattr("spa.providers.aws.Provider.destroy", fake_destroy)
    paths = _mixed_paths(tmp_path)
    _write_named_inventory(
        paths,
        {"idx1": 'ansible_host="10.0.0.1"', "byo1": 'ansible_host="10.0.0.8"'},
    )
    _write_index_state(paths, ["idx1"])
    result = _ready_session(paths, monkeypatch).destroy(confirm=True)
    assert result.ok, result.error
    assert "byo1" not in targeted
    text = (paths.inventory_dir / "hosts").read_text(encoding="utf-8")
    assert "byo1" in text
    assert "idx1" not in text
    assert not paths.terraform_state_dir.exists()
    assert not paths.terraform_state_dir.parent.exists()


def test_destroy_keeps_terraform_when_another_directory_remains(tmp_path, monkeypatch):
    def fake_destroy(self, extra, **kwargs):
        hosts = self.paths.inventory_dir / "hosts"
        if hosts.exists():
            hosts.unlink()
        return 0

    monkeypatch.setattr("spa.providers.aws.Provider.destroy", fake_destroy)
    paths = _mixed_paths(tmp_path)
    _write_named_inventory(paths, {"idx1": 'ansible_host="10.0.0.1"'})
    _write_index_state(paths, ["idx1"])
    other = paths.terraform_state_dir.parent / "other"
    other.mkdir()
    (other / "keep.txt").write_text("keep\n", encoding="utf-8")
    result = _ready_session(paths, monkeypatch).destroy(confirm=True)
    assert result.ok, result.error
    assert not paths.terraform_state_dir.exists()
    assert paths.terraform_state_dir.parent.is_dir()
    assert (other / "keep.txt").read_text(encoding="utf-8") == "keep\n"


def test_failed_mixed_destroy_keeps_managed_inventory_lines(tmp_path, monkeypatch):
    def fake_destroy(self, extra, **kwargs):
        return 1

    monkeypatch.setattr("spa.providers.aws.Provider.destroy", fake_destroy)
    paths = _mixed_paths(tmp_path)
    _write_named_inventory(
        paths,
        {"idx1": 'ansible_host="10.0.0.1"', "byo1": 'ansible_host="10.0.0.8"'},
    )
    _write_index_state(paths, ["idx1"])
    before = (paths.inventory_dir / "hosts").read_text(encoding="utf-8")
    result = _ready_session(paths, monkeypatch).destroy(confirm=True)
    assert result.ok is False
    assert (paths.inventory_dir / "hosts").read_text(encoding="utf-8") == before
    assert paths.terraform_state_dir.is_dir()


def test_failed_mixed_provision_restores_the_external_inventory_line(tmp_path, monkeypatch):
    def fake_provision(self, extra, **kwargs):
        (self.paths.inventory_dir / "hosts").write_text('idx1 ansible_host="10.0.0.1"\n')
        return 1

    monkeypatch.setattr("spa.providers.aws.Provider.provision", fake_provision)
    paths = _mixed_paths(tmp_path)
    _write_named_inventory(
        paths,
        {"idx1": 'ansible_host="10.0.0.1"', "byo1": 'ansible_host="10.0.0.8"'},
    )
    result = _ready_session(paths, monkeypatch).provision(confirm=True, agent=True)
    assert result.ok is False
    text = (paths.inventory_dir / "hosts").read_text(encoding="utf-8")
    assert "idx1" in text
    assert "byo1" in text


def test_external_only_provision_does_not_prompt(tmp_path, monkeypatch, capsys):
    key = tmp_path / "id_ed25519"
    key.write_text("not-read")
    paths = _external_paths(tmp_path, host="byo1", key=str(key))

    def prompted(prompt):
        raise AssertionError(prompt)

    def connected(*_args, **_kwargs):
        raise AssertionError("ssh must not run")

    monkeypatch.setattr("builtins.input", prompted)
    monkeypatch.setattr("spa.providers.external.probe_ssh", connected)
    result = _ready_session(paths, monkeypatch).provision(confirm=False, agent=True)
    assert result.ok, result.error
    assert result.data["note"] == "SPA does not provision external hosts."
    captured = capsys.readouterr()
    assert "Proceed?" not in captured.out
    assert "Proceed?" not in captured.err


def test_mixed_provision_asks_and_names_the_external_hosts(tmp_path, monkeypatch, capsys):
    seen = {}

    def fake_confirm(label, *, confirm, agent, details=None, risk=None):
        seen["label"] = label
        seen["confirm"] = confirm

    def fake_provision(self, extra, **kwargs):
        seen["extra"] = list(extra)
        return 0

    def connected(*_args, **_kwargs):
        raise AssertionError("external provision must not connect")

    monkeypatch.setattr("spa.confirm.ensure_confirmed", fake_confirm)
    monkeypatch.setattr("spa.providers.aws.Provider.provision", fake_provision)
    monkeypatch.setattr("spa.providers.external.probe_ssh", connected)
    paths = _mixed_paths(tmp_path)
    result = _ready_session(paths, monkeypatch).provision(confirm=False)
    assert result.ok, result.error
    assert seen["label"] == "provision"
    assert seen["confirm"] is False
    assert "byo1" not in " ".join(seen["extra"])
    captured = capsys.readouterr()
    assert "SPA does not provision external hosts: byo1" in captured.err


def test_provision_refuses_when_terraform_state_still_has_the_external_name(tmp_path, monkeypatch):
    paths = _mixed_paths(tmp_path)
    _write_index_state(paths, ["idx1", "byo1"])
    result = _ready_session(paths, monkeypatch).provision(confirm=True)
    assert result.ok is False
    assert "byo1" in result.error
    assert "will not destroy" in result.error


def test_mixed_provision_state_ignores_external_names_in_terraform(tmp_path):
    from spa.providers import get_provider

    paths = _mixed_paths(tmp_path)
    _write_index_state(paths, ["idx1"])
    _write_named_inventory(
        paths,
        {"idx1": 'ansible_host="10.0.0.1"', "byo1": 'ansible_host="10.0.0.8"'},
    )
    state = get_provider(paths).provision_state()
    assert state.provisioned is True
    assert state.missing == ()
    (paths.inventory_dir / "hosts").write_text('idx1 ansible_host="10.0.0.1"\n')
    state = get_provider(paths).provision_state()
    assert state.missing == ("byo1",)


def test_suspend_of_only_an_external_host_does_not_call_aws(tmp_path, monkeypatch):
    def boom(*_args, **_kwargs):
        raise AssertionError("aws suspend")

    monkeypatch.setattr("spa.providers.aws.Provider.suspend", boom)
    monkeypatch.setattr(
        "spa.shell.get_inventory_data",
        lambda: {"_meta": {"hostvars": {"idx1": {}, "byo1": {}}}},
    )
    paths = _mixed_paths(tmp_path)
    _write_index_state(paths, ["idx1"])
    _write_named_inventory(
        paths,
        {"idx1": 'ansible_host="10.0.0.1"', "byo1": 'ansible_host="10.0.0.8"'},
    )
    result = _ready_session(paths, monkeypatch).suspend(confirm=True, hosts=["byo1"])
    assert result.ok is False
    assert result.error == "SPA does not own power for external hosts: byo1"


def test_vagrant_refuses_a_created_external_name(tmp_path, monkeypatch):
    called = []

    def fake_run(self, *args, **kwargs):
        called.append(args)
        raise AssertionError("vagrant ran")

    monkeypatch.setattr("spa.providers.virtualbox.Provider._run", fake_run)
    monkeypatch.setattr(
        "spa.providers.virtualbox.Provider._machine_states",
        lambda self: {"byo1": "running"},
    )
    config = (
        "virtualbox:\n"
        "  start_ip: 192.168.56.10\n"
        "splunk_hosts:\n"
        "  - name: idx1\n"
        "    roles: [indexer]\n"
        "  - name: byo1\n"
        "    external:\n"
        "    ansible_host: 10.0.0.8\n"
        "    ansible_user: splunk\n"
        "    ansible_ssh_private_key_file: /tmp/key\n"
    )
    paths = _paths(tmp_path, config)
    result = _ready_session(paths, monkeypatch).provision(confirm=True)
    assert result.ok is False
    assert "will not destroy" in result.error
    assert not called


def test_user_guide_registers_existing_servers():
    from spa_testutil import PROJECT_ROOT

    text = (PROJECT_ROOT / "docs" / "user-guide.md").read_text(encoding="utf-8")
    assert "spa hosts register NAME --address ADDRESS --user USER --key PATH --yes" in text
    assert "does not create, shut down, or terminate" in text
    assert "spa hosts check" in text
    assert "before the playbook" in text
    assert "--allow-unprovisioned" not in text



