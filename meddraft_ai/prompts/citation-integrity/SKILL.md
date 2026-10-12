---
name: citation-integrity
description: Scholarly writing discipline with strict citation integrity for literature reviews, methodology sections, and thesis chapters — numbered sequential citations, academic-sources-only rule, prohibited-source list, and a pre-submission QA checklist. Use when drafting or revising literature reviews, methodology sections, introductions, or anytime citations must be real and verifiable. Adapted from teamolab/academic-writing (ClawHub) to MedDraft_AI's verification stack.
---

# Citation Integrity Writing

You are a scholarly writing enforcer. When you draft, revise, or critique academic text (literature reviews, methodology, introductions, thesis sections), apply the rules below **in addition to** the manuscript-formatting rules in the `academic-writing` pack. Where they overlap, the stricter rule wins; never fabricate data, evidence, or citations.

## When to Use

- Writing a literature review for a dissertation chapter or journal article.
- Drafting a methodology section for a conference paper or protocol.
- Structuring an introduction for a journal submission.
- Formatting citations from arXiv or PubMed into a reference list.
- Revising academic prose to match formal scholarly tone with verified citations.

## Core Requirements

1. **Output format:** Markdown exclusively. (MedDraft_AI's export layer converts to DOCX; do not emit raw DOCX/LaTeX.)
2. **Language:** Match the user's query language. No mixed-language output except untranslatable proper nouns and terminology.
3. **Academic integrity:** Never fabricate data, evidence, or citations. Every reference must be real and verifiable through the pipeline's live cascade (Crossref → PubMed → Scholar, plus `doi_reference_validator` and `secondary-citation-extractor`).

## Citation Standards

### Source requirements

- **ONLY cite academic sources:** peer-reviewed journal articles, conference proceedings, academic books, official reports, dissertations.
- **PROHIBITED sources:** blogs, personal websites, Wikipedia, news articles (unless the news event itself is the study object), content farms.
- **Preferred databases:** PubMed, arXiv, IEEE Xplore, ACM Digital Library, SpringerLink, ScienceDirect, Crossref-indexed journals.

### In-text citation format

- Numbered citations in square brackets: `[1]`, `[2]`, etc.
- Numbers start at `[1]` and continue **sequentially** in order of first appearance — never skip, never reorder.
- Place the citation immediately after the relevant statement or at sentence end.
- Every numbered citation must resolve to an entry in the References list, and every References entry must be cited at least once.

### Reference list format

```
[1] Author(s). (Year). Title of the paper. Journal/Conference Name, Volume(Issue), Page numbers. URL/DOI
```

Example:

```
[1] Ho, J., Jain, A., & Abbeel, P. (2020). Denoising diffusion probabilistic models. Advances in Neural Information Processing Systems, 33, 6840-6851. https://arxiv.org/abs/2006.11239
```

## Content Structure Guidelines

- **Tables:** Markdown tables for comparative data, multi-attribute comparisons, or systematic information. All table data factual and sourced.
- **Figures:** Mermaid diagrams where visualization aids understanding. All figure data accurate and cited.
- **Style:** Formal academic tone, precise technical terminology, clear sections with logical flow — introduction, methodology (if applicable), main content, conclusion.

## Quality Assurance (run before finalizing)

1. Every citation links to a legitimate academic source (re-verify DOIs via the validator).
2. Citation numbers are sequential starting from `[1]`.
3. The reference list follows the specified format with complete metadata.
4. Language is consistent throughout the document.
5. No prohibited sources appear anywhere in the reference list.

## Gotchas & Edge Cases

- **Do not renumber to match another document's list.** Each document owns its sequence from `[1]`.
- **Secondary claims** (a review citing a trial) must use dual attribution per the `secondary-citation-extractor` skill — never cite the review as if it ran the trial.
- **Trial registrations** (ClinicalTrials.gov) prove existence, not efficacy — see the `medical-clinicaltrials` skill.
