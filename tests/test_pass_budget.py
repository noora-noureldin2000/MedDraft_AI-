"""
Tests for Budgeted Map-Reduce Extraction and Unit Packing (Phase E).
"""

import pytest
from pydantic import BaseModel

from meddraft_ai.extraction.evidence import EvidenceIndex, PageEvidence, TableEvidence
from meddraft_ai.extraction.grounding_verifier import GroundingVerifier
from meddraft_ai.extraction.schemas import GroundedField, OutcomeMeasure, ResultsPassSchema
from meddraft_ai.extraction.study_extractor import StudyExtractor


def test_estimate_tokens():
    """Conservative token estimation (chars / 3.5)."""
    text = "A" * 350
    assert StudyExtractor._estimate_tokens(text) == 100
    assert StudyExtractor._estimate_tokens("") == 0


def test_pack_units_under_budget():
    """When total characters are under budget, a single context is returned."""
    units = ["Unit 1 text", "Unit 2 text", "Unit 3 text"]
    packed = StudyExtractor._pack_units(units, budget=1000)
    assert len(packed) == 1
    assert "Unit 1 text" in packed[0]
    assert "Unit 3 text" in packed[0]


def test_pack_units_exceeding_budget_splits_with_overlap():
    """When content exceeds budget, units are packed into multiple sub-contexts with whole-unit overlap."""
    # Create units where each unit is ~50 chars (~14 tokens)
    units = [f"Unit {i} contains structured data block number {i}." for i in range(1, 21)]
    # Set a tiny budget of ~50 tokens (~175 chars)
    packed = StudyExtractor._pack_units(units, budget=50, overlap_units=2)
    assert len(packed) > 1

    # Verify no sub-context cut an atomic unit in half
    for ctx in packed:
        assert ctx.startswith("Unit ")
        assert ctx.endswith(".")

    # Verify overlap: consecutive contexts share whole units
    for idx in range(len(packed) - 1):
        first_lines = set(packed[idx].split("\n\n"))
        second_lines = set(packed[idx + 1].split("\n\n"))
        overlap = first_lines & second_lines
        assert len(overlap) >= 1, "Consecutive sub-contexts must share overlapping units"


def test_merge_models_deduplicates_outcomes_and_detects_conflict():
    """Merging sub-pass models must deduplicate outcomes and flag contradictory values."""
    verifier = GroundingVerifier(page_texts={1: "dummy"})
    extractor = StudyExtractor(llm_structured_callable=lambda s, u, c: None, verifier=verifier)

    om1 = OutcomeMeasure(
        outcome_name="Overall Survival",
        intervention_result="45/100 (45.0%)",
        comparator_result="60/100 (60.0%)",
        effect_size_value="0.70",
    )
    om2 = OutcomeMeasure(
        outcome_name="Overall Survival",
        intervention_result="55/100 (55.0%)",  # Contradicts om1!
        comparator_result="60/100 (60.0%)",
        effect_size_value="0.70",
    )

    m1 = ResultsPassSchema(
        sample_size_analyzed=GroundedField[int](status="REPORTED", value=100, verified_in_source=True),
        baseline_characteristics_summary=GroundedField[str](status="NOT_REPORTED", value=None),
        primary_outcomes=[
            GroundedField[OutcomeMeasure](status="REPORTED", value=om1, verified_in_source=True)
        ],
        secondary_outcomes=[],
        adverse_events_summary=GroundedField[str](status="NOT_REPORTED", value=None),
        discontinuations_attrition=GroundedField[str](status="NOT_REPORTED", value=None),
    )
    m2 = ResultsPassSchema(
        sample_size_analyzed=GroundedField[int](status="REPORTED", value=100, verified_in_source=True),
        baseline_characteristics_summary=GroundedField[str](status="NOT_REPORTED", value=None),
        primary_outcomes=[
            GroundedField[OutcomeMeasure](status="REPORTED", value=om2, verified_in_source=True)
        ],
        secondary_outcomes=[],
        adverse_events_summary=GroundedField[str](status="NOT_REPORTED", value=None),
        discontinuations_attrition=GroundedField[str](status="NOT_REPORTED", value=None),
    )

    merged = extractor._merge_models([m1, m2], ResultsPassSchema)
    # The duplicate outcome should be deduped to 1
    assert len(merged.primary_outcomes) == 1
    # The contradiction should be recorded in extraction_warnings
    assert len(extractor.extraction_warnings) == 1
    assert "Conflict in outcome 'Overall Survival'" in extractor.extraction_warnings[0]


def test_table_deduplication_in_context():
    """Tables appearing multiple times are deduplicated in formatted context."""
    extractor = StudyExtractor(llm_structured_callable=lambda s, u, c: None, verifier=None)
    tables = [
        {"table_id": "Table_p1_1", "page": 1, "caption": "Table 1", "markdown": "| A | B |", "records": []},
        {"table_id": "Table_p1_1", "page": 1, "caption": "Table 1 Duplicate", "markdown": "| A | B |", "records": []},
    ]
    ctx = extractor.format_source_context(chunks=[], tables=tables)
    assert ctx.count("TABLE ID: Table_p1_1") == 1
