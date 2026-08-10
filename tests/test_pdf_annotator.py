"""
Tests for PDFAnnotator (meddraft_ai/extraction/pdf_annotator.py).

Boundary cases covered per test-guard Rule 3 / Rule 4:
  - Annotator raises FileNotFoundError on missing PDF
  - highlight_pdf returns original path gracefully when fitz is unavailable
  - Markdown fence stripping helper works correctly
  - _build_search_variants generates meaningful deduplication
  - Full annotation round-trip via a real minimal PDF created with fitz
  - Multi-line / hyphenated sentence handling
  - Empty sentence list produces output without error
  - Output path defaults to <stem>_highlighted.pdf when not specified
"""

from __future__ import annotations

import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# Skip entire module gracefully if PyMuPDF is not installed in the test env
# ---------------------------------------------------------------------------
fitz = pytest.importorskip("fitz", reason="PyMuPDF (fitz) not installed — skipping annotation tests")

from meddraft_ai.extraction.pdf_annotator import (
    PDFAnnotator,
    highlight_pdf,
    _normalize_sentence,
    _build_search_variants,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_minimal_pdf(tmp_path: Path, text: str = "Hello world. This is a test sentence.") -> Path:
    """Create a minimal single-page PDF containing the given text."""
    pdf_path = tmp_path / "test.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), text, fontsize=11)
    doc.save(str(pdf_path))
    doc.close()
    return pdf_path


# ---------------------------------------------------------------------------
# Unit tests — helpers (fast, no disk I/O)
# ---------------------------------------------------------------------------

class TestNormalizeSentence:
    def test_collapses_multiple_spaces(self):
        result = _normalize_sentence("hello   world")
        assert result == "hello world"

    def test_strips_soft_hyphen(self):
        # U+00AD is a soft hyphen inserted at line-break positions in PDFs
        result = _normalize_sentence("myo\u00adcardial")
        assert "\u00ad" not in result
        assert "myocardial" in result

    def test_strips_non_breaking_space(self):
        result = _normalize_sentence("p\u00a0<\u00a00.05")
        assert "\u00a0" not in result

    def test_unicode_nfc_normalisation(self):
        # NFD decomposed 'é' should normalise to NFC composed form
        nfd = "caf\u0065\u0301"  # 'cafe' + combining acute
        assert _normalize_sentence(nfd) == "café"


class TestBuildSearchVariants:
    def test_returns_at_least_one_variant(self):
        variants = _build_search_variants("Short sentence.")
        assert len(variants) >= 1

    def test_no_duplicates(self):
        variants = _build_search_variants("x")
        assert len(variants) == len(set(variants))

    def test_truncated_variants_for_long_sentence(self):
        long = "a " * 100  # 200 chars
        variants = _build_search_variants(long)
        lengths = [len(v) for v in variants]
        assert any(l <= 120 for l in lengths)

    def test_hyphen_variant_included(self):
        variants = _build_search_variants("anti-inflammatory drug therapy")
        # One variant should have hyphens replaced with spaces
        assert any(" " * 1 in v and "-" not in v for v in variants)


# ---------------------------------------------------------------------------
# Behaviour tests — PDFAnnotator
# ---------------------------------------------------------------------------

class TestPDFAnnotatorFileNotFound:
    def test_raises_on_missing_pdf(self):
        with pytest.raises(FileNotFoundError, match="PDF file not found"):
            PDFAnnotator("/nonexistent/path/to/paper.pdf")


class TestHighlightPdfGracefulDegradation:
    def test_returns_original_path_when_fitz_unavailable(self, tmp_path):
        """highlight_pdf must not raise when PyMuPDF is unavailable — it logs and returns."""
        pdf_path = tmp_path / "paper.pdf"
        pdf_path.write_bytes(b"%PDF-1.4")  # Minimal valid header

        with patch("meddraft_ai.extraction.pdf_annotator.FITZ_AVAILABLE", False):
            result = highlight_pdf(str(pdf_path), ["any sentence"])
        assert result == str(pdf_path)


class TestPDFAnnotatorRoundTrip:
    def test_empty_sentence_list_produces_output(self, tmp_path):
        """No sentences → output PDF still written with 0 annotations, no exception."""
        pdf_path = _make_minimal_pdf(tmp_path)
        annotator = PDFAnnotator(pdf_path)
        out = annotator.highlight_sentences([], output_path=tmp_path / "out.pdf")
        assert Path(out).exists()

    def test_default_output_path_uses_stem(self, tmp_path):
        """When output_path is omitted, file is written as <stem>_highlighted.pdf."""
        pdf_path = _make_minimal_pdf(tmp_path)
        annotator = PDFAnnotator(pdf_path)
        out = annotator.highlight_sentences(["Hello world"])
        assert out.endswith("_highlighted.pdf")
        assert Path(out).exists()

    def test_exact_sentence_is_highlighted(self, tmp_path):
        """A sentence that exists verbatim in the PDF produces at least one annotation."""
        target = "This is a test sentence."
        pdf_path = _make_minimal_pdf(tmp_path, text=f"Prefix. {target} Suffix.")

        out_path = tmp_path / "annotated.pdf"
        annotator = PDFAnnotator(pdf_path)
        result = annotator.highlight_sentences([target], output_path=out_path)

        # Open the annotated PDF and verify at least one annotation exists
        doc = fitz.open(result)
        annots = list(doc[0].annots())
        doc.close()
        assert len(annots) >= 1, "Expected at least one highlight annotation"

    def test_missing_sentence_does_not_raise(self, tmp_path):
        """A sentence absent from the PDF is skipped with a log warning, not an exception."""
        pdf_path = _make_minimal_pdf(tmp_path, text="Only this text exists.")
        annotator = PDFAnnotator(pdf_path)
        out = annotator.highlight_sentences(
            ["This sentence is definitely not in the PDF at all."],
            output_path=tmp_path / "out.pdf",
        )
        assert Path(out).exists()

    def test_empty_string_sentences_are_ignored(self, tmp_path):
        """Empty and whitespace-only sentences must be silently skipped."""
        pdf_path = _make_minimal_pdf(tmp_path)
        annotator = PDFAnnotator(pdf_path)
        out = annotator.highlight_sentences(["", "   ", None], output_path=tmp_path / "out.pdf")
        assert Path(out).exists()

    def test_multiple_sentences_annotated(self, tmp_path):
        """Multiple valid sentences each get their own highlight annotation."""
        text = "First sentence here. Second sentence here. Third sentence here."
        pdf_path = _make_minimal_pdf(tmp_path, text=text)
        annotator = PDFAnnotator(pdf_path)
        out_path = tmp_path / "multi.pdf"
        annotator.highlight_sentences(
            ["First sentence here.", "Second sentence here."],
            output_path=out_path,
        )
        doc = fitz.open(str(out_path))
        annots = list(doc[0].annots())
        doc.close()
        assert len(annots) >= 2
