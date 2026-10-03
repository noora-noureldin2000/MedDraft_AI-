# Citation Modes and Verification Protocol

## 1. Mode selection

| Situation | Mode |
|---|---|
| Default (matches house samples and most thesis chapters produced here) | Numbered Vancouver, bold markers |
| User requests Harvard, or the target document/sample already uses author-date | Harvard, sentence-level |
| User supplies a reference list or prior chapter | Mirror it exactly, including marker style |

Never mix modes inside one document. Ask once at intake if the mode is unclear, then stay silent about it.

## 2. Numbered mode (house default)

### 2.1 In-text markers
- Bold parenthetical numbers at the end of the cited sentence, before the final period:
  - `…representing the second leading cause of cancer-related mortality among women worldwide **(1)**.`
  - Multiple: `…**(6, 7)**.` Ranges: `**(2–5)**.` Combined: `**(1, 3–5, 8)**.`
- Author-prominent comparison form: `In agreement with our findings, **Hu et al. (2026)** (5), in a cross-sectional study of 270…`
- Every sentence carrying an external claim gets a marker. Do not stack more than 3 refs on one sentence; if more are needed, split the sentence.

### 2.2 Reference list (Vancouver)
```
[n]. Author A, Author B, Author C, et al. Title in sentence case. Journal
Abbrev. Year;Vol(Issue):page range. doi:xxx
```
- Up to 6 authors: list all. More than 6: first 3 + et al.
- Journal abbreviated per NLM catalog. DOI included when it exists.
- Order of first appearance in the text.

Worked entries (verified formats from the house samples):
```
1. Bray F, Laversanne M, Sung H. Global cancer statistics 2022: GLOBOCAN
   estimates of incidence and mortality worldwide for 36 cancers in 185
   countries. CA: A Cancer Journal for Clinicians. 2024;74(3):229-63.
2. Wang J, Yan S, Cui Y, Chen F, Piao M, Cui W. The Diagnostic and Prognostic
   Value of the Triglyceride-Glucose Index in Metabolic Dysfunction-Associated
   Fatty Liver Disease (MAFLD): A Systematic Review and Meta-Analysis.
   Nutrients. 2022;14(23):4969.
```

## 3. Harvard mode (on request)

### 3.1 In-text rules
- Cite after EACH sentence that contains sourced information: `(Author, Year)`.
- Multiple sources in one citation: `(Author1, Year; Author2, Year)`.
- Author-prominent: `Smith (2020) demonstrated that…` still needs no trailing citation for the same claim.
- Page numbers only when they genuinely exist and matter (direct quotes or specific statements): `(Author, Year, p. X)`. Omit rather than fabricate.
- Sentence-level density rule: a 4-sentence paragraph citing one source throughout carries the citation on each sourced sentence, not only the last.

Worked paragraph:
> Penetrating abdominal trauma continues to represent a major challenge in trauma surgery, particularly in low- and middle-income countries where violence and interpersonal injury are highly prevalent (Cocco et al., 2019). Traditionally, exploratory laparotomy has been the cornerstone for diagnosis and treatment in such cases (Abbasi et al., 2021).

### 3.2 Reference list (Harvard)
```
Authors (Year). Title. Journal. Volume(Issue), pages. DOI. Available at: URL
(Accessed: Day Month Year).
```
Worked entry:
> Wang, J., Yan, S., Cui, Y., Chen, F., Piao, M. and Cui, W. (2022). The Diagnostic and Prognostic Value of the Triglyceride-Glucose Index in Metabolic Dysfunction-Associated Fatty Liver Disease (MAFLD): A Systematic Review and Meta-Analysis. Nutrients, 14(23), 4969. DOI: 10.3390/nu14234969. Available at: https://www.mdpi.com/2072-6643/14/23/4969 (Accessed: 17 September 2026).

## 4. Verification protocol (both modes)

### 4.1 Sourcing rules
- Allowed: peer-reviewed journals indexed in PubMed/PMC, Scopus, or Web of Science; reputable open-access publishers (BMJ, BMC, MDPI, Wiley OA, Elsevier OA, DOAJ); indexed regional journals (Middle East, Egypt) if publicly accessible.
- Default timeframe: 2015–2025 (2019–2025 for rapidly moving fields). Broaden only with user permission.
- Open-access rule: use only sources whose full text can actually be accessed and read. If full text is not verifiable, state "I cannot verify full-text access" and exclude the source.

### 4.2 What gets verified, per study
1. Existence: the paper is real and indexed (PubMed UID / DOI resolves).
2. Bibliography: every field (authors, title, journal, year, volume, issue, pages, DOI) checked against the source page. Any field that cannot be confirmed is marked **[Unverified]**, never guessed.
3. Numbers: each statistic quoted in a comparative paragraph (n, means, CIs, percentages, p-values, AUCs, cut-offs) is located in the full text (named table, figure, page, or section) and copied exactly. No rounding, no unit conversion unless both values are shown, no inference.
4. Comparability: the study matches the comparison aspect (population, exposure, outcome metric, design) closely enough that the comparison is honest.

### 4.3 Verification worksheet (produce with every deliverable)
For each reference:
```
Ref [n] — Author (Year)
  Full text verified: Yes/No
  Link: [URL or DOI]
  Data location(s): [Table 3 / Results, p. 1127 / Figure 2]
  Claims supported: [one-line list of the numbers drawn from this source]
```
And a closing line: `All numerical data reported in the comparative paragraphs have been verified against the original full-text sources at the locations listed above.`

### 4.4 Failure protocol
- Fewer than 2 verified comparable studies for a requested comparison: stop, report "I cannot verify enough comparable open-access studies", and ask permission to broaden (year range, geography, related populations, closely matched endpoints). Do not silently substitute weak matches.
- A wanted number cannot be located in the full text: drop that number or the whole study; never estimate it.
- A reference exists but a bibliographic field will not resolve: keep the study only if its data are verified, and mark the missing field [Unverified] in the reference list.

## 5. Anti-fabrication checklist

- [ ] No reference appears that was not seen in full text or authoritative index record.
- [ ] No number in any comparative paragraph came from memory; each traces to a listed location.
- [ ] No bibliographic field is invented; unresolved fields are marked [Unverified].
- [ ] Sources are diversified; no single paper carries three distinct claim types.
- [ ] The verification worksheet lists every reference with Yes/No status and a working link.
