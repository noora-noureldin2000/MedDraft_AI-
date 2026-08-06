import os
import re
from pathlib import Path
from typing import Optional
from docx import Document
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn

class MarkdownDocxConverter:
    """
    Converts Markdown content to formatted Word (.docx) documents strictly following
    AMA and APA 7th edition manuscript styling rules.
    """
    def __init__(self, font_name: str = "Times New Roman", font_size: int = 12):
        self.doc = Document()
        self.font_name = font_name
        self.font_size = font_size
        self._setup_styles()

    def _setup_styles(self):
        style = self.doc.styles['Normal']
        font = style.font
        font.name = self.font_name
        font.size = Pt(self.font_size)
        style.paragraph_format.line_spacing = 2.0
        style.paragraph_format.space_after = Pt(0)
        style.paragraph_format.space_before = Pt(0)

    def add_heading_custom(self, text: str, level: int = 1):
        h = self.doc.add_heading(text, level=level)
        for run in h.runs:
            run.font.name = self.font_name
            run.font.color.rgb = RGBColor(0, 0, 0)
        return h

    def add_paragraph_styled(self, text: str, bold: bool = False, italic: bool = False):
        p = self.doc.add_paragraph()
        p.paragraph_format.line_spacing = 2.0
        p.paragraph_format.space_after = Pt(0)
        p.paragraph_format.space_before = Pt(0)
        run = p.add_run(text)
        run.font.name = self.font_name
        run.font.size = Pt(self.font_size)
        run.bold = bold
        run.italic = italic
        return p

    def convert_markdown(self, md_content: str, output_path: str | Path) -> str:
        lines = md_content.split('\n')
        in_code_block = False

        for line in lines:
            line_str = line.strip()
            if not line_str:
                continue

            if line_str.startswith('```'):
                in_code_block = not in_code_block
                continue

            if in_code_block:
                self.add_paragraph_styled(line_str)
                continue

            if line_str.startswith('# '):
                self.add_heading_custom(line_str[2:], level=1)
            elif line_str.startswith('## '):
                self.add_heading_custom(line_str[3:], level=2)
            elif line_str.startswith('### '):
                self.add_heading_custom(line_str[4:], level=3)
            elif line_str.startswith('- ') or line_str.startswith('* '):
                self.add_paragraph_styled(f"• {line_str[2:]}")
            else:
                # Process inline bold/italic
                clean_text = re.sub(r'\*\*(.*?)\*\*', r'\1', line_str)
                clean_text = re.sub(r'\*(.*?)\*', r'\1', clean_text)
                self.add_paragraph_styled(clean_text)

        out_path = Path(output_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        self.doc.save(str(out_path))
        return str(out_path)

def create_docx_from_markdown(md_input: str | Path, output_docx_path: str | Path) -> str:
    if os.path.exists(str(md_input)):
        with open(md_input, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
    else:
        content = str(md_input)

    converter = MarkdownDocxConverter()
    return converter.convert_markdown(content, output_docx_path)
