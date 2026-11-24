"""Standing docs checks: catalogs, links, CFG-ID traceability, lints, CI names."""

from __future__ import annotations

import ast
import re
import subprocess
from pathlib import Path

import yaml

from spa.agent import format_schema_markdown
from spa.catalog import format_config_markdown
from spa_testutil import run_spa

import pytest

pytestmark = pytest.mark.local

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RELEASE_INSTALL_ONE_LINER = (
    "curl -fsSL https://github.com/splunk/splunk-platform-automator/"
    "releases/latest/download/install.sh | sh"
)

KEBAB_MD = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*\.md$")
MD_LINK = re.compile(r"\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
CONFIG_CONTRACT_HEADING = re.compile(r"^### (CFG-[A-Z]+-\d{3})\b", re.MULTILINE)
CONFIG_CONTRACT_REFERENCE = re.compile(r"\b(CFG-[A-Z]+-\d{3})\b")
CONFIG_VERIFICATION = re.compile(
    r"^- `(CFG-[A-Z]+-\d{3})`: `(tests/test_config_contract\.py::[A-Za-z0-9_:]+)`$",
    re.MULTILINE,
)

SKIP_LINK_SCAN = {
    PROJECT_ROOT / "CHANGELOG.md",
}

WELL_KNOWN_ROOT = {
    "AGENTS.md",
    "CHANGELOG.md",
    "README.md",
    "RELEASE.md",
    "ROADMAP.md",
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


def _operator_text_paths() -> list[Path]:
    paths = [PROJECT_ROOT / "README.md", PROJECT_ROOT / "AGENTS.md"]
    paths += sorted(_docs_dir().glob("*.md"))
    paths += sorted((PROJECT_ROOT / "skills").rglob("*.md"))
    paths += sorted((PROJECT_ROOT / ".agent").rglob("*.md"))
    return paths


def test_keep_after_dev_rules_and_orchestrated_plans():
    """Standing tests cover functionality and standards; TDD-only scaffolding does not ship."""
    architecture = (_docs_dir() / "architecture.md").read_text(encoding="utf-8")
    tdd = architecture.split("## Test-driven development", 1)[1].split("\n## ", 1)[0]
    completion = architecture.split("## Feature completion review", 1)[1].split(
        "\n## ", 1
    )[0]
    lifecycle = architecture.split("## Feature development lifecycle", 1)[1].split(
        "\n## ", 1
    )[0]

    assert "functionality" in tdd
    assert "standards" in tdd
    assert "TDD-only tests do not ship" in tdd
    assert "prose is not tested by phrase" in tdd
    assert "standing" in completion and "TDD-only" in completion
    assert "### Orchestrated plans" in lifecycle
    assert "fix-now" in lifecycle
    assert "defer" in lifecycle
    assert "needs-user" in lifecycle
    assert (
        "Documentation and skill contracts start with a failing assertion"
        not in architecture
    )


def test_agents_md_stays_within_token_budget():
    agents = (PROJECT_ROOT / "AGENTS.md").read_text(encoding="utf-8")
    assert len(agents.splitlines()) <= 60


def test_release_install_one_liner_is_identical_in_operator_entry_pages():
    for rel in ("README.md", "docs/install.md", "AGENTS.md", "docs/quick-start.md"):
        text = (PROJECT_ROOT / rel).read_text(encoding="utf-8")
        assert RELEASE_INSTALL_ONE_LINER in text, rel


def test_skill_package_frontmatter_name_matches_directory():
    for path in sorted((PROJECT_ROOT / "skills" / "spa").glob("*/SKILL.md")):
        front = path.read_text(encoding="utf-8").split("---", 2)[1]
        meta = yaml.safe_load(front) or {}
        assert meta.get("name") == path.parent.name, path.relative_to(PROJECT_ROOT)


def test_cursor_skills_are_not_tracked_in_repo():
    tracked = subprocess.check_output(
        ["git", "ls-files", ".cursor/skills"],
        cwd=str(PROJECT_ROOT),
        text=True,
    )
    assert tracked.strip() == ""


def test_every_operator_init_example_names_a_provider_even_with_flags_before_it():
    offenders = []
    pattern = re.compile(r"\bspa (?:environment |env )?init\b")
    for path in _operator_text_paths():
        text = path.read_text(encoding="utf-8")
        for claim in ("aws is implicit", "aws is the implicit default"):
            if claim in text:
                offenders.append("%s: %s" % (path.relative_to(PROJECT_ROOT), claim))
        for number, line in enumerate(text.splitlines(), 1):
            negated = "not `spa init" in line or "not a spa init" in line or "`--example`" in line
            if pattern.search(line) and "--example" in line and "--provider" not in line and not negated:
                offenders.append("%s:%d: %s" % (path.relative_to(PROJECT_ROOT), number, line.strip()))
    assert offenders == [], offenders


def test_operator_docs_and_skills_use_provider_aws():
    """Live AWS discovery is spa provider aws, not top-level spa aws. Kept until the command lint scans real docs."""
    live = (
        "spa aws check-auth",
        "spa aws regions list",
        "spa aws latest-ami",
        "spa aws describe-ami",
        "spa aws validate",
        "spa aws survey",
        "spa aws amis list",
        "spa aws instance-types list",
        "spa aws key-pairs list",
        "spa aws security-groups list",
        "spa aws ...",
        "spa --agent aws",
        "`spa aws`",
    )
    skip = {"config.md", "commands.md"}
    offenders = []
    for path in _operator_text_paths():
        if path.name in skip:
            continue
        text = path.read_text(encoding="utf-8")
        for spelling in live:
            if spelling in text:
                offenders.append("%s: %s" % (path.relative_to(PROJECT_ROOT), spelling))
    assert offenders == [], offenders


def test_skill_aws_discovery_commands_pass_region():
    """AMI and survey lookups must search the region the config uses, so every skill line names --region."""
    skills = PROJECT_ROOT / "skills" / "spa"
    triggers = ("latest-ami", "survey", "describe-ami", "amis list")
    offenders = []
    for path in sorted(skills.rglob("*.md")):
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            aws_discovery = (
                "spa provider aws" in line
                or "spa --agent provider aws" in line
                or "spa aws" in line
                or "spa --agent aws" in line
            )
            if aws_discovery and any(t in line for t in triggers) and "--region" not in line:
                offenders.append("%s:%d" % (path.relative_to(PROJECT_ROOT), number))
    assert offenders == [], offenders


def test_create_config_app_table_uses_the_roles_flag():
    create = (
        PROJECT_ROOT / "skills" / "spa" / "spa-create-config" / "SKILL.md"
    ).read_text(encoding="utf-8")
    assert "apps add APP_ID --target-roles" not in create
    assert "apps add APP_ID --roles ROLE1,ROLE2 --yes" in create


def test_operator_docs_do_not_use_removed_splunk_config_aws_flag():
    skip = {"config.md", "commands.md"}
    for path in _operator_text_paths():
        if path.name in skip:
            continue
        text = path.read_text(encoding="utf-8")
        assert "--splunk-config-aws" not in text, path.relative_to(PROJECT_ROOT)


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

        docs = _docs_dir()
        found = {p.name for p in docs.iterdir() if p.is_file() and p.suffix == ".md"}
        bad = sorted(name for name in found if not KEBAB_MD.match(name))
        assert bad == [], f"docs filenames must be lowercase kebab-case: {bad}"


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
        text = format_config_markdown(PROJECT_ROOT)
        assert re.search(r"\b(setting|topology|provider)\.[A-Za-z0-9_.]+", text) is None
        assert "not a splunk_config.yml setting" not in text


def test_command_lint_flags_stale_spa_line_in_fixture():
    """A known-stale `spa aws` line in the fixture is reported before real docs are scanned."""
    from docs_lints import lint_spa_commands

    fixture = PROJECT_ROOT / "tests" / "fixtures" / "docs_lints" / "stale_spa_command.md"
    errors = lint_spa_commands(fixture.read_text(encoding="utf-8"), source=fixture)
    assert errors, "expected the fixture's spa aws line to fail the schema lint"
    joined = "\n".join(errors)
    assert "unknown command" in joined
    assert "aws" in joined
    assert "regions list" in joined


def test_secret_scan_flags_pem_and_verbose_deploy_in_fixture():
    """A PEM block and spa deploy -v in the fixture fail before real docs are scanned."""
    from docs_lints import scan_secrets

    fixture = PROJECT_ROOT / "tests" / "fixtures" / "docs_lints" / "secret_markers.md"
    errors = scan_secrets(
        fixture.read_text(encoding="utf-8"),
        source=fixture,
        agent_facing=True,
    )
    joined = "\n".join(errors)
    assert "PEM" in joined or "BEGIN" in joined
    assert "-v on spa deploy" in joined


def test_docs_and_skills_secret_scan_is_clean():
    """Operator docs and skills have no PEM bodies, secret-looking literals, or agent -v on deploy/run."""
    from docs_lints import scan_docs_and_skills

    errors = scan_docs_and_skills()
    assert errors == [], "secret scan:\n" + "\n".join(errors)


_FIXTURE_CI = """
jobs:
  syntax:
    name: Syntax
    steps:
      - run: python -m compileall -q lib
  local:
    name: ${{ matrix.name }}
    strategy:
      matrix:
        include:
          - name: CLI help
            marker: local and cli and not cli_runtime
            run: SPA_CLI_MARKEXPR='local and cli and not cli_runtime' ./tests/run_cli_tests.sh -n auto
          - name: CLI runtime
            marker: local and cli and cli_runtime
            run: SPA_CLI_MARKEXPR='local and cli and cli_runtime' ./tests/run_cli_tests.sh -n auto
          - name: Ansible app-scope
            marker: local and ansible and app_scope
            run: SPA_ANSIBLE_MARKEXPR='local and ansible and app_scope' ./tests/run_ansible_tests.sh -n auto
          - name: Ansible env-scaffold
            marker: local and ansible and env_scaffold
            run: SPA_ANSIBLE_MARKEXPR='local and ansible and env_scaffold' ./tests/run_ansible_tests.sh -n auto
          - name: Ansible remaining
            marker: local and ansible and not app_scope and not env_scaffold
            run: SPA_ANSIBLE_MARKEXPR='local and ansible and not app_scope and not env_scaffold' ./tests/run_ansible_tests.sh -n auto
          - name: Unit tests
            marker: local and not cli and not ansible
            run: ./tests/run_unit_tests.sh -n auto
  ansible315:
    name: Ansible tests (3.15)
    steps:
      - name: Set up Python 3.15
        id: py315
        uses: actions/setup-python@v7
        continue-on-error: true
        with:
          python-version: "3.15"
      - name: Set up Python 3.13 fallback
        if: steps.py315.outcome != 'success'
        uses: actions/setup-python@v7
        with:
          python-version: "3.13"
      - run: SPA_ANSIBLE_MARKEXPR='local and ansible and app_scope' ./tests/run_ansible_tests.sh -n auto
"""


def test_ci_parser_includes_non_matrix_pytest_jobs_and_315_fallback():
    """Ansible tests (3.15) is a separate job; its markexpr still maps to LOCAL_JOB_MARKEXPRS."""
    from docs_lints import (
        ci_job_names,
        ci_pytest_markexprs,
        parse_ci_jobs,
        python_setup_steps,
    )
    from spa_testutil import LOCAL_JOB_MARKEXPRS

    names = ci_job_names(_FIXTURE_CI)
    assert "Syntax" in names
    assert "CLI help" in names
    assert "Ansible tests (3.15)" in names
    exprs = ci_pytest_markexprs(_FIXTURE_CI)
    assert exprs == set(LOCAL_JOB_MARKEXPRS)
    band = [job for job in parse_ci_jobs(_FIXTURE_CI) if job["name"] == "Ansible tests (3.15)"]
    assert band
    versions = python_setup_steps(band[0])
    assert any(row["version"] == "3.15" and row["continue_on_error"] for row in versions)
    assert any(row["version"] == "3.13" for row in versions)


def test_ci_pytest_job_markexprs_equal_local_job_markexprs():
    """Every ci.yml pytest job's markexpr is exactly LOCAL_JOB_MARKEXPRS (matrix and non-matrix)."""
    from docs_lints import ci_pytest_markexprs
    from spa_testutil import LOCAL_JOB_MARKEXPRS

    ci = (PROJECT_ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert ci_pytest_markexprs(ci) == set(LOCAL_JOB_MARKEXPRS)


def test_release_required_check_names_keep_dotted_version_in_backticks():
    """Job names like Ansible app-scope (3.15) must not be cut at the version dot."""
    from docs_lints import release_required_check_names

    text = (
        "It requires the status checks `Syntax` and `Ansible app-scope (3.15)` "
        "(shown as `CI / Syntax`)."
    )
    assert release_required_check_names(text) == {"Syntax", "Ansible app-scope (3.15)"}


def test_release_md_required_check_names_equal_ci_job_names():
    """RELEASE.md ruleset required checks are the ci.yml job `name:` values."""
    from docs_lints import ci_job_names, release_required_check_names

    ci = (PROJECT_ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    release = (PROJECT_ROOT / "RELEASE.md").read_text(encoding="utf-8")
    assert release_required_check_names(release) == ci_job_names(ci)


def test_python_315_setup_falls_back_to_313():
    """Any 3.15 pytest job sets up 3.15 with continue-on-error and a 3.13 fallback."""
    from docs_lints import parse_ci_jobs, python_setup_steps

    ci = (PROJECT_ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    for job in parse_ci_jobs(ci):
        versions = python_setup_steps(job)
        if not any(row["version"] == "3.15" for row in versions):
            continue
        assert any(
            row["version"] == "3.15" and row["continue_on_error"] for row in versions
        ), job["name"]
        assert any(row["version"] == "3.13" for row in versions), job["name"]


def _semgrep_job(ci_text: str) -> dict:
    data = yaml.safe_load(ci_text) or {}
    for job in (data.get("jobs") or {}).values():
        if isinstance(job, dict) and job.get("name") == "Semgrep":
            return job
    raise AssertionError("ci.yml has no job named Semgrep")


def _container_image(job: dict) -> str:
    container = job.get("container")
    if isinstance(container, str):
        return container
    if isinstance(container, dict):
        return str(container.get("image") or "")
    return ""


def _job_run_text(job: dict) -> str:
    parts = []
    for step in job.get("steps") or []:
        if isinstance(step, dict) and step.get("run"):
            parts.append(str(step["run"]))
    return "\n".join(parts)


def test_semgrep_job_is_parallel_pinned_fails_on_error_and_uploads_sarif():
    """Semgrep is a required parallel SAST job: no needs, pinned image, --error, SARIF."""
    from docs_lints import release_required_check_names

    ci_text = (PROJECT_ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    job = _semgrep_job(ci_text)
    assert "needs" not in job
    image = _container_image(job)
    assert image.startswith("semgrep/semgrep:")
    assert not image.endswith(":latest")
    assert image.split(":", 1)[1] not in {"", "latest"}
    scan = _job_run_text(job)
    assert "--config p/python" in scan
    assert "--config p/security-audit" in scan
    assert "--severity ERROR" in scan
    assert "--error" in scan
    assert "--metrics=off" in scan
    uses = [
        str(step.get("uses") or "")
        for step in job.get("steps") or []
        if isinstance(step, dict)
    ]
    assert any("upload-sarif" in item for item in uses)
    perms = job.get("permissions") or {}
    assert perms.get("contents") == "read"
    assert perms.get("security-events") == "write"
    release = (PROJECT_ROOT / "RELEASE.md").read_text(encoding="utf-8")
    assert "Semgrep" in release_required_check_names(release)
    docs = "\n".join(
        (PROJECT_ROOT / path).read_text(encoding="utf-8")
        for path in ("RELEASE.md", "tests/README.md")
    )
    assert "semgrep scan" in docs
    assert "--config p/python" in docs
    assert "--config p/security-audit" in docs
    assert "--severity ERROR" in docs
    assert "--error" in docs
    assert "--metrics=off" in docs
