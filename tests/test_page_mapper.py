"""
Tests for PageMapper (Phase A) — page-level text extraction with OCR recovery.

Tests use monkeypatched extractors so no actual PDF or Tesseract binary
is required.  All assertions are deterministic.
"""

import json
from pathlib import Path
from typing import Dict
from unittest.mock import MagicMock, patch

import pytest

from meddraft_ai.extraction.evidence import PageEvidence
from meddraft_ai.ingestion.page_mapper import PageMapper, PageMapResult


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_pdf(tmp_path) -> Path:
    """Create a minimal PDF fixture for testing."""
    import pypdf
    writer = pypdf.PdfWriter()
    for _ in range(4):
        writer.add_blank_page(width=612, height=792)
    pdf = tmp_path / "test_doc.pdf"
    with open(pdf, "wb") as f:
        writer.write(f)
    return pdf


@pytest.fixture
def output_dir(tmp_path) -> Path:
    d = tmp_path / "output"
    d.mkdir()
    return d


# ---------------------------------------------------------------------------
# 1. Text layer extraction produces 1-indexed page keys
# ---------------------------------------------------------------------------

def test_pagemap_has_key_for_every_page(tmp_pdf, output_dir):
    """Every physical page must have a key in the result, even if text is empty."""
    mapper = PageMapper(tmp_pdf, output_dir, ocr_enabled=False)
    result = mapper.build()
    # Blank pages still get entries
    assert result.total_pages == 4
    for i in range(1, 5):
        assert i in result.pages


def test_pagemap_page_numbers_are_1_indexed(tmp_pdf, output_dir):
    """Page numbering must be 1-indexed, matching PDF convention."""
    mapper = PageMapper(tmp_pdf, output_dir, ocr_enabled=False)
    result = mapper.build()
    page_numbers = sorted(result.pages.keys())
    assert page_numbers[0] == 1
    assert page_numbers[-1] == 4


# ---------------------------------------------------------------------------
# 2. OCR flagging based on character count threshold
# ---------------------------------------------------------------------------

def test_needs_ocr_flagged_for_low_char_pages(tmp_pdf, output_dir):
    """Pages with fewer chars than ocr_min_chars are flagged needs_ocr."""
    mapper = PageMapper(tmp_pdf, output_dir, ocr_min_chars=30, ocr_enabled=False)

    # Monkeypatch to inject controlled text
    def mock_extract():
        return {1: ("Full page of text with plenty of characters here", "pymupdf"),
                2: ("", "pymupdf"),          # empty → needs OCR
                3: ("Short", "pymupdf"),     # too few chars → needs OCR
                4: ("This page has enough characters to not need OCR at all.", "pymupdf")}
    mapper._extract_text_layer = mock_extract

    result = mapper.build()
    assert result.pages[1].needs_ocr is False
    assert result.pages[2].needs_ocr is True
    assert result.pages[3].needs_ocr is True
    assert result.pages[4].needs_ocr is False


# ---------------------------------------------------------------------------
# 3. OCR called only on flagged pages
# ---------------------------------------------------------------------------

def test_ocr_called_only_on_flagged_pages(tmp_pdf, output_dir):
    """OCR must only be invoked for pages where needs_ocr is True."""
    mapper = PageMapper(tmp_pdf, output_dir, ocr_min_chars=30, ocr_enabled=True)

    def mock_extract():
        return {1: ("Full text here with many characters", "pymupdf"),
                2: ("", "pymupdf"),
                3: ("OK text that is long enough to pass threshold here", "pymupdf")}
    mapper._extract_text_layer = mock_extract

    ocr_called_pages = []
    original_apply_ocr = mapper._apply_ocr

    def tracking_apply_ocr(result, page_numbers):
        ocr_called_pages.extend(page_numbers)

    mapper._apply_ocr = tracking_apply_ocr
    result = mapper.build()

    # Only page 2 should be in the OCR call
    assert ocr_called_pages == [2]
    assert result.pages[1].needs_ocr is False
    assert result.pages[2].needs_ocr is True


# ---------------------------------------------------------------------------
# 4. PyMuPDF fallback when fitz is unavailable
# ---------------------------------------------------------------------------

def test_pymupdf_fallback_to_pdfplumber(tmp_pdf, output_dir):
    """When PyMuPDF import fails, pdfplumber must be used."""
    mapper = PageMapper(tmp_pdf, output_dir, ocr_enabled=False)

    import builtins
    real_import = builtins.__import__

    def mock_import(name, *args, **kwargs):
        if name == "fitz":
            raise ImportError("fitz not available")
        return real_import(name, *args, **kwargs)

    with patch("builtins.__import__", side_effect=mock_import):
        pages = mapper._extract_text_layer()

    # Should still get results via pdfplumber
    assert len(pages) > 0
    # Engine should be pdfplumber since fitz was blocked
    for _page_no, (text, engine) in pages.items():
        assert engine == "pdfplumber"


# ---------------------------------------------------------------------------
# 5. Pagemap JSON schema validation
# ---------------------------------------------------------------------------

def test_pagemap_json_written_correctly(tmp_pdf, output_dir):
    """The persisted pagemap.json must have the expected schema."""
    mapper = PageMapper(tmp_pdf, output_dir, ocr_enabled=False)

    def mock_extract():
        return {1: ("Page one text", "pymupdf"),
                2: ("Page two text", "pymupdf")}
    mapper._extract_text_layer = mock_extract

    mapper.build()

    pagemap_file = output_dir / "test_doc_pagemap.json"
    assert pagemap_file.exists()

    data = json.loads(pagemap_file.read_text(encoding="utf-8"))
    assert data["document"] == "test_doc"
    assert data["total_pages"] == 2
    assert "pages" in data
    assert "1" in data["pages"]
    assert "2" in data["pages"]

    page_1 = data["pages"]["1"]
    assert "engine" in page_1
    assert "char_count" in page_1
    assert "needs_ocr" in page_1
    assert "ocr_applied" in page_1


# ---------------------------------------------------------------------------
# 6. Empty page gets a key (never missing)
# ---------------------------------------------------------------------------

def test_empty_page_still_has_key(tmp_pdf, output_dir):
    """A page producing zero text must still be present in the result."""
    mapper = PageMapper(tmp_pdf, output_dir, ocr_enabled=False)

    def mock_extract():
        return {1: ("Some text", "pymupdf"), 2: ("", "pymupdf")}
    mapper._extract_text_layer = mock_extract

    result = mapper.build()
    assert 2 in result.pages
    assert result.pages[2].text == ""
    assert result.pages[2].char_count == 0


# ---------------------------------------------------------------------------
# 7. OCR disabled skips everything
# ---------------------------------------------------------------------------

def test_ocr_disabled_skips_ocr(tmp_pdf, output_dir):
    """When ocr_enabled=False, no OCR is ever attempted."""
    mapper = PageMapper(tmp_pdf, output_dir, ocr_enabled=False, ocr_min_chars=9999)

    def mock_extract():
        return {1: ("Short", "pymupdf")}
    mapper._extract_text_layer = mock_extract

    ocr_called = False
    original_apply = mapper._apply_ocr

    def spy_ocr(*args, **kwargs):
        nonlocal ocr_called
        ocr_called = True

    mapper._apply_ocr = spy_ocr
    mapper.build()
    assert ocr_called is False
