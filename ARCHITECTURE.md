# MedDraft_AI — Architecture Specification

## System Overview

MedDraft_AI is structured as a multi-phase pipeline orchestrated by `main.py`:

```mermaid
graph TD
    A[User Request / CLI Topic] --> B[Phase 1: Multi-Database Literature Search]
    B --> C[Phase 2: Screening & Deduplication]
    C --> D[Phase 3: Source-Anchored PDF Extraction]
    D --> E[Phase 4: Section-by-Section IMRAD Drafting]
    E --> F[Phase 5: 5-Pass SciWrite Prose Audit]
    F --> G[Phase 6: Live Reference API Verification]
    G --> H{Humanize Flag Enabled?}
    H -- Yes --> I[On-Demand Humanization Final Pass]
    H -- No --> J[Phase 8: Document Export MD + DOCX]
    I --> J
```

## Provider Routing Architecture

MedDraft_AI supports two execution pathways for language models:

```mermaid
graph LR
    A[LLM Query] --> B{LLM_PROVIDER setting}
    B -- simple --> C[OpenAI-Compatible Endpoint: Claude / OpenAI / Gemini]
    B -- dual --> D{Is Vision Task?}
    D -- No --> E[DeepSeek V4 Flash via OpenCode Proxy]
    D -- Yes --> F[Qwen 2.5 VL via Local Ollama]
```

## Module Structure

- `meddraft_ai.core`: Configuration management, LLM interface, provider routing, and the `SkillRegistry` that indexes prompt packs. `SkillRegistry.match_skill_for_task()` auto-routes task text to the most relevant skill (notably `secondary-citation-extractor` on `as cited in` / nested-citation signals); `get_skill_with_auto_routing()` falls back to routing when an exact name lookup fails.
- `meddraft_ai.search`: Multi-database APIs and Playwright stealth browser engine for Google Scholar. Hosts `clinicaltrials.py` (filtered ClinicalTrials.gov v2 search + NCT-ID lookup, no key) and `search_planner.py` (offline search-angle planner, word budgets, stalemate guard).
- `meddraft_ai.extraction`: Docling-based text/table extraction, PDF reading, page-level citation anchoring, plus `secondary_citation.SecondaryCitationExtractor` (4-step container→trace→verify→dual-attribution pipeline, auto-triggered by `ExtractionEngine` and `main.py` Phase 2b).
- `meddraft_ai.screening`: PICO abstract/fulltext screening, RIS/CSV parsing, PRISMA flow diagrams.
- `meddraft_ai.agents`: CoreWriter, Humanizer, VerifierAndStats, ProofReader, MedicalWriterAgent, plus `SecondaryCitationSpecialist` (carries the secondary-citation-extractor skill context for LLM-grounded tracing), `TrialsSpecialist` (ClinicalTrials.gov context), and `RebuttalSpecialist` (reviewer-response workflow context). `citation-integrity` and `surgical-word-reduction` feed CoreWriter/ProofReader; `academic-search-agent` feeds DeepResearchSpecialist; `medical-clinicaltrials` feeds ReferencesSpecialist. The 20 vendored Nature Paper Skills feed their assigned specialists by `<name>/SKILL.md` file path, and `load_context()` additionally preloads the query-relevant ones first (query-aware preload; neutral queries are byte-identical to before).
- `meddraft_ai.validation`: Live CrossRef and PubMed reference verification.
- `meddraft_ai.export`: Python-docx and Pandoc Markdown-to-DOCX conversion with publisher styles.

## Skill & Prompt Registry

Two skill layers feed the system:

- **Pipeline prompt packs** live in `meddraft_ai/prompts/`. The `SkillRegistry` (`meddraft_ai/core/skill_registry.py`) indexes every `.md`/`.txt` file at runtime; a new pack only needs its folder name added to `REGISTERED_PROMPT_SUBDIRS` in that module. `secondary-citation-extractor/` is registered there and additionally wired for automatic invocation via `AUTO_ROUTE_KEYWORDS` + `match_skill_for_task()`. Same pattern now covers `medical-clinicaltrials/`, `citation-integrity/`, `academic-search-agent/`, `surgical-word-reduction/`, and the 20-pack Nature Paper Skills layer (`meddraft_ai/core/nature_integration.py` + `match_skill_for_task()` chain hook; manifest at `meddraft_ai/prompts/nature-paper-skills/`).
- **Agent skills** live in `.agents/skills/` (guard skills for code/test/docs review plus the `thesis-master-guide` compliance skill and the `secondary-citation-extractor` tracing skill). They are pinned in `skills-lock.json` (`npx skills` lockfile format); `tests/test_skills_lock.py` enforces that every installed skill directory has a lock entry.
