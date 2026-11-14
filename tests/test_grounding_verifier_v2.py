"""
Tests for GroundingVerifier v2 (Phase B) — EvidenceIndex-aware verification.

These tests validate the new EvidenceIndex constructor path while proving
that the legacy page_texts/tables_json path remains unchanged.
"""

from typing import Dict, List

import pytest

from meddraft_ai.extraction.evidence import (
    EvidenceIndex,
    PageEvidence,
    TableEvidence,
    FigureEvidence,
)
from meddraft_ai.extraction.grounding_verifier import GroundingVerifier
from meddraft_ai.extraction.schemas import GroundedField, OutcomeMeasure


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def evidence_index() -> EvidenceIndex:
    """Build an EvidenceIndex with Docling text that differs from pdfplumber."""
    return EvidenceIndex(
        pages={
            1: PageEvidence(
                page=1,
                text="Title: A Randomized Trial of Drug X. Abstract: We enrolled 240 patients with severe asthma.",
                engine="docling",
                char_count=90,
            ),
            2: PageEvidence(
                page=2,
                text="Methods: Eligible patients were randomized 1:1 to receive oral Drug X 50 mg twice daily or placebo for 24 weeks.",
                engine="docling",
                char_count=113,
            ),
            3: PageEvidence(
                page=3,
                text="Results: Primary endpoint occurred in 25/120 (20.8%) patients in the Drug X group vs 48/120 (40.0%) in placebo (HR 0.52, 95% CI 0.32-0.84, p = 0.007).",
                engine="docling",
                char_count=155,
            ),
        },
        tables=[
            TableEvidence(
                table_id="Table_p3_1",
                page=3,
                caption="Table 1. Primary outcomes",
                markdown="| Outcome | Drug X | Placebo |\n|---|---|---|\n| Events | 25/120 | 48/120 |",
                records=[{"Outcome": "Events", "Drug X": "25/120", "Placebo": "48/120"}],
                source="docling",
            ),
        ],
        docling_markdown="Full document markdown...",
    )


@pytest.fixture
def sample_pages() -> Dict[int, str]:
    """Legacy page_texts fixture (same as existing tests)."""
    return {
        1: "Title: A Randomized Trial of Drug X. Abstract: We enrolled 240 patients with severe asthma.",
        2: "Methods: Eligible patients were randomized 1:1 to receive oral Drug X 50 mg twice daily or placebo for 24 weeks.",
        3: "Results: Primary endpoint occurred in 25/120 (20.8%) patients in the Drug X group vs 48/120 (40.0%) in placebo (HR 0.52, 95% CI 0.32-0.84, p = 0.007).",
        4: "Discussion: In this multicenter trial, Drug X significantly reduced exacerbations.",
    }


# ---------------------------------------------------------------------------
# 1. Legacy constructor path unchanged
# ---------------------------------------------------------------------------

def test_legacy_constructor_still_works(sample_pages):
    """The original page_texts+tables_json constructor must remain functional."""
    verifier = GroundingVerifier(page_texts=sample_pages)
    field = GroundedField[int](
        status="REPORTED",
        value=240,
        verbatim_quote="We enrolled 240 patients with severe asthma.",
        page_number=1,
    )
    ok, err = verifier.verify_field("sample_size", field)
    assert ok is True


# ---------------------------------------------------------------------------
# 2. EvidenceIndex constructor accepts and verifies quotes
# ---------------------------------------------------------------------------

def test_evidence_index_constructor_accepts_quote(evidence_index):
    """When evidence= is supplied, the verifier uses its page corpus."""
    verifier = GroundingVerifier(page_texts={}, evidence=evidence_index)
    field = GroundedField[int](
        status="REPORTED",
        value=240,
        verbatim_quote="We enrolled 240 patients with severe asthma.",
        page_number=1,
    )
    ok, err = verifier.verify_field("sample_size", field)
    assert ok is True
    assert field.grounding_source == "docling"


# ---------------------------------------------------------------------------
# 3. Quote in Tesseract text accepted with correct source attribution
# ---------------------------------------------------------------------------

def test_tesseract_text_accepted_with_source():
    """A quote present only in Tesseract OCR text should be accepted."""
    evidence = EvidenceIndex(
        pages={
            1: PageEvidence(
                page=1,
                text="",
                engine="pdfplumber",
                char_count=0,
            ),
        },
    )
    # Add a secondary Tesseract rendering
    evidence.pages[1] = PageEvidence(
        page=1,
        text="OCR recovered text: We enrolled 240 patients with severe asthma.",
        engine="tesseract",
        char_count=65,
        needs_ocr=True,
        ocr_applied=True,
    )

    verifier = GroundingVerifier(page_texts={}, evidence=evidence)
    field = GroundedField[int](
        status="REPORTED",
        value=240,
        verbatim_quote="We enrolled 240 patients with severe asthma.",
        page_number=1,
    )
    ok, err = verifier.verify_field("sample_size", field)
    assert ok is True
    assert field.grounding_source == "tesseract"


# ---------------------------------------------------------------------------
# 4. Docling text accepted even when pdfplumber has nothing
# ---------------------------------------------------------------------------

def test_docling_text_accepted_when_pdfplumber_empty():
    """Regression test: quote in Docling text must not be rejected because
    pdfplumber returned empty for that page (root cause of accuracy leak #1).
    """
    evidence = EvidenceIndex(
        pages={
            2: PageEvidence(
                page=2,
                text="Methods: Eligible patients were randomized 1:1 to receive oral Drug X 50 mg twice daily.",
                engine="docling",
                char_count=90,
            ),
        },
    )
    # Legacy page_texts is empty for page 2 (simulating the bug)
    verifier = GroundingVerifier(page_texts={2: ""}, evidence=evidence)
    field = GroundedField[str](
        status="REPORTED",
        value="RCT",
        verbatim_quote="randomized 1:1 to receive oral Drug X",
        page_number=2,
    )
    ok, err = verifier.verify_field("study_design", field)
    assert ok is True


# ---------------------------------------------------------------------------
# 5. Fabricated number still rejected (union must not increase permissiveness)
# ---------------------------------------------------------------------------

def test_fabricated_number_still_rejected(evidence_index):
    """Union corpus must not widen numeric check. A fabricated 999 must fail."""
    verifier = GroundingVerifier(page_texts={}, evidence=evidence_index)
    outcome = OutcomeMeasure(
        outcome_name="Exacerbation",
        intervention_result="999/120",
        comparator_result="48/120",
        effect_size_metric="HR",
        effect_size_value="0.52",
        confidence_interval_95="0.32-0.84",
        p_value="p = 0.007",
    )
    field = GroundedField[OutcomeMeasure](
        status="REPORTED",
        value=outcome,
        verbatim_quote="Primary endpoint occurred in 25/120 (20.8%) patients in the Drug X group",
        page_number=3,
    )
    ok, err = verifier.verify_field("primary_outcome", field)
    assert ok is False
    assert "999" in err


# ---------------------------------------------------------------------------
# 6. Table-only quote accepted via records
# ---------------------------------------------------------------------------

def test_table_records_accepted(evidence_index):
    """A quote matching table records should be accepted."""
    verifier = GroundingVerifier(page_texts={}, evidence=evidence_index)
    field = GroundedField[str](
        status="REPORTED",
        value="25/120",
        verbatim_quote="25/120",
        page_number=3,
        section_header="Table_p3_1",
    )
    ok, err = verifier.verify_field("events_intervention", field)
    assert ok is True


# ---------------------------------------------------------------------------
# 7. EvidenceIndex coverage summary
# ---------------------------------------------------------------------------

def test_evidence_index_coverage(evidence_index):
    """Coverage summary must report correct totals."""
    cov = evidence_index.coverage()
    assert cov["pages_total"] == 3
    assert cov["pages_with_text"] == 3
    assert cov["pages_empty"] == []
    assert cov["tables_found"] == 1
    assert cov["tables_with_records"] == 1


# ---------------------------------------------------------------------------
# 8. Match score recorded on GroundedField
# ---------------------------------------------------------------------------

def test_match_score_recorded(evidence_index):
    """The verifier must record grounding_source and match_score on successful verification."""
    verifier = GroundingVerifier(page_texts={}, evidence=evidence_index)
    field = GroundedField[int](
        status="REPORTED",
        value=240,
        verbatim_quote="We enrolled 240 patients with severe asthma.",
        page_number=1,
    )
    ok, _ = verifier.verify_field("sample_size", field)
    assert ok is True
    assert field.match_score is not None
    assert field.match_score >= 95.0
