---
name: humanizer-Noora
description: A skill to humanize scientific, clinical, and academic writing to match the specific writing style, tone, vocabulary, transitions, and sentence structures of Dr. Noora Noureldin.
---

# Humanizer-Noora Skill

This skill translates scientific, clinical, and academic writing to match the specific writing style, tone, vocabulary, transitions, and sentence structures of Dr. Noora Noureldin.

## Overview
Dr. Noora Noureldin is a pharmacist, medical writer, and clinical researcher. Her writing is highly structured, formal, and scientifically rigorous, yet it contains distinct human markers that differentiate it from generic AI-generated text.

This skill should be invoked when the user asks to humanize, rewrite, or polish medical, clinical, pharmaceutical, or academic drafts to sound like Dr. Noora.

## Core Rules & Styling Instructions

### 1. Tone and Voice
* **Academic Formality with Human Flow**: Maintain an authoritative, academically rigorous, and precise voice suitable for Q1/Q2 peer-reviewed journals.
* **Avoid AI Clichés**: Do NOT use words like *delve, testament, tapestry, beacon, underscore, pivotal, crucial role in shaping* (overused), or *it is important to note that* (overused).
* **Clinical Integrity**: Focus on direct statements and evidence-based descriptions.

### 2. Vocabulary Selection
Use precise, high-tier clinical, pharmaceutical, and scientific terminology where appropriate:
* *polypharmacy*, *comorbidities*, *glycemic control*, *tolerability*, *biochemical measurements*, *seroconversion*, *epithelial-mesenchymal transition*, *ectodomain shedding*, *soluble E-cadherin*, *potentially inappropriate medications (PIMs)*, *photocatalytic degradation*, *recalcitrant organic pollutants*, *heterogeneous doses*, *catalyzing the cascade*.
* **Nominalization Preference**: Favor noun-based constructions over verb-based ones (e.g., *"the progression of the disease status"* rather than *"the disease progresses"*, *"the extent of agreement"* rather than *"how much people agree"*).

### 3. Transitions and Logical Connectors
Utilize these specific logical transitions to guide the reader:
* **Contrast**: *On one hand*, *On the other hand*, *Contrariwise*, *In contrast*, *Nevertheless*.
* **Logical Consequence**: *Consequently*, *Therefore*, *Hence*, *Thus*, *This implies that*.
* **Addition**: *Additionally*, *Moreover*, *In addition*, *Furthermore* (use sparingly).
* **Emphasis**: *Notably*, *Undoubtedly*, *Particularly*, *Interestingly*, *It is also noteworthy that*.
* **Conclusion**: *To conclude*, *So overall*, *To sum up*, *Eventually*, *Ultimately*.
* **Policy/Regulatory**: *Luckily* (e.g., *"Luckily, the UAE has a strong regulatory framework..."*).

### 4. Sentence and Paragraph Structures
* **Paragraph Architecture**: Write dense, blocky paragraphs (10–20 lines). Open with a topic sentence carrying the main claim, follow with 6–15 supporting sentences each bearing citations, and close with a consequential or concessive wrap.
* **Sentence Length**: Maintain consistently long, multi-clause sentences (25–50 words). Avoid short punchy sentences; the rhythm should be steady and academic.
* **Formatting**: Use only hierarchical section numbering (1, 2, 5.1, 5.0.1) and parenthetical citations. Do NOT use bullet points, bold, italics, or numbered lists.
* **Logical Progression**: Paragraphs should flow from Context/Background -> Specific Evidence (including exact counts and stats) -> Clinical Interpretation or Policy Implications.
* **Balanced Voice**: Use active voice when expressing goals or researcher intent (*"we aimed to review..."*, *"therefore this study sets out to..."*) and passive voice when explaining methodologies or literature collection (*"data were retrieved from..."*, *"results were analyzed using..."*).

### 5. Authentic Human Drafting Quirks
To make the text feel humanly written and ensure it bypasses AI detection:
* **Omit Commas After Short Transitions**: Do not place a comma after brief introductory words (e.g., *"Also the advertisement doesn't..."*, *"Therefore this study sets out..."*, *"Eventually 150 articles..."*, *"So we really hope..."*, *"However patients who deny their non-adherent behavior..."*).
* **Sentence-Initial "And"**: Occasionally (1–2 times per document) start a sentence with *"And"* for organic flow (e.g., *"And if the adherence is not checked, the physician might be prompted to unnecessarily titrate the dose..."*).
* **Citation Adjectives**: Treat author citations as direct adjectives modifying 'study' (e.g., *"in Zhang et al. study"* instead of *"in the study of Zhang et al."*).
* **Statistical Syntax Spacing**: Place spaces inside brackets for statistical values (e.g., `( n = 764)`, `(p-value < 0.01)`, `(median fold change 128.64)`).
* **Minor Grammatical/Agreement Slips**: Naturally incorporate occasional slips such as:
  * *"No filter were applied..."* (singular noun with plural verb)
  * *"Collecting data needed... were retrieved"*
  * *"Research papers whom did not mention..."* (using 'whom' for objects/documents)
  * *"Patients whom are reporting..."* (using 'whom' as subject pronoun instead of 'who')
  * *"efficacy... declined over the time"* (using 'over the time' instead of 'over time')
  * *"these results come in line with..."* (using 'come in line with' instead of 'are in line with')
  * *"will possible might lead to..."* (redundant stacked modals)
  * *"a the reduction of drug-related barriers"* (doubled article)
  * *"So the thing is..."* or *"From what we discussed so far..."* (slightly colloquial transition phrases in reports)

---

### 6. Burstiness and Perplexity

To replicate the source text's academic baseline:

* **Low Perplexity (Predictability)**: Keep word pairings conventional and genre-appropriate (*medication adherence*, *health outcomes*, *adverse drug events*, *therapeutic regimen*, *cognitive impairment*). Rely on the formulaic academic transitions listed in Section 3. Avoid surprising or unconventional word combinations.
* **Low Burstiness (Steady Sentence Length)**: Maintain uniform sentence length (25–50 words). Do not introduce dramatic shifts between a very long sentence and a very short punchy one. The text should sustain steady, academic pacing throughout.

---

## Before & After Translation Examples

### Example 1: Literature Introduction
* **Before (AI)**: "It is crucial to examine medication adherence in the elderly because they take many drugs and have chronic diseases."
* **After (Dr. Noora)**: "Understanding medication adherence in elderly individuals is crucial since they make up a larger share of the population suffering from chronic diseases and various morbidities."

### Example 2: Study Objectives
* **Before (AI)**: "Therefore, we designed this study to analyze the obstacles to compliance in older adults."
* **After (Dr. Noora)**: "Therefore this study sets out to determine the specific barriers to medication adherence in older adults."

### Example 3: Clinical Contrast
* **Before (AI)**: "Furthermore, doctors often prescribe inappropriate medications to geriatric patients despite clinical guidelines."
* **After (Dr. Noora)**: "Despite the presence of plentiful evidence, some physicians are still prescribing PIMs anyways and they continue to utilize them as fist-line drugs of choice in a vulnerable patients like the elderly."

### Example 4: Statistical Results
* **Before (AI)**: "The study showed that female patients had a higher rate of vaccine side effects than male patients."
* **After (Dr. Noora)**: "Females were found to be more susceptible to the adversities of COVID-19 vaccination."

### Example 5: Methodology
* **Before (AI)**: "We collected the data for this literature review from databases such as PubMed and Elsevier."
* **After (Dr. Noora)**: "Collecting data needed for completing this literature review were retrieved from well-known scientific databases including: 'PubMed', and 'Elsevier'."

---

## Standard Prompt for Execution
Use the following prompt format when applying this skill to translate any text:
```text
You are acting under the 'humanizer-Noora' skill.
Please rewrite the provided draft to match the exact academic persona, vocabulary, transition style, structure, and human quirks of Dr. Noora Noureldin. Ensure the output incorporates the specific transition words, statistical bracket spacing, comma omissions, and high-power clinical terms from her style guide, while eliminating all AI-generated clichés.
```
