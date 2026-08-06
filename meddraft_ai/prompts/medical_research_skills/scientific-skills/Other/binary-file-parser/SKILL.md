---
name: binary-file-parser
description: Automatically detect and parse binary files (e.g. PDF, DOCX, XLSX, PPTX, RTF) that are incorrectly named with standard text extensions (like .md or .txt) and convert them back into readable Markdown.
license: MIT
author: AIPOCH
---

# Binary File Parser & Auto-Recovery Skill

## Validation Shortcut

Run this minimal command first to verify the supported execution path:

```bash
python medical-research-skills-main/scientific-skills/Other/binary-file-parser/scripts/parse_binary_file.py --help
```

## When to Use

- When you receive or encounter a file (e.g. `extracted_study2.md`) that raises parsing/viewing errors due to it containing binary content (such as a PDF or Microsoft Word Document renamed with a `.md` extension).
- When a task requires reading a file but standard tool actions report: "I am unable to parse X because it is a binary file (not a standard text or Markdown format), and my tools cannot read it."
- When you want to convert standard Office documents (`.docx`, `.xlsx`, `.pptx`, `.rtf`) or PDFs into clean Markdown formatting for downstream text generation or parsing.

## Key Features

- **Automated Signature (Magic Number) Detection**: Inspects the raw byte stream of input files to determine their true type, bypassing file extension lies (e.g., identifies a PDF file even if named `.md`).
- **Supports Multiple Engines**: 
  - Primary: `markitdown` (Microsoft's comprehensive converter).
  - Fallback: `pdfplumber` (for PDF text layout recovery) and `python-docx` (for Word documents).
- **In-Place Recovery**: Supports overwriting/repairing the misnamed file directly with the converted Markdown text.

## Dependencies

- Python 3.10+
- `markitdown` (primary converter)
- `pdfplumber` (PDF layout fallback)
- `python-docx` (Word fallback)

## Example Usage

### 1) Recover a misnamed binary file in-place (overwriting it with actual Markdown text)
```bash
python medical-research-skills-main/scientific-skills/Other/binary-file-parser/scripts/parse_binary_file.py --input extracted_study2.md --overwrite
```

### 2) Convert a binary file to a new Markdown output file
```bash
python medical-research-skills-main/scientific-skills/Other/binary-file-parser/scripts/parse_binary_file.py --input raw_document.pdf --output document_content.md
```

## Implementation Details

- **True Format Checking**: Uses `detect_file_type()` to read the first 2048 bytes of the file and matches common headers:
  - `%PDF` -> `pdf`
  - `PK\x03\x04` -> ZIP container (checks ZIP structure for subfiles like `word/` to identify `docx`, `xl/` for `xlsx`, or `ppt/` for `pptx`).
  - `{\rtf` -> `rtf`
- **Temporary Copy Parsing**: Creates a temporary copy of the file using its *true extension* so that conversion engines (`markitdown` or other standard utilities) can parse it properly without extension conflicts.
- **Robust Fallback**: If the primary conversion engine raises an exception, the system uses layout/text parsers like `pdfplumber` or `docx` sequentially.

## Required Inputs

- `--input`: Path to the input file to inspect and parse.

## Recommended Workflow

1. Validate whether the input file exists and is indeed reported or suspected to be a binary file.
2. Run the parser script passing the input path.
3. If repair is required for an existing task flow, use the `--overwrite` flag to replace the problematic file with its Markdown representation.
4. Verify the output file size and structure to ensure it is readable plain text.

## Output Contract

- Returns a UTF-8 encoded text/Markdown file containing the extracted text and formatting (headings, tables, and paragraphs).
- Displays success log indicating: true format type detected, the engine used, and final destination path.

## Validation and Safety Rules

- Do not read binary files using standard text readers without validating their encoding or signature.
- Ensure temporary files are cleaned up after parsing is complete.
- Verify that standard UTF-8 encoding is used to save the recovered Markdown text.
