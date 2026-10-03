# Humanization Pass

Apply to every Discussion deliverable before delivery, and as a standalone service when the user supplies text to humanize. Objective: formal, precise, humanized academic prose that reads as a master's-level medical researcher wrote it and does not carry AI-detection markers. Chain-of-thought reasoning stays internal; output is only the rewritten text.

## 1. What must survive the pass unchanged

- All in-text citations, exactly as written.
- All numbers, statistics, units, p-values, CIs, cut-offs, dates.
- All methods, results, and technical claims. No new facts, numbers, references, or claims may enter.
- Original meaning and factual content, paragraph count, and list structure.

If a source sentence violates a rule (for example it contains a banned word inside a quoted title), preserve the title verbatim and flag it in a verification note rather than silently altering it.

## 2. Sentence construction rules

- Average 10–25 words per sentence, with genuine variation: mix short (5–9), medium (10–20), and occasional long (40–50 word) sentences. Uniform 15–20 word rhythm is an AI marker; break it.
- One idea per sentence.
- Active voice in at least 90% of sentences ("The present study demonstrated…", "We compared…").
- Connect with simple words: and, but, so, then, because.
- Occasionally open a sentence with And or But when it reads naturally. Occasionally place the linking word mid-sentence ("The effect, however, was not significant.").
- Vary sentence openings across a paragraph; never start three sentences in a row with the same word or the same template.
- At most one genuine question per ~300 words, answered immediately in the next sentence.

## 3. Punctuation rules (deliverable text)

- Allowed: periods, commas, question marks, colons (lists only).
- Forbidden: semicolons, em dashes, en dashes used as punctuation.
- When a source sentence contains a semicolon, split it into two sentences or restructure with a comma and a conjunction.
- Parentheses only for statistics, citations, and abbreviations, never for asides.

## 4. Vocabulary rules

### 4.1 Banned AI-signature vocabulary (replace or delete)
| Banned | Replacement |
|---|---|
| delve into | examine, investigate |
| crucial | important, essential |
| tapestry | range, variety |
| multifaceted | complex |
| nuanced | subtle, detailed |
| groundbreaking | novel, important |
| paramount | essential, critical |
| a myriad of | many, numerous |
| it is worth noting that | delete, just state it |
| leverage (figurative) | use, apply |
| harness | use, employ |
| foster | promote, support |
| landscape (figurative) | field, area |
| pivotal | central, key |
| testament to | evidence of |
| navigate (figurative) | manage, address |
| underscore | highlight, reinforce (limit remaining uses to 2–3 per chapter) |
| robust | strong, consistent (limit to 1 per chapter) |
| profound / markedly (as filler) | large, clear, substantial (keep only where quantitative) |
| holistic, comprehensive (as filler) | complete, thorough |
| in the realm of | in |
| serves as a testament | delete |

### 4.2 Register
- Concrete, everyday academic words. Replace abstract nouns with measurable descriptors.
- Preserve all field-specific terminology (biomarker names, statistical tests, pathways, scales).
- No corporate jargon, no metaphors, no clichés, no hedging stacks ("might potentially perhaps").

## 5. Paragraph flow rules

- 2–5 sentences per paragraph, with occasional single-sentence paragraphs for verdicts ("This parallel supports the utility of combined TyG and FIB-4 stratification.") — the house samples do this deliberately.
- Vary paragraph length across the chapter.
- Keep the alternating findings/comparison rhythm intact.
- Prefer a short declarative sentence after a long statistics-heavy sentence. This is the house cadence.

## 6. Procedure (standalone humanization requests)

1. Read the source text fully before changing anything.
2. Rewrite sentence by sentence under the rules above, preserving every citation and number.
3. Scan the rewrite: banned words, semicolons, em dashes, uniform rhythm, repeated openers, passive clusters.
4. Fix, then read once more for flow. Reading aloud should sound like a person talking precisely, not a machine listing.
5. Output only the rewritten text. No headings, outlines, explanations, or commentary (unless the user asked for notes).

## 7. Before/after calibration

Before (AI-flavored):
> It is worth noting that the multifaceted landscape of biomarker research delves into crucial parameters; moreover, robust evidence underscores the paramount importance of these markers.

After (house register):
> Biomarker research has moved toward practical, measurable parameters. Several studies now report consistent performance for these markers, and our findings add to that evidence.

Before (uniform rhythm, semicolon):
> The TyG index was elevated in MAFLD patients; the difference was significant; BMI followed the same pattern.

After:
> The TyG index was elevated in MAFLD patients, and the difference was significant. BMI followed the same pattern.

## 8. Self-check before output

- [ ] No banned vocabulary remains.
- [ ] No semicolons or em dashes in the deliverable.
- [ ] Sentence lengths genuinely vary (spot-check: not all 15–20 words).
- [ ] Active voice ~90%.
- [ ] Every citation and number preserved exactly.
- [ ] No new facts, references, or numbers introduced.
- [ ] No three consecutive sentences with identical openings.
- [ ] Reads naturally aloud.
