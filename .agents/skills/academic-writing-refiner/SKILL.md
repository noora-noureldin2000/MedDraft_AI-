---
name: academic-writing-refiner
description: Refine, polish, and edit academic and medical research writing for publication-ready manuscripts and top-tier journals (Nature, Lancet, NEJM, JAMA, IEEE, NeurIPS, ICLR, ICML, ACL, etc.). Polishes abstracts, introductions, methodology, results, discussion, and rebuttal letters with clear, precise, authoritative prose. Enforces IMRAD conventions, tightens sentence structure, removes wordiness and excessive hedging, handles LaTeX formatting, and aligns with high-impact publication standards.
---

# Academic Writing Refiner

This skill transforms draft manuscripts, theses, dissertations, and research papers into polished, publication-ready academic prose for high-impact journals and top-tier peer-reviewed conferences (e.g., *Lancet*, *NEJM*, *JAMA*, *Nature Medicine*, *Bioinformatics*, *NeurIPS*, *ICML*, *ACL*, *IEEE TPAMI*).

---

## Core Philosophy

Reviewers and editors evaluate papers on idea clarity, methodological rigor, and empirical transparency — not on bloated vocabulary. High-impact academic writing serves as a clear window into discoveries.

### Four Key Tenets

1. **Clarity Over Grandiosity**: Use the simplest, most precise word. Use *use* instead of *utilize*, *show* instead of *demonstrate* (unless a mathematical/formal proof is provided), *many* instead of *a plethora of*.
2. **Precision Over Vagueness**: Replace vague hand-waving with exact numbers and metrics. Instead of *"our protocol improved healing substantially"*, write *"the intervention accelerated wound closure by 32% (p = 0.004) compared to vehicle control"*.
3. **Economy Over Verbosity**: Every sentence must earn its place. If deleting a sentence loses no information, delete it.
4. **Logical Cohesion Over Fragmentation**: Connect sentences and paragraphs with logical, cause-and-effect transitions rather than abrupt topic jumps.

---

## Systematic Refinement Workflow

When refining academic text, execute the following 5-stage process:

### 1. Contextual Assessment
- **Determine Section Type**: Abstract, Introduction, Literature Review, Methods, Results, Discussion, Conclusion, or Rebuttal letter. (Each section has distinct tense, style, and structure rules; see `references/section-guide.md`).
- **Identify Venue / Target Field**:
  - *Biomedical / Clinical (ICMJE, AMA, APA)*: Rigorous IMRAD, PICO(T) framing, CONSORT/STROBE alignment, exact p-values, confidence intervals.
  - *Computational / Machine Learning (NeurIPS, ICML, ICLR)*: Concise, equation-heavy notation, clear baseline comparisons, ablation insights.
  - *NLP / Linguistics (ACL, EMNLP)*: Precision in linguistic terminology, detailed error analysis.
- **Stage of Manuscript**: Initial draft (needs structural tightening) vs. camera-ready revision (micro-polishing prose and word limits).

### 2. Structural & Section Alignment
Check against the section conventions in [section-guide.md](file:///d:/GitHub/MedDraft_AI/.agents/skills/academic-writing-refiner/references/section-guide.md):
- **Abstract** (150–250 words): Background → Objective → Methods (study design, N) → Key Results (with numbers/p-values) → Primary Conclusion.
- **Introduction**: The Hourglass model: Broad problem → State of the art → The Knowledge Gap (Formula: *Although X is known, Y remains unknown because Z*) → Study Aim/Hypothesis → Value/Outline.
- **Methods**: Past tense, reproducible detail, ethics, sample size calculation, statistical tests specified.
- **Results**: Past tense, objective reporting, zero interpretation, reference to tables/figures, effect sizes and CIs.
- **Discussion**: Inverted funnel: Principal finding → Mechanisms & Literature context (agreements/contradictions) → Strengths & Limitations → Future directions & conclusion.

### 3. Sentence-Level Micro-Refinement
Consult [word-choice.md](file:///d:/GitHub/MedDraft_AI/.agents/skills/academic-writing-refiner/references/word-choice.md) for exact substitutions:
- **Prune Filler & Wordiness**:
  - *"It is worth noting that"* → Delete.
  - *"In order to investigate"* → *"To investigate"*.
  - *"Due to the fact that"* → *"Because"*.
  - *"At a temperature of 37 degrees"* → *"At 37 °C"*.
- **Fix Syntax & Grammatical Pitfalls**:
  - **Dangling Modifiers**: *"Using gradient descent, the loss decreases"* → *"Using gradient descent, we minimized the loss"*.
  - **Noun Stacking / Pile-ups**: *"Pre-trained language model parameter efficient fine tuning strategy"* → *"Parameter-efficient fine-tuning for pre-trained language models"*.
  - **Ambiguous Pronoun Referents**: *"This demonstrates that..."* → *"This marked reduction in inflammatory cytokines demonstrates that..."*.
- **Calibrate Hedging**:
  - Replace double-hedging (*"could potentially suggest that it might arguably indicate"*) with calibrated academic confidence (*"suggests"*, *"indicates"*, *"is consistent with"*).

### 4. LaTeX & Mathematical Notation Handling
- **Preserve Commands & Macros**: Never alter `\cite{}`, `\ref{}`, `\label{}`, `\eqref{}`, `\begin{equation}`, or math formulas `$x_i \in \mathbb{R}^d$`.
- **Maintain Non-Breaking Spaces**: Keep `~` before citations and cross-references (e.g., `Table~\ref{tab:results}`, `Smith et al.~\cite{smith2023}`).
- **Ensure Notation Consistency**: Check scalar vs. vector notation (e.g., $x$ vs $\mathbf{x}$) and maintain uniform symbol usage throughout.

### 5. Peer-Review Rebuttals & Revision Responses
When refining rebuttal letters or response to reviewers:
- Consult [rebuttal-guide.md](file:///d:/GitHub/MedDraft_AI/.agents/skills/academic-writing-refiner/references/rebuttal-guide.md).
- Follow the 3-part formula: **Gratitude/Agreement** → **Direct Action Taken** (referencing line/page numbers in the revised manuscript) → **Supporting Evidence/Data**.

---

## Output Protocol

When returning refined text:

1. **Refined Text**: Provide the clean, publication-ready text as the primary section.
2. **Substantive Change Summary**: Briefly highlight major structural or clarity improvements (e.g., *"Converted passive wordiness in para 2 to direct active voice"*, *"Strengthened the knowledge gap statement"*).
3. **Author Action Items / Flags**: List any items requiring author verification (missing sample sizes, unclear baseline citations, undefined abbreviations).
4. **Format Preservation**: Retain the original input format (LaTeX stays LaTeX, Markdown stays Markdown).

---

## Reference Guides

- [Section-by-Section Guide](file:///d:/GitHub/MedDraft_AI/.agents/skills/academic-writing-refiner/references/section-guide.md)
- [Word Choice & Substitution Table](file:///d:/GitHub/MedDraft_AI/.agents/skills/academic-writing-refiner/references/word-choice.md)
- [Reviewer Response & Rebuttal Guide](file:///d:/GitHub/MedDraft_AI/.agents/skills/academic-writing-refiner/references/rebuttal-guide.md)
