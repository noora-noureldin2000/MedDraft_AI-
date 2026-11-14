"""
Per-page PDF text extraction with OCR recovery for scanned/hybrid documents.

The PageMapper produces a ``pagemap.json`` that records, for every physical
page, which engine produced the text, whether OCR was needed and applied, and
the character count.  Downstream consumers (EvidenceIndex, verifier) use this
as the single page-text source of truth.

Design principles:
- Text PDFs are never OCR'd (runtime sanity).
- Only pages flagged ``needs_ocr`` get 300-DPI Tesseract.
- Every physical page always gets a key, even if the text is empty.
- Graceful degradation: if PyMuPDF is unavailable, fall back to pdfplumber.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from meddraft_ai.extraction.evidence import PageEvidence

logger = logging.getLogger(__name__)


@dataclass
class PageMapResult:
    """Container for the full page-map output."""
    pages: Dict[int, PageEvidence] = field(default_factory=dict)
    total_pages: int = 0
    ocr_applied_pages: List[int] = field(default_factory=list)


class PageMapper:
    """Builds a per-page text map with OCR recovery for scanned pages.

    Parameters
    ----------
    pdf_path : Path
        Input PDF file.
    output_dir : Path
        Directory to write ``{doc}_pagemap.json``.
    ocr_min_chars : int
        Pages with fewer characters than this are flagged ``needs_ocr``.
    ocr_dpi : int
        DPI for Tesseract rasterisation of OCR-flagged pages.
    ocr_lang : str
        Tesseract language code.
    tesseract_cmd : str
        Tesseract binary path or name.
    ocr_enabled : bool
        Master switch for OCR recovery.
    """

    def __init__(
        self,
        pdf_path: Path,
        output_dir: Path,
        ocr_min_chars: int = 30,
        ocr_dpi: int = 300,
        ocr_lang: str = "eng",
        tesseract_cmd: str = "tesseract",
        ocr_enabled: bool = True,
    ):
        self.pdf_path = Path(pdf_path)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.ocr_min_chars = ocr_min_chars
        self.ocr_dpi = ocr_dpi
        self.ocr_lang = ocr_lang
        self.tesseract_cmd = tesseract_cmd
        self.ocr_enabled = ocr_enabled

    def build(self) -> PageMapResult:
        """Build the page map: extract text, flag OCR needs, apply OCR.

        Returns
        -------
        PageMapResult
            Page evidence keyed by 1-indexed page number.
        """
        result = PageMapResult()

        # Step 1: Extract text layer from every page (PyMuPDF preferred, pdfplumber fallback)
        raw_pages = self._extract_text_layer()
        result.total_pages = len(raw_pages)

        # Step 2: Flag pages needing OCR
        for page_no, (text, engine) in raw_pages.items():
            char_count = len(text.strip())
            needs_ocr = char_count < self.ocr_min_chars
            result.pages[page_no] = PageEvidence(
                page=page_no,
                text=text,
                engine=engine,
                char_count=char_count,
                needs_ocr=needs_ocr,
                ocr_applied=False,
            )

        # Step 3: OCR flagged pages only
        if self.ocr_enabled:
            ocr_targets = [p for p in result.pages.values() if p.needs_ocr]
            if ocr_targets:
                self._apply_ocr(result, [p.page for p in ocr_targets])

        # Step 4: Persist pagemap.json
        self._save_pagemap(result)

        return result

    def _extract_text_layer(self) -> Dict[int, tuple]:
        """Extract text from every page using PyMuPDF, falling back to pdfplumber.

        Returns
        -------
        dict
            ``{page_no: (text, engine)}`` keyed by 1-indexed page number.
        """
        # Try PyMuPDF first (faster, better two-column handling)
        try:
            import fitz
            doc = fitz.open(str(self.pdf_path))
            pages = {}
            for idx in range(len(doc)):
                page = doc[idx]
                text = page.get_text("text") or ""
                pages[idx + 1] = (text, "pymupdf")
            doc.close()
            logger.info("PageMapper: extracted %d pages via PyMuPDF", len(pages))
            return pages
        except ImportError:
            logger.debug("PyMuPDF not available, falling back to pdfplumber")
        except Exception as exc:
            logger.warning("PyMuPDF extraction failed: %s — falling back", exc)

        # Fallback: pdfplumber
        try:
            import pdfplumber
            pages = {}
            with pdfplumber.open(self.pdf_path) as pdf:
                for idx, page in enumerate(pdf.pages, start=1):
                    text = page.extract_text() or ""
                    pages[idx] = (text, "pdfplumber")
            logger.info("PageMapper: extracted %d pages via pdfplumber", len(pages))
            return pages
        except Exception as exc:
            logger.warning("pdfplumber extraction failed: %s", exc)

        # Last resort: return empty for all pages
        try:
            import pypdf
            reader = pypdf.PdfReader(self.pdf_path)
            pages = {}
            for idx in range(len(reader.pages)):
                text = reader.pages[idx].extract_text() or ""
                pages[idx + 1] = (text, "pypdf")
            return pages
        except Exception as exc:
            logger.error("All text extraction methods failed: %s", exc)
            return {}

    def _apply_ocr(self, result: PageMapResult, page_numbers: List[int]) -> None:
        """Apply Tesseract OCR to specific pages at configured DPI."""
        try:
            import pytesseract
            import fitz
            from PIL import Image
            import io
        except ImportError as exc:
            logger.warning("OCR dependencies unavailable (%s); skipping OCR recovery", exc)
            return

        pytesseract.pytesseract.tesseract_cmd = self.tesseract_cmd

        try:
            doc = fitz.open(str(self.pdf_path))
        except Exception as exc:
            logger.warning("Cannot open PDF for OCR: %s", exc)
            return

        for page_no in page_numbers:
            try:
                page = doc[page_no - 1]  # 0-indexed in fitz
                # Rasterise at OCR_DPI
                mat = fitz.Matrix(self.ocr_dpi / 72, self.ocr_dpi / 72)
                pix = page.get_pixmap(matrix=mat)
                img_bytes = pix.tobytes("png")
                img = Image.open(io.BytesIO(img_bytes))

                # Tesseract with standard settings
                ocr_text = pytesseract.image_to_string(
                    img,
                    lang=self.ocr_lang,
                    config="--oem 3 --psm 3",
                )
                ocr_text = ocr_text.strip()

                if len(ocr_text) > len(result.pages[page_no].text.strip()):
                    result.pages[page_no].text = ocr_text
                    result.pages[page_no].engine = "tesseract"
                    result.pages[page_no].char_count = len(ocr_text)

                result.pages[page_no].ocr_applied = True
                result.ocr_applied_pages.append(page_no)
                logger.info(
                    "PageMapper: OCR page %d → %d chars (engine: %s)",
                    page_no, len(ocr_text), result.pages[page_no].engine,
                )

            except Exception as exc:
                logger.warning("OCR failed on page %d: %s", page_no, exc)

        doc.close()

    def _save_pagemap(self, result: PageMapResult) -> Path:
        """Write pagemap.json with per-page diagnostics."""
        doc_name = self.pdf_path.stem
        pagemap_path = self.output_dir / f"{doc_name}_pagemap.json"

        pagemap_data = {
            "document": doc_name,
            "total_pages": result.total_pages,
            "ocr_applied_pages": result.ocr_applied_pages,
            "pages": {
                str(page_no): {
                    "page": ev.page,
                    "engine": ev.engine,
                    "char_count": ev.char_count,
                    "needs_ocr": ev.needs_ocr,
                    "ocr_applied": ev.ocr_applied,
                }
                for page_no, ev in sorted(result.pages.items())
            },
        }

        pagemap_path.write_text(
            json.dumps(pagemap_data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        logger.info("PageMapper: saved %s", pagemap_path)
        return pagemap_path
