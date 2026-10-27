"""Release contract for every public ``spa`` help and schema surface."""

import json
import re
from pathlib import Path

import pytest

from spa_testutil import PROJECT_ROOT, run_spa, run_spa_init, write_min_env


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
            "venv",
            "environment (env)",
            "provision",
            "deploy",
            "destroy",
            "suspend",
            "resume",
            "run",
            "logs",
            "hosts",
            "shell",
            "aws",
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
        ],
    ),
    (
        ["init", "--help"],
        [
            "usage: spa init",
            "env_dir",
            "--example",
            "--provider",
            "spa init list",
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
        ["usage: spa validate", "--config", "--check-licenses", "--splunk-config-aws"],
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
            "path",
            "create",
            "reinstall",
            "upgrade",
            "rebuild",
        ],
    ),
    (
        ["env", "--help"],
        [
            "usage: spa environment",
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
            "--env-dir",
            "--software-dir",
            "--baseconfig-dir",
            "--apps-dir",
            "--default",
            "--provider",
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
            "topology",
            "provider",
            "spa config search QUERY",
            "spa config explain PATH",
            "spa config schema --markdown",
        ],
    ),
    (
        ["config", "set", "--help"],
        ["usage: spa config set", "PATH", "VALUE", "--value-file", "--from-env", "--dry-run", "--expect-revision", "--resolve"],
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
        ],
    ),
    (
        ["apps", "search", "--help"],
        ["usage: spa apps search", "--limit", "--type", "--kind", "addon", "premium_itsi", "keywords"],
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
        ["usage: spa apps add", "--roles", "--set", "--content-pack", "--install-all-content-packs", "--dry-run"],
    ),
    (
        ["apps", "remove", "--help"],
        ["usage: spa apps remove", "--content-pack", "--dry-run", "APP_ID_OR_NAME"],
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
        ["usage: spa logs", "--last", "--follow", "run_id", "--ansible-output"],
    ),
    (
        ["hosts", "--help"],
        ["usage: spa hosts", "ACTION", "list", "ssh", "copy", "register", "unregister", "check", "spa hosts check"],
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
            "--address",
            "--user",
            "--key",
            "--role",
        ],
    ),
    (
        ["hosts", "check", "--help"],
        ["spa deploy", "Does not deploy", "--hosts"],
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
            "regions",
            "amis",
            "spa aws regions list",
            "--latest-ami",
            "--describe-ami",
            "--validate",
            "--survey",
        ],
    ),
    (
        ["aws", "regions", "--help"],
        ["usage: spa aws regions", "list"],
    ),
    (
        ["aws", "regions", "list", "--help"],
        ["usage: spa aws regions list"],
    ),
    (
        ["aws", "amis", "list", "--help"],
        ["usage: spa aws amis list", "--region", "--name-filter", "--owners", "--max-results", "--os"],
    ),
    (
        ["aws", "instance-types", "list", "--help"],
        ["usage: spa aws instance-types list", "--region", "--family"],
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


def test_venv_uses_one_parser_per_action():
    bare = run_spa(["--no-agent", "venv"])
    assert bare.returncode == 2
    assert bare.stdout.strip() == ""
    for action in ("path", "create", "reinstall", "upgrade", "rebuild"):
        assert "spa venv %s" % action in bare.stderr
    assert "--rebuild" not in bare.stderr
    rebuild = run_spa(["--no-agent", "venv", "rebuild", "--help"])
    assert rebuild.returncode == 0, rebuild.stderr
    assert "usage: spa venv rebuild" in rebuild.stdout
    assert "--shared" in rebuild.stdout
    assert "--yes" in rebuild.stdout
    path = run_spa(["--no-agent", "venv", "path", "--help"])
    assert "usage: spa venv path" in path.stdout
    assert "--yes" not in path.stdout
    rejected = run_spa(["--no-agent", "venv", "--rebuild"])
    assert rejected.returncode == 2
    schema = json.loads(run_spa(["--no-agent", "agent", "schema"]).stdout)
    by_name = {row["name"]: row for row in schema["data"]["commands"]}
    assert by_name["venv rebuild"]["example"] == "spa venv rebuild --shared --yes"
    assert "--rebuild" not in json.dumps(by_name["venv path"])


def test_schema_and_help_teach_agent_not_the_json_envelope_flag():
    schema = json.loads(run_spa(["--no-agent", "agent", "schema"]).stdout)
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
    root = run_spa(["--no-agent", "--help"])
    assert "Synonym of --agent" in root.stdout


def test_short_aliases_stay_on_the_command_help_page():
    """Parent help and agent errors use the canonical name. The command page lists Aliases:."""
    parent = run_spa(["--no-agent", "--help"])
    assert parent.returncode == 0, parent.stderr
    assert "validate (val)" not in parent.stdout
    assert re.search(r"\bval\b", parent.stdout) is None
    assert "environment (env)" in parent.stdout

    human = run_spa(["--no-agent", "validate", "--help"])
    assert "usage: spa validate" in human.stdout
    assert "Aliases: val" in human.stdout
    via_alias = run_spa(["--no-agent", "val", "--help"])
    assert via_alias.stdout == human.stdout

    shell = run_spa(["--no-agent", "shell", "--help"])
    assert "usage: spa shell" in shell.stdout
    assert "Aliases: sh" in shell.stdout
    assert re.search(r"\bsh\b", parent.stdout) is None

    agent = run_spa(["--agent", "nosuch"])
    assert agent.returncode == 2
    assert re.search(r"\bval\b", agent.stdout) is None
    assert "validate" in agent.stdout


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
    ("argv", "expect"),
    [
        (["--json", "validate", "--help"], "validate"),
        (["validate", "--json", "--help"], "validate"),
        (["--agent", "validate", "--help"], "validate"),
        (["validate", "--agent", "--help"], "validate"),
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


def test_apps_add_help_names_kinds_flags_and_the_next_action():
    result = run_spa(["--no-agent", "apps", "add", "--help"])
    assert result.returncode == 0, result.stderr
    pieces: list[str] = []
    for line in result.stdout.splitlines():
        stripped = line.strip()
        if pieces and line.startswith(" ") and pieces[-1].endswith("-"):
            pieces[-1] += stripped
        else:
            pieces.append(stripped)
    text = " ".join(pieces)
    for phrase in (
        "edits splunk_config.yml",
        "does not deploy",
        "Normal app",
        "1841",
        "Content Library 5391",
        "7294",
        "spa apps content-packs list 5391",
        "spa validate",
        "spa deploy --yes",
        "required only for normal apps",
        "rejected for ITSI",
        "default latest",
        "default splunkbase",
        "Shorthand for --source local",
        "Mutually exclusive with --source",
        "repeatable",
        "mutually exclusive with --install-all-content-packs",
        "mutually exclusive with --content-pack",
        "without prompting or writing",
        "SHA-256 revision",
        "strict JSON",
        "use - for stdin",
        "agent mode never prompts",
    ):
        assert phrase in text, phrase
    from spa.agent import COMMAND_SCHEMA

    add = next(row for row in COMMAND_SCHEMA["commands"] if row["name"] == "apps add")
    for flag in add["flags"]:
        assert flag["help"] in text, flag["long"]


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

    for argv in (
        ["--agent", "aws", "--help"],
        ["--agent", "licenses", "--help"],
        ["--agent", "shell", "--help"],
    ):
        native = run_spa(argv)
        assert native.returncode == 0, native.stderr
        assert "usage: spa" in native.stdout
        assert not native.stdout.lstrip().startswith("{")


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


def test_parent_help_shows_only_the_documented_env_alias():
    """Hidden shortcuts stay out of the parent list. env remains visible."""
    commands = _discovered_commands()
    names = {" ".join((*parents, name)) for parents, name, _alias in commands}
    assert "environment remove" in names
    assert "hosts list" in names
    assert "apps search" in names
    visible = [(parents, name, alias) for parents, name, alias in commands if alias]
    assert visible == [((), "environment", "env")]
    hidden = {
        (): {"val": "validate", "sh": "shell", "cfg": "config"},
        ("config",): {"top": "topology"},
        ("apps",): {"sea": "search"},
        ("environment",): {"rm": "remove"},
    }
    for parents, mapping in hidden.items():
        for alias, canonical in mapping.items():
            short = run_spa(["--no-agent", *parents, alias, "--help"])
            long = run_spa(["--no-agent", *parents, canonical, "--help"])
            assert short.returncode == 0, (parents, alias, short.stderr)
            assert short.stdout == long.stdout


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


def _defined_options(help_text: str) -> set[str]:
    """Long options argparse defines, not flags named only inside an example."""
    return set(re.findall(r"(?m)^\s+(?:-[A-Za-z],\s+)?(--[A-Za-z0-9-]+)", help_text))


def _help_action_names():
    """Action names advertised by help, including reserved catalog operands."""
    root = run_spa(["--no-agent", "--help"])
    assert root.returncode == 0, root.stderr
    names = set()
    for name, _alias in _command_rows(root.stdout):
        names.add("agent schema" if name == "agent" else name)
    for parent in ("environment", "hosts", "apps", "config", "skills", "venv", "completion"):
        child = run_spa(["--no-agent", parent, "--help"])
        assert child.returncode == 0, child.stderr
        for name, _alias in _command_rows(child.stdout):
            if parent == "apps" and name == "content-packs":
                nested = run_spa(
                    ["--no-agent", "apps", "content-packs", "--help"]
                )
                assert nested.returncode == 0, nested.stderr
                for nested_name, _nested_alias in _command_rows(nested.stdout):
                    names.add("apps content-packs %s" % nested_name)
                continue
            if parent == "config" and name == "header":
                nested = run_spa(["--no-agent", "config", "header", "--help"])
                assert nested.returncode == 0, nested.stderr
                for nested_name, _nested_alias in _command_rows(nested.stdout):
                    names.add("config header %s" % nested_name)
                continue
            names.add("%s %s" % (parent, name))
    catalogs = (
        (["run", "--help"], "spa run list", "run list"),
        (["init", "--help"], "spa init list", "init list"),
        (["environment", "init", "--help"], "spa environment init list", "environment init list"),
        (["logs", "--help"], "spa logs list", "logs list"),
    )
    for argv, phrase, label in catalogs:
        text = run_spa(["--no-agent", *argv])
        assert text.returncode == 0, text.stderr
        flattened = " ".join(text.stdout.split())
        assert phrase in flattened, phrase
        names.add(label)
    for resource in ("regions", "amis", "instance-types", "key-pairs", "security-groups"):
        listed = run_spa(["--no-agent", "aws", resource, "--help"])
        assert listed.returncode == 0, listed.stderr
        for name, _alias in _command_rows(listed.stdout):
            names.add("aws %s %s" % (resource, name))
    return names


def test_agent_schema_is_complete_and_documented():
    result = run_spa(["agent", "schema"])
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    commands = payload["data"]["commands"]
    schema_names = {row["name"] for row in commands}
    assert schema_names == _help_action_names()
    retired = ("--list", "--list-regions", "--list-amis", "--list-instance-types", "--list-key-pairs", "--list-security-groups")
    encoded = json.dumps(commands)
    for flag in retired:
        assert flag not in encoded
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
        ("aws", ("--list-regions", "--name-filter", "--family")),
    ):
        options = _defined_options(run_spa(["--no-agent", parent, "--help"]).stdout)
        for flag in banned:
            assert flag not in options, parent
    amis = run_spa(["--no-agent", "aws", "list", "amis", "--help"]).stdout
    types = run_spa(["--no-agent", "aws", "list", "instance-types", "--help"]).stdout
    assert "--family" not in amis
    assert "--name-filter" not in types

    bare_parents = {
        "config": ("spa config search QUERY", "spa config explain PATH", "spa config get [PATH]"),
        "hosts": (
            "spa hosts list",
            "spa hosts ssh NAME",
            "spa hosts copy SRC DST",
            "spa hosts register NAME --address ADDRESS --user USER --key PATH --yes",
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
    }
    for parent, phrases in bare_parents.items():
        human = run_spa(["--no-agent", parent])
        assert human.returncode == 2, parent
        assert human.stdout.strip() == "", parent
        assert "the following arguments are required" not in human.stderr, parent
        for phrase in phrases:
            assert phrase in human.stderr, (parent, phrase)
        agent = run_spa(["--json", parent])
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
        (["environment", "remove"], "spa environment remove needs NAME."),
        (["feat"], "spa features was removed."),
    )
    for argv, phrase in operands:
        human = run_spa(["--no-agent", *argv])
        assert human.returncode == 2, argv
        assert phrase in human.stderr, argv
        assert "the following arguments are required" not in human.stderr, argv
        agent = run_spa(["--json", *argv])
        assert agent.returncode == 2, argv
        assert agent.stderr == "", argv
        body = json.loads(agent.stdout)
        assert body["ok"] is False and "data" not in body
        assert phrase in body["error"], argv

    aws = run_spa(["--no-agent", "aws"])
    assert aws.returncode == 2, aws.stderr
    assert "spa aws needs an operation." in aws.stderr
    assert "spa aws regions list" in aws.stderr
    assert "spa aws --check-auth" in aws.stderr
    aws_list = run_spa(["--no-agent", "aws", "list"])
    assert aws_list.returncode == 2, aws_list.stderr
    for kind in ("regions", "amis", "instance-types", "key-pairs", "security-groups"):
        assert "spa aws %s list" % kind in aws_list.stderr
