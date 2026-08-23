import re
from pathlib import Path
from typing import Optional, Dict, List, Union

from rich.console import Console
console = Console()

try:
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import PdfPipelineOptions
    from docling.document_converter import DocumentConverter as DoclingDocumentConverter, PdfFormatOption
    DOCLING_AVAILABLE = True
except ImportError:
    DOCLING_AVAILABLE = False

class DocumentConverterEngine:
    """Converts PDF research studies to structured Markdown with embedded
    figure references, page tracking, and citation metadata extraction.
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

    def _setup_dirs(self, output_dir: Optional[Union[str, Path]]) -> None:
        from meddraft_ai.core.config import get_config
        config = get_config()
        base = Path(output_dir) if output_dir else (config.OUTPUT_DIR / "pdf_extractions")
        self.markdown_dir = base / self.doc_name
        self.images_dir = base / self.doc_name / "figures"
        self.markdown_dir.mkdir(parents=True, exist_ok=True)
        self.images_dir.mkdir(parents=True, exist_ok=True)

    def convert(self) -> str:
        if not DOCLING_AVAILABLE:
            return self._fallback_extract_text()
        return self._convert_with_docling()

    def _convert_with_docling(self) -> str:
        try:
            pipeline_opts = PdfPipelineOptions(
                do_ocr=True,
                do_table_structure=True,
            )
            pipeline_opts.table_structure_options.do_cell_matching = True
            converter = DoclingDocumentConverter(
                format_options={
                    InputFormat.PDF: PdfFormatOption(
                        pipeline_options=pipeline_opts,
                    ),
                },
            )

            console.print(f"[yellow]Converting PDF: {self.pdf_path.name}[/yellow]")
            result = converter.convert(self.pdf_path)
            doc = result.document
            try:
                self.total_pages = doc.num_pages
            except Exception:
                try:
                    self.total_pages = len(list(doc.pages))
                except Exception:
                    self.total_pages = 0

            self.markdown_text = doc.export_to_markdown()
            self._extract_images(doc)
            self._rewrite_image_refs()

            md_path = self.markdown_dir / f"{self.doc_name}.md"
            md_path.write_text(self.markdown_text, encoding="utf-8")
            console.print(f"[green]  Markdown saved: {md_path}[/green]")

            return str(md_path)

        except Exception as e:
            console.print(f"[red]Docling conversion failed: {e}. Falling back to text extraction.[/red]")
            return self._fallback_extract_text()

    def _extract_images(self, doc) -> None:
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
        text = self._extract_with_pypdf()
        self.markdown_text = text
        md_path = self.markdown_dir / f"{self.doc_name}.md"
        md_path.write_text(text, encoding="utf-8")
        return str(md_path)

    def _extract_with_pypdf(self) -> str:
        try:
            import pypdf
            reader = pypdf.PdfReader(self.pdf_path)
            self.total_pages = len(reader.pages)
            pages = []
            for i, page in enumerate(reader.pages, start=1):
                pages.append(f"[Page {i}]\n" + page.extract_text())
            return "\n\n".join(pages)
        except Exception:
            return f"[ERROR] Could not extract text from {self.pdf_path.name}"

    def extract_citation_metadata(self) -> dict:
        text = self.markdown_text
        meta = {}
        doi_match = re.search(r"10\.\d{4,}/[-._;()/:a-zA-Z0-9]+", text)
        if doi_match:
            meta["doi"] = doi_match.group(0)

        pmid_match = re.search(r"PMID[:\s]*(\d+)", text, re.IGNORECASE)
        if pmid_match:
            meta["pmid"] = pmid_match.group(1)

        return meta

DocumentConverter = DocumentConverterEngine
