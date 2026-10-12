# Nature Paper Skills — Additive Integration Layer (MedDraft_AI)

Vendored subset — **20 of 27 skills** — from
[Boom5426/Nature-Paper-Skills](https://github.com/Boom5426/Nature-Paper-Skills)
(upstream version in `UPSTREAM_VERSION.txt`; original licenses: MIT, plus
Apache-2.0 for `scientific-prose-style`, `stats-reporting-audit`, and
`figure-style` — see `LICENSE-APACHE` and `NOTICE`).

> **Additive only.** No existing skill, prompt pack, or specialist was removed
> or renamed. Each skill below is mirrored in two places, per this repo's
> convention: `.agents/skills/<name>/` (agent discovery, pinned in
> `skills-lock.json`) and `meddraft_ai/prompts/<name>/` (pipeline registry,
> listed in `REGISTERED_PROMPT_SUBDIRS`).

Wiring lives in `meddraft_ai/core/nature_integration.py` (skill→specialist map,
trigger patterns, pipeline chains) and is called automatically from
`SkillRegistry.match_skill_for_task()`.

## What was integrated and why

| Skill | Fills which gap in this repo |
|---|---|
| `claim-source-verification` | Semantic claim→source support check. `doi_reference_validator` proves a DOI exists; this proves the cited paper actually says what the sentence claims. |
| `stats-reporting-audit` | Reporting audit (independent-unit `n`, replication, multiple comparisons, legend stats). Complements `apa_reporting.md` results narration. |
| `submission-audit` | Pre-submission/pre-resubmission QA checklist. Previously missing. |
| `rebuttal-response` | Author-side point-by-point rebuttal letters. Carried by the new `RebuttalSpecialist`. |
| `paper-reviewer` | Nature-style referee checklist + reply grading. Pairs with `rebuttal-response`. |
| `manuscript-optimizer` | Claim-hierarchy / evidence-chain structural revision before sentence polish. |
| `results-section-revision` | Late-stage Results flow repair (subsection titles, bridges, paragraph openings). |
| `figure-planner` | One-claim-per-figure design, panel roles, legend↔text sync. Previously missing. |
| `figure-style` | Publication-grade figure legibility checklist + lightweight matplotlib helpers. |
| `scientific-prose-style` | Sentence-level lint (em-dash budget, hedging, AI tells + detection script). Complements `sciwrite` + humanizer passes. |
| `anti-defensive-writing` | Removes audit/defensive/self-critical voice while preserving numbers and scope conditions. |
| `write-scientific-manuscript` | Clarity/logic diagnosis layer (buried topics, referents, observation vs interpretation). |
| `data-availability` | Data-sharing statements, repository plans, source-data coverage. |
| `draft-marker-discipline` | Multi-session TODO-marker tracking, triage, safe archival. |
| `paper-bootstrap` | New-paper project init: source of truth, venue defaults. |
| `review-article-architecture` | Review / survey / Perspective architecture — new article type for this repo (narrative-review support beyond the existing systematic-review pipeline). |
| `paper-analyzer` | Deep single-paper notes (claims, methods, figures, limits). Feeds `DeepResearchSpecialist`. |
| `results-analysis` | Experiment outputs → paper-ready findings. Bridges analysis outputs into manuscript writing. |
| `citation-verifier` | Offline `.bib` hygiene (duplicate keys, placeholders, cited-vs-defined). Complements live-API validation and `citation-integrity`. |
| `nature-portfolio-playbook` | Venue fit for Nature / Nature Methods / Nature Biotechnology + policy preflight. |

`section-contracts.md` + `section-evidence.md` are vendored from the upstream
`paper-workflow` router **as reference data only** (what each section must do);
the router skill itself was deliberately NOT installed to avoid conflicting with
this repo's own `match_skill_for_task()` routing.

## Deliberately skipped (7) and why

| Skipped | Reason |
|---|---|
| `paper-workflow` (router) | Would conflict with `SkillRegistry.match_skill_for_task()`; contracts vendored as references instead. |
| `scientific-writing` | Overlaps the existing `academic-writing` pack. |
| `nature-figure` (production) | Heavy plotting-backend + OpenRouter route; `figure-planner` + `figure-style` cover the need. |
| `academic-researcher` | Duplicates `research_surfer` / `academic-search-agent` / deep-research. |
| `conference-paper-writing` | ML-conference-first; out of medical scope. |
| `academic-presentations` | Out of scope. |
| `reference-audit-guide` | Principles overlap live validation + `claim-source-verification`. |

## Context-budget note

`BaseSpecialist.load_context()` caps context at 60,000 chars. Nature skills are
therefore wired by `.../<name>/SKILL.md` file path (main skill file only) rather
than by directory name, so each specialist gains roughly one skill file
(~8–16 KB) without crowding out its existing packs. The `references/` guides
remain indexed by the registry and reachable via keyword fallback.
