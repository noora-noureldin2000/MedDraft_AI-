"""
Tests for Coverage Manifest and Routing Fallbacks (Phase E).
"""

from meddraft_ai.extraction.coverage import CoverageAuditor, CoverageManifest
from meddraft_ai.extraction.evidence import EvidenceIndex, PageEvidence, TableEvidence
from meddraft_ai.extraction.schemas import GroundedField, MethodsPassSchema, ResultsPassSchema, StudyExtractionSchema, DiscussionPassSchema, CrossSectionAudit
from meddraft_ai.extraction.semantic_chunker import SemanticDocumentChunker


def test_coverage_auditor_reports_metrics():
    """CoverageAuditor builds complete diagnostic summary."""
    evidence = EvidenceIndex(
        pages={
            1: PageEvidence(page=1, text="Methods text...", engine="pymupdf", char_count=100),
            2: PageEvidence(page=2, text="OCR recovered text", engine="tesseract", char_count=50, ocr_applied=True),
            3: PageEvidence(page=3, text="", engine="pymupdf", char_count=0),
        },
        tables=[
            TableEvidence(table_id="Table_p1_1", page=1, caption="Table 1", markdown="| a |", records=[{"a": 1}]),
        ],
    )
    chunks = {
        "methods": [{"page": 1, "text": "Methods text..."}],
        "results": [],
        "discussion": [],
        "tables": [{"table_id": "Table_p1_1", "page": 1, "records": [{"a": 1}], "caption": "Table 1"}],
    }

    schema = StudyExtractionSchema(
        study_id="study_test",
        methods=MethodsPassSchema(
            study_design=GroundedField[str](status="REPORTED", value="RCT", verified_in_source=True),
            registration_id=GroundedField[str](status="NOT_REPORTED", value=None),
            population_description=GroundedField[str](status="NOT_REPORTED", value=None),
            inclusion_criteria=GroundedField[list](status="NOT_REPORTED", value=None),
            exclusion_criteria=GroundedField[list](status="NOT_REPORTED", value=None),
            sample_size_enrolled=GroundedField[int](status="NOT_REPORTED", value=None),
            intervention_details=GroundedField[str](status="NOT_REPORTED", value=None),
            comparator_details=GroundedField[str](status="NOT_REPORTED", value=None),
            follow_up_duration=GroundedField[str](status="NOT_REPORTED", value=None),
        ),
        results=ResultsPassSchema(
            sample_size_analyzed=GroundedField[int](status="NOT_REPORTED", value=None),
            baseline_characteristics_summary=GroundedField[str](status="NOT_REPORTED", value=None),
            primary_outcomes=[],
            secondary_outcomes=[],
            adverse_events_summary=GroundedField[str](status="NOT_REPORTED", value=None),
            discontinuations_attrition=GroundedField[str](status="NOT_REPORTED", value=None),
        ),
        discussion=DiscussionPassSchema(
            author_conclusions=GroundedField[str](status="NOT_REPORTED", value=None),
            study_limitations=GroundedField[list](status="NOT_REPORTED", value=None),
            funding_and_conflicts=GroundedField[str](status="NOT_REPORTED", value=None),
        ),
        semantic_audit=CrossSectionAudit(
            sample_size_consistent=True,
            discrepancy_evidence=GroundedField[str](status="NOT_REPORTED", value=None),
            overall_risk_of_reporting_bias="LOW",
        ),
    )

    manifest = CoverageAuditor.audit(
        evidence_index=evidence,
        semantic_chunks=chunks,
        study_schema=schema,
        pass_budgets={"methods": 200, "results": 0},
    )

    data = manifest.to_dict()
    assert data["pages_total"] == 3
    assert data["pages_with_text"] == 2
    assert data["pages_ocr"] == [2]
    assert data["pages_empty"] == [3]
    assert data["tables"]["found"] == 1
    assert data["verification"]["reported"] == 1
    assert data["verification"]["not_reported"] >= 1


def test_coverage_auditor_warns_on_budget_exceeded():
    """Manifest logs warning when any pass exceeds the configured budget."""
    manifest = CoverageAuditor.audit(
        evidence_index=None,
        semantic_chunks={"methods": []},
        pass_budgets={"PASS_2_RESULTS": 50000},
        budget_limit=45000,
    )
    assert any("exceeded budget limit" in w for w in manifest.warnings)


def test_header_fallback_routes_unlabeled_header():
    """Unlabeled header line without markdown hashes is matched by header fallback."""
    chunker = SemanticDocumentChunker()
    # A standalone unlabelled "RESULTS" line in a Docling document
    class MockItem:
        label = "text"  # Mislabelled by Docling as normal text!
        text = "RESULTS"
        prov = [type("Prov", (), {"page_no": 5})()]

    class MockDoc:
        def iterate_items(self):
            return [(MockItem(), 0)]

    chunks = chunker.chunk_docling_document(MockDoc())
    assert chunker.header_fallbacks >= 1
    # Items after the header go into results
    assert "results" in chunks
