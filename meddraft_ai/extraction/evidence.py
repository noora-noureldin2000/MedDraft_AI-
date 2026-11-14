"""
Evidence corpus data structures for unified PDF extraction grounding.

The EvidenceIndex is the single source of truth that flows through chunker,
extractor, and verifier. It unifies Docling markdown, page-level text from
multiple engines, table records, and figure OCR into one object so that the
grounding verifier never validates quotes against a different rendering than
the one the LLM read.

Phase 0: dataclass definitions only — no behavioural change.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class PageEvidence:
    """Text evidence for a single PDF page from the best available engine."""
    page: int
    text: str                 # best available rendering
    engine: str               # docling | tesseract | pymupdf | pdfplumber
    char_count: int = 0
    needs_ocr: bool = False
    ocr_applied: bool = False

    def __post_init__(self) -> None:
        if not self.char_count and self.text:
            self.char_count = len(self.text)


@dataclass
class TableEvidence:
    """Structured table evidence with both markdown and record representations."""
    table_id: str
    page: Optional[int] = None
    caption: str = ""
    markdown: str = ""
    records: list = field(default_factory=list)
    source: str = "docling"               # docling | pdfplumber

    def to_dict(self) -> Dict[str, Any]:
        """Serialise to the same shape used by tables_data today."""
        return {
            "table_id": self.table_id,
            "page": self.page,
            "caption": self.caption,
            "markdown": self.markdown,
            "records": self.records,
            "source": self.source,
        }


@dataclass
class FigureEvidence:
    """Evidence from an exported figure image, its caption, and OCR text."""
    figure_id: str
    page: Optional[int] = None
    image_path: str = ""
    caption: str = ""
    ocr_text: str = ""
    ocr_candidates: List[str] = field(default_factory=list)


@dataclass
class EvidenceIndex:
    """Central evidence corpus flowing through the entire extraction pipeline.

    Provides unified page, table, and figure lookups for the grounding verifier,
    while keeping the original Docling markdown for prompt construction.
    """
    pages: Dict[int, PageEvidence] = field(default_factory=dict)
    tables: List[TableEvidence] = field(default_factory=list)
    figures: List[FigureEvidence] = field(default_factory=list)
    docling_markdown: str = ""

    # ── Query helpers ──────────────────────────────────────────────────

    def page_candidates(self, page: int) -> List[Tuple[str, str]]:
        """Return (source_engine, normalised_text) pairs for *page*.

        The caller gets every available rendering so the verifier can match
        against whichever engine produced the text the LLM actually saw.
        """
        results: List[Tuple[str, str]] = []
        evidence = self.pages.get(page)
        if evidence and evidence.text:
            results.append((evidence.engine, evidence.text))
        return results

    def table_candidates(
        self,
        page: Optional[int] = None,
        table_id: Optional[str] = None,
    ) -> List[Tuple[str, str]]:
        """Return (source, text) for tables matching *page* or *table_id*."""
        results: List[Tuple[str, str]] = []
        for tbl in self.tables:
            match_page = page is not None and tbl.page == page
            match_id = table_id is not None and tbl.table_id == table_id
            if match_page or match_id:
                if tbl.markdown:
                    results.append((f"table_{tbl.source}_md", tbl.markdown))
                if tbl.records:
                    import json
                    results.append((f"table_{tbl.source}_records", json.dumps(tbl.records, ensure_ascii=False)))
        return results

    def get_table(self, table_id: str) -> Optional[TableEvidence]:
        """Find a TableEvidence by table_id."""
        for tbl in self.tables:
            if tbl.table_id == table_id:
                return tbl
        return None

    def figure_candidates(self, page: Optional[int] = None) -> List[Tuple[str, str]]:
        """Return (source, text) for figure OCR/caption on *page*."""
        results: List[Tuple[str, str]] = []
        for fig in self.figures:
            if page is not None and fig.page != page:
                continue
            if fig.caption:
                results.append(("figure_caption", fig.caption))
            if fig.ocr_text:
                results.append(("figure_ocr", fig.ocr_text))
        return results

    # ── Coverage summary ───────────────────────────────────────────────

    def coverage(self) -> Dict[str, Any]:
        """Generate a coverage summary for diagnostics and audit output."""
        pages_total = len(self.pages)
        pages_with_text = sum(1 for p in self.pages.values() if p.char_count > 0)
        pages_ocr = sorted(p.page for p in self.pages.values() if p.ocr_applied)
        pages_empty = sorted(p.page for p in self.pages.values() if p.char_count == 0)
        pages_needing_ocr = sorted(p.page for p in self.pages.values() if p.needs_ocr)

        return {
            "pages_total": pages_total,
            "pages_with_text": pages_with_text,
            "pages_ocr": pages_ocr,
            "pages_empty": pages_empty,
            "pages_needing_ocr": pages_needing_ocr,
            "tables_found": len(self.tables),
            "tables_with_records": sum(1 for t in self.tables if t.records),
            "tables_with_caption": sum(1 for t in self.tables if t.caption),
            "figures_exported": len(self.figures),
            "figures_with_ocr": sum(1 for f in self.figures if f.ocr_text),
        }
