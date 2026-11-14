"""
Tests for Figure Extraction Pipeline (Phase D).
"""

from typing import Dict, List
import pytest
from pydantic import BaseModel

from meddraft_ai.extraction.grounding_verifier import GroundingVerifier
from meddraft_ai.extraction.schemas import (
    FigurePassSchema,
    FigurePoint,
    MethodsPassSchema,
    ResultsPassSchema,
    DiscussionPassSchema,
    CrossSectionAudit,
    GroundedField,
)
from meddraft_ai.extraction.study_extractor import StudyExtractor


def test_no_figures_skips_pass_without_error():
    """When chunks have no figures, Pass 2b is skipped and extraction succeeds."""
    verifier = GroundingVerifier(page_texts={1: "Short text."})

    def mock_llm(sys_p, usr_p, schema_cls):
        if schema_cls == MethodsPassSchema:
            return MethodsPassSchema(
                study_design=GroundedField[str](status="NOT_REPORTED", value=None),
                registration_id=GroundedField[str](status="NOT_REPORTED", value=None),
                population_description=GroundedField[str](status="NOT_REPORTED", value=None),
                inclusion_criteria=GroundedField[List[str]](status="NOT_REPORTED", value=None),
                exclusion_criteria=GroundedField[List[str]](status="NOT_REPORTED", value=None),
                sample_size_enrolled=GroundedField[int](status="NOT_REPORTED", value=None),
                intervention_details=GroundedField[str](status="NOT_REPORTED", value=None),
                comparator_details=GroundedField[str](status="NOT_REPORTED", value=None),
                follow_up_duration=GroundedField[str](status="NOT_REPORTED", value=None),
            )
        elif schema_cls == ResultsPassSchema:
            return ResultsPassSchema(
                sample_size_analyzed=GroundedField[int](status="NOT_REPORTED", value=None),
                baseline_characteristics_summary=GroundedField[str](status="NOT_REPORTED", value=None),
                primary_outcomes=[],
                secondary_outcomes=[],
                adverse_events_summary=GroundedField[str](status="NOT_REPORTED", value=None),
                discontinuations_attrition=GroundedField[str](status="NOT_REPORTED", value=None),
            )
        elif schema_cls == DiscussionPassSchema:
            return DiscussionPassSchema(
                author_conclusions=GroundedField[str](status="NOT_REPORTED", value=None),
                study_limitations=GroundedField[List[str]](status="NOT_REPORTED", value=None),
                funding_and_conflicts=GroundedField[str](status="NOT_REPORTED", value=None),
            )
        elif schema_cls == CrossSectionAudit:
            return CrossSectionAudit(
                sample_size_consistent=True,
                discrepancy_evidence=GroundedField[str](status="NOT_REPORTED", value=None),
                overall_risk_of_reporting_bias="LOW",
            )
        raise ValueError(f"Unexpected schema: {schema_cls}")

    extractor = StudyExtractor(llm_structured_callable=mock_llm, verifier=verifier)
    chunks = {
        "abstract_intro": [{"page": 1, "section": "abstract_intro", "text": "Sample text"}],
        "methods": [],
        "results": [],
        "discussion": [],
        "tables": [],
        "figures": [],
    }
    res = extractor.extract_all(study_id="study_no_figs", semantic_chunks=chunks)
    assert res.study_id == "study_no_figs"
    assert res.figures == []


def test_figure_extraction_pass_executed():
    """When figures are present, Pass 2b runs and populates study_data.figures."""
    verifier = GroundingVerifier(page_texts={1: "Short text."})
    called_schemas = []

    def mock_llm(sys_p, usr_p, schema_cls):
        called_schemas.append(schema_cls)
        if schema_cls == FigurePassSchema:
            return FigurePassSchema(
                figure_id="Figure_p2_1",
                figure_type="forest_plot",
                extracted_points=[
                    FigurePoint(label="Subgroup A", estimate="0.65", confidence_interval="0.45-0.92")
                ],
                pooled_estimate="0.65",
                confidence_interval="0.45-0.92",
                ocr_agreement="FULL",
            )
        elif schema_cls == MethodsPassSchema:
            return MethodsPassSchema(
                study_design=GroundedField[str](status="NOT_REPORTED", value=None),
                registration_id=GroundedField[str](status="NOT_REPORTED", value=None),
                population_description=GroundedField[str](status="NOT_REPORTED", value=None),
                inclusion_criteria=GroundedField[List[str]](status="NOT_REPORTED", value=None),
                exclusion_criteria=GroundedField[List[str]](status="NOT_REPORTED", value=None),
                sample_size_enrolled=GroundedField[int](status="NOT_REPORTED", value=None),
                intervention_details=GroundedField[str](status="NOT_REPORTED", value=None),
                comparator_details=GroundedField[str](status="NOT_REPORTED", value=None),
                follow_up_duration=GroundedField[str](status="NOT_REPORTED", value=None),
            )
        elif schema_cls == ResultsPassSchema:
            return ResultsPassSchema(
                sample_size_analyzed=GroundedField[int](status="NOT_REPORTED", value=None),
                baseline_characteristics_summary=GroundedField[str](status="NOT_REPORTED", value=None),
                primary_outcomes=[],
                secondary_outcomes=[],
                adverse_events_summary=GroundedField[str](status="NOT_REPORTED", value=None),
                discontinuations_attrition=GroundedField[str](status="NOT_REPORTED", value=None),
            )
        elif schema_cls == DiscussionPassSchema:
            return DiscussionPassSchema(
                author_conclusions=GroundedField[str](status="NOT_REPORTED", value=None),
                study_limitations=GroundedField[List[str]](status="NOT_REPORTED", value=None),
                funding_and_conflicts=GroundedField[str](status="NOT_REPORTED", value=None),
            )
        elif schema_cls == CrossSectionAudit:
            return CrossSectionAudit(
                sample_size_consistent=True,
                discrepancy_evidence=GroundedField[str](status="NOT_REPORTED", value=None),
                overall_risk_of_reporting_bias="LOW",
            )
        raise ValueError(f"Unexpected schema: {schema_cls}")

    extractor = StudyExtractor(llm_structured_callable=mock_llm, verifier=verifier)
    chunks = {
        "abstract_intro": [{"page": 1, "section": "abstract_intro", "text": "Sample text"}],
        "methods": [],
        "results": [],
        "discussion": [],
        "tables": [],
        "figures": [{
            "figure_id": "Figure_p2_1",
            "page": 2,
            "caption": "Figure 1: Forest plot of primary efficacy",
            "ocr_text": "Subgroup A 0.65 [0.45, 0.92]",
        }],
    }
    res = extractor.extract_all(study_id="study_with_figs", semantic_chunks=chunks)
    assert FigurePassSchema in called_schemas
    assert len(res.figures) == 1
    assert res.figures[0].figure_type == "forest_plot"
    assert res.figures[0].extracted_points[0].estimate == "0.65"
