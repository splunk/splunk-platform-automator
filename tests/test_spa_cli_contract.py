"""Release contract for every public ``spa`` help and schema surface."""

import json
import re
from pathlib import Path

import pytest

from spa.providers import format_provider_choice
from spa_testutil import (
    PROJECT_ROOT,
    min_env_vars,
    run_spa,
    run_spa_inprocess,
    run_spa_init,
    write_min_env,
)


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
            "validate",
            "doctor",
            "version",
            "self",
            "venv",
            "environment",
            "deploy",
            "destroy",
            "suspend",
            "resume",
            "run",
            "logs",
            "hosts",
            "shell",
            "provider",
            "licenses",
            "config",
            "apps",
            "agent",
            "--json",
            "--agent",
            "--no-agent",
            "--yes",
            "--verbose",
            "--start-dir",
            "Force agent mode",
            "Force human mode",
        ],
    ),
    (
        ["init", "--help"],
        [
            "usage: spa init",
            "env_dir",
            "--example",
            "--architecture",
            "--provider",
            "spa init list",
            "--from",
            "--migrate",
            "--keep-source",
            "--force",
            "--reset-paths",
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
            "splunk_config.yml",
            "for this env (.spa.yml)",
            "If omitted, uses existing .spa.yml unless --reset-paths, then ~/.config/spa/paths.yml then discovery",
            "Seeds paths.yml only when that key is unset",
            format_provider_choice(),
        ],
    ),
    (
        ["validate", "--help"],
        ["usage: spa validate", "Aliases: val", "--config", "--check-licenses", "--splunk-config"],
    ),
    (
        ["doctor", "--help"],
        [
            "usage: spa doctor",
            "--spa-home",
            "--env",
            "--provider",
            "--strict",
            "--json",
        ],
    ),
    (
        ["version", "--help"],
        [
            "usage: spa version",
            "Print the installed SPA version",
            "check",
        ],
    ),
    (
        ["version", "check", "--help"],
        [
            "usage: spa version check",
            "GitHub",
        ],
    ),
    (
        ["self", "--help"],
        [
            "usage: spa self",
            "update",
            "spa self needs an action",
            "spa self update",
        ],
    ),
    (
        ["self", "update", "--help"],
        [
            "usage: spa self update",
            "--yes",
            "--version",
        ],
    ),
    (
        ["venv", "--help"],
        [
            "usage: spa venv",
            "path",
            "create",
            "reinstall",
            "upgrade",
            "rebuild",
        ],
    ),
    (
        ["venv", "rebuild", "--help"],
        ["usage: spa venv rebuild", "--shared", "--yes"],
    ),
    (
        ["venv", "path", "--help"],
        ["usage: spa venv path"],
    ),
    (
        ["env", "--help"],
        [
            "usage: spa environment",
            "Aliases: env",
            "--export",
            "list",
            "init",
            "set",
            "remove",
            "spa environment needs an action.",
            "spa environment list",
        ],
    ),
    (
        ["environment", "set", "--help"],
        [
            "usage: spa environment set",
            "--create-defaults",
            "--yes",
            "--env-dir",
            "--software-dir",
            "--baseconfig-dir",
            "--apps-dir",
            "--default",
            "--provider",
            "saved in paths.yml",
        ],
    ),
    (
        ["config", "--help"],
        [
            "usage: spa config",
            "get",
            "explain",
            "search",
            "keys",
            "schema",
            "set",
            "add",
            "unset",
            "merge",
            "move",
            "topology",
            "provider",
            "migrate",
            "audit",
            "templates",
            "spa config search QUERY",
            "spa config explain PATH",
            "spa config schema --markdown",
        ],
    ),
    (
        ["config", "templates", "--help"],
        [
            "usage: spa config templates",
            "ACTION",
            "list",
            "Aliases: tpl",
            "spa config templates needs an action",
        ],
    ),
    (
        ["config", "templates", "list", "--help"],
        ["usage: spa config templates list"],
    ),
    (
        ["config", "audit", "--help"],
        ["usage: spa config audit", "--check-hand-edits"],
    ),
    (
        ["config", "set", "--help"],
        ["usage: spa config set", "PATH", "VALUE", "--value-file", "--from-env", "--dry-run", "--expect-revision", "--resolve"],
    ),
    (
        ["config", "migrate", "--help"],
        ["usage: spa config migrate", "--dry-run", "--expect-revision", "--show-diff", "--yes"],
    ),
    (
        ["config", "header", "set", "--help"],
        [
            "usage: spa config header set",
            "--intent",
            "--requirements",
            "--sva",
            "--placement",
            "--license",
            "--installer",
            "--os",
            "--aws",
            "--deploy",
            "--yes",
            "Omitted fields are removed.",
            "Header fields",
            "config-test | app-lab | production-like",
            "Example:",
        ],
    ),
    (
        ["config", "add", "--help"],
        ["usage: spa config add", "SELECTOR", "JSON_OBJECT", "--value-file", "--from-env", "--dry-run", "--resolve"],
    ),
    (
        ["config", "merge", "--help"],
        ["usage: spa config merge", "TEMPLATE", "--file", "--dry-run", "--resolve-file"],
    ),
    (
        ["config", "move", "--help"],
        ["usage: spa config move", "role", "host"],
    ),
    (
        ["config", "move", "role", "--help"],
        ["usage: spa config move role", "ROLE", "--from", "--to"],
    ),
    (
        ["config", "move", "host", "--help"],
        ["usage: spa config move host", "--to", "--prefix", "--postfix"],
    ),
    (
        ["architecture", "--help"],
        ["usage: spa architecture", "plan", "apply", "check"],
    ),
    (
        ["architecture", "plan", "--help"],
        ["usage: spa architecture plan", "FILE", "examples/architectures/c3.json", "schema 1"],
    ),
    (
        ["architecture", "apply", "--help"],
        ["usage: spa architecture apply", "FILE", "--yes"],
    ),
    (
        ["architecture", "check", "--help"],
        ["usage: spa architecture check", "FILE"],
    ),
    (
        ["apps", "--help"],
        [
            "usage: spa apps",
            "search",
            "content-packs",
            "snippet",
            "add",
            "remove",
            "download",
            "Splunkbase",
            "spa apps needs an action.",
            "spa apps search QUERY",
            "Discover ITSI content packs",
            "Content Library 5391",
        ],
    ),
    (
        ["apps", "search", "--help"],
        [
            "usage: spa apps search",
            "--limit",
            "--type",
            "--kind",
            "addon",
            "premium_itsi",
            "premium_es",
            "keywords",
            "spa apps content-packs list 5391",
            "itsi_content_library",
            "itsi_content_pack_single",
            "One pack with its own Splunkbase app ID",
        ],
    ),
    (
        ["apps", "content-packs", "list", "--help"],
        [
            "usage: spa apps content-packs list",
            "--version",
            "--archive",
            "matching archive in apps_dir",
            "install archive",
            "--version",
            "cached pack app.conf",
        ],
    ),
    (
        ["apps", "snippet", "--help"],
        ["usage: spa apps snippet", "--version", "--roles", "--source", "--customize", "--set", "APP_ID_OR_NAME"],
    ),
    (
        ["apps", "add", "--help"],
        [
            "usage: spa apps add",
            "--roles",
            "--new",
            "--set",
            "--content-pack",
            "--install-all-content-packs",
            "--dry-run",
            "edits splunk_config.yml",
            "does not deploy",
            "Normal app",
            "1841",
            "Content Library 5391",
            "7294",
            "spa apps content-packs list 5391",
            "spa validate",
            "spa deploy --yes",
            "spa hosts check",
            "spa run splunk_apps_deploy --yes",
            "Already-running lab",
            "First-time install",
            "required only for normal apps",
            "rejected for ITSI",
            "default latest",
            "default splunkbase",
            "Shorthand for --source local",
            "Mutually exclusive with --source",
            "repeatable",
            "mutually exclusive with --install-all-content-packs",
            "mutually exclusive with --content-pack",
            "named content pack",
            "without prompting or writing",
            "SHA-256 revision",
            "strict JSON",
            "use - for stdin",
            "agent mode never prompts",
        ],
    ),
    (
        ["apps", "remove", "--help"],
        ["usage: spa apps remove", "--roles", "--content-pack", "--dry-run", "APP_ID_OR_NAME"],
    ),
    (
        ["apps", "download", "--help"],
        ["usage: spa apps download", "--yes", "--version", "--extract", "--overwrite", "apps_dir"],
    ),
    (["hosts", "provision", "--help"], ["usage: spa hosts provision", "-y", "--yes", "--ansible-output", "-v", "Confirm hosts provision"]),
    (
        ["deploy", "--help"],
        [
            "usage: spa deploy",
            "-y",
            "--yes",
            "--hosts",
            "--ansible-output",
            "-v",
            "required in agent mode",
            "[--ansible-output] [--timestamps] [--color] [-v]",
            "Increase Ansible verbosity and show native output",
            "repeat through -vvvv",
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
            "spa run list",
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
        ["usage: spa logs", "--last", "--follow", "--wait", "run_id", "--ansible-output"],
    ),
    (
        ["hosts", "--help"],
        ["usage: spa hosts", "ACTION", "list", "ssh", "copy", "register", "unregister", "provision", "check", "spa hosts check"],
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
        ["hosts", "register", "--help"],
        [
            "IP, hostname, or FQDN. Must be reachable by SSH.",
            "--ssh-host",
            "--ip-addr",
            "--user",
            "--key",
            "--ssh-port",
            "--role",
        ],
    ),
    (
        ["hosts", "check", "--help"],
        ["spa deploy", "Does not deploy", "--hosts"],
    ),
    (
        ["shell", "--help"],
        ["usage: spa shell", "Aliases: sh", "name", "ssh_args", "Inventory hostname", "passed to ssh"],
    ),
    (
        ["provider", "aws", "--help"],
        [
            "usage: spa provider aws",
            "ACTION",
            "check-auth",
            "latest-ami",
            "describe-ami",
            "validate",
            "survey",
            "regions",
            "amis",
            "spa provider aws check-auth",
            "spa provider aws regions list",
        ],
    ),
    (
        ["provider", "aws", "check-auth", "--help"],
        ["usage: spa provider aws check-auth"],
    ),
    (
        ["provider", "aws", "latest-ami", "--help"],
        ["usage: spa provider aws latest-ami", "--region", "--os"],
    ),
    (
        ["provider", "aws", "describe-ami", "--help"],
        ["usage: spa provider aws describe-ami", "--ami-id"],
    ),
    (
        ["provider", "aws", "validate", "--help"],
        ["usage: spa provider aws validate", "--region", "--details", "--ami-id", "--key-name", "--security-groups", "--instance-type"],
    ),
    (
        ["provider", "aws", "survey", "--help"],
        ["usage: spa provider aws survey", "--region"],
    ),
    (
        ["provider", "aws", "regions", "--help"],
        ["usage: spa provider aws regions", "list"],
    ),
    (
        ["provider", "aws", "regions", "list", "--help"],
        ["usage: spa provider aws regions list"],
    ),
    (
        ["provider", "aws", "amis", "list", "--help"],
        ["usage: spa provider aws amis list", "--region", "--name-filter", "--owners", "--max-results", "--os"],
    ),
    (
        ["provider", "aws", "instance-types", "list", "--help"],
        ["usage: spa provider aws instance-types list", "--region", "--family"],
    ),
    (
        ["licenses", "--help"],
        [
            "usage: spa licenses",
            "ACTION",
            "list",
            "add",
            "List or add Software licenses",
            "Aliases: lic",
            "spa licenses needs an action",
        ],
    ),
    (
        ["skills", "--help"],
        [
            "usage: spa skills",
            "Copy SPA skills into a user IDE skill directory",
            "install",
            "update",
            "remove",
            "claude-code (claude)",
            "cursor",
            "codex",
            "opencode",
            "windsurf",
            "gemini-code (gemini)",
            "pi (pi-dev)",
            "antigravity (agy)",
            "or all",
            "spa skills update",
        ],
    ),
    (
        ["skills", "install", "--help"],
        ["usage: spa skills install", "--name", "--all"],
    ),
    (
        ["skills", "update", "--help"],
        ["usage: spa skills update"],
    ),
    (
        ["licenses", "list", "--help"],
        [
            "usage: spa licenses list",
            "--software-dir",
            "--config",
            "--details",
            "--no-env-recommend",
        ],
    ),
    (
        ["licenses", "add", "--help"],
        [
            "usage: spa licenses add",
            "FILE",
            "--software-dir",
            "--force",
            "--replace",
            "--yes",
        ],
    ),
    (
        ["agent", "--help"],
        [
            "usage: spa agent [schema]",
            "ACTION",
            "spa agent schema",
            "requires_confirmation",
            "spa --agent run list",
            "--markdown",
            "docs/commands.md",
        ],
    ),
]


def test_hosts_ping_names_check():
    result = run_spa(["--no-agent", "hosts", "ping"])
    assert result.returncode == 2
    assert "spa hosts check" in result.stderr


def _collapsed_help(stdout: str) -> str:
    """Join wrapped argparse lines so HELP_CONTRACTS can match phrase-level copy."""
    pieces: list[str] = []
    for line in stdout.splitlines():
        stripped = line.strip()
        if pieces and line.startswith(" ") and pieces[-1].endswith("-"):
            pieces[-1] += stripped
        else:
            pieces.append(stripped)
    return " ".join(pieces)


@pytest.mark.parametrize(
    ("argv", "required"),
    HELP_CONTRACTS,
    ids=["root" if argv == ["--help"] else "-".join(argv[:-1]) for argv, _ in HELP_CONTRACTS],
)
def test_complete_help_contract(argv, required):
    result = run_spa_inprocess(["--no-agent", *argv])
    assert result.returncode == 0, result.stderr
    assert not result.stderr
    text = _collapsed_help(result.stdout)
    for needle in required:
        assert needle in text, "%r missing from `spa %s`" % (needle, " ".join(argv))
    assert "==SUPPRESS==" not in result.stdout
    assert "{init," not in result.stdout
    if argv == ["apps", "add", "--help"]:
        from spa.agent import COMMAND_SCHEMA

        add = next(row for row in COMMAND_SCHEMA["commands"] if row["name"] == "apps add")
        for flag in add["flags"]:
            assert flag["help"] in text, flag["long"]


# Help rows look like "    validate (val)      Validate splunk_config.yml".
_COMMAND_ROW = re.compile(r"^    ([a-z][a-z0-9_-]*)(?: \(([a-z0-9]+)\))?\s{2,}\S", re.MULTILINE)
_ACTION_PARENTS = ("environment", "hosts", "apps", "licenses")


def _command_rows(help_text: str):
    return [(match.group(1), match.group(2)) for match in _COMMAND_ROW.finditer(help_text)]


def _discovered_commands():
    """(parent argv, canonical name, short alias or None) for every spa command."""
    root = run_spa_inprocess(["--no-agent", "--help"])
    assert root.returncode == 0, root.stderr
    found = [((), name, alias) for name, alias in _command_rows(root.stdout)]
    for parent in _ACTION_PARENTS:
        child = run_spa_inprocess(["--no-agent", parent, "--help"])
        assert child.returncode == 0, child.stderr
        found.extend([((parent,), name, alias) for name, alias in _command_rows(child.stdout)])
    return found


def test_schema_and_help_teach_agent_not_the_json_envelope_flag(agent_schema):
    schema = agent_schema
    assert schema["ok"] is True
    for row in schema["data"]["commands"]:
        for field in ("example", "summary"):
            text = row.get(field) or ""
            assert "spa --json" not in text, (row["name"], field)
            assert "spa env --export" not in text
    exported = next(row for row in schema["data"]["commands"] if row["name"] == "environment")
    assert exported["example"] == "spa environment --export"
    by_agent = run_spa(["--agent", "init", "list"])
    by_json = run_spa(["--json", "init", "list"])
    assert by_agent.returncode == by_json.returncode == 0
    assert by_agent.stdout == by_json.stdout
    root = run_spa_inprocess(["--no-agent", "--help"])
    assert "Synonym of --agent" in root.stdout


def test_every_discovered_top_level_command_and_alias_use_canonical_help():
    for parents, canonical, alias in _discovered_commands():
        if parents:
            continue
        expected_usage = "usage: spa %s" % canonical
        canonical_help = run_spa_inprocess(["--no-agent", canonical, "--help"])
        assert canonical_help.returncode == 0, canonical_help.stderr
        assert expected_usage in canonical_help.stdout
        for invoked in (alias,) if alias else ():
            alias_help = run_spa_inprocess(["--no-agent", invoked, "--help"])
            assert alias_help.returncode == 0, alias_help.stderr
            assert alias_help.stdout == canonical_help.stdout


@pytest.mark.parametrize(
    ("argv", "expect"),
    [
        (["--json", "validate", "--help"], "validate"),
        (["validate", "--json", "--help"], "validate"),
        (["--agent", "validate", "--help"], "validate"),
        (["validate", "--agent", "--help"], "validate"),
        (["--no-agent", "validate", "--help"], "usage: spa validate"),
        (["validate", "--no-agent", "--help"], "usage: spa validate"),
        (["--yes", "hosts", "provision", "--help"], "usage: spa hosts provision"),
        (["hosts", "provision", "--yes", "--help"], "usage: spa hosts provision"),
        (["--env", "lab", "validate", "--help"], "usage: spa validate"),
        (["validate", "--env", "lab", "--help"], "usage: spa validate"),
        (["--start-dir", "/tmp/lab", "validate", "--help"], "usage: spa validate"),
        (["-v", "deploy", "--help"], "usage: spa deploy"),
        (["deploy", "-v", "--help"], "usage: spa deploy"),
    ],
)
def test_accepted_global_positions(argv, expect):
    result = run_spa(argv)
    assert result.returncode == 0, result.stderr
    assert "unrecognized arguments" not in result.stderr
    if expect.startswith("usage:"):
        assert expect in result.stdout
        return
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["schema_version"] == 1
    assert "data" in payload
    assert payload["data"]["name"] == expect
    assert re.search(r"\bval\b", result.stdout) is None


@pytest.mark.parametrize(
    "argv",
    [
        ["config", "set"],
        ["config", "add"],
        ["config", "unset"],
        ["config", "provider"],
        ["apps", "remove"],
    ],
)
@pytest.mark.parametrize("mode", ["--no-agent", "--agent"])
def test_required_operands_say_how_to_find_a_legal_value(argv, mode):
    result = run_spa([mode, *argv])
    assert result.returncode == 2, result.stderr + result.stdout
    if mode == "--agent":
        payload = json.loads(result.stdout)
        assert payload["ok"] is False
        assert "data" not in payload
        text = payload["error"]
        assert result.stderr == ""
    else:
        text = result.stderr
        assert result.stdout.strip() == ""
    assert "the following arguments are required" not in text
    if argv[-1] == "provider":
        assert "spa init list" in text
        assert "spa config provider aws" in text


def test_config_topology_without_operand_lists_catalog_links():
    result = run_spa(["config", "topology"])
    assert result.returncode == 0, result.stderr
    assert "topology.c1  cm_2idxc_sh" in result.stdout
    assert "topology.d11  2idx_sh_es" in result.stdout


def test_config_topology_without_operand_json_lists_catalog_links():
    result = run_spa(["--json", "config", "topology"])
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    catalog = {item["id"]: item["template"] for item in payload["data"]["catalog"]}
    assert catalog["topology.c1"] == "cm_2idxc_sh"
    assert catalog["topology.m3"] == "cm_4idxc2site_2x3shc_ds"


def test_command_classes_keep_one_human_and_agent_shape(tmp_path):
    """One representative of each output class. Same facts, two renderings."""
    dest = tmp_path / "env"
    created = run_spa_init(["--example", "single_node", "--provider", "aws", str(dest)])
    assert created.returncode == 0, created.stderr
    env = {"SPA_HOME": str(PROJECT_ROOT), "SPA_ENV_DIR": str(dest)}

    human_search = run_spa(["--no-agent", "config", "search", "host"])
    agent_search = run_spa(["--agent", "config", "search", "host"])
    assert human_search.returncode == 0, human_search.stderr
    assert not human_search.stdout.lstrip().startswith("{")
    human_rows = [line.split("  ", 1)[0] for line in human_search.stdout.splitlines() if line.strip()]
    search_body = json.loads(agent_search.stdout)
    matches = search_body["data"]["matches"]
    assert search_body["data"]["truncated"] is True
    assert search_body["data"]["total_matches"] > len(matches)
    assert [row["path"] for row in matches] == human_rows
    again = json.loads(run_spa(["--agent", "config", "search", "host"]).stdout)
    assert [row["path"] for row in again["data"]["matches"]] == [row["path"] for row in matches]

    human_explain = run_spa(["--no-agent", "config", "explain", "os.packages"])
    agent_explain = run_spa(["--agent", "config", "explain", "os.packages"])
    assert human_explain.stdout.splitlines()[0] == "PATH: os.packages"
    explained = json.loads(agent_explain.stdout)["data"]
    assert explained["path"] == "os.packages"
    assert explained["type"]
    assert "matches" not in explained

    human_get = run_spa(["--no-agent", "config", "get", "os.time_zone"], env=env)
    agent_get = run_spa(["--agent", "config", "get", "os.time_zone"], env=env)
    assert human_get.returncode == 0, human_get.stderr
    assert not human_get.stdout.lstrip().startswith("{")
    got = json.loads(agent_get.stdout)
    assert got["ok"] is True
    assert got["data"]["path"] == "os.time_zone"
    assert "revision" in got["data"]

    human_edit = run_spa(
        ["--no-agent", "config", "set", "os.time_zone", "Europe/Berlin", "--dry-run"],
        env=env,
    )
    agent_edit = run_spa(
        ["--agent", "config", "set", "os.time_zone", "Europe/Berlin", "--dry-run"],
        env=env,
    )
    assert human_edit.returncode == 0, human_edit.stderr
    assert "would change" in human_edit.stdout or "unchanged" in human_edit.stdout
    edited = json.loads(agent_edit.stdout)
    assert edited["ok"] is True
    assert "revision_before" in edited["data"]
    assert "Proceed?" not in agent_edit.stdout
    assert "Proceed?" not in agent_edit.stderr

    human_validate = run_spa(["--no-agent", "validate"], env=env)
    agent_validate = run_spa(["--agent", "validate"], env=env)
    assert not human_validate.stdout.lstrip().startswith("{")
    validated = json.loads(agent_validate.stdout)
    assert validated["schema_version"] == 1
    assert validated["ok"] is (agent_validate.returncode == 0)
    if validated["ok"]:
        assert validated["data"]["config_file"]
    else:
        assert validated.get("error") or validated.get("data")

    folder = Path(dest) / "logs"
    folder.mkdir()
    jsonl = folder / "rid.jsonl"
    jsonl.write_text(
        '{"time":"2026-09-18T15:00:00.000+02:00","msg":"hello-run"}\n',
        encoding="utf-8",
    )
    (folder / "rid.meta.json").write_text(
        json.dumps(
            {
                "run_id": "rid",
                "command": "deploy",
                "rc": 0,
                "log": str(jsonl),
                "start": "2026-09-18T15:00:00.000+02:00",
            }
        ),
        encoding="utf-8",
    )
    human_log = run_spa(["--no-agent", "logs", "--last"], env=env)
    agent_log = run_spa(["--agent", "logs", "--last"], env=env)
    assert human_log.returncode == 0, human_log.stderr
    assert "hello-run" in human_log.stdout
    assert "  rc=" not in human_log.stdout
    logged = json.loads(agent_log.stdout)
    assert logged["data"]["log"]
    assert logged["data"]["run_id"] == "rid"
    assert "transcript" not in logged["data"]
    assert "hello-run" not in agent_log.stdout


def test_unknown_topology_is_reported_before_confirmation(tmp_path):
    dest = write_min_env(tmp_path / "env")
    (dest / "config" / "splunk_config.yml").write_text("splunk_hosts: []\n", encoding="utf-8")
    env = {"SPA_HOME": str(PROJECT_ROOT), "SPA_ENV_DIR": str(dest)}
    human = run_spa(["--no-agent", "config", "topology", "not_a_real_topology"], env=env)
    assert human.returncode == 2, human.stderr
    assert "spa init list" in human.stderr
    assert "requires -y/--yes" not in human.stderr + human.stdout


def test_unknown_topology_points_at_init_list(tmp_path):
    dest = tmp_path / "env"
    created = run_spa_init(["--example", "single_node", "--provider", "aws", str(dest)])
    assert created.returncode == 0, created.stderr
    env = {"SPA_HOME": str(PROJECT_ROOT), "SPA_ENV_DIR": str(dest)}
    human = run_spa(
        ["--no-agent", "config", "topology", "not_a_real_topology", "--dry-run"],
        env=env,
    )
    agent = run_spa(
        ["--agent", "config", "topology", "not_a_real_topology"],
        env=env,
    )
    assert human.returncode == 2, human.stderr
    assert "spa init list" in human.stderr
    assert "not_a_real_topology" in human.stderr
    assert "/examples/" not in human.stderr
    body = json.loads(agent.stdout)
    assert agent.returncode == 2
    assert "data" not in body
    assert body["error"] in human.stderr
    assert "spa init list" in body["error"]
    assert "not_a_real_topology" in body["error"]
    assert "/examples/" not in body["error"]


def test_agent_help_is_one_schema_entry_or_an_index():
    root = run_spa(["--agent", "--help"])
    assert root.returncode == 0, root.stderr
    index = json.loads(root.stdout)
    assert index["ok"] is True
    rows = index["data"]["commands"]
    validate = next(row for row in rows if row["name"] == "validate")
    assert validate["help"] == "spa validate --help"
    assert "summary" in validate
    assert "flags" not in validate
    assert all(row["name"] != "val" for row in rows)

    nested = run_spa(["--agent", "config", "explain", "--help"])
    assert nested.returncode == 0, nested.stderr
    explained = json.loads(nested.stdout)
    assert explained["data"]["name"] == "config explain"
    assert explained["data"]["positionals"][0]["name"] == "PATH"

    detected = run_spa(["config", "explain", "--help"], extra_env={"SPA_AGENT": "1"})
    assert json.loads(detected.stdout)["data"]["name"] == "config explain"

    forced_human = run_spa(
        ["--no-agent", "validate", "--help"], extra_env={"SPA_AGENT": "1"}
    )
    assert "usage: spa validate" in forced_human.stdout
    assert not forced_human.stdout.lstrip().startswith("{")


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
    ("argv", "name"),
    [
        (["provider", "aws", "--json", "--help"], "provider aws"),
        (["--agent", "provider", "aws", "--json", "--help"], "provider aws"),
        (["--agent", "provider", "aws", "--help"], "provider aws"),
        (["--agent", "shell", "--help"], "shell"),
    ],
)
def test_agent_aws_and_shell_help_is_schema_envelope(argv, name):
    result = run_spa(argv)
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["schema_version"] == 1
    assert payload["data"]["name"] == name
    assert result.stderr == ""


def test_parent_help_omits_hidden_aliases():
    """Hidden shortcuts stay out of the parent list, including env."""
    commands = _discovered_commands()
    names = {" ".join((*parents, name)) for parents, name, _alias in commands}
    assert "environment remove" in names
    assert "hosts list" in names
    assert "apps search" in names
    visible = [(parents, name, alias) for parents, name, alias in commands if alias]
    assert visible == []
    hidden = {
        (): {"val": "validate", "sh": "shell", "cfg": "config", "env": "environment"},
        ("config",): {"top": "topology"},
        ("apps",): {"sea": "search"},
        ("environment",): {"rm": "remove"},
    }
    for parents, mapping in hidden.items():
        for alias, canonical in mapping.items():
            short = run_spa_inprocess(["--no-agent", *parents, alias, "--help"])
            long = run_spa_inprocess(["--no-agent", *parents, canonical, "--help"])
            assert short.returncode == 0, (parents, alias, short.stderr)
            assert short.stdout == long.stdout


@pytest.mark.parametrize(
    "argv",
    [
        ["deploy", "--ansible-output", "-v"],
        ["dep", "-v", "--ansible-output"],
        ["hosts", "provision", "-v"],
        ["destroy", "-v"],
        ["suspend", "-v"],
        ["resume", "-v"],
        ["run", "-v"],
        ["logs", "-v"],
        ["hosts", "list", "-s"],
    ],
)
def test_verbose_is_accepted_after_the_subcommand(argv):
    result = run_spa_inprocess(["--no-agent", *argv, "--help"])
    assert result.returncode == 0, result.stderr
    assert "unrecognized arguments" not in result.stderr


def test_hosts_list_status_short_flag_is_s_not_v():
    help_out = run_spa_inprocess(["--no-agent", "hosts", "list", "--help"])
    assert help_out.returncode == 0, help_out.stderr
    assert "-s, --status" in help_out.stdout
    assert "Same as --status" not in help_out.stdout
    rejected = run_spa(["--no-agent", "hosts", "list", "-v"])
    assert rejected.returncode != 0
    assert "unrecognized arguments" in rejected.stderr


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


def _defined_options(help_text: str) -> set[str]:
    """Long options argparse defines, not flags named only inside an example."""
    return set(re.findall(r"(?m)^\s+(?:-[A-Za-z],\s+)?(--[A-Za-z0-9-]+)", help_text))


def _help_action_names():
    """Action names advertised by help, including reserved catalog operands."""
    root = run_spa_inprocess(["--no-agent", "--help"])
    assert root.returncode == 0, root.stderr
    names = set()
    for name, _alias in _command_rows(root.stdout):
        names.add("agent schema" if name == "agent" else name)
    for parent in ("environment", "hosts", "apps", "config", "skills", "venv", "completion", "architecture", "licenses", "provider", "version", "self"):
        child = run_spa_inprocess(["--no-agent", parent, "--help"])
        assert child.returncode == 0, child.stderr
        for name, _alias in _command_rows(child.stdout):
            if parent == "apps" and name == "content-packs":
                nested = run_spa_inprocess(
                    ["--no-agent", "apps", "content-packs", "--help"]
                )
                assert nested.returncode == 0, nested.stderr
                for nested_name, _nested_alias in _command_rows(nested.stdout):
                    names.add("apps content-packs %s" % nested_name)
                continue
            if parent == "config" and name == "header":
                nested = run_spa_inprocess(["--no-agent", "config", "header", "--help"])
                assert nested.returncode == 0, nested.stderr
                for nested_name, _nested_alias in _command_rows(nested.stdout):
                    names.add("config header %s" % nested_name)
                continue
            if parent == "config" and name == "move":
                names.add("config move")
                nested = run_spa_inprocess(["--no-agent", "config", "move", "--help"])
                assert nested.returncode == 0, nested.stderr
                for nested_name, _nested_alias in _command_rows(nested.stdout):
                    names.add("config move %s" % nested_name)
                continue
            if parent == "config" and name == "templates":
                names.add("config templates")
                nested = run_spa_inprocess(["--no-agent", "config", "templates", "--help"])
                assert nested.returncode == 0, nested.stderr
                for nested_name, _nested_alias in _command_rows(nested.stdout):
                    names.add("config templates %s" % nested_name)
                continue
            if parent == "provider" and name == "aws":
                names.add("provider aws")
                nested = run_spa_inprocess(["--no-agent", "provider", "aws", "--help"])
                assert nested.returncode == 0, nested.stderr
                aws_folders = {
                    "regions",
                    "amis",
                    "instance-types",
                    "key-pairs",
                    "security-groups",
                }
                for nested_name, _nested_alias in _command_rows(nested.stdout):
                    if nested_name in aws_folders:
                        continue
                    names.add("provider aws %s" % nested_name)
                continue
            if parent == "provider" and name == "ccm":
                continue
            names.add("%s %s" % (parent, name))
    catalogs = (
        (["run", "--help"], "spa run list", "run list"),
        (["init", "--help"], "spa init list", "init list"),
        (["environment", "init", "--help"], "spa environment init list", "environment init list"),
        (["logs", "--help"], "spa logs list", "logs list"),
    )
    for argv, phrase, label in catalogs:
        text = run_spa_inprocess(["--no-agent", *argv])
        assert text.returncode == 0, text.stderr
        flattened = " ".join(text.stdout.split())
        assert phrase in flattened, phrase
        names.add(label)
    for resource in ("regions", "amis", "instance-types", "key-pairs", "security-groups"):
        listed = run_spa_inprocess(["--no-agent", "provider", "aws", resource, "--help"])
        assert listed.returncode == 0, listed.stderr
        for name, _alias in _command_rows(listed.stdout):
            names.add("provider aws %s %s" % (resource, name))
    names.add("provider")
    names.add("provider ccm")
    ccm_help = run_spa_inprocess(["--no-agent", "provider", "ccm", "--help"])
    assert ccm_help.returncode == 0, ccm_help.stderr
    ccm_folders = {
        "operating-systems",
        "instance-types",
        "disk-storage",
        "business-purposes",
        "operation-hours",
        "ssh-keys",
        "ttl",
    }
    for nested_name, _nested_alias in _command_rows(ccm_help.stdout):
        if nested_name in ccm_folders:
            continue
        names.add("provider ccm %s" % nested_name)
    for resource in (
        "operating-systems",
        "instance-types",
        "disk-storage",
        "business-purposes",
        "operation-hours",
        "ssh-keys",
        "ttl",
    ):
        listed = run_spa_inprocess(["--no-agent", "provider", "ccm", resource, "--help"])
        assert listed.returncode == 0, listed.stderr
        for name, _alias in _command_rows(listed.stdout):
            names.add("provider ccm %s %s" % (resource, name))
    return names


def test_agent_schema_is_complete_and_documented():
    result = run_spa_inprocess(["agent", "schema"])
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    commands = payload["data"]["commands"]
    schema_names = {row["name"] for row in commands}
    assert schema_names == _help_action_names()
    encoded = json.dumps(commands)
    assert "--list" not in encoded
    for row in commands:
        assert row.get("summary"), row["name"]
        for flag in row.get("flags", []):
            assert flag.get("long"), (row["name"], flag)
            assert flag.get("help"), (row["name"], flag)

    by_name = {row["name"]: row for row in commands}
    for name in ("hosts provision", "deploy", "destroy", "suspend", "resume"):
        assert by_name[name]["requires_confirmation"] is True
        assert "--yes" in {flag["long"] for flag in by_name[name]["flags"]}

    run_flags = {flag["long"] for flag in by_name["run"]["flags"]}
    assert {"--hosts", "--yes", "--apps-playbook"} <= run_flags
    assert "--list" not in run_flags
    assert by_name["apps download"]["requires_confirmation"] is True
    assert "--yes" in {flag["long"] for flag in by_name["apps download"]["flags"]}
    assert "--extract" in {flag["long"] for flag in by_name["apps download"]["flags"]}
    assert "--overwrite" in {flag["long"] for flag in by_name["apps download"]["flags"]}
    assert "--source" in {flag["long"] for flag in by_name["apps snippet"]["flags"]}
    assert "--customize" in {flag["long"] for flag in by_name["apps snippet"]["flags"]}
    search_flags = {flag["long"] for flag in by_name["apps search"]["flags"]}
    assert {"--limit", "--type", "--kind"} <= search_flags
    assert "--markdown" in {flag["long"] for flag in by_name["agent schema"]["flags"]}
    assert "features" not in by_name
    assert "--markdown" in {flag["long"] for flag in by_name["config schema"]["flags"]}
    assert by_name["config search"]["positionals"][0]["name"] == "QUERY"
    assert by_name["config explain"]["positionals"][0]["name"] == "PATH"
    assert "config search" in by_name["config schema"]["summary"]

    for parent, banned in (
        ("config", ("--keys", "--command")),
        ("hosts", ("--status", "--hosts")),
        (
            "provider aws",
            (
                "--list-regions",
                "--name-filter",
                "--family",
                "--check-auth",
                "--latest-ami",
                "--describe-ami",
                "--validate",
                "--survey",
                "--region",
                "--os",
                "--details",
            ),
        ),
    ):
        options = _defined_options(
            run_spa_inprocess(["--no-agent", *parent.split(), "--help"]).stdout
        )
        for flag in banned:
            assert flag not in options, parent
    amis = run_spa_inprocess(["--no-agent", "provider", "aws", "amis", "list", "--help"]).stdout
    types = run_spa_inprocess(
        ["--no-agent", "provider", "aws", "instance-types", "list", "--help"]
    ).stdout
    assert "--family" not in amis
    assert "--name-filter" not in types

    bare_parents = {
        "config": ("spa config search QUERY", "spa config explain PATH", "spa config get [PATH]"),
        "hosts": (
            "spa hosts list",
            "spa hosts ssh NAME",
            "spa hosts copy SRC DST",
            "spa hosts register NAME --ssh-host HOST --user USER --key PATH --yes",
        ),
        "apps": ("spa apps search QUERY", "spa apps snippet APP_ID", "spa apps download APP_ID --yes"),
        "environment": (
            "spa environment list",
            "spa environment init NAME",
            "spa environment set",
            "spa environment remove NAME",
        ),
        "run": ("spa run list", "spa run NAME --help", "spa run NAME"),
        "logs": ("spa logs list", "spa logs RUN_ID", "spa logs --last"),
        "licenses": ("spa licenses list", "spa licenses add FILE --yes"),
        "provider aws": (
            "spa provider aws check-auth",
            "spa provider aws latest-ami --os OS",
            "spa provider aws describe-ami --ami-id AMI",
            "spa provider aws validate",
            "spa provider aws survey",
            "spa provider aws regions list",
        ),
    }
    for parent, phrases in bare_parents.items():
        argv = parent.split()
        human = run_spa_inprocess(["--no-agent", *argv])
        assert human.returncode == 2, parent
        assert human.stdout.strip() == "", parent
        assert "the following arguments are required" not in human.stderr, parent
        for phrase in phrases:
            assert phrase in human.stderr, (parent, phrase)
        agent = run_spa_inprocess(["--json", *argv])
        assert agent.returncode == 2, parent
        assert agent.stderr == "", parent
        body = json.loads(agent.stdout)
        assert body["ok"] is False
        assert body.get("error")
        assert "data" not in body
        for phrase in phrases:
            assert phrase in body["error"], (parent, phrase)

    operands = (
        (["config", "search"], "spa config search needs QUERY."),
        (["apps", "search"], "spa apps search needs QUERY."),
        (["apps", "snippet"], "spa apps snippet needs APP_ID."),
        (["apps", "download"], "spa apps download needs APP_ID."),
        (["hosts", "ssh"], "spa hosts ssh needs NAME."),
        (["shell"], "spa shell needs NAME."),
        (["sh"], "spa shell needs NAME."),
        (["environment", "remove"], "spa environment remove needs NAME."),
        (["feat"], "spa features was removed."),
    )
    for argv, phrase in operands:
        human = run_spa_inprocess(["--no-agent", *argv])
        assert human.returncode == 2, argv
        assert phrase in human.stderr, argv
        assert "the following arguments are required" not in human.stderr, argv
        agent = run_spa_inprocess(["--json", *argv])
        assert agent.returncode == 2, argv
        assert agent.stderr == "", argv
        body = json.loads(agent.stdout)
        assert body["ok"] is False and "data" not in body
        assert phrase in body["error"], argv

    aws = run_spa_inprocess(["--no-agent", "provider", "aws"])
    assert aws.returncode == 2, aws.stderr
    assert "spa provider aws needs an action." in aws.stderr
    assert "spa provider aws regions list" in aws.stderr
    assert "spa provider aws check-auth" in aws.stderr
    assert "spa aws --check-auth" not in aws.stderr


def test_licenses_list_is_the_catalog():
    """spa licenses is a catalog parent. list is the action; the bare parent exits 2."""
    from spa.agent import COMMAND_SCHEMA

    needs_action = (
        "spa licenses needs an action.\n"
        "List: spa licenses list\n"
        "Add:  spa licenses add FILE --yes"
    )
    for parent in ("licenses", "lic"):
        human = run_spa(["--no-agent", parent])
        assert human.returncode == 2, parent
        assert human.stdout.strip() == "", parent
        assert human.stderr.strip() == needs_action, parent
        agent = run_spa(["--json", parent])
        assert agent.returncode == 2, parent
        assert agent.stderr == "", parent
        body = json.loads(agent.stdout)
        assert body["ok"] is False
        assert body["schema_version"] == 1
        assert "data" not in body
        assert body["error"] == needs_action

    old_form = run_spa(["licenses", "--json"])
    assert old_form.returncode == 2
    assert old_form.stderr == ""
    old_body = json.loads(old_form.stdout)
    assert old_body["ok"] is False
    assert old_body["schema_version"] == 1
    assert "data" not in old_body
    assert old_body["error"] == needs_action

    help_text = run_spa_inprocess(["--no-agent", "licenses", "--help"])
    assert help_text.returncode == 0, help_text.stderr
    assert "usage: spa licenses" in help_text.stdout
    assert "Aliases: lic" in help_text.stdout
    assert "list" in help_text.stdout
    assert "add" in help_text.stdout
    list_help = run_spa_inprocess(["--no-agent", "licenses", "list", "--help"])
    assert list_help.returncode == 0, list_help.stderr
    assert "usage: spa licenses list" in list_help.stdout
    for flag in ("--software-dir", "--config", "--details", "--no-env-recommend"):
        assert flag in list_help.stdout
        assert flag not in _defined_options(help_text.stdout)
    add_help = run_spa_inprocess(["--no-agent", "licenses", "add", "--help"])
    assert add_help.returncode == 0, add_help.stderr
    assert "usage: spa licenses add" in add_help.stdout
    for flag in ("--software-dir", "--force", "--replace", "--yes"):
        assert flag in add_help.stdout
    for flag in ("--software-dir", "--force", "--replace"):
        assert flag not in _defined_options(help_text.stdout)

    by_name = {row["name"]: row for row in COMMAND_SCHEMA["commands"]}
    assert "licenses list" in by_name
    assert "licenses add" in by_name
    assert by_name["licenses"]["example"] == "spa --agent licenses list"
    assert "add" in by_name["licenses"]["summary"].lower()
    assert "flags" not in by_name["licenses"]
    listed = by_name["licenses list"]
    assert listed["example"] == "spa --agent licenses list"
    flag_names = {flag["long"] for flag in listed.get("flags") or []}
    assert flag_names == {"--software-dir", "--config", "--details", "--no-env-recommend"}
    added = by_name["licenses add"]
    assert added["example"] == "spa --agent licenses add FILE --yes"
    assert added["requires_confirmation"] is True
    add_flags = {flag["long"] for flag in added.get("flags") or []}
    assert add_flags == {"--software-dir", "--force", "--replace", "--yes"}
    assert added["positionals"][0]["name"] == "FILE"

    parent_help = run_spa(["--agent", "licenses", "--help"])
    assert parent_help.returncode == 0, parent_help.stderr
    parent_payload = json.loads(parent_help.stdout)
    assert parent_payload["ok"] is True
    assert parent_payload["schema_version"] == 1
    assert parent_payload["data"]["name"] == "licenses"
    list_schema = run_spa(["--agent", "licenses", "list", "--help"])
    assert list_schema.returncode == 0, list_schema.stderr
    list_payload = json.loads(list_schema.stdout)
    assert list_payload["ok"] is True
    assert list_payload["schema_version"] == 1
    assert list_payload["data"]["name"] == "licenses list"
    add_schema = run_spa(["--agent", "licenses", "add", "--help"])
    assert add_schema.returncode == 0, add_schema.stderr
    add_payload = json.loads(add_schema.stdout)
    assert add_payload["ok"] is True
    assert add_payload["schema_version"] == 1
    assert add_payload["data"]["name"] == "licenses add"


def _license_add_xml(*, expiration="4102444800"):
    return (
        "<license><signature>must-not-be-emitted</signature><payload>"
        "<guid>must-not-be-emitted</guid><type>enterprise</type>"
        "<group_id>Enterprise</group_id><creation_time>1700000000</creation_time>"
        "<expiration_time>%s</expiration_time></payload></license>" % expiration
    )


def test_licenses_add_human_and_agent_mutation_stack(tmp_path):
    """Copy + envelope. A stacked size-extension leaves the canonical unchanged."""
    software = tmp_path / "Software"
    software.mkdir()
    nfr = tmp_path / "Splunk_Enterprise_NFR_lab.License"
    nfr.write_text(_license_add_xml(), encoding="utf-8")
    first = run_spa(
        ["--no-agent", "licenses", "add", str(nfr), "--software-dir", str(software), "--yes"]
    )
    assert first.returncode == 0, first.stderr
    assert "Copied Splunk_Enterprise_NFR_lab.License" in first.stdout
    assert "must-not-be-emitted" not in first.stdout + first.stderr
    canonical = software / "Splunk_Enterprise.lic"
    assert canonical.is_symlink()
    assert canonical.readlink() == Path("Splunk_Enterprise_NFR_lab.License")

    pending = tmp_path / "Splunk_Enterprise_NFR_pending.License"
    pending.write_text(_license_add_xml(), encoding="utf-8")
    missing_yes = run_spa(
        ["--agent", "licenses", "add", str(pending), "--software-dir", str(software)]
    )
    assert missing_yes.returncode == 1
    missing_body = json.loads(missing_yes.stdout)
    assert missing_body["ok"] is False
    assert "requires -y/--yes" in missing_body["error"]
    assert missing_yes.stderr == ""
    assert not (software / pending.name).exists()

    non_tty = tmp_path / "Splunk_Enterprise_NFR_tty.License"
    non_tty.write_text(_license_add_xml(), encoding="utf-8")
    human_missing = run_spa(
        ["--no-agent", "licenses", "add", str(non_tty), "--software-dir", str(software)]
    )
    assert human_missing.returncode == 2
    assert "-y/--yes" in human_missing.stderr
    assert "agent mode" not in human_missing.stderr
    assert not (software / non_tty.name).exists()

    extension = tmp_path / "Splunk_Enterprise_50GB.lic"
    extension.write_text(_license_add_xml(), encoding="utf-8")
    human = run_spa(
        [
            "--no-agent",
            "licenses",
            "add",
            str(extension),
            "--software-dir",
            str(software),
            "--yes",
        ]
    )
    assert human.returncode == 0, human.stderr
    assert "Copied Splunk_Enterprise_50GB.lic" in human.stdout
    assert "canonical unchanged" in human.stdout
    assert "must-not-be-emitted" not in human.stdout + human.stderr
    assert "<license>" not in human.stdout
    assert canonical.readlink() == Path("Splunk_Enterprise_NFR_lab.License")

    extra = tmp_path / "Splunk_Enterprise_100GB.lic"
    extra.write_text(_license_add_xml(), encoding="utf-8")
    agent = run_spa(
        [
            "--agent",
            "licenses",
            "add",
            str(extra),
            "--software-dir",
            str(software),
            "--yes",
        ]
    )
    assert agent.returncode == 0, agent.stderr
    assert agent.stderr == ""
    payload = json.loads(agent.stdout)
    assert payload["ok"] is True
    data = payload["data"]
    assert data["copied"] is True
    assert data["basename"] == "Splunk_Enterprise_100GB.lic"
    assert data["replaced"] is False
    assert data["status"] == "valid"
    assert "must-not-be-emitted" not in agent.stdout
    assert "<license>" not in agent.stdout
    assert "path" not in data
    assert canonical.readlink() == Path("Splunk_Enterprise_NFR_lab.License")
    next_ids = [row["id"] for row in data.get("next") or []]
    assert "licenses.list" in next_ids


def test_licenses_add_agent_next_sets_license_file_when_env_config_exists(tmp_path):
    dest = write_min_env(tmp_path / "env")
    (dest / "config" / "splunk_config.yml").write_text(
        "splunk_defaults:\n  splunk_admin_password: x\n",
        encoding="utf-8",
    )
    software = tmp_path / "Software"
    software.mkdir()
    src = tmp_path / "Splunk_Enterprise_NFR_lab.License"
    src.write_text(_license_add_xml(), encoding="utf-8")
    result = run_spa(
        [
            "--agent",
            "licenses",
            "add",
            str(src),
            "--software-dir",
            str(software),
            "--yes",
        ],
        extra_env=min_env_vars(dest),
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    nxt = {row["id"]: row for row in payload["data"].get("next") or []}
    assert "licenses.list" in nxt
    write = nxt["config.set.license_file"]
    assert "Splunk_Enterprise.lic" in write["ask"]
    assert "Splunk_Enterprise_NFR_lab.License" in write["ask"]
    assert "spa --agent config set splunk_defaults.splunk_license_file" in write["command"]
    config = (dest / "config" / "splunk_config.yml").read_text(encoding="utf-8")
    assert "splunk_license_file" not in config


def test_templates_list_is_the_catalog():
    """spa config templates is a catalog parent. list is the action; the bare parent exits 2."""
    from spa.agent import COMMAND_SCHEMA

    needs_action = (
        "spa config templates needs an action.\n"
        "List: spa config templates list"
    )
    for argv in (["config", "templates"], ["config", "tpl"]):
        human = run_spa(["--no-agent", *argv])
        assert human.returncode == 2, argv
        assert human.stdout.strip() == "", argv
        assert human.stderr.strip() == needs_action, argv
        agent = run_spa(["--json", *argv])
        assert agent.returncode == 2, argv
        assert agent.stderr == "", argv
        body = json.loads(agent.stdout)
        assert body["ok"] is False
        assert body["schema_version"] == 1
        assert "data" not in body
        assert body["error"] == needs_action

    help_text = run_spa_inprocess(["--no-agent", "config", "templates", "--help"])
    assert help_text.returncode == 0, help_text.stderr
    assert "usage: spa config templates" in help_text.stdout
    assert "Aliases: tpl" in help_text.stdout
    assert "list" in help_text.stdout
    list_help = run_spa_inprocess(["--no-agent", "config", "templates", "list", "--help"])
    assert list_help.returncode == 0, list_help.stderr
    assert "usage: spa config templates list" in list_help.stdout

    by_name = {row["name"]: row for row in COMMAND_SCHEMA["commands"]}
    assert "config templates list" in by_name
    assert by_name["config templates"]["example"] == "spa --agent config templates list"
    assert "flags" not in by_name["config templates"]
    listed = by_name["config templates list"]
    assert listed["example"] == "spa --agent config templates list"
    merge = by_name["config merge"]
    assert merge["example"] == "spa --agent config merge remote-provider --yes"
    template = next(item for item in merge["positionals"] if item["name"] == "TEMPLATE")
    assert template["completes_from"] == "config templates list"

    parent_help = run_spa(["--agent", "config", "templates", "--help"])
    assert parent_help.returncode == 0, parent_help.stderr
    parent_payload = json.loads(parent_help.stdout)
    assert parent_payload["ok"] is True
    assert parent_payload["schema_version"] == 1
    assert parent_payload["data"]["name"] == "config templates"
    list_schema = run_spa(["--agent", "config", "templates", "list", "--help"])
    assert list_schema.returncode == 0, list_schema.stderr
    list_payload = json.loads(list_schema.stdout)
    assert list_payload["ok"] is True
    assert list_payload["schema_version"] == 1
    assert list_payload["data"]["name"] == "config templates list"


PROVIDER_NEEDS_ACTION = (
    "spa provider needs an action.\n"
    "AWS: spa provider aws check-auth"
)
PROVIDER_NEEDS_ACTION_WITH_CCM = (
    PROVIDER_NEEDS_ACTION + "\n"
    "CCM: spa provider ccm check-auth"
)
PROVIDER_CCM_NEEDS_ACTION = (
    "spa provider ccm needs an action.\n"
    "spa provider ccm check-auth\n"
    "spa provider ccm survey\n"
    "spa provider ccm operating-systems list\n"
    "spa provider ccm instance-types list\n"
    "spa provider ccm disk-storage list\n"
    "spa provider ccm business-purposes list\n"
    "spa provider ccm operation-hours list\n"
    "spa provider ccm ssh-keys list\n"
    "spa provider ccm ttl extend --days N --yes\n"
    "spa provider ccm operation-hours set manual|business_hours --yes"
)


@pytest.mark.parametrize("token", [None, "test-ccm-pat-value"])
def test_human_parent_help_lists_canonical_provider(token):
    extra = {"CCM_TOKEN": token} if token else None
    parent = run_spa(["--no-agent", "--help"], extra_env=extra)
    assert parent.returncode == 0, parent.stderr
    names = {name for name, _alias in _command_rows(parent.stdout)}
    assert "provider" in names
    assert "aws" not in names
    assert "pro" not in names
    assert "provider (pro)" not in parent.stdout
    if token:
        assert token not in parent.stdout
        assert token not in parent.stderr


def test_human_parent_help_lists_canonical_provider_for_a_ccm_env(tmp_path):
    dest = write_min_env(tmp_path)
    (dest / "config" / "splunk_config.yml").write_text(
        "ccm:\n  instance_type: t3a.medium\n",
        encoding="utf-8",
    )
    parent = run_spa_inprocess(
        ["--no-agent", "--help"],
        extra_env={"SPA_ENV_DIR": str(dest), "SPA_HOME": str(PROJECT_ROOT)},
    )
    assert parent.returncode == 0, parent.stderr
    names = {name for name, _alias in _command_rows(parent.stdout)}
    assert "provider" in names
    assert "pro" not in names


@pytest.mark.parametrize("token", [None, "test-ccm-pat-value"])
def test_human_invalid_choice_lists_canonical_provider(token):
    extra = {"CCM_TOKEN": token} if token else None
    result = run_spa(["--no-agent", "nosuch"], extra_env=extra)
    assert result.returncode == 2
    assert "invalid choice" in result.stderr
    assert "provider" in result.stderr
    assert "'aws'" not in result.stderr
    assert "'pro'" not in result.stderr
    if token:
        assert token not in result.stderr


def test_agent_invalid_choice_lists_provider_without_ccm_audience():
    result = run_spa(["--agent", "nosuch"])
    assert result.returncode == 2
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert payload["schema_version"] == 1
    assert "data" not in payload
    assert "invalid choice" in payload["error"]
    assert "provider" in payload["error"]
    assert result.stderr == ""


def test_provider_help_shows_hidden_pro_alias_and_public_aws():
    help_text = run_spa_inprocess(["--no-agent", "provider", "--help"])
    assert help_text.returncode == 0, help_text.stderr
    assert "usage: spa provider" in help_text.stdout
    assert "Aliases: pro" in help_text.stdout
    names = {name for name, _alias in _command_rows(help_text.stdout)}
    assert "aws" in names
    assert "ccm" in names
    via_alias = run_spa_inprocess(["--no-agent", "pro", "--help"])
    assert via_alias.returncode == 0, via_alias.stderr
    assert via_alias.stdout == help_text.stdout
    with_ccm = run_spa(
        ["--no-agent", "provider", "--help"],
        extra_env={"CCM_TOKEN": "test-ccm-pat-value"},
    )
    assert with_ccm.returncode == 0, with_ccm.stderr
    ccm_names = {name for name, _alias in _command_rows(with_ccm.stdout)}
    assert "aws" in ccm_names
    assert "ccm" in ccm_names
    assert "test-ccm-pat-value" not in with_ccm.stdout


def test_agent_schema_includes_provider_aws_and_gates_ccm(agent_schema):
    schema = agent_schema
    assert schema["ok"] is True
    encoded = json.dumps(schema)
    names = {row["name"] for row in schema["data"]["commands"]}
    assert "provider aws check-auth" in names
    assert "aws check-auth" not in names
    assert "aws" not in names
    assert "provider ccm check-auth" in names
    assert "provider ccm survey" in names
    assert "provider ccm ttl extend" in names
    assert "provider ccm operation-hours set" in names
    for row in schema["data"]["commands"]:
        if row["name"] == "provider" or row["name"].startswith("provider "):
            assert "audience" not in row, row["name"]
    assert "spa pro " not in encoded
    assert not any(
        (row.get("example") or "").startswith("spa pro ")
        or row["name"] == "pro"
        or row["name"].startswith("pro ")
        for row in schema["data"]["commands"]
    )
    by_name = {row["name"]: row for row in schema["data"]["commands"]}
    assert by_name["provider"]["example"] == "spa --agent provider aws check-auth"


def test_init_list_provider_choice_includes_ccm_when_token_is_set():
    from spa.providers import provider_ids

    result = run_spa(
        ["--agent", "init", "list"],
        extra_env={"CCM_TOKEN": "test-ccm-pat-value"},
    )
    assert result.returncode == 0, result.stderr
    nxt = json.loads(result.stdout)["data"]["next"]
    provider = next(row for row in nxt if row["id"] == "provider")
    assert provider["choice"]["allowed"] == list(provider_ids())
    assert provider["choice"]["allowed"][0] == "ccm"
    assert "test-ccm-pat-value" not in result.stdout


def test_provider_and_provider_ccm_bare_parents_exit_2():
    for argv, human_message, agent_message in (
        (["provider"], PROVIDER_NEEDS_ACTION_WITH_CCM, PROVIDER_NEEDS_ACTION_WITH_CCM),
        (["pro"], PROVIDER_NEEDS_ACTION_WITH_CCM, PROVIDER_NEEDS_ACTION_WITH_CCM),
        (["provider", "ccm"], PROVIDER_CCM_NEEDS_ACTION, PROVIDER_CCM_NEEDS_ACTION),
        (["pro", "ccm"], PROVIDER_CCM_NEEDS_ACTION, PROVIDER_CCM_NEEDS_ACTION),
    ):
        human = run_spa(["--no-agent", *argv])
        assert human.returncode == 2, argv
        assert human.stdout.strip() == "", argv
        for line in human_message.splitlines():
            assert line.rstrip(".") in human.stderr, (argv, line)
        agent = run_spa(["--json", *argv])
        assert agent.returncode == 2, argv
        assert agent.stderr == "", argv
        body = json.loads(agent.stdout)
        assert body["ok"] is False
        assert body["schema_version"] == 1
        assert "data" not in body
        for line in agent_message.splitlines():
            assert line.rstrip(".") in body["error"], (argv, line)
    with_ccm = run_spa(
        ["--no-agent", "provider"],
        extra_env={"CCM_TOKEN": "test-ccm-pat-value"},
    )
    assert with_ccm.returncode == 2, with_ccm.stderr
    for line in PROVIDER_NEEDS_ACTION_WITH_CCM.splitlines():
        assert line.rstrip(".") in with_ccm.stderr, line
    assert "test-ccm-pat-value" not in with_ccm.stderr
