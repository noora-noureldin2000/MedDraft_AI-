# Prose guardrails

The Discussion must read like an experienced evidence-synthesis author wrote it, not like a model summarising a table.

---

## 1. MEAL paragraphs

| Element | Requirement |
|---|---|
| Main idea | One topic sentence with the paragraph's claim. No throat-clearing. |
| Evidence | The synthesised finding, or a cited benchmark, stated precisely. |
| Analysis | Why it matters, the mechanism, or the discrepancy explanation. |
| Link | A bridge that sets up the next paragraph. |

A paragraph without analysis is a Results paragraph. A paragraph without evidence is opinion. A paragraph without a link is a list item.

---

## 2. Tense architecture

| Content | Tense | Example |
|---|---|---|
| Findings of this review | Simple past | `Triple therapy lowered systolic pressure by 8.4 mmHg.` |
| Specific prior findings | Simple past | `The TRINITY trial reported a comparable reduction.` |
| General conclusions | Simple present | `These findings suggest a class-level advantage.` |
| Established mechanisms | Simple present | `Chlorthalidone sustains natriuresis across the dosing interval.` |
| Ongoing inquiry | Present perfect | `Several reviews have compared thiazide-like diuretics.` |
| Speculation | Modal | `This may reflect differences in baseline severity.` |
| Recommendations | Modal | `Clinicians should recheck electrolytes within four weeks.` |

Do not narrate the review in the present tense (`The meta-analysis shows...`) and prior trials in the past within the same sentence. Pick the frame and stay in it.

---

## 3. Banned language

### Hard bans

`delve`, `underscore`, `testament`, `tapestry`, `beacon`, `pivotal`, `paramount`, `multifaceted`, `realm`, `intricate`, `notably`, `importantly`, `it is worth noting that`, `in summary`.

### House-style warnings

`crucial`, `nuanced`, `groundbreaking`, `a myriad of`, `leverage`, `foster`, `harness`, `commendable`.

### Structural bans

- `More research is needed`, `further studies are warranted` as a standalone recommendation.
- `Unfortunately`, `our study suffered from`, `we regret`.
- `This study proves`, `definitively demonstrates`, `undeniably shows`.
- Meta-commentary: `In this section, we will discuss...`, `It is important to note that...`.
- Rhetorical questions.
- Anthropomorphic claims: `the evidence tells us`, `the data want to...`.

---

## 4. Punctuation

- Zero em dashes (—). Use a comma, colon, parentheses, or a period.
- Keep semicolons rare. Three per 3,000 words is plenty.
- No exclamation marks.
- No scare quotes around ordinary technical terms.
- En dashes are acceptable in numeric ranges (Weeks 2–8).

---

## 5. Rhythm

Alternate sentence lengths. A short sentence lands a claim. A longer sentence can carry the qualification, the mechanism, and the boundary condition, provided it stays grammatical and readable.

Avoid:

- Four consecutive sentences of 25–30 words.
- Every paragraph opening with a transition.
- Every paragraph ending with `These findings suggest...`.

Vary the openers: the finding, the comparator, the mechanism, the population, the clinical consequence. Do not vary by adding filler.

---

## 6. Block synthesis

Group by clinical finding, comparator class, or mechanism. Never produce a study-by-study inventory.

**Weak**:

> Smith (2019) found a reduction. Jones (2020) found a reduction. Lee (2021) found a reduction. Patel (2022) found no difference.

**Strong**:

> Four trials using a thiazide-like diuretic plus a CCB and an ARB reported reductions of similar magnitude to ours, whereas the one trial built on indapamide found no between-arm difference. The divergence tracks the shorter follow-up and lower baseline pressure of that trial rather than a different pharmacological principle.

Rules:

- One paragraph can carry two to four studies.
- Newest first within an agreement group.
- Name a study only when its design or result is doing work in the argument.
- Refer back to your own finding in words, not by repeating the number.

---

## 7. Numbers in prose

- Report each anchor estimate once in the body, fully (estimate, CI, p, I²). Refer to it afterwards in words.
- Do not stack three statistics in one sentence unless the sentence is explicitly comparing them.
- Use units at first mention, then omit if unambiguous.
- Keep decimal precision identical to the source.
- Avoid `trend toward significance`. Report the estimate and CI, and say the result was inconclusive.
- Avoid `highly significant`. Report the p value or the CI.

---

## 8. Citations

- Vancouver numbered `[1]` is the default for biomedical journals; author-year is acceptable when the target uses it. Never mix.
- Number sequentially by first appearance. Every number resolves.
- Cite primary trials for primary data. Cite reviews for synthesis claims.
- One citation per distinct claim; do not stack five references on a sentence to look thorough.
- Use `secondary-citation-extractor` for nested claims, and attribute both layers.
- Verify with `meddraft_ai/validation/reference_validator.py`, then run the claim-support check: the source must contain the claim, not just the DOI.

---

## 9. Humanisation pass

Apply after the content is correct. Preserve every number, every citation, every technical term.

- Read the draft aloud mentally. If a sentence cannot be said in one breath, split it.
- Replace nominalisations: `performed an evaluation of` → `evaluated`; `there was a reduction in` → `pressure fell`.
- Remove one hedge per claim. `May potentially possibly` becomes `may`.
- Prefer the concrete subject: `The trial` rather than `It is observed that`.
- Keep one qualification where it is load-bearing. Do not strip uncertainty that GRADE requires.
- Delete any sentence that only restates the previous one.

Do not add new facts, references, or numbers during humanisation.

---

## 10. Self-check

- [ ] Every paragraph has a claim, evidence, analysis, and a link.
- [ ] No paragraph is a study-by-study list.
- [ ] Tense matches the content type throughout.
- [ ] No banned word, no em dash, no generic research call.
- [ ] Anchor estimates appear once, precisely; later references are verbal.
- [ ] Citations are consistent and every claim has one.
- [ ] Rhythm varies; no wall of equal-length sentences.
