# Academic Writing Refiner: Section-by-Section Guide

This guide details the structural requirements, tense rules, and rhetorical moves for every major section of an academic or medical research paper.

---

## 1. Title & Abstract

### Title
- **Concise & Informative**: State the primary finding, intervention, and population or method clearly.
- **Avoid Vague Hooks**: Avoid *"Studies on..."*, *"An investigation into..."*, *"Observations regarding..."*.
- **Clinical/Trial Standard**: Include study design if appropriate (*"Effect of Empagliflozin on Heart Failure: A Randomized Controlled Trial"*).

### Abstract (150–250 Words)
- **Background (1–2 sentences)**: State context and the specific clinical/scientific problem.
- **Objective (1 sentence)**: Formulate the primary aim or hypothesis.
- **Methods (2–3 sentences)**: Study design, setting, participant/sample size ($N$), primary intervention/exposure, comparator, and key primary endpoints.
- **Results (3–4 sentences)**: Quantitative results with exact numerical values, effect sizes (RR, OR, HR, MD), 95% confidence intervals, and exact $p$-values. Never write "results were significant" without numbers.
- **Conclusions (1–2 sentences)**: Direct answer to the objective without extrapolation or unwarranted clinical claims.

---

## 2. Introduction (The Hourglass Model)

The Introduction moves from general scientific context to the specific research question:

1. **Paragraph 1: Broad Scientific Importance & Epidemiology**:
   - Establish the clinical or theoretical importance of the problem (e.g., prevalence, mortality, computational bottleneck).
2. **Paragraph 2: Current State of the Art & What is Known**:
   - Summarize established mechanisms and current standard-of-care or leading algorithms with authoritative citations.
3. **Paragraph 3: The Critical Knowledge Gap**:
   - Use the **Gap Formula**: *"Although [what is known], [what remains unknown] because [why prior studies were limited (methodological, population, or mechanistic)]"*.
4. **Paragraph 4: Study Aim & Working Hypothesis**:
   - Explicit statement: *"Therefore, this study aimed to evaluate whether [intervention/technique] improves [outcome] compared with [comparator] in [target population]"*.
5. **Paragraph 5 (Optional for CS/Engineering)**:
   - Brief roadmap or summary of main contributions.

---

## 3. Materials and Methods

- **Goal**: Full reproducibility. A competent peer must be able to replicate the work.
- **Verb Tense**: Past tense (*"Patients were randomized..."*, *"Cells were incubated..."*).
- **Structure**:
  - **Ethical Approval & Consent**: Institutional Review Board (IRB) / Ethics committee approval numbers and informed consent declaration.
  - **Study Design & Participants**: Inclusion and exclusion criteria, recruitment timeframe, blinding, and allocation concealment.
  - **Interventions / Experimental Setup**: Doses, device models, software versions, chemical purities, and standard protocols.
  - **Outcome Measures**: Primary and secondary outcome definitions and measurement intervals.
  - **Statistical Analysis**: Power/sample size calculation, test for normality (e.g., Shapiro-Wilk), parametric/non-parametric tests, handling of missing data, software name and version (e.g., *R version 4.3.2*, *SPSS v29*), and significance threshold ($\alpha = 0.05$).

---

## 4. Results

- **Strict Rule**: Zero interpretation or speculation in the Results section. Report only what was observed.
- **Verb Tense**: Past tense (*"The mean systolic blood pressure decreased from... to..."*).
- **Format**:
  - Lead with the most important primary outcome, followed by secondary outcomes, subgroup analyses, and adverse events.
  - Text and tables must complement, not duplicate, one another. Summarize key trends in text and refer to tables/figures: *(Table 2)*, *(Figure 3B)*.
  - Always report: Central tendency (Mean ± SD or Median [IQR]), effect size (e.g., Mean Difference, Hazard Ratio), 95% Confidence Intervals $[95\%\text{ CI: } \dots]$, and exact $p$-values (e.g., $p = 0.003$; report $p < 0.001$ rather than $p = 0.0000$).

---

## 5. Discussion (The Inverted Funnel)

The Discussion moves from your specific results outward to the broader field:

1. **Paragraph 1: Principal Findings**:
   - Immediately restate the primary finding answering the research question. Do not repeat raw numbers; state the conceptual answer.
2. **Paragraphs 2–4: Mechanisms & Literature Comparison**:
   - Compare your findings with published literature.
   - For findings that agree: cite supporting studies and explain why (shared mechanism, similar cohort).
   - For findings that disagree: analyze methodological differences, demographic variations, dosage discrepancies, or analytical differences.
   - Discuss biological or computational plausibility and plausible mechanisms.
3. **Penultimate Paragraph: Strengths & Limitations**:
   - Honest evaluation of study strengths (e.g., prospective design, blinded assessment, multi-center validation).
   - Transparent acknowledgment of limitations (e.g., sample size, short follow-up duration, single-center setting, unmeasured confounders).
4. **Final Paragraph: Conclusions & Future Directions**:
   - Summary of practical or clinical relevance and specific unaddressed questions for future investigations.

---

## 6. Verb Tense Quick Reference

| Section | Recommended Tense | Example |
|---|---|---|
| **Abstract** | Past for methods/results; Present for conclusions | *"The treatment reduced mortality... These findings suggest..."* |
| **Introduction** | Present for established facts; Past/Present Perfect for prior studies | *"Diabetes is a metabolic disease... Smith et al. (2022) showed..."* |
| **Methods** | Past tense exclusively | *"Rats were anesthetized with isoflurane..."* |
| **Results** | Past tense exclusively | *"Serum creatinine levels declined significantly..."* |
| **Discussion** | Past for discussing current results; Present for established principles & implications | *"Our intervention reduced pain scores... This indicates that central sensitization is..."* |
| **Conclusion** | Present tense | *"The proposed framework provides an efficient approach for..."* |
