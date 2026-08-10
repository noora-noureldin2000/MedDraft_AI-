"""
Tests for SkillRegistry (meddraft_ai/core/skill_registry.py).

Covers: loading, get_skill, error propagation, new prompt directory registration.
No live filesystem required — all tests use tmp_path fixtures.
"""

from __future__ import annotations

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from meddraft_ai.core.skill_registry import SkillRegistry, REGISTERED_PROMPT_SUBDIRS


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_registry_with_dir(prompts_dir: Path) -> SkillRegistry:
    """Return a loaded SkillRegistry pointing at a custom prompts dir."""
    config = MagicMock()
    config.PROMPTS_DIR = prompts_dir
    registry = SkillRegistry.__new__(SkillRegistry)
    registry.config = config
    registry.prompts_dir = prompts_dir
    registry.skills = []
    return registry.load()


# ---------------------------------------------------------------------------
# REGISTERED_PROMPT_SUBDIRS — Phase 2 registration check
# ---------------------------------------------------------------------------

class TestRegisteredSubdirs:
    def test_pdf_dir_is_registered(self):
        assert "pdf" in REGISTERED_PROMPT_SUBDIRS

    def test_humanizer_main_dir_is_registered(self):
        assert "humanizer-main" in REGISTERED_PROMPT_SUBDIRS

    def test_docx_dir_is_registered(self):
        assert "docx" in REGISTERED_PROMPT_SUBDIRS


# ---------------------------------------------------------------------------
# SkillRegistry.load()
# ---------------------------------------------------------------------------

class TestSkillRegistryLoad:
    def test_load_discovers_md_files(self, tmp_path):
        (tmp_path / "skill_a.md").write_text("# Skill A content", encoding="utf-8")
        (tmp_path / "skill_b.txt").write_text("Skill B content", encoding="utf-8")
        registry = _make_registry_with_dir(tmp_path)
        names = [s["name"] for s in registry.skills]
        assert "skill_a" in names
        assert "skill_b" in names

    def test_load_ignores_non_md_txt_files(self, tmp_path):
        (tmp_path / "data.json").write_text("{}", encoding="utf-8")
        (tmp_path / "image.png").write_bytes(b"\x89PNG")
        registry = _make_registry_with_dir(tmp_path)
        assert registry.skills == []

    def test_load_recurses_into_subdirectories(self, tmp_path):
        subdir = tmp_path / "sub"
        subdir.mkdir()
        (subdir / "nested.md").write_text("Nested skill", encoding="utf-8")
        registry = _make_registry_with_dir(tmp_path)
        names = [s["name"] for s in registry.skills]
        assert "nested" in names

    def test_load_handles_missing_prompts_dir_gracefully(self, tmp_path):
        missing = tmp_path / "does_not_exist"
        registry = _make_registry_with_dir(missing)
        assert registry.skills == []

    def test_load_populates_abs_path(self, tmp_path):
        skill_file = tmp_path / "myskill.md"
        skill_file.write_text("content", encoding="utf-8")
        registry = _make_registry_with_dir(tmp_path)
        assert registry.skills[0]["abs_path"] == str(skill_file)

    def test_load_handles_utf8_content_without_corruption(self, tmp_path):
        # Medical Unicode symbols must not be silently dropped (L-04 fix)
        (tmp_path / "medical.md").write_text(
            "Alpha: \u03b1, Beta: \u03b2, Mu: \u00b5", encoding="utf-8"
        )
        registry = _make_registry_with_dir(tmp_path)
        skill = next(s for s in registry.skills if s["name"] == "medical")
        content = Path(skill["abs_path"]).read_text(encoding="utf-8")
        assert "\u03b1" in content  # α preserved


# ---------------------------------------------------------------------------
# SkillRegistry.get_skill()
# ---------------------------------------------------------------------------

class TestSkillRegistryGetSkill:
    def test_returns_content_for_known_skill(self, tmp_path):
        (tmp_path / "humanizer.md").write_text("Humanize this.", encoding="utf-8")
        registry = _make_registry_with_dir(tmp_path)
        content = registry.get_skill("humanizer")
        assert "Humanize this." in content

    def test_case_insensitive_lookup(self, tmp_path):
        (tmp_path / "MySkill.md").write_text("Case test.", encoding="utf-8")
        registry = _make_registry_with_dir(tmp_path)
        # Both upper and lower should resolve
        assert "Case test." in registry.get_skill("myskill")
        assert "Case test." in registry.get_skill("MYSKILL")

    def test_raises_value_error_for_missing_skill(self, tmp_path):
        """H-07 fix: get_skill must raise ValueError instead of returning empty string."""
        registry = _make_registry_with_dir(tmp_path)
        with pytest.raises(ValueError, match="not found in registry"):
            registry.get_skill("nonexistent_skill")

    def test_raises_value_error_when_file_deleted_after_load(self, tmp_path):
        """If the file disappears after registry load, get_skill raises ValueError."""
        skill_file = tmp_path / "volatile.md"
        skill_file.write_text("temp", encoding="utf-8")
        registry = _make_registry_with_dir(tmp_path)
        skill_file.unlink()
        with pytest.raises(ValueError, match="cannot be read"):
            registry.get_skill("volatile")


# ---------------------------------------------------------------------------
# New prompt directory integration
# ---------------------------------------------------------------------------

class TestNewPromptDirectories:
    def test_pdf_prompt_files_are_discovered(self, tmp_path):
        pdf_dir = tmp_path / "pdf"
        pdf_dir.mkdir()
        (pdf_dir / "forms.md").write_text("PDF form instructions", encoding="utf-8")
        registry = _make_registry_with_dir(tmp_path)
        names = [s["name"] for s in registry.skills]
        assert "forms" in names

    def test_humanizer_main_prompt_files_are_discovered(self, tmp_path):
        hum_dir = tmp_path / "humanizer-main"
        hum_dir.mkdir()
        (hum_dir / "SKILL.md").write_text("Humanizer main skill", encoding="utf-8")
        registry = _make_registry_with_dir(tmp_path)
        names = [s["name"] for s in registry.skills]
        assert "SKILL" in names

    def test_docx_prompt_files_are_discovered(self, tmp_path):
        docx_dir = tmp_path / "docx"
        docx_dir.mkdir()
        (docx_dir / "ooxml.md").write_text("OOXML formatting guide", encoding="utf-8")
        registry = _make_registry_with_dir(tmp_path)
        names = [s["name"] for s in registry.skills]
        assert "ooxml" in names
