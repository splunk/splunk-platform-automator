"""spa skills install / remove against temp homes, never the operator IDE dirs."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from spa.skills import SkillsError, install_skills, remove_skills
from spa_testutil import run_spa, spa_env

pytestmark = [pytest.mark.local, pytest.mark.cli]

_DETECT_VARS = (
    "SPA_SKILLS_PLATFORMS",
    "CLAUDECODE",
    "CLAUDE_CODE",
    "CURSOR_AGENT",
    "CODEX",
    "OPENAI_CODEX",
    "OPENCODE",
    "AIDER",
    "CLINE",
    "WINDSURF_AGENT",
    "GITHUB_COPILOT",
    "AMAZON_Q",
    "AWS_Q_DEVELOPER",
    "GEMINI_CODE_ASSIST",
    "ANTIGRAVITY",
    "SRC_CODY",
    "PI_CODING_AGENT",
    "AGENT",
)


def _package(root: Path, name: str, body: str = "skill") -> Path:
    dest = root / name
    dest.mkdir(parents=True)
    (dest / "SKILL.md").write_text("---\nname: %s\n---\n%s\n" % (name, body), encoding="utf-8")
    return dest


def _source(tmp_path: Path) -> Path:
    source = tmp_path / "skills" / "spa"
    _package(source, "spa")
    _package(source, "spa-apps")
    return source


def _touch_bin(directory: Path, name: str) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    path.chmod(0o755)


def _install(tmp_path: Path, **kwargs):
    source = kwargs.pop("source", None) or _source(tmp_path)
    home = kwargs.pop("home", None) or (tmp_path / "home")
    home.mkdir(parents=True, exist_ok=True)
    environ = {"HOME": str(home)}
    environ.update(kwargs.pop("environ", {}))
    return install_skills(
        source=source,
        home=home,
        environ=environ,
        path_env=kwargs.pop("path_env", ""),
        config_dir=kwargs.pop("config_dir", tmp_path / "config" / "spa"),
        **kwargs,
    )


def test_install_symlinks_every_package_and_is_idempotent(tmp_path):
    source = _source(tmp_path)
    first = _install(tmp_path, source=source, platform="cursor")
    link = tmp_path / "home" / ".cursor" / "skills" / "spa"
    assert link.is_symlink()
    assert link.resolve() == (source / "spa").resolve()
    assert (tmp_path / "home" / ".cursor" / "skills" / "spa-apps").resolve() == (source / "spa-apps").resolve()
    assert first["detectedVia"] == "explicit"
    assert first["platforms"] == ["cursor"]
    second = _install(tmp_path, source=source, platform="cursor")
    assert second["installed"] == ["spa", "spa-apps"]
    assert link.is_symlink()


def test_install_replaces_spa_named_directory_and_keeps_neighbor(tmp_path):
    source = _source(tmp_path)
    skills = tmp_path / "home" / ".cursor" / "skills"
    stale = skills / "spa"
    stale.mkdir(parents=True)
    (stale / "SKILL.md").write_text("old\n", encoding="utf-8")
    neighbor = skills / "my-notes"
    neighbor.mkdir()
    (neighbor / "SKILL.md").write_text("keep\n", encoding="utf-8")
    other_link = skills / "elsewhere"
    other_link.symlink_to(neighbor)

    _install(tmp_path, source=source, platform="cursor", name="spa")

    assert (skills / "spa").is_symlink()
    assert (skills / "spa").resolve() == (source / "spa").resolve()
    assert (neighbor / "SKILL.md").read_text(encoding="utf-8") == "keep\n"
    assert other_link.is_symlink()
    assert not (skills / "spa-apps").exists()


def test_platforms_env_installs_both_and_ignores_path(tmp_path):
    bindir = tmp_path / "bin"
    _touch_bin(bindir, "windsurf")
    result = _install(
        tmp_path,
        platform=None,
        environ={"SPA_SKILLS_PLATFORMS": "cursor,claude-code"},
        path_env=str(bindir),
    )
    home = tmp_path / "home"
    assert result["detectedVia"] == "env_platforms"
    assert result["platforms"] == ["claude-code", "cursor"]
    assert (home / ".cursor" / "skills" / "spa").is_symlink()
    assert (home / ".claude" / "skills" / "spa").is_symlink()
    assert not (home / ".windsurf" / "skills").exists()


def test_explicit_platform_ignores_platforms_env(tmp_path):
    result = _install(
        tmp_path,
        platform="cursor",
        environ={"SPA_SKILLS_PLATFORMS": "claude-code"},
    )
    assert result["platforms"] == ["cursor"]
    assert result["detectedVia"] == "explicit"
    assert not (tmp_path / "home" / ".claude").exists()


def test_comma_separated_platforms_install_each(tmp_path):
    source = _source(tmp_path)
    result = _install(
        tmp_path,
        source=source,
        platform="cursor, claude",
        environ={"SPA_SKILLS_PLATFORMS": "windsurf"},
        name="spa",
    )
    assert result["detectedVia"] == "explicit"
    assert result["platforms"] == ["cursor", "claude-code"]
    home = tmp_path / "home"
    assert (home / ".cursor" / "skills" / "spa").is_symlink()
    assert (home / ".claude" / "skills" / "spa").is_symlink()
    assert not (home / ".windsurf").exists()


def test_comma_separated_unknown_names_the_token(tmp_path):
    with pytest.raises(SkillsError) as caught:
        _install(tmp_path, platform="cursor,nope")
    assert caught.value.code == 2
    assert "unknown platform: 'nope'" in str(caught.value)


def test_ambiguous_path_names_platforms(tmp_path):
    bindir = tmp_path / "bin"
    _touch_bin(bindir, "cursor")
    _touch_bin(bindir, "claude")
    with pytest.raises(SkillsError) as caught:
        _install(tmp_path, platform=None, path_env=str(bindir))
    message = str(caught.value)
    assert caught.value.code == 2
    assert "could not auto-detect" in message
    assert "spa skills install cursor" in message
    assert "spa skills install claude-code" in message
    assert "SPA_SKILLS_PLATFORMS" in message


def test_antigravity_alias_uses_gemini_config_skills(tmp_path):
    source = _source(tmp_path)
    _install(tmp_path, source=source, platform="agy", name="spa")
    link = tmp_path / "home" / ".gemini" / "config" / "skills" / "spa"
    assert link.is_symlink()
    assert link.resolve() == (source / "spa").resolve()


def test_remove_deletes_registry_name_only(tmp_path):
    source = _source(tmp_path)
    _install(tmp_path, source=source, platform="cursor")
    skills = tmp_path / "home" / ".cursor" / "skills"
    neighbor = skills / "my-notes"
    neighbor.mkdir()
    (neighbor / "SKILL.md").write_text("keep\n", encoding="utf-8")
    real = skills / "spa-create-config"
    real.mkdir()
    (real / "SKILL.md").write_text("stale\n", encoding="utf-8")

    removed = remove_skills(
        source=source,
        home=tmp_path / "home",
        platform="cursor",
        environ={"HOME": str(tmp_path / "home")},
        path_env="",
        config_dir=tmp_path / "config" / "spa",
    )
    assert "spa" in removed["removed"]
    assert "spa-apps" in removed["removed"]
    assert not (skills / "spa").exists()
    assert not (skills / "spa-apps").is_symlink()
    assert not (skills / "spa-apps").exists()
    assert (neighbor / "SKILL.md").read_text(encoding="utf-8") == "keep\n"
    assert real.is_dir() and not real.is_symlink()


def test_name_and_all_together_is_usage_error(tmp_path):
    with pytest.raises(SkillsError) as caught:
        _install(tmp_path, platform="cursor", name="spa", all_packages=True)
    assert caught.value.code == 2


def test_symlink_failure_copies_package_and_records_path(tmp_path, monkeypatch):
    source = _source(tmp_path)

    def refuse_symlink(*_args, **_kwargs):
        raise OSError("symlinks are not available")

    monkeypatch.setattr(os, "symlink", refuse_symlink)
    config = tmp_path / "config" / "spa"
    _install(tmp_path, source=source, platform="antigravity", name="spa", config_dir=config)
    dest = tmp_path / "home" / ".gemini" / "config" / "skills" / "spa"
    assert dest.is_dir()
    assert not dest.is_symlink()
    assert (dest / "SKILL.md").is_file()
    recorded = (config / "skills.yml").read_text(encoding="utf-8")
    assert str(dest) in recorded
    assert "password" not in recorded.lower()
    assert "BEGIN CERTIFICATE" not in recorded


def _cli_env(tmp_path: Path, **extra: str) -> dict:
    env = spa_env()
    for name in _DETECT_VARS:
        env.pop(name, None)
    env["HOME"] = str(tmp_path / "home")
    env["XDG_CONFIG_HOME"] = str(tmp_path / "xdg")
    env["PATH"] = "/usr/bin:/bin"
    env.update(extra)
    (tmp_path / "home").mkdir(parents=True, exist_ok=True)
    return env


def test_skills_help_lists_platforms():
    result = run_spa(["--no-agent", "sk", "--help"])
    assert result.returncode == 0, result.stderr
    for name in (
        "claude-code (claude)",
        "cursor",
        "codex",
        "opencode",
        "windsurf",
        "gemini-code (gemini)",
        "pi (pi-dev)",
        "antigravity (agy)",
        "or all",
        "cursor,claude",
    ):
        assert name in result.stdout, name


def test_cli_remove_without_yes_fails_in_agent_mode(tmp_path):
    env = _cli_env(tmp_path)
    result = run_spa(["--agent", "skills", "remove", "cursor", "--all"], env=env)
    assert result.returncode == 1, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert "data" not in payload
    assert "--yes" in payload["error"]
    assert not (tmp_path / "home" / ".cursor" / "skills").exists()


def test_cli_install_comma_separated_platforms(tmp_path):
    env = _cli_env(tmp_path)
    result = run_spa(["--agent", "skills", "install", "cursor,claude", "--name", "spa"], env=env)
    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["data"]["platforms"] == ["cursor", "claude-code"]
    assert payload["data"]["detectedVia"] == "explicit"
    assert (tmp_path / "home" / ".cursor" / "skills" / "spa").is_symlink()
    assert (tmp_path / "home" / ".claude" / "skills" / "spa").is_symlink()


def test_cli_install_and_remove_round_trip(tmp_path):
    env = _cli_env(tmp_path, SPA_SKILLS_PLATFORMS="cursor")
    installed = run_spa(["--agent", "skills", "install"], env=env)
    assert installed.returncode == 0, installed.stdout + installed.stderr
    payload = json.loads(installed.stdout)
    assert payload["data"]["detectedVia"] == "env_platforms"
    link = tmp_path / "home" / ".cursor" / "skills" / "spa"
    assert link.is_symlink()
    assert link.resolve().name == "spa"
    removed = run_spa(["--agent", "skills", "remove", "--yes"], env=env)
    assert removed.returncode == 0, removed.stdout + removed.stderr
    assert not link.is_symlink()
    assert not link.exists()
