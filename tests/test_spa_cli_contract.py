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
            "env",
            "provision (prov)",
            "deploy (dep)",
            "destroy",
            "suspend (sus)",
            "resume (res)",
            "run",
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
            "--no-envrc",
            "--skip-doctor",
            "--software-dir",
            "--baseconfig-dir",
            "--apps-dir",
            "Environment directory",
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
            "--fix-direnv",
        ],
    ),
    (["env", "--help"], ["usage: spa env", "--export", "--start-dir"]),
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
        ["usage: spa apps snippet", "--version", "--roles", "--source", "APP_ID_OR_NAME"],
    ),
    (
        ["apps", "download", "--help"],
        ["usage: spa apps download", "--yes", "--version", "--extract", "--overwrite", "apps_dir"],
    ),
    (["provision", "--help"], ["usage: spa provision", "-y", "--yes", "Confirm provision"]),
    (
        ["deploy", "--help"],
        ["usage: spa deploy", "-y", "--yes", "--hosts", "--allow-unprovisioned", "required in agent mode"],
    ),
    (["destroy", "--help"], ["usage: spa destroy", "-y", "--yes", "Confirm destroy"]),
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
            "requires_confirmation",
            "spa run NAME --help",
        ],
    ),
    (
        ["hosts", "--help"],
        ["usage: spa hosts", "ACTION", "list (ls)", "ssh", "copy (cp)", "--status", "--hosts"],
    ),
    (
        ["hosts", "list", "--help"],
        ["usage: spa hosts list", "--status", "--hosts", "runtime power state"],
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
}


@pytest.mark.parametrize(("alias", "usage"), ALIASES.items())
def test_every_top_level_alias_routes_to_canonical_help(alias, usage):
    result = run_spa(["--no-agent", alias, "--help"])
    assert result.returncode == 0, result.stderr
    assert usage in result.stdout


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
        "env",
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
    assert {"--list", "--hosts", "--yes"} <= run_flags
    assert by_name["apps download"]["requires_confirmation"] is True
    assert "--yes" in {flag["long"] for flag in by_name["apps download"]["flags"]}
    assert "--extract" in {flag["long"] for flag in by_name["apps download"]["flags"]}
    assert "--overwrite" in {flag["long"] for flag in by_name["apps download"]["flags"]}
    assert "--source" in {flag["long"] for flag in by_name["apps snippet"]["flags"]}
    search_flags = {flag["long"] for flag in by_name["apps search"]["flags"]}
    assert {"--limit", "--type", "--kind"} <= search_flags
