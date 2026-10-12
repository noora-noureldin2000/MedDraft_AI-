"""
Tests for the three externally sourced skill integrations:

  * medical-clinicaltrials (pascalwhoop) — filtered CT.gov search + NCT lookup
  * citation-integrity (teamolab academic-writing) — routing + specialist wiring
  * academic-search-agent (teamolab call-academic-search-agent) — planner + routing

All network I/O is mocked. Tests run offline, instantly, deterministically.
"""

from __future__ import annotations

import inspect
import json
from pathlib import Path
from unittest.mock import patch
from io import BytesIO

from meddraft_ai.search import clinicaltrials as ct
from meddraft_ai.search import search_planner as planner
from meddraft_ai.core.skill_registry import (
    REGISTERED_PROMPT_SUBDIRS,
    AUTO_ROUTE_KEYWORDS,
)

REPO_ROOT = Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------------------
# clinicaltrials — pure helpers
# ---------------------------------------------------------------------------

class TestPhaseStatusNormalization:
    def test_phase_aliases(self):
        assert ct.normalize_phase("Phase 3") == "PHASE3"
        assert ct.normalize_phase("phase ii") == "PHASE2"
        assert ct.normalize_phase("PHASE1") == "PHASE1"

    def test_unknown_phase_returns_empty(self):
        assert ct.normalize_phase("Phase 9") == ""

    def test_status_aliases(self):
        assert ct.normalize_status("Recruiting") == "RECRUITING"
        assert ct.normalize_status("completed") == "COMPLETED"

    def test_unknown_status_returns_empty(self):
        assert ct.normalize_status("Maybe later") == ""


class TestShouldIncludeTrials:
    def test_clinical_topic_triggers(self):
        assert ct.should_include_trials("Phase 3 randomized trial of SGLT2 inhibitors") is True

    def test_nct_id_triggers(self):
        assert ct.should_include_trials("Summarize NCT04368728") is True

    def test_basic_topic_does_not_trigger(self):
        assert ct.should_include_trials("Anatomy of the human ear") is False

    def test_empty_topic_does_not_trigger(self):
        assert ct.should_include_trials("") is False


# ---------------------------------------------------------------------------
# clinicaltrials — mocked HTTP (urllib boundary only)
# ---------------------------------------------------------------------------

CTG_SEARCH_PAYLOAD = {
    "totalCount": 1,
    "studies": [
        {
            "protocolSection": {
                "identificationModule": {"nctId": "NCT04368728", "briefTitle": "Test vaccine trial"},
                "statusModule": {
                    "overallStatus": "RECRUITING",
                    "phases": ["PHASE3"],
                    "startDateStruct": {"date": "2020-05-01"},
                    "completionDateStruct": {"date": "2023-01-01"},
                },
                "conditionsModule": {"conditions": ["COVID-19"]},
                "armsInterventionsModule": {
                    "interventions": [{"type": "BIOLOGICAL", "name": "BNT162b2"}]
                },
                "descriptionModule": {"briefSummary": "A test summary."},
                "designModule": {"studyType": "INTERVENTIONAL"},
            }
        }
    ],
}


def _fake_urlopen(payload: dict):
    data = json.dumps(payload).encode()

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return data

    return FakeResponse()


class TestSearchStudiesMocked:
    def test_filtered_search_parses_results(self):
        with patch("urllib.request.urlopen", return_value=_fake_urlopen(CTG_SEARCH_PAYLOAD)):
            res = ct.search_studies(condition="COVID-19", phase="Phase 3", status="Recruiting")
        assert res["success"] is True
        assert res["count"] == 1
        first = res["results"][0]
        assert first["nct_id"] == "NCT04368728"
        assert first["phase"] == "PHASE3"
        assert first["url"] == "https://clinicaltrials.gov/study/NCT04368728"

    def test_invalid_phase_fails_fast_without_network(self):
        with patch("urllib.request.urlopen", side_effect=AssertionError("must not call network")):
            res = ct.search_studies(phase="Phase 9")
        assert res["success"] is False
        assert "Phase 3" in res["error"] or "phase" in res["error"].lower()

    def test_network_failure_returns_not_success(self):
        with patch("urllib.request.urlopen", side_effect=OSError("offline")):
            res = ct.search_studies(condition="diabetes")
        assert res["success"] is False
        assert res["results"] == []


class TestGetStudyMocked:
    def test_invalid_nct_id_rejected(self):
        res = ct.get_study("not-an-nct")
        assert res["success"] is False
        assert "NCT" in res["error"]

    def test_valid_nct_fetch_parses_detail(self):
        with patch("urllib.request.urlopen", return_value=_fake_urlopen(CTG_SEARCH_PAYLOAD["studies"][0])):
            res = ct.get_study("NCT04368728")
        assert res["success"] is True
        assert res["study"]["nct_id"] == "NCT04368728"

    def test_orchestrator_search_trials_never_raises(self):
        from meddraft_ai.search.research_orchestrator import ResearchOrchestrator
        orch = ResearchOrchestrator.__new__(ResearchOrchestrator)
        with patch("urllib.request.urlopen", side_effect=OSError("offline")):
            assert orch.search_trials(query="diabetes trial") == []
            assert orch.get_trial("NCT00000000")["success"] is False


# ---------------------------------------------------------------------------
# search_planner — pure logic
# ---------------------------------------------------------------------------

class TestSearchPlanner:
    def test_plan_returns_three_to_five_angles(self):
        angles = planner.plan_search_angles("diffusion models in medical imaging")
        assert 3 <= len(angles) <= 5
        assert len(set(angles)) == len(angles)

    def test_empty_topic_returns_empty(self):
        assert planner.plan_search_angles("") == []
        assert planner.plan_search_angles("   ") == []

    def test_truncate_keeps_budget(self):
        text = " ".join(f"w{i}" for i in range(6000))
        out = planner.truncate_to_budget(text, budget=5000)
        assert len(out.split()) <= 5100  # words + small marker overhead
        assert "w0" in out and "w5999" in out

    def test_stop_collecting_threshold(self):
        assert planner.should_stop_collecting("word " * 4000) is True
        assert planner.should_stop_collecting("short log") is False


# ---------------------------------------------------------------------------
# Registry routing + wiring
# ---------------------------------------------------------------------------

class TestNewSkillsRouting:
    def test_subdirs_registered(self):
        for name in ("medical-clinicaltrials", "citation-integrity", "academic-search-agent"):
            assert name in REGISTERED_PROMPT_SUBDIRS, name

    def test_route_keywords_present(self):
        for name in ("medical-clinicaltrials", "citation-integrity", "academic-search-agent"):
            assert name in AUTO_ROUTE_KEYWORDS, name

    def test_trials_task_routes(self):
        from meddraft_ai.core.skill_registry import SkillRegistry
        from unittest.mock import MagicMock
        config = MagicMock()
        config.PROMPTS_DIR = REPO_ROOT / "meddraft_ai" / "prompts"
        registry = SkillRegistry.__new__(SkillRegistry)
        registry.config = config
        registry.prompts_dir = config.PROMPTS_DIR
        registry.skills = []
        assert registry.match_skill_for_task(
            "What Phase 3 trials are recruiting for multiple sclerosis?"
        ) == "medical-clinicaltrials"

    def test_lit_review_task_routes(self):
        from meddraft_ai.core.skill_registry import SkillRegistry
        from unittest.mock import MagicMock
        config = MagicMock()
        config.PROMPTS_DIR = REPO_ROOT / "meddraft_ai" / "prompts"
        registry = SkillRegistry.__new__(SkillRegistry)
        registry.config = config
        registry.prompts_dir = config.PROMPTS_DIR
        registry.skills = []
        assert registry.match_skill_for_task(
            "Write a literature review with numbered citations and a verifiable reference list"
        ) == "citation-integrity"

    def test_background_search_task_routes(self):
        from meddraft_ai.core.skill_registry import SkillRegistry
        from unittest.mock import MagicMock
        config = MagicMock()
        config.PROMPTS_DIR = REPO_ROOT / "meddraft_ai" / "prompts"
        registry = SkillRegistry.__new__(SkillRegistry)
        registry.config = config
        registry.prompts_dir = config.PROMPTS_DIR
        registry.skills = []
        assert registry.match_skill_for_task(
            "Compile background literature and a timeline of key papers with a research log"
        ) == "academic-search-agent"

    def test_packs_and_agent_skills_exist(self):
        for name in ("medical-clinicaltrials", "citation-integrity", "academic-search-agent"):
            assert (REPO_ROOT / "meddraft_ai" / "prompts" / name / "SKILL.md").exists(), name
            assert (REPO_ROOT / ".agents" / "skills" / name / "SKILL.md").exists(), name

    def test_specialist_wiring(self):
        from meddraft_ai.agents import specialists
        assert "citation-integrity" in inspect.getsource(specialists.CoreWriterSpecialist.__init__)
        assert "citation-integrity" in inspect.getsource(specialists.ProofReaderSpecialist.__init__)
        assert "academic-search-agent" in inspect.getsource(specialists.DeepResearchSpecialist.__init__)
        assert "medical-clinicaltrials" in inspect.getsource(specialists.ReferencesSpecialist.__init__)
        assert "medical-clinicaltrials" in inspect.getsource(specialists.TrialsSpecialist.__init__)


class TestNewCliCommands:
    def test_trials_search_parses(self):
        from meddraft_ai.cli import build_parser
        args = build_parser().parse_args(
            ["refs", "trials-search", "--condition", "diabetes", "--phase", "Phase 3"]
        )
        assert args.refs_command == "trials-search"
        assert args.condition == "diabetes"

    def test_trials_get_parses(self):
        from meddraft_ai.cli import build_parser
        args = build_parser().parse_args(["refs", "trials-get", "NCT04368728"])
        assert args.refs_command == "trials-get"
        assert args.nct_id == "NCT04368728"

    def test_plan_angles_parses(self):
        from meddraft_ai.cli import build_parser
        args = build_parser().parse_args(["refs", "plan-angles", "SGLT2 inhibitors"])
        assert args.refs_command == "plan-angles"
