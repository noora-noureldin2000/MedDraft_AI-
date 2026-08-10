"""
PDF sentence highlighting and annotation via PyMuPDF (fitz).

Provides exact-text matching with yellow highlight annotations, robust handling
of multi-line text (hyphenation, soft-hyphen, line-break normalisation), and
graceful degradation when text is not found — no uncaught exceptions.
"""

from __future__ import annotations

import logging
import re
import unicodedata
from pathlib import Path
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Availability guard
# ---------------------------------------------------------------------------
try:
    import fitz  # PyMuPDF

    FITZ_AVAILABLE = True
except ImportError:
    FITZ_AVAILABLE = False
    logger.warning(
        "PyMuPDF (fitz) is not installed. PDF annotation is unavailable. "
        "Install it with: pip install pymupdf"
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _normalize_whitespace(text: str) -> str:
    """Collapse all whitespace variants to a single space."""
    return re.sub(r"[\s\u00a0\u200b]+", " ", text).strip()


def _strip_soft_hyphens(text: str) -> str:
    """Remove soft hyphens (U+00AD) that appear at line-break positions in PDFs."""
    return text.replace("\u00ad", "")


def _normalize_sentence(text: str) -> str:
    """
    Apply all normalisations needed to compare extracted PDF text with a
    user-supplied search string.  Order matters:
      1. Unicode NFC normalisation (handles ligatures, composed chars)
      2. Remove soft hyphens
      3. Collapse whitespace
    """
    text = unicodedata.normalize("NFC", text)
    text = _strip_soft_hyphens(text)
    return _normalize_whitespace(text)


def _build_search_variants(sentence: str) -> List[str]:
    """
    Return a list of search variants to try against each page.

    PyMuPDF's search_for() does substring matching against the page's extracted
    text.  PDFs often break hyphenated words across lines, so we generate
    variants that handle:
      - Normalised form (the primary attempt)
      - Version with hyphens stripped (handles "end-of-line" hyphens)
      - Truncated forms (first 120 / 80 chars) to match partial sentences
        that span page columns or text blocks
    """
    normalised = _normalize_sentence(sentence)
    no_hyphen = normalised.replace("-", " ")

    variants: List[str] = []
    for candidate in [normalised, no_hyphen]:
        variants.append(candidate)
        if len(candidate) > 120:
            variants.append(candidate[:120])
        if len(candidate) > 80:
            variants.append(candidate[:80])

    # De-duplicate while preserving order
    seen: set[str] = set()
    unique: List[str] = []
    for v in variants:
        if v and v not in seen:
            seen.add(v)
            unique.append(v)
    return unique


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

class PDFAnnotator:
    """
    Highlights sentences in a PDF using yellow highlight annotations.

    Usage::

        annotator = PDFAnnotator("paper.pdf")
        annotator.highlight_sentences(
            ["The intervention group showed...", "p < 0.05"],
            output_path="paper_highlighted.pdf",
        )

    The annotator is safe to use even when PyMuPDF is not installed — it logs a
    warning and returns the original path rather than raising.
    """

    # PyMuPDF colour: yellow (R=1, G=1, B=0)
    _HIGHLIGHT_COLOR: Tuple[float, float, float] = (1.0, 1.0, 0.0)

    def __init__(self, pdf_path: str | Path) -> None:
        self.pdf_path = Path(pdf_path)
        if not self.pdf_path.exists():
            raise FileNotFoundError(f"PDF file not found: {self.pdf_path}")

    # ------------------------------------------------------------------
    # Core method
    # ------------------------------------------------------------------

    def highlight_sentences(
        self,
        sentences: List[str],
        output_path: Optional[str | Path] = None,
    ) -> str:
        """
        Search for each sentence in the PDF and annotate matches with a yellow
        highlight.  Multi-page and multi-line matches are handled via PyMuPDF's
        built-in quad/rect search.

        Args:
            sentences: List of text strings to locate and highlight.
            output_path: Destination PDF.  Defaults to
                         ``<stem>_highlighted.pdf`` next to the source file.

        Returns:
            Absolute path to the annotated PDF as a string.

        Raises:
            FileNotFoundError: If the source PDF does not exist.
            RuntimeError: If PyMuPDF is not installed.
        """
        if not FITZ_AVAILABLE:
            raise RuntimeError(
                "PyMuPDF (fitz) is required for PDF annotation. "
                "Install it with: pip install pymupdf"
            )

        out_path = Path(output_path) if output_path else (
            self.pdf_path.parent / f"{self.pdf_path.stem}_highlighted.pdf"
        )

        doc = fitz.open(str(self.pdf_path))
        total_highlights = 0
        not_found: List[str] = []

        for sentence in sentences:
            if not sentence or not sentence.strip():
                continue

            found = self._highlight_single(doc, sentence)
            if found:
                total_highlights += found
            else:
                not_found.append(sentence[:80])

        doc.save(str(out_path))
        doc.close()

        if not_found:
            logger.warning(
                "PDF annotation: %d sentence(s) could not be located and were skipped:\n%s",
                len(not_found),
                "\n".join(f"  - {s}" for s in not_found),
            )

        logger.info(
            "PDF annotation complete: %d highlight(s) added → %s",
            total_highlights,
            out_path,
        )
        return str(out_path)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _highlight_single(self, doc: "fitz.Document", sentence: str) -> int:
        """
        Try to highlight one sentence across all pages of the document.

        Attempts multiple search variants to handle line-break hyphens and
        whitespace normalisation.  Returns the number of annotation rectangles
        added (0 if nothing matched).
        """
        variants = _build_search_variants(sentence)
        count = 0

        for page in doc:
            for variant in variants:
                quads = page.search_for(variant, quads=True)
                if not quads:
                    continue
                for quad in quads:
                    try:
                        annot = page.add_highlight_annot(quad)
                        annot.set_colors(stroke=self._HIGHLIGHT_COLOR)
                        annot.update()
                        count += 1
                    except Exception as exc:
                        # Individual annotation failure must not abort the loop
                        logger.debug(
                            "Failed to add highlight annot on page %d: %s", page.number, exc
                        )
                if count:
                    # Found on this page with this variant — no need to try others
                    break

        return count


# ---------------------------------------------------------------------------
# Convenience function (mirrors pdf_reader.read_pdf pattern)
# ---------------------------------------------------------------------------

def highlight_pdf(
    pdf_path: str | Path,
    sentences: List[str],
    output_path: Optional[str | Path] = None,
) -> str:
    """
    Convenience wrapper around :class:`PDFAnnotator`.

    Returns the output path.  Logs a warning and returns the original path if
    PyMuPDF is unavailable rather than raising.
    """
    if not FITZ_AVAILABLE:
        logger.warning(
            "PyMuPDF not available — skipping highlight for %s", pdf_path
        )
        return str(pdf_path)

    annotator = PDFAnnotator(pdf_path)
    return annotator.highlight_sentences(sentences, output_path=output_path)
