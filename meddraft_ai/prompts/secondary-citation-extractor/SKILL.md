---
name: secondary-citation-extractor
description: Identify nested or secondary citations within uploaded PDF research papers, distinguish primary paper authors from original referenced authors, and retrieve verified full bibliographic metadata using Crossref, PubMed, or Google Scholar. Use when extracting citations from papers, verifying claims cited from another study, resolving secondary sources, or building accurate dual bibliographies.
---

# Secondary Citation Extractor

Extract, disambiguate, and retrieve complete bibliographic citations for claims in PDF documents where the author cites an external prior work (nested/secondary citations).

## When to Use

- When extracting claims, data, or quotes from a PDF where the document author cites another author.
- When distinguishing between the author of the PDF document and the root creator of an underlying claim.
- When resolving incomplete or abbreviated reference entries from a paper's bibliography by querying scholarly databases (Crossref, PubMed, or Google Scholar).
- When producing dual bibliographies that clearly show primary versus secondary container attribution.

Use this skill whenever the user wants to trace a nested citation, asks to "verify a claim cited from another study", says "as cited in", uploads a PDF excerpt with a reference marker, asks to resolve a secondary source, or needs a dual bibliography.

## Conceptual Roles & Terminology

- **Container Document (Secondary Source):** The actual PDF paper on the system. Its authors are the Container Authors.
- **Root Document (Primary Source):** The original research paper, trial, or review where the underlying finding, statistic, or quote originated. Its authors are the Original Authors.
- **Nested / Secondary Citation:** An in-text citation inside the Container Document pointing to the Root Document (e.g., (Miller, 2018), [14]).

## 4-Step Operational Workflow

### Step 1: Detect and Distinguish the Container Author

1. Identify the container document's header, title block, metadata, or first page.
2. Record the container authors, publication title, journal/conference/book, and year.
3. Verify whether an extracted statement is:
   - An original finding of the container author (experimental results, primary synthesis, author conclusions).
   - A cited claim referring to outside work (marked with author-date parentheticals, bracketed numbers, superscript digits, or narrative phrases like "as reported by...").

### Step 2: Trace the In-Text Citation to the PDF Reference List

1. Extract the raw citation key (e.g., `[23]`, `(Alvarez et al., 2020)`).
2. Jump to the References / Bibliography section of the PDF.
3. Locate the corresponding bibliography entry.
4. Extract available metadata: author list, title, year, journal/book, volume, issue, page range, and DOI/PMID if present.

### Step 3: Bibliographic Verification & Retrieval (External Databases)

When the PDF bibliography entry is abbreviated, partial, missing, or unverified, formulate targeted search queries for Crossref, PubMed, or Google Scholar:

- **Crossref (Recommended for DOI & structured metadata):**
  - Preferred search: exact title query or DOI lookup (`https://api.crossref.org/works?query.bibliographic=...`).
  - Best for: DOIs, publisher volume/issue/pages, cross-publisher normalization.
- **PubMed (Recommended for biomedical and clinical papers):**
  - Preferred search: `[Author 1] [First few words of title] [Year] [journal]` or PMID lookup.
  - Best for: Medline-indexed medical literature, NLM citation formats, MeSH terms.
- **Google Scholar (Recommended for preprints, theses, books, and hard-to-find papers):**
  - Preferred search: enclose the article title in quotes: `"Full Title of Paper"` + primary author surname.
  - Best for: grey literature, conference proceedings, book chapters.

In code (`SecondaryCitationExtractor`), this maps to the existing live-verification cascade: CrossRef by DOI → CrossRef by title → PubMed → Semantic Scholar/OpenAlex → Google Scholar query guidance. Never invent metadata — only report API-verified fields, and flag externally retrieved details explicitly.

### Step 4: Synthesize Dual Citation Output

Generate standard dual attribution:

- **In-Text Academic Formula:**
  - Author-Date: `([Original Author], [Original Year], as cited in [Container Author], [Container Year])`
  - Numeric/Vancouver: `[Original Author] et al. [X], as cited by [Container Author] et al. [Y]`
- **Dual Bibliographic Record:**
  - Original Source (Root Study): fully resolved bibliographic entry with verified DOI/PMID.
  - Container Source (Secondary Document): full citation of the PDF analyzed.

## Output Template

### Extracted Claim / Finding
> "[Direct excerpt or summarized finding]"

### In-Text Attribution
([Original Author], [Year], as cited in [Container Author], [Year])

### Full Bibliographic Entries

1. **Original Source (Root Work):**
   - **Authors:** [Full list or standard et al.]
   - **Title:** [Complete article title]
   - **Source:** [Journal / Conference / Publisher], [Year], [Vol(Issue):Pages]
   - **Identifier:** [DOI / PMID / URL retrieved via Crossref/PubMed/Google Scholar]
   - **Status:** [Verified via Crossref / PubMed / Google Scholar]

2. **Container Source (PDF Analyzed):**
   - **Authors:** [PDF authors]
   - **Title:** [PDF paper title]
   - **Source:** [Journal / Book / Conference], [Year], [Vol(Issue):Pages]
   - **Location in PDF:** Page [X], Paragraph [Y], Reference #[Z]

## Few-Shot Examples

### Example 1: Resolving a Biomedical Paper Citation via PubMed / Crossref

Context in PDF:

- Container PDF: Al-Mansoor, H., & Chen, Y. (2024). Mechanisms of Insulin Resistance in Metabolic Syndrome. Journal of Endocrinology & Metabolism.
- Text on Page 18: "Skeletal muscle GLUT4 translocation is blunted by approximately 40% under sustained lipid infusion [28]."
- PDF Reference List Entry [28]: 28. Roden M, et al. J Clin Invest. 1996;97:2859-65.

Retrieval Step:

- Query PubMed / Crossref: Roden M J Clin Invest 1996 97 2859
- Resolved DOI: 10.1172/JCI118742
- Full Title: "Mechanism of free fatty acid-induced insulin resistance in humans"

Final Output:

- In-Text Citation: Roden et al. (1996) [28], as cited in Al-Mansoor and Chen (2024).
- Original Source: Roden, M., Price, T. B., Perseghin, G., Petersen, K. F., Rothman, D. L., Cline, G. W., & Shulman, G. I. (1996). Mechanism of free fatty acid-induced insulin resistance in humans. Journal of Clinical Investigation, 97(12), 2859–2865. https://doi.org/10.1172/JCI118742 (Verified via Crossref/PubMed).
- Container Source: Al-Mansoor, H., & Chen, Y. (2024). Mechanisms of Insulin Resistance in Metabolic Syndrome. Journal of Endocrinology & Metabolism, 39(1), 15–29.

### Example 2: Incomplete Reference Resolved via Google Scholar / Crossref

Context in PDF:

- Container PDF: Henderson, T. (2022). Graph Neural Networks in Production. O'Reilly Media.
- Text on Page 63: "Neighborhood sampling caps memory explosion during mini-batch training (Hamilton 2017)."
- PDF Reference List Entry: Hamilton, W. (2017). Inductive representation learning on large graphs. NIPS.

Retrieval Step:

- Query Crossref / Google Scholar: "Inductive representation learning on large graphs" Hamilton 2017
- Resolved Authors & Venue: William L. Hamilton, Rex Ying, Jure Leskovec. Advances in Neural Information Processing Systems (NeurIPS 2017), 30, 1024–1034.

Final Output:

- In-Text Citation: (Hamilton et al., 2017, as cited in Henderson, 2022)
- Original Source: Hamilton, W. L., Ying, R., & Leskovec, J. (2017). Inductive representation learning on large graphs. Advances in Neural Information Processing Systems, 30, 1024–1034. (Verified via Google Scholar).
- Container Source: Henderson, T. (2022). Graph Neural Networks in Production. O'Reilly Media.

## Gotchas & Edge Cases

- **Do Not Conflate the Container with the Root:** Never cite the container paper author as the sole source of a finding if their text clearly has a reference marker attached to that specific sentence.
- **Truncated Author Lists:** Reference lists in papers frequently use et al. after 3 or 6 authors. Always use Crossref or PubMed to restore the complete author roster for formal bibliographies.
- **Review Papers:** Review articles synthesize hundreds of primary studies. If an agent extracts a clinical trial outcome from a narrative review, it must trace back to the actual trial (root), rather than citing the review author as having run the trial.
- **Missing In-Text Reference:** If an author mentions an outside study without a formal bibliography entry, extract `[Author, Year]` from the prose, run a strict title query on Google Scholar/Crossref, and explicitly flag: "(Full details retrieved externally; unlisted in container bibliography)".
