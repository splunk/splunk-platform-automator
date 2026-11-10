"""CCM HTTP client tests (mocked HTTP; no live CCM)."""

from __future__ import annotations

import sys
from typing import List

import pytest

from spa_testutil import LIB

pytestmark = [pytest.mark.local, pytest.mark.cli]

sys.path.insert(0, str(LIB))


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
