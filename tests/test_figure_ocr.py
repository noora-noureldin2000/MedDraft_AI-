"""
Tests for Figure OCR and Consensus Scoring (Phase D).
"""

from pathlib import Path
import pytest
from PIL import Image

from meddraft_ai.extraction.evidence import FigureEvidence
from meddraft_ai.extraction.schemas import FigurePassSchema, FigurePoint
from meddraft_ai.ingestion.figure_ocr import FigureOCR, select_consensus_candidate


def test_consensus_scorer_prefers_consensus_over_longest_junk():
    """Consensus scorer must reject long noisy junk in favor of high-overlap text."""
    # PSM 3 gives noisy repetitive punctuation garbage that is very long
    junk_candidate = ".................................................................------------------^^^^^^^^"
    # PSM 6 gives clean text that agrees with PSM 11
    cand_1 = "Study A: HR 0.65 (95% CI 0.45-0.92) Weight 24.5%"
    cand_2 = "Study A: HR 0.65 (0.45 to 0.92) Weight 24.5%"

    selected = select_consensus_candidate([junk_candidate, cand_1, cand_2])
    # The consensus scorer must select cand_1 or cand_2, NEVER the junk
    assert selected in (cand_1, cand_2)
    assert selected != junk_candidate


def test_consensus_scorer_handles_empty_or_single():
    assert select_consensus_candidate([]) == ""
    assert select_consensus_candidate(["Single candidate"]) == "Single candidate"
    assert select_consensus_candidate(["", "  "]) == ""


def test_figure_preprocessing_graceful_degradation(tmp_path):
    """Preprocessing non-existent or corrupted image degrades gracefully without raising."""
    ocr = FigureOCR()
    # Non-existent file
    res = ocr.preprocess_image(tmp_path / "does_not_exist.png")
    assert res is None


def test_figure_preprocessing_success(tmp_path):
    """Preprocessing a real image upscales and enhances."""
    img_path = tmp_path / "sample_plot.png"
    # Create simple test image
    img = Image.new("RGB", (100, 50), color="white")
    img.save(img_path)

    ocr = FigureOCR()
    enhanced = ocr.preprocess_image(img_path)
    assert enhanced is not None
    # 2x upscale
    assert enhanced.size == (200, 100)
    assert enhanced.mode == "L"


def test_figure_schema_serialization():
    """FigurePassSchema validates and serializes correctly."""
    schema = FigurePassSchema(
        figure_id="Figure_p4_1",
        figure_type="forest_plot",
        axis_labels={"x": "Hazard Ratio (log scale)", "y": "Study"},
        extracted_points=[
            FigurePoint(
                label="Smith et al. 2021",
                estimate="0.68",
                confidence_interval="0.45 to 0.95",
                derived_from_figure=True,
            ),
            FigurePoint(
                label="Jones et al. 2023",
                estimate="0.55",
                confidence_interval="0.32 to 0.88",
                derived_from_figure=True,
            ),
        ],
        pooled_estimate="0.62",
        confidence_interval="0.48 to 0.79",
        ocr_agreement="FULL",
    )
    dump = schema.model_dump()
    assert dump["figure_id"] == "Figure_p4_1"
    assert len(dump["extracted_points"]) == 2
    assert dump["extracted_points"][0]["derived_from_figure"] is True
    assert dump["ocr_agreement"] == "FULL"
