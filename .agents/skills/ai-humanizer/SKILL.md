---
name: ai-humanizer
description: Humanize AI-generated text and academic/medical drafts by detecting and eliminating 24 LLM writing patterns, 500+ AI vocabulary clichés across 3 tiers, and robotic sentence structures. Enforces natural human variance (burstiness, TTR), direct authoritative voice, and Dr. Noora Noureldin's writing style markers. Use when asked to humanize text, de-AI writing, polish medical/academic drafts to sound natural, remove AI slop, reduce AI detector scores, or inject authentic voice into AI-generated prose.
---

# AI Humanizer: Eliminate AI Writing Patterns & Slop

The `ai-humanizer` skill transforms robotic, formulaic LLM prose into natural, compelling, and human writing. It detects and eliminates 24 distinct AI writing patterns, screens against 500+ vocabulary clichés across 3 tiers, measures statistical metrics (burstiness, type-token ratio, sentence variance), and enforces Dr. Noora Noureldin's academic and medical writing markers.

Based on stylometric analysis, Wikipedia Signs of AI writing, Copyleaks research, and medical peer-review standards.

---

## The 24 Anti-AI Pattern Detector

| # | Pattern Name | Category | What to Watch For & How to Eliminate |
|---|--------------|----------|---------------------------------------|
| 1 | **Significance Inflation** | Content | Clichés like *"marking a pivotal moment in the evolution of..."*, *"serves as a groundbreaking milestone"*. → State empirical facts directly with numbers. |
| 2 | **Notability Name-Dropping** | Content | Listing broad entities or journals without specific claims. → Quote specific data points or cite specific findings. |
| 3 | **Superficial `-ing` Analyses** | Content | Stacking participle clauses: *"...showcasing X, reflecting Y, while underscoring Z..."*. → Split into clear independent sentences. |
| 4 | **Promotional Adjectives** | Content | *"nestled"*, *"breathtaking"*, *"stunning"*, *"renowned"*, *"paramount"*, *"indispensable"*. → Cut hyperbole; describe features objectively. |
| 5 | **Vague Attributions** | Content | *"Experts believe"*, *"Studies show"*, *"Industry reports indicate"*. → Name the author/group and year (e.g., *Smith et al., 2024*). |
| 6 | **Formulaic Challenges** | Content | *"Despite challenges... continues to thrive"*, *"While hurdles remain, the promise is undeniable"*. → State specific barriers and quantified outcomes. |
| 7 | **AI Vocabulary Clichés** | Language | *"delve"*, *"tapestry"*, *"landscape"*, *"testament"*, *"seamless"*, *"beacon"*, *"multifaceted"*. → Substitute with direct, precise verbs and nouns. |
| 8 | **Copula Avoidance** | Language | Using *"serves as"*, *"boasts"*, *"features"*, *"acts as"* instead of simple *"is"* or *"has"*. → Use plain copula verbs (*is*, *are*, *has*). |
| 9 | **Negative Parallelisms** | Language | *"It's not just about X; it's about Y."*, *"Not only did it improve X, but it also revolutionized Y."* → State what it does plainly. |
| 10 | **Rule of Three Clichés** | Language | Triadic grouping: *"innovation, inspiration, and insights"*, *"efficiency, scalability, and resilience"*. → Keep only the relevant concepts. |
| 11 | **Synonym Cycling** | Language | Rapidly cycling synonyms (*"the protagonist... the central figure... the main character..."*). → Use consistent, precise terminology. |
| 12 | **False Ranges** | Language | Stacking extremes: *"from the Big Bang to dark matter"*, *"from basic cells to complex ecosystems"*. → State the actual scope accurately. |
| 13 | **Em Dash Overuse** | Style | Excessive em dashes (`—`) cluttering sentences. → Limit to at most one per page; use commas, parentheses, or separate sentences. |
| 14 | **Mechanical Boldface** | Style | **Randomly** **bolding** **every** **keyword** in paragraphs. → Reserve bolding strictly for structural headings or defined clinical terms. |
| 15 | **Inline-Header Lists** | Style | Over-relying on `- **Concept:** Description` bullet lists for everything. → Convert into flowing, cohesive narrative paragraphs. |
| 16 | **Title Case Clichés** | Style | Capitalizing Every Single Word In Normal Subheadings. → Use standard sentence case for subheadings. |
| 17 | **Emoji Overuse** | Style | Decorating text with 🚀💡✅📊🩺. → Eliminate completely in academic, clinical, and formal writing. |
| 18 | **Curly Quote Inconsistency** | Style | Mixing `“` `”` with `"` inconsistently. → Standardize quotation marks across the text. |
| 19 | **Chatbot Artifacts** | Tone | *"I hope this helps!"*, *"Let me know if you need anything else!"*, *"Certainly!"* → Cut conversational conversational pleasantries entirely. |
| 20 | **Cutoff Disclaimers** | Tone | *"As of my last training update..."*, *"While literature is limited..."* → Speak authoritatively based on verified cited sources. |
| 21 | **Sycophantic Openers** | Tone | *"Great question!"*, *"You've made an excellent point!"*, *"Indeed!"* → Jump straight into the substantive analysis. |
| 22 | **Filler Prepositional Bloat** | Filler | *"In order to"* (→ *to*), *"Due to the fact that"* (→ *because*), *"At this point in time"* (→ *currently* / *now*). → Trim ruthlessly. |
| 23 | **Excessive Hedging** | Filler | Stacking hedges: *"could potentially possibly suggest that it might arguably indicate..."* → Calibrate to a single clear qualification: *"suggests that..."*. |
| 24 | **Generic Utopian Conclusions** | Filler | *"The future looks bright."*, *"Exciting times lie ahead."*, *"Only time will tell what lies on the horizon."* → Conclude with concrete next steps or research gaps. |

---

## Statistical Signals: Human vs. LLM

| Signal | Human Baseline | AI / LLM Baseline | Remediation Rule |
|---|---|---|---|
| **Burstiness** | High (0.5–1.0) | Low (0.1–0.3) | Alternate punchy short sentences (5–9 words) with compound analytical sentences (20–30 words). Avoid uniform sentence lengths. |
| **Type-Token Ratio (TTR)** | 0.5–0.7 | 0.3–0.5 | Expand vocabulary diversity; avoid repeating favorite transitional adverbs (*moreover*, *furthermore*, *crucial*). |
| **Sentence Length Variance** | High CoV (>0.45) | Low CoV (<0.25) | Break up monotone rhythms. Introduce rhythmic diversity. |
| **Trigram Repetition** | Low (<0.04) | High (>0.09) | Eliminate repetitive three-word phrases (*"plays an important"*, *"in terms of"*, *"it is essential"*). |

---

## Vocabulary Tiers & Forbidden Words

### Tier 1: Dead Giveaways (Zero-Tolerance Banned in Final Drafts)
> `delve` • `tapestry` • `vibrant` • `crucial` • `comprehensive` • `meticulous` • `embark` • `robust` • `seamless` • `groundbreaking` • `leverage` • `synergy` • `transformative` • `paramount` • `multifaceted` • `myriad` • `cornerstone` • `reimagine` • `empower` • `catalyst` • `invaluable` • `bustling` • `nestled` • `realm` • `unwavering` • `beacon` • `testament` • `pivotal` • `underscore`

### Tier 2: Suspicious When Clustered (Limit strictly, max 1 per 2,000 words)
> `furthermore` • `moreover` • `paradigm` • `holistic` • `utilize` • `facilitate` • `nuanced` • `illuminate` • `encompasses` • `catalyze` • `proactive` • `ubiquitous` • `quintessential` • `foster` • `spearhead` • `dynamic`

### Forbidden AI Cliché Phrases
- *"In today's fast-paced digital age / rapidly evolving landscape..."*
- *"It is worth noting that / It is important to emphasize that..."*
- *"Plays a pivotal / crucial role in the realm of..."*
- *"Serves as a testament to..."*
- *"Without further ado..."*
- *"A double-edged sword..."*
- *"At the forefront of innovation..."*

---

## Medical & Academic Writing Style (Dr. Noora Noureldin Rules)

When humanizing academic papers, medical theses, and systematic reviews:

1. **Lead with Data and Inverted Pyramid**:
   - Begin paragraphs with the primary empirical result or direct clinical implication, not with broad generic philosophical throat-clearing.
2. **Precision Over Grandiosity**:
   - Write *"HbA1c decreased by 0.8% (p = 0.002)"* instead of *"The therapy demonstrated groundbreaking efficacy in glycemic management"*.
3. **Active Voice for Author Actions, Passive for Standard Methods**:
   - *"We recruited 120 patients"* (Active for author choices)
   - *"Blood samples were centrifuged at 3000 rpm for 10 min"* (Passive for standard laboratory protocols)
4. **Respect the Inverted Funnel in Discussion**:
   - Para 1: Principal finding.
   - Para 2–N: Mechanism, comparison with prior literature (agreement/disagreement), biological plausibility.
   - Penultimate: Strengths and clinical limitations.
   - Final: Unanswered questions and concrete future directions.

---

## Before & After Transformation

### ❌ AI-Generated Draft (Slop & Formulaic)
> *Great question! In today's rapidly evolving biomedical landscape, SGLT2 inhibitors serve as a testament to groundbreaking innovation, playing a pivotal role in multifaceted renal protection. Furthermore, it is important to note that these revolutionary agents not only delve into glycemic control, but they also empower clinicians to seamlessly combat diabetic kidney disease. Despite challenges, the future of nephrology looks bright. I hope this helps!*

### ✅ Humanized & Academic Refinement
> *SGLT2 inhibitors reduce the risk of progression to end-stage kidney disease by 37% in patients with type 2 diabetes (EMPA-KIDNEY, 2023). This nephroprotective benefit operates primarily through reducing intraglomerular pressure via tubuloglomerular feedback rather than blood glucose lowering alone. However, eGFR decline often accelerates during the first two weeks of initiation before stabilizing—a hemodynamic effect clinicians must distinguish from acute tubular injury.*

---

## Execution Workflow

When humanizing any text:

1. **Scan & Flag**: Check against the 24 patterns and 3 vocabulary tiers.
2. **Measure Rhythm**: Calculate or inspect sentence length variation; break up uniform 20-word sentences into 8-word punches and 25-word compound explanations.
3. **Surgically Replace**: Substitute Tier 1/2 clichés with simple, exact terms (*utilize* → *use*, *serves as* → *is*).
4. **Remove Fluff**: Delete throat-clearing openers (*"It is important to note that..."*).
5. **Preserve Rigor**: Retain all mathematical notation, p-values, sample sizes, and citations without modification.
6. **Read Aloud Check**: Confirm the text sounds authoritative, natural, and like a domain expert speaking directly to peer reviewers.
