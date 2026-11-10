"""CCM HTTP client tests (mocked HTTP; no live CCM)."""

from __future__ import annotations

import json
import sys
from dataclasses import replace
from typing import List

import pytest

from spa.paths import resolve_spa_paths
from spa_testutil import LIB, PROJECT_ROOT

pytestmark = [pytest.mark.local, pytest.mark.cli]

sys.path.insert(0, str(LIB))


def _ccm_paths(tmp_path, config: str):
    config_path = tmp_path / "config" / "splunk_config.yml"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(config, encoding="utf-8")
    (tmp_path / "inventory").mkdir(exist_ok=True)
    base = resolve_spa_paths(start_dir=PROJECT_ROOT)
    return replace(
        base,
        spa_env_dir=tmp_path,
        config_file=config_path,
        inventory_dir=tmp_path / "inventory",
        roots_differ=True,
    )


_CCM_MIN = """\
ccm:
  instance_type: t3a.medium
  disk_storage: 50
  operating_system: rhel_9
  key_name: CCM-Key
  ssh_private_key_file: /tmp/ccm-test-key
  ssh_username: ec2-user
"""


class _FakeResponse:
    def __init__(self, status: int, body: bytes) -> None:
        self.status = status
        self._body = body

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, *args: object) -> None:
        return None


class FakeOpener:
    def __init__(self, status: int = 200, body: bytes = b"[]") -> None:
        self.status = status
        self.body = body
        self.requests: List[object] = []

    def open(self, req: object, timeout: object = None) -> _FakeResponse:
        self.requests.append(req)
        return _FakeResponse(self.status, self.body)


class ScriptedOpener:
    def __init__(self, responses: List[object]) -> None:
        self._responses = list(responses)
        self.requests: List[object] = []

    def open(self, req: object, timeout: object = None) -> _FakeResponse:
        self.requests.append(req)
        if not self._responses:
            raise AssertionError("unexpected %s %s" % (req.get_method(), req.full_url))
        status, body = self._responses.pop(0)
        if isinstance(body, (dict, list)):
            raw = json.dumps(body).encode("utf-8")
        elif isinstance(body, str):
            raw = body.encode("utf-8")
        else:
            raw = body
        return _FakeResponse(status, raw)


def test_ccm_client_requires_token_and_reports_not_set(monkeypatch):
    monkeypatch.delenv("CCM_TOKEN", raising=False)
    from spa.providers.ccm import CcmError, UrllibCcmClient

    with pytest.raises(CcmError, match=r"CCM_TOKEN: not set") as caught:
        UrllibCcmClient.from_env()
    assert "secret" not in str(caught.value).lower()
    monkeypatch.setenv("CCM_TOKEN", "   ")
    with pytest.raises(CcmError, match=r"CCM_TOKEN: not set"):
        UrllibCcmClient.from_env()


def test_ccm_client_get_uses_https_and_bearer_token():
    from spa.providers.ccm import API_ROOT, UrllibCcmClient

    opener = FakeOpener(status=200, body=b"[]")
    client = UrllibCcmClient(token="test-ccm-token", opener=opener)
    status, payload = client.request("GET", "/api/v1/deployments")
    assert status == 200
    assert payload == []
    assert len(opener.requests) == 1
    req = opener.requests[0]
    assert req.full_url == API_ROOT + "/api/v1/deployments"
    assert req.full_url.startswith("https://")
    assert req.get_header("Authorization") == "Bearer test-ccm-token"


def test_ccm_client_rejects_http_urls():
    from spa.providers.ccm import CcmError, UrllibCcmClient

    client = UrllibCcmClient(token="test-ccm-token", opener=FakeOpener())
    with pytest.raises(CcmError, match="HTTPS"):
        client.request("GET", "http://api.ccm.splunkits.io/api/v1/deployments")
    with pytest.raises(CcmError, match="HTTPS"):
        UrllibCcmClient(token="test-ccm-token", base_url="http://api.ccm.splunkits.io")


def test_ccm_client_url_error_does_not_echo_token():
    import urllib.error

    from spa.providers.ccm import CcmError, UrllibCcmClient

    token = "test-ccm-pat-value"

    class BoomOpener:
        def open(self, req: object, timeout: object = None) -> None:
            raise urllib.error.URLError("failed with %s" % token)

    client = UrllibCcmClient(token=token, opener=BoomOpener())
    with pytest.raises(CcmError, match="CCM API request failed") as caught:
        client.request("GET", "/api/v1/deployments")
    assert token not in str(caught.value)
    assert token not in repr(caught.value)


def test_ccm_ping_reports_http_status_without_body_or_token():
    from spa.providers.ccm import CcmError, UrllibCcmClient, ping

    token = "test-ccm-pat-value"
    opener = FakeOpener(status=401, body=b'{"detail":"rejected test-ccm-pat-value"}')
    client = UrllibCcmClient(token=token, opener=opener)
    with pytest.raises(CcmError, match=r"CCM API returned HTTP 401") as caught:
        ping(client=client)
    assert token not in str(caught.value)
    assert "rejected" not in str(caught.value)


def test_ccm_ping_succeeds_on_deployments_list():
    from spa.providers.ccm import UrllibCcmClient, ping

    opener = FakeOpener(status=200, body=b"[]")
    ping(client=UrllibCcmClient(token="test-ccm-token", opener=opener))
    assert opener.requests[0].full_url.endswith("/api/v1/deployments")


def test_ccm_client_post_json_uses_https_query_and_bearer():
    from spa.providers.ccm import API_ROOT, UrllibCcmClient

    opener = FakeOpener(status=200, body=b'{"data":{"deployment_id":"dep-1"}}')
    client = UrllibCcmClient(token="test-ccm-token", opener=opener)
    status, payload = client.request(
        "POST",
        "/api/v1/deployments",
        query={"type": "ec2"},
        body={"name": "my-lab", "disk_storage": 50},
    )
    assert status == 200
    assert payload["data"]["deployment_id"] == "dep-1"
    req = opener.requests[0]
    assert req.full_url == API_ROOT + "/api/v1/deployments?type=ec2"
    assert req.full_url.startswith("https://")
    assert req.get_method() == "POST"
    assert req.get_header("Authorization") == "Bearer test-ccm-token"
    assert b'"name": "my-lab"' in (req.data or b"")
    assert "json" in (req.get_header("Content-type") or "").lower()


def test_ccm_provision_rejects_more_than_50_hosts(tmp_path):
    from spa.providers import ProviderError
    from spa.providers.ccm import Provider as CcmProvider

    paths = _ccm_paths(
        tmp_path,
        _CCM_MIN
        + "splunk_hosts:\n"
        + "  - iter:\n"
        + "      prefix: h\n"
        + '      numbers: "01..51"\n'
        + "    roles: [indexer]\n",
    )
    provider = CcmProvider(paths, {"instance_type": "t3a.medium"})
    with pytest.raises(ProviderError, match=r"51 hosts.*50") as caught:
        provider.provision([])
    assert "not implemented" not in str(caught.value).lower()


def test_ccm_provision_rejects_illegal_derived_name(tmp_path):
    from spa.providers import ProviderError
    from spa.providers.ccm import Provider as CcmProvider

    env = tmp_path / "lab"
    env.mkdir()
    paths = _ccm_paths(
        env,
        _CCM_MIN + "splunk_hosts:\n  - name: idx1\n    roles: [indexer]\n",
    )
    provider = CcmProvider(paths, {})
    with pytest.raises(ProviderError, match=r"lab") as caught:
        provider.provision([])
    assert caught.value.code == 2
    assert "not implemented" not in str(caught.value).lower()
    assert "idx1-lab" not in str(caught.value)


_CCM_CONFIG = {
    "instance_type": "t3a.medium",
    "disk_storage": 50,
    "operating_system": "rhel_9",
    "key_name": "CCM-Key",
    "ssh_private_key_file": "/tmp/ccm-test-key",
    "ssh_username": "ec2-user",
    "ttl_days": 7,
}


def _ready_deployment(deployment_id="dep-9", ttl="2026-11-17T12:00:00.000Z"):
    return {
        "data": {
            "deployment_id": deployment_id,
            "req_state": "ready",
            "ttl": ttl,
            "instances_data": [
                {"instance_id": "i-aaa", "ip_address": "1.1.1.1", "state": "running"},
                {"instance_id": "i-bbb", "ip_address": "2.2.2.2", "state": "running"},
            ],
        }
    }


def test_ccm_provision_writes_state_inventory_and_warns_ttl(tmp_path, capsys):
    from datetime import datetime, timezone

    from spa.providers.ccm import Provider as CcmProvider, UrllibCcmClient

    env = tmp_path / "mylab"
    env.mkdir()
    paths = _ccm_paths(
        env,
        _CCM_MIN
        + "splunk_hosts:\n"
        + "  - name: idx1\n"
        + "    roles: [indexer]\n"
        + "  - name: sh1\n"
        + "    roles: [search_head]\n",
    )
    opener = ScriptedOpener(
        [
            (200, {"data": {"deployment_id": "dep-9"}}),
            (200, _ready_deployment()),
        ]
    )
    client = UrllibCcmClient(token="test-ccm-token", opener=opener)
    now = datetime(2026, 11, 10, 12, 0, tzinfo=timezone.utc)
    provider = CcmProvider(
        paths,
        _CCM_CONFIG,
        client=client,
        sleep=lambda _seconds: None,
        now=lambda: now,
    )
    result = provider.provision([])
    post = opener.requests[0]
    assert post.get_method() == "POST"
    assert "type=ec2" in post.full_url
    body = json.loads(post.data.decode("utf-8"))
    assert body["num_instances"] == 2
    assert body["name"] == "mylab"
    assert body["ttl"] == "2026-11-17T12:00:00.000Z"
    assert body["ssh_key_name"] == "CCM-Key"
    assert "ebs_storage" not in body
    assert "test-ccm-token" not in json.dumps(body)

    state = json.loads((env / "ccm" / "state.json").read_text(encoding="utf-8"))
    assert state["deployment_id"] == "dep-9"
    assert state["ttl"] == "2026-11-17T12:00:00.000Z"
    assert state["hosts"]["idx1"]["instance_id"] == "i-aaa"
    assert state["hosts"]["sh1"]["instance_id"] == "i-bbb"
    assert "test-ccm-token" not in json.dumps(state)

    inventory = (env / "inventory" / "hosts").read_text(encoding="utf-8")
    assert "idx1" in inventory and "1.1.1.1" in inventory
    assert "sh1" in inventory and "2.2.2.2" in inventory
    assert "ec2-user" in inventory
    assert "/tmp/ccm-test-key" in inventory

    err = capsys.readouterr().err
    assert "terminate" in err.lower()
    assert "2026-11-17" in err
    warnings = result.get("warnings") or []
    assert any("terminate" in item.lower() for item in warnings)


def test_ccm_provision_posts_ebs_storage_when_configured(tmp_path):
    from spa.providers.ccm import Provider as CcmProvider, UrllibCcmClient

    env = tmp_path / "mylab"
    env.mkdir()
    paths = _ccm_paths(
        env,
        _CCM_MIN
        + "  ebs_storage:\n"
        + "    ebs_count: 2\n"
        + "    ebs_size: 100\n"
        + "splunk_hosts:\n"
        + "  - name: idx1\n"
        + "    roles: [indexer]\n"
        + "  - name: sh1\n"
        + "    roles: [search_head]\n",
    )
    opener = ScriptedOpener(
        [
            (200, {"data": {"deployment_id": "dep-9"}}),
            (200, _ready_deployment()),
        ]
    )
    config = dict(_CCM_CONFIG)
    config["ebs_storage"] = {"ebs_count": 2, "ebs_size": 100}
    provider = CcmProvider(
        paths,
        config,
        client=UrllibCcmClient(token="test-ccm-token", opener=opener),
        sleep=lambda _seconds: None,
    )
    provider.provision([])
    body = json.loads(opener.requests[0].data.decode("utf-8"))
    assert body["ebs_storage"] == {"ebs_count": 2, "ebs_size": 100}


def test_ccm_provision_polls_until_req_state_ready(tmp_path):
    from spa.providers.ccm import Provider as CcmProvider, UrllibCcmClient

    env = tmp_path / "mylab"
    env.mkdir()
    paths = _ccm_paths(
        env,
        _CCM_MIN
        + "splunk_hosts:\n"
        + "  - name: idx1\n"
        + "    roles: [indexer]\n"
        + "  - name: sh1\n"
        + "    roles: [search_head]\n",
    )
    pending = _ready_deployment()
    pending["data"]["req_state"] = "pending"
    opener = ScriptedOpener(
        [
            (200, {"data": {"deployment_id": "dep-9"}}),
            (200, pending),
            (200, _ready_deployment()),
        ]
    )
    slept = []
    provider = CcmProvider(
        paths,
        _CCM_CONFIG,
        client=UrllibCcmClient(token="test-ccm-token", opener=opener),
        sleep=slept.append,
        poll_interval=5,
    )
    result = provider.provision([])
    assert result["deployment_id"] == "dep-9"
    assert [req.get_method() for req in opener.requests] == ["POST", "GET", "GET"]
    assert slept == [5]


def _write_ccm_state(env, deployment_id="dep-9", hosts=None):
    state_dir = env / "ccm"
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / "state.json").write_text(
        json.dumps(
            {
                "deployment_id": deployment_id,
                "ttl": "2026-11-01T00:00:00.000Z",
                "hosts": hosts or {"idx1": {"instance_id": "i-aaa"}},
            }
        )
        + "\n",
        encoding="utf-8",
    )


class CcmApiOpener:
    """Route GET/PATCH by path so suspend/resume tests are not request-order scripts."""

    def __init__(self, deployment, missing=False) -> None:
        self.deployment = deployment
        self.missing = missing
        self.requests: List[object] = []
        self.patches: List[dict] = []

    def open(self, req: object, timeout: object = None) -> _FakeResponse:
        import urllib.parse

        self.requests.append(req)
        method = req.get_method()
        path = urllib.parse.urlparse(req.full_url).path
        if self.missing:
            return _FakeResponse(404, b'{"detail":"not found"}')
        if method == "PATCH" and "/instances/" in path:
            body = json.loads(req.data.decode("utf-8")) if req.data else {}
            instance_id = path.rsplit("/", 1)[-1]
            self.patches.append(
                {"instance_id": instance_id, "body": body, "url": req.full_url}
            )
            desired = str(body.get("desired_state") or "")
            for row in self.deployment.get("instances_data") or []:
                if row.get("instance_id") == instance_id and desired:
                    row["state"] = desired
                    row["desired_state"] = desired
            return _FakeResponse(200, b'{"code":200}')
        if method == "GET" and path.endswith("/deployments/" + str(self.deployment.get("deployment_id") or "dep-9")):
            return _FakeResponse(200, json.dumps({"data": self.deployment}).encode("utf-8"))
        raise AssertionError("unexpected %s %s" % (method, req.full_url))


def test_ccm_suspend_patches_instances_stopped(tmp_path):
    from spa.providers.ccm import API_ROOT, Provider as CcmProvider, UrllibCcmClient

    env = tmp_path / "mylab"
    env.mkdir()
    paths = _ccm_paths(
        env,
        _CCM_MIN
        + "splunk_hosts:\n"
        + "  - name: idx1\n"
        + "    roles: [indexer]\n"
        + "  - name: sh1\n"
        + "    roles: [search_head]\n",
    )
    _write_ccm_state(
        env,
        hosts={
            "idx1": {"instance_id": "i-aaa"},
            "sh1": {"instance_id": "i-bbb"},
        },
    )
    deployment = {
        "deployment_id": "dep-9",
        "req_state": "ready",
        "instances_data": [
            {"instance_id": "i-aaa", "ip_address": "1.1.1.1", "state": "running"},
            {"instance_id": "i-bbb", "ip_address": "2.2.2.2", "state": "running"},
        ],
    }
    opener = CcmApiOpener(deployment)
    provider = CcmProvider(
        paths,
        _CCM_CONFIG,
        client=UrllibCcmClient(token="test-ccm-token", opener=opener),
        sleep=lambda _seconds: None,
    )
    result = provider.suspend(yes=True)
    assert "not implemented" not in str(result).lower()
    patched = {row["instance_id"]: row["body"] for row in opener.patches}
    assert patched == {
        "i-aaa": {"desired_state": "stopped"},
        "i-bbb": {"desired_state": "stopped"},
    }
    for row in opener.patches:
        assert row["url"].startswith(API_ROOT)
        assert row["url"].startswith("https://")
        assert "/api/v1/deployments/dep-9/instances/" in row["url"]
    auth = [req.get_header("Authorization") for req in opener.requests]
    assert all(value == "Bearer test-ccm-token" for value in auth)
    assert (env / "ccm" / "state.json").is_file()


def test_ccm_resume_patches_running_and_refreshes_inventory_ips(tmp_path):
    from spa.providers.ccm import Provider as CcmProvider, UrllibCcmClient

    env = tmp_path / "mylab"
    env.mkdir()
    paths = _ccm_paths(
        env,
        _CCM_MIN
        + "splunk_hosts:\n"
        + "  - name: idx1\n"
        + "    roles: [indexer]\n"
        + "  - name: sh1\n"
        + "    roles: [search_head]\n",
    )
    _write_ccm_state(
        env,
        hosts={
            "idx1": {"instance_id": "i-aaa"},
            "sh1": {"instance_id": "i-bbb"},
        },
    )
    hosts_file = env / "inventory" / "hosts"
    hosts_file.write_text(
        'idx1 ansible_host="1.1.1.1" ansible_user="ec2-user" '
        'ansible_ssh_private_key_file="/tmp/ccm-test-key"\n'
        'sh1 ansible_host="2.2.2.2" ansible_user="ec2-user" '
        'ansible_ssh_private_key_file="/tmp/ccm-test-key"\n',
        encoding="utf-8",
    )
    deployment = {
        "deployment_id": "dep-9",
        "req_state": "ready",
        "instances_data": [
            {"instance_id": "i-aaa", "ip_address": "9.9.9.9", "state": "stopped"},
            {"instance_id": "i-bbb", "ip_address": "8.8.8.8", "state": "stopped"},
        ],
    }
    opener = CcmApiOpener(deployment)
    provider = CcmProvider(
        paths,
        _CCM_CONFIG,
        client=UrllibCcmClient(token="test-ccm-token", opener=opener),
        sleep=lambda _seconds: None,
    )
    result = provider.resume(yes=True)
    patched = {row["instance_id"]: row["body"] for row in opener.patches}
    assert patched == {
        "i-aaa": {"desired_state": "running"},
        "i-bbb": {"desired_state": "running"},
    }
    inventory = hosts_file.read_text(encoding="utf-8")
    assert "9.9.9.9" in inventory
    assert "8.8.8.8" in inventory
    assert "1.1.1.1" not in inventory
    assert "2.2.2.2" not in inventory
    assert result.get("inventory") == str(hosts_file)


def test_ccm_resume_hosts_filter_merges_inventory(tmp_path):
    from spa.providers.ccm import Provider as CcmProvider, UrllibCcmClient

    env = tmp_path / "mylab"
    env.mkdir()
    paths = _ccm_paths(
        env,
        _CCM_MIN
        + "splunk_hosts:\n"
        + "  - name: idx1\n"
        + "    roles: [indexer]\n"
        + "  - name: sh1\n"
        + "    roles: [search_head]\n",
    )
    _write_ccm_state(
        env,
        hosts={
            "idx1": {"instance_id": "i-aaa"},
            "sh1": {"instance_id": "i-bbb"},
        },
    )
    hosts_file = env / "inventory" / "hosts"
    hosts_file.write_text(
        'idx1 ansible_host="1.1.1.1" ansible_user="ec2-user" '
        'ansible_ssh_private_key_file="/tmp/ccm-test-key"\n'
        'sh1 ansible_host="2.2.2.2" ansible_user="ec2-user" '
        'ansible_ssh_private_key_file="/tmp/ccm-test-key"\n',
        encoding="utf-8",
    )
    opener = CcmApiOpener(
        {
            "deployment_id": "dep-9",
            "req_state": "ready",
            "instances_data": [
                {"instance_id": "i-aaa", "ip_address": "9.9.9.9", "state": "stopped"},
                {"instance_id": "i-bbb", "ip_address": "2.2.2.2", "state": "stopped"},
            ],
        }
    )
    provider = CcmProvider(
        paths,
        _CCM_CONFIG,
        client=UrllibCcmClient(token="test-ccm-token", opener=opener),
        sleep=lambda _seconds: None,
    )
    provider.resume(yes=True, hosts=["idx1"])
    assert {row["instance_id"] for row in opener.patches} == {"i-aaa"}
    inventory = hosts_file.read_text(encoding="utf-8")
    assert "9.9.9.9" in inventory
    assert "sh1" in inventory
    assert "2.2.2.2" in inventory


def test_ccm_resume_warns_when_operation_hours_are_business_hours(tmp_path, capsys):
    from spa.providers.ccm import Provider as CcmProvider, UrllibCcmClient

    env = tmp_path / "mylab"
    env.mkdir()
    paths = _ccm_paths(
        env,
        _CCM_MIN
        + "  operation_hours: business_hours\n"
        + "splunk_hosts:\n  - name: idx1\n    roles: [indexer]\n",
    )
    _write_ccm_state(env)
    config = dict(_CCM_CONFIG)
    config["operation_hours"] = "business_hours"
    opener = CcmApiOpener(
        {
            "deployment_id": "dep-9",
            "req_state": "ready",
            "instances_data": [
                {"instance_id": "i-aaa", "ip_address": "9.9.9.9", "state": "stopped"},
            ],
        }
    )
    provider = CcmProvider(
        paths,
        config,
        client=UrllibCcmClient(token="test-ccm-token", opener=opener),
        sleep=lambda _seconds: None,
    )
    result = provider.resume(yes=True)
    err = capsys.readouterr().err
    assert "business_hours" in err
    assert "stop" in err.lower()
    warnings = result.get("warnings") or []
    assert any("business_hours" in item and "stop" in item.lower() for item in warnings)
    assert all("operation_hours" not in row["body"] for row in opener.patches)


@pytest.mark.parametrize("action", ["suspend", "resume"])
def test_ccm_power_fails_when_deployment_expired(tmp_path, action):
    from spa.providers import ProviderError
    from spa.providers.ccm import Provider as CcmProvider, UrllibCcmClient

    env = tmp_path / "mylab"
    env.mkdir()
    paths = _ccm_paths(
        env,
        _CCM_MIN + "splunk_hosts:\n  - name: idx1\n    roles: [indexer]\n",
    )
    _write_ccm_state(env)
    opener = CcmApiOpener(
        {
            "deployment_id": "dep-9",
            "instances_data": [
                {"instance_id": "i-aaa", "ip_address": "1.1.1.1", "state": "stopped"},
            ],
        },
        missing=True,
    )
    provider = CcmProvider(
        paths,
        _CCM_CONFIG,
        client=UrllibCcmClient(token="test-ccm-token", opener=opener),
    )
    with pytest.raises(ProviderError) as caught:
        getattr(provider, action)(yes=True)
    message = str(caught.value)
    assert "TTL" in message or "terminate" in message.lower()
    assert "spa destroy --yes" in message
    assert "spa provision --yes" in message
    assert opener.patches == []


def test_ccm_host_status_indexes_name_instance_and_ip(tmp_path):
    from spa.providers.ccm import Provider as CcmProvider, UrllibCcmClient

    env = tmp_path / "mylab"
    env.mkdir()
    paths = _ccm_paths(
        env,
        _CCM_MIN
        + "splunk_hosts:\n"
        + "  - name: idx1\n"
        + "    roles: [indexer]\n"
        + "  - name: sh1\n"
        + "    roles: [search_head]\n",
    )
    _write_ccm_state(
        env,
        hosts={
            "idx1": {"instance_id": "i-aaa"},
            "sh1": {"instance_id": "i-bbb"},
        },
    )
    opener = CcmApiOpener(
        {
            "deployment_id": "dep-9",
            "req_state": "ready",
            "instances_data": [
                {"instance_id": "i-aaa", "ip_address": "1.1.1.1", "state": "stopped"},
                {"instance_id": "i-bbb", "ip_address": "2.2.2.2", "state": "running"},
            ],
        }
    )
    provider = CcmProvider(
        paths,
        _CCM_CONFIG,
        client=UrllibCcmClient(token="test-ccm-token", opener=opener),
    )
    status = provider.host_status()
    assert status["idx1"]["state"] == "stopped"
    assert status["idx1"]["reachable"] is False
    assert status["idx1"]["instance_id"] == "i-aaa"
    assert status["i-aaa"] == status["idx1"]
    assert status["1.1.1.1"] == status["idx1"]
    assert status["sh1"]["state"] == "running"
    assert status["sh1"]["reachable"] is True
    assert status["2.2.2.2"] == status["sh1"]
    methods = [req.get_method() for req in opener.requests]
    assert methods == ["GET"]
    assert opener.patches == []


def test_ccm_provision_state_404_is_not_provisioned(tmp_path):
    from spa.providers.ccm import Provider as CcmProvider, UrllibCcmClient

    env = tmp_path / "mylab"
    env.mkdir()
    paths = _ccm_paths(
        env,
        _CCM_MIN + "splunk_hosts:\n  - name: idx1\n    roles: [indexer]\n",
    )
    _write_ccm_state(env)
    opener = ScriptedOpener([(404, {"detail": "not found"})])
    provider = CcmProvider(
        paths,
        _CCM_CONFIG,
        client=UrllibCcmClient(token="test-ccm-token", opener=opener),
    )
    state = provider.provision_state()
    assert state.provisioned is False
    assert "TTL" in state.reason or "terminate" in state.reason.lower()
    assert "spa destroy --yes" in state.hint
    assert "spa provision --yes" in state.hint


def test_ccm_provision_state_missing_from_list_is_not_provisioned(tmp_path):
    from spa.providers.ccm import Provider as CcmProvider, UrllibCcmClient

    env = tmp_path / "mylab"
    env.mkdir()
    paths = _ccm_paths(
        env,
        _CCM_MIN + "splunk_hosts:\n  - name: idx1\n    roles: [indexer]\n",
    )
    _write_ccm_state(env)
    opener = ScriptedOpener(
        [
            (200, {"data": None}),
            (200, {"data": [{"deployment_id": "dep-other"}]}),
        ]
    )
    provider = CcmProvider(
        paths,
        _CCM_CONFIG,
        client=UrllibCcmClient(token="test-ccm-token", opener=opener),
    )
    state = provider.provision_state()
    assert state.provisioned is False
    assert "TTL" in state.reason or "terminate" in state.reason.lower()
    assert "spa destroy --yes" in state.hint


def test_ccm_destroy_treats_404_as_success_and_clears_local_state(tmp_path):
    from spa.providers.ccm import API_ROOT, Provider as CcmProvider, UrllibCcmClient

    env = tmp_path / "mylab"
    env.mkdir()
    paths = _ccm_paths(
        env,
        _CCM_MIN + "splunk_hosts:\n  - name: idx1\n    roles: [indexer]\n",
    )
    _write_ccm_state(env)
    hosts_file = env / "inventory" / "hosts"
    hosts_file.write_text('idx1 ansible_host="1.1.1.1"\n', encoding="utf-8")
    opener = ScriptedOpener([(404, b"")])
    provider = CcmProvider(
        paths,
        _CCM_CONFIG,
        client=UrllibCcmClient(token="test-ccm-token", opener=opener),
    )
    result = provider.destroy([])
    req = opener.requests[0]
    assert req.get_method() == "DELETE"
    assert req.full_url == API_ROOT + "/api/v1/deployments/dep-9"
    assert not (env / "ccm" / "state.json").exists()
    assert not hosts_file.exists() or not hosts_file.read_text(encoding="utf-8").strip()
    assert result["deployment_id"] == "dep-9"
