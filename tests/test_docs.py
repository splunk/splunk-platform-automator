"""Canonical operator docs exist and relative markdown links resolve."""

from __future__ import annotations

import ast
import re
import subprocess
from pathlib import Path

from spa.agent import format_schema_markdown
from spa.catalog import format_config_markdown
from spa_testutil import run_spa

import pytest

pytestmark = pytest.mark.local

PROJECT_ROOT = Path(__file__).resolve().parents[1]

CANONICAL_DOCS = {
    "apps.md",
    "architecture.md",
    "aws.md",
    "commands.md",
    "config-editing.md",
    "config-walkthrough.md",
    "config.md",
    "contributing.md",
    "install.md",
    "migrate.md",
    "secrets.md",
    "upgrade.md",
    "user-guide.md",
}

WELL_KNOWN_ROOT = {
    "AGENTS.md",
    "CHANGELOG.md",
    "README.md",
    "RELEASE.md",
    "ROADMAP.md",
}

KEBAB_MD = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*\.md$")
MD_LINK = re.compile(r"\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
CONFIG_CONTRACT_HEADING = re.compile(r"^### (CFG-[A-Z]+-\d{3})\b", re.MULTILINE)
CONFIG_CONTRACT_REFERENCE = re.compile(r"\b(CFG-[A-Z]+-\d{3})\b")
CONFIG_VERIFICATION = re.compile(
    r"^- `(CFG-[A-Z]+-\d{3})`: `(tests/test_config_contract\.py::[A-Za-z0-9_:]+)`$",
    re.MULTILINE,
)

# Versioned changelog is allowed to cite old paths; do not treat it as live docs.
SKIP_LINK_SCAN = {
    PROJECT_ROOT / "CHANGELOG.md",
}


def _docs_dir() -> Path:
    return PROJECT_ROOT / "docs"


def _markdown_for_links() -> list[Path]:
    paths: list[Path] = []
    for name in WELL_KNOWN_ROOT:
        path = PROJECT_ROOT / name
        if path not in SKIP_LINK_SCAN:
            paths.append(path)
    paths.extend(sorted(_docs_dir().glob("*.md")))
    tf_readme = PROJECT_ROOT / "terraform" / "aws" / "README.md"
    if tf_readme.is_file():
        paths.append(tf_readme)
    paths.extend(sorted((PROJECT_ROOT / "skills" / "spa").rglob("*.md")))
    workflows = PROJECT_ROOT / ".agent" / "workflows"
    if workflows.is_dir():
        paths.extend(sorted(workflows.glob("*.md")))
    tests_readme = PROJECT_ROOT / "tests" / "README.md"
    if tests_readme.is_file():
        paths.append(tests_readme)
    return paths


def _link_target(raw: str) -> str | None:
    dest = raw.strip().strip("<>").split()[0]
    if dest.startswith(("http://", "https://", "mailto:", "file:")):
        return None
    path = dest.split("#", 1)[0]
    return path or None


def test_agents_md_points_at_command_authoring():
    text = (PROJECT_ROOT / "AGENTS.md").read_text(encoding="utf-8")
    assert "docs/contributing.md#adding-a-spa-command" in text
    assert "docs/architecture.md#feature-development-lifecycle" in text
    assert "docs/architecture.md#controller-architecture" in text
    assert "./tests/run_cli_tests.sh" in text
    assert "docs/commands.md" in text
    assert "generated" in text.lower()


def test_architecture_defines_cli_ux_and_output_conventions():
    architecture = (_docs_dir() / "architecture.md").read_text(encoding="utf-8")
    contributing = (_docs_dir() / "contributing.md").read_text(encoding="utf-8")
    assert "## CLI UX and output conventions" in architecture
    assert "schema_version" in architecture
    assert "`list` is a catalog" in architecture
    assert "`get` is the current value" in architecture
    assert "`explain` is one definition" in architecture
    assert "`search` is ranked discovery" in architecture
    assert "spa init list" in architecture
    assert "Aliases:" in architecture
    assert "`--agent` is the documented selector" in architecture
    assert "`--json` stays a working synonym" in architecture
    assert "stdin is not a terminal" in architecture
    assert "spa aws" in architecture
    assert "spa licenses" in architecture
    assert "spa shell" in architecture
    assert "VirtualBox" in architecture
    assert "architecture.md#cli-ux-and-output-conventions" in contributing


def test_shell_completion_is_part_of_shipping_a_command():
    architecture = (_docs_dir() / "architecture.md").read_text(encoding="utf-8")
    contributing = (_docs_dir() / "contributing.md").read_text(encoding="utf-8")
    install = (_docs_dir() / "install.md").read_text(encoding="utf-8")
    guide = (_docs_dir() / "user-guide.md").read_text(encoding="utf-8")
    rule = "A new spa command is not done until shell completion can offer it."
    assert architecture.count(rule) >= 2
    assert "Do not add a command whose arguments can only be discovered by reading help." in architecture
    assert "Shell completion is a later command" not in architecture
    assert "takes_value" in contributing
    assert "completes_from" in contributing
    assert "spa completion --help" in install
    assert "does not edit" in install
    assert 'eval "$(spa --no-agent completion zsh)"' not in install
    assert "Press Tab twice" in guide
    assert "every `spa` command, subcommand, and flag" in guide
    assert "install.md#shell-completion" in guide
    assert 'eval "$(spa --no-agent completion zsh)"' not in guide


def test_user_guide_does_not_repeat_install_steps():
    guide = (_docs_dir() / "user-guide.md").read_text(encoding="utf-8")
    start = guide.split("## Start here", 1)[1].split("\n## ", 1)[0]
    assert "install.md" in start
    assert "README.md#install" not in guide
    assert "spa venv create" not in guide

    contributing = (_docs_dir() / "contributing.md").read_text(encoding="utf-8")
    documentation = contributing.split("## Documentation", 1)[1]
    assert "The user guide explains how to use spa after it is installed." in documentation

    architecture = (_docs_dir() / "architecture.md").read_text(encoding="utf-8")
    intro = architecture.split("## Current execution architecture", 1)[0]
    assert "install.md" in intro
    assert "do not copy those commands" in intro

    install = (_docs_dir() / "install.md").read_text(encoding="utf-8")
    assert "go/baseconfigs" not in install
    assert "user-guide.md#prepare-software" in install
    assert "spa environment set --software-dir" in install

    setup = contributing.split("## Development setup", 1)[1].split("\n## ", 1)[0]
    assert "install.md#develop-spa-git-clone" in setup
    assert "Python 3.9 through 3.14" not in setup
    assert "bin/spa venv create" not in setup
    assert "source bin/spa_venv.sh" in setup
    assert "Homebrew" in setup


def test_baseconfig_link_is_the_short_go_link_and_the_changelog_names_no_link():
    """The employee baseconfig link is http://go/baseconfigs. The CHANGELOG carries no link to it."""
    for rel in ("skills/spa/spa/SKILL.md", "docs/user-guide.md"):
        text = (PROJECT_ROOT / rel).read_text(encoding="utf-8")
        assert "go2.cisco.com/baseconfigs" not in text, rel
        assert "http://go/baseconfigs" in text, rel
    changelog = (PROJECT_ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    assert "go2.cisco.com/baseconfigs" not in changelog
    assert "go/baseconfigs" not in changelog


def test_readme_and_user_guide_name_the_external_provider_for_existing_hosts():
    """The README intro, Features, and Start here, and the user guide intro, all name existing hosts."""
    readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
    intro = readme.split("\n## ", 1)[0]
    assert "existing hosts" in intro
    assert "external provider" in intro
    features = readme.split("## Features", 1)[1].split("\n## ", 1)[0]
    assert "Existing hosts" in features
    assert "--provider external" in features
    assert "spa hosts register" in features
    start = readme.split("## Start here", 1)[1].split("\n## ", 1)[0]
    assert "--provider external" in start
    assert "spa hosts register" in start

    guide_intro = (_docs_dir() / "user-guide.md").read_text(encoding="utf-8").split("## Start here", 1)[0]
    assert "existing hosts" in guide_intro


def test_readme_opens_with_the_spa_pitch_before_support():
    """The SPA pitch sits above the support notice, so a new reader sees the case before the caveats."""
    readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
    assert "## Why SPA" in readme
    assert readme.index("## Why SPA") < readme.index("## Support")
    pitch = readme.split("## Why SPA", 1)[1].split("\n## ", 1)[0]
    assert "**One file, the whole environment.**" in pitch
    assert "**Agent-ready.**" in pitch
    assert "spa skills install cursor" in pitch


def test_architecture_documents_playbook_resolution_contract():
    text = (_docs_dir() / "architecture.md").read_text(encoding="utf-8")
    assert "`resolve()` and `resolve_named()` enforce" in text
    assert "Absolute paths are accepted only inside those approved roots" in text
    assert "`verification/<stem>`" in text


def test_development_docs_require_tdd_and_feature_review():
    architecture = (_docs_dir() / "architecture.md").read_text(encoding="utf-8")
    contributing = (_docs_dir() / "contributing.md").read_text(encoding="utf-8")
    agents = (PROJECT_ROOT / "AGENTS.md").read_text(encoding="utf-8")

    assert "## Test-driven development" in architecture
    assert "## Feature completion review" in architecture
    assert "what was left out" in architecture
    assert "until the user confirms the left-out items" in architecture
    assert "Saying the feature is complete does not replace that report." in architecture
    assert "A completion request that arrived before the report is not that confirmation." in architecture
    assert "even when the user already said the feature is complete" in agents
    assert "A completion request that arrived before the report is not that confirmation." in agents
    assert "architecture.md#test-driven-development" in contributing
    assert "architecture.md#feature-completion-review" in contributing
    assert "docs/architecture.md#test-driven-development" in agents
    assert "docs/architecture.md#feature-completion-review" in agents
    assert "before the first file edit" in agents
    assert "see it fail before changing production code" in agents
    assert "only after its drift test has failed" in agents
    assert "Leave the slice open until `./tests/run_local_tests.sh` passes." in agents
    assert "A plan, a todo list, or an implement-this request does not skip these steps." in agents


def test_config_editing_contract_is_linked_from_development_docs():
    architecture = (_docs_dir() / "architecture.md").read_text(encoding="utf-8")
    contributing = (_docs_dir() / "contributing.md").read_text(encoding="utf-8")

    assert "[config-editing.md](config-editing.md)" in architecture
    assert "[config-editing contract](config-editing.md)" in contributing


def test_operator_guidance_uses_transactional_config_commands():
    paths = [
        _docs_dir() / "user-guide.md",
        PROJECT_ROOT / "skills" / "spa" / "spa" / "SKILL.md",
        PROJECT_ROOT / "skills" / "spa" / "spa-create-config" / "SKILL.md",
        PROJECT_ROOT / "skills" / "spa" / "spa-apps" / "SKILL.md",
        PROJECT_ROOT / "skills" / "spa" / "spa-create-config" / "references" / "apps-questionnaire.md",
        PROJECT_ROOT / "skills" / "spa" / "spa-create-config" / "references" / "licenses.md",
    ]
    text = "\n".join(path.read_text(encoding="utf-8") for path in paths)
    assert "merge the `apply` snippet" not in text.lower()
    assert "merge the printed snippet" not in text.lower()
    assert "then merge the safe snippet" not in text.lower()
    assert "`yaml_snippet` — paste" not in text.lower()
    assert "spa --agent config set" in text
    assert "spa --agent apps add" in text
    assert "spa --agent validate" in text
    contributing = (_docs_dir() / "contributing.md").read_text(encoding="utf-8")
    assert "`merge` is `deep` or `replace`" not in contributing
    assert "catalog snippets are examples" in contributing.lower()
    changelog = (PROJECT_ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    assert "transactional config editor" in changelog.lower()
    roadmap = (PROJECT_ROOT / "ROADMAP.md").read_text(encoding="utf-8")
    assert "- [x] `spa config`" in roadmap


def test_every_config_editing_contract_id_has_behavioral_test_traceability():
    contract = (_docs_dir() / "config-editing.md").read_text(encoding="utf-8")
    definitions = CONFIG_CONTRACT_HEADING.findall(contract)
    assert len(definitions) == len(set(definitions)), "duplicate config contract IDs"

    test_sources = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted((PROJECT_ROOT / "tests").glob("test_*.py"))
    )
    covered = set(CONFIG_CONTRACT_REFERENCE.findall(test_sources))
    assert sorted(set(definitions) - covered) == [], "config contract IDs without tests"
    assert sorted(covered - set(definitions)) == [], "tests reference undocumented config contract IDs"

    mappings = CONFIG_VERIFICATION.findall(contract)
    assert {contract_id for contract_id, _ in mappings} == set(definitions)
    assert len(mappings) == len(definitions)

    source_path = PROJECT_ROOT / "tests" / "test_config_contract.py"
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    nodes = {
        "tests/test_config_contract.py::%s::%s" % (class_node.name, item.name)
        for class_node in tree.body
        if isinstance(class_node, ast.ClassDef)
        for item in class_node.body
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
        and item.name.startswith("test_")
    }
    missing_nodes = sorted({node for _, node in mappings} - nodes)
    assert missing_nodes == [], "verification-index targets do not exist"


class TestCanonicalDocs:
    def test_well_known_root_files_exist(self):
        missing = [name for name in sorted(WELL_KNOWN_ROOT) if not (PROJECT_ROOT / name).is_file()]
        assert missing == [], f"missing well-known root files: {missing}"

    def test_docs_are_exactly_the_canonical_kebab_set(self):
        docs = _docs_dir()
        assert docs.is_dir()
        found = {p.name for p in docs.iterdir() if p.is_file() and p.suffix == ".md"}
        extra = sorted(found - CANONICAL_DOCS)
        missing = sorted(CANONICAL_DOCS - found)
        assert extra == [], f"unexpected docs/*.md files: {extra}"
        assert missing == [], f"missing canonical docs: {missing}"
        bad = sorted(name for name in found if not KEBAB_MD.match(name))
        assert bad == [], f"docs filenames must be lowercase kebab-case: {bad}"


class TestMarkdownLinks:
    def test_relative_markdown_links_resolve(self):
        broken: list[str] = []
        for source in _markdown_for_links():
            text = source.read_text(encoding="utf-8")
            for match in MD_LINK.finditer(text):
                rel = _link_target(match.group(1))
                if rel is None:
                    continue
                target = (source.parent / rel).resolve()
                try:
                    target.relative_to(PROJECT_ROOT.resolve())
                except ValueError:
                    broken.append(f"{source.relative_to(PROJECT_ROOT)}: {rel} (outside repo)")
                    continue
                if not target.exists():
                    line = text.count("\n", 0, match.start()) + 1
                    broken.append(f"{source.relative_to(PROJECT_ROOT)}:{line}: {rel}")
        assert broken == [], "broken relative markdown links:\n" + "\n".join(broken)


class TestCommandsMarkdown:
    def test_committed_file_matches_schema_renderer_and_cli(self):
        committed = (_docs_dir() / "commands.md").read_text(encoding="utf-8")
        assert committed == format_schema_markdown()
        result = run_spa(["--no-agent", "agent", "schema", "--markdown"])
        assert result.returncode == 0, result.stderr
        assert result.stdout == committed


class TestConfigMarkdown:
    def test_committed_file_matches_renderer_and_cli(self):
        committed = (_docs_dir() / "config.md").read_text(encoding="utf-8")
        rendered = format_config_markdown(PROJECT_ROOT)
        assert committed == rendered
        result = run_spa(["--no-agent", "config", "schema", "--markdown"])
        assert result.returncode == 0, result.stderr
        assert result.stdout == committed

    def test_generated_descriptions_hide_internal_ids(self):
        import re

        text = format_config_markdown(PROJECT_ROOT)
        assert re.search(r"\b(setting|topology|provider)\.[A-Za-z0-9_.]+", text) is None
        assert "not a splunk_config.yml setting" not in text

    def test_generated_descriptions_state_behavior(self):
        text = format_config_markdown(PROJECT_ROOT)
        assert "Text placed before each generated number" in text
        assert "Omit the key to add nothing before the number" in text
        assert "Default false" not in text
        assert "default=False" in text
        assert "VirtualBox always turns this on" in text
        assert "Per-host override of `os.time_zone`" in text
        assert "default='splk'" in text


class TestSpaSkill:
    def test_entry_skill_frontmatter_name(self):
        path = PROJECT_ROOT / "skills" / "spa" / "spa" / "SKILL.md"
        assert path.is_file()
        text = path.read_text(encoding="utf-8")
        assert text.startswith("---\n")
        assert "\nname: spa\n" in text.split("---", 2)[1]
        tracked = subprocess.check_output(
            ["git", "ls-files", ".cursor/skills"],
            cwd=str(PROJECT_ROOT),
            text=True,
        )
        assert tracked.strip() == ""

    def test_create_config_skill_uses_feature_discovery_loop(self):
        skill = PROJECT_ROOT / "skills" / "spa" / "spa-create-config" / "SKILL.md"
        text = skill.read_text(encoding="utf-8")
        assert "spa --agent config search QUERY" in text
        assert "spa --agent config explain PATH" in text
        assert "spa validate" in text
        assert "unsupported" in text
        assert "do not read `examples/catalog/features.yml`" in text
        assert "spa --agent config set PATH VALUE" in text
        assert "spa aws --json regions list" in text
        assert "spa aws list regions" not in text
        entry = (PROJECT_ROOT / "skills" / "spa" / "spa" / "SKILL.md").read_text(encoding="utf-8")
        assert "spa --agent config explain PATH" in entry

    def test_spa_skill_confirms_before_destroy(self):
        skill_root = PROJECT_ROOT / "skills" / "spa" / "spa"
        skill = (skill_root / "SKILL.md").read_text(encoding="utf-8")
        lifecycle = (skill_root / "references" / "lifecycle.md").read_text(
            encoding="utf-8"
        )
        prerequisites = (skill_root / "references" / "prerequisites.md").read_text(
            encoding="utf-8"
        )
        for text in (skill, lifecycle, prerequisites):
            assert "ansible-playbook" not in text
        assert "Ask in chat and wait" in skill or "Ask in chat and wait" in lifecycle
        assert "The request in the same message is not the yes." in lifecycle
        assert "keeps the registered env" in lifecycle
        assert "splunk_config.yml" in lifecycle
        assert "environment remove" in lifecycle
        assert "drops the registry entry" in lifecycle
        assert "spa-create-config" in skill
        assert "spa-apps" in skill
        assert "spa-add-test-scenario" not in skill
        assert "spa hosts check" in lifecycle
        assert "spa hosts check --hosts" in lifecycle
        assert "--ami-id" not in lifecycle
        assert "https://www.splunk.com/en_us/download/splunk-enterprise.html" in prerequisites
        assert (
            "https://www.splunk.com/en_us/download/universal-forwarder.html"
            in prerequisites
        )
        assert "SPLUNKBASE_USERNAME" in prerequisites
        assert "SPLUNKBASE_PASSWORD" in prerequisites
        assert "AWS_PROFILE" in prerequisites
        assert "AWS_ACCESS_KEY_ID" in prerequisites
        assert "set" in prerequisites and "not set" in prerequisites
        assert "${!v}" not in prerequisites

    def test_entry_skill_waits_on_phase_sentences(self):
        text = (PROJECT_ROOT / "skills" / "spa" / "spa" / "SKILL.md").read_text(encoding="utf-8")
        assert "Creating HOST." in text
        assert "Downloading Splunk on HOST." in text
        assert "Configuring Splunk." in text
        assert "Installing apps on HOST." in text
        assert "terraform apply" not in text
        assert "Apply complete" not in text

    def test_create_config_asks_location_name_and_summary_before_init(self):
        skill = PROJECT_ROOT / "skills" / "spa" / "spa-create-config" / "SKILL.md"
        text = skill.read_text(encoding="utf-8")
        gate_heading = "## Environment location, name, and summary (mandatory before init)"
        assert gate_heading in text
        gate_start = text.index(gate_heading)
        phase1 = text.index("## Phase 1 — Topology path")
        phase3 = text.index("## Phase 3 — Linux OS")
        phase4 = text.index("## Phase 4 — AWS settings")
        assert phase1 < phase3 < gate_start < phase4, (
            "the gate comes after topology and OS are chosen, and before init and AWS settings"
        )
        assert "spa environment init" not in text[phase1:phase3], "topology and OS must not run init"
        gate = text[gate_start:phase4]
        # Location: current directory is the recommended default; registered environments are alternatives.
        assert "current directory" in gate
        assert "spa --agent environment list" in gate
        assert "AskQuestion" in gate
        # Name: one recommended name, derived from topology and OS (both chosen before the gate), checked against the registry.
        assert "recommend" in gate.lower()
        assert "topology and OS" in gate
        # Summary and explicit yes before the init command runs.
        assert "summary" in gate.lower()
        assert "PARENT/NAME" in gate and "--example" in gate
        assert "--name" in gate  # optional: only when the registry name differs from the folder
        assert "wait" in gate.lower()
        # After init, the flow continues with the AWS settings, which set values with spa config set.
        assert "Phase 4" in gate

    def test_create_config_phase7_sets_header_by_command(self):
        skill = PROJECT_ROOT / "skills" / "spa" / "spa-create-config" / "SKILL.md"
        text = skill.read_text(encoding="utf-8")
        _before, marker, after_phase7 = text.partition("## Phase 7 — Write config")
        assert marker
        phase7_body, phase8, _rest = after_phase7.partition("## Phase 8")
        assert phase8
        assert "spa config header set" in phase7_body
        assert "config-header-template.md" not in phase7_body

    def test_create_config_apps_and_licenses_are_mandatory_gates(self):
        text = (PROJECT_ROOT / "skills" / "spa" / "spa-create-config" / "SKILL.md").read_text(
            encoding="utf-8"
        )
        assert "## Phase 6 — Apps (optional)" not in text
        assert "Skip entire `splunk_app_deployment` if no." not in text
        phase6 = text[text.index("## Phase 6 — Apps"):text.index("## Phase 6b")]
        assert "AskQuestion" in phase6
        assert "reconfirm" in phase6.lower()
        phase6b = text[text.index("## Phase 6b"):text.index("## Phase 6c")]
        assert "AskQuestion" in phase6b
        assert "reconfirm" in phase6b.lower()
        assert "Confirmed: trial-only license. Continue?" in phase6b
        assert "If `proposed_splunk_license_file` is non-empty, ask" not in phase6b
        assert "No usable files in Software → warn" not in phase6b
        assert "spa licenses --config config/splunk_config.yml --json" in phase6b
        step0 = text[text.index("## Step 0"):text.index("## Pre-Phase Checkpoint")]
        assert "spa licenses" not in step0, "licenses are scanned once, in Phase 6b"

    def test_create_config_classifies_user_input_before_phases(self):
        text = (PROJECT_ROOT / "skills" / "spa" / "spa-create-config" / "SKILL.md").read_text(
            encoding="utf-8"
        )
        assert "## Pre-Phase Checkpoint" in text
        step0_end = text.index("## Phase 0a — Deployment intent")
        assert text.index("## Step 0") < text.index("## Pre-Phase Checkpoint") < step0_end
        block = text[text.index("## Pre-Phase Checkpoint"):step0_end]
        assert "| User Specified | Can Skip | Must Reconfirm |" in block
        assert "6, 6b" in block
        assert "MANDATORY" in block

    def test_create_config_asks_mode_only_after_minimum_requirements(self):
        text = (PROJECT_ROOT / "skills" / "spa" / "spa-create-config" / "SKILL.md").read_text(
            encoding="utf-8"
        )
        step0 = text[text.index("## Step 0"):text.index("## Pre-Phase Checkpoint")]
        assert "AskQuestion if available, otherwise ask in chat, unless user already stated intent" not in step0, (
            "the plan-or-write question must wait for the minimum requirements"
        )
        gate_start = text.index("## Environment location, name, and summary (mandatory before init)")
        phase4 = text.index("## Phase 4 — AWS settings")
        gate = text[gate_start:phase4]
        assert "**Minimum requirements first:**" in gate
        assert "**Mode**" in gate, "the mode question is asked in the gate, before init"
        assert gate.index("**Minimum requirements first:**") < gate.index("**Mode**") < gate.index("**Ask the location**"), (
            "minimum requirements, then mode, then location"
        )

    def test_create_config_shows_reconfirmation_table_before_write(self):
        text = (PROJECT_ROOT / "skills" / "spa" / "spa-create-config" / "SKILL.md").read_text(
            encoding="utf-8"
        )
        start = text.index("## Reconfirmation Checkpoint")
        phase7 = text.index("## Phase 7 — Write config")
        assert start < phase7
        block = text[start:phase7]
        assert "| Phase | Source | Value | Status |" in block
        for row in ("2 Sizing", "3 OS", "4 Provider", "5b Placement"):
            assert row in block, row
        assert "explicit yes" in block.lower()

    def test_create_config_phase9_asks_before_running_provision_and_deploy(self):
        text = (PROJECT_ROOT / "skills" / "spa" / "spa-create-config" / "SKILL.md").read_text(
            encoding="utf-8"
        )
        phase9 = text[text.index("## Phase 9 — Handoff"):]
        assert "spa provision --yes && spa deploy --yes" in phase9
        assert "Show me the command" in phase9 or "print" in phase9.lower()
        assert "explicit yes" in phase9
        assert "does **not** auto-provision" not in phase9
        assert "- Auto-running provision/deploy" not in text
        agents = (PROJECT_ROOT / "AGENTS.md").read_text(encoding="utf-8")
        assert "spa-create-config" in agents and "Phase 9" in agents

    def test_create_config_accepts_architecture_input_as_json_file(self):
        skill_dir = PROJECT_ROOT / "skills" / "spa" / "spa-create-config"
        create = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
        ref = skill_dir / "references" / "architecture-input.md"
        assert ref.is_file(), ref
        assert "references/architecture-input.md" in create
        assert "--architecture-file" not in create
        assert "--architecture-stdin" not in create
        contract = ref.read_text(encoding="utf-8")
        for key in ('"confirmed"', '"phase_1"', '"phase_2"', '"phase_3"', '"phase_4"', '"phase_6"', '"phase_6b"'):
            assert key in contract, key
        assert "still asked" in contract.lower()
        assert "secret" in contract.lower()

    def test_create_config_region_question_puts_aws_config_region_first(self):
        text = (PROJECT_ROOT / "skills" / "spa" / "spa-create-config" / "SKILL.md").read_text(
            encoding="utf-8"
        )
        phase4 = text[text.index("## Phase 4 — AWS settings"):text.index("## Phase 5 — Topology counts")]
        assert "spa aws --json regions list" in phase4
        assert "aws_config_region" in phase4
        assert "aws_config_profile" in phase4
        assert "first" in phase4.lower()
        assert "from AWS config" in phase4
        assert "AskQuestion" in phase4
        assert "scaffold" in phase4

    def test_create_config_apps_loop_asks_for_more_after_each_add(self):
        skills = PROJECT_ROOT / "skills" / "spa"
        create = (skills / "spa-create-config" / "SKILL.md").read_text(encoding="utf-8")
        phase6 = create[create.index("## Phase 6 — Apps"):create.index("## Phase 6b")]
        assert "Add another app?" in phase6
        assert "after each" in phase6.lower()
        assert "until" in phase6.lower() and "no" in phase6.lower()
        assert "spa --agent config get splunk_app_deployment" in phase6
        assert "reconfirm" in phase6.lower()

        apps = (skills / "spa-apps" / "SKILL.md").read_text(encoding="utf-8")
        workflow = apps[apps.index("## Workflow"):apps.index("ITSI / ITE Work")]
        assert "Add another app?" in workflow
        assert "after every add" in workflow.lower()

    def test_create_config_asks_content_packs_after_itsi_before_more_apps(self):
        skills = PROJECT_ROOT / "skills" / "spa"
        create = (skills / "spa-create-config" / "SKILL.md").read_text(encoding="utf-8")
        phase6 = create[create.index("## Phase 6 — Apps"):create.index("## Phase 6b")]
        loop = phase6[phase6.index("**Loop"):]
        assert "ITSI (1841)" in loop
        assert "content-packs list 5391" in loop
        assert loop.index("content-packs list 5391") < loop.index("Add another app?"), (
            "after ITSI, content packs are asked before the add-another question"
        )

        apps = (skills / "spa-apps" / "SKILL.md").read_text(encoding="utf-8")
        step8 = apps[apps.index("8. **After every add"):apps.index("9. `spa --agent validate`")]
        assert "1841" in step8
        assert "content-packs list 5391" in step8
        assert step8.index("content-packs list 5391") < step8.index("Add another app?")

    def test_apps_skill_asks_roles_for_every_normal_app(self):
        apps = (PROJECT_ROOT / "skills" / "spa" / "spa-apps" / "SKILL.md").read_text(encoding="utf-8")
        workflow = apps[apps.index("## Workflow"):apps.index("ITSI / ITE Work")]
        assert "One host with one role" not in workflow, "a single role must still be asked, not picked"
        assert "even when the config has one host with one role" in workflow
        assert "ITSI (1841) and content packs never ask this question" in workflow

    def test_create_config_phase6_asks_roles_before_a_normal_app_add(self):
        create = (PROJECT_ROOT / "skills" / "spa" / "spa-create-config" / "SKILL.md").read_text(encoding="utf-8")
        phase6 = create[create.index("## Phase 6 — Apps"):create.index("## Phase 6b")]
        loop = phase6[phase6.index("**Loop"):]
        step1 = loop.split("\n1. ", 1)[1].split("\n1b.", 1)[0]
        assert "pick the ID and roles" not in loop
        assert "AskQuestion" in step1 and "roles" in step1
        assert "no roles question" in step1

    def test_create_config_app_table_uses_the_roles_flag(self):
        create = (PROJECT_ROOT / "skills" / "spa" / "spa-create-config" / "SKILL.md").read_text(encoding="utf-8")
        assert "apps add APP_ID --target-roles" not in create
        assert "apps add APP_ID --roles ROLE1,ROLE2 --yes" in create

    def test_apps_questionnaire_asks_roles_for_normal_apps_only(self):
        questionnaire = (
            PROJECT_ROOT / "skills" / "spa" / "spa-create-config" / "references" / "apps-questionnaire.md"
        ).read_text(encoding="utf-8")
        section4 = questionnaire[questionnaire.index("## 4. Target roles"):questionnaire.index("## 5. Premium ITSI?")]
        assert "AskQuestion" in section4
        assert "normal" in section4 and "not ask" in section4.lower()

    def test_region_default_never_comes_from_agent_knowledge(self):
        skills = PROJECT_ROOT / "skills" / "spa" / "spa-create-config"
        create = (skills / "SKILL.md").read_text(encoding="utf-8")
        phase4 = create[create.index("## Phase 4 — AWS settings"):create.index("## Phase 5 — Topology counts")]
        assert "from your own knowledge" in phase4
        assert "null" in phase4
        without_creds = (skills / "references" / "aws-without-credentials.md").read_text(encoding="utf-8")
        assert "do not call `spa aws regions list`" not in without_creds
        assert "aws_config_region" in without_creds
        assert "ok: false" in without_creds

    def test_create_config_skill_stays_under_500_lines(self):
        text = (PROJECT_ROOT / "skills" / "spa" / "spa-create-config" / "SKILL.md").read_text(
            encoding="utf-8"
        )
        assert len(text.splitlines()) < 500

    def test_config_skills_never_hand_edit_splunk_config(self):
        skills = PROJECT_ROOT / "skills" / "spa"
        paths = [
            skills / "spa" / "SKILL.md",
            skills / "spa-create-config" / "SKILL.md",
            skills / "spa-apps" / "SKILL.md",
        ]
        for path in paths:
            text = path.read_text(encoding="utf-8")
            assert "never edit" in text.lower(), path.name
            assert "spa config" in text, path.name

        agents = (PROJECT_ROOT / "AGENTS.md").read_text(encoding="utf-8")
        assert "Do not hand-edit" in agents
        assert "spa config" in agents

    def test_config_skills_hand_off_to_each_other(self):
        skills = PROJECT_ROOT / "skills" / "spa"
        spa = (skills / "spa" / "SKILL.md").read_text(encoding="utf-8")
        create = (skills / "spa-create-config" / "SKILL.md").read_text(encoding="utf-8")
        apps = (skills / "spa-apps" / "SKILL.md").read_text(encoding="utf-8")
        assert "/spa-create-config" in spa and "/spa-apps" in spa
        assert "/spa-apps" in create and "/spa" in create
        assert "/spa-create-config" in apps and "/spa" in apps

    def test_config_skills_use_the_current_validate_flag(self):
        skills_root = PROJECT_ROOT / "skills" / "spa"
        for path in skills_root.rglob("*.md"):
            text = path.read_text(encoding="utf-8")
            assert "--splunk-config-aws" not in text, path

    def test_create_config_header_asset_names_the_command(self):
        template = (
            PROJECT_ROOT
            / "skills"
            / "spa"
            / "spa-create-config"
            / "assets"
            / "config-header-template.md"
        ).read_text(encoding="utf-8")
        assert "spa --agent config header set" in template
        assert "--intent" in template and "--deploy" in template
        assert "do not paste" in template.lower()

    def test_entry_points_and_skill_selection_guide(self):
        skills = PROJECT_ROOT / "skills" / "spa"
        create = (skills / "spa-create-config" / "SKILL.md").read_text(encoding="utf-8")
        entry = (skills / "spa" / "SKILL.md").read_text(encoding="utf-8")
        refs = skills / "spa-create-config" / "references"
        decision = refs / "workflow-decision-tree.md"
        best = refs / "config-header-best-practices.md"

        assert "## Entry points" in create
        for phrase in ("Brand new environment", "Modify existing config", "Lifecycle"):
            assert phrase in create, phrase
        assert "workflow-decision-tree.md" in create
        assert "config-header-best-practices.md" in create

        assert "## Skill selection" in entry
        assert "Load one skill at a time" in entry
        assert "Load ONE skill" not in entry
        assert "Load ONE skill" not in create

        assert decision.is_file(), decision
        tree = decision.read_text(encoding="utf-8")
        for route in ("/spa-create-config", "/spa-apps", "/spa"):
            assert route in tree, route

        assert best.is_file(), best
        header = best.read_text(encoding="utf-8")
        assert "spa config header set" in header
        assert "--yes" in header
        assert "--sva" in header

    def test_init_examples_name_a_provider(self):
        """Every operator-facing init example names --provider, since init requires one."""
        pattern = re.compile(r"\b(?:spa|bin/spa) (?:environment |env )?init --example\b")
        paths = [
            PROJECT_ROOT / "AGENTS.md",
            PROJECT_ROOT / "README.md",
            PROJECT_ROOT / "docs" / "user-guide.md",
            PROJECT_ROOT / "skills" / "spa" / "spa" / "SKILL.md",
            PROJECT_ROOT / "skills" / "spa" / "spa-create-config" / "SKILL.md",
        ]
        for path in paths:
            text = path.read_text(encoding="utf-8")
            for number, line in enumerate(text.splitlines(), 1):
                if pattern.search(line):
                    assert "--provider" in line, "%s:%d: %s" % (path.name, number, line)
            assert "aws is implicit" not in text, path.name
            assert "aws is the implicit default" not in text, path.name

    def test_skill_aws_discovery_commands_pass_region(self):
        """AMI and survey lookups must search the region the config uses, so every skill line names --region."""
        skills = PROJECT_ROOT / "skills" / "spa"
        triggers = ("--latest-ami", "--survey", "--describe-ami", "amis list")
        offenders = []
        for path in sorted(skills.rglob("*.md")):
            for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if "spa aws" in line and any(t in line for t in triggers) and "--region" not in line:
                    offenders.append("%s:%d" % (path.relative_to(PROJECT_ROOT), number))
        assert offenders == [], offenders

    def test_entry_skill_names_environment_cleanup(self):
        skill = (PROJECT_ROOT / "skills" / "spa" / "spa" / "SKILL.md").read_text(encoding="utf-8")
        line = next(ln for ln in skill.splitlines() if "spa environment cleanup" in ln)
        assert "--yes" in line

    def test_skill_descriptions_route_lab_requests_to_spa(self):
        import yaml

        def description(path: Path) -> str:
            front = path.read_text(encoding="utf-8").split("---", 2)[1]
            meta = yaml.safe_load(front)
            return " ".join(str(meta["description"]).split())

        entry = description(PROJECT_ROOT / "skills" / "spa" / "spa" / "SKILL.md")
        for phrase in (
            "Splunk lab",
            "Splunk environment",
            "AWS CLI",
            "Redhat",
            "single-node",
            "provision",
            "deploy",
            "destroy",
            "existing hosts",
            "hosts register",
        ):
            assert phrase in entry, phrase

        body = (PROJECT_ROOT / "skills" / "spa" / "spa" / "SKILL.md").read_text(
            encoding="utf-8"
        )
        routing = next(
            line for line in body.splitlines() if line.startswith("- **Routing:**")
        )
        assert "existing hosts" in routing, routing

        config = description(
            PROJECT_ROOT / "skills" / "spa" / "spa-create-config" / "SKILL.md"
        )
        for phrase in ("Splunk lab", "Splunk environment", "AWS", "single-node", "Redhat"):
            assert phrase in config, phrase

        agents = (PROJECT_ROOT / "AGENTS.md").read_text(encoding="utf-8")
        assert "Splunk lab" in agents
        assert "AWS CLI" in agents

    def test_operator_skills_omit_add_test_scenario(self):
        readme = (PROJECT_ROOT / "skills" / "spa" / "README.md").read_text(
            encoding="utf-8"
        )
        agents = (PROJECT_ROOT / "AGENTS.md").read_text(encoding="utf-8")
        contributing = (_docs_dir() / "contributing.md").read_text(encoding="utf-8")
        for text in (readme, agents, contributing):
            assert "spa-create-config" in text
            assert "spa-apps" in text
            assert "spa-add-test-scenario" not in text
        tests_readme = (PROJECT_ROOT / "tests" / "README.md").read_text(encoding="utf-8")
        assert "tests/configs/app_scope/<name>/" in tests_readme
        assert "UPDATE_SCOPE_SNAPSHOTS=1" in tests_readme
        assert "./tests/run_app_scope_scenarios_tests.sh" in tests_readme
        user_guide = (_docs_dir() / "user-guide.md").read_text(encoding="utf-8")
        assert "wait for a yes in chat" in user_guide
        assert "spa destroy --hosts" in user_guide
        retired = (
            PROJECT_ROOT / "skills" / "spa" / "spa-add-test-scenario" / "SKILL.md"
        )
        assert not retired.exists()


def _operator_text_paths():
    """Every markdown file an operator or agent reads for commands."""
    paths = [PROJECT_ROOT / "README.md", PROJECT_ROOT / "AGENTS.md"]
    paths += sorted((_docs_dir()).glob("*.md"))
    paths += sorted((PROJECT_ROOT / "skills").rglob("*.md"))
    paths += sorted((PROJECT_ROOT / ".agent").rglob("*.md"))
    return paths


class TestReviewFindings67:
    """Contracts from the #67 completion review. Each was red before its fix."""

    def test_every_operator_init_example_names_a_provider_even_with_flags_before_it(self):
        offenders = []
        pattern = re.compile(r"\bspa (?:environment |env )?init\b")
        for path in _operator_text_paths():
            for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                # Prose that names the flag or negates a topology (not a command) is not an operator example.
                negated = "not `spa init" in line or "not a spa init" in line or "`--example`" in line
                if pattern.search(line) and "--example" in line and "--provider" not in line and not negated:
                    offenders.append("%s:%d: %s" % (path.relative_to(PROJECT_ROOT), number, line.strip()))
        assert offenders == [], offenders

    def test_spa_apps_hands_deploy_to_the_chat_gate_not_a_bare_command(self):
        text = (PROJECT_ROOT / "skills" / "spa" / "spa-apps" / "SKILL.md").read_text(encoding="utf-8")
        assert "(`spa deploy --yes`)" not in text
        assert "Deploy only after the operator's yes in chat" in text

    def test_no_agent_facing_file_uses_a_non_existent_playbook_or_typo_command(self):
        offenders = []
        for path in _operator_text_paths():
            if "ap ansible/" in path.read_text(encoding="utf-8"):
                offenders.append(str(path.relative_to(PROJECT_ROOT)))
        assert offenders == [], offenders

    def test_legacy_aws_runbook_points_to_the_skills_and_drops_the_unsafe_steps(self):
        path = PROJECT_ROOT / ".agent" / "workflows" / "deploy-aws-terraform.md"
        text = path.read_text(encoding="utf-8")
        head = "\n".join(text.splitlines()[:6])
        assert "/spa" in head and "legacy" in head.lower(), head
        assert "spa sh " not in text
        assert "-- -v" not in text
        assert "Edit `config/splunk_config.yml`" not in text
        assert "Non-interactive (agents / CI)" not in text

    def test_every_gate_list_names_environment_cleanup_as_well_as_remove(self):
        skills = PROJECT_ROOT / "skills" / "spa"
        for path in (
            skills / "spa" / "references" / "lifecycle.md",
            skills / "spa" / "SKILL.md",
            skills / "spa-create-config" / "references" / "workflow-decision-tree.md",
        ):
            text = path.read_text(encoding="utf-8")
            assert "environment remove" in text, path.name
            assert "environment cleanup" in text, path.name

    def test_changelog_records_the_validate_flag_rename(self):
        text = (PROJECT_ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
        unreleased = text.split("## [Unreleased]", 1)[1].split("\n## [", 1)[0]
        assert "--splunk-config-aws" in unreleased
        assert "--splunk-config aws" in unreleased
