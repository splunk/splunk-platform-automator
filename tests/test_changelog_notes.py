"""Tests for scripts/changelog_notes.py."""

import os
import sys

import pytest

pytestmark = pytest.mark.local

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(PROJECT_ROOT, "scripts"))

from changelog_notes import extract_notes  # noqa: E402


def test_extract_released_section():
    changelog = (os.path.join(PROJECT_ROOT, "CHANGELOG.md"))
    with open(changelog, encoding="utf-8") as handle:
        notes = extract_notes(handle.read(), "2.4.0")
    assert "App Deployment" in notes
    assert "## [2.3" not in notes


def test_missing_version_raises():
    with pytest.raises(ValueError, match="No changelog section"):
        extract_notes("## [Unreleased]\n\n- note\n", "9.9.9")


def test_empty_section_raises():
    with pytest.raises(ValueError, match="empty"):
        extract_notes("## [1.0.0] - 2026-01-01\n\n## [0.9.0] - 2025-01-01\n\n- old\n", "1.0.0")
