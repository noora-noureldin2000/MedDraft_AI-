import os
import subprocess
import logging
from pathlib import Path
from typing import Optional

from meddraft_ai.export.create_docx import create_docx_from_markdown

logger = logging.getLogger(__name__)

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
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        if out_file.exists():
            logger.info(f"Pandoc conversion successful: {out_file}")
            return str(out_file)
    except Exception as e:
        logger.info(f"Pandoc not available or failed: {e}. Falling back to python-docx converter.")

    # Fallback to python-docx converter
    return create_docx_from_markdown(str(md_file), str(out_file))
