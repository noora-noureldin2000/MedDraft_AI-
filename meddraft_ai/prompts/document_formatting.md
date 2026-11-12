---
name: document-formatting-skill
description: "Instructions for styling Markdown manuscripts and exporting them to APA/AMA-compliant Microsoft Word (.docx) files using the repo's python-docx and Pandoc converters."
license: MIT

---

# Stylistic Document Formatting Skill Guide

This skill defines the workflow for turning a finished Markdown manuscript into a
styled `.docx` using the converters that actually ship in this repo:

- `meddraft_ai/export/pandoc_converter.py` — Pandoc first, python-docx fallback.
- `meddraft_ai/export/create_docx.py` — `MarkdownDocxConverter` (Times New Roman
  12 pt, double spacing, inline bold/italic, headings, tables).

Draft in Markdown, export last. Do not hand-edit OOXML.

---

## 1. Export Workflow

`main.py` already runs this in Phase 8 (`--output-format both|docx`). To export an
existing Markdown file:

```bash
python -c "from meddraft_ai.export import convert_markdown_to_docx as c; print(c('outputs/draft.md', 'outputs/draft.docx'))"
```

`convert_markdown_to_docx()` invokes `pandoc <md> -o <docx>` when Pandoc is on
PATH; otherwise it falls back to `MarkdownDocxConverter`, which applies the
manuscript style programmatically.

### Style rules applied by the native fallback

| Element | Rule |
| :--- | :--- |
| Body text | Times New Roman 12 pt, double spaced, 0 pt before/after |
| Headings | Bold, black (no theme blue), same family |
| Inline markup | `**bold**` and `*italic*` parsed into separate runs |
| Tables | Standard Markdown tables converted to Word tables |
| References | Plain text list; validate with the 5-tier checker (below) |

Publisher-specific DOCX templates (MDPI/Elsevier page geometry, three-line
tables, Zotero field codes) are **not** bundled in this repo. If a submission
needs them, apply the journal's own template in Word after export, or supply a
custom Pandoc `--reference-doc`.

---

## 2. Best Practices for the Agent

* **Always draft in Markdown first.** It prevents raw XML manipulation errors and is much faster.
* Use **Heading 1 (`#`)** for main sections (e.g., Introduction, Methods) and **Heading 2 (`##`)** for subsections.
* Keep tables as standard Markdown tables so the converter can map them to Word tables.
* For references, use simple `[1]`, `[2]` bracket notation in Markdown. Validate the
  extracted DOIs/PMIDs before export:

  ```bash
  python -m meddraft_ai.validation.reference_validator "outputs/draft.md" --format all --output outputs/ref_report.json
  ```

* Verification is live: only `status == "verified"` or `"partial_match"` records may
  enter the final bibliography; `not_found` entries are treated as hallucinated and
  must be removed or replaced.
* Run `submission-audit` + `citation-verifier` on the exported draft as the
  pre-submission gate.
