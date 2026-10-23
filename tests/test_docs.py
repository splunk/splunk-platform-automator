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
        entry = (PROJECT_ROOT / "skills" / "spa" / "spa" / "SKILL.md").read_text(encoding="utf-8")
        assert "spa --agent config explain PATH" in entry
