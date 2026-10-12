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
9. **Project-Grounded Drafting**:
   - `--project-dir` loads protocol, results, and discussion notes (Markdown) from a local project folder and treats them as the authoritative source — no invented data, references, or protocol details. With `--type thesis`, this focuses generation on the Discussion and References chapters (inverted-funnel structure with required ending headers).
10. **Post-Humanization Re-Verification**:
   - After the optional humanization pass, the full draft's references are re-validated live, since humanization can alter citation formatting.

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

# Install Node dependencies, compile the browser engine, and download Chromium
npm run setup
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

# Source-grounded thesis Discussion generation from project files
python main.py --topic "Hibiscus extract on periodontal healing" --type thesis --project-dir ./projects/BioGap_G2_Hibiscus
```

`--project-dir` points at a folder of Markdown materials (protocol, results, notes); when omitted but `--pdf-input` is given, the PDF's parent folder is auto-detected as the project directory.

### Research Surfer CLI (`refs`)

The `research-surfer` skill (`meddraft_ai/prompts/research_surfer/`) wraps the same search orchestrator and browser engine behind a standalone CLI. All commands run from the repo root:

```bash
# Combined API + stealth-browser deep search (PubMed, ScienceDirect, Scholar, CrossRef, Semantic Scholar, Europe PMC)
python -m meddraft_ai refs deep-search "your query string" --limit 5

# Google Scholar direct browser search (Playwright stealth)
python -m meddraft_ai refs scholar-search "your query string" --limit 5

# Paper deep dive: abstract, open-access status, PMCID, PDF link
python -m meddraft_ai refs deep-dive "10.1038/nature12373"   # DOI, PMID, or JSON

# Download an open-access PDF to outputs/downloaded_papers/
python -m meddraft_ai refs download "{\"title\": \"Paper Title\", \"pdf_url\": \"https://example.com/paper.pdf\"}"

# Trace nested/secondary citations in a PDF or excerpt to root sources (dual attribution)
python -m meddraft_ai refs secondary-cite ./sample_paper.pdf --style Harvard
python -m meddraft_ai refs secondary-cite "GLUT4 translocation is blunted [28]. References 28. Roden M, et al. J Clin Invest. 1996;97:2859-65." --markdown

# Filtered ClinicalTrials.gov search + full record by NCT ID
python -m meddraft_ai refs trials-search --condition "multiple sclerosis" --phase "Phase 3" --status Recruiting --limit 5
python -m meddraft_ai refs trials-get NCT04368728

# Draft structured Scholar search angles for a topic (search playbook)
python -m meddraft_ai refs plan-angles "SGLT2 inhibitors renal outcomes"
```

Low-level DOM navigation (mapped `data-agent-id`) is available through the compiled browser engine directly:

```bash
node meddraft_ai/search/browser_engine/dist/cli.js navigate <url>
node meddraft_ai/search/browser_engine/dist/cli.js click <url> <id>
```

---

## 🧠 Agent Skills & Prompt Packs

The repo carries two skill layers, both wired into the project's "brain":

**Agent skills (`.agents/skills/`)** — quality gates and compliance guides applied to AI-assisted work in this repository. They are pinned in `skills-lock.json` (the `npx skills` lockfile format), and `tests/test_skills_lock.py` verifies every installed skill directory has a matching lock entry:

| Skill | Role |
|---|---|
| `clean-code-guard` | Reactive review of generated/changed production code (Clean Code, SOLID, DRY, KISS, YAGNI, LLM failure modes) |
| `test-guard` | Reactive review of generated/changed test code |
| `docs-guard` | Reactive review of generated/changed documentation |
| `thesis-master-guide` | Cairo University Faculty of Dentistry Master Thesis formatting and content guide (27-component order, margins, spacing, reference style) |
| `secondary-citation-extractor` | Nested/secondary citation tracing: distinguishes container vs root authors, maps in-text keys to the bibliography, verifies via Crossref/PubMed/Scholar, emits dual `as cited in` attribution |
| `medical-clinicaltrials` | Filtered ClinicalTrials.gov search (condition/intervention/phase/status) + full NCT-ID records for evidence tables and recruitment tracking (no API key) |
| `citation-integrity` | Numbered sequential citations, academic-sources-only rule, and QA checklist for literature reviews and methodology sections |
| `academic-search-agent` | Three-phase Scholar playbook: breadth angles → authoritative deep-reads → single-question iteration with word budgets |
| `wp-guard` / `woo-guard` | WordPress / WooCommerce code review gates (kept from the shared guard-skills toolkit) |

**Automatic routing:** `SkillRegistry.match_skill_for_task()` calls out skills automatically whenever the task text carries their signals (`as cited in` → `secondary-citation-extractor`; trial/phase/NCT language → `medical-clinicaltrials`; literature-review/numbered-citation language → `citation-integrity`; background/timeline/research-log language → `academic-search-agent`). The pipeline likewise auto-runs them: `main.py` Phase 1 adds a bounded ClinicalTrials.gov lookup for clinical topics and Phase 2b traces secondary citations from any `--pdf-input`; `ExtractionEngine` attaches `secondary_citations` whenever markers are detected. `TrialsSpecialist` / `SecondaryCitationSpecialist` (`meddraft_ai/agents/specialists.py`) carry the skill contexts for LLM-grounded work, while `citation-integrity` feeds `CoreWriter`/`ProofReader` and `academic-search-agent` feeds `DeepResearchSpecialist`.

**Pipeline prompt packs (`meddraft_ai/prompts/`)** — domain prompts indexed at runtime by the `SkillRegistry` (`meddraft_ai/core/skill_registry.py`). Newly added packs must be listed in `REGISTERED_PROMPT_SUBDIRS` (registration is enforced by `tests/test_skill_registry.py`):

`academic-writing` · `academic_research_skills` · `academic-search-agent` · `citation-integrity` · `claude_scientific_writer` · `docx` · `doi_reference_validator` · `humanizer-main` · `humanizer_noora` · `language-refinement` · `medical-clinicaltrials` · `medical_research_skills` · `med_paper_assistant` · `pdf` · `research_surfer` · `sciwrite` · `secondary-citation-extractor` · `thesis-discussion-writer`

Root-level rule files in `meddraft_ai/prompts/` (`Thesis_guide.md` — the pipeline mirror of the `thesis-master-guide` agent skill — plus `apa_reporting.md`, `agent_instructions.md`, `document_formatting.md`, `humanizer_general.md`, `proofreading.md`) are indexed automatically.

**Evaluated but not integrated** (additive-only policy respected; reasons recorded): `kesslerio/academic-deep-research` is already covered by the repo's local `academic-deep-research` skill + `DeepResearchSpecialist`; `dayunyan/academic-writer` was rejected (VirusTotal Suspicious flag, requires 4–7 GB texlive + Linux + an external hub skill, while Pandoc/DOCX export already covers output); `nimhar/aclawdemy` was rejected (VirusTotal Suspicious, external agent-publishing platform with API registration — conflicts with the zero-hallucination clinical posture); `huaruoji/research-report` was rejected (VirusTotal + OpenClaw Suspicious flags, texlive/conda/CUDA requirements, overlaps the existing export + 5-pass SciWrite audit).

---

## 🧪 Testing

```bash
pytest tests/ -v

# Windows Python 3.12 known issue (see tests/conftest.py): a pypdfium2 native
# crash at collection time — pytest recovers, but it can be suppressed via:
pytest tests/ -v --ignore=tests/test_pdf.py
```

---

## 🏛️ Repository Architecture

```
D:\GitHub\MedDraft_AI\
├── main.py                     # CLI entry point — multi-phase manuscript pipeline
├── meddraft_ai/
│   ├── core/                   # Configuration, LLM client, provider routing, SkillRegistry
│   ├── search/                 # PubMed, ScienceDirect, Scholar, Europe PMC, stealth browser engine
│   ├── extraction/             # PDF reading, Docling extraction, citation anchoring
│   ├── screening/              # RIS/CSV parser, deduplication, screeners, PRISMA flow
│   ├── agents/                 # CoreWriter, Humanizer, Verifier, ProofReader, MedicalWriter
│   ├── validation/             # Live CrossRef & PubMed reference verification
│   ├── export/                 # DOCX converter, Pandoc pipeline, journal formatters
│   ├── prompts/                # Prompt & skill packs (registered in core/skill_registry.py)
│   └── templates/              # APA statistical reporting templates
├── .agents/skills/             # Agent skills: guard skills + thesis-master-guide
├── skills-lock.json            # Pin file for .agents/skills (npx skills lockfile)
├── tests/                      # Pytest suite (skill registry, lock, search, PDF, export, validation)
├── projects/                   # Local research projects for --project-dir (gitignored)
├── outputs/                    # Generated manuscripts, downloads, scratch runs (gitignored)
├── ARCHITECTURE.md             # Pipeline and provider routing diagrams
├── CONTRIBUTING.md             # Code style, test, and PR process
├── PLUG_AND_PLAY_PROMPTS.md    # Ready-to-use prompt recipes (.docx twin available)
├── requirements.txt            # Python dependencies
├── package.json                # Node / Playwright dependencies (browser engine)
└── .env.example                # Configuration template
```

---

## 📜 License

Distributed under the MIT License. See `LICENSE` for more information.
