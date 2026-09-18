"""Release contract for every public ``spa`` help and schema surface."""

import json

import pytest

from spa_testutil import run_spa


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
        ["usage: spa features", "list", "show", "search", "keys", "--keys", "--json", "--agent"],
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
        ["usage: spa logs", "--last", "--follow", "run_id", "--ansible-output", "-v"],
    ),
    (
        ["hosts", "--help"],
        ["usage: spa hosts", "ACTION", "list (ls)", "ssh", "copy (cp)", "--status", "-s", "--hosts"],
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


ALIASES = {
    "feat": "usage: spa features",
    "val": "usage: spa validate",
    "doc": "usage: spa doctor",
    "prov": "usage: spa provision",
    "dep": "usage: spa deploy",
    "des": "usage: spa destroy",
    "sus": "usage: spa suspend",
    "res": "usage: spa resume",
    "h": "usage: spa hosts",
    "sh": "usage: spa shell",
    "lic": "usage: spa licenses",
    "env": "usage: spa environment",
}


@pytest.mark.parametrize(("alias", "usage"), ALIASES.items())
def test_every_top_level_alias_routes_to_canonical_help(alias, usage):
    result = run_spa(["--no-agent", alias, "--help"])
    assert result.returncode == 0, result.stderr
    assert usage in result.stdout


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
    assert "[--ansible-output] [-v]" in compact
    idx_ao = options.index("--ansible-output")
    idx_v = options.index("-v, --verbose")
    assert idx_ao < idx_v
    between = options[idx_ao:idx_v]
    assert "--agent" not in between
    assert "--json" not in between
    compact_opts = " ".join(options.split())
    # -v is the unredacted native stream, not a synonym for --ansible-output.
    assert "Stream Ansible's own output unredacted" in compact_opts
    # Ansible's own verbosity stays a pass-through, not a -v level.
    assert "-- -vv" in compact_opts
    assert "Same as --ansible-output" not in compact_opts


@pytest.mark.parametrize(
    ("argv", "usage"),
    [
        (["hosts", "ls", "--help"], "usage: spa hosts list"),
        (["hosts", "cp", "--help"], "usage: spa hosts copy"),
    ],
)
def test_every_hosts_alias_routes_to_canonical_help(argv, usage):
    result = run_spa(["--no-agent", *argv])
    assert result.returncode == 0, result.stderr
    assert usage in result.stdout


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
