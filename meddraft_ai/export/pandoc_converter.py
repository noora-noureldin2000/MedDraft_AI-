import subprocess
import logging
from pathlib import Path
from typing import Optional

from meddraft_ai.export.create_docx import create_docx_from_markdown

logger = logging.getLogger(__name__)

MANUSCRIPT_FONT = "Times New Roman"
MANUSCRIPT_FONT_SIZE_PT = 12
MANUSCRIPT_LINE_SPACING = 2.0


def _apply_manuscript_style(docx_path: Path) -> None:
    """Force APA manuscript body style onto a Pandoc-produced document.

    Pandoc's default reference document is not the manuscript style the export
    contract promises, so the Normal style is overwritten after conversion.
    """
    from docx import Document
    from docx.shared import Pt

    document = Document(str(docx_path))
    normal = document.styles["Normal"]
    normal.font.name = MANUSCRIPT_FONT
    normal.font.size = Pt(MANUSCRIPT_FONT_SIZE_PT)
    normal.paragraph_format.line_spacing = MANUSCRIPT_LINE_SPACING
    document.save(str(docx_path))


def convert_markdown_to_docx(md_path: str | Path, output_docx_path: Optional[str | Path] = None) -> str:
    """
    Converts a Markdown file to formatted DOCX using Pandoc if available,
    or falls back to the native python-docx MarkdownDocxConverter.
    """
    md_file = Path(md_path)
    if not md_file.exists():
        raise FileNotFoundError(f"Markdown file not found: {md_file}")

    out_file = Path(output_docx_path) if output_docx_path else md_file.with_suffix(".docx")

    # Try Pandoc conversion first
    try:
        cmd = ["pandoc", str(md_file), "-o", str(out_file)]
        subprocess.run(cmd, capture_output=True, text=True, check=True)
        if out_file.exists():
            _apply_manuscript_style(out_file)
            logger.info(f"Pandoc conversion successful: {out_file}")
            return str(out_file)
    except Exception as e:
        logger.warning("Pandoc not available or failed: %s. Falling back to python-docx converter.", e)

    # Fallback to python-docx converter
    return create_docx_from_markdown(str(md_file), str(out_file))
