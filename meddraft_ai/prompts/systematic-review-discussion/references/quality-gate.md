# Quality gate

Run this gate after drafting and after humanisation. The deterministic checks are implemented in `meddraft_ai/core/sr_discussion.py` and exposed through the CLI.

---

## 1. Commands

```bash
# Mechanical audit (em dash, banned words, opening, GRADE, limitations, sections, length)
python -m meddraft_ai sr audit "<draft.md>" \
  --require "MSSBP week 8" \
  --require "MSDBP week 8" \
  --require "BP control rate" \
  --require "serious adverse events" \
  --require "discontinuation" \
  --min-words 1500 --max-words 3000

# Numeric fidelity against the evidence files
python -m meddraft_ai sr fidelity --draft "<draft.md>" \
  --source "<meta_dir>" --source "<included_studies_dir>" --source "<protocol.docx.md>"

# Workspace manifest
python -m meddraft_ai sr inventory "<study_root>" --json
```

Exit code is `0` when the audit has no errors, `1` otherwise. Warnings do not fail the build, but each one needs a decision.

---

## 2. Gate items and auditor codes

| Gate | Auditor code | Severity | Repair |
|---|---|---|---|
| Every required outcome discussed | `outcome_omitted` | error | Add a sentence or block; never mark it discussed if it is not |
| No em dash | `em_dash` | error | Replace with comma, colon, parentheses, or period |
| No banned AI vocabulary | `banned_vocabulary` | error | Rewrite the sentence, do not synonym-swap |
| Opening answers the question | `background_opening` | error | Delete the platitude; lead with the synthesis |
| No certainty overclaim | `grade_overclaim` | error | Match verb to GRADE rating |
| No generic research call | `generic_future_research` | error | Name design, population, comparator, outcome, duration |
| GRADE addressed | `grade_missing` | warning | Add a rating or state that GRADE was not performed |
| Clinical significance calibrated | `clinical_significance_missing` | warning | Add MCID comparison |
| Heterogeneity interpreted | `heterogeneity_missing` / `heterogeneity_uninterpreted` | warning | Add I², sources, applicability |
| Limitations split by tier | `limitations_single_tier` | warning | Separate study-level and review-level |
| Limitations state impact | `limitations_no_impact` | warning | Add the consequence for validity/precision/generalisability |
| Limitations state mitigation | `limitations_no_mitigation` | warning | Add what was done, or accept residual uncertainty |
| No apologetic tone | `apologetic_limitation` | warning | Use objective framing |
| Future research is specific | `future_research_vague` | warning | Add design and population |
| Citations present | `citations_missing` | warning | Add numbered or author-year markers |
| No data dump | `data_dump` | warning | Move tables to Results |
| Length in range | `length_low` / `length_high` | warning | Expand with substance or tighten without dropping outcomes |
| All blocks present | `section_missing` | warning | Add the missing block |
| Semicolon discipline | `semicolon_density` | warning | Split sentences |

---

## 3. Human review (not automatable)

- **Claim hierarchy**: does the opening claim match the strongest evidence, and do the secondary claims stay subordinate?
- **Completeness**: does every Results outcome have a Discussion sentence, including the null ones?
- **Accuracy of comparison**: is the external trial being compared on the same outcome, same timepoint, same effect measure?
- **Discrepancy logic**: is the explanation plausible and supported, or invented?
- **Mechanism**: is it grounded in cited physiology, and labelled as mechanism rather than result?
- **Certainty consistency**: does a low-certainty outcome get a cautious recommendation?
- **Applicability**: would a clinician know which patient this applies to?
- **Novelty**: is the "what this adds" claim explicit and defensible?

---

## 4. Numeric fidelity

`sr fidelity` extracts decimals, percentages, and integers of three or more digits from the draft and from the supplied evidence files. Any draft token absent from the sources is listed with context.

Interpretation:

- A pooled estimate, CI bound, p value, I², or sample size absent from the sources is a likely transcription error or invention. Resolve before delivery.
- Guideline thresholds (`140/90`, `130/80`), MCIDs, and externally cited trial values may legitimately be absent from the study files. Cite them and record the source in the evidence-trace table.
- Years and small integers (weeks, k) are excluded by design.
- Binary files (PDF, DOCX, XLSX) are skipped. Extract them to text first when they are the only source.

The check proves string presence, not statistical correctness. A number can appear in the sources and still be attached to the wrong outcome. The human review must confirm the pairing.

---

## 5. Repair patterns

| Failure | Do not | Do instead |
|---|---|---|
| Banned word | Swap `pivotal` for `critical` | Rewrite the claim: `This trial established...` |
| Overclaim | Delete the finding | Add the certainty qualifier and keep the estimate |
| Missing outcome | Add a vague sentence | Add the estimate and its interpretation |
| Vague research call | Add `well-designed studies` | Name design, population, comparator, duration |
| Data dump | Delete the numbers | Keep the anchor estimate, move the table to Results |
| Single-tier limitations | Add a generic sentence | Split into two paragraphs with distinct content |
| Apologetic tone | Soften the apology | State the limitation objectively |

---

## 6. Delivery checklist

- [ ] `sr audit` returns PASS.
- [ ] Every warning has been fixed or explicitly justified.
- [ ] `sr fidelity` is clean, or every unmatched token has a cited external source.
- [ ] Reference validation is clean.
- [ ] The Master Evidence Summary Table is attached or archived.
- [ ] The evidence-trace table covers every external number.
- [ ] Markdown and DOCX are exported from the same source.
- [ ] The draft is saved in the project directory and backed up to `outputs/`.
