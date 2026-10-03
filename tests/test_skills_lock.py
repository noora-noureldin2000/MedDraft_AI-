"""
Tests for skills-lock.json consistency with .agents/skills/.

The lock file is the project-level skill registry (npx skills lockfile
format). Every skill directory installed under .agents/skills/ must have a
lock entry, and every lock entry must have an installed directory — this is
what keeps newly added skills connected to the repo's skill registry.

Hash verification is intentionally left to the `npx skills` CLI: its
computedHash replicates JavaScript locale-aware collation, which cannot be
reproduced portably in Python.
"""

from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
AGENTS_SKILLS_DIR = REPO_ROOT / ".agents" / "skills"
LOCK_PATH = REPO_ROOT / "skills-lock.json"


def _installed_skill_dirs() -> set:
    return {p.name for p in AGENTS_SKILLS_DIR.iterdir() if p.is_dir()}


def _locked_skills() -> dict:
    return json.loads(LOCK_PATH.read_text(encoding="utf-8"))["skills"]


class TestSkillsLockCoverage:
    def test_installed_dirs_and_lock_entries_match(self):
        """Every installed skill dir has a lock entry and vice versa."""
        assert _installed_skill_dirs() == set(_locked_skills())

    def test_lock_entries_have_required_fields(self):
        for name, entry in _locked_skills().items():
            assert "source" in entry, name
            assert "sourceType" in entry, name
            computed_hash = entry.get("computedHash")
            assert isinstance(computed_hash, str), name
            assert len(computed_hash) == 64, name

    def test_guard_skills_are_locked(self):
        locked = _locked_skills()
        for name in (
            "clean-code-guard",
            "docs-guard",
            "test-guard",
            "thesis-master-guide",
            "woo-guard",
            "wp-guard",
        ):
            assert name in locked, name
