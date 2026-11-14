from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from rich.console import Console

console = Console()
logger = logging.getLogger(__name__)

DOCLING_AVAILABLE: Optional[bool] = None


def is_docling_available() -> bool:
    """Lazy evaluation guard to prevent Windows pypdfium2 access violation on import."""
    global DOCLING_AVAILABLE
    if DOCLING_AVAILABLE is not None:
        return DOCLING_AVAILABLE
    try:
        from docling.document_converter import DocumentConverter as DoclingDocumentConverter  # noqa: F401
        DOCLING_AVAILABLE = True
    except (ImportError, Exception) as exc:
        logger.debug("Docling unavailable: %s", exc)
        DOCLING_AVAILABLE = False
    return DOCLING_AVAILABLE


@dataclass
class ProcessedDocumentBundle:
    """Strongly typed container for complete document extraction representations."""
    markdown: str
    docling_doc: Optional[Any] = None
    page_texts: Dict[int, str] = field(default_factory=dict)
    tables_data: List[Dict[str, Any]] = field(default_factory=list)
    # Phase 0 additions — defaulted so nothing breaks.
    pagemap_path: Optional[str] = None
    figure_ocr_path: Optional[str] = None
    evidence: Optional[Any] = None       # EvidenceIndex when available
    coverage: Dict[str, Any] = field(default_factory=dict)


class DocumentConverterEngine:
    """Converts PDF research studies to structured Markdown with embedded
    figure references, page tracking, table dataframes, and citation metadata extraction.
    """

    def __init__(self, pdf_path: Union[str, Path], output_dir: Optional[Union[str, Path]] = None):
        self.pdf_path = Path(pdf_path)
        if not self.pdf_path.exists():
            raise FileNotFoundError(f"PDF not found: {self.pdf_path}")

        self.doc_name = self.pdf_path.stem
        self._setup_dirs(output_dir)

        self.markdown_text: str = ""
        self.image_refs: Dict[str, str] = {}
        self.total_pages: int = 0
        self.docling_doc: Optional[Any] = None
        self.page_texts: Dict[int, str] = {}
        self.tables_data: List[Dict[str, Any]] = []
        self.figure_evidences: List[Any] = []

    def _setup_dirs(self, output_dir: Optional[Union[str, Path]]) -> None:
        from meddraft_ai.core.config import get_config
        config = get_config()
        base = Path(output_dir) if output_dir else (config.OUTPUT_DIR / "pdf_extractions")
        self.markdown_dir = base / self.doc_name
        self.images_dir = base / self.doc_name / "figures"
        self.markdown_dir.mkdir(parents=True, exist_ok=True)
        self.images_dir.mkdir(parents=True, exist_ok=True)

    def extract_page_texts(self) -> Dict[int, str]:
        """Extract 1-indexed dictionary of page texts using PageMapper first,
        falling back to PyMuPDF, pdfplumber, and pypdf.
        Ensures every physical page has a key.
        """
        # 1. Try PageMapper if enabled
        from meddraft_ai.core.config import get_config
        config = get_config()
        if config.OCR_ENABLED:
            try:
                from meddraft_ai.ingestion.page_mapper import PageMapper
                mapper = PageMapper(
                    pdf_path=self.pdf_path,
                    output_dir=self.markdown_dir,
                    ocr_min_chars=config.OCR_MIN_CHARS,
                    ocr_dpi=config.OCR_DPI,
                    ocr_lang=config.OCR_LANG,
                    tesseract_cmd=config.TESSERACT_CMD,
                    ocr_enabled=config.OCR_ENABLED,
                )
                map_res = mapper.build()
                if map_res.pages:
                    self.page_map_result = map_res
                    pages = {p: ev.text for p, ev in map_res.pages.items()}
                    self.total_pages = len(pages)
                    return pages
            except Exception as exc:
                logger.debug("PageMapper extraction failed or skipped: %s", exc)

        pages: Dict[int, str] = {}
        # 2. PyMuPDF (fitz)
        try:
            import fitz
            doc = fitz.open(str(self.pdf_path))
            for idx in range(len(doc)):
                pages[idx + 1] = doc[idx].get_text("text") or ""
            doc.close()
            self.total_pages = len(pages)
            return pages
        except Exception as exc:
            logger.debug("fitz extraction failed: %s", exc)

        # 3. pdfplumber
        try:
            import pdfplumber
            with pdfplumber.open(self.pdf_path) as pdf:
                for idx, page in enumerate(pdf.pages, start=1):
                    pages[idx] = page.extract_text() or ""
            self.total_pages = len(pages)
            return pages
        except Exception as exc:
            logger.debug("pdfplumber page text extraction failed: %s", exc)

        # 4. pypdf
        try:
            import pypdf
            reader = pypdf.PdfReader(self.pdf_path)
            for idx, page in enumerate(reader.pages, start=1):
                pages[idx] = page.extract_text() or ""
            self.total_pages = len(reader.pages)
            return pages
        except Exception as exc:
            logger.warning("pypdf page text extraction failed: %s", exc)

        if self.total_pages > 0:
            for p in range(1, self.total_pages + 1):
                pages.setdefault(p, "")

        return pages

    def _align_page_indices(self, docling_doc: Any, page_texts: Dict[int, str]) -> int:
        """Compare Docling prov page numbers against physical page texts.
        Returns the offset if consistently page±1.
        """
        if not docling_doc or not page_texts:
            return 0
        offsets = []
        try:
            for item, _level in docling_doc.iterate_items():
                if getattr(item, "label", "") in ("section_header", "text") and len(getattr(item, "text", "")) > 20:
                    doc_p = item.prov[0].page_no if getattr(item, "prov", None) else None
                    if doc_p is None:
                        continue
                    snippet = item.text[:40].strip().lower()
                    for offset in (0, -1, 1):
                        cand_p = doc_p + offset
                        if cand_p in page_texts and snippet in page_texts[cand_p].lower():
                            offsets.append(offset)
                            break
                    if len(offsets) >= 10:
                        break
        except Exception:
            pass

        if offsets and len(offsets) >= 3:
            common = max(set(offsets), key=offsets.count)
            if offsets.count(common) >= len(offsets) * 0.8 and common != 0:
                logger.warning("Docling page alignment drift detected! Applying offset: %d", common)
                return common
        return 0

    def _build_evidence_index(self) -> Any:
        from meddraft_ai.extraction.evidence import (
            EvidenceIndex,
            PageEvidence,
            TableEvidence,
            FigureEvidence,
        )
        page_evidences: Dict[int, PageEvidence] = {}
        if hasattr(self, "page_map_result") and self.page_map_result and self.page_map_result.pages:
            page_evidences = self.page_map_result.pages
        else:
            for p, txt in self.page_texts.items():
                page_evidences[p] = PageEvidence(
                    page=p,
                    text=txt,
                    engine="fitz",
                    char_count=len(txt),
                )

        table_evidences: List[TableEvidence] = []
        for t in self.tables_data:
            table_evidences.append(TableEvidence(
                table_id=t.get("table_id", ""),
                page=t.get("page"),
                caption=t.get("caption", ""),
                markdown=t.get("markdown", ""),
                records=t.get("records", []),
                source=t.get("source", "docling"),
            ))

        fig_evidences: List[FigureEvidence] = getattr(self, "figure_evidences", [])

        idx = EvidenceIndex(
            pages=page_evidences,
            tables=table_evidences,
            figures=fig_evidences,
            docling_markdown=self.markdown_text,
        )
        return idx

    def convert_full(self) -> ProcessedDocumentBundle:
        """Runs complete conversion producing docling document, page texts, and table data."""
        self.page_texts = self.extract_page_texts()
        self.total_pages = len(self.page_texts)

        if not is_docling_available():
            self.markdown_text = self._fallback_extract_text()
            if not self.tables_data:
                self.tables_data = self._extract_tables_pdfplumber()
            evidence = self._build_evidence_index()
            pagemap_p = self.markdown_dir / f"{self.doc_name}_pagemap.json"
            return ProcessedDocumentBundle(
                markdown=self.markdown_text,
                docling_doc=None,
                page_texts=self.page_texts,
                tables_data=self.tables_data,
                pagemap_path=str(pagemap_p) if pagemap_p.exists() else None,
                evidence=evidence,
                coverage=evidence.coverage(),
            )

        return self._convert_with_docling_full()

    def convert(self) -> str:
        """Backwards-compatible converter entry point returning saved markdown path."""
        bundle = self.convert_full()
        md_path = self.markdown_dir / f"{self.doc_name}.md"
        if not md_path.exists():
            md_path.write_text(bundle.markdown, encoding="utf-8")
        return str(md_path)

    def _convert_with_docling_full(self) -> ProcessedDocumentBundle:
        try:
            from docling.datamodel.base_models import InputFormat
            from docling.datamodel.pipeline_options import PdfPipelineOptions
            from docling.document_converter import DocumentConverter as DoclingDocumentConverter, PdfFormatOption

            pipeline_opts = PdfPipelineOptions(do_ocr=True, do_table_structure=True)
            pipeline_opts.table_structure_options.do_cell_matching = True

            from meddraft_ai.core.config import get_config
            cfg = get_config()
            try:
                from docling.datamodel.pipeline_options import TesseractCliOcrOptions
                pipeline_opts.ocr_options = TesseractCliOcrOptions(
                    tesseract_cmd=cfg.TESSERACT_CMD,
                    lang=[cfg.OCR_LANG],
                )
            except Exception as ocr_exc:
                logger.debug("Could not pin TesseractCliOcrOptions: %s", ocr_exc)

            converter = DoclingDocumentConverter(
                format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_opts)}
            )

            console.print(f"[yellow]Converting PDF: {self.pdf_path.name}[/yellow]")
            result = converter.convert(self.pdf_path)
            self.docling_doc = result.document

            try:
                self.total_pages = self.docling_doc.num_pages
            except Exception:
                pass

            self.markdown_text = self.docling_doc.export_to_markdown()
            self._extract_images(self.docling_doc)
            self._rewrite_image_refs()
            self._extract_tables_from_docling(self.docling_doc)

            # Fallback to pdfplumber tables if docling found zero tables
            if not self.tables_data:
                self.tables_data = self._extract_tables_pdfplumber()

            md_path = self.markdown_dir / f"{self.doc_name}.md"
            md_path.write_text(self.markdown_text, encoding="utf-8")
            console.print(f"[green]  Markdown saved: {md_path}[/green]")

            evidence = self._build_evidence_index()
            pagemap_p = self.markdown_dir / f"{self.doc_name}_pagemap.json"
            fig_ocr_p = self.images_dir / f"{self.doc_name}_figure_ocr.json"
            return ProcessedDocumentBundle(
                markdown=self.markdown_text,
                docling_doc=self.docling_doc,
                page_texts=self.page_texts,
                tables_data=self.tables_data,
                pagemap_path=str(pagemap_p) if pagemap_p.exists() else None,
                figure_ocr_path=str(fig_ocr_p) if fig_ocr_p.exists() else None,
                evidence=evidence,
                coverage=evidence.coverage(),
            )

        except Exception as exc:
            console.print(f"[red]Docling conversion failed: {exc}. Falling back to text extraction.[/red]")
            self.markdown_text = self._fallback_extract_text()
            if not self.tables_data:
                self.tables_data = self._extract_tables_pdfplumber()
            evidence = self._build_evidence_index()
            pagemap_p = self.markdown_dir / f"{self.doc_name}_pagemap.json"
            return ProcessedDocumentBundle(
                markdown=self.markdown_text,
                docling_doc=None,
                page_texts=self.page_texts,
                tables_data=self.tables_data,
                pagemap_path=str(pagemap_p) if pagemap_p.exists() else None,
                evidence=evidence,
                coverage=evidence.coverage(),
            )

    def _extract_tables_from_docling(self, doc: Any) -> None:
        """Extract structured tables with coordinates, markdown grid, and records."""
        table_count = 0
        self.tables_data = []
        for element, _level in doc.iterate_items():
            if getattr(element, "label", "") == "table":
                table_count += 1
                page_no = element.prov[0].page_no if getattr(element, "prov", None) else 1
                records = []
                try:
                    df = element.export_to_dataframe()
                    records = df.to_dict(orient="records")
                except Exception as exc:
                    logger.debug("Failed dataframe export on table %d: %s", table_count, exc)

                caption = getattr(element, "caption_text", None) or f"Table {table_count}"
                caption_source = "docling_caption" if getattr(element, "caption_text", None) else "synthesized"

                self.tables_data.append({
                    "table_id": f"Table_p{page_no}_{table_count}",
                    "page": page_no,
                    "caption": caption,
                    "caption_source": caption_source,
                    "markdown": element.export_to_markdown() if hasattr(element, "export_to_markdown") else "",
                    "records": records,
                    "source": "docling",
                })

    def _extract_tables_pdfplumber(self) -> List[Dict[str, Any]]:
        """Fallback table extraction using pdfplumber when Docling is unavailable or returns 0 tables."""
        tables: List[Dict[str, Any]] = []
        try:
            import pdfplumber
            with pdfplumber.open(self.pdf_path) as pdf:
                table_count = 0
                for page_idx, page in enumerate(pdf.pages, start=1):
                    raw_tables = page.extract_tables() or []
                    for raw_t in raw_tables:
                        if not raw_t or len(raw_t) < 2:
                            continue
                        table_count += 1
                        headers = [str(c).strip() if c is not None else f"col_{j}" for j, c in enumerate(raw_t[0])]
                        records = []
                        for row in raw_t[1:]:
                            rec = {}
                            for j, h in enumerate(headers):
                                rec[h] = str(row[j]).strip() if j < len(row) and row[j] is not None else ""
                            records.append(rec)

                        # Generate Markdown grid
                        md_lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join(["---"] * len(headers)) + " |"]
                        for r in records:
                            md_lines.append("| " + " | ".join(str(r.get(h, "")) for h in headers) + " |")
                        md_table = "\n".join(md_lines)

                        tables.append({
                            "table_id": f"Table_p{page_idx}_{table_count}",
                            "page": page_idx,
                            "caption": f"Table {table_count}",
                            "caption_source": "pdfplumber_fallback",
                            "markdown": md_table,
                            "records": records,
                            "source": "pdfplumber",
                        })
        except Exception as exc:
            logger.debug("pdfplumber table extraction failed: %s", exc)
        return tables

    def _extract_images(self, doc: Any) -> None:
        from meddraft_ai.extraction.evidence import FigureEvidence
        image_counter = 0
        self.figure_evidences = []
        for element, _level in doc.iterate_items():
            image_ref = getattr(element, "image", None)
            if image_ref is None or not getattr(image_ref, "uri", None):
                continue
            try:
                pil_image = image_ref.get_image(doc)
                if pil_image is None:
                    continue
                image_counter += 1
                filename = f"fig_{image_counter:04d}.png"
                filepath = self.images_dir / filename
                pil_image.save(str(filepath))
                self.image_refs[image_ref.uri] = filename

                page_no = element.prov[0].page_no if getattr(element, "prov", None) else None
                caption = getattr(element, "caption_text", None) or f"Figure {image_counter}"

                self.figure_evidences.append(FigureEvidence(
                    figure_id=f"Figure_p{page_no or 1}_{image_counter}",
                    page=page_no,
                    image_path=str(filepath),
                    caption=caption,
                ))
            except Exception as exc:
                logger.debug("Image extraction failed: %s", exc)

        # Run Figure OCR if enabled
        from meddraft_ai.core.config import get_config
        cfg = get_config()
        if cfg.FIGURE_OCR_ENABLED and self.figure_evidences:
            try:
                from meddraft_ai.ingestion.figure_ocr import FigureOCR
                f_ocr = FigureOCR(
                    tesseract_cmd=cfg.TESSERACT_CMD,
                    lang=cfg.OCR_LANG,
                    output_dir=self.images_dir,
                )
                self.figure_evidences = f_ocr.process_all(self.figure_evidences, doc_name=self.doc_name)
            except Exception as ocr_exc:
                logger.debug("Figure OCR processing failed: %s", ocr_exc)

    def _rewrite_image_refs(self) -> None:
        for original_uri, local_name in self.image_refs.items():
            relative_path = f"figures/{local_name}"
            self.markdown_text = self.markdown_text.replace(original_uri, relative_path)

    def _fallback_extract_text(self) -> str:
        if self.page_texts:
            text = "\n\n".join(f"--- Page {p} ---\n{txt}" for p, txt in sorted(self.page_texts.items()))
        else:
            text = self._extract_with_pypdf()
        self.markdown_text = text
        md_path = self.markdown_dir / f"{self.doc_name}.md"
        md_path.write_text(text, encoding="utf-8")
        return text

    def _extract_with_pypdf(self) -> str:
        try:
            import pypdf
            reader = pypdf.PdfReader(self.pdf_path)
            self.total_pages = len(reader.pages)
            pages = []
            for i, page in enumerate(reader.pages, start=1):
                pages.append(f"[Page {i}]\n" + (page.extract_text() or ""))
            return "\n\n".join(pages)
        except Exception:
            return f"[ERROR] Could not extract text from {self.pdf_path.name}"

    def extract_citation_metadata(self) -> Dict[str, str]:
        from meddraft_ai.extraction.citation_tracker import (
            DOI_PATTERN,
            strip_doi_punctuation,
        )
        text = self.markdown_text
        meta: Dict[str, str] = {}
        doi_match = re.search(DOI_PATTERN, text)
        if doi_match:
            doi = strip_doi_punctuation(doi_match.group(0))
            if doi:
                meta["doi"] = doi

        pmid_match = re.search(r"PMID[:\s]*(\d+)", text, re.IGNORECASE)
        if pmid_match:
            meta["pmid"] = pmid_match.group(1)

        return meta


DocumentConverter = DocumentConverterEngine
