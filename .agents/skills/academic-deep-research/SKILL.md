---
name: academic-deep-research
description: Transparent, rigorous multi-cycle deep research methodology with full provenance, evidence hierarchy, and APA 7th citations. Conducts exhaustive investigations through mandated 2-cycle research per theme, gap analysis, contradiction resolution, and structured reporting. Use for literature reviews, comprehensive medical/scientific topic synthesis, competitive intelligence, and exhaustive academic investigations.
---

# Academic Deep Research 🔬

The `academic-deep-research` skill guides systematic, exhaustive investigations of complex medical, clinical, and scientific topics. It replaces superficial single-pass searches with a transparent, multi-cycle discovery process backed by an explicit hierarchy of evidence, APA 7th edition referencing, and progressive knowledge synthesis.

---

## When to Trigger This Skill

- User requests **deep research**, **exhaustive literature investigation**, or **systematic synthesis**.
- Complex, multifaceted topics requiring multi-source evidence verification.
- Comprehensive literature reviews, competitive intelligence, or clinical state-of-the-art reports.
- Resolving conflicting evidence across medical/scientific studies.

---

## Tool Mapping & Execution

| Deep Research Role | Antigravity Tool | Execution Strategy |
|---|---|---|
| **Broad Landscape Search** | `search_web` / `run_command` (PubMed / CrossRef CLI) | Query major databases, review high-level consensus, identify leading authors/trials. |
| **Deep Content Extraction** | `read_url_content` / `view_file` | Extract full-text methodology, effect sizes, statistical intervals, and limitations. |
| **Parallel Theme Tracks** | `invoke_subagent` (using `research` or `self`) | Spawn concurrent subagents to investigate independent themes simultaneously. |
| **Local Knowledge Context** | `grep_search` / `find_by_name` | Check local workspace project folders (e.g. `./projects/`, Markdown protocols) for existing grounded data. |

---

## The Four-Phase Protocol (With Three User Checkpoints)

### Phase 1: Initial Engagement & Problem Scoping `[CHECKPOINT 1 — CLARIFY]`

Before executing searches, clarify scope and align on boundaries:

1. **Clarifying Questions**:
   - What is the primary question, clinical condition, or hypothesis?
   - What is the target population, intervention, comparator, or outcome (PICO)?
   - What depth of analysis is required (broad scoping overview vs. exhaustive evidence synthesis)?
   - Are there specific date cutoffs (e.g., 2020–2026), study designs (RCTs only), or geographic parameters?
2. **Reflect Understanding**:
   - Restate the research objective and obtain user confirmation before building the plan.

---

### Phase 2: Research Planning & Theme Mapping `[CHECKPOINT 2 — PLAN APPROVAL]`

Present a structured research roadmap for user review:

1. **Identify 3–5 Core Themes**:
   - *Theme 1 (e.g., Clinical Efficacy & Primary Endpoints)*: Key questions, target trials, expected endpoints.
   - *Theme 2 (e.g., Molecular/Biological Mechanisms)*: Target receptors, cellular pathways, biomarkers.
   - *Theme 3 (e.g., Safety, Adverse Events & Contraindications)*: Risk factors, drug interactions, long-term tolerability.
   - *Theme 4 (e.g., Comparative Effectiveness vs Standard of Care)*: Head-to-head trials, meta-analyses.
2. **Execution Schedule & Tool Strategy**:
   - Table outlining query strings, primary databases to search, and target primary sources.
3. **Wait for explicit approval** before launching research cycles.

---

### Phase 3: Mandated 2-Cycle Research Execution `[NO STOPS — AUTONOMOUS]`

Complete **two full research cycles** for EACH identified theme:

```
For Each Theme:
  ├── Cycle 1: Initial Landscape Analysis
  │     ├── 1. Broad Search across databases
  │     ├── 2. Extract key patterns, dominant findings, initial hypotheses
  │     └── 3. Identify knowledge gaps, unresolved questions, conflicting data
  │
  └── Cycle 2: Targeted Deep Investigation
        ├── 1. Focused deep extraction of primary papers targeting Cycle 1 gaps
        ├── 2. Critical evaluation of study methodologies, sample sizes, and biases
        └── 3. Synthesize Cycle 2 evidence with Cycle 1 baseline; resolve or document contradictions
```

#### Intermediate Analysis Rules
After every major retrieval step, document reasoning:
- **Link Evidence**: How does new data confirm, refine, or refute prior findings?
- **Address Contradictions**: When two studies report opposing results, compare sample populations, dosages, follow-up durations, or risk of bias.
- **Track Epistemic Shifts**: Note where initial assumptions were challenged by primary evidence.

---

### Phase 4: Comprehensive Synthesis Report `[CHECKPOINT 3 — PRESENTATION]`

Synthesize findings into an authoritative, flowing academic report.

#### Core Structure

```markdown
# Comprehensive Research Report: [Topic]

## 1. Executive Summary
- High-level clinical/scientific overview, main empirical conclusions, and confidence ratings.

## 2. Knowledge Development & Methodological Evolution
- Narrative tracing how understanding evolved across research cycles, initial assumptions challenged, and resolution of controversies.

## 3. Comprehensive Analysis
- **Primary Findings & Clinical/Scientific Significance**: Deep narrative integrating data and mechanisms.
- **Patterns & Meta-Trends**: Longitudinal evolution of the field.
- **Contradictions & Discrepancy Analysis**: Detailed comparison of conflicting trials and reasons for divergence.
- **Strength of Evidence & Epistemic Confidence**: Evaluation according to evidence hierarchy.
- **Gaps in Current Literature**: Explicitly identified unaddressed questions.

## 4. Practical Implications & Applications
- Immediate clinical/translational recommendations, implementation considerations, and future research directions.

## 5. References (APA 7th Edition)
- Alphabetical bibliography with complete authors, year, title, journal, volume(issue), pages, and DOI/URL.
```

---

## Hierarchy of Evidence & Confidence Annotations

Evaluate sources using established evidence levels:

1. **Level 1 (Highest)**: Systematic reviews and meta-analyses of randomized controlled trials (RCTs).
2. **Level 2 (High)**: Well-designed individual randomized controlled trials.
3. **Level 3 (Moderate-High)**: Controlled cohort studies and prospective observational trials.
4. **Level 4 (Moderate)**: Case-control and cross-sectional studies.
5. **Level 5 (Moderate-Low)**: Systematic reviews of descriptive/qualitative studies.
6. **Level 6 (Low)**: Single descriptive, qualitative, or animal/in vitro study.
7. **Level 7 (Lowest)**: Expert committee opinions, consensus reports, narrative editorials.

### Confidence Badges

- **`[HIGH CONFIDENCE]`**: Supported by multiple Level 1/2 studies with consistent effect sizes.
- **`[MODERATE CONFIDENCE]`**: Supported by Level 3 studies or limited RCT data without major contradictions.
- **`[LOW / PRELIMINARY]`**: Supported only by single-center reports, pilot trials, or observational data.
- **`[SPECULATIVE / HYPOTHETICAL]`**: Theoretical mechanism lacking in vivo clinical validation.

---

## Citation & Formatting Rules (APA 7th Edition)

- **In-Text Citations**:
  - Direct assertions: *"SGLT2 inhibitors reduce cardiovascular death in patients with heart failure regardless of ejection fraction (Anker et al., 2021; Packer et al., 2021)."*
  - Narrative integration: *"In a landmark meta-analysis of 13 trials, Baigent et al. (2022) demonstrated..."*
- **Strict Narrative Prose**: In the final synthesis report, present insights as flowing, structured narrative paragraphs rather than fragmented bullet lists.
- **Ethics & Intellectual Honesty**: Transparently disclose study limitations, funding conflicts, and unverified assumptions.
