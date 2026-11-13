"""External / BYO SSH hosts."""

import json
import os
import sys

import yaml

import pytest
from pydantic import ValidationError

pytestmark = [pytest.mark.local, pytest.mark.cli]


@pytest.fixture(autouse=True)
def _isolate_ansible_fact_cache(tmp_path, monkeypatch):
    """Keep ping tests off the operator's real /tmp/ansible_facts cache."""
    monkeypatch.setenv("ANSIBLE_CACHE_PLUGIN_CONNECTION", str(tmp_path / "unused-fact-cache"))

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "ansible", "plugins", "inventory"))

from schema import SplunkConfig  # noqa: E402
from spa.providers.classify import classify_hostnames  # noqa: E402

_PASSWORD = "{{ lookup('env', 'SPLUNK_ADMIN_PASSWORD') }}"


def _touch_linux_archive(software, architecture="amd64", version="9.3.2"):
    name = "splunk-%s-000000000000-linux-%s.tgz" % (version, architecture)
    (software / name).write_bytes(b"dummy")


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
    if "schema_version:" not in config:
        config = "schema_version: 1\n" + config
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


def test_hosts_entries_use_ansible_host_when_external_hosts_have_no_ip_addr():
    import yaml
    from ansible.parsing.dataloader import DataLoader
    from ansible.template import Templar, trust_as_template

    from spa_testutil import PROJECT_ROOT

    data = yaml.safe_load(
        (PROJECT_ROOT / "ansible" / "group_vars" / "all" / "dynamic.yml").read_text(encoding="utf-8")
    )
    templar = Templar(
        loader=DataLoader(),
        variables={
            "hostvars": {
                "shidx": {"ansible_host": "10.1.2.3"},
                "idx1": {"ip_addr": "10.9.9.9", "ansible_host": "203.0.113.5"},
            }
        },
    )
    rendered = str(templar.template(trust_as_template(data["splunk_hosts_entries"])))
    assert "10.1.2.3 shidx" in rendered
    assert "10.9.9.9 idx1" in rendered
    assert "203.0.113.5" not in rendered


def _link_page_host(hostname="shidx", **overrides):
    """Hostvars for one link-page host. Tests must not put secrets in the HTML."""
    values = {
        "splunk_env_name": "lab",
        "ansible_host": "10.1.2.3",
        "splunk_ssl": {"web": {"enable": True}},
    }
    values.update(overrides)
    return {hostname: values}


def _render_link_page(groups=None, hostvars=None, extra=None):
    from ansible.parsing.dataloader import DataLoader
    from ansible.template import Templar, trust_as_template

    from spa_testutil import PROJECT_ROOT

    text = (
        PROJECT_ROOT / "ansible" / "roles" / "splunk_control" / "templates" / "config" / "index.html.j2"
    ).read_text(encoding="utf-8")
    variables = {
        "groups": groups or {
            "splunk_env_lab": ["shidx"],
            "role_search_head": ["shidx"],
        },
        "hostvars": hostvars if hostvars is not None else _link_page_host(),
        "url_locale": "en-GB",
    }
    if extra:
        variables.update(extra)
    return str(Templar(loader=DataLoader(), variables=variables).template(trust_as_template(text)))


def _link_page_anchor_tags(rendered):
    import re

    return re.findall(r"<a\b[^>]*>", rendered, flags=re.IGNORECASE)


def _link_page_tags(rendered, name="article"):
    import re

    return re.findall(r"<%s\b[^>]*>" % name, rendered, flags=re.IGNORECASE)


def _link_page_attr(tag, name):
    import re

    match = re.search(r'\b%s="([^"]*)"' % re.escape(name), tag)
    return match.group(1) if match else None


def _link_page_host_tags(rendered):
    import re

    rows = []
    for match in re.finditer(r"<[^>]+data-host=\"([^\"]+)\"[^>]*>", rendered):
        tag = match.group(0)
        rows.append({
            "host": match.group(1),
            "cluster": _link_page_attr(tag, "data-cluster"),
            "tag": tag,
        })
    return rows


def _link_page_edges(rendered):
    import re

    blobs = re.findall(
        r'<script type="application/json" class="architecture-edges">\s*(.*?)\s*</script>',
        rendered,
        flags=re.S,
    )
    edges = []
    for raw in blobs:
        payload = json.loads(raw)
        assert isinstance(payload, list)
        edges.extend(payload)
    return edges


def _link_page_visible_chip(rendered, hostname):
    import re

    match = re.search(
        r'<article\b[^>]*data-host="%s"[^>]*>.*?</article>' % re.escape(hostname),
        rendered,
        flags=re.S,
    )
    assert match, "missing article for %s" % hostname
    html = match.group(0)
    return html.split("<details", 1)[0] if "<details" in html else html


def _expand_iter_hostnames(spec):
    numbers = spec["numbers"]
    start, end = numbers.split("..", 1)
    width = len(end)
    prefix = spec.get("prefix") or ""
    postfix = spec.get("postfix") or ""
    names = []
    for number in range(int(start), int(end) + 1):
        names.append("%s%s%s" % (prefix, str(number).zfill(width), postfix))
    return names


def _topology_hostnames(entry):
    if entry.get("name"):
        return [entry["name"]]
    if entry.get("list"):
        return list(entry["list"])
    if entry.get("iter"):
        return _expand_iter_hostnames(entry["iter"])
    return []


def _inventory_from_topology(config):
    """Expand a topology YAML the way the inventory plugin groups hosts."""
    defaults = config.get("splunk_defaults") or {}
    default_env = defaults.get("splunk_env_name") or "splk"
    groups = {}
    hostvars = {}

    def add(group, hostname):
        members = groups.setdefault(group, [])
        if hostname not in members:
            members.append(hostname)

    for entry in config.get("splunk_hosts") or []:
        roles = list(entry.get("roles") or [])
        env_name = entry.get("splunk_env") or default_env
        idxcluster = entry.get("idxcluster")
        shcluster = entry.get("shcluster")
        site = entry.get("site")
        for hostname in _topology_hostnames(entry):
            add("splunk_env_%s" % env_name, hostname)
            values = {
                "splunk_env_name": env_name,
                "ansible_host": "%s.example.test" % hostname,
                "splunk_ssl": {"web": {"enable": True}},
            }
            if site:
                values["site"] = site
            if entry.get("splunk_version"):
                values["splunk_version"] = entry["splunk_version"]
            hostvars[hostname] = values
            for role in roles:
                add("role_%s" % role, hostname)
                if role in ("indexer", "cluster_manager") and idxcluster:
                    add("idxcluster_%s" % idxcluster, hostname)
                    if role == "indexer" and site:
                        add("idxcluster_%s_%s" % (idxcluster, site), hostname)
                if role in ("search_head", "deployer") and shcluster:
                    add("shcluster_%s" % shcluster, hostname)
                    if role == "search_head" and site:
                        add("shcluster_%s_%s" % (shcluster, site), hostname)
    extra = {}
    if defaults:
        extra["splunk_defaults"] = defaults
    if config.get("splunk_app_deployment"):
        extra["splunk_app_deployment"] = config["splunk_app_deployment"]
    if config.get("terraform"):
        extra["terraform"] = config["terraform"]
    if config.get("virtualbox"):
        extra["virtualbox"] = config["virtualbox"]
    if config.get("ccm"):
        extra["ccm"] = config["ccm"]
    if config.get("external") is not None:
        extra["external"] = config["external"]
    return groups, hostvars, extra


def _topology_files():
    from spa_testutil import PROJECT_ROOT

    files = sorted((PROJECT_ROOT / "examples" / "topologies").glob("*.yml"))
    files.append(PROJECT_ROOT / "examples" / "single_node_itsi.yml")
    return files


def test_link_page_uses_ansible_host_when_dns_and_ip_addr_are_absent():
    rendered = _render_link_page()
    assert "https://10.1.2.3:8000/" in rendered
    assert "https://unknown:" not in rendered
    assert "Reachable address" in rendered
    assert "10.1.2.3" in rendered
    assert "Private IP" not in rendered


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


def test_external_provision_does_not_ssh(tmp_path):
    from spa.providers.external import Provider, inventory_line

    key = tmp_path / "id_ed25519"
    key.write_text("not-read")
    hosts = tmp_path / "inventory" / "hosts"
    hosts.parent.mkdir()
    hosts.write_text(
        inventory_line("byo1", "10.0.0.8", "splunk", str(key), 22) + "\n"
    )
    before = hosts.read_bytes()
    paths = _external_paths(tmp_path, host="byo1", key=str(key))
    seen = []

    def run(argv):
        seen.append(list(argv))
        return 0

    result = Provider(paths, {}, run=run).provision([])
    assert seen == []
    assert hosts.read_bytes() == before
    assert result["action"] == "provision"


def test_external_status_captures_ssh_stderr(tmp_path, monkeypatch):
    from types import SimpleNamespace

    from spa.providers.external import Provider, inventory_line

    key = tmp_path / "id_ed25519"
    key.write_text("not-read")
    hosts = tmp_path / "inventory" / "hosts"
    hosts.parent.mkdir()
    hosts.write_text(inventory_line("byo1", "10.0.0.8", "splunk", str(key), 22) + "\n")
    paths = _external_paths(tmp_path, host="byo1", key=str(key))
    seen = {}

    def fake_run(argv, **kwargs):
        seen["kwargs"] = kwargs
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr("subprocess.run", fake_run)
    status = Provider(paths, {}).host_status("byo1")
    assert seen["kwargs"].get("capture_output") is True
    assert status["reachable"] is True


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


def test_register_ssh_port_writes_ansible_port(tmp_path):
    from spa_testutil import run_spa, run_spa_inprocess

    key = tmp_path / "id_ed25519"
    key.write_text("not-read")
    dest = _external_env(tmp_path)
    result = run_spa(
        [
            "--agent", "hosts", "register", "byo1",
            "--ssh-host", "203.0.113.10",
            "--ssh-port", "2222",
            "--user", "splunk",
            "--key", str(key),
            "--yes",
        ],
        env=_cli_env(dest, _fake_ssh(tmp_path)),
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["data"]["ansible_port"] == 2222
    listed = (dest / "inventory" / "hosts").read_text(encoding="utf-8")
    assert "ansible_port=2222" in listed
    help_result = run_spa_inprocess(["hosts", "register", "--help"])
    assert "--ssh-port" in help_result.stdout
    assert "--port" not in help_result.stdout
    text = help_result.stdout
    assert text.index("--ssh-host") < text.index("--ssh-port") < text.index("--ip-addr")


def test_register_ssh_host_and_optional_ip_addr(tmp_path):
    from spa_testutil import run_spa

    key = tmp_path / "id_ed25519"
    key.write_text("not-read")
    dest = _external_env(tmp_path)
    env = _cli_env(dest, _fake_ssh(tmp_path))
    with_addr = run_spa(
        [
            "--agent", "hosts", "register", "byo1",
            "--ssh-host", "203.0.113.10",
            "--ip-addr", "10.0.0.10",
            "--user", "splunk",
            "--key", str(key),
            "--yes",
        ],
        env=env,
    )
    assert with_addr.returncode == 0, with_addr.stderr
    payload = json.loads(with_addr.stdout)
    assert payload["data"]["ansible_host"] == "203.0.113.10"
    assert payload["data"]["ip_addr"] == "10.0.0.10"
    listed = (dest / "inventory" / "hosts").read_text(encoding="utf-8")
    assert 'ansible_host="203.0.113.10"' in listed
    assert 'ip_addr="10.0.0.10"' in listed
    config_text = (dest / "config" / "splunk_config.yml").read_text(encoding="utf-8")
    assert "ip_addr" not in config_text
    assert "ansible_host" not in config_text

    plain = run_spa(
        [
            "--agent", "hosts", "register", "byo2",
            "--ssh-host", "203.0.113.11",
            "--user", "splunk",
            "--key", str(key),
            "--yes",
        ],
        env=env,
    )
    assert plain.returncode == 0, plain.stderr
    plain_data = json.loads(plain.stdout)["data"]
    assert plain_data["ansible_host"] == "203.0.113.11"
    assert "ip_addr" not in plain_data
    listed = (dest / "inventory" / "hosts").read_text(encoding="utf-8")
    byo2 = next(line for line in listed.splitlines() if line.startswith("byo2 "))
    assert "ip_addr" not in byo2


def test_link_page_keeps_the_ssh_host_when_ip_addr_is_internal():
    rendered = _render_link_page(
        hostvars=_link_page_host(ansible_host="203.0.113.10", ip_addr="10.0.0.10"),
    )
    assert "https://203.0.113.10:8000/" in rendered
    assert "https://10.0.0.10:8000/" not in rendered
    assert "Reachable address" in rendered
    assert "203.0.113.10" in rendered
    assert "Private IP" in rendered
    assert "10.0.0.10" in rendered


def test_link_page_uses_public_dns_name_as_reachable_address():
    rendered = _render_link_page(
        hostvars=_link_page_host(
            public_dns_name="ec2-1-2-3-4.compute.example",
            ansible_host="203.0.113.10",
            ip_addr="10.0.0.10",
        ),
    )
    assert "https://ec2-1-2-3-4.compute.example:8000/" in rendered
    assert "https://203.0.113.10:8000/" not in rendered
    assert "Reachable address" in rendered
    assert "ec2-1-2-3-4.compute.example" in rendered
    assert "Private IP" in rendered
    assert "10.0.0.10" in rendered


def test_link_page_styles_offline_without_bootstrap():
    rendered = _render_link_page()
    lower = rendered.lower()
    assert "jsdelivr" not in lower
    assert "bootstrap" not in lower
    assert "cdn.jsdelivr.net" not in lower
    assert "<style>" in lower
    assert "prefers-color-scheme" in lower
    assert ":focus" in lower
    assert "--" in rendered


def test_link_page_header_names_the_env_and_omits_secrets():
    sentinel_password = "sentinel-admin-password-do-not-emit"
    sentinel_key = "/tmp/sentinel-key-path-do-not-emit"
    rendered = _render_link_page(
        hostvars=_link_page_host(
            splunk_admin_password=sentinel_password,
            ansible_ssh_private_key_file=sentinel_key,
        ),
    )
    assert "<header" in rendered
    header = rendered[rendered.index("<header") : rendered.index("</header>")]
    assert "lab" in header
    assert "banner" in header
    assert 'class="meta"' in header
    assert "spa hosts ssh HOST" not in header
    assert "spa hosts list --status" not in header
    assert "Splunk Web user" not in header
    assert "does not include the password" not in header
    assert "Env: lab" not in rendered
    assert sentinel_password not in rendered
    assert sentinel_key not in rendered
    assert "<h1><p" not in rendered
    assert 'class="container-fluid" class=' not in rendered


def test_link_page_prints_generated_time_from_extra():
    rendered = _render_link_page()
    assert "Generated 2026" not in rendered
    stamped = _render_link_page(extra={"linkpage_generated_at": "2026-11-12T22:00:00Z"})
    header = stamped[stamped.index("<header") : stamped.index("</header>")]
    title = header[header.index("<h1") : header.index('class="meta"')]
    assert "<strong>Generated</strong>" in title
    assert 'data-utc="2026-11-12T22:00:00Z"' in title
    assert "function parseUtc" in stamped
    assert "function formatLocal" in stamped
    assert "Expires" not in title


def test_link_page_details_uses_a_disclosure_chevron():
    rendered = _render_link_page()
    article = rendered[rendered.index("<article") : rendered.index("</article>")]
    assert "<summary>Details</summary>" not in article
    assert 'aria-label="Details"' in article
    assert "article.host summary::after" in rendered
    assert "article.host details[open] summary::after" in rendered


def test_link_page_uses_semantic_host_articles():
    rendered = _render_link_page()
    assert "<main" in rendered
    assert "<article" in rendered
    tags = _link_page_tags(rendered, "article")
    assert tags
    article = rendered[rendered.index("<article") : rendered.index("</article>")]
    assert "shidx" in article
    assert "Search Head" in article


def test_link_page_web_links_open_with_noopener():
    rendered = _render_link_page()
    anchors = _link_page_anchor_tags(rendered)
    assert anchors
    for tag in anchors:
        if 'target="_blank"' in tag or "target='_blank'" in tag:
            assert 'rel="noopener noreferrer"' in tag
    chip = _link_page_visible_chip(rendered, "shidx")
    roles = chip[chip.index('<ul class="roles"'):]
    assert 'href="https://10.1.2.3:8000/en-GB/app/launcher/home"' in roles
    assert ">Search Head</a>" in roles
    assert ">Splunk Web<" not in rendered


def test_link_page_clickable_role_badges_have_a_thicker_border():
    rendered = _render_link_page(
        groups={
            "splunk_env_lab": ["shidx"],
            "role_search_head": ["shidx"],
            "role_indexer": ["shidx"],
        },
        hostvars=_link_page_host(),
    )
    chip = _link_page_visible_chip(rendered, "shidx")
    roles = chip[chip.index('<ul class="roles"'):]
    assert '<li class="is-link">' in roles
    assert ">Search Head</a>" in roles
    assert "<li>Indexer</li>" in roles
    assert roles.count('class="is-link"') == 1
    assert "header .chip-provider" in rendered
    assert ".roles li.is-link" in rendered
    assert "border: 1px solid var(--border)" in rendered
    assert "border: 1px solid transparent" in rendered
    assert "border-color: var(--accent)" in rendered


def test_link_page_http_when_ssl_web_is_disabled():
    rendered = _render_link_page(
        hostvars=_link_page_host(splunk_ssl={"web": {"enable": False}}),
    )
    assert "http://10.1.2.3:8000/" in rendered
    assert "https://10.1.2.3:8000/" not in rendered


def test_link_page_no_web_roles_are_plain_text():
    rendered = _render_link_page(
        groups={
            "splunk_env_lab": ["idx1", "uf1"],
            "role_indexer": ["idx1"],
            "role_universal_forwarder": ["uf1"],
        },
        hostvars={
            **_link_page_host("idx1", ansible_host="10.1.2.11"),
            **_link_page_host("uf1", ansible_host="10.1.2.12"),
        },
    )
    assert "data-toggle" not in rendered
    assert "Indexer" in rendered
    assert "Universal Forwarder" in rendered
    assert ":8000/" not in rendered
    assert "/app/itsi/" not in rendered


def test_link_page_combined_roles_keep_web_and_show_cluster_fields():
    rendered = _render_link_page(
        groups={
            "splunk_env_lab": ["shidx"],
            "role_search_head": ["shidx"],
            "role_indexer": ["shidx"],
            "idxcluster_idxc1": ["shidx"],
            "shcluster_shc1": ["shidx"],
        },
        hostvars=_link_page_host(site="site1"),
    )
    assert "Search Head" in rendered
    assert "Indexer" in rendered
    assert "https://10.1.2.3:8000/en-GB/app/launcher/home" in rendered
    assert "No Splunk Web" not in rendered
    assert "site1" in rendered
    assert "idxc1" in rendered
    assert "shc1" in rendered


def test_link_page_manager_roles_keep_deep_links():
    rendered = _render_link_page(
        groups={
            "splunk_env_lab": ["mgr"],
            "role_license_manager": ["mgr"],
            "role_cluster_manager": ["mgr"],
            "role_deployment_server": ["mgr"],
            "role_monitoring_console": ["mgr"],
        },
        hostvars=_link_page_host("mgr"),
    )
    chip = _link_page_visible_chip(rendered, "mgr")
    roles = chip[chip.index('<ul class="roles"'):]
    assert "https://10.1.2.3:8000/en-GB/manager/system/licensing" in roles
    assert "https://10.1.2.3:8000/en-GB/manager/system/clustering" in roles
    assert "https://10.1.2.3:8000/en-GB/manager/system/deploymentserver" in roles
    assert "https://10.1.2.3:8000/en-GB/app/splunk_monitoring_console" in roles
    assert ">License Manager</a>" in roles
    assert ">Cluster Manager</a>" in roles
    assert ">Deployment Server</a>" in roles
    assert ">Monitoring Console</a>" in roles
    article = rendered[rendered.index("<article") : rendered.index("</article>")]
    details = article.split("<details", 1)[1]
    assert "manager/system/licensing" not in details
    assert "manager/system/clustering" not in details
    assert "manager/system/deploymentserver" not in details
    assert "splunk_monitoring_console" not in details
    assert 'class="action' not in rendered
    for tag in _link_page_anchor_tags(rendered):
        if 'target="_blank"' in tag or "target='_blank'" in tag:
            assert 'rel="noopener noreferrer"' in tag


def test_link_page_copy_ssh_control_uses_execcommand():
    rendered = _render_link_page(extra={"spa_registered_name": "pro-lab"})
    assert "spa --env pro-lab hosts ssh shidx" in rendered
    assert 'type="button"' in rendered
    assert ">Copy<" in rendered
    assert "execCommand('copy')" in rendered
    assert "ssh://" not in rendered.lower()
    assert "spa:" not in rendered


def test_link_page_header_shows_registry_name_and_env_directory():
    rendered = _render_link_page(
        extra={
            "spa_registered_name": "pro-lab",
            "spa_env_dir": "/Users/me/itsi500",
            "linkpage_generated_at": "2026-11-13T08:00:00Z",
        },
    )
    header = rendered[rendered.index("<header") : rendered.index("</header>")]
    assert "pro-lab" in header
    assert "/Users/me/itsi500" in header
    assert "itsi500" in header
    assert "Generated" in header
    assert 'data-utc="2026-11-13T08:00:00Z"' in header


def test_link_page_header_shows_version_licenses_provider_and_ccm_ttl():
    guid = "AAAA-BBBB-CCCC-DDDD-EEEE"
    rendered = _render_link_page(
        extra={
            "splunk_defaults": {"splunk_version": "latest"},
            "linkpage_resolved_version": "9.3.2",
            "linkpage_licenses": [
                {
                    "basename": "Splunk_Enterprise.lic",
                    "expires_at": "2027-01-15",
                    "status": "valid",
                    "guid": guid,
                },
                {
                    "basename": "Splunk_ITSI.lic",
                    "expires_at": "2026-11-20",
                    "status": "expiring",
                },
            ],
            "terraform": {"aws": {"region": "eu-central-1"}},
            "linkpage_ccm_ttl": "2026-12-01T00:00:00Z",
            "linkpage_power_state": "running",
            "linkpage_generated_at": "2026-11-13T08:00:00Z",
        },
    )
    header = rendered[rendered.index("<header") : rendered.index("</header>")]
    title = header[header.index("<h1") : header.index('class="meta"')]
    assert "<strong>Generated</strong>" in title
    assert 'data-utc="2026-11-13T08:00:00Z"' in title
    assert "<strong>Expires</strong>" not in title
    assert "data-remaining" not in title
    assert "function remainingDays" in rendered
    assert "function remainingLabel" in rendered
    assert "function licenseStatus" in rendered
    assert "banner" in header
    assert "chip" in header
    assert "9.3.2" in header
    assert "latest" in header
    assert "Provider" in header
    assert "AWS" in header
    assert "eu-central-1" in header
    assert 'class="meta"' in header
    assert "<strong>Splunk_Enterprise.lic</strong>" in header
    assert 'data-utc="2027-01-15"' in header
    assert "<strong>Splunk_ITSI.lic</strong>" in header
    assert 'data-utc="2026-11-20"' in header
    licenses = header[header.index('class="licenses"'):]
    assert licenses.count("data-remaining") == 2
    assert 'data-license-status' not in licenses
    assert "CCM TTL" not in header
    assert 'data-utc="2026-12-01T00:00:00Z"' not in header
    assert guid not in rendered
    assert "Lab suspended" not in header


def test_link_page_ccm_header_expires_is_lab_ttl():
    rendered = _render_link_page(
        extra={
            "ccm": {"ttl_days": 7},
            "linkpage_ccm_ttl": "2026-12-01T00:00:00Z",
            "linkpage_licenses": [
                {
                    "basename": "Splunk_Enterprise.lic",
                    "expires_at": "2026-11-20",
                    "status": "expiring",
                },
            ],
            "linkpage_generated_at": "2026-11-13T08:00:00Z",
        },
    )
    header = rendered[rendered.index("<header") : rendered.index("</header>")]
    title = header[header.index("<h1") : header.index('class="meta"')]
    assert "<strong>Expires</strong>" in title
    assert 'data-utc="2026-12-01T00:00:00Z"' in title
    assert "data-remaining" in title
    assert 'data-utc="2026-11-20"' not in title
    assert 'data-utc="2026-11-20"' in header


def test_link_page_ccm_provider_chip_links_to_the_gui():
    rendered = _render_link_page(extra={"ccm": {"ttl_days": 7}})
    header = rendered[rendered.index("<header") : rendered.index("</header>")]
    assert "CCM" in header
    assert 'href="https://ccm.splunkits.io/cloud-compute"' in header
    assert "AWS" not in header
    for tag in _link_page_anchor_tags(header):
        if "ccm.splunkits.io" in tag:
            assert 'target="_blank"' in tag
            assert 'rel="noopener noreferrer"' in tag
            break
    else:
        raise AssertionError("CCM GUI link missing from header")


def test_link_page_aws_provider_chip_links_to_the_console():
    rendered = _render_link_page(extra={"terraform": {"aws": {"region": "eu-central-1"}}})
    header = rendered[rendered.index("<header") : rendered.index("</header>")]
    assert "AWS" in header
    assert 'href="https://eu-central-1.console.aws.amazon.com/ec2/home?region=eu-central-1"' in header
    assert "ccm.splunkits.io" not in header
    for tag in _link_page_anchor_tags(header):
        if "console.aws.amazon.com" in tag:
            assert 'target="_blank"' in tag
            assert 'rel="noopener noreferrer"' in tag
            break
    else:
        raise AssertionError("AWS console link missing from header")


def test_link_page_omits_license_list_when_extra_absent():
    rendered = _render_link_page()
    header = rendered[rendered.index("<header") : rendered.index("</header>")]
    assert ".lic" not in header


def test_link_page_suspended_grays_hosts_and_keeps_copy_ssh():
    rendered = _render_link_page(
        extra={
            "linkpage_power_state": "suspended",
            "linkpage_suspended_hosts": ["shidx"],
            "spa_registered_name": "pro-lab",
        },
    )
    header = rendered[rendered.index("<header") : rendered.index("</header>")]
    assert "Lab suspended" in header
    tags = [tag for tag in _link_page_tags(rendered, "article") if 'data-host="shidx"' in tag]
    assert tags
    assert "is-suspended" in tags[0]
    assert "Suspended" in rendered
    assert "spa --env pro-lab hosts ssh shidx" in rendered
    for tag in _link_page_anchor_tags(rendered):
        if "app/launcher/home" in tag:
            assert "aria-disabled" in tag


def test_link_page_itsi_button_on_search_heads_only():
    apps = {
        "apps": [
            {"name": "Splunk IT Service Intelligence", "premium_app": "itsi", "state": "present"},
        ],
    }
    rendered = _render_link_page(
        groups={
            "splunk_env_lab": ["itsi", "uf1", "cm"],
            "role_search_head": ["itsi"],
            "role_indexer": ["itsi"],
            "role_license_manager": ["itsi"],
            "role_universal_forwarder": ["uf1"],
            "role_cluster_manager": ["cm"],
        },
        hostvars={
            **_link_page_host("itsi", ansible_host="10.1.2.3"),
            **_link_page_host("uf1", ansible_host="10.1.2.12"),
            **_link_page_host("cm", ansible_host="10.1.2.13"),
        },
        extra={"splunk_app_deployment": apps},
    )
    visible = _link_page_visible_chip(rendered, "itsi")
    roles = visible[visible.index('<ul class="roles"'):]
    assert "/app/itsi/" in roles
    assert ">ITSI</a>" in roles
    assert "https://10.1.2.3:8000/en-GB/app/itsi/" in rendered
    assert "https://10.1.2.3:8000/en-GB/app/launcher/home" in roles
    assert "https://10.1.2.3:8000/en-GB/manager/system/licensing" in roles
    uf_visible = _link_page_visible_chip(rendered, "uf1")
    assert "/app/itsi/" not in uf_visible
    assert "/app/launcher/home" not in uf_visible
    cm_html = rendered[rendered.find('data-host="cm"'): rendered.find('data-host="cm"') + 4000]
    assert cm_html
    assert "https://10.1.2.13:8000/en-GB/app/itsi/" not in rendered


def test_link_page_hides_itsi_when_app_absent():
    rendered = _render_link_page(
        extra={
            "splunk_app_deployment": {
                "apps": [{"name": "Splunk IT Service Intelligence", "premium_app": "itsi", "state": "absent"}],
            },
        },
    )
    assert "/app/itsi/" not in rendered


def test_link_page_site_badge_is_on_the_chip():
    rendered = _render_link_page(
        groups={
            "splunk_env_lab": ["cm", "idx1"],
            "role_cluster_manager": ["cm"],
            "role_indexer": ["idx1"],
            "idxcluster_idxc1": ["cm", "idx1"],
        },
        hostvars={
            **_link_page_host("cm", site="site0", ansible_host="10.1.2.20"),
            **_link_page_host("idx1", site="site1", ansible_host="10.1.2.21"),
        },
    )
    idx_chip = _link_page_visible_chip(rendered, "idx1")
    assert "site0" in _link_page_visible_chip(rendered, "cm")
    assert "site1" in idx_chip
    heading = idx_chip[idx_chip.index("<h2") : idx_chip.index("<ul")]
    assert "<h2>idx1</h2>" in heading
    assert 'class="site-badge"' in heading
    assert "site1" in heading
    roles = idx_chip[idx_chip.index('<ul class="roles"'):]
    assert "site1" not in roles


def test_link_page_boxes_idxc_and_shc_members_by_site():
    rendered = _render_link_page(
        groups={
            "splunk_env_lab": ["cm", "idx1", "idx2", "sh1", "sh2"],
            "role_cluster_manager": ["cm"],
            "role_indexer": ["idx1", "idx2"],
            "role_search_head": ["sh1", "sh2"],
            "idxcluster_idxc1": ["cm", "idx1", "idx2"],
            "shcluster_shc1": ["sh1", "sh2"],
        },
        hostvars={
            **_link_page_host("cm", site="site0", ansible_host="10.1.2.20"),
            **_link_page_host("idx1", site="site1", ansible_host="10.1.2.21"),
            **_link_page_host("idx2", site="site2", ansible_host="10.1.2.22"),
            **_link_page_host("sh1", site="site1", ansible_host="10.1.2.23"),
            **_link_page_host("sh2", site="site1", ansible_host="10.1.2.24"),
        },
    )
    shc_at = rendered.index('id="shc-shc1"')
    idxc_at = rendered.index('id="idxc-idxc1"')
    assert shc_at < idxc_at
    shc = rendered[shc_at:idxc_at]
    idxc = rendered[idxc_at:]
    assert idxc.count('class="site-group"') == 2
    assert "<h4>site1</h4>" in idxc
    assert "<h4>site2</h4>" in idxc
    assert 'class="site-group"' in shc
    assert "<h4>site1</h4>" in shc
    assert 'data-host="sh1"' in shc
    assert 'data-host="sh2"' in shc


def test_link_page_cluster_manager_and_deployer_are_badges():
    rendered = _render_link_page(
        groups={
            "splunk_env_lab": ["cm", "idx1", "ds", "sh1"],
            "role_cluster_manager": ["cm"],
            "role_indexer": ["idx1"],
            "role_deployer": ["ds"],
            "role_search_head": ["sh1"],
            "idxcluster_idxc1": ["cm", "idx1"],
            "shcluster_shc1": ["ds", "sh1"],
        },
        hostvars={
            **_link_page_host("cm", ansible_host="10.1.2.20"),
            **_link_page_host("idx1", ansible_host="10.1.2.21"),
            **_link_page_host("ds", ansible_host="10.1.2.22"),
            **_link_page_host("sh1", ansible_host="10.1.2.23"),
        },
    )
    shc_at = rendered.index('id="shc-shc1"')
    idxc_at = rendered.index('id="idxc-idxc1"')
    shc = rendered[shc_at:idxc_at]
    idxc = rendered[idxc_at:]
    assert "<h3>shc1</h3>" in shc
    assert 'class="cluster-badge"' in shc
    assert "Deployer: ds" in shc
    assert "· Deployer:" not in shc
    assert "<h3>idxc1</h3>" in idxc
    assert 'class="cluster-badge"' in idxc
    assert "Cluster Manager: cm" in idxc
    assert "· Cluster Manager:" not in idxc


def test_link_page_stacks_management_in_a_left_column():
    rendered = _render_link_page(
        groups={
            "splunk_env_lab": ["cm", "sh", "idx1", "uf1"],
            "role_cluster_manager": ["cm"],
            "role_search_head": ["sh"],
            "role_indexer": ["idx1"],
            "role_universal_forwarder": ["uf1"],
            "idxcluster_idxc1": ["cm", "idx1"],
        },
        hostvars={
            **_link_page_host("cm", ansible_host="10.1.2.20"),
            **_link_page_host("sh", ansible_host="10.1.2.21"),
            **_link_page_host("idx1", ansible_host="10.1.2.22"),
            **_link_page_host("uf1", ansible_host="10.1.2.23"),
        },
    )
    mgmt = rendered.find('class="mgmt-column"')
    work = rendered.find('class="workload-column"')
    assert 0 <= mgmt < work
    left = rendered[mgmt:work]
    right = rendered[work:]
    assert 'data-tier="management"' in left
    assert 'data-host="cm"' in left
    assert 'data-tier="search"' not in left
    assert 'data-tier="search"' in right
    assert 'data-tier="index"' in right
    assert 'data-tier="forwarders"' in right
    assert 'data-host="sh"' in right
    assert 'data-host="idx1"' in right
    assert 'data-host="uf1"' in right
    assert "ar.right" in rendered
    assert ".mgmt-column .tier-hosts" in rendered
    assert "align-items: stretch" in rendered
    assert ".mgmt-column article.host" in rendered
    assert "width: 100%" in rendered
    assert ".mgmt-column article.host:has(details[open])" in rendered
    assert "min-width: 22rem" in rendered
    assert 'addEventListener("toggle"' in rendered


def test_link_page_omits_mgmt_column_without_management_hosts():
    rendered = _render_link_page()
    assert 'class="mgmt-column"' not in rendered
    assert 'class="workload-column"' in rendered
    assert 'data-tier="search"' in rendered


def test_link_page_combined_search_indexer_sits_in_search_tier():
    rendered = _render_link_page(
        groups={
            "splunk_env_lab": ["itsi"],
            "role_search_head": ["itsi"],
            "role_indexer": ["itsi"],
            "role_license_manager": ["itsi"],
        },
        hostvars=_link_page_host("itsi"),
    )
    search_start = rendered.find('data-tier="search"')
    assert search_start != -1
    next_tier = rendered.find('data-tier="', search_start + 1)
    chunk = rendered[search_start: next_tier if next_tier != -1 else None]
    assert 'data-host="itsi"' in chunk
    assert 'data-tier="index"' not in rendered
    assert 'data-host="itsi"' in rendered
    hosts = _link_page_host_tags(rendered)
    assert [row["host"] for row in hosts] == ["itsi"]


def test_link_page_forwarder_layer_puts_hf_and_uf_boxes_side_by_side():
    rendered = _render_link_page(
        groups={
            "splunk_env_lab": ["cm", "sh", "idx1", "hf", "uf1", "uf2"],
            "role_cluster_manager": ["cm"],
            "role_search_head": ["sh"],
            "role_indexer": ["idx1"],
            "role_heavy_forwarder": ["hf"],
            "role_universal_forwarder": ["uf1", "uf2"],
            "idxcluster_idxc1": ["cm", "idx1"],
        },
        hostvars={
            **_link_page_host("cm", ansible_host="10.1.2.20"),
            **_link_page_host("sh", ansible_host="10.1.2.21"),
            **_link_page_host("idx1", ansible_host="10.1.2.22"),
            **_link_page_host("hf", ansible_host="10.1.2.30"),
            **_link_page_host("uf1", ansible_host="10.1.2.31"),
            **_link_page_host("uf2", ansible_host="10.1.2.32"),
        },
    )
    work = rendered.find('class="workload-column"')
    fwd = rendered.find('data-tier="forwarders"')
    idx = rendered.find('data-tier="index"')
    assert 0 <= work < idx < fwd
    workload = rendered[work:fwd]
    layer = rendered[fwd:]
    assert 'data-tier="search"' in workload
    assert 'data-tier="index"' in workload
    assert 'data-host="hf"' not in workload
    assert 'data-host="uf1"' not in workload
    assert 'data-tier="heavy"' not in rendered
    assert 'data-tier="universal"' not in rendered
    assert 'class="tier forwarder-layer"' in rendered
    hf_box = layer.find('class="cluster hf-box"')
    uf_box = layer.find('class="cluster uf-box"')
    assert 0 <= hf_box < uf_box
    assert "Heavy Forwarder" in layer[hf_box:uf_box]
    assert "Universal Forwarders" in layer[uf_box:]
    assert 'data-host="hf"' in layer[hf_box:uf_box]
    assert 'data-host="uf1"' in layer[uf_box:]
    assert 'data-cluster="hf-lab"' in "".join(
        row["tag"] for row in _link_page_host_tags(rendered) if row["host"] == "hf"
    )
    assert 'data-cluster="uf-lab"' in "".join(
        row["tag"] for row in _link_page_host_tags(rendered) if row["host"].startswith("uf")
    )
    assert ".forwarder-layer .cluster" in rendered


def test_link_page_groups_two_ufs_and_keeps_hf_separate():
    rendered = _render_link_page(
        groups={
            "splunk_env_lab": ["hf", "uf1", "uf2"],
            "role_heavy_forwarder": ["hf"],
            "role_universal_forwarder": ["uf1", "uf2"],
        },
        hostvars={
            **_link_page_host("hf", ansible_host="10.1.2.30"),
            **_link_page_host("uf1", ansible_host="10.1.2.31"),
            **_link_page_host("uf2", ansible_host="10.1.2.32"),
        },
    )
    assert "Universal Forwarders" in rendered
    assert 'data-tier="forwarders"' in rendered
    assert 'data-host="hf"' in rendered
    assert 'data-node="uf-lab"' in rendered
    assert 'class="cluster hf-box"' in rendered
    assert 'data-cluster="uf-lab"' in "".join(row["tag"] for row in _link_page_host_tags(rendered) if row["host"].startswith("uf"))
    assert not any(row["host"] == "hf" and row.get("cluster") == "uf-lab" for row in _link_page_host_tags(rendered))


def test_link_page_ds_draws_edges_to_forwarder_boxes():
    rendered = _render_link_page(
        groups={
            "splunk_env_lab": ["ds", "hf", "uf1", "uf2"],
            "role_deployment_server": ["ds"],
            "role_heavy_forwarder": ["hf"],
            "role_universal_forwarder": ["uf1", "uf2"],
        },
        hostvars={
            **_link_page_host("ds", ansible_host="10.1.2.10"),
            **_link_page_host("hf", ansible_host="10.1.2.30"),
            **_link_page_host("uf1", ansible_host="10.1.2.31"),
            **_link_page_host("uf2", ansible_host="10.1.2.32"),
        },
    )
    edges = {(edge["from"], edge["to"], edge["label"]) for edge in _link_page_edges(rendered)}
    assert ("host-ds", "hf-lab", "phone-home") in edges
    assert ("host-ds", "uf-lab", "phone-home") in edges
    assert ("host-uf1", "host-ds", "phone-home") not in edges
    assert ("uf-lab", "host-ds", "phone-home") not in edges


def test_link_page_collapses_many_universal_forwarders():
    ufs = ["uf%s" % index for index in range(1, 9)]
    rendered = _render_link_page(
        groups={
            "splunk_env_lab": ufs,
            "role_universal_forwarder": ufs,
        },
        hostvars={
            hostname: _link_page_host(hostname, ansible_host="10.1.2.%s" % (40 + index))[hostname]
            for index, hostname in enumerate(ufs, start=1)
        },
    )
    assert "8 universal forwarders" in rendered.lower() or "8 Universal Forwarders" in rendered
    assert "Universal Forwarders" in rendered
    hosts = [row["host"] for row in _link_page_host_tags(rendered)]
    assert hosts == ufs
    assert rendered.lower().count("<article") < 8


def test_link_page_windows_uf_shares_the_box():
    rendered = _render_link_page(
        groups={
            "splunk_env_lab": ["uf1", "wuf1"],
            "role_universal_forwarder": ["uf1"],
            "role_universal_forwarder_windows": ["wuf1"],
        },
        hostvars={
            **_link_page_host("uf1", ansible_host="10.1.2.41"),
            **_link_page_host("wuf1", ansible_host="10.1.2.42"),
        },
    )
    assert "Universal Forwarders" in rendered
    assert "Windows" in rendered
    hosts = [row["host"] for row in _link_page_host_tags(rendered)]
    assert hosts == ["uf1", "wuf1"]


@pytest.mark.parametrize("topology", _topology_files(), ids=lambda path: path.name)
def test_link_page_renders_each_topology(topology):
    config = yaml.safe_load(topology.read_text(encoding="utf-8"))
    groups, hostvars, extra = _inventory_from_topology(config)
    extra.update({
        "spa_registered_name": "lab-%s" % topology.stem,
        "spa_env_dir": "/tmp/spa-envs/%s" % topology.stem,
        "linkpage_generated_at": "2026-11-13T09:00:00Z",
    })
    rendered = _render_link_page(groups=groups, hostvars=hostvars, extra=extra)
    lower = rendered.lower()
    assert "jsdelivr" not in lower
    assert "cdn.jsdelivr.net" not in lower
    assert "{{ lookup('env'" not in rendered
    assert "SPLUNK_ADMIN_PASSWORD" not in rendered
    assert "privkey" not in lower
    assert "/.ssh/" not in rendered

    env_names = []
    hostnames = []
    for group_name, members in groups.items():
        if group_name.startswith("splunk_env_"):
            env_names.append(group_name[len("splunk_env_"):])
            hostnames.extend(members)
    tagged = _link_page_host_tags(rendered)
    found = [row["host"] for row in tagged]
    assert sorted(found) == sorted(hostnames)
    assert len(found) == len(set(hostnames))

    header = rendered[rendered.index("<header") : rendered.index("</header>")]
    assert "lab-%s" % topology.stem in header
    assert "/tmp/spa-envs/%s" % topology.stem in header
    assert "Generated" in header
    assert 'data-utc="2026-11-13T09:00:00Z"' in header
    assert "function formatLocal" in rendered

    edges = {(edge["from"], edge["to"], edge["label"]) for edge in _link_page_edges(rendered)}
    indexer_roles = set(groups.get("role_indexer") or [])
    search_roles = set(groups.get("role_search_head") or [])
    cms = groups.get("role_cluster_manager") or []
    deployers = groups.get("role_deployer") or []
    for cluster_name, members in groups.items():
        if cluster_name.startswith("idxcluster_") and "_site" not in cluster_name.split("idxcluster_", 1)[1]:
            short = cluster_name[len("idxcluster_"):]
            box_hosts = [row["host"] for row in tagged if row.get("cluster") == "idxc-%s" % short]
            assert set(box_hosts) == (set(members) & indexer_roles)
            for manager in cms:
                if manager in members:
                    assert ("host-%s" % manager, "idxc-%s" % short, "manages") in edges
        if cluster_name.startswith("shcluster_") and "_site" not in cluster_name.split("shcluster_", 1)[1]:
            short = cluster_name[len("shcluster_"):]
            box_hosts = [row["host"] for row in tagged if row.get("cluster") == "shc-%s" % short]
            assert set(box_hosts) == (set(members) & search_roles)
            for deployer in deployers:
                if deployer in members:
                    assert ("host-%s" % deployer, "shc-%s" % short, "bundle") in edges

    for env_name in env_names:
        env_hosts = set(groups.get("splunk_env_%s" % env_name) or [])
        ufs = [
            host for host in (groups.get("role_universal_forwarder") or [])
            + (groups.get("role_universal_forwarder_windows") or [])
            if host in env_hosts
        ]
        dses = [host for host in (groups.get("role_deployment_server") or []) if host in env_hosts]
        hfs = [host for host in (groups.get("role_heavy_forwarder") or []) if host in env_hosts]
        if ufs and dses:
            assert ("host-%s" % dses[0], "uf-%s" % env_name, "phone-home") in edges
        elif ufs:
            assert not any(edge[2] == "phone-home" and edge[1] == "uf-%s" % env_name for edge in edges)
        if hfs and dses:
            assert ("host-%s" % dses[0], "hf-%s" % env_name, "phone-home") in edges

    name = topology.name
    if len(env_names) >= 2:
        assert 'class="stack-tabs"' in rendered
        for env_name in env_names:
            assert env_name in rendered
        assert ("host-uf1", "host-ds2", "phone-home") not in edges
        assert ("host-cm1", "idxc-idxc2", "manages") not in edges
    else:
        assert 'class="stack-tabs"' not in rendered

    if name == "ds_cm_2idxc1site_sh_hf_uf.yml":
        assert 'data-tier="forwarders"' in rendered
        assert 'data-host="hf"' in rendered
        assert any(row["host"] == "hf" and row.get("cluster") == "hf-splk" for row in tagged)
        assert ("host-ds", "uf-splk", "phone-home") in edges
        assert ("host-ds", "hf-splk", "phone-home") in edges
    if name == "cm1_2idxc1site_cm2_2idxc1site_ds_3shc_smc_uf.yml":
        assert 'data-node="idxc-idxc1"' in rendered
        assert 'data-node="idxc-idxc2"' in rendered
        assert 'data-host="smc"' in rendered
    if name in ("cm_2idxc_2x3shc_ds.yml", "cm_4idxc2site_4x3shc_ds.yml"):
        for cluster in ("shc1", "shc_es") if "2x3" in name and "4x3" not in name and "stretched" not in name else ():
            assert 'data-node="shc-%s"' % cluster in rendered
        if name == "cm_2idxc_2x3shc_ds.yml":
            assert 'data-node="shc-shc1"' in rendered
            assert 'data-node="shc-shc_es"' in rendered
        if name == "cm_4idxc2site_4x3shc_ds.yml":
            for cluster in ("shc1", "shc2", "shc_es1", "shc_es2"):
                assert 'data-node="shc-%s"' % cluster in rendered
    if "2site" in name or name.startswith("4idxc"):
        for hostname, values in hostvars.items():
            site = values.get("site")
            if site:
                assert site in _link_page_visible_chip(rendered, hostname)
    if "stretched" in name:
        assert rendered.count('data-node="shc-shc1"') == 1
    if topology.name == "single_node_itsi.yml":
        assert "/app/itsi/" in _link_page_visible_chip(rendered, "itsi")
        assert "/app/SplunkEnterpriseSecuritySuite/" not in rendered
    if name.endswith("_es.yml") or "es" in name and "itsi" not in name:
        assert "/app/SplunkEnterpriseSecuritySuite/" not in rendered
        assert ">ES<" not in rendered


def test_register_writes_inventory_and_agent_json_hides_the_key_body(tmp_path):
    from spa_testutil import run_spa

    key = tmp_path / "id_ed25519"
    marker = "key-body-not-for-output\n"
    key.write_text(marker)
    dest = _external_env(tmp_path)
    result = run_spa(
        [
            "--agent", "hosts", "register", "byo1",
            "--ssh-host", "10.0.0.8", "--user", "splunk",
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
            "--ssh-host", "10.0.0.8", "--user", "splunk",
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
            "--ssh-host", "10.0.0.8", "--user", "splunk",
            "--key", str(key), "--yes",
        ],
        env=_cli_env(dest, _fake_ssh(tmp_path / "okssh", code=0)),
    )
    assert ok.returncode == 0, ok.stderr
    assert ok.stdout.strip() == "registered byo1 ansible_host=10.0.0.8 user=splunk key=set"


def test_register_leaves_config_when_the_inventory_write_fails(tmp_path, monkeypatch):
    from spa.providers.external import RegisterSpec, register_host

    key = tmp_path / "id_ed25519"
    key.write_text("not-read")
    paths = _paths(tmp_path, "external: {}\nsplunk_hosts: []\n")
    paths.inventory_dir.mkdir(parents=True, exist_ok=True)
    inventory = paths.inventory_dir / "hosts"
    inventory.write_text("# keep\n")
    config_before = paths.config_file.read_bytes()
    inventory_before = inventory.read_bytes()

    def boom(*_args, **_kwargs):
        raise OSError("disk full")

    monkeypatch.setattr("spa.providers.external.upsert_inventory", boom)
    with pytest.raises(OSError, match="disk full"):
        register_host(
            paths,
            RegisterSpec("byo1", "10.0.0.8", "splunk", str(key), 22, ("search_head",)),
            lambda _argv: 0,
        )
    assert paths.config_file.read_bytes() == config_before
    assert inventory.read_bytes() == inventory_before


def test_register_leaves_inventory_when_the_config_write_fails(tmp_path, monkeypatch):
    from spa.providers.external import RegisterSpec, register_host

    key = tmp_path / "id_ed25519"
    key.write_text("not-read")
    paths = _paths(tmp_path, "external: {}\nsplunk_hosts: []\n")
    paths.inventory_dir.mkdir(parents=True, exist_ok=True)
    inventory = paths.inventory_dir / "hosts"
    inventory.write_text("# keep\n")
    config_before = paths.config_file.read_bytes()
    inventory_before = inventory.read_bytes()

    def boom(*_args, **_kwargs):
        raise OSError("config disk full")

    monkeypatch.setattr("spa.providers.external._dump_document", boom)
    with pytest.raises(OSError, match="config disk full"):
        register_host(
            paths,
            RegisterSpec("byo1", "10.0.0.8", "splunk", str(key), 22, ()),
            lambda _argv: 0,
        )
    assert paths.config_file.read_bytes() == config_before
    assert inventory.read_bytes() == inventory_before


def test_register_drops_the_shared_interpreter_cache_for_that_hostname(tmp_path, monkeypatch):
    from spa.providers.external import RegisterSpec, register_host

    key = tmp_path / "id_ed25519"
    key.write_text("not-read")
    paths = _paths(tmp_path, "external: {}\nsplunk_hosts: []\n")
    cache = tmp_path / "facts"
    cache.mkdir()
    stale = {
        "__payload__": json.dumps(
            {"discovered_interpreter_python": "/usr/bin/python3.12"}
        )
    }
    (cache / "s1_byo1").write_text(json.dumps(stale), encoding="utf-8")
    (cache / "s1_other").write_text(json.dumps(stale), encoding="utf-8")
    monkeypatch.setenv("ANSIBLE_CACHE_PLUGIN_CONNECTION", str(cache))
    register_host(
        paths,
        RegisterSpec("byo1", "10.0.0.8", "splunk", str(key), 22, ()),
        lambda _argv: 0,
    )
    assert not (cache / "s1_byo1").exists()
    assert (cache / "s1_other").exists()


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
            "--ssh-host", "10.0.0.8", "--user", "splunk",
            "--key", str(key), "--yes",
        ],
        env=_cli_env(dest, _fake_ssh(tmp_path)),
    )
    assert result.returncode == 1
    assert "shidx is managed by aws. SPA does not take over a managed host." in result.stderr
    added = run_spa(
        [
            "--no-agent", "hosts", "register", "byo1",
            "--ssh-host", "10.0.0.8", "--user", "splunk",
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
            "--ssh-host", "10.0.0.9", "--user", "splunk",
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
        "schema_version: 1\n"
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
        "schema_version: 1\n"
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
        "schema_version: 1\n"
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
    _touch_linux_archive(software, "arm64")
    _touch_linux_archive(software, "amd64")
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
        "schema_version: 1\n"
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
    _touch_linux_archive(software, "arm64")
    _touch_linux_archive(software, "amd64")
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


def test_wait_for_ssh_retries_connection_refused_then_succeeds(tmp_path, monkeypatch):
    from spa.hosts import HostsError, wait_for_ssh

    paths = _paths(tmp_path, "external: {}\nsplunk_hosts:\n  - name: idx1\n")
    calls = {"n": 0}
    sleeps = []

    def fake_ping(_paths, hosts=None, run=None):
        del hosts, run
        calls["n"] += 1
        if calls["n"] < 3:
            raise HostsError(
                "SSH failed for idx1. Failed to connect to the host via ssh: "
                "tcp connect to 10.0.0.8:22: Connection refused"
            )
        return {"hosts": [{"name": "idx1", "ok": True, "ssh": True, "become": True}]}

    monkeypatch.setattr("spa.hosts.ping_hosts", fake_ping)
    result = wait_for_ssh(paths, ["idx1"], sleep=sleeps.append, attempts=5, delay=1)
    assert calls["n"] == 3
    assert sleeps == [1, 1]
    assert result["hosts"][0]["ok"] is True


@pytest.mark.parametrize(
    "message",
    [
        "Connection timed out during banner exchange",
        "Permission denied (publickey).",
        "ssh: connect to host 10.0.0.8 port 22: Operation timed out",
    ],
)
def test_wait_for_ssh_retries_any_unreachable_host(tmp_path, monkeypatch, message):
    from spa.hosts import wait_for_ssh

    paths = _paths(tmp_path, "external: {}\nsplunk_hosts:\n  - name: idx1\n")
    calls = {"n": 0}
    sleeps = []

    def fake_ansible_ping(names, paths=None, become=False, run=None):
        calls["n"] += 1
        if calls["n"] < 3:
            return [
                {"name": "idx1", "ok": False, "ssh": False, "become": False, "message": message}
            ], None
        return [{"name": "idx1", "ok": True, "ssh": True, "become": True, "message": ""}], None

    monkeypatch.setattr("spa.shell.ansible_ping", fake_ansible_ping)
    monkeypatch.setattr(
        "spa.shell.ansible_architecture", lambda names, paths=None, run=None: ({"idx1": "x86_64"}, None)
    )
    monkeypatch.setattr("spa.shell.drop_discovered_interpreter_cache", lambda *a, **k: None)
    monkeypatch.setattr(
        "spa.providers.inventory_hostnames_from_file", lambda _paths: ["idx1"]
    )
    result = wait_for_ssh(paths, ["idx1"], sleep=sleeps.append, attempts=5, delay=1)
    assert calls["n"] == 3
    assert sleeps == [1, 1]
    assert result["hosts"][0]["ok"] is True


def test_wait_for_ssh_fails_immediately_when_sudo_fails(tmp_path, monkeypatch):
    from spa.hosts import HostsError, wait_for_ssh

    paths = _paths(tmp_path, "external: {}\nsplunk_hosts:\n  - name: idx1\n")
    calls = {"n": 0}

    def fake_ansible_ping(names, paths=None, become=False, run=None):
        calls["n"] += 1
        return [
            {"name": "idx1", "ok": False, "ssh": True, "become": False, "message": "sudo: a password is required"}
        ], None

    monkeypatch.setattr("spa.shell.ansible_ping", fake_ansible_ping)
    monkeypatch.setattr("spa.shell.drop_discovered_interpreter_cache", lambda *a, **k: None)
    monkeypatch.setattr(
        "spa.providers.inventory_hostnames_from_file", lambda _paths: ["idx1"]
    )
    with pytest.raises(HostsError, match="passwordless sudo"):
        wait_for_ssh(paths, ["idx1"], sleep=lambda _delay: None, attempts=5)
    assert calls["n"] == 1


def test_wait_for_ssh_fails_immediately_on_architecture_mismatch(tmp_path, monkeypatch):
    from spa.hosts import HostsError, wait_for_ssh

    paths = _paths(tmp_path, "external: {}\nsplunk_hosts:\n  - name: idx1\n")
    calls = {"n": 0}

    def fake_ping(_paths, hosts=None, run=None):
        del hosts, run
        calls["n"] += 1
        raise HostsError(
            "idx1 architecture mismatch: config arm64, host x86_64",
            rows=[
                {
                    "name": "idx1",
                    "ok": False,
                    "expected_architecture": "arm64",
                    "architecture": "x86_64",
                }
            ],
        )

    monkeypatch.setattr("spa.hosts.ping_hosts", fake_ping)
    with pytest.raises(HostsError, match="architecture mismatch"):
        wait_for_ssh(paths, ["idx1"], sleep=lambda _delay: None, attempts=5)
    assert calls["n"] == 1


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


def test_hosts_check_uses_the_environment_architecture(tmp_path):
    from spa.hosts import ping_hosts

    paths = _paths(
        tmp_path,
        "external: {}\n"
        "splunk_defaults:\n"
        "  splunk_env_name: splk\n"
        "  splunk_architecture: amd64\n"
        "splunk_environments:\n"
        "  - splunk_env_name: lab\n"
        "    splunk_architecture: arm64\n"
        "splunk_hosts:\n"
        "  - name: byo1\n"
        "    splunk_env: lab\n"
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
                handle.write('{"ansible_facts": {"ansible_architecture": "aarch64"}}')
        return 0

    data = ping_hosts(paths, ["byo1"], run)
    assert data["hosts"][0]["ok"] is True
    assert data["hosts"][0]["expected_architecture"] == "arm64"


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


def test_become_ping_does_not_blame_sudo_for_a_missing_interpreter(tmp_path, capsys):
    from spa.hosts import HostsError, ping_hosts

    def run(argv, tree):
        with open(os.path.join(tree, "byo1"), "w", encoding="utf-8") as handle:
            handle.write(
                '{"rc": 127, "msg": "The module interpreter \'/usr/bin/python3.12\' was not found."}'
            )
        return 2

    with pytest.raises(HostsError, match="module interpreter '/usr/bin/python3.12' was not found") as exc:
        ping_hosts(_ping_paths(tmp_path), ["byo1"], run)
    assert "passwordless sudo" not in str(exc.value)
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""


def test_ping_drops_stale_discovered_interpreter_before_ansible(tmp_path, monkeypatch):
    from spa.hosts import ping_hosts

    cache = tmp_path / "facts"
    cache.mkdir()
    (cache / "s1_byo1").write_text(
        json.dumps(
            {
                "__payload__": json.dumps(
                    {
                        "discovered_interpreter_python": "/usr/bin/python3.12",
                        "ansible_architecture": "x86_64",
                    }
                )
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("ANSIBLE_CACHE_PLUGIN_CONNECTION", str(cache))
    seen = {}

    def run(argv, tree):
        seen["module"] = argv[argv.index("-m") + 1]
        seen["cache_left"] = (cache / "s1_byo1").exists()
        with open(os.path.join(tree, "byo1"), "w", encoding="utf-8") as handle:
            if seen["module"] == "ping":
                handle.write('{"ping": "pong"}')
            else:
                handle.write('{"ansible_facts": {"ansible_architecture": "x86_64"}}')
        return 0

    data = ping_hosts(_ping_paths(tmp_path), ["byo1"], run)
    assert seen["cache_left"] is False
    assert data["hosts"][0]["ok"] is True


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


def test_in_repo_destroy_leaves_framework_terraform_files(tmp_path, monkeypatch):
    from dataclasses import replace

    def fake_destroy(self, extra, **kwargs):
        hosts = self.paths.inventory_dir / "hosts"
        if hosts.exists():
            hosts.unlink()
        return 0

    monkeypatch.setattr("spa.providers.aws.Provider.destroy", fake_destroy)
    paths = _paths(
        tmp_path,
        "terraform:\n"
        "  aws:\n"
        "    region: eu-central-1\n"
        "splunk_hosts:\n"
        "  - name: idx1\n"
        "    roles: [indexer]\n",
    )
    shared = tmp_path / "framework" / "terraform" / "aws"
    shared.mkdir(parents=True)
    (shared / "main.tf").write_text("# tracked\n", encoding="utf-8")
    (shared / "terraform.tfstate").write_text("{}\n", encoding="utf-8")
    (shared / "terraform.tfvars").write_text('region = "eu-central-1"\n', encoding="utf-8")
    paths = replace(paths, terraform_state_dir=shared, terraform_modules_dir=shared)
    _write_named_inventory(paths, {"idx1": 'ansible_host="10.0.0.1"'})
    result = _ready_session(paths, monkeypatch).destroy(confirm=True)
    assert result.ok, result.error
    assert (shared / "main.tf").read_text(encoding="utf-8") == "# tracked\n"
    assert (shared / "terraform.tfstate").is_file()
    assert (shared / "terraform.tfvars").is_file()


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
    assert seen["label"] == "hosts provision"
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


def test_register_role_choices_match_allowed_role():
    import sys

    from spa.hosts import allowed_role_names
    from spa_testutil import PROJECT_ROOT, run_spa, run_spa_inprocess

    plugin = str(PROJECT_ROOT / "ansible" / "plugins" / "inventory")
    if plugin not in sys.path:
        sys.path.insert(0, plugin)
    from schema import AllowedRole

    names = allowed_role_names()
    assert names == [role.value for role in AllowedRole]
    help_result = run_spa_inprocess(["hosts", "register", "--help"])
    assert help_result.returncode == 0, help_result.stderr
    for name in names:
        assert name in help_result.stdout
    schema = json.loads(run_spa(["agent", "schema"]).stdout)
    register = next(row for row in schema["data"]["commands"] if row["name"] == "hosts register")
    role = next(flag for flag in register["flags"] if flag["long"] == "--role")
    assert role["choices"] == names


def test_user_guide_registers_existing_servers():
    from spa_testutil import PROJECT_ROOT

    text = (PROJECT_ROOT / "docs" / "user-guide.md").read_text(encoding="utf-8")
    assert "spa hosts register NAME --ssh-host HOST --user USER --key PATH --yes" in text
    assert "does not create, shut down, or terminate" in text
    assert "spa hosts check" in text
    assert "before the playbook" in text
    assert "splunk_environments" in text
    assert "--allow-unprovisioned" not in text



