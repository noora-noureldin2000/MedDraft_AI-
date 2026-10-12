---
name: academic-search-agent
description: Structured three-phase Scholar search playbook — breadth search across 3-5 angles, authoritative deep-reads, and single-question focused iteration until the log supports a fully cited report. Use when compiling background literature, verifying coverage of a model or product, building a timeline of key papers, or generating a cited reference list on a narrow topic. Adapted from teamolab/call-academic-search-agent (ClawHub) to MedDraft_AI's ResearchOrchestrator tooling.
---

# Academic Search Agent Playbook

An agentic workflow for structured academic literature search. It replaces the manual loop of searching, reading, and note-taking with parallel searches, deep-reads of authoritative sources, and a cited report in one disciplined pass.

## When to Use

- Compiling background literature for a thesis or research proposal.
- Verifying whether a named model, product, or intervention has published academic coverage.
- Building a timeline of key papers in a technical or clinical field.
- Researching a new technique before a presentation or protocol.
- Generating a cited reference list on a narrow scientific topic.

## Golden Rules (highest priority, override all else)

1. **User input is the absolute first fact.** Never "correct" a term, product name, or version number because it is absent from internal knowledge. Assume the user is correct and the knowledge is outdated — verify the exact string first, then research around it unmodified.
2. **Cost-effectiveness and progress supreme.** Every step must advance the task. For any independent sub-goal, if **2 consecutive attempts** (different strategies) yield no effective progress, mark it `[Blocked]`, record the reason plus alternative leads, and move on. More than 2 invalid attempts on one sub-goal is task failure. Hard budgets: research log ≤ 5000 words, final report ≤ 5000 words; stop new collection once the log reaches ~4000 words (see `meddraft_ai.search.search_planner` constants and `truncate_to_budget`).
3. **Academic honesty.** Quoted text in double quotes must be **verbatim** from a fully read source. Any quoted words not present in the original are major misconduct and total task failure.

## Core Principles

1. **Tool truth wins.** Real-time results from `ResearchOrchestrator` (deep_search, scholar-stealth, deep-dive, trials) outrank internal knowledge on every conflict.
2. **Embrace the unknown.** Unknown concepts are assumed real and investigated immediately.
3. **Efficiency.** No redundant calls; never re-fetch the same URL.
4. **Scope focus.** All actions serve the original request; on drift, stop and refocus.
5. **Report language.** User's explicit language choice first; otherwise the user's input language. Never infer from prompt or source language.
6. **Scholar priority.** Prefer Google Scholar (`refs scholar-search`) for discovery; fall back to PubMed/Crossref/Semantic Scholar/Europe PMC via `refs deep-search`.

## Tool Mapping (MedDraft_AI equivalents)

| Playbook action | MedDraft_AI equivalent |
|---|---|
| Plan 3–5 search angles | `refs plan-angles "topic"` / `search_planner.plan_search_angles()` |
| Parallel breadth search | `refs deep-search` + `refs scholar-search` per angle |
| Deep-read ≤ 4 authoritative URLs | `refs deep-dive` (+ `refs download` for OA PDFs) |
| Focused single-question iteration | One precise `deep-search`/`scholar-search` per loop |
| Inline citations + numbered references | `citation-integrity` skill conventions |
| Trial enrichment | `medical-clinicaltrials` skill (`refs trials-search`) |

## Workflow

### Phase 1 — Setup and breadth search

1. **Formulate a plan** of 3–5 core angles (e.g., `"X review"`, `"X timeline key papers"`, `"seminal papers on X"`, `"X recent advances"`, `"X methods comparison"`).
2. **Open a research log** (working notes with titles, abstracts, URLs per angle).
3. **Execute breadth search in parallel** — one `deep-search`/`scholar-search` per angle; log titles, abstracts, URLs.
4. **First deep-read round** — evaluate authority (guidelines/official > PubMed/arXiv > top venues > media > blogs/forums); read at most 4 top URLs via `deep-dive`; log key facts (numbers, dates, parameters) with source URLs.

### Phase 2 — Focused iteration (one question at a time)

5. **Integrate and ask one next question.** Review the log against the original request and state exactly one most-important clarifying question (e.g., "The log shows DDPM (2020) is the key node — what was the first major clinical follow-up?").
6. **Research that single question** with 1–2 focused queries; deep-read 1–2 top hits; append to the log.
7. **Loop to step 5** until the log supports a complete report — or the 4000-word stop rule fires.

### Phase 3 — Report synthesis

8. **Write the final report in one pass** with this outline: Abstract → Background → Core Findings (subsections as needed) → Conclusion → References. Every key claim carries an inline source citation; all cited URLs appear as a numbered reference list. Distill and compress — never paste raw source text except inside verbatim quotes.

## Gotchas & Edge Cases

- **Blocked sub-goals are data, not failure** — log them with reasons and alternatives.
- **Authority ordering matters for clinical topics:** guidelines and registered trials outrank preprints; verify trial claims via `medical-clinicaltrials`, then trace nested citations via `secondary-citation-extractor`.
- **Word budgets are hard limits**, enforced by `search_planner.truncate_to_budget` — check `should_stop_collecting` before each new collection round.
