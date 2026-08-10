"""
Extraction package public API.

DocumentConverter depends on docling/pypdfium2, which has a known crash on
some Windows Python environments during import. It is guarded here so that
test_pdf.py (which only needs PDFReader) and test_skill_registry.py can
run without the native library loaded.
"""
from .citation_tracker import CitationTracker
from .extraction_engine import ExtractionEngine
from .pdf_reader import PDFReader, read_pdf
from .pdf_annotator import PDFAnnotator, highlight_pdf

try:
    from .converter import DocumentConverter
except Exception:  # noqa: BLE001  — native-lib crash guard
    import logging as _logging
    _logging.getLogger(__name__).warning(
        "DocumentConverter could not be imported (docling/pypdfium2 unavailable). "
        "PDF conversion via Docling will be disabled."
    )
    DocumentConverter = None  # type: ignore[assignment,misc]

__all__ = [
    "DocumentConverter",
    "CitationTracker",
    "ExtractionEngine",
    "PDFReader",
    "read_pdf",
    "PDFAnnotator",
    "highlight_pdf",
]
