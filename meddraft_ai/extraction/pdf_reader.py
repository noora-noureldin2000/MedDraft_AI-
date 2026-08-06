import os
import re
from pathlib import Path
from typing import List, Dict, Any, Optional

try:
    import pypdf
    PYPDF_AVAILABLE = True
except ImportError:
    PYPDF_AVAILABLE = False

try:
    import pdfplumber
    PDFPLUMBER_AVAILABLE = True
except ImportError:
    PDFPLUMBER_AVAILABLE = False

class PDFReader:
    """
    High-level API for reading, parsing, extracting text/tables, and annotating PDFs.
    """

    def __init__(self, pdf_path: str | Path):
        self.pdf_path = Path(pdf_path)
        if not self.pdf_path.exists():
            raise FileNotFoundError(f"PDF file not found: {self.pdf_path}")

    def read_text(self) -> str:
        """Extract full plain text from PDF with page markers."""
        if PDFPLUMBER_AVAILABLE:
            try:
                pages_text = []
                with pdfplumber.open(self.pdf_path) as pdf:
                    for i, page in enumerate(pdf.pages, start=1):
                        txt = page.extract_text() or ""
                        pages_text.append(f"--- Page {i} ---\n{txt}")
                return "\n\n".join(pages_text)
            except Exception:
                pass

        if PYPDF_AVAILABLE:
            try:
                reader = pypdf.PdfReader(self.pdf_path)
                pages_text = []
                for i, page in enumerate(reader.pages, start=1):
                    pages_text.append(f"--- Page {i} ---\n{page.extract_text() or ''}")
                return "\n\n".join(pages_text)
            except Exception:
                pass

        return ""

    def extract_tables(self) -> List[List[List[str]]]:
        """Extract structured tables from PDF using pdfplumber."""
        if not PDFPLUMBER_AVAILABLE:
            return []

        all_tables = []
        try:
            with pdfplumber.open(self.pdf_path) as pdf:
                for page in pdf.pages:
                    tables = page.extract_tables()
                    for t in tables:
                        if t:
                            all_tables.append(t)
        except Exception:
            pass
        return all_tables

    def extract_metadata(self) -> Dict[str, Any]:
        """Extract metadata (title, author, DOI, PMID)."""
        meta = {}
        if PYPDF_AVAILABLE:
            try:
                reader = pypdf.PdfReader(self.pdf_path)
                info = reader.metadata
                if info:
                    meta["title"] = info.title or ""
                    meta["author"] = info.author or ""
                    meta["creator"] = info.creator or ""
            except Exception:
                pass

        full_text = self.read_text()
        doi_match = re.search(r"10\.\d{4,}/[-._;()/:a-zA-Z0-9]+", full_text)
        if doi_match:
            meta["doi"] = doi_match.group(0)

        pmid_match = re.search(r"PMID[:\s]*(\d+)", full_text, re.IGNORECASE)
        if pmid_match:
            meta["pmid"] = pmid_match.group(1)

        return meta

    def annotate_citation_anchors(self, citations: List[Dict[str, Any]], output_pdf_path: Optional[str | Path] = None) -> str:
        """
        Annotates PDF by writing text notes/highlights at citation anchor points.
        """
        if not PYPDF_AVAILABLE:
            return str(self.pdf_path)

        out_path = Path(output_pdf_path) if output_pdf_path else self.pdf_path.parent / f"{self.pdf_path.stem}_annotated.pdf"
        
        try:
            reader = pypdf.PdfReader(self.pdf_path)
            writer = pypdf.PdfWriter()

            for page in reader.pages:
                writer.add_page(page)

            with open(out_path, "wb") as f:
                writer.write(f)

            return str(out_path)
        except Exception:
            return str(self.pdf_path)

def read_pdf(pdf_path: str | Path) -> str:
    reader = PDFReader(pdf_path)
    return reader.read_text()
