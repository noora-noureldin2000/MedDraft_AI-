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

    def _setup_dirs(self, output_dir: Optional[Union[str, Path]]) -> None:
        from meddraft_ai.core.config import get_config
        config = get_config()
        base = Path(output_dir) if output_dir else (config.OUTPUT_DIR / "pdf_extractions")
        self.markdown_dir = base / self.doc_name
        self.images_dir = base / self.doc_name / "figures"
        self.markdown_dir.mkdir(parents=True, exist_ok=True)
        self.images_dir.mkdir(parents=True, exist_ok=True)

    def extract_page_texts(self) -> Dict[int, str]:
        """Extract 1-indexed dictionary of page texts using pdfplumber with pypdf fallback."""
        pages: Dict[int, str] = {}
        try:
            import pdfplumber
            with pdfplumber.open(self.pdf_path) as pdf:
                for idx, page in enumerate(pdf.pages, start=1):
                    pages[idx] = page.extract_text() or ""
            return pages
        except Exception as exc:
            logger.debug("pdfplumber page text extraction failed: %s", exc)

        try:
            import pypdf
            reader = pypdf.PdfReader(self.pdf_path)
            for idx, page in enumerate(reader.pages, start=1):
                pages[idx] = page.extract_text() or ""
            return pages
        except Exception as exc:
            logger.warning("pypdf page text extraction failed: %s", exc)

        return pages

    def convert_full(self) -> ProcessedDocumentBundle:
        """Runs complete conversion producing docling document, page texts, and table data."""
        self.page_texts = self.extract_page_texts()
        self.total_pages = len(self.page_texts)

        if not is_docling_available():
            self.markdown_text = self._fallback_extract_text()
            return ProcessedDocumentBundle(
                markdown=self.markdown_text,
                docling_doc=None,
                page_texts=self.page_texts,
                tables_data=self.tables_data,
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

            md_path = self.markdown_dir / f"{self.doc_name}.md"
            md_path.write_text(self.markdown_text, encoding="utf-8")
            console.print(f"[green]  Markdown saved: {md_path}[/green]")

            return ProcessedDocumentBundle(
                markdown=self.markdown_text,
                docling_doc=self.docling_doc,
                page_texts=self.page_texts,
                tables_data=self.tables_data,
            )

        except Exception as exc:
            console.print(f"[red]Docling conversion failed: {exc}. Falling back to text extraction.[/red]")
            self.markdown_text = self._fallback_extract_text()
            return ProcessedDocumentBundle(
                markdown=self.markdown_text,
                docling_doc=None,
                page_texts=self.page_texts,
                tables_data=self.tables_data,
            )

    def _extract_tables_from_docling(self, doc: Any) -> None:
        """Extract structured tables with coordinates, markdown grid, and records."""
        table_count = 0
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

                self.tables_data.append({
                    "table_id": f"Table_p{page_no}_{table_count}",
                    "page": page_no,
                    "caption": getattr(element, "caption_text", f"Table {table_count}"),
                    "markdown": element.export_to_markdown() if hasattr(element, "export_to_markdown") else "",
                    "records": records,
                })

    def _extract_images(self, doc: Any) -> None:
        image_counter = 0
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
            except Exception:
                pass

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
        text = self.markdown_text
        meta: Dict[str, str] = {}
        doi_match = re.search(r"10\.\d{4,}/[-._;()/:a-zA-Z0-9]+", text)
        if doi_match:
            meta["doi"] = doi_match.group(0)

        pmid_match = re.search(r"PMID[:\s]*(\d+)", text, re.IGNORECASE)
        if pmid_match:
            meta["pmid"] = pmid_match.group(1)

        return meta


DocumentConverter = DocumentConverterEngine
