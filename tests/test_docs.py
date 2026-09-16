"""Canonical operator docs exist and relative markdown links resolve."""

from __future__ import annotations

import re
from pathlib import Path

from spa.agent import format_schema_markdown
from spa_testutil import run_spa

import pytest

pytestmark = pytest.mark.local

PROJECT_ROOT = Path(__file__).resolve().parents[1]

CANONICAL_DOCS = {
    "apps.md",
    "aws.md",
    "commands.md",
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
