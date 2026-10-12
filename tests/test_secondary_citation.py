"""
Tests for the secondary-citation-extractor skill integration.

Covers: auto-trigger routing, in-text key detection, bibliography tracing,
dual-attribution formatting, SkillRegistry auto-routing, and CLI registration.
All tests run offline — live API calls are mocked to raise.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from meddraft_ai.extraction.secondary_citation import (
    SecondaryCitationExtractor,
    SKILL_NAME,
)
from meddraft_ai.core.skill_registry import (
    SkillRegistry,
    REGISTERED_PROMPT_SUBDIRS,
    AUTO_ROUTE_KEYWORDS,
)

REPO_ROOT = Path(__file__).resolve().parent.parent


def _offline(*args, **kwargs):
    raise OSError("offline — no network in tests")


SAMPLE_PDF_TEXT = """Mechanisms of Insulin Resistance in Metabolic Syndrome
Al-Mansoor, H., & Chen, Y. (2024). Journal of Endocrinology & Metabolism.

Skeletal muscle GLUT4 translocation is blunted by approximately 40% under sustained lipid infusion [28].

References
28. Roden M, Price TB, Perseghin G. Mechanism of free fatty acid-induced insulin resistance in humans. J Clin Invest. 1996;97:2859-65.
"""


class TestAutoTrigger:
    def test_as_cited_in_triggers(self):
        assert SecondaryCitationExtractor.should_trigger(
            "Roden et al. (1996), as cited in Al-Mansoor and Chen (2024)"
        ) is True

    def test_skill_name_triggers(self):
        assert SecondaryCitationExtractor.should_trigger(
            "Use secondary-citation-extractor on this excerpt"
        ) is True

    def test_plain_text_does_not_trigger(self):
        assert SecondaryCitationExtractor.should_trigger(
            "The sky is blue and water is wet."
        ) is False

    def test_match_score_orders_correctly(self):
        strong = SecondaryCitationExtractor.match_score(
            "Trace this nested citation and build a dual bibliography, as cited in Smith (2020)"
        )
        weak = SecondaryCitationExtractor.match_score("Hello world sunny day")
        assert strong > weak


class TestDetectionAndTracing:
    def test_detect_bracket_and_author_date_keys(self):
        keys = SecondaryCitationExtractor.detect_in_text_keys(
            "Blunted by 40% [28]. Neighborhood sampling caps memory (Hamilton 2017)."
        )
        kinds = {k["kind"] for k in keys}
        assert "bracket" in kinds
        assert "author-date" in kinds

    def test_parse_reference_list(self):
        entries = SecondaryCitationExtractor.parse_reference_list(SAMPLE_PDF_TEXT)
        assert len(entries) == 1
        assert entries[0]["index"] == "28"
        assert entries[0]["year"] == 1996

    def test_trace_bracket_to_index(self):
        entries = SecondaryCitationExtractor.parse_reference_list(SAMPLE_PDF_TEXT)
        hit = SecondaryCitationExtractor.trace_to_reference("[28]", entries)
        assert hit["index"] == "28"
        assert "Roden" in hit["raw"]

    def test_trace_missing_entry_flagged(self):
        hit = SecondaryCitationExtractor.trace_to_reference("[99]", [])
        assert hit.get("missing") is True


class TestExtractOffline:
    def test_extract_returns_dual_attribution_without_network(self):
        with patch(
            "meddraft_ai.extraction.citation_tracker.CitationVerifier.verify_doi",
            side_effect=_offline,
        ), patch(
            "meddraft_ai.validation.reference_validator.validate_citation",
            side_effect=_offline,
        ):
            results = SecondaryCitationExtractor.extract(
                SAMPLE_PDF_TEXT,
                container_meta={"author": "Al-Mansoor, H.", "title": "Mechanisms"},
                max_claims=5,
            )
        assert len(results) >= 1
        first = results[0]
        assert first.in_text_key == "[28]"
        assert "as cited in" in first.in_text_attribution() or "as cited by" in first.in_text_attribution()

    def test_markdown_template_shape(self):
        with patch(
            "meddraft_ai.extraction.citation_tracker.CitationVerifier.verify_doi",
            side_effect=_offline,
        ), patch(
            "meddraft_ai.validation.reference_validator.validate_citation",
            side_effect=_offline,
        ):
            md = SecondaryCitationExtractor.extract_to_markdown(
                SAMPLE_PDF_TEXT,
                container_meta={"author": "Al-Mansoor, H.", "title": "Mechanisms"},
                max_claims=5,
            )
        assert "### Extracted Claim / Finding" in md
        assert "### Full Bibliographic Entries" in md
        assert "Original Source (Root Work)" in md
        assert "Container Source (PDF Analyzed)" in md


class TestRegistryIntegration:
    def test_subdir_registered(self):
        assert "secondary-citation-extractor" in REGISTERED_PROMPT_SUBDIRS

    def test_auto_route_keywords_present(self):
        assert "secondary-citation-extractor" in AUTO_ROUTE_KEYWORDS

    def test_match_skill_for_task_routes(self):
        registry = SkillRegistry.__new__(SkillRegistry)
        from unittest.mock import MagicMock
        config = MagicMock()
        config.PROMPTS_DIR = REPO_ROOT / "meddraft_ai" / "prompts"
        registry.config = config
        registry.prompts_dir = config.PROMPTS_DIR
        registry.skills = []
        routed = registry.match_skill_for_task(
            "Trace this nested citation, as cited in Smith (2020), dual bibliography please"
        )
        assert routed == SKILL_NAME

    def test_pack_file_indexed(self):
        pack = REPO_ROOT / "meddraft_ai" / "prompts" / "secondary-citation-extractor" / "SKILL.md"
        assert pack.exists()
        agent_skill = REPO_ROOT / ".agents" / "skills" / "secondary-citation-extractor" / "SKILL.md"
        assert agent_skill.exists()

    def test_specialist_keyword_wiring(self):
        from meddraft_ai.agents.specialists import SecondaryCitationSpecialist
        # Real check: constructor keywords via inspect without full init
        import inspect
        src = inspect.getsource(SecondaryCitationSpecialist.__init__)
        assert "secondary-citation-extractor" in src


class TestCliIntegration:
    def test_secondary_cite_subcommand_registered(self):
        from meddraft_ai.cli import build_parser
        parser = build_parser()
        import io
        from contextlib import redirect_stderr
        # Parse a secondary-cite invocation — must not error on argument shape.
        args = parser.parse_args(["refs", "secondary-cite", "some excerpt (Smith, 2020)"])
        assert args.refs_command == "secondary-cite"
        assert args.style == "Harvard"
