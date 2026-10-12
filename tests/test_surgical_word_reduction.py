"""
Tests for the surgical-word-reduction skill integration:

  * registry registration (REGISTERED_PROMPT_SUBDIRS)
  * AUTO_ROUTE_KEYWORDS presence + match_skill_for_task routing
  * dual mirrors (.agents/skills + meddraft_ai/prompts) existence + identity
  * specialist wiring (CoreWriter + ProofReader folder keywords)
  * skills-lock entry
  * skill content contracts (3-pass framework, section protocols, checklist)

No network I/O. Routing tests use an empty skill index so they exercise
keyword overlap deterministically.
"""

from __future__ import annotations

import inspect
import json
from pathlib import Path
from unittest.mock import MagicMock

from meddraft_ai.core.skill_registry import (
    REGISTERED_PROMPT_SUBDIRS,
    AUTO_ROUTE_KEYWORDS,
    SkillRegistry,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
SKILL_NAME = "surgical-word-reduction"


def _empty_registry() -> SkillRegistry:
    config = MagicMock()
    config.PROMPTS_DIR = REPO_ROOT / "meddraft_ai" / "prompts"
    registry = SkillRegistry.__new__(SkillRegistry)
    registry.config = config
    registry.prompts_dir = config.PROMPTS_DIR
    registry.skills = []
    return registry


class TestSurgicalRegistration:
    def test_subdir_registered(self):
        assert SKILL_NAME in REGISTERED_PROMPT_SUBDIRS

    def test_route_keywords_present(self):
        assert SKILL_NAME in AUTO_ROUTE_KEYWORDS
        assert len(AUTO_ROUTE_KEYWORDS[SKILL_NAME]) >= 2


class TestSurgicalRouting:
    def test_reduce_word_count_routes(self):
        assert _empty_registry().match_skill_for_task(
            "Reduce word count of my Discussion to meet word limit"
        ) == SKILL_NAME

    def test_shorten_manuscript_routes(self):
        assert _empty_registry().match_skill_for_task(
            "Shorten manuscript that is over word limit with concise revision"
        ) == SKILL_NAME

    def test_tighten_prose_routes(self):
        assert _empty_registry().match_skill_for_task(
            "Tighten prose to reduce word count under the word limit"
        ) == SKILL_NAME

    def test_unrelated_query_does_not_route(self):
        assert _empty_registry().match_skill_for_task(
            "Anatomy of the human ear"
        ) is None


class TestSurgicalMirrors:
    def test_agent_skill_and_prompt_pack_exist(self):
        assert (REPO_ROOT / ".agents" / "skills" / SKILL_NAME / "SKILL.md").exists()
        assert (REPO_ROOT / "meddraft_ai" / "prompts" / SKILL_NAME / "SKILL.md").exists()

    def test_mirrors_are_identical(self):
        agent = (REPO_ROOT / ".agents" / "skills" / SKILL_NAME / "SKILL.md").read_bytes()
        pack = (REPO_ROOT / "meddraft_ai" / "prompts" / SKILL_NAME / "SKILL.md").read_bytes()
        assert agent == pack

    def test_frontmatter_present(self):
        text = (REPO_ROOT / ".agents" / "skills" / SKILL_NAME / "SKILL.md").read_text(encoding="utf-8")
        assert "name: surgical-word-reduction" in text
        assert "description:" in text

    def test_registry_indexes_skill_file(self):
        registry = SkillRegistry()
        registry.prompts_dir = REPO_ROOT / "meddraft_ai" / "prompts"
        registry.load()
        rel_paths = {s["rel_path"].replace("\\", "/") for s in registry.skills}
        assert f"{SKILL_NAME}/SKILL.md" in rel_paths


class TestSurgicalSpecialistWiring:
    def test_core_writer_wiring(self):
        from meddraft_ai.agents import specialists
        assert SKILL_NAME in inspect.getsource(specialists.CoreWriterSpecialist.__init__)

    def test_proof_reader_wiring(self):
        from meddraft_ai.agents import specialists
        assert SKILL_NAME in inspect.getsource(specialists.ProofReaderSpecialist.__init__)

    def test_core_writer_preloads_on_word_limit_query(self):
        # Convention parity with citation-integrity (see test_external_skills):
        # generic packs are carried via folder_keywords, not the Nature
        # query-aware preload. Assert the wiring, plus end-to-end routing.
        from meddraft_ai.agents.specialists import CoreWriterSpecialist
        sp = CoreWriterSpecialist()
        assert SKILL_NAME in sp.folder_keywords
        assert _empty_registry().match_skill_for_task(
            "Reduce word count of my manuscript to meet word limit with concise revision"
        ) == SKILL_NAME


class TestSurgicalContent:
    def test_three_pass_framework(self):
        text = (REPO_ROOT / ".agents" / "skills" / SKILL_NAME / "SKILL.md").read_text(encoding="utf-8")
        for marker in ("Pass 1", "Pass 2", "Pass 3", "8-10%", "5-7%"):
            assert marker in text, marker

    def test_section_protocols(self):
        text = (REPO_ROOT / ".agents" / "skills" / SKILL_NAME / "SKILL.md").read_text(encoding="utf-8")
        for marker in ("Introduction", "Methods and Results", "Discussion and Conclusion"):
            assert marker in text, marker

    def test_replacement_dictionary_and_checklist(self):
        text = (REPO_ROOT / ".agents" / "skills" / SKILL_NAME / "SKILL.md").read_text(encoding="utf-8")
        for marker in ("due to the fact that", "in order to", "Data integrity", "Scientific meaning", "Academic tone"):
            assert marker in text, marker

    def test_hard_constraints_no_invention(self):
        text = (REPO_ROOT / ".agents" / "skills" / SKILL_NAME / "SKILL.md").read_text(encoding="utf-8")
        assert "Hard constraints" in text
        assert "Never" in text


class TestSurgicalSkillsLock:
    def test_lock_covers_skill(self):
        locked = json.loads((REPO_ROOT / "skills-lock.json").read_text(encoding="utf-8"))["skills"]
        entry = locked.get(SKILL_NAME)
        assert entry is not None
        assert entry["source"] == f"./.agents/skills/{SKILL_NAME}"
        assert entry["sourceType"] == "local"
        assert len(entry["computedHash"]) == 64
