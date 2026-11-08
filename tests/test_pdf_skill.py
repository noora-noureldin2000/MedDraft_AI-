"""
Tests for the pdf skill integration:

  * dual mirrors (.agents/skills/pdf + meddraft_ai/prompts/pdf) existence/identity
  * registry registration, directory-level lookup, and auto-routing
  * specialist wiring (DeepResearch folder keywords)
  * skills-lock entry
  * content/script contracts (text + table extraction, forms, OCR)

No network I/O. Routing tests use an empty skill index so they exercise the
keyword table deterministically.
"""

from __future__ import annotations

import inspect
import json
import re
from pathlib import Path
from unittest.mock import MagicMock

from meddraft_ai.core.skill_registry import (
    AUTO_ROUTE_KEYWORDS,
    REGISTERED_PROMPT_SUBDIRS,
    SkillRegistry,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
SKILL_NAME = "pdf"
AGENT_SKILL_DIR = REPO_ROOT / ".agents" / "skills" / SKILL_NAME
PROMPT_SKILL_DIR = REPO_ROOT / "meddraft_ai" / "prompts" / SKILL_NAME


def _empty_registry() -> SkillRegistry:
    config = MagicMock()
    config.PROMPTS_DIR = REPO_ROOT / "meddraft_ai" / "prompts"
    registry = SkillRegistry.__new__(SkillRegistry)
    registry.config = config
    registry.prompts_dir = config.PROMPTS_DIR
    registry.skills = []
    return registry


def _comparable_files(root: Path) -> set[str]:
    return {
        p.relative_to(root).as_posix()
        for p in root.rglob("*")
        if p.is_file() and "__pycache__" not in p.parts
    }


class TestPdfRegistration:
    def test_subdir_registered(self):
        assert SKILL_NAME in REGISTERED_PROMPT_SUBDIRS

    def test_route_keywords_present(self):
        assert SKILL_NAME in AUTO_ROUTE_KEYWORDS
        assert len(AUTO_ROUTE_KEYWORDS[SKILL_NAME]) >= 5


class TestPdfRouting:
    def test_parse_text_and_tables_routes(self):
        assert _empty_registry().match_skill_for_task(
            "Parse this PDF and extract text and tables"
        ) == SKILL_NAME

    def test_fill_form_routes(self):
        assert _empty_registry().match_skill_for_task(
            "Fill out this PDF form and return the completed file"
        ) == SKILL_NAME

    def test_merge_or_split_routes(self):
        registry = _empty_registry()
        assert registry.match_skill_for_task("Merge PDF files into one document") == SKILL_NAME
        assert registry.match_skill_for_task("Split pages of a PDF into separate files") == SKILL_NAME

    def test_unrelated_query_does_not_route(self):
        assert _empty_registry().match_skill_for_task(
            "Anatomy of the human ear"
        ) is None


class TestPdfMirrors:
    def test_dual_mirrors_exist(self):
        assert (AGENT_SKILL_DIR / "SKILL.md").is_file()
        assert (PROMPT_SKILL_DIR / "SKILL.md").is_file()

    def test_mirrors_have_same_file_set(self):
        assert _comparable_files(AGENT_SKILL_DIR) == _comparable_files(PROMPT_SKILL_DIR)

    def test_mirrored_files_are_identical(self):
        for rel in _comparable_files(AGENT_SKILL_DIR):
            assert (AGENT_SKILL_DIR / rel).read_bytes() == (PROMPT_SKILL_DIR / rel).read_bytes(), rel

    def test_frontmatter_present(self):
        text = (AGENT_SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
        assert "name: pdf" in text
        assert "description:" in text


class TestPdfRegistryLookup:
    def test_registry_indexes_pack_files(self):
        registry = SkillRegistry()
        registry.prompts_dir = PROMPT_SKILL_DIR.parent
        registry.load()
        rel_paths = {s["rel_path"].replace("\\", "/") for s in registry.skills}
        assert "pdf/SKILL.md" in rel_paths
        assert "pdf/forms.md" in rel_paths

    def test_get_skill_resolves_pack_directory(self):
        content = _empty_registry().get_skill(SKILL_NAME)
        assert "# PDF Processing Guide" in content
        assert "pdfplumber" in content

    def test_get_skill_rejects_path_traversal(self):
        registry = _empty_registry()
        for name in ("../pdf", "pdf/../../secrets", "..", ""):
            try:
                registry.get_skill(name)
            except ValueError:
                pass
            else:
                raise AssertionError(f"traversal name accepted: {name!r}")


class TestPdfSpecialistWiring:
    def test_deep_research_wiring(self):
        from meddraft_ai.agents import specialists
        source = inspect.getsource(specialists.DeepResearchSpecialist.__init__)
        assert "pdf/SKILL.md" in source


class TestPdfSkillsLock:
    def test_lock_covers_skill(self):
        locked = json.loads(
            (REPO_ROOT / "skills-lock.json").read_text(encoding="utf-8")
        )["skills"]
        entry = locked.get(SKILL_NAME)
        assert entry is not None
        assert entry["source"] == f"./.agents/skills/{SKILL_NAME}"
        assert entry["sourceType"] == "local"
        assert re.fullmatch(r"[0-9a-f]{64}", entry["computedHash"])


class TestPdfContent:
    def test_skill_covers_text_and_table_extraction(self):
        text = (AGENT_SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
        for marker in ("page.extract_text()", "page.extract_tables()", "pypdf", "pdfplumber"):
            assert marker in text, marker

    def test_skill_covers_ocr_and_forms(self):
        text = (AGENT_SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
        for marker in ("pytesseract", "forms.md"):
            assert marker in text, marker

    def test_form_workflow_and_scripts_present(self):
        forms = (AGENT_SKILL_DIR / "forms.md").read_text(encoding="utf-8")
        assert "Fillable fields" in forms
        assert "extract_form_field_info" in forms
        scripts = AGENT_SKILL_DIR / "scripts"
        for name in (
            "check_fillable_fields.py",
            "extract_form_field_info.py",
            "fill_fillable_fields.py",
            "fill_pdf_form_with_annotations.py",
            "convert_pdf_to_images.py",
        ):
            assert (scripts / name).is_file(), name
