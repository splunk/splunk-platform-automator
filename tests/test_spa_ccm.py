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


@pytest.fixture(autouse=True)
def _noop_ssh_wait(monkeypatch):
    monkeypatch.setattr(
        "spa.providers.ccm.wait_managed_ssh", lambda *a, **k: {"hosts": []}
    )

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
    assert "Check VPN" in str(caught.value)
    assert "failed with" not in str(caught.value)


def test_ccm_client_url_error_classifies_dns_tls_timeout_and_refused():
    import socket
    import ssl
    import urllib.error

    from spa.providers.ccm import CcmError, UrllibCcmClient

    token = "test-ccm-pat-value"

    cases = (
        (socket.gaierror(8, "nodename nor servname provided, or not known"), "DNS"),
        (ConnectionRefusedError(61, "Connection refused to %s" % token), "connection refused"),
        (ssl.SSLError("certificate verify failed with %s" % token), "TLS"),
        (TimeoutError("timed out talking to %s" % token), "timeout"),
    )
    for reason, label in cases:
        class BoomOpener:
            def open(self, req: object, timeout: object = None) -> None:
                raise urllib.error.URLError(reason)

        client = UrllibCcmClient(token=token, opener=BoomOpener())
        with pytest.raises(CcmError, match="CCM API request failed") as caught:
            client.request("GET", "/api/v1/deployments")
        text = str(caught.value)
        assert label in text
        assert "Check VPN" in text
        assert token not in text
        assert "Authorization" not in text
        assert "certificate verify failed" not in text
        assert "nodename" not in text
        assert "Connection refused to" not in text
        assert "timed out talking" not in text


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


def test_ccm_provision_rejects_mixed_external_hosts(tmp_path):
    from spa.providers import ProviderError
    from spa.providers.ccm import Provider as CcmProvider, UrllibCcmClient

    paths = _ccm_paths(
        tmp_path,
        _CCM_MIN
        + "splunk_hosts:\n"
        + "  - name: idx1\n"
        + "    roles: [indexer]\n"
        + "  - name: byo1\n"
        + "    roles: [search_head]\n"
        + "    external:\n",
    )
    opener = FakeOpener()
    provider = CcmProvider(
        paths,
        _CCM_CONFIG,
        client=UrllibCcmClient(token="test-ccm-token", opener=opener),
    )
    with pytest.raises(ProviderError, match=r"cannot mix external hosts") as caught:
        provider.provision([])
    assert caught.value.code == 2
    assert opener.requests == []


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
    assert "terminate" not in err.lower()
    warnings = result.get("warnings") or []
    assert warnings
    for item in warnings:
        assert "terminate" in item.lower()
        assert "2026-11-17T12:00:00.000Z" not in item


def test_ccm_lifecycle_warnings_use_controller_local_time(tmp_path):
    import os
    import time
    from datetime import datetime, timezone

    from spa.providers.ccm import Provider as CcmProvider, UrllibCcmClient

    env = tmp_path / "mylab"
    env.mkdir()
    paths = _ccm_paths(
        env,
        _CCM_MIN
        + "splunk_hosts:\n"
        + "  - name: idx1\n"
        + "    roles: [indexer]\n",
    )
    previous = os.environ.get("TZ")
    os.environ["TZ"] = "America/New_York"
    time.tzset()
    try:
        provider = CcmProvider(
            paths,
            _CCM_CONFIG,
            client=UrllibCcmClient(token="test-ccm-token", opener=ScriptedOpener([])),
            now=lambda: datetime(2026, 11, 10, 12, 0, tzinfo=timezone.utc),
        )
        warnings = provider.lifecycle_warnings("provision")
        assert warnings == [
            "CCM will terminate the whole deployment when "
            "Tuesday, 17 Nov 2026 at 07:00 EST passes."
        ]
        assert provider.lifecycle_warnings("destroy") == []
    finally:
        if previous is None:
            os.environ.pop("TZ", None)
        else:
            os.environ["TZ"] = previous
        time.tzset()


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


def test_ccm_provision_emits_run_log_progress(tmp_path):
    from spa.providers.ccm import Provider as CcmProvider, UrllibCcmClient

    class RecordingLog:
        def __init__(self) -> None:
            self.events = []
            self.heartbeats = 0

        def emit(self, raw):
            self.events.append(dict(raw))
            return raw

        def start_heartbeat(self) -> None:
            self.heartbeats += 1

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
    log = RecordingLog()
    provider = CcmProvider(
        paths,
        _CCM_CONFIG,
        client=UrllibCcmClient(token="test-ccm-token", opener=opener),
        sleep=lambda _seconds: None,
    )
    provider.provision([], run_log=log)
    phases = [row.get("phase") for row in log.events]
    tasks = " ".join(str(row.get("task") or "") for row in log.events)
    assert "ccm_create" in phases
    assert "ccm_ready" in phases
    assert "wait_ssh" in phases
    assert "CCM" in tasks
    assert "dep-9" in tasks
    assert log.heartbeats == 1


def test_ccm_provision_refuses_when_state_has_live_deployment(tmp_path):
    from spa.providers import ProviderError
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
    _write_ccm_state(env)
    opener = ScriptedOpener(
        [
            (200, {"data": {"deployment_id": "dep-9", "req_state": "ready"}}),
            (200, _ready_deployment()),
        ]
    )
    provider = CcmProvider(
        paths,
        _CCM_CONFIG,
        client=UrllibCcmClient(token="test-ccm-token", opener=opener),
        sleep=lambda _seconds: None,
    )
    with pytest.raises(ProviderError, match=r"already provisioned: dep-9") as caught:
        provider.provision([])
    assert caught.value.code == 2
    assert "spa destroy --yes" in str(caught.value)
    assert [req.get_method() for req in opener.requests] == ["GET"]


def test_ccm_provision_refuses_when_state_has_expired_deployment(tmp_path):
    from spa.providers import ProviderError
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
    _write_ccm_state(env)
    opener = ScriptedOpener(
        [
            (404, {"detail": "not found"}),
            (200, {"data": {"deployment_id": "dep-new"}}),
            (200, _ready_deployment("dep-new")),
        ]
    )
    provider = CcmProvider(
        paths,
        _CCM_CONFIG,
        client=UrllibCcmClient(token="test-ccm-token", opener=opener),
        sleep=lambda _seconds: None,
    )
    with pytest.raises(ProviderError, match=r"spa destroy --yes then spa deploy --yes") as caught:
        provider.provision([])
    text = str(caught.value)
    assert "TTL" in text or "terminate" in text.lower()
    assert "dep-9" in text
    assert [req.get_method() for req in opener.requests] == ["GET"]


def test_ccm_provision_records_deployment_id_when_poll_fails(tmp_path):
    from spa.providers import ProviderError
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
            (200, b""),
        ]
    )
    provider = CcmProvider(
        paths,
        _CCM_CONFIG,
        client=UrllibCcmClient(token="test-ccm-token", opener=opener),
        sleep=lambda _seconds: None,
        poll_attempts=1,
    )
    with pytest.raises(ProviderError, match=r"did not become ready"):
        provider.provision([])
    state = json.loads((env / "ccm" / "state.json").read_text(encoding="utf-8"))
    assert state["deployment_id"] == "dep-9"
    assert state["hosts"] == {}
    assert state.get("req_state") == "pending"
    result = provider.destroy([])
    assert result["deployment_id"] == "dep-9"
    assert [req.get_method() for req in opener.requests] == ["POST", "GET", "DELETE"]
    assert opener.requests[2].full_url.endswith("/api/v1/deployments/dep-9")


def test_ccm_provision_refuses_when_state_is_pending(tmp_path):
    from spa.providers import ProviderError
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
    state_dir = env / "ccm"
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / "state.json").write_text(
        json.dumps(
            {
                "deployment_id": "dep-9",
                "ttl": "2026-11-17T12:00:00.000Z",
                "hosts": {},
                "req_state": "pending",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    opener = ScriptedOpener(
        [
            (200, {"data": {"deployment_id": "dep-9", "req_state": "pending"}}),
            (200, {"data": {"deployment_id": "dep-new"}}),
            (200, _ready_deployment("dep-new")),
        ]
    )
    provider = CcmProvider(
        paths,
        _CCM_CONFIG,
        client=UrllibCcmClient(token="test-ccm-token", opener=opener),
        sleep=lambda _seconds: None,
    )
    with pytest.raises(ProviderError, match=r"already provisioned: dep-9") as caught:
        provider.provision([])
    assert caught.value.code == 2
    assert [req.get_method() for req in opener.requests] == ["GET"]


def _validate_cap_env(tmp_path, host_count, deployment_id=None):
    key = tmp_path / "CCM-Key.pem"
    key.write_text("not-a-real-key\n", encoding="utf-8")
    env = tmp_path / "mylab"
    env.mkdir()
    paths = _ccm_paths(
        env,
        _CCM_MIN
        + "splunk_hosts:\n"
        + "  - iter:\n"
        + "      prefix: h\n"
        + '      numbers: "01..%02d"\n' % host_count
        + "    roles: [indexer]\n",
    )
    if deployment_id is not None:
        _write_ccm_state(env, deployment_id=deployment_id)
    config = {
        **_CCM_CONFIG,
        "ssh_private_key_file": str(key),
        "key_name": "CCM-Key",
    }
    return paths, config


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


class AfterPatchGetOpener(CcmApiOpener):
    """Serve scripted GET bodies after the first instance PATCH (poll sequences)."""

    def __init__(self, deployment, after_patch_gets, missing=False) -> None:
        super().__init__(deployment, missing=missing)
        self.after_patch_gets = list(after_patch_gets)

    def open(self, req: object, timeout: object = None) -> _FakeResponse:
        import urllib.parse

        method = req.get_method()
        path = urllib.parse.urlparse(req.full_url).path
        dep_id = str(self.deployment.get("deployment_id") or "dep-9")
        if (
            method == "GET"
            and self.patches
            and self.after_patch_gets
            and path.endswith("/deployments/" + dep_id)
        ):
            self.requests.append(req)
            payload = self.after_patch_gets.pop(0)
            return _FakeResponse(200, json.dumps({"data": payload}).encode("utf-8"))
        return super().open(req, timeout)


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


def test_ccm_resume_skips_patch_when_already_running_and_rewrites_ssh_user(tmp_path):
    from spa.providers.ccm import Provider as CcmProvider, UrllibCcmClient

    env = tmp_path / "mylab"
    env.mkdir()
    paths = _ccm_paths(
        env,
        _CCM_MIN
        + "splunk_hosts:\n"
        + "  - name: idx1\n"
        + "    roles: [indexer]\n",
    )
    _write_ccm_state(env, hosts={"idx1": {"instance_id": "i-aaa"}})
    hosts_file = env / "inventory" / "hosts"
    hosts_file.write_text(
        'idx1 ansible_host="1.1.1.1" ansible_user="ec2-user" '
        'ansible_ssh_private_key_file="/tmp/ccm-test-key"\n',
        encoding="utf-8",
    )
    deployment = {
        "deployment_id": "dep-9",
        "req_state": "ready",
        "instances_data": [
            {"instance_id": "i-aaa", "ip_address": "9.9.9.9", "state": "running"},
        ],
    }
    opener = CcmApiOpener(deployment)
    provider = CcmProvider(
        paths,
        {**_CCM_CONFIG, "ssh_username": "splunker"},
        client=UrllibCcmClient(token="test-ccm-token", opener=opener),
        sleep=lambda _seconds: None,
    )
    result = provider.resume(yes=True)
    assert opener.patches == []
    inventory = hosts_file.read_text(encoding="utf-8")
    assert 'ansible_user="splunker"' in inventory
    assert 'ansible_user="ec2-user"' not in inventory
    assert "9.9.9.9" in inventory
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


def test_ccm_resume_polls_until_running_with_ip_and_refreshes_inventory(tmp_path):
    from spa.providers.ccm import Provider as CcmProvider, UrllibCcmClient

    env = tmp_path / "mylab"
    env.mkdir()
    paths = _ccm_paths(
        env,
        _CCM_MIN + "splunk_hosts:\n  - name: idx1\n    roles: [indexer]\n",
    )
    _write_ccm_state(env)
    hosts_file = env / "inventory" / "hosts"
    hosts_file.write_text(
        'idx1 ansible_host="1.1.1.1" ansible_user="ec2-user" '
        'ansible_ssh_private_key_file="/tmp/ccm-test-key"\n',
        encoding="utf-8",
    )
    pending = {
        "deployment_id": "dep-9",
        "req_state": "ready",
        "instances_data": [
            {"instance_id": "i-aaa", "ip_address": "", "state": "pending"},
        ],
    }
    ready = {
        "deployment_id": "dep-9",
        "req_state": "ready",
        "instances_data": [
            {"instance_id": "i-aaa", "ip_address": "9.9.9.9", "state": "running"},
        ],
    }
    opener = AfterPatchGetOpener(pending, after_patch_gets=[pending, ready])
    slept = []
    provider = CcmProvider(
        paths,
        _CCM_CONFIG,
        client=UrllibCcmClient(token="test-ccm-token", opener=opener),
        sleep=slept.append,
        poll_interval=5,
    )
    result = provider.resume(yes=True)
    inventory = hosts_file.read_text(encoding="utf-8")
    assert "9.9.9.9" in inventory
    assert "1.1.1.1" not in inventory
    assert slept == [5]
    assert result.get("waited") is True
    assert result.get("inventory") == str(hosts_file)


def test_ccm_resume_poll_exhaustion_raises(tmp_path):
    from spa.providers import ProviderError
    from spa.providers.ccm import Provider as CcmProvider, UrllibCcmClient

    env = tmp_path / "mylab"
    env.mkdir()
    paths = _ccm_paths(
        env,
        _CCM_MIN + "splunk_hosts:\n  - name: idx1\n    roles: [indexer]\n",
    )
    _write_ccm_state(env)
    pending = {
        "deployment_id": "dep-9",
        "req_state": "ready",
        "instances_data": [
            {"instance_id": "i-aaa", "ip_address": "", "state": "pending"},
        ],
    }
    opener = AfterPatchGetOpener(pending, after_patch_gets=[pending, pending])
    provider = CcmProvider(
        paths,
        _CCM_CONFIG,
        client=UrllibCcmClient(token="test-ccm-token", opener=opener),
        sleep=lambda _seconds: None,
        poll_attempts=2,
    )
    with pytest.raises(ProviderError, match=r"did not become running"):
        provider.resume(yes=True)


def test_ccm_resume_wait_false_skips_poll_and_inventory(tmp_path):
    from spa.providers.ccm import Provider as CcmProvider, UrllibCcmClient

    env = tmp_path / "mylab"
    env.mkdir()
    paths = _ccm_paths(
        env,
        _CCM_MIN + "splunk_hosts:\n  - name: idx1\n    roles: [indexer]\n",
    )
    _write_ccm_state(env)
    hosts_file = env / "inventory" / "hosts"
    original = (
        'idx1 ansible_host="1.1.1.1" ansible_user="ec2-user" '
        'ansible_ssh_private_key_file="/tmp/ccm-test-key"\n'
    )
    hosts_file.write_text(original, encoding="utf-8")
    opener = CcmApiOpener(
        {
            "deployment_id": "dep-9",
            "req_state": "ready",
            "instances_data": [
                {"instance_id": "i-aaa", "ip_address": "9.9.9.9", "state": "stopped"},
            ],
        }
    )
    slept = []
    provider = CcmProvider(
        paths,
        _CCM_CONFIG,
        client=UrllibCcmClient(token="test-ccm-token", opener=opener),
        sleep=slept.append,
    )
    result = provider.resume(yes=True, wait=False)
    assert result.get("waited") is False
    assert "inventory" not in result
    assert slept == []
    assert hosts_file.read_text(encoding="utf-8") == original
    methods = [req.get_method() for req in opener.requests]
    assert methods.count("PATCH") == 1
    assert methods.count("GET") == 1


def test_ccm_suspend_polls_until_stopped(tmp_path):
    from spa.providers.ccm import Provider as CcmProvider, UrllibCcmClient

    env = tmp_path / "mylab"
    env.mkdir()
    paths = _ccm_paths(
        env,
        _CCM_MIN + "splunk_hosts:\n  - name: idx1\n    roles: [indexer]\n",
    )
    _write_ccm_state(env)
    stopping = {
        "deployment_id": "dep-9",
        "req_state": "ready",
        "instances_data": [
            {"instance_id": "i-aaa", "ip_address": "1.1.1.1", "state": "stopping"},
        ],
    }
    stopped = {
        "deployment_id": "dep-9",
        "req_state": "ready",
        "instances_data": [
            {"instance_id": "i-aaa", "ip_address": "1.1.1.1", "state": "stopped"},
        ],
    }
    opener = AfterPatchGetOpener(
        {
            "deployment_id": "dep-9",
            "req_state": "ready",
            "instances_data": [
                {"instance_id": "i-aaa", "ip_address": "1.1.1.1", "state": "running"},
            ],
        },
        after_patch_gets=[stopping, stopped],
    )
    slept = []
    provider = CcmProvider(
        paths,
        _CCM_CONFIG,
        client=UrllibCcmClient(token="test-ccm-token", opener=opener),
        sleep=slept.append,
        poll_interval=5,
    )
    result = provider.suspend(yes=True)
    assert slept == [5]
    assert result.get("waited") is True


def test_ccm_resume_warns_when_operation_hours_are_business_hours(tmp_path, capsys):
    from datetime import datetime, timezone

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
        now=lambda: datetime(2026, 11, 13, 20, 0, tzinfo=timezone.utc),
    )
    result = provider.resume(yes=True)
    err = capsys.readouterr().err
    assert "business_hours" in err
    assert "stop" in err.lower()
    warnings = result.get("warnings") or []
    assert any("business_hours" in item and "stop" in item.lower() for item in warnings)
    assert all("operation_hours" not in row["body"] for row in opener.patches)


def test_ccm_resume_skips_warning_inside_business_hours_window(tmp_path, capsys):
    from datetime import datetime, timezone

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
        now=lambda: datetime(2026, 11, 13, 10, 0, tzinfo=timezone.utc),
    )
    result = provider.resume(yes=True)
    err = capsys.readouterr().err
    assert "business_hours" not in err
    assert not result.get("warnings")


def test_ccm_operation_hours_set_records_state_and_resume_skips_stale_yaml_warning(
    tmp_path, capsys
):
    from datetime import datetime, timezone

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
    config["timezone"] = "UTC"
    setter = CcmProvider(
        paths,
        config,
        client=UrllibCcmClient(token="test-ccm-token", opener=FakeOpener(status=200, body=b"{}")),
    )
    setter.set_operation_hours("manual")
    state = json.loads((env / "ccm" / "state.json").read_text(encoding="utf-8"))
    assert state["operation_hours"] == "manual"
    assert state["deployment_id"] == "dep-9"
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
        now=lambda: datetime(2026, 11, 13, 20, 0, tzinfo=timezone.utc),
    )
    result = provider.resume(yes=True)
    err = capsys.readouterr().err
    assert "business_hours" not in err
    assert not result.get("warnings")


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
    assert "spa deploy --yes" in message
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
            "ttl": "2026-11-24T13:26:51.000Z",
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
    assert status["idx1"]["ttl"] == "2026-11-24T13:26:51.000Z"
    assert status["i-aaa"] == status["idx1"]
    assert status["1.1.1.1"] == status["idx1"]
    assert status["sh1"]["state"] == "running"
    assert status["sh1"]["reachable"] is True
    assert status["sh1"]["ttl"] == "2026-11-24T13:26:51.000Z"
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
    assert "spa deploy --yes" in state.hint


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


def test_ccm_destroy_raises_on_http_500(tmp_path):
    from spa.providers import ProviderError
    from spa.providers.ccm import Provider as CcmProvider, UrllibCcmClient

    env = tmp_path / "mylab"
    env.mkdir()
    paths = _ccm_paths(
        env,
        _CCM_MIN + "splunk_hosts:\n  - name: idx1\n    roles: [indexer]\n",
    )
    _write_ccm_state(env)
    opener = FakeOpener(status=500, body=b"")
    provider = CcmProvider(
        paths,
        _CCM_CONFIG,
        client=UrllibCcmClient(token="test-ccm-token", opener=opener),
    )
    with pytest.raises(ProviderError, match=r"HTTP 500"):
        provider.destroy([])
    assert (env / "ccm" / "state.json").is_file()


def test_ccm_check_auth_reports_token_not_set(monkeypatch):
    monkeypatch.delenv("CCM_TOKEN", raising=False)
    from spa.providers.ccm import execute

    result = execute(action="check-auth")
    assert result.ok is False
    assert result.code == 1
    assert "CCM_TOKEN is not set" in (result.error or "")
    assert "test-ccm" not in (result.error or "").lower()


def test_ccm_check_auth_accepts_bearer_without_printing_token():
    from spa.providers.ccm import UrllibCcmClient, execute

    opener = FakeOpener(status=200, body=b"[]")
    result = execute(
        action="check-auth",
        client=UrllibCcmClient(token="test-ccm-token", opener=opener),
    )
    assert result.ok is True
    assert result.data["ccm_token"] == "set"
    assert opener.requests[0].full_url.endswith("/api/v1/deployments")
    encoded = json.dumps(result.data)
    assert "test-ccm-token" not in encoded


def test_ccm_business_purposes_and_operation_hours_are_closed_sets():
    from spa.providers.ccm import execute

    purposes = execute(action="business-purposes", subaction="list")
    assert purposes.ok is True
    names = [row["name"] for row in purposes.data["items"]]
    assert names == ["DeveloperInstance", "SalesOpportunity", "SupportCase"]
    hours = execute(action="operation-hours", subaction="list")
    assert hours.ok is True
    assert [row["name"] for row in hours.data["items"]] == ["manual", "business_hours"]


def test_ccm_operating_systems_list_uses_meta_attribute():
    from spa.providers.ccm import API_ROOT, UrllibCcmClient, execute

    opener = FakeOpener(
        status=200,
        body=json.dumps(["ubuntu_22.04", "rhel_9"]).encode("utf-8"),
    )
    result = execute(
        action="operating-systems",
        subaction="list",
        client=UrllibCcmClient(token="test-ccm-token", opener=opener),
    )
    assert result.ok is True
    assert [row["name"] for row in result.data["items"]] == ["ubuntu_22.04", "rhel_9"]
    req = opener.requests[0]
    assert req.full_url.startswith(API_ROOT + "/api/v1/meta")
    assert "attribute=operating_systems" in req.full_url
    assert req.get_method() == "GET"


def test_ccm_instance_types_list_reads_meta_object_envelope():
    from spa.providers.ccm import UrllibCcmClient, execute, format_ccm_text

    opener = FakeOpener(
        status=200,
        body=json.dumps(
            {
                "operating_systems": None,
                "disk_storage": None,
                "instance_types": ["c5a.4xlarge", "t3a.medium"],
                "svas": None,
                "ebs_disk_storage": None,
            }
        ).encode("utf-8"),
    )
    result = execute(
        action="instance-types",
        subaction="list",
        client=UrllibCcmClient(token="test-ccm-token", opener=opener),
    )
    assert result.ok is True
    assert [row["name"] for row in result.data["items"]] == ["c5a.4xlarge", "t3a.medium"]
    assert format_ccm_text(result.data) == "c5a.4xlarge\nt3a.medium\n"


def test_ccm_survey_includes_meta_and_gui_sets():
    import urllib.parse

    from spa.providers.ccm import UrllibCcmClient, execute

    class MetaOpener:
        def __init__(self) -> None:
            self.requests: List[object] = []

        def open(self, req: object, timeout: object = None) -> _FakeResponse:
            self.requests.append(req)
            attr = urllib.parse.parse_qs(urllib.parse.urlparse(req.full_url).query).get(
                "attribute", [""]
            )[0]
            payload = {
                "operating_systems": ["rhel_9"],
                "instance_types": ["t3a.medium"],
                "disk_storage": [50, 100],
            }.get(attr, [])
            return _FakeResponse(200, json.dumps(payload).encode("utf-8"))

    opener = MetaOpener()
    result = execute(
        action="survey",
        client=UrllibCcmClient(token="test-ccm-token", opener=opener),
    )
    assert result.ok is True
    data = result.data
    assert [row["name"] for row in data["operating_systems"]["items"]] == ["rhel_9"]
    assert [row["name"] for row in data["instance_types"]["items"]] == ["t3a.medium"]
    assert [row["name"] for row in data["disk_storage"]["items"]] == [50, 100]
    assert [row["name"] for row in data["business_purposes"]["items"]] == [
        "DeveloperInstance",
        "SalesOpportunity",
        "SupportCase",
    ]
    assert [row["name"] for row in data["operation_hours"]["items"]] == [
        "manual",
        "business_hours",
    ]
    queried = [
        urllib.parse.parse_qs(urllib.parse.urlparse(req.full_url).query)["attribute"][0]
        for req in opener.requests
    ]
    assert queried == ["operating_systems", "instance_types", "disk_storage"]


def test_ccm_ssh_keys_list_marks_local_file_and_omits_public_key(tmp_path):
    from spa.providers.ccm import UrllibCcmClient, execute

    key = tmp_path / "CCM-Key.pem"
    key.write_text("not-a-real-key\n", encoding="utf-8")
    opener = FakeOpener(
        status=200,
        body=json.dumps(
            [
                {
                    "pub_key_name": "CCM-Key",
                    "fingerprint": "SHA256:abcd",
                    "public_key": "ssh-rsa AAAA-long-material",
                }
            ]
        ).encode("utf-8"),
    )
    result = execute(
        action="ssh-keys",
        subaction="list",
        config={"ssh_private_key_file": str(key), "key_name": "CCM-Key"},
        client=UrllibCcmClient(token="test-ccm-token", opener=opener),
    )
    assert result.ok is True
    row = result.data["items"][0]
    assert row["name"] == "CCM-Key"
    assert row["fingerprint"] == "SHA256:abcd"
    assert row["local_private_key"] == "yes"
    encoded = json.dumps(result.data)
    assert "AAAA-long-material" not in encoded
    assert "public_key" not in encoded
    assert opener.requests[0].full_url.endswith("/ssh_keys/")


def test_ccm_ttl_extend_patches_and_persists_expiry(tmp_path):
    from datetime import datetime, timezone

    from spa.providers.ccm import API_ROOT, UrllibCcmClient, execute

    env = tmp_path / "mylab"
    env.mkdir()
    paths = _ccm_paths(
        env,
        _CCM_MIN + "splunk_hosts:\n  - name: idx1\n    roles: [indexer]\n",
    )
    _write_ccm_state(env)
    opener = FakeOpener(status=200, body=b'{"data":{"ttl":"2026-12-10T12:00:00.000Z"}}')
    now = datetime(2026, 11, 10, 12, 0, tzinfo=timezone.utc)
    result = execute(
        action="ttl",
        subaction="extend",
        days=30,
        confirm=True,
        paths=paths,
        config=_CCM_CONFIG,
        client=UrllibCcmClient(token="test-ccm-token", opener=opener),
        now=now,
    )
    assert result.ok is True
    req = opener.requests[0]
    assert req.get_method() == "PATCH"
    assert req.full_url == API_ROOT + "/api/v1/deployments/dep-9"
    body = json.loads(req.data.decode("utf-8"))
    assert body == {"ttl": "2026-12-10T12:00:00.000Z"}
    state = json.loads((env / "ccm" / "state.json").read_text(encoding="utf-8"))
    assert state["ttl"] == "2026-12-10T12:00:00.000Z"
    assert result.data["ttl"] == "2026-12-10T12:00:00.000Z"


def test_ccm_ttl_extend_without_yes_on_non_tty_names_yes():
    from spa.providers.ccm import execute

    result = execute(action="ttl", subaction="extend", days=7, confirm=False, agent=False)
    assert result.ok is False
    assert result.code == 2
    assert "-y/--yes" in (result.error or "")


def test_ccm_operation_hours_set_patches_manual(tmp_path):
    from spa.providers.ccm import API_ROOT, UrllibCcmClient, execute

    env = tmp_path / "mylab"
    env.mkdir()
    paths = _ccm_paths(
        env,
        _CCM_MIN + "splunk_hosts:\n  - name: idx1\n    roles: [indexer]\n",
    )
    _write_ccm_state(env)
    opener = FakeOpener(status=200, body=b"{}")
    result = execute(
        action="operation-hours",
        subaction="set",
        hours="manual",
        confirm=True,
        paths=paths,
        config={**_CCM_CONFIG, "timezone": "UTC"},
        client=UrllibCcmClient(token="test-ccm-token", opener=opener),
    )
    assert result.ok is True
    req = opener.requests[0]
    assert req.get_method() == "PATCH"
    assert req.full_url == API_ROOT + "/api/v1/deployments/dep-9"
    body = json.loads(req.data.decode("utf-8"))
    assert body["operation_hours"] == "manual"
    assert body["timezone"] == "UTC"


def test_ccm_validate_rejects_illegal_derived_name(tmp_path):
    from spa.providers.ccm import validate_ccm

    env = tmp_path / "lab"
    env.mkdir()
    paths = _ccm_paths(
        env,
        _CCM_MIN + "splunk_hosts:\n  - name: idx1\n    roles: [indexer]\n",
    )
    result = validate_ccm(paths, _CCM_CONFIG)
    assert result.ok is False
    assert result.code == 2
    assert "lab" in (result.error or "")
    assert "ccm.name" in (result.error or "")
    assert "idx1-lab" not in (result.error or "")


def test_ccm_validate_rejects_mixed_external_hosts(tmp_path):
    from spa.providers.ccm import validate_ccm

    paths = _ccm_paths(
        tmp_path,
        _CCM_MIN
        + "splunk_hosts:\n"
        + "  - name: idx1\n"
        + "    roles: [indexer]\n"
        + "  - name: byo1\n"
        + "    roles: [search_head]\n"
        + "    external:\n",
    )
    result = validate_ccm(paths, _CCM_CONFIG)
    assert result.ok is False
    assert result.code == 2
    assert "cannot mix external hosts" in (result.error or "")


def test_ccm_validate_fails_when_host_count_exceeds_50(tmp_path):
    from spa.providers.ccm import validate_ccm

    paths = _ccm_paths(
        tmp_path,
        _CCM_MIN
        + "splunk_hosts:\n"
        + "  - iter:\n"
        + "      prefix: h\n"
        + '      numbers: "01..51"\n'
        + "    roles: [indexer]\n",
    )
    result = validate_ccm(paths, _CCM_CONFIG)
    assert result.ok is False
    assert "51" in (result.error or "")
    assert "50" in (result.error or "")


def test_ccm_validate_fails_when_private_key_file_is_missing(tmp_path):
    from spa.providers.ccm import validate_ccm

    missing = tmp_path / "no-such-key.pem"
    paths = _ccm_paths(
        tmp_path,
        _CCM_MIN + "splunk_hosts:\n  - name: idx1\n    roles: [indexer]\n",
    )
    result = validate_ccm(
        paths,
        {**_CCM_CONFIG, "ssh_private_key_file": str(missing)},
    )
    assert result.ok is False
    assert "ssh_private_key_file" in (result.error or "")


def test_ccm_validate_account_cap_and_key_name_when_token_set(tmp_path):
    from spa.providers.ccm import UrllibCcmClient, validate_ccm

    key = tmp_path / "CCM-Key.pem"
    key.write_text("not-a-real-key\n", encoding="utf-8")
    paths = _ccm_paths(
        tmp_path,
        _CCM_MIN + "splunk_hosts:\n  - name: idx1\n    roles: [indexer]\n",
    )
    deployments = [
        {
            "deployment_id": "other",
            "instances_data": [{"instance_id": "i-%s" % i} for i in range(100)],
        }
    ]
    keys = [{"pub_key_name": "other-key", "fingerprint": "SHA256:ffff"}]
    opener = ScriptedOpener(
        [
            (200, deployments),
            (200, keys),
        ]
    )
    result = validate_ccm(
        paths,
        {
            **_CCM_CONFIG,
            "ssh_private_key_file": str(key),
            "key_name": "CCM-Key",
        },
        client=UrllibCcmClient(token="test-ccm-token", opener=opener),
    )
    assert result.ok is False
    text = result.error or ""
    assert "100" in text or "101" in text
    assert "CCM-Key" in text or "key_name" in text


def test_ccm_validate_account_cap_excludes_this_env_deployment(tmp_path):
    from spa.providers.ccm import UrllibCcmClient, validate_ccm

    paths, config = _validate_cap_env(tmp_path, 40, deployment_id="dep-own")
    deployments = [
        {
            "deployment_id": "other",
            "instances_data": [
                {"instance_id": "i-o-%s" % i, "state": "running"} for i in range(30)
            ],
        },
        {
            "deployment_id": "dep-own",
            "instances_data": [
                {"instance_id": "i-m-%s" % i, "state": "running"} for i in range(40)
            ],
        },
    ]
    opener = ScriptedOpener(
        [
            (200, deployments),
            (200, [{"pub_key_name": "CCM-Key"}]),
        ]
    )
    result = validate_ccm(
        paths,
        config,
        client=UrllibCcmClient(token="test-ccm-token", opener=opener),
    )
    assert result.ok is True


def test_ccm_validate_account_cap_skips_terminated_instances(tmp_path):
    from spa.providers.ccm import UrllibCcmClient, validate_ccm

    paths, config = _validate_cap_env(tmp_path, 40)
    deployments = [
        {
            "deployment_id": "gone",
            "instances_data": [
                {"instance_id": "i-t-%s" % i, "state": "terminated"} for i in range(50)
            ]
            + [
                {"instance_id": "i-s-%s" % i, "state": "shutting-down"}
                for i in range(20)
            ],
        },
        {
            "deployment_id": "live",
            "instances_data": [
                {"instance_id": "i-r-%s" % i, "state": "running"} for i in range(30)
            ],
        },
    ]
    opener = ScriptedOpener(
        [
            (200, deployments),
            (200, [{"pub_key_name": "CCM-Key"}]),
        ]
    )
    result = validate_ccm(
        paths,
        config,
        client=UrllibCcmClient(token="test-ccm-token", opener=opener),
    )
    assert result.ok is True


def test_ccm_validate_account_cap_fails_when_other_instances_plus_hosts_exceed_100(
    tmp_path,
):
    from spa.providers.ccm import UrllibCcmClient, validate_ccm

    paths, config = _validate_cap_env(tmp_path, 40, deployment_id="dep-own")
    deployments = [
        {
            "deployment_id": "other",
            "instances_data": [
                {"instance_id": "i-o-%s" % i, "state": "running"} for i in range(70)
            ],
        },
        {
            "deployment_id": "dep-own",
            "instances_data": [
                {"instance_id": "i-m-%s" % i, "state": "running"} for i in range(40)
            ],
        },
    ]
    opener = ScriptedOpener(
        [
            (200, deployments),
            (200, [{"pub_key_name": "CCM-Key"}]),
        ]
    )
    result = validate_ccm(
        paths,
        config,
        client=UrllibCcmClient(token="test-ccm-token", opener=opener),
    )
    assert result.ok is False
    text = result.error or ""
    assert "40" in text
    assert "70" in text
    assert "100" in text


def test_ccm_operating_systems_human_text_is_one_row_per_item():
    from spa.providers.ccm import UrllibCcmClient, execute, format_ccm_text

    opener = FakeOpener(
        status=200,
        body=json.dumps(["ubuntu_22.04", "rhel_9"]).encode("utf-8"),
    )
    result = execute(
        action="operating-systems",
        subaction="list",
        client=UrllibCcmClient(token="test-ccm-token", opener=opener),
    )
    assert result.ok is True
    text = format_ccm_text(result.data)
    assert text == "ubuntu_22.04\nrhel_9\n"
    payload = result.to_dict()
    assert payload["ok"] is True
    assert payload["schema_version"] == 1
    assert [row["name"] for row in payload["data"]["items"]] == ["ubuntu_22.04", "rhel_9"]


def test_ccm_check_auth_failure_agent_envelope_omits_data(monkeypatch):
    monkeypatch.delenv("CCM_TOKEN", raising=False)
    from spa.providers.ccm import execute

    result = execute(action="check-auth")
    payload = result.to_dict()
    assert payload["ok"] is False
    assert payload["schema_version"] == 1
    assert "data" not in payload
    assert "CCM_TOKEN is not set" in payload["error"]


def test_ccm_ssh_keys_human_text_omits_public_key_material():
    from spa.providers.ccm import format_ccm_text

    text = format_ccm_text(
        {
            "items": [
                {
                    "name": "CCM-Key",
                    "fingerprint": "SHA256:abcd",
                    "local_private_key": "yes",
                }
            ]
        }
    )
    assert "CCM-Key" in text
    assert "SHA256:abcd" in text
    assert "yes" in text
    assert "public_key" not in text
    assert "ssh-rsa" not in text


def test_ccm_ttl_extend_rejects_days_outside_1_to_30():
    from spa.providers.ccm import execute

    result = execute(action="ttl", subaction="extend", days=31, confirm=True)
    assert result.ok is False
    assert result.code == 2
    assert "30" in (result.error or "")


def test_ccm_ttl_extend_rejects_bad_days_before_confirm():
    from spa.providers.ccm import execute

    result = execute(action="ttl", subaction="extend", days=0, confirm=False, agent=False)
    assert result.ok is False
    assert result.code == 2
    assert "--days" in (result.error or "")
    assert "-y/--yes" not in (result.error or "")
    missing = execute(
        action="ttl", subaction="extend", days=None, confirm=False, agent=False
    )
    assert missing.ok is False
    assert missing.code == 2
    assert "--days" in (missing.error or "")
    assert "-y/--yes" not in (missing.error or "")


def test_ccm_ttl_extend_fails_when_not_provisioned(tmp_path):
    from spa.providers.ccm import UrllibCcmClient, execute

    env = tmp_path / "mylab"
    env.mkdir()
    paths = _ccm_paths(
        env,
        _CCM_MIN + "splunk_hosts:\n  - name: idx1\n    roles: [indexer]\n",
    )
    opener = FakeOpener(status=200, body=b"{}")
    result = execute(
        action="ttl",
        subaction="extend",
        days=7,
        confirm=True,
        paths=paths,
        config=_CCM_CONFIG,
        client=UrllibCcmClient(token="test-ccm-token", opener=opener),
    )
    assert result.ok is False
    assert opener.requests == []
    assert "state" in (result.error or "").lower() or "provision" in (result.error or "").lower()


def test_validate_env_fails_when_ccm_host_count_exceeds_50(tmp_path):
    from spa.validate import validate_env

    paths = _ccm_paths(
        tmp_path,
        _CCM_MIN
        + "splunk_hosts:\n"
        + "  - iter:\n"
        + "      prefix: h\n"
        + '      numbers: "01..51"\n'
        + "    roles: [indexer]\n",
    )
    result = validate_env(paths)
    assert result.ok is False
    assert "51" in (result.error or "")
    assert "50" in (result.error or "")
