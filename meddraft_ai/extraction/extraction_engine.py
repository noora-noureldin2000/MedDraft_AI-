import json
import re
from pathlib import Path
from typing import Optional, List, Dict, Any

from rich.console import Console
console = Console()

from meddraft_ai.extraction.converter import DocumentConverter
from meddraft_ai.extraction.citation_tracker import CitationVerifier
from meddraft_ai.extraction.secondary_citation import SecondaryCitationExtractor

class ExtractionEngine:
    """Orchestrates PDF ingestion, variable extraction, citation verification,
    and structured result production with full source anchoring.
    """

    def __init__(self, pdf_path: str | Path, output_dir: Optional[str | Path] = None):
        self.pdf_path = Path(pdf_path)
        self.output_dir = Path(output_dir) if output_dir else None
        self.converter: Optional[DocumentConverter] = None
        self.markdown_path: Optional[Path] = None
        self.doc_text: str = ""

    def extract_text_and_citations(self) -> Dict[str, Any]:
        console.print(f"[bold blue]Ingesting PDF: {self.pdf_path.name}...[/bold blue]")
        self.converter = DocumentConverter(self.pdf_path, self.output_dir)
        self.markdown_path = Path(self.converter.convert())
        self.doc_text = self.converter.markdown_text

        citation_meta = self.converter.extract_citation_metadata()
        verified_citations = CitationVerifier.extract_and_verify(self.doc_text)

        # Automatic secondary/nested citation tracing (skill auto-routing:
        # only runs when the text actually contains traceable markers).
        secondary_citations: list[dict] = []
        try:
            if SecondaryCitationExtractor.should_trigger(self.doc_text):
                traced = SecondaryCitationExtractor.extract(
                    self.doc_text,
                    container_meta=citation_meta,
                    max_claims=10,
                )
                secondary_citations = [c.to_dict() for c in traced]
        except Exception as exc:
            console.print(f"[yellow]Secondary citation tracing skipped: {exc}[/yellow]")

        return {
            "study_id": self.pdf_path.stem,
            "markdown_path": str(self.markdown_path),
            "text_snippet": self.doc_text[:2000],
            "metadata": citation_meta,
            "verified_citations": [c.to_dict() for c in verified_citations],
            "secondary_citations": secondary_citations,
        }
