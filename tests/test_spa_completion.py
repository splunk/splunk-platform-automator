"""Human bash and zsh completion. Agents are refused."""

import json
import os
import stat
import subprocess
import sys

import pytest

from spa.completion import complete, words_from_line
from spa_testutil import PROJECT_ROOT, SPA, run_spa, write_min_env

pytestmark = [pytest.mark.local, pytest.mark.cli]


def test_completion_zsh_prints_a_callback_and_not_the_schema():
    result = run_spa(["completion", "zsh"])
    assert result.returncode == 0, result.stderr
    # zsh CURRENT is 1-based; the callback index is 0-based, same as bash COMP_CWORD.
    assert 'spa --no-agent completion -- "$((CURRENT - 1))" "${words[@]}"' in result.stdout
    assert "compdef _spa spa" in result.stdout
    assert '[[ "${funcstack[1]-}" == _spa ]]' in result.stdout
    assert "compadd -Q" not in result.stdout
    assert "_files -/" in result.stdout
    assert "hosts ssh" not in result.stdout
    assert "COMMAND_SCHEMA" not in result.stdout
    assert "splunk_hosts" not in result.stdout


def test_completion_zsh_eval_does_not_call_compadd(tmp_path):
    """Sourcing the function registers completion. It does not run compadd."""
    zsh = "/bin/zsh"
    if not os.path.exists(zsh):
        pytest.skip("zsh is not installed")
    result = run_spa(["completion", "zsh"])
    script = tmp_path / "spa.zsh"
    script.write_text(result.stdout, encoding="utf-8")
    loaded = subprocess.run(
        [zsh, "-f", "-c", "autoload -Uz compinit; compinit -u; source %s; echo OK" % script],
        capture_output=True,
        text=True,
    )
    assert loaded.returncode == 0, loaded.stderr
    assert "can only be called from completion function" not in loaded.stderr
    assert "OK" in loaded.stdout


def test_completion_zsh_without_compinit_does_not_error(tmp_path):
    zsh = "/bin/zsh"
    if not os.path.exists(zsh):
        pytest.skip("zsh is not installed")
    result = run_spa(["completion", "zsh"])
    script = tmp_path / "spa.zsh"
    script.write_text(result.stdout, encoding="utf-8")
    loaded = subprocess.run(
        [zsh, "-f", "-c", "source %s; echo OK" % script],
        capture_output=True,
        text=True,
    )
    assert loaded.returncode == 0, loaded.stderr
    assert "command not found: compdef" not in loaded.stderr
    assert "OK" in loaded.stdout


def test_completion_bash_prints_a_callback():
    result = run_spa(["completion", "bash"])
    assert result.returncode == 0, result.stderr
    assert 'spa --no-agent completion -- line "$COMP_POINT" "$COMP_LINE"' in result.stdout
    assert "compgen -d" in result.stdout
    assert "${COMP_WORDS[@]}" not in result.stdout
    assert "hosts ssh" not in result.stdout


def test_agent_completion_is_refused():
    result = run_spa(["completion", "zsh"], extra_env={"CURSOR_AGENT": "1"})
    assert result.returncode == 2
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert "data" not in payload
    assert "spa agent schema" in payload["error"]


def test_completion_help_is_the_install_page():
    result = run_spa(["--no-agent", "completion", "--help"])
    assert result.returncode == 0
    assert 'eval "$(spa --no-agent completion zsh)"' in result.stdout
    assert "~/.zsh/completions/_spa" in result.stdout
    assert "compinit" in result.stdout
    assert "bash-completion 2" in result.stdout
    assert "does not edit" in result.stdout


def test_bare_completion_names_the_shells():
    result = run_spa(["completion"])
    assert result.returncode == 2
    assert "spa completion bash" in result.stderr
    assert "spa completion zsh" in result.stderr


def test_unknown_shell_names_the_shells():
    result = run_spa(["completion", "fish"])
    assert result.returncode == 2
    assert "bash" in result.stderr and "zsh" in result.stderr


def test_bare_completion_is_an_agent_usage_error():
    result = run_spa(["--agent", "completion"])
    assert result.returncode == 2
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert "data" not in payload
    assert "spa completion zsh" in payload["error"]
    assert "spa agent schema" in payload["error"]


def test_unknown_shell_in_agent_mode_names_the_schema():
    result = run_spa(["--agent", "completion", "fish"])
    assert result.returncode == 2
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert "data" not in payload
    assert "spa agent schema" in payload["error"]
    assert "spa completion zsh" in payload["error"]


def test_no_agent_completion_prints_when_an_agent_is_detected():
    result = run_spa(["--no-agent", "completion", "zsh"], extra_env={"CURSOR_AGENT": "1"})
    assert result.returncode == 0, result.stderr
    assert "compdef _spa spa" in result.stdout


def test_completion_offers_canonical_names_only():
    names = complete(["spa", ""], 1)
    assert "environment" in names
    assert "shell" in names
    assert "hosts" in names
    assert "completion" in names
    for alias in ("env", "sh", "cfg", "h", "feat", "features"):
        assert alias not in names


def test_typed_alias_still_completes_the_canonical_subcommand():
    assert "explain" in complete(["spa", "cfg", ""], 2)
    assert "exp" not in complete(["spa", "config", ""], 2)


def test_flags_belong_to_the_command_being_typed():
    deploy = complete(["spa", "deploy", "--"], 2)
    assert "--hosts" in deploy
    assert "--markdown" not in deploy
    setting = complete(["spa", "config", "set", "--"], 3)
    assert "--yes" in setting
    assert "--hosts" not in setting


def test_provider_and_search_choices_come_from_the_schema():
    assert "virtualbox" in complete(["spa", "init", "--provider", "v"], 3)
    assert "aws" in complete(["spa", "environment", "set", "--provider", ""], 4)
    kinds = complete(["spa", "apps", "search", "--kind", ""], 4)
    assert "ta" in kinds
    assert "premium_itsi" in kinds
    assert "app" in complete(["spa", "apps", "search", "--type", ""], 4)


def test_keys_flag_is_not_offered():
    assert "--keys" not in complete(["spa", "config", "--"], 2)


def test_callback_prints_canonical_names():
    result = run_spa(["--no-agent", "completion", "--", "1", "spa", ""])
    assert result.returncode == 0, result.stderr
    lines = result.stdout.splitlines()
    assert "environment" in lines
    assert "env" not in lines


def test_prefix_completes_the_current_config_token():
    found = complete(["spa", "config", "set", "splunk_def"], 3)
    assert "splunk_defaults" in found
    assert all("[]" not in item for item in found)


def test_exact_node_and_trailing_dot_offer_children():
    exact = complete(["spa", "config", "explain", "splunk_defaults"], 3)
    dotted = complete(["spa", "config", "explain", "splunk_defaults."], 3)
    assert "splunk_defaults.splunk_version" in exact
    assert "splunk_defaults.splunk_version" in dotted
    assert "splunk_defaults" not in exact
    assert all("[]" not in item for item in exact + dotted)


def test_per_host_path_keeps_the_real_selector():
    config = {"splunk_hosts": [{"name": "idx1", "roles": ["indexer"]}]}
    found = complete(["spa", "config", "get", "splunk_hosts[name=idx1]."], 3, config=config)
    assert "splunk_hosts[name=idx1].roles" in found
    assert all("[]" not in item for item in found)


def test_secret_values_and_env_names_are_not_offered():
    assert complete(["spa", "config", "set", "splunk_defaults.splunk_admin_password", ""], 4) == []
    assert complete(["spa", "config", "set", "--from-env", ""], 4) == []


def test_config_keys_takes_no_path():
    assert complete(["spa", "config", "keys", "splunk"], 3) == []


def test_hosts_and_roles_come_from_config_only(monkeypatch):
    def fail_run(*_args, **_kwargs):
        raise AssertionError("completion must not run a subprocess")

    monkeypatch.setattr(subprocess, "run", fail_run)
    config = {
        "splunk_hosts": [
            {"name": "idx1", "roles": ["indexer"]},
            {"iter": {"prefix": "sh", "numbers": "1..2"}, "roles": ["search_head"]},
        ]
    }
    flags = complete(["spa", "deploy", "--hosts", ""], 3, config=config)
    assert "idx1" in flags
    assert "sh1" in flags
    assert "indexer" in flags
    assert "search_head" in flags
    assert "idx1" in complete(["spa", "hosts", "ssh", "id"], 3, config=config)
    assert "idx1" in complete(["spa", "shell", "id"], 2, config=config)
    assert "idx1" in complete(["spa", "--env", "lab", "shell", "id"], 4, config=config)
    deploy_flags = complete(["spa", "--env", "lab", "deploy", "--"], 4, config=config)
    assert "--hosts" in deploy_flags


def test_missing_config_does_not_invent_hosts():
    result = run_spa(["completion", "--", "3", "spa", "deploy", "--hosts", ""])
    assert result.returncode == 0
    assert result.stdout.strip() == ""


def test_local_catalogs_complete_without_a_network():
    playbooks = complete(["spa", "run", ""], 2)
    assert "deploy_site" in playbooks
    examples = complete(["spa", "init", "--example", ""], 3)
    assert "single_node" in examples
    assert "list" not in complete(["spa", "run", "deploy_site", ""], 3)


def test_boolean_flags_do_not_consume_the_next_word():
    flags = complete(["spa", "venv", "create", "--environment", "--"], 4)
    assert "--yes" in flags
    packs = complete(["spa", "apps", "add", "--install-all-content-packs", "--"], 4)
    assert "--yes" in packs


def test_positional_choices_are_offered(monkeypatch):
    import spa.agent as agent

    monkeypatch.setattr(
        agent,
        "COMMAND_SCHEMA",
        {"commands": [{"name": "demo", "positionals": [{"name": "KIND", "choices": ["alpha", "beta"]}]}]},
    )
    assert complete(["spa", "demo", "a"], 2) == ["alpha"]


def test_line_mode_keeps_a_selector_in_one_word():
    line = "spa config explain splunk_hosts[name=idx1]."
    words, index = words_from_line(line, len(line))
    assert words[index] == "splunk_hosts[name=idx1]."
    result = run_spa(["completion", "--", "line", str(len(line)), line])
    assert result.returncode == 0
    assert "splunk_hosts[name=idx1].roles" in result.stdout.splitlines()


def test_typed_env_completes_that_environments_hosts(tmp_path):
    xdg = tmp_path / "xdg"
    (xdg / "spa").mkdir(parents=True)

    def make_env(name, host):
        dest = write_min_env(tmp_path / name)
        (dest / "config" / "splunk_config.yml").write_text(
            "splunk_hosts:\n  - name: %s\n    roles: [indexer]\n" % host,
            encoding="utf-8",
        )
        return dest

    default = make_env("default-lab", "from-default")
    other = make_env("other-lab", "from-other")
    (xdg / "spa" / "environments.yml").write_text(
        "default: default-lab\n"
        "environments:\n"
        "  default-lab:\n"
        "    path: %s\n"
        "  other-lab:\n"
        "    path: %s\n" % (default, other),
        encoding="utf-8",
    )
    result = run_spa(
        ["completion", "--", "4", "spa", "--env", "other-lab", "shell", ""],
        extra_env={
            "XDG_CONFIG_HOME": str(xdg),
            "SPA_ENV_DIR": str(default),
            "SPA_HOME": str(PROJECT_ROOT),
        },
    )
    assert result.returncode == 0, result.stderr
    assert "from-other" in result.stdout.splitlines()
    assert "from-default" not in result.stdout.splitlines()


def test_start_dir_is_a_root_flag_and_does_not_offer_commands():
    assert "--start-dir" in complete(["spa", "--"], 1)
    values = complete(["spa", "--start-dir", ""], 2)
    assert values == []
    assert "deploy" not in values


def test_bash_function_completes_a_command_and_a_directory(tmp_path):
    import shutil
    import stat

    bash = shutil.which("bash")
    if not bash:
        pytest.skip("bash is not installed")
    wrapper = tmp_path / "bin"
    wrapper.mkdir()
    spa = wrapper / "spa"
    spa.write_text(
        "#!/bin/sh\nexec %s %s \"$@\"\n" % (sys.executable, SPA),
        encoding="utf-8",
    )
    spa.chmod(spa.stat().st_mode | stat.S_IEXEC)
    folder = tmp_path / "mydir"
    folder.mkdir()
    script = run_spa(["completion", "bash"]).stdout
    program = """
set -e
source '%s'
line='spa dep'
COMP_LINE="$line"
COMP_POINT=${#line}
COMP_WORDS=(spa dep)
COMP_CWORD=1
_spa_completion
printf '%%s\\n' "${COMPREPLY[@]}"
COMP_LINE='spa --start-dir my'
COMP_POINT=${#COMP_LINE}
COMP_WORDS=(spa --start-dir my)
COMP_CWORD=2
_spa_completion
printf '%%s\\n' "${COMPREPLY[@]}"
""" % (tmp_path / "spa.bash")
    (tmp_path / "spa.bash").write_text(script, encoding="utf-8")
    (tmp_path / "run.bash").write_text(program, encoding="utf-8")
    loaded = subprocess.run(
        [bash, str(tmp_path / "run.bash")],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        env={**os.environ, "PATH": str(wrapper) + os.pathsep + os.environ.get("PATH", "")},
    )
    assert loaded.returncode == 0, loaded.stderr
    assert "deploy" in loaded.stdout.splitlines()
    assert "mydir" in loaded.stdout.splitlines()


def test_schema_flag_values_match_command_help():
    """Every flag shown in help takes a value only when completion says it does."""
    import re

    from spa.agent import COMMAND_SCHEMA
    from spa.completion import _takes_value

    def option_takes_value(text, flag):
        for line in text.splitlines():
            if not re.match(r"^  -\S", line):
                continue
            tokens = line.strip().split()
            if flag not in tokens:
                continue
            index = tokens.index(flag)
            if index + 1 >= len(tokens):
                return False
            nxt = tokens[index + 1]
            if nxt.startswith("-"):
                return False
            if nxt.startswith("{") or re.fullmatch(r"[A-Z0-9_.-]+", nxt):
                return True
            return False
        return None

    mismatches = []
    checked = 0
    for row in COMMAND_SCHEMA["commands"]:
        flags = [flag for flag in (row.get("flags") or []) if flag.get("long")]
        if not flags:
            continue
        result = run_spa([*str(row["name"]).split(), "--help"])
        text = result.stdout + "\n" + result.stderr
        for flag in flags:
            seen = option_takes_value(text, str(flag["long"]))
            if seen is None:
                continue
            checked += 1
            if seen != _takes_value(flag):
                mismatches.append((row["name"], flag["long"], seen, _takes_value(flag)))
    assert checked > 100
    assert mismatches == []
