# Evidence intake and Master Evidence Summary

The Discussion is only as honest as its intake. Complete this stage before drafting.

---

## 1. Workspace inventory

```bash
python -m meddraft_ai sr inventory \
  "<protocol_dir>" \
  "<included_studies_dir>" \
  "<meta_dir>" \
  "<prior_reviews_dir>" \
  --json
```

The command is read-only. It classifies files into `protocol`, `included_studies`, `meta_analysis`, `prior_reviews`, `data`, `figure`, `document`, and `other`.

For each bucket, record:

| Bucket | Required extraction | Format |
|---|---|---|
| Protocol | PICO, eligibility, pre-specified outcomes and timepoints, subgroup plan, registration ID, any protocol deviation | Short prose |
| Included studies | Author, year, country, design, N, population, baseline values, arms and doses, comparator, follow-up, risk of bias | Table |
| Meta outputs | Outcome, timepoint, k studies, N, effect measure, estimate, 95% CI, p, I², tau², Q p, model, software | Table |
| Prior reviews | Author, year, design, k, N, scope, main findings, certainty, overlap with this review | Table |
| Figures | Forest plots, funnel plots, RoB summary, GRADE SoF | Visual check |

If a directory is absent, say which one and proceed with what exists. Never silently downgrade the study to "no meta-analysis".

---

## 2. Included-study table

One row per trial. Columns:

| Column | Notes |
|---|---|
| Study ID | First author + year, as cited |
| Design | RCT, crossover, open-label, multicentre |
| Country / region | Relevant to generalisability and ethnicity |
| N randomised / analysed | Both if attrition is material |
| Population | Inclusion criteria, baseline severity, background therapy |
| Intervention arm | Agent, dose, formulation, titration |
| Comparator arm | Exact dual combination and dose |
| Co-interventions | Allowed or prohibited |
| Follow-up | Weeks, and the timepoints analysed |
| Primary outcome | As defined by the trial |
| Risk of bias | RoB 2 domain summary |

If two trials use the same ARB at different doses, keep them as separate rows. Dose is a heterogeneity source, not a footnote.

---

## 3. Pooled-outcome table

One row per outcome × timepoint. Never collapse timepoints.

| Column | Notes |
|---|---|
| Domain | Efficacy, target attainment, safety, laboratory |
| Outcome | MSSBP, MSDBP, control rate, response rate, AE, SAE, ADR, discontinuation, potassium, uric acid, creatinine/eGFR, glucose, sodium |
| Timepoint | Week 2, Week 4, Week 8, end of treatment |
| k | Number of studies contributing |
| N | Participants contributing |
| Effect measure | MD, SMD, RR, OR, HR |
| Estimate | Exact value and sign |
| 95% CI | Exact bounds |
| p | Exact, or `p < 0.001` only if source says so |
| I² | Percent |
| tau² | As reported, with unit if given |
| Q p | As reported |
| Model | Random or fixed |
| Direction | Favours intervention / comparator / null |
| Certainty | GRADE rating for this outcome |

If an outcome was reported narratively only, mark `NOT_POOLED` and record why (k = 1, incompatible definitions, clinical heterogeneity). If a timepoint was not analysed, mark `NOT_REPORTED`. Do not back-fill.

---

## 4. Prior-review comparison grid

For each prior review:

| Column | Notes |
|---|---|
| Review ID | Author + year |
| Design | SR, MA, network MA, umbrella |
| k / N | Scope size |
| Population | Same, broader, or narrower |
| Intervention class | Thiazide-like, HCTZ, any diuretic, triple therapy |
| Comparators | Dual, placebo, usual care |
| Timepoints | Which the review pooled |
| Main efficacy finding | Estimate + CI |
| Main safety finding | Estimate + CI or narrative |
| Certainty | GRADE or equivalent |
| How this review differs | Newer trials, Chlorthalidone-specific focus, extra timepoints, different comparator strata, larger N, safety granularity |

The "how this review differs" column becomes the Extends paragraph. Without it, the Discussion has no novelty claim.

---

## 5. Transcription rules

1. Preserve precision. `-8.42` stays `-8.42`; do not round to `-8.4`.
2. Preserve sign and direction. A reduction can be reported as `-8.42` or `8.42 in favour of intervention`; convert once, consistently, and state the convention.
3. Preserve units. mmHg for blood pressure, mmol/L for potassium, µmol/L for uric acid, mL/min/1.73 m² for eGFR.
4. Preserve the CI structure. If the source reports `MD -8.42 (95% CI -10.11 to -6.73)`, keep both bounds and the dash direction.
5. Never convert a CI to a standard error for prose. Never recompute a p value.
6. Record heterogeneity exactly as reported. If `I²` is absent but tau² is present, report tau² only.
7. Distinguish `p = 0.04` from `p < 0.05`. Distinguish `p < 0.001` from `p = 0.000`.
8. If two files disagree (for example a CSV and a forest-plot image), flag the conflict and state which file you used. Do not average them.

---

## 6. Missing-data protocol

| Situation | Action |
|---|---|
| Outcome not in the meta folder | `NOT_REPORTED`, and say which file would have contained it |
| Outcome pooled in only one study | `NOT_POOLED (k = 1)`; discuss the study-level finding narratively |
| Timepoint absent | `NOT_REPORTED`; do not infer from a neighbouring week |
| Subgroup not pre-specified | Label exploratory; do not present as confirmatory |
| Safety outcome reported only in some trials | Report k and N; warn about selective reporting |
| Forest plot unreadable | State `UNREADABLE`; use the numeric table if it exists |

The Discussion may say `the review did not pool this outcome`. It may never say `the effect was probably around ...`.

---

## 7. Plug-and-play study spec

`python -m meddraft_ai sr brief --spec study_spec.json` renders the system command
with the workspace already inventoried. Minimal spec:

```json
{
  "title": "Efficacy and safety of triple therapy in uncontrolled hypertension",
  "population": "Adults with uncontrolled hypertension on dual therapy",
  "intervention": "Chlorthalidone + amlodipine + ARB",
  "comparator": "Any dual combination of the same classes",
  "outcomes": [
    "MSSBP change at Week 8 (primary)",
    "MSDBP change at Weeks 2, 4, 8",
    "BP control and response rates",
    "AEs, SAEs, ADRs, discontinuations",
    "Potassium, sodium, uric acid, creatinine/eGFR, glucose"
  ],
  "timepoint": "Week 8",
  "workspace": [
    "path/to/protocol",
    "path/to/included studies",
    "path/to/meta",
    "path/to/old meta&systematic review"
  ],
  "output": "path/to/Discussion_Draft.md",
  "citation_style": "Vancouver"
}
```

The builder inventories every path and embeds the file manifest, so the first
instruction the agent receives is the Step 0 proof. It also repeats the
zero-omission, GRADE, and prose gates. The spec is a launcher, not evidence: the
numbers still come only from the workspace files.

---

## 8. Pre-draft gate

Proceed only when:

- [ ] Every workspace directory has been listed.
- [ ] The included-study table is complete, with `UNREADABLE` used honestly.
- [ ] Every pooled outcome has a row, including null and safety outcomes.
- [ ] Every `NOT_POOLED` and `NOT_REPORTED` is explicit.
- [ ] Prior reviews have a comparison row and a novelty statement.
- [ ] Conflicts between files are documented.
- [ ] No number in the table came from memory or another paper.
