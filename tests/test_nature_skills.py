"""
Tests for the Nature Paper Skills integration (20 vendored skills):

  * registry registration (REGISTERED_PROMPT_SUBDIRS)
  * AUTO_ROUTE_KEYWORDS presence + match_skill_for_task routing
  * dual mirrors (.agents/skills + meddraft_ai/prompts) existence
  * specialist wiring (folder keywords + RebuttalSpecialist)
  * skills-lock entries for the 20 new agent skills

No network I/O. Routing tests use an empty skill index so they exercise the
chain hook + keyword overlap deterministically.
"""

from __future__ import annotations

import inspect
import json
from pathlib import Path
from unittest.mock import MagicMock

from meddraft_ai.core.nature_integration import (
    NATURE_SKILL_TO_SPECIALIST,
    NATURE_TRIGGER_KEYWORDS,
    PIPELINE_CHAINS,
    get_nature_chain,
    nature_keywords_for,
)
from meddraft_ai.core.skill_registry import (
    REGISTERED_PROMPT_SUBDIRS,
    AUTO_ROUTE_KEYWORDS,
    SkillRegistry,
)

REPO_ROOT = Path(__file__).resolve().parent.parent

NATURE_SKILLS = sorted(NATURE_SKILL_TO_SPECIALIST)


def _empty_registry() -> SkillRegistry:
    config = MagicMock()
    config.PROMPTS_DIR = REPO_ROOT / "meddraft_ai" / "prompts"
    registry = SkillRegistry.__new__(SkillRegistry)
    registry.config = config
    registry.prompts_dir = config.PROMPTS_DIR
    registry.skills = []
    return registry


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

class TestNatureRegistration:
    def test_all_skills_registered_as_subdirs(self):
        for name in NATURE_SKILLS:
            assert name in REGISTERED_PROMPT_SUBDIRS, name

    def test_manifest_dir_registered(self):
        assert "nature-paper-skills" in REGISTERED_PROMPT_SUBDIRS

    def test_all_skills_have_route_keywords(self):
        for name in NATURE_SKILLS:
            assert name in AUTO_ROUTE_KEYWORDS, name
            assert len(AUTO_ROUTE_KEYWORDS[name]) >= 2, name

    def test_trigger_map_matches_registry(self):
        assert set(NATURE_TRIGGER_KEYWORDS) == set(NATURE_SKILLS)


# ---------------------------------------------------------------------------
# Routing — chain hook + keyword overlap
# ---------------------------------------------------------------------------

class TestNatureRouting:
    def test_submission_preflight_routes(self):
        assert _empty_registry().match_skill_for_task(
            "Run a submission audit preflight check before I submit my manuscript"
        ) == "submission-audit"

    def test_claim_source_routes(self):
        assert _empty_registry().match_skill_for_task(
            "Do these cited sources actually support my claims? verify claim to evidence"
        ) == "claim-source-verification"

    def test_rebuttal_routes_to_chain_primary(self):
        assert _empty_registry().match_skill_for_task(
            "Draft a point-by-point rebuttal response letter to reviewer comments"
        ) == "paper-reviewer"

    def test_results_repair_routes(self):
        assert _empty_registry().match_skill_for_task(
            "Revise my Results section, it reads like stitched figure captions"
        ) == "results-section-revision"

    def test_figure_plan_routes(self):
        assert _empty_registry().match_skill_for_task(
            "Plan my figures: one claim per figure with legend sync"
        ) == "figure-planner"

    def test_stats_audit_routes(self):
        assert _empty_registry().match_skill_for_task(
            "Audit my statistical reporting: independent units and technical replicates"
        ) == "stats-reporting-audit"

    def test_data_availability_routes(self):
        assert _empty_registry().match_skill_for_task(
            "Write my data availability statement with repository plan"
        ) == "data-availability"

    def test_de_audit_routes(self):
        assert _empty_registry().match_skill_for_task(
            "Remove defensive writing and de-audit this manuscript"
        ) == "anti-defensive-writing"

    def test_review_article_routes(self):
        assert _empty_registry().match_skill_for_task(
            "I want to write a review article with a governing plan document"
        ) == "review-article-architecture"

    def test_paper_analyzer_routes(self):
        assert _empty_registry().match_skill_for_task(
            "Run a paper analyzer single-paper analysis with structured notes on claims"
        ) == "paper-analyzer"

    # Existing skills must keep winning their own signals (no stealing).
    def test_trials_routing_unchanged(self):
        assert _empty_registry().match_skill_for_task(
            "What Phase 3 trials are recruiting for multiple sclerosis?"
        ) == "medical-clinicaltrials"

    def test_citation_integrity_routing_unchanged(self):
        assert _empty_registry().match_skill_for_task(
            "Write a literature review with numbered citations and a verifiable reference list"
        ) == "citation-integrity"

    def test_search_agent_routing_unchanged(self):
        assert _empty_registry().match_skill_for_task(
            "Compile background literature and a timeline of key papers with a research log"
        ) == "academic-search-agent"


# ---------------------------------------------------------------------------
# get_nature_chain unit behavior
# ---------------------------------------------------------------------------

class TestNatureChains:
    def test_pre_submission_chain(self):
        chain, specialist, skills = get_nature_chain(
            "submission audit preflight before resubmission"
        )
        assert chain == "pre_submission"
        assert specialist == "VERIFIER_AND_STATS"
        assert skills == PIPELINE_CHAINS["pre_submission"]["skills"]

    def test_rebuttal_chain(self):
        chain, specialist, skills = get_nature_chain(
            "point-by-point rebuttal to reviewer comments"
        )
        assert chain == "rebuttal"
        assert specialist == "REBUTTAL"
        assert "rebuttal-response" in skills

    def test_no_match_returns_empties(self):
        assert get_nature_chain("") == (None, None, [])
        assert get_nature_chain("Anatomy of the human ear") == (None, None, [])

    def test_every_chain_skill_has_specialist_mapping(self):
        for chain in PIPELINE_CHAINS.values():
            assert chain["specialist"] in {
                "VERIFIER_AND_STATS", "CORE_WRITER", "PROOF_READER", "REBUTTAL",
                "ACADEMIC_PAPER", "DEEP_RESEARCH",
            }
            for skill in chain["skills"]:
                assert skill in NATURE_SKILL_TO_SPECIALIST, skill


# ---------------------------------------------------------------------------
# Dual mirrors on disk
# ---------------------------------------------------------------------------

class TestNatureMirrors:
    def test_agent_skill_and_prompt_pack_exist(self):
        for name in NATURE_SKILLS:
            assert (REPO_ROOT / ".agents" / "skills" / name / "SKILL.md").exists(), name
            assert (REPO_ROOT / "meddraft_ai" / "prompts" / name / "SKILL.md").exists(), name

    def test_mirrors_are_identical(self):
        for name in NATURE_SKILLS:
            agent = (REPO_ROOT / ".agents" / "skills" / name / "SKILL.md").read_bytes()
            pack = (REPO_ROOT / "meddraft_ai" / "prompts" / name / "SKILL.md").read_bytes()
            assert agent == pack, name

    def test_manifest_and_provenance_exist(self):
        manifest = REPO_ROOT / "meddraft_ai" / "prompts" / "nature-paper-skills"
        for fname in ("README.md", "UPSTREAM_VERSION.txt", "NOTICE", "LICENSE-APACHE"):
            assert (manifest / fname).exists(), fname

    def test_registry_indexes_all_skill_files(self):
        registry = SkillRegistry()
        registry.prompts_dir = REPO_ROOT / "meddraft_ai" / "prompts"
        registry.load()
        rel_paths = {s["rel_path"].replace("\\", "/") for s in registry.skills}
        for name in NATURE_SKILLS:
            assert f"{name}/SKILL.md" in rel_paths, name


# ---------------------------------------------------------------------------
# Specialist wiring
# ---------------------------------------------------------------------------

class TestNatureSpecialistWiring:
    def test_core_writer_wiring(self):
        from meddraft_ai.agents import specialists
        src = inspect.getsource(specialists.CoreWriterSpecialist.__init__)
        for frag in ("manuscript-optimizer/SKILL.md", "results-section-revision/SKILL.md",
                     "figure-planner/SKILL.md", "review-article-architecture/SKILL.md"):
            assert frag in src, frag

    def test_verifier_wiring(self):
        from meddraft_ai.agents import specialists
        src = inspect.getsource(specialists.VerifierAndStatsSpecialist.__init__)
        for frag in ("claim-source-verification/SKILL.md", "stats-reporting-audit/SKILL.md",
                     "submission-audit/SKILL.md", "citation-verifier/SKILL.md",
                     "data-availability/SKILL.md"):
            assert frag in src, frag

    def test_proof_reader_wiring(self):
        from meddraft_ai.agents import specialists
        src = inspect.getsource(specialists.ProofReaderSpecialist.__init__)
        for frag in ("scientific-prose-style/SKILL.md", "anti-defensive-writing/SKILL.md",
                     "write-scientific-manuscript/SKILL.md"):
            assert frag in src, frag

    def test_deep_research_and_academic_paper_wiring(self):
        from meddraft_ai.agents import specialists
        assert "paper-analyzer/SKILL.md" in inspect.getsource(
            specialists.DeepResearchSpecialist.__init__)
        src = inspect.getsource(specialists.AcademicPaperSpecialist.__init__)
        for frag in ("nature-portfolio-playbook/SKILL.md", "figure-style/SKILL.md",
                     "results-analysis/SKILL.md"):
            assert frag in src, frag

    def test_rebuttal_specialist_exists(self):
        from meddraft_ai.agents import specialists
        assert hasattr(specialists, "RebuttalSpecialist")
        assert "reviewer-response" in (specialists.RebuttalSpecialist.__doc__ or "")
        assert "rebuttal-response/SKILL.md" in inspect.getsource(
            specialists.RebuttalSpecialist.__init__)
        assert "paper-reviewer/SKILL.md" in inspect.getsource(
            specialists.RebuttalSpecialist.__init__)

    def test_nature_keywords_for_matches_mapping(self):
        for skill, specialist in NATURE_SKILL_TO_SPECIALIST.items():
            frags = nature_keywords_for(specialist)
            assert any(skill in f for f in frags), (skill, specialist)


# ---------------------------------------------------------------------------
# Specialist context loading (query-aware Nature preload)
# ---------------------------------------------------------------------------

class TestNatureContextLoading:
    def test_verifier_preloads_chain_skills(self):
        from meddraft_ai.agents.specialists import VerifierAndStatsSpecialist
        ctx = VerifierAndStatsSpecialist().load_context(
            "Run a submission audit preflight before I submit my manuscript"
        )
        for marker in ("name: submission-audit", "name: claim-source-verification",
                       "name: stats-reporting-audit"):
            assert marker in ctx, marker

    def test_plain_query_loads_no_nature(self):
        from meddraft_ai.agents.specialists import VerifierAndStatsSpecialist
        ctx = VerifierAndStatsSpecialist().load_context("What Phase 3 trials are recruiting?")
        for skill in NATURE_SKILLS:
            assert f"name: {skill}" not in ctx, skill

    def test_neutral_query_matches_noarg(self):
        from meddraft_ai.agents.specialists import CoreWriterSpecialist
        sp = CoreWriterSpecialist()
        assert sp.load_context("Anatomy of the human ear") == sp.load_context()

    def test_core_results_query_preloads(self):
        from meddraft_ai.agents.specialists import CoreWriterSpecialist
        ctx = CoreWriterSpecialist().load_context(
            "Revise my Results section, it reads like stitched figure captions"
        )
        assert "name: results-section-revision" in ctx

    def test_proof_deaudit_preloads(self):
        from meddraft_ai.agents.specialists import ProofReaderSpecialist
        ctx = ProofReaderSpecialist().load_context(
            "Remove defensive writing and de-audit this manuscript"
        )
        assert "name: anti-defensive-writing" in ctx

    def test_rebuttal_preloads_both(self):
        from meddraft_ai.agents.specialists import RebuttalSpecialist
        ctx = RebuttalSpecialist().load_context(
            "Draft a point-by-point rebuttal response letter"
        )
        assert "name: rebuttal-response" in ctx
        assert "name: paper-reviewer" in ctx


# ---------------------------------------------------------------------------
# skills-lock entries
# ---------------------------------------------------------------------------

class TestNatureSkillsLock:
    def test_lock_covers_all_nature_skills(self):
        locked = json.loads((REPO_ROOT / "skills-lock.json").read_text(encoding="utf-8"))["skills"]
        for name in NATURE_SKILLS:
            entry = locked.get(name)
            assert entry is not None, name
            assert entry["source"] == f"./.agents/skills/{name}", name
            assert entry["sourceType"] == "local", name
            assert len(entry["computedHash"]) == 64, name
