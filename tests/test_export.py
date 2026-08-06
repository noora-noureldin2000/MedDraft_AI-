import os
from pathlib import Path
import pytest
from meddraft_ai.export.create_docx import create_docx_from_markdown
from meddraft_ai.export.pandoc_converter import convert_markdown_to_docx

def test_docx_export(tmp_path):
    md_content = "# Title\n\n## Introduction\n\nThis is a sample introduction text."
    md_file = tmp_path / "sample.md"
    docx_file = tmp_path / "sample.docx"
    md_file.write_text(md_content, encoding="utf-8")

    out_path = create_docx_from_markdown(str(md_file), str(docx_file))
    assert Path(out_path).exists()

def test_pandoc_fallback_export(tmp_path):
    md_content = "# Title\n\n## Methods\n\nSample methods section."
    md_file = tmp_path / "sample2.md"
    docx_file = tmp_path / "sample2.docx"
    md_file.write_text(md_content, encoding="utf-8")

    out_path = convert_markdown_to_docx(str(md_file), str(docx_file))
    assert Path(out_path).exists()
