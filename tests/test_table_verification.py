"""
Tests for Table Hardening (Phase C) — row-level verification and sanity bounds.

Guarantees:
- Value in correct row accepted.
- Value in wrong row rejected (page-level co-occurrence is not enough).
- Invented table_id rejected.
- Sanity check: events > total rejected.
- Sanity check: reversed CI (lower > upper) rejected.
- pdfplumber fallback table produces TableEvidence shape.
"""

import pytest

from meddraft_ai.extraction.evidence import EvidenceIndex, PageEvidence, TableEvidence
from meddraft_ai.extraction.grounding_verifier import GroundingVerifier
from meddraft_ai.extraction.schemas import GroundedField, OutcomeMeasure


@pytest.fixture
def table_evidence_index() -> EvidenceIndex:
    """Fixture containing a structured table with distinct rows."""
    return EvidenceIndex(
        pages={
            3: PageEvidence(
                page=3,
                text="Results: Primary endpoint and adverse events are shown in Table 1.",
                engine="docling",
                char_count=67,
            )
        },
        tables=[
            TableEvidence(
                table_id="Table_p3_1",
                page=3,
                caption="Table 1. Efficacy and Safety Outcomes",
                markdown=(
                    "| Outcome | Drug X (N=120) | Placebo (N=120) | HR (95% CI) |\n"
                    "|---|---|---|---|\n"
                    "| Primary Endpoint | 25/120 (20.8%) | 48/120 (40.0%) | 0.52 (0.32-0.84) |\n"
                    "| Severe Headache | 12/120 (10.0%) | 10/120 (8.3%) | 1.20 (0.50-2.88) |\n"
                ),
                records=[
                    {
                        "Outcome": "Primary Endpoint",
                        "Drug X (N=120)": "25/120 (20.8%)",
                        "Placebo (N=120)": "48/120 (40.0%)",
                        "HR (95% CI)": "0.52 (0.32-0.84)",
                    },
                    {
                        "Outcome": "Severe Headache",
                        "Drug X (N=120)": "12/120 (10.0%)",
                        "Placebo (N=120)": "10/120 (8.3%)",
                        "HR (95% CI)": "1.20 (0.50-2.88)",
                    },
                ],
                source="docling",
            )
        ],
        docling_markdown="Full document markdown with Table 1...",
    )


def test_table_correct_row_accepted(table_evidence_index):
    """Numbers matching the correct row are accepted."""
    verifier = GroundingVerifier(page_texts={}, evidence=table_evidence_index)
    outcome = OutcomeMeasure(
        outcome_name="Primary Endpoint",
        intervention_result="25/120 (20.8%)",
        comparator_result="48/120 (40.0%)",
        effect_size_metric="HR",
        effect_size_value="0.52",
        confidence_interval_95="0.32-0.84",
        source_table_id="Table_p3_1",
    )
    field = GroundedField[OutcomeMeasure](
        status="REPORTED",
        value=outcome,
        verbatim_quote="25/120 (20.8%)",
        page_number=3,
        section_header="Table_p3_1",
    )
    ok, err = verifier.verify_field("primary_outcome", field)
    assert ok is True
    assert err is None


def test_table_wrong_row_rejected(table_evidence_index):
    """Value with numbers from a different row must fail row-level verification."""
    verifier = GroundingVerifier(page_texts={}, evidence=table_evidence_index)
    # 12/120 is in the 'Severe Headache' row, NOT 'Primary Endpoint'
    outcome = OutcomeMeasure(
        outcome_name="Primary Endpoint",
        intervention_result="12/120 (10.0%)",
        comparator_result="48/120 (40.0%)",
        source_table_id="Table_p3_1",
    )
    field = GroundedField[OutcomeMeasure](
        status="REPORTED",
        value=outcome,
        verbatim_quote="12/120 (10.0%)",
        page_number=3,
        section_header="Table_p3_1",
    )
    ok, err = verifier.verify_field("primary_outcome", field)
    assert ok is False
    assert "not found in row" in err


def test_table_hallucinated_id_rejected(table_evidence_index):
    """An invented table_id must fail verification immediately."""
    verifier = GroundingVerifier(page_texts={}, evidence=table_evidence_index)
    outcome = OutcomeMeasure(
        outcome_name="Primary Endpoint",
        intervention_result="25/120",
        comparator_result="48/120",
        source_table_id="Table_p99_NonExistent",
    )
    field = GroundedField[OutcomeMeasure](
        status="REPORTED",
        value=outcome,
        verbatim_quote="25/120",
        page_number=3,
    )
    ok, err = verifier.verify_field("primary_outcome", field)
    assert ok is False
    assert "not found in extracted tables" in err


def test_events_greater_than_total_flagged(table_evidence_index):
    """events > total in outcome string must be flagged as sanity failure."""
    verifier = GroundingVerifier(page_texts={}, evidence=table_evidence_index)
    outcome = OutcomeMeasure(
        outcome_name="Primary Endpoint",
        intervention_result="150/120",  # Impossible: 150 > 120
        comparator_result="48/120",
        source_table_id="Table_p3_1",
    )
    field = GroundedField[OutcomeMeasure](
        status="REPORTED",
        value=outcome,
        verbatim_quote="150/120",
        page_number=3,
        section_header="Table_p3_1",
    )
    ok, err = verifier.verify_field("primary_outcome", field)
    assert ok is False
    assert "events (150) > total (120)" in err


def test_reversed_ci_flagged(table_evidence_index):
    """Reversed confidence interval (lower > upper) must be flagged as sanity failure."""
    verifier = GroundingVerifier(page_texts={}, evidence=table_evidence_index)
    outcome = OutcomeMeasure(
        outcome_name="Primary Endpoint",
        intervention_result="25/120",
        comparator_result="48/120",
        effect_size_metric="HR",
        effect_size_value="0.52",
        confidence_interval_95="0.84 to 0.32",  # Reversed!
        source_table_id="Table_p3_1",
    )
    field = GroundedField[OutcomeMeasure](
        status="REPORTED",
        value=outcome,
        verbatim_quote="25/120",
        page_number=3,
        section_header="Table_p3_1",
    )
    ok, err = verifier.verify_field("primary_outcome", field)
    assert ok is False
    assert "CI lower bound (0.84) > upper bound (0.32)" in err


def test_pdfplumber_fallback_table_evidence_shape(tmp_path):
    """pdfplumber fallback table produces the standard TableEvidence format."""
    from meddraft_ai.extraction.converter import DocumentConverter

    # Mock converter without calling docling
    converter = DocumentConverter.__new__(DocumentConverter)
    converter.pdf_path = tmp_path / "dummy.pdf"

    # Simulate pdfplumber extracting a table
    class MockPage:
        def extract_tables(self):
            return [
                [["Group", "N", "Rate"], ["Treatment", "50", "20%"], ["Control", "50", "40%"]]
            ]

    class MockPDF:
        def __init__(self):
            self.pages = [MockPage()]
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass

    import pdfplumber
    original_open = pdfplumber.open
    try:
        pdfplumber.open = lambda p: MockPDF()
        tables = converter._extract_tables_pdfplumber()
        assert len(tables) == 1
        tbl = tables[0]
        assert tbl["table_id"] == "Table_p1_1"
        assert tbl["page"] == 1
        assert tbl["source"] == "pdfplumber"
        assert len(tbl["records"]) == 2
        assert tbl["records"][0]["Group"] == "Treatment"
        assert tbl["records"][0]["Rate"] == "20%"
        assert "| Group | N | Rate |" in tbl["markdown"]
    finally:
        pdfplumber.open = original_open
