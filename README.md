# MedDraft_AI 🩺🤖

**Production-Ready Standalone AI Medical Research Writing Platform**

`MedDraft_AI` is an autonomous local-first pipeline designed exclusively for academic medical research writing — manuscripts, theses, dissertations, systematic reviews, narrative reviews, scoping reviews, meta-analyses, protocols, and clinical reports.

Derived from the `Mega_Medical_writer_Noora` architecture, `MedDraft_AI` automates deep literature retrieval, source-anchored PDF extraction, IMRAD drafting, live DOI reference validation, APA/AMA style formatting, and on-demand AI-text humanization. It also ships an agent-ready **Google Images search tool** that chains SerpApi and Brave with a Playwright fallback, so visual references (figures, anatomy, histology, devices) are available without burning a single provider's quota.

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
   - Every run writes `reference_verification_report.json` and lists any DOI that no API confirmed, so hallucinated or unreachable references are visible before submission instead of being counted and discarded.

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
11. **Google Images Search with Free-Tier Fallback**:
   - `refs image-search` chains **SerpApi → Brave → Playwright**, skips exhausted free tiers through a local quota ledger, and returns compact `{title, image_url, thumbnail_url, context_url}` results for LLM context windows.
   - Google Custom Search JSON API remains supported as a **legacy** provider for grandfathered projects, but Google closed it to new customers and existing access ends 2027-01-01.
   - Includes keyword relevance scoring (`--require-term`, `--exclude-term`, `--prefer-host`), `![Title](image_url)` rendering, an OpenAI-style tool schema plus dispatcher for agent binding, and optional browser screenshot capture for vision models.
   - See [Google Images Search with Free-Tier Fallback](#google-images-search-with-free-tier-fallback).

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

# Google Images search (optional; any configured subset works)
SERP_API_KEY=your_serpapi_key
GOOGLE_CSE_API_KEY=your_google_cloud_key
GOOGLE_CSE_ID=your_search_engine_id
BRAVE_API_KEY=your_brave_key
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

# Source-grounded SR/MA Discussion + deterministic skill gate
python main.py --topic "Triple therapy in uncontrolled hypertension" --type systematic-review \
  --project-dir ./projects/triple-therapy --sr-require "MSSBP week 8" --sr-require "serious adverse events" --humanize

# Zero-hallucination structured extraction of a single study PDF
# → auditable JSON (every field: value + verbatim quote + page + verification status)
# → highlighted proof PDF with all verified quotes marked
python main.py --parse-pdf ./sample_paper.pdf --out ./outputs/sample_extraction.json --annotated-pdf ./outputs/sample_annotated.pdf
```

The `--parse-pdf` flow runs the full 4-pass pipeline with no truncation: Docling conversion → IMRaD semantic chunking → Methods / Results+Tables / Discussion extraction (each verified verbatim against source with numeric-fidelity checks and self-correction retries) → verified cross-section audit. Fields absent from the source are emitted as `NOT_REPORTED`, never invented.

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

### Google Images Search with Free-Tier Fallback

`refs image-search` answers visual reference requests (figures, anatomy, histology, devices) by chaining SerpApi → Brave → Playwright. It stops as soon as the requested number of unique images is filled, and a local ledger skips any provider whose free tier is used up. Google Custom Search JSON API remains supported as a legacy provider for grandfathered projects.

| Order | Provider | Free tier | Credentials |
| --- | --- | --- | --- |
| 1 | SerpApi Google Images | 100 searches/month | `SERP_API_KEY` |
| 2 | Brave Images API | 2,000 queries/month | `BRAVE_API_KEY` |
| 3 | Playwright Google Images | No API quota | Node.js + built browser engine |
| Legacy | Google Custom Search JSON API | 100 queries/day, grandfathered projects only | `GOOGLE_CSE_API_KEY` + `GOOGLE_CSE_ID` |

> **Google CSE status:** Google closed the Custom Search JSON API to new customers, and existing access ends on **2027-01-01**. A new project receives `403 Permission denied on the service` even with the API enabled, a valid key, and a valid `cx`. Add `google_cse` to `IMAGE_SEARCH_PROVIDER_ORDER` only if the project already had access before the closure.

```bash
# Show which providers are configured and how much local free-tier quota is left
python -m meddraft_ai refs image-providers
# "credentials set" means present, not validated; run one search to confirm the key/API enablement.

# Search and render Markdown images for a chat client
python -m meddraft_ai refs image-search "gingival sulcus histology" --limit 3 --markdown

# Relevance scoring: require a term, drop clipart, prefer an authoritative host
python -m meddraft_ai refs image-search "alveolar bone radiograph" \
  --require-term radiograph --exclude-term clipart --prefer-host ncbi.nlm.nih.gov

# Force one provider, or force the no-key browser fallback with a screenshot
python -m meddraft_ai refs image-search "suture techniques" --provider-order brave --no-fallback
python -m meddraft_ai refs image-search "suture techniques" --provider-order browser --screenshot

# Legacy only: explicitly re-enable Google CSE for a grandfathered project
python -m meddraft_ai refs image-search "suture techniques" \
  --provider-order serpapi,google_cse,brave,browser
```

Setup:

- **SerpApi:** create an account and copy the private API key into `SERP_API_KEY`.
- **Brave:** subscribe to the free Search plan and put the key in `BRAVE_API_KEY`.
- **Google CSE (legacy only):** create a Programmable Search Engine, enable **Image search** and **Search the entire web**, copy the Search Engine ID into `GOOGLE_CSE_ID`, then enable the **Custom Search API** and create an API key in the same Cloud project. New projects are not entitled and will receive `403 Permission denied on the service`; use SerpApi or Brave instead.
- **Browser fallback:** run `npm install && npm run build` in `meddraft_ai/search/browser_engine/`. Google may present a CAPTCHA; with the default `BROWSER_HEADLESS=false` the window opens so it can be solved manually.

The quota ledger lives at `.cache/image_search_quota.json` (gitignored). It records successes, daily/monthly rollovers, and short 429 cooldowns. It is best-effort: it cannot see usage from other machines or other tools sharing a key, so the provider's own dashboard remains authoritative.

Agent binding: register `get_image_search_tool_schema()` in the model's `tools` list. The schema exposes `query`, `num_results`, `safe_search`, `required_terms`, and `exclude_terms`. Dispatch the model's arguments with `execute_image_search_tool(arguments)`; no manual translation is needed. Returned results are deliberately small (`title`, `image_url`, `thumbnail_url`, `context_url`, `width`, `height`, `provider`). Tell the model to render them as `![Title](image_url)`; `render_markdown(envelope)` does it directly. `image_url` can be passed straight to a multimodal model that accepts URLs, while `--screenshot` gives a local PNG for vision clients that require a file path.

### Systematic-Review Discussion CLI (`sr`)

The `systematic-review-discussion` skill exposes its deterministic gates as a standalone CLI:

```bash
# List and classify every file in the protocol / included / meta / prior-review folders
python -m meddraft_ai sr inventory "./projects/triple-therapy" --json

# Gate a drafted Discussion (exit 1 on error-severity findings)
python -m meddraft_ai sr audit "./projects/triple-therapy/Discussion_Draft.md" \
  --require "MSSBP week 8" --require "BP control rate" --require "serious adverse events"

# Confirm every quantitative token exists in the evidence files
python -m meddraft_ai sr fidelity --draft "./projects/triple-therapy/Discussion_Draft.md" \
  --source "./projects/triple-therapy/meta" --source "./projects/triple-therapy/included studies"

# Render the plug-and-play system command from a JSON study spec
python -m meddraft_ai sr brief --spec "./projects/triple-therapy/study_spec.json" --out "./projects/triple-therapy/discussion_brief.md"
```

Low-level DOM navigation (mapped `data-agent-id`) is available through the compiled browser engine directly:

```bash
node meddraft_ai/search/browser_engine/dist/cli.js navigate <url>
node meddraft_ai/search/browser_engine/dist/cli.js click <url> <id>
```

---

## 🧠 Agent Skills & Prompt Packs

Three skill layers are wired into the pipeline:

**Agent skills (`.agents/skills/`)** — quality gates and compliance guides applied to AI-assisted work in this repository. They are pinned in `skills-lock.json` (the `npx skills` lockfile format), and `tests/test_skills_lock.py` verifies every installed skill directory has a matching lock entry:

| Skill | Role |
|---|---|
| `clean-code-guard` | Reactive review of generated/changed production code (Clean Code, SOLID, DRY, KISS, YAGNI, LLM failure modes) |
| `test-guard` | Reactive review of generated/changed test code |
| `docs-guard` | Reactive review of generated/changed documentation |
| `thesis-master-guide` | Cairo University Faculty of Dentistry Master Thesis formatting and content guide (27-component order, margins, spacing, reference style) |
| `systematic-review-discussion` | SR/MA Discussion architect: zero-omission outcome coverage, RCI interpretation, GRADE-calibrated certainty, two-tier limitations, and a deterministic audit + numeric-fidelity CLI (mirrored in `meddraft_ai/prompts/`) |
| `secondary-citation-extractor` | Nested/secondary citation tracing: distinguishes container vs root authors, maps in-text keys to the bibliography, verifies via Crossref/PubMed/Scholar, emits dual `as cited in` attribution |
| `medical-clinicaltrials` | Filtered ClinicalTrials.gov search (condition/intervention/phase/status) + full NCT-ID records for evidence tables and recruitment tracking (no API key) |
| `citation-integrity` | Numbered sequential citations, academic-sources-only rule, and QA checklist for literature reviews and methodology sections |
| `surgical-word-reduction` | 3-pass surgical word-count reduction (structural trim → syntactic tightening → micro-polish) with section protocols, replacement dictionary, and preservation checklist |
| `academic-search-agent` | Three-phase Scholar playbook: breadth angles → authoritative deep-reads → single-question iteration with word budgets |
| `pdf` | PDF toolkit: layout-aware text/table extraction, scanned-PDF OCR fallback, merge/split/rotate/metadata, and fillable or annotation-based form filling (mirrored in `meddraft_ai/prompts/pdf/`) |
| `pptx` | Deck builder: 16:9 native-shape design engine (blueprint → `.pptx`) plus quota-aware figure sourcing through the SerpApi → Brave → Playwright image chain (legacy Google CSE opt-in; mirrored in `meddraft_ai/prompts/pptx/`) |

**Nature Paper Skills layer (20 skills)** — manuscript integrity, revision, and submission skills from [Boom5426/Nature-Paper-Skills](https://github.com/Boom5426/Nature-Paper-Skills) (upstream v0.2.0; MIT + Apache-2.0, see `meddraft_ai/prompts/nature-paper-skills/`). Wiring: `meddraft_ai/core/nature_integration.py`, auto-routed by `match_skill_for_task()`, carried by the existing specialists plus the new `RebuttalSpecialist`:

| Skills | Role |
|---|---|
| `claim-source-verification` | Semantic claim→source support check (validator proves a DOI *exists*; this proves the paper *says* it) |
| `stats-reporting-audit` | Reporting audit: independent-unit `n`, replication, multiple comparisons, legend stats |
| `submission-audit` | Pre-submission / resubmission preflight QA |
| `rebuttal-response` + `paper-reviewer` | Author-side point-by-point rebuttals + referee checklists with reply grading |
| `manuscript-optimizer` / `results-section-revision` | Structural + late-stage Results flow repair |
| `figure-planner` / `figure-style` | One-claim-per-figure design, legend sync, legibility checklist |
| `scientific-prose-style` / `anti-defensive-writing` / `write-scientific-manuscript` | Sentence lint, de-auditing, clarity/logic diagnosis |
| `data-availability` / `paper-bootstrap` / `draft-marker-discipline` | Data-sharing statements, project init, multi-session tracking |
| `review-article-architecture` | New article type: Reviews / surveys / Perspectives |
| `paper-analyzer` / `results-analysis` | Single-paper deep notes; experiment-outputs → findings bridge |
| `citation-verifier` | Offline `.bib` hygiene complementing live-API validation |
| `nature-portfolio-playbook` | Venue fit + policy preflight (Nature / Methods / Biotech) |

**Automatic routing:** `SkillRegistry.match_skill_for_task()` calls out skills automatically whenever the task text carries their signals (`as cited in` → `secondary-citation-extractor`; trial/phase/NCT language → `medical-clinicaltrials`; mixed Arabic + Latin script, or Arabic/RTL + document wording → `arabic-mixed-rtl`; systematic-review/meta-analysis + Discussion language → `systematic-review-discussion`; literature-review/numbered-citation language → `citation-integrity`; reduce-word-count/word-limit/shorten-manuscript language → `surgical-word-reduction`; background/timeline/research-log language → `academic-search-agent`; PDF parsing/extraction/form language → `pdf`). Script detection lives in `meddraft_ai/core/language_routing.py`. The pipeline likewise auto-runs them: `main.py` Phase 1 adds a bounded ClinicalTrials.gov lookup for clinical topics, Phase 2b traces secondary citations from any `--pdf-input`, and Phase 4b audits a systematic-review/meta-analysis Discussion against the skill gates. `TrialsSpecialist` / `SecondaryCitationSpecialist` / `SystematicReviewDiscussionSpecialist` (`meddraft_ai/agents/specialists.py`) carry the skill contexts for LLM-grounded work, while `citation-integrity` and `surgical-word-reduction` feed `CoreWriter`/`ProofReader` and `academic-search-agent` feeds `DeepResearchSpecialist`.

**Pipeline prompt packs (`meddraft_ai/prompts/`)** — domain prompts indexed at runtime by the `SkillRegistry` (`meddraft_ai/core/skill_registry.py`). Newly added packs must be listed in `REGISTERED_PROMPT_SUBDIRS` (registration is enforced by `tests/test_skill_registry.py`):

`academic-writing` · `academic_research_skills` · `academic-search-agent` · `citation-integrity` · `surgical-word-reduction` · `claude_scientific_writer` · `docx` · `pptx` · `doi_reference_validator` · `humanizer-main` · `humanizer_noora` · `language-refinement` · `medical-clinicaltrials` · `medical_research_skills` · `med_paper_assistant` · `pdf` · `research_surfer` · `sciwrite` · `secondary-citation-extractor` · `thesis-discussion-writer` · `systematic-review-discussion` · `claim-source-verification` · `citation-verifier` · `stats-reporting-audit` · `submission-audit` · `rebuttal-response` · `paper-reviewer` · `manuscript-optimizer` · `results-section-revision` · `figure-planner` · `figure-style` · `scientific-prose-style` · `anti-defensive-writing` · `write-scientific-manuscript` · `data-availability` · `draft-marker-discipline` · `paper-bootstrap` · `review-article-architecture` · `paper-analyzer` · `results-analysis` · `nature-portfolio-playbook` · `nature-paper-skills` (manifest + section-contract references)

The `pptx` pack adds a 16:9 native-shape deck engine (blueprint JSON → editable `.pptx`) and quota-aware figure sourcing: `scripts/fetch_figures.py` fills figure slots through the SerpApi → Brave → Playwright chain (legacy Google CSE opt-in) and writes a provenance sidecar per image. It is described in `meddraft_ai/prompts/pptx/SKILL.md` and auto-routes on PowerPoint/slide-deck language.

Root-level rule files in `meddraft_ai/prompts/` (`Thesis_guide.md` — the pipeline mirror of the `thesis-master-guide` agent skill — plus `apa_reporting.md`, `agent_instructions.md`, `arabic-mixed-rtl.md`, `document_formatting.md`, `humanizer_general.md`, `proofreading.md`) are indexed automatically. `arabic-mixed-rtl.md` is a standalone skill selected by script detection rather than topic keywords: any request mixing Arabic and Latin letters, or naming Arabic/RTL formatting for a document, routes to it (see `meddraft_ai/core/language_routing.py` and `tests/test_skill_registry.py`).

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
│   ├── export/                 # DOCX converter (Pandoc + python-docx), APA/AMA styling
│   ├── prompts/                # Prompt & skill packs (registered in core/skill_registry.py)
│   └── templates/              # APA statistical reporting templates
├── .agents/skills/             # Agent skills: guard skills + thesis-master-guide
├── skills-lock.json            # Pin file for .agents/skills (npx skills lockfile)
├── tests/                      # Pytest suite (skill registry, lock, search, PDF, export, validation)
├── projects/                   # Local research projects for --project-dir (gitignored)
├── scratch/                    # Ad-hoc drafts and one-off scripts (gitignored)
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
