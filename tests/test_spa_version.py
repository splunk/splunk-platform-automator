"""Local spa version, install_kind, and GitHub version check (issue #172)."""

import json
import re
import subprocess
import sys
import urllib.error
from pathlib import Path

import pytest

from spa_testutil import LIB, PROJECT_ROOT, run_spa, run_spa_inprocess, spa_env

pytestmark = [pytest.mark.local, pytest.mark.cli]

sys.path.insert(0, str(LIB))

from spa.install_kind import classify_install_kind  # noqa: E402


def _write_install_wrapper(path: Path, prefix: Path) -> None:
    """Match install.sh write_wrapper: PATH launcher, not a symlink to bin/spa."""
    quoted = str(prefix).replace("'", "'\\''")
    path.write_text(
        (
            "#!/bin/sh\n"
            "export SPA_HOME='__PREFIX__'\n"
            'venv="$SPA_HOME/.venv/bin/python"\n'
            'if [ -x "$venv" ]; then\n'
            '    exec "$venv" "$SPA_HOME/bin/spa" "$@"\n'
            "fi\n"
            'exec "$SPA_HOME/bin/spa" "$@"\n'
        ).replace("__PREFIX__", quoted)
    )
    path.chmod(0o755)


def _checkout(tmp_path: Path, name: str = "clone") -> Path:
    home = tmp_path / name
    (home / "bin").mkdir(parents=True)
    (home / "bin" / "spa").write_text("#!/usr/bin/env python3\n" + ("x" * 9000))
    (home / "bin" / "spa").chmod(0o755)
    (home / "VERSION").write_text("2.5.2\n")
    return home


def test_git_dir_is_clone(tmp_path):
    home = _checkout(tmp_path)
    (home / ".git").mkdir()
    wrapper = tmp_path / "bin" / "spa"
    wrapper.parent.mkdir()
    _write_install_wrapper(wrapper, home)
    assert classify_install_kind(home, str(wrapper)) == "clone"


def test_git_file_worktree_is_clone(tmp_path):
    home = _checkout(tmp_path)
    (home / ".git").write_text("gitdir: /tmp/worktrees/spa\n")
    assert classify_install_kind(home, None) == "clone"


def test_installer_wrapper_without_git_is_prefix(tmp_path):
    home = _checkout(tmp_path, "prefix")
    wrapper = tmp_path / "local" / "bin" / "spa"
    wrapper.parent.mkdir(parents=True)
    _write_install_wrapper(wrapper, home)
    assert classify_install_kind(home, str(wrapper)) == "prefix"


def test_symlink_to_checkout_bin_spa_is_clone_not_prefix(tmp_path):
    home = _checkout(tmp_path)
    (home / ".git").mkdir()
    bindir = tmp_path / "local" / "bin"
    bindir.mkdir(parents=True)
    link = bindir / "spa"
    link.symlink_to(home / "bin" / "spa")
    assert classify_install_kind(home, str(link)) == "clone"


def test_symlink_into_non_git_tree_is_unknown(tmp_path):
    home = _checkout(tmp_path, "extract")
    bindir = tmp_path / "local" / "bin"
    bindir.mkdir(parents=True)
    link = bindir / "spa"
    link.symlink_to(home / "bin" / "spa")
    assert classify_install_kind(home, str(link)) == "unknown"


def _expected_version() -> str:
    return (PROJECT_ROOT / "VERSION").read_text(encoding="utf-8").strip()


def test_human_version_flag_prints_spa_version():
    result = run_spa(["--no-agent", "--version"])
    assert result.returncode == 0, result.stderr
    assert result.stdout == "spa %s\n" % _expected_version()
    assert result.stderr == ""


def test_human_version_command_prints_spa_version():
    result = run_spa(["--no-agent", "version"])
    assert result.returncode == 0, result.stderr
    assert result.stdout == "spa %s\n" % _expected_version()
    assert result.stderr == ""


def test_agent_version_envelope_has_install_kind():
    for argv in (["--agent", "version"], ["--agent", "--version"], ["--json", "version"]):
        result = run_spa(argv)
        assert result.returncode == 0, (argv, result.stderr, result.stdout)
        assert result.stderr == "", argv
        payload = json.loads(result.stdout)
        assert payload["ok"] is True
        assert payload["schema_version"] == 1
        data = payload["data"]
        assert data["version"] == _expected_version()
        assert data["spa_home"] == str(PROJECT_ROOT.resolve())
        assert data["install_kind"] == "clone"
        assert set(data) == {"version", "spa_home", "install_kind"}


def test_apps_download_version_is_not_spa_version():
    help_text = run_spa_inprocess(["--no-agent", "apps", "download", "--help"])
    assert help_text.returncode == 0, help_text.stderr
    assert "--version" in help_text.stdout
    assert "Release version" in help_text.stdout

    result = run_spa(["--no-agent", "apps", "download", "--version", "1.2.3", "833"])
    assert "spa %s" % _expected_version() not in result.stdout
    assert result.returncode != 0


def test_version_help_does_not_advertise_apps_version():
    help_text = run_spa_inprocess(["--no-agent", "version", "--help"])
    assert help_text.returncode == 0, help_text.stderr
    assert "usage: spa version" in help_text.stdout
    assert "Release version" not in help_text.stdout
    defined = set(re.findall(r"(?m)^\s+(?:-[A-Za-z],\s+)?(--[A-Za-z0-9-]+)", help_text.stdout))
    assert "--version" not in defined


def test_version_skips_env_dir_and_venv_gates(tmp_path):
    env = spa_env()
    env["PATH"] = "/usr/bin:/bin"
    result = run_spa(["--no-agent", "version"], env=env, cwd=tmp_path)
    assert result.returncode == 0, result.stderr
    assert result.stdout == "spa %s\n" % _expected_version()


LATEST_URL = "https://github.com/splunk/splunk-platform-automator/releases/tag/v2.6.0"
SECRET_TOKEN = "ghp_leaked_token_value_xyz"
AUTH_PHRASES = ("set --from", "gh auth login", "GITHUB_TOKEN")


def _fake_gh_run(*, auth_ok=True, tag="v2.6.0", view_rc=0):
    calls = []

    def run(argv, **kwargs):
        argv = list(argv)
        calls.append(argv)
        if argv[:4] == ["gh", "auth", "status", "-h"]:
            return subprocess.CompletedProcess(argv, 0 if auth_ok else 1, "", "")
        if argv[:3] == ["gh", "release", "view"]:
            stdout = tag + "\n" if view_rc == 0 else ""
            return subprocess.CompletedProcess(argv, view_rc, stdout, "denied")
        raise AssertionError("unexpected gh argv: %s" % argv)

    run.calls = calls
    return run


class _FakeResponse:
    def __init__(self, payload):
        self._payload = json.dumps(payload).encode("utf-8")

    def read(self):
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def _fake_urlopen(payload=None, error=None):
    requests = []

    def urlopen(req, timeout=None):
        requests.append(req)
        if error is not None:
            raise error
        return _FakeResponse(payload)

    urlopen.requests = requests
    return urlopen


def _check_home(tmp_path, *, version="2.5.2", git=True, name="clone"):
    home = _checkout(tmp_path, name)
    home.joinpath("VERSION").write_text(version + "\n")
    if git:
        (home / ".git").mkdir()
    return home


def test_check_outdated_via_gh(tmp_path, monkeypatch):
    from spa.version import check_version

    home = _check_home(tmp_path)
    runner = _fake_gh_run(tag="v2.6.0")
    monkeypatch.setattr("spa.version.shutil.which", lambda name: "/usr/bin/gh" if name == "gh" else None)
    monkeypatch.setattr("spa.version.subprocess.run", runner)
    result = check_version(home)
    assert result.ok is True
    assert result.code == 0
    data = result.data
    assert data["version"] == "2.5.2"
    assert data["latest"] == "2.6.0"
    assert data["outdated"] is True
    assert data["install_kind"] == "clone"
    assert data["release_url"] == LATEST_URL
    assert data["next"][0]["command"] == "spa self update --yes"
    assert any("release view" in " ".join(call) for call in runner.calls)


def test_check_current_via_github_token(tmp_path, monkeypatch):
    from spa.version import check_version

    home = _check_home(tmp_path, version="2.6.0", git=False, name="prefix")
    wrapper = tmp_path / "local" / "bin" / "spa"
    wrapper.parent.mkdir(parents=True)
    _write_install_wrapper(wrapper, home)
    urlopen = _fake_urlopen(
        {
            "tag_name": "v2.6.0",
            "html_url": LATEST_URL,
        }
    )
    monkeypatch.setenv("GITHUB_TOKEN", SECRET_TOKEN)
    monkeypatch.setattr("spa.version.shutil.which", lambda name: None)
    monkeypatch.setattr("spa.version.urllib.request.urlopen", urlopen)
    result = check_version(home, spa_bin=str(wrapper))
    assert result.ok is True
    assert result.code == 0
    data = result.data
    assert data["version"] == "2.6.0"
    assert data["latest"] == "2.6.0"
    assert data["outdated"] is False
    assert data["install_kind"] == "prefix"
    assert "next" not in data
    assert urlopen.requests
    req = urlopen.requests[0]
    header = (
        req.get_header("Authorization")
        or req.headers.get("Authorization")
        or getattr(req, "unredirected_hdrs", {}).get("Authorization")
    )
    assert SECRET_TOKEN in (header or "")


def test_check_clone_still_queries_github(tmp_path, monkeypatch):
    from spa.version import check_version

    home = _check_home(tmp_path)
    fetched = []

    def fetch(**_kwargs):
        fetched.append(True)
        return {"tag": "v2.6.0", "url": LATEST_URL}

    result = check_version(home, fetch=fetch)
    assert fetched == [True]
    assert result.ok is True
    assert result.data["install_kind"] == "clone"
    assert result.data["outdated"] is True


def test_check_auth_failure_names_install_sh_and_hides_token(tmp_path, monkeypatch):
    from spa.version import check_version

    home = _check_home(tmp_path)
    monkeypatch.setenv("GITHUB_TOKEN", SECRET_TOKEN)
    monkeypatch.setattr("spa.version.shutil.which", lambda name: None)
    monkeypatch.setattr(
        "spa.version.urllib.request.urlopen",
        _fake_urlopen(error=urllib.error.URLError("offline")),
    )
    result = check_version(home)
    assert result.ok is False
    assert result.code == 1
    assert result.data is None
    error = result.error or ""
    for phrase in AUTH_PHRASES:
        assert phrase in error
    assert SECRET_TOKEN not in error


def test_check_prefers_gh_over_github_token(tmp_path, monkeypatch):
    from spa.version import fetch_latest_release

    runner = _fake_gh_run(tag="v2.6.0")
    urlopen = _fake_urlopen(error=AssertionError("token path must not run when gh auth works"))
    monkeypatch.setenv("GITHUB_TOKEN", SECRET_TOKEN)
    monkeypatch.setattr("spa.version.shutil.which", lambda name: "/usr/bin/gh" if name == "gh" else None)
    monkeypatch.setattr("spa.version.subprocess.run", runner)
    monkeypatch.setattr("spa.version.urllib.request.urlopen", urlopen)
    release = fetch_latest_release()
    assert release["tag"] == "v2.6.0"
    assert not urlopen.requests


def test_human_check_outdated_prints_next_on_stderr(monkeypatch):
    monkeypatch.setattr(
        "spa.version.fetch_latest_release",
        lambda **_kwargs: {"tag": "v2.6.0", "url": LATEST_URL},
    )
    monkeypatch.setattr("spa.version.read_local_version", lambda _home: "2.5.2")
    result = run_spa_inprocess(["--no-agent", "version", "check"])
    assert result.returncode == 0, result.stderr
    assert result.stdout == "spa 2.5.2 (latest is 2.6.0)\n"
    assert "Next:" in result.stderr
    assert "spa self update --yes" in result.stderr
    assert "--agent" not in result.stderr
    assert SECRET_TOKEN not in result.stdout + result.stderr


def test_human_check_current_has_no_next(monkeypatch):
    monkeypatch.setattr(
        "spa.version.fetch_latest_release",
        lambda **_kwargs: {"tag": "v2.5.2", "url": LATEST_URL.replace("v2.6.0", "v2.5.2")},
    )
    monkeypatch.setattr("spa.version.read_local_version", lambda _home: "2.5.2")
    result = run_spa_inprocess(["--no-agent", "version", "check"])
    assert result.returncode == 0, result.stderr
    assert result.stdout == "spa 2.5.2 (up to date)\n"
    assert "Next:" not in result.stderr


def test_agent_check_envelope_includes_outdated(monkeypatch):
    monkeypatch.setattr(
        "spa.version.fetch_latest_release",
        lambda **_kwargs: {"tag": "v2.6.0", "url": LATEST_URL},
    )
    monkeypatch.setattr("spa.version.read_local_version", lambda _home: "2.5.2")
    result = run_spa_inprocess(["--agent", "version", "check"])
    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    data = payload["data"]
    assert data["outdated"] is True
    assert data["version"] == "2.5.2"
    assert data["latest"] == "2.6.0"
    assert data["release_url"] == LATEST_URL
    assert data["install_kind"] in {"clone", "prefix", "unknown"}
    assert data["next"][0]["command"] == "spa self update --yes"


def test_human_check_auth_failure_exit_1(monkeypatch):
    from spa.version import VersionError

    monkeypatch.setenv("GITHUB_TOKEN", SECRET_TOKEN)

    def boom(**_kwargs):
        raise VersionError(
            "set --from FILE, or run gh auth login / set GITHUB_TOKEN to download a release."
        )

    monkeypatch.setattr("spa.version.fetch_latest_release", boom)
    result = run_spa_inprocess(["--no-agent", "version", "check"])
    assert result.returncode == 1
    combined = result.stdout + result.stderr
    for phrase in AUTH_PHRASES:
        assert phrase in result.stderr
    assert SECRET_TOKEN not in combined
    agent = run_spa_inprocess(["--agent", "version", "check"])
    assert agent.returncode == 1
    assert agent.stderr == ""
    payload = json.loads(agent.stdout)
    assert payload["ok"] is False
    assert "data" not in payload
    for phrase in AUTH_PHRASES:
        assert phrase in payload["error"]
    assert SECRET_TOKEN not in agent.stdout


def test_version_check_skips_env_dir_and_venv_gates(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "spa.version.fetch_latest_release",
        lambda **_kwargs: {"tag": "v2.5.2", "url": LATEST_URL.replace("v2.6.0", "v2.5.2")},
    )
    env = spa_env()
    env["PATH"] = "/usr/bin:/bin"
    result = run_spa_inprocess(["--no-agent", "version", "check"], env=env, cwd=tmp_path)
    assert result.returncode == 0, result.stderr
    assert "up to date" in result.stdout


def test_schema_includes_version_check():
    from spa.agent import COMMAND_SCHEMA

    by_name = {row["name"]: row for row in COMMAND_SCHEMA["commands"]}
    assert by_name["version"]["read_only"] is True
    check = by_name["version check"]
    assert check["read_only"] is True
    assert check["example"] == "spa --agent version check"
    assert "GitHub" in check["summary"]
    help_text = run_spa_inprocess(["--no-agent", "version", "check", "--help"])
    assert help_text.returncode == 0, help_text.stderr
    assert "usage: spa version check" in help_text.stdout
    agent_help = run_spa(["--agent", "version", "check", "--help"])
    assert agent_help.returncode == 0, agent_help.stderr
    payload = json.loads(agent_help.stdout)
    assert payload["data"]["name"] == "version check"
