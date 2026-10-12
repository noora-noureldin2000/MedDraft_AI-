---
name: medical-clinicaltrials
description: Search ClinicalTrials.gov with advanced filters (condition, intervention, phase, status) and retrieve full trial records by NCT ID for evidence tables, repurposing research, and recruitment tracking. Use when the user asks about clinical trials, trial phases, recruiting studies, NCT lookups, or comparing interventions across trials. Adapted from pascalwhoop/medical-clinicaltrials (ClawHub) to the MedDraft_AI search stack — no API key required.
---

# Medical Clinical Trials Search

Connects the pipeline to the public ClinicalTrials.gov API v2 to search and retrieve structured clinical trial data without manual website navigation and without an API key.

## When to Use

- Finding recruiting trials for a diagnosis (e.g., multiple sclerosis, myasthenia gravis).
- Checking trial phase and status for a specific drug or intervention.
- Researching repurposing candidates for an existing compound.
- Looking up study details by NCT ID for a literature review or evidence table.
- Comparing available interventions across trials for a condition.

## Tool Mapping (MedDraft_AI equivalents)

| Upstream tool | MedDraft_AI equivalent |
|---|---|
| `ctg_search_studies` | `meddraft_ai.search.clinicaltrials.search_studies()` / `ResearchOrchestrator.search_trials()` / `refs trials-search` CLI |
| `ctg_get_study` | `meddraft_ai.search.clinicaltrials.get_study()` / `ResearchOrchestrator.get_trial()` / `refs trials-get` CLI |
| `ctg_search_by_condition` | `search_by_condition()` (disease-focused wrapper) |
| `ctg_search_by_intervention` | `search_by_intervention()` (treatment-focused wrapper) |
| `ctg_get_study_metadata` | `get_study_metadata()` (phase/status vocabularies) |

## Core Workflow

### Step 1 — Formulate the filtered query

Map the user's request onto fielded filters before searching:

- **Condition:** disease name as indexed on ClinicalTrials.gov (e.g., `multiple sclerosis`, not abbreviations alone).
- **Intervention:** drug, device, or procedure name (e.g., `ocrelizumab`).
- **Phase:** user-friendly text (`Phase 1` … `Phase 4`, `Early Phase 1`) — the code layer normalizes to `PHASE1` … `PHASE4`.
- **Status:** user-friendly text (`Recruiting`, `Completed`, `Active not recruiting`, …) — normalized to API values.
- **Free term:** anything else falls back to `query.term`.

```bash
python -m meddraft_ai refs trials-search --condition "multiple sclerosis" --phase "Phase 3" --status Recruiting --limit 5
```

### Step 2 — Parse the trial list

Each result carries: `nct_id`, `title`, `status`, `phase`, `conditions`, `interventions`, `start_date`, `completion_date`, `summary`, `url`. Keep the NCT ID attached to every downstream mention — it is the trial's unique identifier and the lookup key for Step 3.

### Step 3 — Deep-dive by NCT ID

```bash
python -m meddraft_ai refs trials-get NCT04368728
```

The full record adds: primary/secondary outcome measures, eligibility criteria (age, sex, key inclusions), lead sponsor, and up to 10 locations with recruitment status. Use outcome measures and eligibility verbatim when building evidence tables — paraphrase the brief summary, quote eligibility only when the exact criterion matters.

### Step 4 — Synthesize for the manuscript

- Evidence tables: one row per trial — NCT ID (linked), phase, status, population, intervention, primary outcome.
- Discussion sections: cite recruiting status with a retrieval date, since status changes over time.
- Never present a trial as supporting efficacy based on registration data alone — registration proves existence, not results. Link to published results (PubMed/Crossref) via the existing verification cascade.

## Gotchas & Edge Cases

- **Status is time-sensitive.** Always stamp trial-status claims with the lookup date.
- **Unknown filter values fail fast.** The code layer returns `success: false` with valid vocabularies — show them to the user instead of guessing.
- **Invalid NCT IDs fail fast.** Expected format is `NCT` + 6–8 digits (e.g., `NCT04368728`).
- **Offline behavior.** Network failures return `success: false`, never raise — the pipeline treats trials as an enrichment source, so a failed lookup must not block drafting.
- **Automatic invocation.** `main.py` Phase 1 runs a bounded trials lookup (limit 5) whenever the topic carries clinical signals (trial/phase/randomized/placebo/recruiting/NCT…); `ResearchOrchestrator.search_trials()` is available for explicit calls.
