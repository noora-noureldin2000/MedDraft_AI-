# GRADE certainty

A systematic review that reports only p values has not finished its job. GRADE converts a body of evidence into a defensible certainty statement, and the Discussion verb must match it.

---

## 1. The five downgrading domains

| Domain | Ask | Typical downgrade |
|---|---|---|
| Risk of bias | Were allocation concealment, blinding, and attrition adequate across the trials contributing to this outcome? | -1 serious, -2 very serious |
| Inconsistency | Is the direction and magnitude consistent? Is unexplained heterogeneity large (I² > 50%, non-overlapping CIs)? | -1 or -2 |
| Indirectness | Do the populations, interventions, comparators, and outcomes match the review question? | -1 or -2 |
| Imprecision | Is the CI narrow enough to support a decision? Does it cross the MCID or the null? Is the total N adequate? | -1 or -2 |
| Publication bias | Is there funnel-plot asymmetry, registry suppression, or evidence of missing negative trials? | -1 (strong suspicion) |

Upgrade only with an explicit rationale: large magnitude, dose-response, or plausible confounding that would bias against the observed effect. Never upgrade by default.

---

## 2. Rating workflow

1. List the critical outcomes. Do not rate every surrogate; rate the ones that drive the conclusion.
2. For each, start at the design baseline (RCT = high, observational = low).
3. Apply downgrades with a one-line justification each.
4. Assign final certainty: high, moderate, low, very low.
5. Write the certainty sentence with the matching verb.
6. If the review reports a Summary of Findings table, stay consistent with it. If it does not, state that the rating is this Discussion's assessment.

A rating without a reason is decoration. Every downgrade needs a clause: `downgraded for imprecision because the confidence interval included both a trivial and a clinically important effect`.

---

## 3. Calibrated vocabulary

| Certainty | Claim verb | Example | Prohibited |
|---|---|---|---|
| High | shows, reduces (plain present) | `The evidence shows that triple therapy reduces Week 8 systolic pressure.` | `may` as the main verb |
| Moderate | likely reduces; suggests | `Triple therapy likely reduces Week 8 systolic pressure.` | `proves`, `definitively` |
| Low | may reduce; indicates potential | `Triple therapy may reduce Week 8 systolic pressure.` | `shows`, `confirms` |
| Very low | very uncertain | `The evidence is very uncertain about the effect of triple therapy on Week 8 systolic pressure.` | any claim of efficacy |

Additional rules:

- `Significant` is a statistical adjective. Pair it with a clinical magnitude or drop it.
- `Effective` is a clinical claim. It needs a certainty rating and an effect size.
- Do not hedge a high-certainty finding into invisibility. `The evidence shows` is allowed when the rating supports it.
- Do not promote a low-certainty finding with confident prose. One confident adjective undoes four cautious sentences.

---

## 4. Sentence templates

**Efficacy, moderate certainty**

> Moderate-certainty evidence indicates that Chlorthalidone-based triple therapy likely lowers Week 8 mean sitting systolic pressure by a clinically meaningful margin compared with dual therapy.

**Safety, low certainty**

> The evidence for serious adverse events was of low certainty, and the confidence interval does not exclude a meaningful increase in risk.

**Null outcome, moderate certainty**

> For adverse drug reactions leading to discontinuation, the evidence suggests little or no difference between triple and dual therapy, although the total number of events was small.

**Very low certainty**

> The evidence is very uncertain about the effect of triple therapy on laboratory potassium shifts, because only two trials reported the outcome and both were at high risk of bias.

---

## 5. Publication bias language

- `Funnel-plot inspection and Egger's test suggested asymmetry, raising concern that small negative trials may be missing; this would bias the pooled estimate toward benefit.`
- `With fewer than ten contributing studies, funnel-plot asymmetry could not be interpreted reliably, and publication bias remains a possible limitation.`
- `The review searched trial registries and conference proceedings, which reduces but does not eliminate the risk of unpublished negative findings.`

Never claim `no publication bias` from a non-significant Egger test with five studies. Absence of evidence of bias is not evidence of absence.

---

## 6. Certainty in the implications

| Certainty | Practice language | Research language |
|---|---|---|
| High | `We recommend ...` / `Clinicians should ...` | Confirmatory or implementation research |
| Moderate | `Clinicians may reasonably ...` / `It is reasonable to ...` | Pragmatic trial, cost-effectiveness |
| Low | `Shared decision-making should acknowledge ...` / `Conditional recommendation` | Adequately powered RCT with blinded outcome assessment |
| Very low | `No firm recommendation can be made ...` | Foundational efficacy trial before implementation |

The recommendation's strength must never exceed the certainty of the evidence behind it.

---

## 7. Certainty audit

- [ ] Every critical outcome has a rating or an explicit statement that GRADE was not performed.
- [ ] Every downgrade has a stated reason.
- [ ] The verb matches the rating in every sentence.
- [ ] Statistical significance is not used as a proxy for certainty.
- [ ] Publication bias is discussed, or its non-assessability is stated.
- [ ] Practice recommendations are calibrated to the rating.
- [ ] The Conclusions do not assert more than the weakest link in the chain.
