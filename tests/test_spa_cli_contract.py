"""Release contract for every public ``spa`` help and schema surface."""

import json
import re

import pytest

from spa_testutil import PROJECT_ROOT, run_spa


pytestmark = [pytest.mark.local, pytest.mark.cli]


# Every public command/subcommand is listed here with the text that must remain
# discoverable. This intentionally tests the rendered CLI, not argparse
# internals, so routing and native-parser delegation are covered too.
HELP_CONTRACTS = [
    (
        ["--help"],
        [
            "usage: spa ",
            "COMMAND",
            "init",
            "validate (val)",
            "doctor (doc)",
            "venv",
            "environment (env)",
            "provision (prov)",
            "deploy (dep)",
            "destroy",
            "suspend (sus)",
            "resume (res)",
            "run",
            "logs",
            "hosts (h)",
            "shell (sh)",
            "aws",
            "licenses (lic)",
            "features (feat)",
            "apps",
            "agent",
            "--json",
            "--agent",
            "--no-agent",
            "--yes",
            "--verbose",
            "--start-dir",
        ],
    ),
    (
        ["init", "--help"],
        [
            "usage: spa init",
            "env_dir",
            "--example",
            "--provider",
            "--list",
            "--from",
            "--migrate",
            "--keep-source",
            "--force",
            "--venv",
            "--python",
            "--ansible",
            "--pip",
            "--skip-doctor",
            "--software-dir",
            "--baseconfig-dir",
            "--apps-dir",
            "--name",
            "--env-dir",
        ],
    ),
    (
        ["validate", "--help"],
        ["usage: spa validate", "config", "--check-licenses", "--splunk-config-aws"],
    ),
    (
        ["doctor", "--help"],
        [
            "usage: spa doctor",
            "--spa-home",
            "--env",
            "--aws",
            "--virtualbox",
            "--strict",
            "--json",
        ],
    ),
    (
        ["venv", "--help"],
        [
            "usage: spa venv",
            "--path",
            "--create",
            "--reinstall",
            "--upgrade",
            "--rebuild",
            "--shared",
            "--environment",
            "--python",
            "--no-install",
            "--yes",
        ],
    ),
    (["env", "--help"], ["usage: spa environment", "--export", "list", "init", "set", "remove"]),
    (
        ["environment", "set", "--help"],
        [
            "usage: spa environment set",
            "--env-dir",
            "--software-dir",
            "--baseconfig-dir",
            "--apps-dir",
            "--default",
            "--provider",
        ],
    ),
    (
        ["features", "--help"],
        ["usage: spa features", "list", "show", "search", "keys", "schema", "--keys", "--markdown", "--json", "--agent"],
    ),
    (
        ["apps", "--help"],
        ["usage: spa apps", "search", "snippet", "download", "Splunkbase"],
    ),
    (
        ["apps", "search", "--help"],
        ["usage: spa apps search", "--limit", "--type", "--kind", "addon", "premium_itsi", "keywords"],
    ),
    (
        ["apps", "snippet", "--help"],
        ["usage: spa apps snippet", "--version", "--roles", "--source", "--customize", "APP_ID_OR_NAME"],
    ),
    (
        ["apps", "download", "--help"],
        ["usage: spa apps download", "--yes", "--version", "--extract", "--overwrite", "apps_dir"],
    ),
    (["provision", "--help"], ["usage: spa provision", "-y", "--yes", "--ansible-output", "-v", "Confirm provision"]),
    (
        ["deploy", "--help"],
        [
            "usage: spa deploy",
            "-y",
            "--yes",
            "--hosts",
            "--allow-unprovisioned",
            "--ansible-output",
            "-v",
            "required in agent mode",
        ],
    ),
    (["destroy", "--help"], ["usage: spa destroy", "-y", "--yes", "--ansible-output", "-v", "Confirm destroy"]),
    (
        ["suspend", "--help"],
        ["usage: spa suspend", "-y", "--yes", "--no-wait", "--hosts", "power change"],
    ),
    (
        ["resume", "--help"],
        ["usage: spa resume", "-y", "--yes", "--hosts", "power change"],
    ),
    (
        ["run", "--help"],
        [
            "usage: spa run",
            "--list",
            "--dir",
            "--hosts",
            "--yes",
            "--apps-playbook",
            "--ansible-output",
            "-v",
            "requires_confirmation",
            "spa run NAME --help",
        ],
    ),
    (
        ["logs", "--help"],
        ["usage: spa logs", "--last", "--follow", "run_id", "--ansible-output"],
    ),
    (
        ["hosts", "--help"],
        ["usage: spa hosts", "ACTION", "list", "ssh", "copy", "--status", "-s", "--hosts"],
    ),
    (
        ["hosts", "list", "--help"],
        ["usage: spa hosts list", "--status", "-s", "--hosts", "runtime power state"],
    ),
    (
        ["hosts", "ssh", "--help"],
        ["usage: spa hosts ssh", "name", "ssh_args", "Inventory hostname", "passed to ssh"],
    ),
    (
        ["hosts", "copy", "--help"],
        [
            "usage: spa hosts copy [-r] SRC [SRC ...] DST",
            "-r",
            "--recursive",
            "HOST:PATH",
            "spa hosts copy app.tgz idx1:/tmp/",
        ],
    ),
    (
        ["shell", "--help"],
        ["usage: spa shell", "host", "-c", "--copy", "Additional arguments", "HOST:PATH"],
    ),
    (
        ["aws", "--help"],
        [
            "usage: spa aws",
            "--json",
            "--region",
            "--check-auth",
            "--list-regions",
            "--list-amis",
            "--latest-ami",
            "--list-instance-types",
            "--list-key-pairs",
            "--list-security-groups",
            "--describe-ami",
            "--validate",
            "--survey",
        ],
    ),
    (
        ["licenses", "--help"],
        ["usage: spa licenses", "--json", "--software-dir", "--config", "--no-env-recommend"],
    ),
    (
        ["agent", "--help"],
        [
            "usage: spa agent [schema]",
            "ACTION",
            "spa agent schema",
            "requires_confirmation",
            "spa --json run --list",
            "--markdown",
            "docs/commands.md",
        ],
    ),
]


@pytest.mark.parametrize(
    ("argv", "required"),
    HELP_CONTRACTS,
    ids=["root" if argv == ["--help"] else "-".join(argv[:-1]) for argv, _ in HELP_CONTRACTS],
)
def test_complete_help_contract(argv, required):
    result = run_spa(["--no-agent", *argv])
    assert result.returncode == 0, result.stderr
    assert not result.stderr
    for text in required:
        assert text in result.stdout, "%r missing from `spa %s`" % (text, " ".join(argv))
    assert "==SUPPRESS==" not in result.stdout


# Help rows look like "    validate (val)      Validate splunk_config.yml".
_COMMAND_ROW = re.compile(r"^    ([a-z][a-z0-9_-]*)(?: \(([a-z0-9]+)\))?\s{2,}\S", re.MULTILINE)
_ACTION_PARENTS = ("environment", "hosts", "apps")
# Positional args that get the handler past argparse without mutating or calling out.
_ALIAS_PROBE = {
    ("environment", "remove"): ["no-such-env"],
    ("hosts", "ssh"): ["no-such-host"],
    ("apps", "search"): ["splunk", "--kind", "not-a-kind"],
    ("apps", "snippet"): ["localapp", "--source", "local"],
    ("apps", "download"): ["123"],
}


def _command_rows(help_text: str):
    return [(match.group(1), match.group(2)) for match in _COMMAND_ROW.finditer(help_text)]


def _discovered_commands():
    """(parent argv, canonical name, short alias or None) for every spa command."""
    root = run_spa(["--no-agent", "--help"])
    assert root.returncode == 0, root.stderr
    found = [((), name, alias) for name, alias in _command_rows(root.stdout)]
    for parent in _ACTION_PARENTS:
        child = run_spa(["--no-agent", parent, "--help"])
        assert child.returncode == 0, child.stderr
        found.extend([((parent,), name, alias) for name, alias in _command_rows(child.stdout)])
    return found


def test_every_discovered_top_level_command_and_alias_use_canonical_help():
    for parents, canonical, alias in _discovered_commands():
        if parents:
            continue
        expected_usage = "usage: spa %s" % canonical
        canonical_help = run_spa(["--no-agent", canonical, "--help"])
        assert canonical_help.returncode == 0, canonical_help.stderr
        assert expected_usage in canonical_help.stdout
        for invoked in (alias,) if alias else ():
            alias_help = run_spa(["--no-agent", invoked, "--help"])
            assert alias_help.returncode == 0, alias_help.stderr
            assert alias_help.stdout == canonical_help.stdout


@pytest.mark.parametrize(
    ("argv", "usage"),
    [
        (["--json", "validate", "--help"], "usage: spa validate"),
        (["validate", "--json", "--help"], "usage: spa validate"),
        (["--agent", "validate", "--help"], "usage: spa validate"),
        (["validate", "--agent", "--help"], "usage: spa validate"),
        (["--no-agent", "validate", "--help"], "usage: spa validate"),
        (["validate", "--no-agent", "--help"], "usage: spa validate"),
        (["--yes", "provision", "--help"], "usage: spa provision"),
        (["provision", "--yes", "--help"], "usage: spa provision"),
        (["--env", "lab", "validate", "--help"], "usage: spa validate"),
        (["validate", "--env", "lab", "--help"], "usage: spa validate"),
        (["--start-dir", "/tmp/lab", "validate", "--help"], "usage: spa validate"),
        (["-v", "deploy", "--help"], "usage: spa deploy"),
        (["deploy", "-v", "--help"], "usage: spa deploy"),
    ],
)
def test_accepted_global_positions(argv, usage):
    result = run_spa(argv)
    assert result.returncode == 0, result.stderr
    assert usage in result.stdout
    assert "unrecognized arguments" not in result.stderr


@pytest.mark.parametrize(
    "argv",
    [
        ["--start-dir", str(PROJECT_ROOT), "agent", "schema"],
        ["agent", "--start-dir", str(PROJECT_ROOT), "schema"],
    ],
)
def test_start_dir_routes_before_and_after_subcommand(argv):
    result = run_spa(argv)
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["data"]["name"] == "spa"


@pytest.mark.parametrize(
    ("argv", "usage"),
    [
        (["shell", "--help"], "usage: spa shell"),
        (["sh", "--help"], "usage: spa shell"),
        (["aws", "--json", "--help"], "usage: spa aws"),
        (["licenses", "--json", "--help"], "usage: spa licenses"),
        (["lic", "--json", "--help"], "usage: spa licenses"),
        (["--agent", "aws", "--json", "--help"], "usage: spa aws"),
        (["--agent", "licenses", "--json", "--help"], "usage: spa licenses"),
    ],
)
def test_native_commands_keep_native_flags(argv, usage):
    result = run_spa(argv)
    assert result.returncode == 0, result.stderr
    assert usage in result.stdout
    assert not result.stdout.lstrip().startswith('{"ok":')


def test_every_short_command_is_short_enough_and_dispatches():
    """Names under 5 characters have no alias. Longer names have one alias under 5 that runs the same command."""
    commands = _discovered_commands()
    names = {" ".join((*parents, name)) for parents, name, _alias in commands}
    assert "environment remove" in names
    assert "hosts list" in names
    assert "apps search" in names
    for parents, name, alias in commands:
        label = " ".join((*parents, name))
        if len(name) < 5:
            assert alias is None, "%s is %s characters and must not have a short command" % (
                label,
                len(name),
            )
            continue
        assert alias, "%s needs a short command" % label
        assert len(alias) < 5, "%s short command %s must be under 5 characters" % (label, alias)
        probe = _ALIAS_PROBE.get(tuple(parents) + (name,), [])
        short = run_spa(["--no-agent", *parents, alias, *probe], stdin="n\n")
        long = run_spa(["--no-agent", *parents, name, *probe], stdin="n\n")
        assert short.returncode == long.returncode, label
        assert short.stdout == long.stdout, label
        assert short.stderr == long.stderr, label


@pytest.mark.parametrize(
    "argv",
    [
        ["deploy", "--ansible-output", "-v"],
        ["dep", "-v", "--ansible-output"],
        ["provision", "-v"],
        ["destroy", "-v"],
        ["suspend", "-v"],
        ["resume", "-v"],
        ["run", "-v"],
        ["logs", "-v"],
        ["hosts", "list", "-s"],
    ],
)
def test_verbose_is_accepted_after_the_subcommand(argv):
    result = run_spa(["--no-agent", *argv, "--help"])
    assert result.returncode == 0, result.stderr
    assert "unrecognized arguments" not in result.stderr


def test_hosts_list_status_short_flag_is_s_not_v():
    help_out = run_spa(["--no-agent", "hosts", "list", "--help"])
    assert help_out.returncode == 0, help_out.stderr
    assert "-s, --status" in help_out.stdout
    assert "Same as --status" not in help_out.stdout
    rejected = run_spa(["--no-agent", "hosts", "list", "-v"])
    assert rejected.returncode != 0
    assert "unrecognized arguments" in rejected.stderr


def test_verbose_is_listed_next_to_ansible_output():
    result = run_spa(["--no-agent", "deploy", "--help"])
    assert result.returncode == 0, result.stderr
    usage, options = result.stdout.split("options:", 1)
    compact = " ".join(usage.split())
    assert "[--ansible-output] [--timestamps] [--color] [-v]" in compact
    idx_ao = options.index("--ansible-output")
    idx_v = options.index("-v, --verbose")
    assert idx_ao < idx_v
    between = options[idx_ao:idx_v]
    assert "--agent" not in between
    assert "--json" not in between
    compact_opts = " ".join(options.split())
    assert "Increase Ansible verbosity and show native output" in compact_opts
    assert "repeat through -vvvv" in compact_opts
    assert "Same as --ansible-output" not in compact_opts


@pytest.mark.parametrize(
    "argv",
    [
        ["--no-agent", "logs", "-v"],
        ["--no-agent", "-v", "logs"],
    ],
)
def test_logs_rejects_execution_verbosity(argv):
    result = run_spa(argv)
    assert result.returncode != 0
    assert "error:" in result.stderr


@pytest.mark.parametrize("backend_flag", ["-vv", "--verbose"])
def test_ansible_verbosity_is_limited_and_not_duplicated_after_separator(backend_flag):
    too_verbose = run_spa(
        ["--no-agent", "run", "splunk_cli", "--yes", "-vvvvv"]
    )
    assert too_verbose.returncode != 0
    assert "supports at most -vvvv" in too_verbose.stderr

    duplicated = run_spa(
        ["--no-agent", "run", "splunk_cli", "--yes", "-v", "--", backend_flag]
    )
    assert duplicated.returncode != 0
    assert "verbosity before or after --, not both" in duplicated.stderr


def test_removed_short_names_are_not_commands():
    for argv in (["hosts", "ls"], ["hosts", "cp"], ["environment", "ls"]):
        result = run_spa(["--no-agent", *argv])
        assert result.returncode != 0, argv
        assert "invalid choice" in result.stderr


def test_agent_schema_is_complete_and_documented():
    result = run_spa(["agent", "schema"])
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    commands = payload["data"]["commands"]

    assert {row["name"] for row in commands} == {
        "init",
        "features",
        "validate",
        "doctor",
        "venv",
        "environment list",
        "environment init",
        "environment set",
        "environment remove",
        "environment",
        "provision",
        "deploy",
        "destroy",
        "suspend",
        "resume",
        "hosts list",
        "hosts ssh",
        "hosts copy",
        "shell",
        "aws",
        "licenses",
        "run",
        "logs",
        "apps search",
        "apps snippet",
        "apps download",
        "agent schema",
    }
    for row in commands:
        assert row.get("summary"), row["name"]
        for flag in row.get("flags", []):
            assert flag.get("long"), (row["name"], flag)
            assert flag.get("help"), (row["name"], flag)

    by_name = {row["name"]: row for row in commands}
    for name in ("provision", "deploy", "destroy", "suspend", "resume"):
        assert by_name[name]["requires_confirmation"] is True
        assert "--yes" in {flag["long"] for flag in by_name[name]["flags"]}

    run_flags = {flag["long"] for flag in by_name["run"]["flags"]}
    assert {"--list", "--hosts", "--yes", "--apps-playbook"} <= run_flags
    assert by_name["apps download"]["requires_confirmation"] is True
    assert "--yes" in {flag["long"] for flag in by_name["apps download"]["flags"]}
    assert "--extract" in {flag["long"] for flag in by_name["apps download"]["flags"]}
    assert "--overwrite" in {flag["long"] for flag in by_name["apps download"]["flags"]}
    assert "--source" in {flag["long"] for flag in by_name["apps snippet"]["flags"]}
    assert "--customize" in {flag["long"] for flag in by_name["apps snippet"]["flags"]}
    search_flags = {flag["long"] for flag in by_name["apps search"]["flags"]}
    assert {"--limit", "--type", "--kind"} <= search_flags
    assert "--markdown" in {flag["long"] for flag in by_name["agent schema"]["flags"]}
