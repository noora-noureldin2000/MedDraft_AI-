from __future__ import annotations

import re
from typing import Any, Generic, List, Literal, Optional, TypeVar
from pydantic import BaseModel, Field

T = TypeVar("T")


class GroundedField(BaseModel, Generic[T]):
    """Wraps an extracted data point with strict verbatim source grounding and audit metadata."""
    status: Literal["REPORTED", "NOT_REPORTED", "UNCLEAR"] = Field(
        description="REPORTED if stated in source. NOT_REPORTED if absent. UNCLEAR if contradictory or ambiguous."
    )
    value: Optional[T] = Field(
        default=None,
        description="Structured extracted value. Must be None if status is NOT_REPORTED."
    )
    semantic_interpretation: Optional[str] = Field(
        default=None,
        description="Standardized clinical interpretation (e.g. normalizing dosages or defining population acronyms)."
    )
    verbatim_quote: Optional[str] = Field(
        default=None,
        description="Exact character-for-character substring from the text or table. Never paraphrase or use ellipses."
    )
    page_number: Optional[int] = Field(
        default=None,
        description="1-indexed page number where verbatim_quote or table appears."
    )
    section_header: Optional[str] = Field(
        default=None,
        description="Section header or Table ID where the quote appears."
    )
    verified_in_source: bool = Field(
        default=False,
        description="Populated programmatically by GroundingVerifier post-extraction."
    )
    verification_note: Optional[str] = Field(
        default=None,
        description="Audit diagnostics note populated by GroundingVerifier."
    )


class OutcomeMeasure(BaseModel):
    """Structured clinical outcome with exact numeric string fidelity."""
    outcome_name: str = Field(description="Exact clinical outcome endpoint.")
    timepoint: Optional[str] = Field(default=None, description="Assessment timepoint (e.g., '12 weeks').")
    analysis_population: Optional[str] = Field(default=None, description="e.g. 'ITT', 'mITT', 'Per-Protocol', or sample n.")
    intervention_result: str = Field(description="Exact result for intervention arm (e.g., '45/120 (37.5%)').")
    comparator_result: str = Field(description="Exact result for comparator arm (e.g., '60/120 (50.0%)').")
    effect_size_metric: Optional[str] = Field(default=None, description="e.g., HR, OR, RR, MD, ARD.")
    effect_size_value: Optional[str] = Field(
        default=None,
        description="Exact string representation of effect size to preserve trailing zeros (e.g., '0.70')."
    )
    confidence_interval_95: Optional[str] = Field(default=None, description="Exact 95% CI string (e.g., '0.52 to 0.94').")
    p_value: Optional[str] = Field(default=None, description="Exact p-value string with operator (e.g., 'p = 0.018', 'p < 0.001').")
    source_table_id: Optional[str] = Field(default=None, description="Table ID if extracted from a table (e.g., 'Table_p5_2').")

    @property
    def effect_size_numeric(self) -> Optional[float]:
        """Optional helper parsing float value when available."""
        if not self.effect_size_value:
            return None
        match = re.search(r"[-+]?\d*\.?\d+", self.effect_size_value)
        return float(match.group(0)) if match else None


class MethodsPassSchema(BaseModel):
    """Schema for Abstract and Methods extraction pass."""
    study_design: GroundedField[str]
    registration_id: GroundedField[str]
    population_description: GroundedField[str]
    inclusion_criteria: GroundedField[List[str]]
    exclusion_criteria: GroundedField[List[str]]
    sample_size_enrolled: GroundedField[int]
    intervention_details: GroundedField[str]
    comparator_details: GroundedField[str]
    follow_up_duration: GroundedField[str]


class ResultsPassSchema(BaseModel):
    """Schema for Results and Tables extraction pass."""
    sample_size_analyzed: GroundedField[int]
    baseline_characteristics_summary: GroundedField[str]
    primary_outcomes: List[GroundedField[OutcomeMeasure]]
    secondary_outcomes: List[GroundedField[OutcomeMeasure]]
    adverse_events_summary: GroundedField[str]
    discontinuations_attrition: GroundedField[str]


class DiscussionPassSchema(BaseModel):
    """Schema for Discussion and Limitations extraction pass."""
    author_conclusions: GroundedField[str]
    study_limitations: GroundedField[List[str]]
    funding_and_conflicts: GroundedField[str]


class CrossSectionAudit(BaseModel):
    """Internal semantic consistency check across Methods, Results, and Tables."""
    sample_size_consistent: bool = Field(
        description="True if enrolled N in Methods aligns with analyzed N and Table denominators."
    )
    discrepancy_notes: Optional[str] = Field(
        default=None,
        description="Detailed explanation of any denominator shifts, attrition discrepancies, or outcome switching."
    )
    overall_risk_of_reporting_bias: Literal["LOW", "MODERATE", "HIGH", "UNCLEAR"]


class StudyExtractionSchema(BaseModel):
    """Master auditable output schema for a clinical study."""
    study_id: str
    metadata_doi: Optional[str] = None
    metadata_pmid: Optional[str] = None
    methods: MethodsPassSchema
    results: ResultsPassSchema
    discussion: DiscussionPassSchema
    semantic_audit: CrossSectionAudit
