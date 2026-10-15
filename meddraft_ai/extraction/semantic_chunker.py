from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class SemanticDocumentChunker:
    """Splits full document into IMRaD semantic sections and isolates tables with provenance."""

    SECTION_MAP = {
        "methods": r"\b(methods?|materials?|study design|participants|patients|interventions?|eligibility)\b",
        "results": r"\b(results?|findings|outcomes|efficacy|safety|adverse events)\b",
        "discussion": r"\b(discussion|limitations?|conclusions?|implications)\b",
    }

    def chunk_bundle(self, bundle: Any) -> Dict[str, List[Dict[str, Any]]]:
        """Entry point accepting ProcessedDocumentBundle."""
        docling_doc = getattr(bundle, "docling_doc", None)
        tables_data = getattr(bundle, "tables_data", [])
        page_texts = getattr(bundle, "page_texts", {})

        if docling_doc:
            chunks = self.chunk_docling_document(docling_doc)
            if not chunks.get("tables") and tables_data:
                chunks["tables"] = tables_data
            return chunks

        return self.chunk_text_fallback(page_texts, tables_data=tables_data)

    def chunk_docling_document(self, docling_doc: Any) -> Dict[str, List[Dict[str, Any]]]:
        """Iterates items in a Docling document and classifies them into IMRaD buckets."""
        buckets: Dict[str, List[Dict[str, Any]]] = {
            "abstract_intro": [],
            "methods": [],
            "results": [],
            "discussion": [],
            "tables": [],
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

                buckets["tables"].append({
                    "table_id": f"Table_p{page_no}_{len(buckets['tables']) + 1}",
                    "page": page_no,
                    "caption": getattr(item, "caption_text", f"Table {len(buckets['tables']) + 1}"),
                    "markdown": item.export_to_markdown() if hasattr(item, "export_to_markdown") else "",
                    "records": records,
                })
                continue

            text = getattr(item, "text", "").strip()
            if not text:
                continue

            if getattr(item, "label", "") in ("section_header", "title"):
                matched_bucket = self._match_section_header(text)
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
            # Matches standalone short header line (e.g. 'Study Design and Methods')
            if len(clean) < 60 and re.search(pattern, clean, re.IGNORECASE):
                return bucket
        return None
