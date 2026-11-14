from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class SemanticDocumentChunker:
    """Splits full document into IMRaD semantic sections and isolates tables and figures with provenance."""

    SECTION_MAP = {
        "methods": r"\b(methods?|materials?|study design|participants|patients|interventions?|eligibility)\b",
        "results": r"\b(results?|findings|outcomes|efficacy|safety|adverse events)\b",
        "discussion": r"\b(discussion|limitations?|conclusions?|implications)\b",
        "references": r"\b(references?|bibliography|literature cited)\b",
    }

    def __init__(self):
        self.header_fallbacks: int = 0

    def chunk_bundle(self, bundle: Any) -> Dict[str, List[Dict[str, Any]]]:
        """Entry point accepting ProcessedDocumentBundle."""
        docling_doc = getattr(bundle, "docling_doc", None)
        tables_data = getattr(bundle, "tables_data", [])
        page_texts = getattr(bundle, "page_texts", {})
        evidence = getattr(bundle, "evidence", None)

        if docling_doc:
            chunks = self.chunk_docling_document(docling_doc)
            if not chunks.get("tables") and tables_data:
                chunks["tables"] = tables_data
        else:
            chunks = self.chunk_text_fallback(page_texts, tables_data=tables_data)

        # Wire figures from EvidenceIndex if present and chunks["figures"] is empty
        if evidence and hasattr(evidence, "figures") and evidence.figures and not chunks.get("figures"):
            for fig in evidence.figures:
                ocr_part = f" | OCR: {fig.ocr_text}" if fig.ocr_text else ""
                chunks["figures"].append({
                    "page": fig.page or 1,
                    "figure_id": fig.figure_id,
                    "caption": fig.caption,
                    "image_path": fig.image_path,
                    "ocr_text": fig.ocr_text,
                    "text": f"[FIGURE p{fig.page or '?'}] {fig.caption}{ocr_part}".strip(),
                })

        return chunks

    def chunk_docling_document(self, docling_doc: Any) -> Dict[str, List[Dict[str, Any]]]:
        """Iterates items in a Docling document and classifies them into IMRaD buckets."""
        buckets: Dict[str, List[Dict[str, Any]]] = {
            "abstract_intro": [],
            "methods": [],
            "results": [],
            "discussion": [],
            "tables": [],
            "figures": [],
            "references": [],
            "unassigned": [],
        }
        current_bucket = "abstract_intro"

        for item, _level in docling_doc.iterate_items():
            page_no = item.prov[0].page_no if getattr(item, "prov", None) else 1

            if getattr(item, "label", "") == "table":
                records = []
                try:
                    records = item.export_to_dataframe().to_dict(orient="records")
                except Exception as exc:
                    logger.debug("Docling table export failed: %s", exc)

                caption = getattr(item, "caption_text", None) or f"Table {len(buckets['tables']) + 1}"
                buckets["tables"].append({
                    "table_id": f"Table_p{page_no}_{len(buckets['tables']) + 1}",
                    "page": page_no,
                    "caption": caption,
                    "markdown": item.export_to_markdown() if hasattr(item, "export_to_markdown") else "",
                    "records": records,
                })
                continue

            if getattr(item, "label", "") in ("picture", "figure", "image"):
                caption = getattr(item, "caption_text", None) or getattr(item, "text", "") or f"Figure {len(buckets['figures']) + 1}"
                buckets["figures"].append({
                    "figure_id": f"Figure_p{page_no}_{len(buckets['figures']) + 1}",
                    "page": page_no,
                    "caption": caption,
                    "text": f"[FIGURE p{page_no}] {caption}".strip(),
                })
                continue

            text = getattr(item, "text", "").strip()
            if not text:
                continue

            # Header match: check item label or fallback for short text lines
            matched_bucket = None
            if getattr(item, "label", "") in ("section_header", "title"):
                matched_bucket = self._match_section_header(text)
            elif len(text.split()) <= 6 and len(text) < 50:
                matched_bucket = self._match_section_header(text)
                if matched_bucket:
                    self.header_fallbacks += 1

            if matched_bucket:
                current_bucket = matched_bucket

            buckets[current_bucket].append({
                "page": page_no,
                "section": current_bucket,
                "text": text,
            })

        return buckets

    def chunk_text_fallback(
        self,
        page_texts: Dict[int, str],
        tables_data: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Fallback chunker operating on 1-indexed page texts when Docling document is absent."""
        buckets: Dict[str, List[Dict[str, Any]]] = {
            "abstract_intro": [],
            "methods": [],
            "results": [],
            "discussion": [],
            "tables": tables_data or [],
            "figures": [],
            "references": [],
            "unassigned": [],
        }
        current_bucket = "abstract_intro"

        for page_no, page_text in sorted(page_texts.items()):
            lines = [ln.strip() for ln in page_text.splitlines() if ln.strip()]
            current_chunk_lines: List[str] = []

            for line in lines:
                matched = self._match_section_header(line)
                if matched:
                    if current_chunk_lines:
                        buckets[current_bucket].append({
                            "page": page_no,
                            "section": current_bucket,
                            "text": " ".join(current_chunk_lines),
                        })
                        current_chunk_lines = []
                    current_bucket = matched

                current_chunk_lines.append(line)

            if current_chunk_lines:
                buckets[current_bucket].append({
                    "page": page_no,
                    "section": current_bucket,
                    "text": " ".join(current_chunk_lines),
                })

        return buckets

    def _match_section_header(self, text: str) -> Optional[str]:
        """Determines if text matches or begins with a standard IMRaD section header."""
        clean = text.strip().lstrip("#").strip()
        for bucket, pattern in self.SECTION_MAP.items():
            # Matches line starting with the section name (e.g. 'Methods: ...' or 'Results - ...')
            if re.match(r"^" + pattern + r"[\s:\-–—\.]", clean, re.IGNORECASE):
                return bucket
            # Matches a standalone short header line (e.g. 'Study Design and Methods').
            # Body sentences such as 'A total of 278 patients were enrolled.' are
            # excluded: they end in a period and run past the header word count,
            # and treating them as headers would resegment results into Methods.
            word_count = len(clean.split())
            if (
                len(clean) < 60
                and word_count <= 8
                and not clean.endswith((".", ";", ","))
                and re.search(pattern, clean, re.IGNORECASE)
            ):
                return bucket
        return None
