"""Local spa version, install_kind, GitHub check, and prefix self-update (issue #172)."""

import json
import os
import re
import shutil
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
OFFLINE_PHRASES = ("offline", "rate limit", "spa version check")


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


def test_check_outdated_via_api(tmp_path, monkeypatch):
    from spa.version import check_version

    home = _check_home(tmp_path)
    urlopen = _fake_urlopen({"tag_name": "v2.6.0", "html_url": LATEST_URL})

    def boom_run(argv, **_kwargs):
        raise AssertionError("gh must not run: %s" % argv)

    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.setattr("spa.version.shutil.which", lambda name: "/usr/bin/gh" if name == "gh" else None)
    monkeypatch.setattr("spa.version.subprocess.run", boom_run)
    monkeypatch.setattr("spa.version.urllib.request.urlopen", urlopen)
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
    assert len(urlopen.requests) == 1
    assert _auth_header(urlopen.requests[0]) is None


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
    for req in urlopen.requests:
        assert req.full_url.startswith("https://api.github.com/")
    assert SECRET_TOKEN in (_auth_header(urlopen.requests[0]) or "")


def _auth_header(req):
    return (
        req.get_header("Authorization")
        or req.headers.get("Authorization")
        or getattr(req, "unredirected_hdrs", {}).get("Authorization")
    )


def test_check_anonymous_without_gh_or_token(tmp_path, monkeypatch):
    from spa.version import check_version

    home = _check_home(tmp_path)
    urlopen = _fake_urlopen({"tag_name": "v2.6.0", "html_url": LATEST_URL})
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.setattr("spa.version.shutil.which", lambda name: None)
    monkeypatch.setattr("spa.version.urllib.request.urlopen", urlopen)
    result = check_version(home)
    assert result.ok is True, result.error
    assert result.data["latest"] == "2.6.0"
    assert result.data["outdated"] is True
    assert len(urlopen.requests) == 1
    req = urlopen.requests[0]
    assert req.full_url == (
        "https://api.github.com/repos/splunk/splunk-platform-automator/releases/latest"
    )
    assert _auth_header(req) is None


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


@pytest.mark.parametrize("token", [SECRET_TOKEN, None])
def test_check_offline_names_retry_and_hides_token(tmp_path, monkeypatch, token):
    from spa.version import check_version

    home = _check_home(tmp_path)
    if token:
        monkeypatch.setenv("GITHUB_TOKEN", token)
    else:
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)
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
    for phrase in OFFLINE_PHRASES:
        assert phrase in error
    assert "gh auth login" not in error
    assert SECRET_TOKEN not in error


def test_check_ignores_gh_even_when_authenticated(tmp_path, monkeypatch):
    from spa.version import fetch_latest_release

    urlopen = _fake_urlopen({"tag_name": "v2.6.0", "html_url": LATEST_URL})

    def boom_run(argv, **_kwargs):
        raise AssertionError("gh must not run: %s" % argv)

    monkeypatch.setenv("GITHUB_TOKEN", SECRET_TOKEN)
    monkeypatch.setattr("spa.version.shutil.which", lambda name: "/usr/bin/gh" if name == "gh" else None)
    monkeypatch.setattr("spa.version.subprocess.run", boom_run)
    monkeypatch.setattr("spa.version.urllib.request.urlopen", urlopen)
    release = fetch_latest_release()
    assert release["tag"] == "v2.6.0"
    assert SECRET_TOKEN in (_auth_header(urlopen.requests[0]) or "")


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


def test_human_check_offline_exit_1(monkeypatch):
    from spa.version import VersionError, offline_error

    monkeypatch.setenv("GITHUB_TOKEN", SECRET_TOKEN)

    def boom(**_kwargs):
        raise VersionError(offline_error("splunk/splunk-platform-automator"))

    monkeypatch.setattr("spa.version.fetch_latest_release", boom)
    result = run_spa_inprocess(["--no-agent", "version", "check"])
    assert result.returncode == 1
    combined = result.stdout + result.stderr
    for phrase in OFFLINE_PHRASES:
        assert phrase in result.stderr
    assert SECRET_TOKEN not in combined
    agent = run_spa_inprocess(["--agent", "version", "check"])
    assert agent.returncode == 1
    assert agent.stderr == ""
    payload = json.loads(agent.stdout)
    assert payload["ok"] is False
    assert "data" not in payload
    for phrase in OFFLINE_PHRASES:
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


CLONE_REFUSE = ("git pull", "spa venv upgrade --shared --yes", "rebuild", "spa skills update")


def _prefix_home(tmp_path, *, version="2.5.2", install_sh="#!/bin/sh\nexit 0\n"):
    home = _checkout(tmp_path, "prefix")
    home.joinpath("VERSION").write_text(version + "\n")
    (home / "install.sh").write_text(install_sh)
    (home / "install.sh").chmod(0o755)
    wrapper = tmp_path / "local" / "bin" / "spa"
    wrapper.parent.mkdir(parents=True)
    _write_install_wrapper(wrapper, home)
    return home, wrapper


def _skill_package(root: Path, name: str, body: str) -> Path:
    dest = root / name
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "SKILL.md").write_text("---\nname: %s\n---\n%s\n" % (name, body), encoding="utf-8")
    return dest


def _write_skills_yml(path: Path, copies) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["# SPA skill copies. Not secrets.", "copies:"]
    for item in copies:
        lines.append("  - %s" % item)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _recording_runner(calls, home: Path, *, version="3.1.0", skill_body=None):
    def runner(argv):
        calls.append(list(argv))
        (home / "VERSION").write_text(version + "\n")
        if skill_body is not None:
            _skill_package(home / "skills" / "spa", "spa", skill_body)
        return 0, ""

    return runner


def test_self_update_prefix_invokes_runner_with_force_prefix_bindir(tmp_path):
    from spa.version import self_update

    home, wrapper = _prefix_home(tmp_path)
    env_dir = tmp_path / "env"
    env_dir.mkdir()
    config_dir = tmp_path / "xdg" / "spa"
    config_dir.mkdir(parents=True)
    (config_dir / "keep-me").write_text("ok\n")
    calls = []
    result = self_update(
        home,
        spa_bin=str(wrapper),
        confirm=True,
        runner=_recording_runner(calls, home),
        config_dir=config_dir,
    )
    assert result.ok is True
    assert result.code == 0
    data = result.data
    assert data["previous"] == "2.5.2"
    assert data["version"] == "3.1.0"
    assert data["install_kind"] == "prefix"
    assert data["spa_home"] == str(home.resolve())
    assert calls
    argv = calls[0]
    assert "--force" in argv
    assert argv[argv.index("--prefix") + 1] == str(home.resolve())
    assert argv[argv.index("--bindir") + 1] == str(wrapper.parent)
    assert str(env_dir) not in argv
    assert str(config_dir) not in argv
    assert str(config_dir.parent) not in argv
    assert (config_dir / "keep-me").is_file()


def test_self_update_passes_wrapper_spa_home_unresolved_as_prefix(tmp_path):
    from spa.version import self_update

    real = tmp_path / "real-share"
    real.mkdir()
    link = tmp_path / "share"
    link.symlink_to(real, target_is_directory=True)
    home, _ = _prefix_home(real)
    linked_home = link / home.name
    wrapper = tmp_path / "bin" / "spa"
    wrapper.parent.mkdir()
    _write_install_wrapper(wrapper, linked_home)
    calls = []
    result = self_update(
        home,
        spa_bin=str(wrapper),
        confirm=True,
        runner=_recording_runner(calls, home),
        skills_update=lambda **_kwargs: {"platforms": []},
    )
    assert result.ok is True, result.error
    argv = calls[0]
    assert argv[argv.index("--prefix") + 1] == str(linked_home)
    assert result.data["install_kind"] == "prefix"


def test_self_update_refreshes_recorded_skills_from_new_tree(tmp_path):
    from spa.version import self_update

    home, wrapper = _prefix_home(tmp_path)
    source = home / "skills" / "spa"
    _skill_package(source, "spa", "old")
    dest = tmp_path / "home" / ".cursor" / "skills" / "spa"
    _skill_package(dest.parent, "spa", "old")
    config_dir = tmp_path / "xdg" / "spa"
    _write_skills_yml(config_dir / "skills.yml", [str(dest)])
    calls = []
    result = self_update(
        home,
        spa_bin=str(wrapper),
        confirm=True,
        runner=_recording_runner(calls, home, skill_body="new-from-release"),
        config_dir=config_dir,
        home=tmp_path / "home",
    )
    assert result.ok is True
    assert calls
    assert "new-from-release" in (dest / "SKILL.md").read_text(encoding="utf-8")
    assert (config_dir / "skills.yml").is_file()
    skills = result.data["skills"]
    assert "spa" in skills["updated"]
    assert "cursor" in skills["platforms"]
    assert "error" not in skills
    next_commands = [item["command"] for item in result.data["next"]]
    assert "spa doctor" in next_commands
    assert "spa skills update" not in next_commands


def test_self_update_non_tty_requires_yes(tmp_path, monkeypatch):
    from spa.version import self_update

    home, wrapper = _prefix_home(tmp_path)
    calls = []
    monkeypatch.setattr("sys.stdin.isatty", lambda: False)
    result = self_update(
        home,
        spa_bin=str(wrapper),
        confirm=False,
        agent=False,
        runner=_recording_runner(calls, home),
    )
    assert result.ok is False
    assert result.code == 2
    assert "-y/--yes" in (result.error or "")
    assert "agent mode" not in (result.error or "")
    assert not calls


def test_self_update_agent_requires_yes(tmp_path):
    from spa.version import self_update

    home, wrapper = _prefix_home(tmp_path)
    calls = []
    result = self_update(
        home,
        spa_bin=str(wrapper),
        confirm=False,
        agent=True,
        runner=_recording_runner(calls, home),
    )
    assert result.ok is False
    assert result.code == 1
    assert "-y/--yes" in (result.error or "")
    assert not calls


def test_self_update_refuses_clone(tmp_path):
    from spa.version import self_update

    home = _check_home(tmp_path)
    calls = []
    result = self_update(
        home,
        confirm=True,
        runner=_recording_runner(calls, home),
    )
    assert result.ok is False
    assert result.code == 1
    assert not calls
    error = result.error or ""
    for phrase in CLONE_REFUSE:
        assert phrase in error, phrase


def test_self_update_refuses_symlink_into_checkout(tmp_path):
    from spa.version import self_update

    home = _check_home(tmp_path)
    bindir = tmp_path / "local" / "bin"
    bindir.mkdir(parents=True)
    link = bindir / "spa"
    link.symlink_to(home / "bin" / "spa")
    calls = []
    result = self_update(
        home,
        spa_bin=str(link),
        confirm=True,
        runner=_recording_runner(calls, home),
    )
    assert result.ok is False
    assert result.code == 1
    assert not calls
    error = result.error or ""
    for phrase in CLONE_REFUSE:
        assert phrase in error, phrase


def test_self_update_refuses_hardlink_into_checkout(tmp_path):
    from spa.version import self_update

    home = _check_home(tmp_path)
    bindir = tmp_path / "local" / "bin"
    bindir.mkdir(parents=True)
    hard = bindir / "spa"
    os.link(home / "bin" / "spa", hard)
    calls = []
    result = self_update(
        home,
        spa_bin=str(hard),
        confirm=True,
        runner=_recording_runner(calls, home),
    )
    assert result.ok is False
    assert result.code == 1
    assert not calls
    error = result.error or ""
    for phrase in CLONE_REFUSE:
        assert phrase in error, phrase


def test_self_update_refuses_unknown(tmp_path):
    from spa.version import self_update

    home = _checkout(tmp_path, "extract")
    calls = []
    result = self_update(
        home,
        spa_bin=str(home / "bin" / "spa"),
        confirm=True,
        runner=_recording_runner(calls, home),
    )
    assert result.ok is False
    assert result.code == 1
    assert not calls
    assert "spa doctor" in (result.error or "")


def test_self_update_forwards_version_flag(tmp_path):
    from spa.version import self_update

    home, wrapper = _prefix_home(tmp_path)
    calls = []
    result = self_update(
        home,
        spa_bin=str(wrapper),
        version="3.1.0",
        confirm=True,
        runner=_recording_runner(calls, home, version="3.1.0"),
    )
    assert result.ok is True
    argv = calls[0]
    assert argv[argv.index("--version") + 1] == "3.1.0"
    assert argv.count("3.1.0") == 1
    assert "--version" in argv
    assert argv[argv.index("--force") + 1] != "3.1.0"


def test_self_update_skills_error_keeps_prefix_ok(tmp_path):
    from spa.skills import SkillsError
    from spa.version import self_update

    home, wrapper = _prefix_home(tmp_path)
    calls = []

    def boom(**_kwargs):
        raise SkillsError("cannot refresh recorded skills", code=1)

    result = self_update(
        home,
        spa_bin=str(wrapper),
        confirm=True,
        runner=_recording_runner(calls, home),
        skills_update=boom,
    )
    assert result.ok is True
    assert calls
    assert result.data["version"] == "3.1.0"
    assert result.data["previous"] == "2.5.2"
    assert result.data["skills"]["error"] == "cannot refresh recorded skills"
    next_commands = [item["command"] for item in result.data["next"]]
    assert "spa skills update" in next_commands


def test_self_update_empty_skills_names_install_and_doctor(tmp_path):
    from spa.version import self_update

    home, wrapper = _prefix_home(tmp_path)
    config_dir = tmp_path / "xdg" / "spa"
    config_dir.mkdir(parents=True)
    result = self_update(
        home,
        spa_bin=str(wrapper),
        confirm=True,
        runner=_recording_runner([], home),
        config_dir=config_dir,
        home=tmp_path / "home",
    )
    assert result.ok is True
    next_commands = [item["command"] for item in result.data["next"]]
    assert "spa skills install" in next_commands
    assert "spa doctor" in next_commands


BOOTSTRAP = "releases/latest/download/install.sh | sh -s -- --force"


def test_self_update_runs_a_temp_copy_of_prefix_install_sh(tmp_path):
    from spa.version import self_update

    home, wrapper = _prefix_home(tmp_path, install_sh="#!/bin/sh\n# prefix copy\n")
    seen = {}

    def runner(argv):
        script = Path(argv[0])
        seen["script"] = script
        seen["text"] = script.read_text()
        (home / "VERSION").write_text("3.1.0\n")
        return 0, ""

    result = self_update(home, spa_bin=str(wrapper), confirm=True, runner=runner)
    assert result.ok is True, result.error
    script = seen["script"]
    assert script.name == "install.sh"
    assert home.resolve() not in script.resolve().parents
    assert seen["text"] == "#!/bin/sh\n# prefix copy\n"
    assert not script.parent.exists()


def test_self_update_without_prefix_install_sh_names_bootstrap(tmp_path):
    from spa.version import self_update

    home, wrapper = _prefix_home(tmp_path)
    (home / "install.sh").unlink()
    calls = []
    result = self_update(
        home, spa_bin=str(wrapper), confirm=True, runner=_recording_runner(calls, home)
    )
    assert result.ok is False
    assert result.code == 1
    assert not calls
    assert "install.sh" in (result.error or "")
    assert "curl -fsSL" in (result.error or "")
    assert BOOTSTRAP in (result.error or "")


def test_self_update_forwards_from_as_absolute_path(tmp_path, monkeypatch):
    from spa.version import self_update

    home, wrapper = _prefix_home(tmp_path)
    monkeypatch.chdir(tmp_path)
    calls = []
    result = self_update(
        home,
        spa_bin=str(wrapper),
        confirm=True,
        from_file="./new.tar.gz",
        runner=_recording_runner(calls, home),
    )
    assert result.ok is True, result.error
    argv = calls[0]
    assert argv[argv.index("--from") + 1] == str(tmp_path / "new.tar.gz")


@pytest.mark.parametrize(
    "folder,flag",
    [
        ("Software", "--software-dir"),
        ("Baseconfigs", "--baseconfig-dir"),
        ("Apps", "--apps-dir"),
        ("Envs", "--env-dir"),
    ],
)
def test_self_update_refuses_user_content_in_prefix(tmp_path, folder, flag):
    from spa.version import self_update

    home, wrapper = _prefix_home(tmp_path)
    (home / folder).mkdir()
    calls = []
    result = self_update(
        home,
        spa_bin=str(wrapper),
        confirm=False,
        agent=True,
        runner=_recording_runner(calls, home),
    )
    assert result.ok is False
    assert result.code == 1
    assert not calls
    error = result.error or ""
    assert str(home / folder) in error
    assert "spa environment set %s DIR" % flag in error
    assert "-y/--yes" not in error


def test_self_update_agent_failure_reports_redacted_install_tail(tmp_path):
    from spa.version import self_update

    lines = "".join("echo 'line %02d'\n" % n for n in range(1, 31))
    install_sh = (
        "#!/bin/sh\n" + lines + "echo 'GITHUB_TOKEN=ghp_fakeSecret123'\n"
        "echo 'ERROR: could not reach GitHub releases' >&2\nexit 3\n"
    )
    home, wrapper = _prefix_home(tmp_path, install_sh=install_sh)
    result = self_update(home, spa_bin=str(wrapper), confirm=True, agent=True)
    assert result.ok is False
    assert result.code == 1
    error = result.error or ""
    assert "exit 3" in error
    assert "ERROR: could not reach GitHub releases" in error
    assert "line 30" in error
    assert "line 05" not in error
    assert "ghp_fakeSecret123" not in json.dumps(result.to_dict())
    assert BOOTSTRAP not in error


def test_self_update_failure_with_missing_bin_spa_names_bootstrap(tmp_path):
    from spa.version import self_update

    home, wrapper = _prefix_home(tmp_path)

    def runner(_argv):
        (home / "bin" / "spa").unlink()
        return 1, ""

    result = self_update(home, spa_bin=str(wrapper), confirm=True, agent=True, runner=runner)
    assert result.ok is False
    assert result.code == 1
    assert BOOTSTRAP in (result.error or "")


_HARNESS = r"""
import shutil, sys
from pathlib import Path

prefix, wrapper, new_tree, mode, agent, cfg, home = sys.argv[1:8]
sys.path.insert(0, str(Path(prefix) / "lib"))
from spa import cli
from spa.version import self_update

def runner(_argv):
    shutil.rmtree(prefix)
    if mode == "fail":
        return 1, "ERROR: boom\n"
    shutil.copytree(new_tree, prefix, symlinks=True)
    return 0, ""

as_agent = agent == "1"
result = self_update(
    Path(prefix),
    spa_bin=wrapper,
    confirm=True,
    agent=as_agent,
    runner=runner,
    config_dir=Path(cfg),
    home=Path(home),
)
sys.exit(cli._print_version(result, as_agent))
"""


def _copied_lib_prefix(root: Path, version: str) -> Path:
    root.mkdir(parents=True)
    shutil.copytree(
        LIB, root / "lib", ignore=shutil.ignore_patterns("__pycache__", "*.pyc")
    )
    (root / "ansible").symlink_to(PROJECT_ROOT / "ansible")
    (root / "bin").mkdir()
    shutil.copy2(PROJECT_ROOT / "bin" / "spa", root / "bin" / "spa")
    (root / "VERSION").write_text(version + "\n")
    (root / "install.sh").write_text("#!/bin/sh\nexit 0\n")
    (root / "install.sh").chmod(0o755)
    return root


def _run_harness(tmp_path, mode, agent):
    prefix = _copied_lib_prefix(tmp_path / "prefix", "2.5.2")
    new_tree = _copied_lib_prefix(tmp_path / "new-tree", "9.9.9")
    for name in ("next_steps.py", "runlog.py"):
        (new_tree / "lib" / "spa" / name).write_text(
            "raise RuntimeError('imported from the new tree')\n"
        )
    wrapper = tmp_path / "local" / "bin" / "spa"
    wrapper.parent.mkdir(parents=True)
    _write_install_wrapper(wrapper, prefix)
    (tmp_path / "xdg").mkdir()
    env = spa_env({"PYTHONDONTWRITEBYTECODE": "1", "HOME": str(tmp_path / "home")})
    env.pop("PYTHONPATH", None)
    return subprocess.run(
        [
            sys.executable,
            "-c",
            _HARNESS,
            str(prefix),
            str(wrapper),
            str(new_tree),
            mode,
            "1" if agent else "0",
            str(tmp_path / "xdg"),
            str(tmp_path / "home"),
        ],
        capture_output=True,
        text=True,
        env=env,
        cwd=tmp_path,
    )


@pytest.mark.parametrize("agent", [True, False])
def test_self_update_failure_after_tree_deleted_still_renders(tmp_path, agent):
    result = _run_harness(tmp_path, "fail", agent)
    assert result.returncode == 1, result.stdout + result.stderr
    assert "Traceback" not in result.stderr
    if agent:
        payload = json.loads(result.stdout)
        assert payload["ok"] is False
        assert "ERROR: boom" in payload["error"]
    else:
        assert "install.sh --force failed" in result.stderr


@pytest.mark.parametrize("agent", [True, False])
def test_self_update_success_does_not_import_from_new_tree(tmp_path, agent):
    result = _run_harness(tmp_path, "ok", agent)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Traceback" not in result.stderr
    if agent:
        payload = json.loads(result.stdout)
        assert payload["ok"] is True
        assert payload["data"]["version"] == "9.9.9"
    else:
        assert result.stdout == "spa 9.9.9 (was 2.5.2)\n"


def test_schema_includes_self_update():
    from spa.agent import COMMAND_SCHEMA

    by_name = {row["name"]: row for row in COMMAND_SCHEMA["commands"]}
    parent = by_name["self"]
    assert parent["example"] == "spa self update --yes"
    update = by_name["self update"]
    assert update["requires_confirmation"] is True
    flags = {flag["long"]: flag for flag in update["flags"]}
    assert "--yes" in flags
    assert flags["--version"]["takes_value"] is True
    assert flags["--from"]["takes_value"] is True
    help_text = run_spa_inprocess(["--no-agent", "self", "update", "--help"])
    assert help_text.returncode == 0, help_text.stderr
    assert "usage: spa self update" in help_text.stdout
    assert "--version" in help_text.stdout
    assert "--from FILE" in help_text.stdout
    assert "--yes" in help_text.stdout
    agent_help = run_spa(["--agent", "self", "update", "--help"])
    assert agent_help.returncode == 0, agent_help.stderr
    payload = json.loads(agent_help.stdout)
    assert payload["data"]["name"] == "self update"


def test_bare_self_names_self_update():
    human = run_spa_inprocess(["--no-agent", "self"])
    assert human.returncode == 2
    assert "spa self update" in human.stderr
    agent = run_spa_inprocess(["--agent", "self"])
    assert agent.returncode == 2
    assert agent.stderr == ""
    payload = json.loads(agent.stdout)
    assert payload["ok"] is False
    assert "spa self update" in payload["error"]


def test_cli_self_update_forwards_version_and_yes(monkeypatch):
    from spa.api import CommandResult

    captured = {}

    def fake_self_update(spa_home, **kwargs):
        captured["spa_home"] = spa_home
        captured.update(kwargs)
        return CommandResult(
            ok=True,
            data={
                "version": "3.1.0",
                "previous": "2.5.2",
                "spa_home": str(spa_home),
                "install_kind": "prefix",
                "skills": {"updated": [], "unchanged": [], "platforms": []},
            },
        )

    monkeypatch.setattr("spa.version.self_update", fake_self_update)
    result = run_spa_inprocess(["--no-agent", "self", "update", "--version", "3.1.0", "--yes"])
    assert result.returncode == 0, result.stderr
    assert captured.get("confirm") is True
    assert captured.get("version") == "3.1.0"
    assert result.stdout == "spa 3.1.0 (was 2.5.2)\n"

    captured.clear()
    result = run_spa_inprocess(
        ["--no-agent", "self", "update", "--from", "./new.tar.gz", "--yes"]
    )
    assert result.returncode == 0, result.stderr
    assert captured.get("from_file") == "./new.tar.gz"


def test_default_install_runner_hides_output_in_agent_mode(tmp_path, capfd):
    from spa.version import _install_runner

    script = tmp_path / "install.sh"
    script.write_text("#!/bin/sh\necho leaked-out\necho leaked-err >&2\n")
    script.chmod(0o755)
    rc, output = _install_runner([str(script)], agent=True)
    assert rc == 0
    captured = capfd.readouterr()
    assert "leaked" not in captured.out + captured.err
    assert "leaked-out" in output
    assert "leaked-err" in output


def test_default_install_runner_streams_to_stderr_for_humans(tmp_path, capfd):
    from spa.version import _install_runner

    script = tmp_path / "install.sh"
    script.write_text("#!/bin/sh\necho leaked-out\necho leaked-err >&2\n")
    script.chmod(0o755)
    rc, output = _install_runner([str(script)], agent=False)
    assert rc == 0
    assert output == ""
    captured = capfd.readouterr()
    assert captured.out == ""
    assert "leaked-out" in captured.err
    assert "leaked-err" in captured.err


def test_default_install_runner_does_not_pipe_for_humans(tmp_path, monkeypatch):
    from spa import version as version_mod

    seen = {}

    def fake_run(argv, **kwargs):
        seen.update(kwargs)
        return subprocess.CompletedProcess(argv, 0)

    monkeypatch.setattr(version_mod.subprocess, "run", fake_run)
    version_mod._install_runner(["install.sh"], agent=False)
    assert not seen.get("capture_output")
    assert seen.get("stdout") is not subprocess.PIPE
    assert seen.get("stderr") is not subprocess.PIPE


def test_self_update_skips_env_dir_and_venv_gates(tmp_path, monkeypatch):
    from spa.api import CommandResult

    monkeypatch.setattr(
        "spa.version.self_update",
        lambda spa_home, **_kwargs: CommandResult(
            ok=True,
            data={
                "version": "3.1.0",
                "previous": "2.5.2",
                "spa_home": str(spa_home),
                "install_kind": "prefix",
                "skills": {"updated": [], "unchanged": [], "platforms": []},
            },
        ),
    )
    env = spa_env()
    env["PATH"] = "/usr/bin:/bin"
    result = run_spa_inprocess(["--no-agent", "self", "update", "--yes"], env=env, cwd=tmp_path)
    assert result.returncode == 0, result.stderr
    assert "spa 3.1.0 (was 2.5.2)" in result.stdout
