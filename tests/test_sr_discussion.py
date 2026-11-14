"""Tests for the systematic-review-discussion skill and its wiring.

The skill has four integration points, all covered here:

1. registry registration and automatic routing (``skill_registry``);
2. specialist wiring (``specialists.SystematicReviewDiscussionSpecialist``);
3. deterministic gates (``core.sr_discussion``);
4. CLI tools (``meddraft_ai sr ...``).

All tests are offline and deterministic.
"""

from __future__ import annotations

import inspect
import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from meddraft_ai.cli import _run_sr, build_parser
from meddraft_ai.core.skill_registry import (
    AUTO_ROUTE_KEYWORDS,
    REGISTERED_PROMPT_SUBDIRS,
    SkillRegistry,
)
from meddraft_ai.core.sr_discussion import (
    SKILL_NAME,
    audit_discussion,
    build_system_command,
    check_numeric_fidelity,
    extract_quantitative_tokens,
    inventory_project,
    read_source_texts,
    should_trigger,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
PACK_DIR = REPO_ROOT / "meddraft_ai" / "prompts" / SKILL_NAME
AGENT_DIR = REPO_ROOT / ".agents" / "skills" / SKILL_NAME

CLEAN_DRAFT = """\
## Summary of main findings

In this systematic review and meta-analysis of five randomised trials involving 4200 adults with uncontrolled hypertension, Chlorthalidone-based triple therapy reduced MSSBP week 8 by 8.4 mmHg compared with dual therapy, answering our primary objective. MSDBP week 8 also fell, and BP control rate was higher. Serious adverse events did not differ materially between arms.

## Interpretation

The Week 2 and Week 4 estimates indicate a rapid onset, consistent with the complementary pharmacology of the three classes [1]. These findings align with prior triple-combination trials and extend them to a Chlorthalidone-specific population [2]. Heterogeneity was low to moderate, and the prediction interval remained below the null.

## Certainty of evidence

Moderate certainty evidence suggests that the combination likely reduces systolic pressure. The evidence for serious adverse events was of low certainty.

## Limitations

This review has several limitations. At the study level, follow-up was short, which may limit inference about hard outcomes. We mitigated this by pre-specifying the Week 8 endpoint. At the review level, an English-language restriction may restrict generalisability. Dual screening reduced selection error.

## Implications for practice

Clinicians may reasonably consider this combination for patients uncontrolled on dual therapy, with electrolyte monitoring within four weeks.

## Future research

A multicentre randomised trial in older adults should compare this regimen with an active dual comparator over 12 months and report 24-hour ambulatory pressure.

## Conclusions

On moderate certainty evidence, the combination likely offers a rapid step-up option.
"""

REQUIRED = ["MSSBP week 8", "MSDBP week 8", "BP control rate", "serious adverse events"]


# ---------------------------------------------------------------------------
# Routing
# ---------------------------------------------------------------------------

class TestShouldTrigger:
    @pytest.mark.parametrize(
        "text",
        [
            "Write the Discussion for my systematic review and meta-analysis",
            "Draft a meta-analysis discussion with GRADE certainty",
            "Interpret the pooled effect for this systematic review",
            "Write the discussion section of the systematic review, including strengths and limitations",
        ],
    )
    def test_discussion_tasks(self, text):
        assert should_trigger(text) is True

    @pytest.mark.parametrize(
        "text",
        [
            "",
            "Draft the PRISMA search strategy and screening protocol",
            "Draft the methods section of my systematic review",
            "Draft a systematic review protocol",
            "Extract data from the included RCTs",
            "Write the results section of my randomised trial",
            "Summarize NCT04368728",
            "Write a narrative review on hypertension",
        ],
    )
    def test_non_discussion_tasks(self, text):
        assert should_trigger(text) is False


class TestRegistryWiring:
    def test_pack_registered(self):
        assert SKILL_NAME in REGISTERED_PROMPT_SUBDIRS

    def test_route_keywords_present(self):
        keywords = AUTO_ROUTE_KEYWORDS[SKILL_NAME]
        assert "systematic review discussion" in keywords
        assert "grade certainty" in keywords

    def test_routes_to_skill(self):
        registry = SkillRegistry()
        registry.config = MagicMock()
        registry.prompts_dir = PACK_DIR.parent
        registry.skills = []
        assert registry.match_skill_for_task(
            "Write the discussion section for my systematic review and meta-analysis"
        ) == SKILL_NAME

    def test_existing_routes_unchanged(self):
        registry = SkillRegistry()
        registry.config = MagicMock()
        registry.prompts_dir = PACK_DIR.parent
        registry.skills = []
        assert registry.match_skill_for_task(
            "Trace this nested citation as cited in Smith (2020)"
        ) == "secondary-citation-extractor"
        assert registry.match_skill_for_task("Summarize NCT04368728") == "medical-clinicaltrials"

    def test_agent_skill_and_pack_exist(self):
        assert (PACK_DIR / "SKILL.md").is_file()
        assert (AGENT_DIR / "SKILL.md").is_file()

    @pytest.mark.parametrize(
        "relative",
        [
            "references/evidence-intake.md",
            "references/rci-and-heterogeneity.md",
            "references/grade-certainty.md",
            "references/section-blueprints.md",
            "references/prose-guardrails.md",
            "references/quality-gate.md",
            "assets/master-evidence-table.md",
        ],
    )
    def test_on_demand_references_exist(self, relative):
        assert (PACK_DIR / relative).is_file(), relative

    def test_both_frontmatters_name_the_skill(self):
        for path in (PACK_DIR / "SKILL.md", AGENT_DIR / "SKILL.md"):
            head = path.read_text(encoding="utf-8")[:400]
            assert "name: systematic-review-discussion" in head


class TestSpecialistWiring:
    def test_specialist_class_exists(self):
        from meddraft_ai.agents import SystematicReviewDiscussionSpecialist
        from meddraft_ai.agents import specialists

        assert hasattr(specialists, "SystematicReviewDiscussionSpecialist")
        assert SystematicReviewDiscussionSpecialist is specialists.SystematicReviewDiscussionSpecialist
        source = inspect.getsource(specialists.SystematicReviewDiscussionSpecialist)
        assert "systematic-review-discussion/SKILL.md" in source
        assert "def draft" in source

    def test_verifier_carries_the_gate(self):
        from meddraft_ai.agents import specialists

        source = inspect.getsource(specialists.VerifierAndStatsSpecialist.__init__)
        assert "systematic-review-discussion/SKILL.md" in source

    def test_primary_pack_survives_the_context_budget(self):
        from meddraft_ai.agents.specialists import SystematicReviewDiscussionSpecialist

        specialist = SystematicReviewDiscussionSpecialist()
        context = specialist.load_context("Write the discussion for my systematic review")
        assert "Systematic Review & Meta-Analysis Discussion Architect" in context
        assert "systematic-review-discussion" in context.lower()


# ---------------------------------------------------------------------------
# Auditor
# ---------------------------------------------------------------------------

class TestAuditor:
    def test_clean_draft_passes(self):
        report = audit_discussion(CLEAN_DRAFT, required_outcomes=REQUIRED)
        assert report.passed, [f.to_dict() for f in report.errors]
        assert report.outcomes_missing == []

    def test_em_dash_is_an_error(self):
        report = audit_discussion("The effect was large \u2014 and consistent [1].")
        assert any(f.code == "em_dash" and f.severity == "error" for f in report.findings)

    def test_banned_vocabulary_is_an_error(self):
        report = audit_discussion(
            "In this systematic review we delve into the pooled estimate [1]."
        )
        assert any(f.code == "banned_vocabulary" for f in report.errors)

    def test_background_opening_is_an_error(self):
        report = audit_discussion(
            "Hypertension affects millions of people worldwide. This review examined triple therapy [1]."
        )
        codes = [f.code for f in report.errors]
        assert "background_opening" in codes

    def test_overclaim_is_an_error(self):
        report = audit_discussion("This review proves that triple therapy works in all patients [1].")
        assert any(f.code == "grade_overclaim" for f in report.errors)

    def test_prove_verb_is_allowed_only_under_high_certainty(self):
        overclaim = audit_discussion("This review proves the effect [1].")
        assert any(f.code == "grade_overclaim" for f in overclaim.errors)

        high = audit_discussion(
            "High certainty evidence. The evidence proves the effect [1]."
        )
        assert not any(f.code == "grade_overclaim" for f in high.errors)

    def test_generic_research_call_is_an_error(self):
        report = audit_discussion(
            "More research is needed to confirm these findings [1]."
        )
        assert any(f.code == "generic_future_research" for f in report.errors)

    def test_missing_required_outcome_is_an_error(self):
        report = audit_discussion(CLEAN_DRAFT, required_outcomes=["serum potassium"])
        assert "serum potassium" in report.outcomes_missing
        assert any(f.code == "outcome_omitted" for f in report.errors)
        assert report.passed is False

    def test_aliases_count_as_coverage(self):
        report = audit_discussion(
            CLEAN_DRAFT,
            required_outcomes=[{"label": "systolic pressure", "aliases": ["MSSBP"]}],
        )
        assert report.outcomes_missing == []

    def test_single_tier_limitations_warns(self):
        text = (
            "## Limitations\n\nAt the study level, the included trials were small "
            "and this may limit precision. We used dual screening.\n"
        )
        report = audit_discussion(text)
        assert any(f.code == "limitations_single_tier" for f in report.warnings)

    def test_apologetic_limitation_warns(self):
        report = audit_discussion("Unfortunately our study suffered from small samples.")
        assert any(f.code == "apologetic_limitation" for f in report.warnings)

    def test_uninterpreted_heterogeneity_warns(self):
        text = "The analysis showed I2 of 78% across trials [1]. " * 80
        report = audit_discussion(text)
        assert any(f.code in {"heterogeneity_uninterpreted"} for f in report.warnings)

    def test_markdown_table_dump_warns(self):
        table = "\n".join(f"| row {i} | value |" for i in range(8))
        report = audit_discussion(table)
        assert any(f.code == "data_dump" for f in report.warnings)

    def test_report_serialises(self):
        report = audit_discussion(CLEAN_DRAFT, required_outcomes=REQUIRED)
        payload = report.to_dict()
        assert payload["skill"] == SKILL_NAME
        assert payload["passed"] is True
        assert isinstance(payload["findings"], list)
        assert "PASS" in report.to_markdown()


# ---------------------------------------------------------------------------
# Numeric fidelity
# ---------------------------------------------------------------------------

class TestNumericFidelity:
    def test_tokens_ignore_years_and_small_integers(self):
        tokens = extract_quantitative_tokens("In 2024, 5 trials with 4200 patients showed 8.42 mmHg.")
        assert "2024" not in tokens
        assert "4200" in tokens
        assert "8.42" in tokens
        assert "5" not in tokens

    def test_matched_and_unmatched(self):
        draft = "The estimate was 8.42 mmHg (95% CI 6.73 to 10.11) in 4200 patients."
        report = check_numeric_fidelity(draft, ["MD -8.42, 95% CI -10.11 to -6.73; N=4,200"])
        assert "8.42" in report.matched
        assert "4200" in report.matched
        assert report.passed is True

    def test_invented_value_is_flagged(self):
        report = check_numeric_fidelity(
            "The estimate was 9.99 mmHg.", ["The estimate was 8.42 mmHg."]
        )
        assert [item["value"] for item in report.unmatched] == ["9.99"]
        assert report.passed is False

    def test_percentages_are_compared(self):
        report = check_numeric_fidelity("I2 was 32%.", ["heterogeneity I2 = 32%"])
        assert report.passed is True

    def test_ci_label_is_not_treated_as_an_evidence_value(self):
        tokens = extract_quantitative_tokens("MD -8.42 (95% CI -10.11 to -6.73)")
        assert "95" not in tokens
        report = check_numeric_fidelity(
            "MD -8.42 (95% CI -10.11 to -6.73)", ["MD -8.42 (-10.11, -6.73)"]
        )
        assert report.passed is True

    def test_read_source_texts_skips_binary(self, tmp_path):
        (tmp_path / "pooled.csv").write_text("outcome,md\nMSSBP,-8.42\n", encoding="utf-8")
        (tmp_path / "forest.pdf").write_bytes(b"%PDF-1.4")
        texts = read_source_texts([tmp_path])
        assert any("MSSBP" in text for text in texts)
        assert all("PDF-1.4" not in text for text in texts)

    def test_read_source_texts_can_exclude_the_draft(self, tmp_path):
        draft = tmp_path / "discussion.md"
        draft.write_text("The estimate was 9.99.", encoding="utf-8")
        evidence = tmp_path / "pooled.csv"
        evidence.write_text("MSSBP,-8.42", encoding="utf-8")
        texts = read_source_texts([tmp_path], exclude=[draft])
        assert all("9.99" not in text for text in texts)
        assert any("-8.42" in text for text in texts)


# ---------------------------------------------------------------------------
# Inventory and brief builder
# ---------------------------------------------------------------------------

class TestInventory:
    def test_inventory_classifies_buckets(self, tmp_path):
        for relative in (
            "protocol/eligibility.md",
            "included/a.pdf",
            "meta/forest.png",
            "meta/pooled.csv",
            "old meta/review.md",
        ):
            target = tmp_path / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("x", encoding="utf-8")

        inventory = inventory_project([tmp_path])
        categories = inventory.categories

        assert "included_studies" in categories
        assert "meta_analysis" in categories
        assert "prior_reviews" in categories
        assert "protocol" in categories
        assert len(inventory.files) == 5
        assert "Evidence workspace inventory" in inventory.to_markdown()
        assert inventory.to_dict()["count"] == 5

    def test_root_name_does_not_contaminate_categories(self, tmp_path):
        root = tmp_path / "study_and_meta_root"
        target = root / "protocol" / "eligibility.md"
        target.parent.mkdir(parents=True)
        target.write_text("x", encoding="utf-8")

        inventory = inventory_project([root])
        assert inventory.files[0]["category"] == "protocol"

    def test_missing_path_is_tolerated(self, tmp_path):
        inventory = inventory_project([tmp_path / "does_not_exist"])
        assert inventory.files == []


class TestSystemCommand:
    def test_brief_contains_study_and_guardrails(self, tmp_path):
        (tmp_path / "pooled.csv").write_text("outcome,md\nMSSBP,-8.42\n", encoding="utf-8")
        command = build_system_command(
            {
                "title": "Triple therapy in uncontrolled hypertension",
                "population": "Adults with uncontrolled hypertension",
                "intervention": "Chlorthalidone + amlodipine + ARB",
                "comparator": "Dual therapy",
                "outcomes": ["MSSBP Week 8", "SAEs"],
                "timepoint": "Week 8",
                "workspace": [tmp_path],
                "output": "discussion.md",
                "citation_style": "Vancouver",
            }
        )
        assert "Triple therapy in uncontrolled hypertension" in command
        assert "Chlorthalidone + amlodipine + ARB" in command
        assert "MSSBP Week 8; SAEs" in command
        assert "Evidence workspace inventory" in command
        assert "No em dashes" in command
        assert "NOT_POOLED" in command


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

class TestCli:
    def test_parser_accepts_sr_commands(self):
        audit_args = build_parser().parse_args(
            ["sr", "audit", "draft.md", "--require", "MSSBP week 8", "--json"]
        )
        assert audit_args.command == "sr"
        assert audit_args.sr_command == "audit"
        assert audit_args.require == ["MSSBP week 8"]

        fidelity_args = build_parser().parse_args(
            ["sr", "fidelity", "--draft", "d.md", "--source", "meta"]
        )
        assert fidelity_args.sr_command == "fidelity"
        assert fidelity_args.source == ["meta"]

        inv_args = build_parser().parse_args(["sr", "inventory", "project"])
        assert inv_args.paths == ["project"]

        brief_args = build_parser().parse_args(["sr", "brief", "--spec", "spec.json"])
        assert brief_args.spec == "spec.json"

    def test_audit_exit_codes(self, tmp_path, capsys):
        good = tmp_path / "good.md"
        good.write_text(CLEAN_DRAFT, encoding="utf-8")
        args = build_parser().parse_args(
            ["sr", "audit", str(good), "--require", "MSSBP week 8", "--min-words", "10", "--json"]
        )
        assert _run_sr(args) == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["passed"] is True

        bad = tmp_path / "bad.md"
        bad.write_text("The effect was large \u2014 and we delve into it.", encoding="utf-8")
        args = build_parser().parse_args(["sr", "audit", str(bad), "--json"])
        assert _run_sr(args) == 1

    def test_inventory_command_emits_json(self, tmp_path, capsys):
        (tmp_path / "meta").mkdir()
        (tmp_path / "meta" / "pooled.json").write_text("{}", encoding="utf-8")
        args = build_parser().parse_args(["sr", "inventory", str(tmp_path), "--json"])
        assert _run_sr(args) == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["count"] == 1
        assert "meta_analysis" in payload["categories"]
