# RCI interpretation and heterogeneity

RCI is the engine of the Discussion body: **Restate → Compare → Interpret**. It prevents both the data dump (restate only) and the unsupported claim (interpret only).

---

## 1. The four moves

### Move 1, Restate

One or two sentences. Direction, magnitude, precision, consistency.

> Pooled across five randomised trials, triple therapy lowered mean sitting systolic pressure by a further 8.4 mmHg at Week 8 compared with dual therapy, with a confidence interval that excluded a trivial difference.

Avoid: `The MD was -8.42, 95% CI -10.11 to -6.73, p < 0.001, I² = 32%` as a standalone sentence. That is a table row, not prose.

### Move 2, Compare

Choose a stance explicitly:

| Stance | When | Opening |
|---|---|---|
| Confirms | Direction and magnitude agree with prior synthesis | `Consistent with our findings, ...` / `This aligns with ...` |
| Contradicts | Direction, magnitude, or significance diverges | `In contrast to our findings, ...` / `This diverges from ...` |
| Extends | New trials, populations, agents, timepoints, or scope | `Our review extends this evidence by ...` / `Beyond earlier syntheses, ...` |

Sequence: newest evidence first, agreement before contrast, primary trials before reviews.

### Move 3, Explain

For any divergence, select one or more of the four admissible explanations:

1. **Population**: baseline severity, age, comorbidity, ethnicity, region, background therapy, adherence.
2. **Intervention/comparator**: agent, dose, duration, titration, formulation, co-intervention, active vs placebo vs usual care.
3. **Methodology**: ITT vs per-protocol, confounding adjustment, risk-of-bias handling, model choice, unit-of-analysis, search scope.
4. **Power/measurement**: sample size, follow-up, scale, cut-off for response/control, precision.

Template:

> This divergence may reflect [population difference], since [concrete detail]. It may also reflect [comparator or dose difference], which would [direction of expected bias].

Never: `Smith et al. were wrong` or `their study was flawed`. Describe the design difference, not the authors.

### Move 4, Interpret

Mechanism and meaning. Ground every mechanism in cited physiology, pharmacology, or trial data.

- Mechanism claim directly supported by your data: `Our data demonstrate ...`
- Reasonable inference: `These findings suggest ...`
- Literature-supported possibility: `A plausible mechanism is ...`
- Speculation: `We speculate that ...`

Label the certainty of the mechanism, not only of the effect.

---

## 2. Domain blocks

Build one block per domain, in Results order.

### Efficacy block

- Restate the primary effect and its clinical magnitude against the MCID.
- Restate every secondary efficacy outcome, including null ones.
- Compare with prior reviews and landmark trials.
- Explain the time course: onset, trajectory, plateau.
- Interpret the pharmacological or behavioural mechanism.

### Target-attainment block

- Control and response are composite, threshold-dependent outcomes. State the threshold used by each trial.
- Compare absolute risk differences, not only pooled RRs. A 20% relative increase can be a 6% absolute increase.
- Interpret early attainment in terms of therapeutic inertia, adherence, and early risk.

### Safety and laboratory block

- Report total AEs, SAEs, ADRs, and discontinuations separately. A null SAE result does not mean a null AE result.
- For each laboratory shift, distinguish transient haemodynamic change from structural injury.
- Compare with class expectations and with the comparator's known profile.
- Interpret mechanism (for example, RAAS blockade blunting diuretic potassium wasting).
- State whether the safety data are powered to detect rare events (usually not).

### Subgroup block

- Pre-specified subgroups are findings; post-hoc subgroups are hypotheses.
- Report interaction tests, not within-subgroup p values alone.
- Resist claiming subgroup-specific efficacy when the interaction is not significant.

---

## 3. Heterogeneity

### What to report

Always: I², tau² (if reported), Q p value, model, and k. When available: prediction interval.

### How to read it

| I² | Label | Interpretation for practice |
|---|---|---|
| 0–40% | Low | Pooled estimate reasonably transferable; residual clinical diversity still worth naming |
| 40–75% | Moderate | Explore sources; the average may not fit every setting |
| > 75% | Considerable | The average may be misleading for an individual setting; prediction interval is essential |

`I²` describes the proportion of variability due to between-study differences rather than chance. It does not say whether those differences are clinically important. A statistically homogeneous set of trials can still be clinically diverse.

### Source hunt

Check, in order:

1. Baseline severity (higher baseline pressure produces larger absolute reductions).
2. Comparator composition (ARB + CCB vs ARB + diuretic vs CCB + diuretic).
3. Agent and dose (azilsartan vs losartan; low vs high dose).
4. Design (titration-to-target vs fixed dose; open-label vs double-blind).
5. Follow-up and timepoint.
6. Region and ethnicity.
7. Risk of bias.
8. Outcome definition (office vs home vs ambulatory; control threshold).

### Prediction interval

If reported, translate it: `Although the average effect was -8.4 mmHg, the prediction interval suggests that a future comparable trial could observe an effect ranging from ... to ...`. If not reported and I² is high, recommend it as a reporting gap.

### Publication bias

- Funnel plot and Egger's test are unreliable with fewer than 10 studies. Say so.
- If asymmetry is present, discuss the likely direction: small negative trials missing would inflate the pooled benefit.
- Trim-and-fill, if used, is a sensitivity analysis, not a corrected truth.

---

## 4. Worked contrast paragraph

> Our Week 8 estimate exceeds the 5 mmHg between-arm difference reported for an olmesartan/amlodipine/HCTZ single pill, a gap that likely reflects both the longer half-life of Chlorthalidone and the higher baseline pressure of the trials in our review. The smaller indapamide-based trial, by contrast, found no significant difference; its shorter follow-up and lower baseline systolic pressure would both compress the observable treatment effect. These differences are clinical and methodological rather than evidence of inconsistency in the underlying pharmacology.

Why it works: restates direction, compares two benchmarks, explains each discrepancy with named categories, and avoids criticising authors.
