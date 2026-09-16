"""Provider selection and AWS lifecycle tests (no cloud calls)."""

from dataclasses import replace
from types import SimpleNamespace

import pytest

from spa.paths import resolve_spa_paths
from spa.providers import ProviderError, detect_provider
from spa.providers.aws import Provider as AwsProvider
from spa_testutil import PROJECT_ROOT

pytestmark = [pytest.mark.local, pytest.mark.cli]


def _paths(tmp_path, config):
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


def test_detects_aws_from_terraform_config(tmp_path):
    paths = _paths(tmp_path, "terraform:\n  aws:\n    region: eu-central-1\n")
    selected = detect_provider(paths)
    assert selected.name == "aws"
    assert selected.config["region"] == "eu-central-1"


def test_provider_detection_rejects_multiple_providers(tmp_path):
    paths = _paths(
        tmp_path,
        "terraform:\n  aws: {}\n  gcp: {}\n",
    )
    with pytest.raises(ProviderError, match="Multiple terraform providers"):
        detect_provider(paths)


def test_future_provider_is_recognized_but_not_implemented(tmp_path):
    paths = _paths(tmp_path, "terraform:\n  gcp:\n    project: example\n")
    with pytest.raises(ProviderError, match="not implemented"):
        detect_provider(paths)


def test_detects_virtualbox_from_config(tmp_path):
    paths = _paths(tmp_path, "virtualbox:\n  memory: 4096\n")
    selected = detect_provider(paths)
    assert selected.name == "virtualbox"
    assert selected.config["memory"] == 4096


def test_legacy_aws_is_not_mistaken_for_terraform(tmp_path):
    paths = _paths(tmp_path, "aws:\n  region: eu-central-1\n")
    with pytest.raises(ProviderError, match="inventory-only"):
        detect_provider(paths)


def test_virtualbox_cli_accepts_env_dir(tmp_path, monkeypatch):
    called = {}

    class FakeProvider:
        name = "virtualbox"

        def suspend(self, **kwargs):
            called.update(kwargs)
            return {"instances": []}

    monkeypatch.setattr("spa.providers.get_provider", lambda _paths: FakeProvider())
    from spa.providers import ProvisionState

    monkeypatch.setattr(
        "spa.providers.check_provisioned",
        lambda paths: ProvisionState(provider="virtualbox", provisioned=True),
    )
    from spa.cli import main

    rc = main(["--no-agent", "suspend", "--yes"])
    assert rc == 0
    assert called.get("yes") is True


def _vbox_paths(tmp_path, config="virtualbox:\n  memory: 4096\nsplunk_hosts:\n  - name: idx1\n    roles: [indexer]\n"):
    home = tmp_path / "home"
    env = tmp_path / "env"
    home.mkdir()
    env.mkdir()
    (home / "Vagrantfile").write_text("# test\n")
    config_path = env / "config" / "splunk_config.yml"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(config)
    inv = env / "inventory"
    inv.mkdir()
    base = resolve_spa_paths(start_dir=PROJECT_ROOT)
    return replace(
        base,
        spa_home=home,
        spa_env_dir=env,
        config_file=config_path,
        inventory_dir=inv,
        roots_differ=True,
    )


class _Waiter:
    def __init__(self, calls, name):
        self.calls = calls
        self.name = name

    def wait(self, **kwargs):
        self.calls.append(("wait", self.name, kwargs["InstanceIds"]))


class _Ec2:
    def __init__(self, state):
        self.state = state
        self.calls = []

    def describe_instances(self, InstanceIds):
        instances = []
        for instance_id in InstanceIds:
            instances.append(
                {
                    "InstanceId": instance_id,
                    "State": {"Name": self.state},
                    "PublicDnsName": "host.example.test" if self.state == "running" else "",
                    "PublicIpAddress": "192.0.2.10" if self.state == "running" else "",
                    "PrivateDnsName": "ip-10-0-0-10.internal",
                    "PrivateIpAddress": "10.0.0.10",
                }
            )
        return {"Reservations": [{"Instances": instances}]}

    def stop_instances(self, InstanceIds):
        self.calls.append(("stop", InstanceIds))
        self.state = "stopped"

    def start_instances(self, InstanceIds):
        self.calls.append(("start", InstanceIds))
        self.state = "running"

    def get_waiter(self, name):
        return _Waiter(self.calls, name)


def _aws_provider(tmp_path):
    paths = _paths(tmp_path, "terraform:\n  aws:\n    region: eu-central-1\n")
    provider = AwsProvider(paths, {"region": "eu-central-1", "ssh_username": "ec2-user"})
    provider._targets = lambda: {"idx1": {"id": "i-123", "state": "running"}}
    return provider


def test_suspend_stops_and_waits_without_destroying_state(tmp_path):
    provider = _aws_provider(tmp_path)
    ec2 = _Ec2("running")
    provider._ec2 = lambda: ec2
    result = provider.suspend(yes=True, agent=False)
    assert ("stop", ["i-123"]) in ec2.calls
    assert ("wait", "instance_stopped", ["i-123"]) in ec2.calls
    assert result["instances"][0]["state"] == "stopped"
    assert "charges" in result["note"]


def test_aws_provider_host_status_indexes_inventory_identifiers(tmp_path):
    provider = _aws_provider(tmp_path)
    provider._ec2 = lambda: _Ec2("running")

    status = provider.host_status()

    assert status["idx1"]["state"] == "running"
    assert status["idx1"]["reachable"] is True
    assert status["i-123"]["state"] == "running"
    assert status["192.0.2.10"]["state"] == "running"
    assert status["10.0.0.10"]["state"] == "running"


def test_shell_host_report_uses_provider_snapshot(monkeypatch):
    from spa import shell

    inventory = {
        "_meta": {
            "hostvars": {
                "idx1": {"ansible_host": "host.example.test"},
                "idx2": {"ansible_host": "stopped.example.test"},
            }
        },
        "role_indexer": {"hosts": ["idx1", "idx2"]},
    }
    snapshot = {
        "name": "testcloud",
        "hosts": {
            "host.example.test": {"state": "running", "reachable": True},
            "stopped.example.test": {"state": "stopped", "reachable": False},
        },
        "error": None,
    }
    checked = {}

    def fake_ansible(hosts):
        checked["hosts"] = hosts
        return {host: "Success" for host in hosts}

    monkeypatch.setattr(shell, "check_ansible_status", fake_ansible)
    report = shell.host_report(
        inventory, verbose=True, provider_snapshot=snapshot
    )

    rows = {row["name"]: row for row in report["hosts"]}
    assert report["provider"] == "testcloud"
    assert rows["idx1"]["provider_status"] == "running"
    assert rows["idx1"]["ansible"] == "Success"
    assert rows["idx2"]["provider_status"] == "stopped"
    assert rows["idx2"]["ansible"] == "N/A"
    assert checked["hosts"] == ["idx1"]


def test_shell_host_report_runtime_false_skips_checks(monkeypatch):
    from spa import shell

    inventory = {
        "_meta": {"hostvars": {"idx1": {}}},
        "role_indexer": {"hosts": ["idx1"]},
    }
    monkeypatch.setattr(
        shell,
        "check_ansible_status",
        lambda hosts: (_ for _ in ()).throw(AssertionError("ping")),
    )
    monkeypatch.setattr(
        shell,
        "get_provider_status",
        lambda paths=None: (_ for _ in ()).throw(AssertionError("provider")),
    )
    report = shell.host_report(inventory, verbose=True, runtime=False)
    rows = {row["name"]: row for row in report["hosts"]}
    assert rows["idx1"]["ansible"] == "unprovisioned"
    assert rows["idx1"]["provider_status"] == "unprovisioned"
    assert report["provider"] is None


def test_resume_starts_waits_and_refreshes_inventory(tmp_path):
    provider = _aws_provider(tmp_path)
    ec2 = _Ec2("stopped")
    provider._ec2 = lambda: ec2
    provider._terraform_output = lambda name: {
        "idx1": {
            "ansible_user": "ec2-user",
            "ansible_ssh_private_key_file": "~/.ssh/test key.pem",
        }
    }
    result = provider.resume(yes=True, agent=False)
    assert ("start", ["i-123"]) in ec2.calls
    assert ("wait", "instance_running", ["i-123"]) in ec2.calls
    assert ("wait", "instance_status_ok", ["i-123"]) in ec2.calls
    inventory = (tmp_path / "inventory" / "hosts").read_text()
    assert 'ansible_host="host.example.test"' in inventory
    assert 'ansible_ssh_private_key_file="~/.ssh/test key.pem"' in inventory
    assert result["inventory"].endswith("inventory/hosts")


def test_suspend_hosts_filters_targets(tmp_path):
    provider = _aws_provider(tmp_path)
    provider._targets = lambda: {
        "idx1": {"id": "i-123", "state": "running"},
        "sh1": {"id": "i-456", "state": "running"},
    }
    ec2 = _Ec2("running")
    provider._ec2 = lambda: ec2
    result = provider.suspend(yes=True, agent=False, hosts=["sh1"])
    assert ("stop", ["i-456"]) in ec2.calls
    assert [row["name"] for row in result["instances"]] == ["sh1"]


@pytest.mark.parametrize("action", ["suspend", "resume"])
def test_confirm_groups_hosts_by_role(tmp_path, monkeypatch, capsys, action):
    """50 hosts must not print 50 lines; group them by role instead."""
    provider = _aws_provider(tmp_path)
    monkeypatch.setattr("builtins.input", lambda prompt: "y")
    monkeypatch.setattr(
        "spa.hosts.load_inventory",
        lambda: {
            "role_indexer": {"hosts": ["idx1", "idx2", "idx3"]},
            "role_search_head": {"hosts": ["sh1", "sh2"]},
        },
    )
    targets = {name: {} for name in ["idx1", "idx2", "idx3", "sh1", "sh2", "dpl"]}

    provider._confirm(action, targets, yes=False, agent=False)

    err = capsys.readouterr().err
    assert "%s 6 AWS instances:" % action.capitalize() in err
    assert "  indexer (3): idx1, idx2, idx3" in err
    assert "  search head (2): sh1, sh2" in err
    assert "  no role (1): dpl" in err


def test_confirm_trims_very_long_role_lines(tmp_path, monkeypatch, capsys):
    provider = _aws_provider(tmp_path)
    monkeypatch.setattr("builtins.input", lambda prompt: "y")
    names = ["idx%02d" % index for index in range(1, 51)]
    monkeypatch.setattr("spa.hosts.load_inventory", lambda: {"role_indexer": {"hosts": names}})

    provider._confirm("suspend", {name: {} for name in names}, yes=False, agent=False)

    err = capsys.readouterr().err
    assert "Suspend 50 AWS instances:" in err
    role_line = next(line for line in err.splitlines() if line.startswith("  indexer"))
    assert "indexer (50):" in role_line
    assert "more" in role_line
    assert len(role_line) < 100


def test_agent_lifecycle_requires_yes(tmp_path):
    provider = _aws_provider(tmp_path)
    with pytest.raises(ProviderError, match="requires -y/--yes"):
        provider.suspend(yes=False, agent=True)


def test_terraform_output_requires_state(tmp_path):
    provider = _aws_provider(tmp_path)
    with pytest.raises(ProviderError, match="Run spa provision first"):
        provider._terraform_output("instance_states")


def test_terraform_error_does_not_echo_diagnostics(monkeypatch, tmp_path):
    provider = _aws_provider(tmp_path)
    provider.state_dir.mkdir(parents=True)
    (provider.state_dir / "terraform.tfstate").write_text("{}")
    monkeypatch.setattr("spa.providers.aws.tool_path", lambda paths, name: "terraform")
    monkeypatch.setattr(
        "spa.providers.aws.subprocess.run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=1,
            stdout="",
            stderr="AWS_SECRET_ACCESS_KEY=must-not-be-emitted",
        ),
    )
    with pytest.raises(ProviderError) as excinfo:
        provider._terraform_output("instance_states")
    assert "must-not-be-emitted" not in str(excinfo.value)


def test_parse_machine_readable_status():
    from spa.providers.virtualbox import parse_machine_readable_status

    text = "\n".join(
        [
            "1,idx1,provider-name,virtualbox",
            "1,idx1,state,running",
            "1,sh1,state,poweroff",
        ]
    )
    assert parse_machine_readable_status(text) == {"idx1": "running", "sh1": "poweroff"}


def test_drop_ansible_extra_strips_auto_approve():
    from spa.providers.virtualbox import drop_ansible_extra

    assert drop_ansible_extra(["-e", "auto_approve=true", "idx1"]) == ["idx1"]


def test_virtualbox_suspend_runs_vagrant_halt(tmp_path, monkeypatch):
    from spa.providers.virtualbox import Provider as VboxProvider

    paths = _vbox_paths(tmp_path)
    provider = VboxProvider(paths, {"memory": 4096})
    calls = []

    def fake_run(cmd, cwd=None, capture_output=False, text=True, env=None):
        calls.append((cmd[1:], cwd, capture_output, env))
        if cmd[1] == "status":
            return SimpleNamespace(
                returncode=0,
                stdout="1,idx1,state,poweroff\n",
                stderr="",
            )
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr("spa.providers.virtualbox.tool_path", lambda paths, name: "vagrant")
    monkeypatch.setattr("spa.providers.virtualbox.subprocess.run", fake_run)
    result = provider.suspend(yes=True, agent=False, hosts=["idx1"])
    assert ["halt", "idx1"] in [c[0] for c in calls]
    assert calls[0][1] == str(paths.spa_home)
    vagrant_env = calls[0][3]
    assert vagrant_env["VAGRANT_CWD"] == str(paths.spa_home)
    assert vagrant_env["VAGRANT_DOTFILE_PATH"] == str(paths.spa_env_dir / ".vagrant")
    assert result["instances"][0]["name"] == "idx1"


def test_virtualbox_refuses_stale_other_provider_state(tmp_path, monkeypatch):
    from spa.providers.virtualbox import Provider as VboxProvider

    paths = _vbox_paths(tmp_path)
    (paths.spa_env_dir / ".vagrant" / "machines" / "idx1" / "aws").mkdir(parents=True)
    provider = VboxProvider(paths, {})

    def fake_run(*_args, **_kwargs):
        raise AssertionError("vagrant must not run with stale aws state")

    monkeypatch.setattr("spa.providers.virtualbox.tool_path", lambda paths, name: "vagrant")
    monkeypatch.setattr("spa.providers.virtualbox.subprocess.run", fake_run)
    with pytest.raises(ProviderError) as excinfo:
        provider.provision([])
    message = str(excinfo.value)
    assert "another provider (aws)" in message
    assert "rm -rf" in message
    assert str(paths.spa_env_dir / ".vagrant" / "machines" / "idx1" / "aws") in message


def test_virtualbox_accepts_own_machine_state(tmp_path, monkeypatch):
    from spa.providers.virtualbox import Provider as VboxProvider

    paths = _vbox_paths(tmp_path)
    (paths.spa_env_dir / ".vagrant" / "machines" / "idx1" / "virtualbox").mkdir(parents=True)
    provider = VboxProvider(paths, {})
    monkeypatch.setattr("spa.providers.virtualbox.tool_path", lambda paths, name: "vagrant")
    monkeypatch.setattr(
        "spa.providers.virtualbox.subprocess.run",
        lambda *a, **k: SimpleNamespace(returncode=0, stdout="", stderr=""),
    )
    assert provider.provision([]) == 0


def test_virtualbox_provision_drops_ansible_flags(tmp_path, monkeypatch):
    from spa.providers.virtualbox import Provider as VboxProvider

    paths = _vbox_paths(tmp_path)
    provider = VboxProvider(paths, {})
    seen = []

    def fake_run(cmd, cwd=None, capture_output=False, text=True, env=None):
        seen.append((cmd[1:], env))
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr("spa.providers.virtualbox.tool_path", lambda paths, name: "vagrant")
    monkeypatch.setattr("spa.providers.virtualbox.subprocess.run", fake_run)
    assert provider.provision(["-e", "auto_approve=true"]) == 0
    assert seen[0][0] == ["up"]
    assert seen[0][1]["VAGRANT_CWD"] == str(paths.spa_home)
    assert seen[0][1]["VAGRANT_DOTFILE_PATH"] == str(paths.spa_env_dir / ".vagrant")
