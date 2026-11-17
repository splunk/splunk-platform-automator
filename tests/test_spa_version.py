"""Local spa version and install_kind classification (issue #172 slice 1)."""

import json
import re
import sys
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
