"""
Coverage manifest generator and audit checks for clinical extraction.

Tracks total pages, OCR recovery, section routing, tables, figures, token budgets,
and verification counts. Emits auditable diagnostics to verify that no page
or section was silently dropped.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class SectionCoverage:
    pages: List[int] = field(default_factory=list)
    chunks: int = 0
    est_tokens: int = 0


@dataclass
class TableCoverage:
    found: int = 0
    with_records: int = 0
    with_caption: int = 0
    pages: List[int] = field(default_factory=list)


@dataclass
class FigureCoverage:
    exported: int = 0
    ocr_hits: int = 0
    vision_extracted: int = 0


@dataclass
class VerificationCoverage:
    reported: int = 0
    not_reported: int = 0
    downgraded: int = 0
    unclear: int = 0


@dataclass
class CoverageManifest:
    pages_total: int = 0
    pages_with_text: int = 0
    pages_ocr: List[int] = field(default_factory=list)
    pages_empty: List[int] = field(default_factory=list)
    page_index_offset: int = 0
    sections: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    tables: Dict[str, Any] = field(default_factory=dict)
    figures: Dict[str, Any] = field(default_factory=dict)
    budget: Dict[str, int] = field(default_factory=dict)
    routing: Dict[str, int] = field(default_factory=dict)
    verification: Dict[str, int] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "pages_total": self.pages_total,
            "pages_with_text": self.pages_with_text,
            "pages_ocr": self.pages_ocr,
            "pages_empty": self.pages_empty,
            "page_index_offset": self.page_index_offset,
            "sections": self.sections,
            "tables": self.tables,
            "figures": self.figures,
            "budget": self.budget,
            "routing": self.routing,
            "verification": self.verification,
            "warnings": self.warnings,
        }

    def save(self, output_path: Path | str) -> Path:
        p = Path(output_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(self.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
        return p


class CoverageAuditor:
    """Computes coverage metrics and checks for accuracy leaks across the pipeline."""

    @staticmethod
    def audit(
        evidence_index: Any,
        semantic_chunks: Dict[str, List[Dict[str, Any]]],
        study_schema: Optional[Any] = None,
        pass_budgets: Optional[Dict[str, int]] = None,
        header_fallbacks: int = 0,
        unassigned_count: int = 0,
        budget_limit: int = 45000,
    ) -> CoverageManifest:
        manifest = CoverageManifest()

        # 1. Pages
        if evidence_index:
            manifest.pages_total = len(evidence_index.pages)
            manifest.pages_with_text = sum(1 for p in evidence_index.pages.values() if p.char_count > 0)
            manifest.pages_ocr = sorted(p.page for p in evidence_index.pages.values() if p.ocr_applied)
            manifest.pages_empty = sorted(p.page for p in evidence_index.pages.values() if p.char_count == 0)

        # 2. Sections
        for sec_name, chunks in semantic_chunks.items():
            if sec_name in ("tables", "figures", "unassigned"):
                continue
            pages_set = sorted({c.get("page", 1) for c in chunks})
            total_chars = sum(len(c.get("text", "")) for c in chunks)
            est_tokens = int(total_chars / 3.5)
            manifest.sections[sec_name] = {
                "pages": pages_set,
                "chunks": len(chunks),
                "est_tokens": est_tokens,
            }
            if not chunks and manifest.pages_total > 3 and sec_name in ("methods", "results"):
                manifest.warnings.append(
                    f"Warning: Section '{sec_name}' is empty while document has {manifest.pages_total} pages."
                )

        # 3. Tables
        tables_list = semantic_chunks.get("tables", [])
        tbl_pages = sorted({t.get("page", 1) for t in tables_list if t.get("page")})
        manifest.tables = {
            "found": len(tables_list),
            "with_records": sum(1 for t in tables_list if t.get("records")),
            "with_caption": sum(1 for t in tables_list if t.get("caption")),
            "pages": tbl_pages,
        }

        # 4. Figures
        figs_list = semantic_chunks.get("figures", [])
        manifest.figures = {
            "exported": len(figs_list),
            "ocr_hits": sum(1 for f in figs_list if f.get("ocr_text")),
            "vision_extracted": len(getattr(study_schema, "figures", [])) if study_schema else 0,
        }

        # 5. Token budgets
        if pass_budgets:
            manifest.budget = pass_budgets
            for p_name, p_tokens in pass_budgets.items():
                if p_tokens > budget_limit:
                    manifest.warnings.append(
                        f"Warning: Pass '{p_name}' estimated tokens ({p_tokens}) exceeded budget limit ({budget_limit})."
                    )

        # 6. Routing fallbacks
        manifest.routing = {
            "header_fallbacks": header_fallbacks,
            "unassigned_items": unassigned_count,
        }

        # 7. Verification metrics
        if study_schema:
            rep = 0
            not_rep = 0
            downgraded = 0
            unclear = 0

            def _count_field(val: Any):
                nonlocal rep, not_rep, downgraded, unclear
                if hasattr(val, "status"):
                    st = getattr(val, "status")
                    note = getattr(val, "verification_note", "") or ""
                    if "DOWNGRADED" in note:
                        downgraded += 1
                    elif st == "REPORTED":
                        rep += 1
                    elif st == "NOT_REPORTED":
                        not_rep += 1
                    elif st == "UNCLEAR":
                        unclear += 1

            for mod_name in ("methods", "results", "discussion"):
                mod = getattr(study_schema, mod_name, None)
                if mod:
                    for f_name in mod.__class__.model_fields:
                        attr = getattr(mod, f_name, None)
                        if isinstance(attr, list):
                            for item in attr:
                                _count_field(item)
                        else:
                            _count_field(attr)

            manifest.verification = {
                "reported": rep,
                "not_reported": not_rep,
                "downgraded": downgraded,
                "unclear": unclear,
            }

        return manifest
