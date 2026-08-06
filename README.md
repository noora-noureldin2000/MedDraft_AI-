# MedDraft_AI 🩺🤖

**Production-Ready Standalone AI Medical Research Writing Platform**

`MedDraft_AI` is an autonomous local-first pipeline designed exclusively for academic medical research writing — manuscripts, theses, dissertations, systematic reviews, narrative reviews, scoping reviews, meta-analyses, protocols, and clinical reports.

Derived from the `Mega_Medical_writer_Noora` architecture, `MedDraft_AI` automates deep literature retrieval, source-anchored PDF extraction, IMRAD drafting, live DOI reference validation, APA/AMA style formatting, and on-demand AI-text humanization.

---

## 🌟 Core Features

1. **Multi-Database Academic Search**:
   - **Primary APIs**: PubMed (NCBI), ScienceDirect (Elsevier), Google Scholar (stealth browser engine).
   - **Secondary APIs**: CrossRef, Semantic Scholar, Europe PMC, ClinicalTrials.gov, DOAJ, FindPapers.
2. **Zero-Hallucination Evidence Extraction**:
   - Page-level citation anchoring via Docling and `pdfplumber`.
   - Annotation of citation anchor markers directly into PDF documents.
3. **IMRAD Section Drafting**:
   - Title, Abstract, Introduction, Literature Review, Methodology, Results, Discussion, Conclusion, Limitations, References.
4. **APA 7th Edition Results Narrative Writer**:
   - Takes raw pre-computed statistics JSON and writes publication-ready APA 7th narrative paragraphs and tables.
5. **Live Reference Verification**:
   - Real-time API validation against CrossRef and PubMed to verify DOIs, PMIDs, authors, titles, and publication dates.
6. **On-Demand Humanization Pass**:
   - Optional `--humanize` flag applies Dr. Noora Noureldin's writing style markers and anti-AI cliché rules as a final post-processing pass.
7. **Dual & Simple LLM Provider Support**:
   - **Simple Path**: Connect your Claude API key, OpenAI, Gemini, or DeepSeek via `.env`.
   - **Dual Path**: Route text tasks to DeepSeek V4 Flash and visual chart inspection to local Qwen 2.5 VL (via Ollama).
8. **Dual Output Formatting**:
   - Generates both clean Markdown (`.md`) and styled Microsoft Word (`.docx`) files with Times New Roman 12pt, double spacing, and APA table borders via Pandoc and `python-docx`.

---

## 🚀 Quick Start

### 1. Prerequisites
- Python 3.10+
- Node.js 18+ (for Playwright stealth browser engine)
- Optional: Pandoc (for advanced DOCX conversion)

### 2. Installation
```bash
# Clone or navigate to the repository
cd D:\GitHub\MedDraft_AI

# Install Python dependencies
pip install -r requirements.txt

# Install Node dependencies and Playwright browser engine
npm install
npx playwright install chromium
```

### 3. Configuration
Copy `.env.example` to `.env` and set your API keys:
```bash
cp .env.example .env
```

Edit `.env`:
```env
LLM_PROVIDER=simple
SIMPLE_API_KEY=sk-your-openai-or-claude-api-key
SIMPLE_MODEL=gpt-4o

# Academic APIs (Optional but recommended)
NCBI_API_KEY=your_ncbi_key
SCIENCEDIRECT_API_KEY=your_elsevier_key
```

---

## 💻 CLI Usage

```bash
# Basic Manuscript Generation
python main.py --topic "Impact of SGLT2 inhibitors on renal outcomes in T2D"

# Full Thesis Generation with On-Demand Humanization
python main.py --topic "Artificial intelligence in digital pathology" --type thesis --humanize

# Systematic Review with PDF Reference Ingestion
python main.py --topic "Telemedicine in rural cardiology" --type systematic-review --pdf-input ./sample_paper.pdf

# Specifying Output Formats and Search Depth
python main.py --topic "CAR-T cell therapy in refractory lymphoma" --search-depth 15 --output-format both
```

---

## 🏛️ Repository Architecture

```
D:\GitHub\MedDraft_AI\
├── meddraft_ai/
│   ├── core/           # Configuration, LLM client, Provider routing
│   ├── search/         # PubMed, ScienceDirect, Scholar, Europe PMC, Browser engine
│   ├── extraction/     # PDF reading, Docling extraction, citation anchoring
│   ├── screening/      # RIS/CSV parser, deduplication, PRISMA flow
│   ├── agents/         # CoreWriter, Humanizer, Verifier, ProofReader, MedicalWriter
│   ├── validation/     # Live CrossRef & PubMed reference verification
│   ├── export/         # DOCX converter, Pandoc pipeline, journal formatters
│   ├── prompts/        # IMRAD prompts, sciwrite, APA rules, style guides
│   └── templates/      # APA statistical reporting templates
├── main.py             # CLI entry point
├── requirements.txt    # Python dependencies
├── package.json        # Node / Playwright dependencies
└── .env.example        # Configuration template
```

---

## 📜 License

Distributed under the MIT License. See `LICENSE` for more information.
