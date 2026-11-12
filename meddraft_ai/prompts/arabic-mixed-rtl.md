---
name: arabic-mixed-rtl
description: Repair and format mixed Arabic/English Word documents (.docx) with bulletproof APA 7th citation handling. Eliminates flipped parentheses, fragmented citations (e.g., "(Author) & (2020)"), detached punctuation, and jumping numbers in RTL environments. Employs template cloning, regex-based APA citation isolation, and character-class run chunking.
---

# Arabic Mixed-Direction Line Repair & APA 7th Engine

Goal: Every mixed Arabic/English line renders in clean visual order. APA 7th parenthetical and narrative citations remain unified, parentheses never invert, and inline Latin terms never disrupt the right-to-left sentence flow.

**Routing:** selected automatically by `SkillRegistry.match_skill_for_task()` whenever a request mixes Arabic and Latin script, or names Arabic/RTL document work (`meddraft_ai/core/language_routing.py`); also reachable by name via `get_skill("arabic-mixed-rtl")`.

## 1. When to Use

| Situation | Action |
| :--- | :--- |
| Existing Arabic `.docx` has inverted `()`, broken citations, split years | **Use this skill** (re-chunk runs & isolate citations) |
| Authoring a mixed Arabic-English paper using APA 7th referencing | **Use this skill** (guarantees citation integrity) |
| Producing a final report matching an approved institutional style | **Use this skill** (clone template, inject clean XML) |

---

## 2. Core Architectural Rules

1. **APA Citation Atomicity (Primary Rule):**
   A citation like `(Alexander, 2020; Mercer & Howe, 2012)` or `(Hattie & Timperley, 2007)` must **never** be chunked into separate runs. The opening paren, author names, ampersands, commas, year, semicolon, and closing paren must reside in a **single LTR run**.
2. **Narrative Citation Isolation:**
   When an English author is cited narratively in Arabic text (e.g., `يشير Hattie و Timperley (2007)`):
   - Keep English names in a Latin run.
   - Keep Arabic conjunctions (like `و`) in an Arabic run.
   - Wrap the parenthetical year `(2020)` in an isolated Latin run so the parentheses do not jump across the Arabic conjunction.
3. **No Script Sharing in Runs:**
   Arabic and Latin glyphs must never share a `<w:r>`.
4. **Punctuation Ownership:**
   - Parentheses enclosing English text belong inside the Latin run: `(Think-Write-Pair-Share)`.
   - Parentheses enclosing purely Arabic text remain in the Arabic run: `(أكاديمية الشارقة للتعليم)`.
5. **Template Preservation:**
   Always clone the reference `.docx`. Strip only target body paragraphs (`<w:p>`), while keeping styles, numbering, headers/footers, and page sections (`w:sectPr`).

---

## 3. The Improved APA-Aware Chunker

The previous naive character-class chunker broke when an ampersand or symbol separated English words near Arabic text. The improved engine uses a **two-pass tokenizer**:

1. **Pass 1 (Pre-extraction):** Extracts full parenthetical APA citations, DOIs, URLs, and inline parenthesized English terms using regex.
2. **Pass 2 (Run Tokenization):** Runs the Latin/Arabic boundary chunker on remaining text and re-integrates the protected tokens.

```python
import re

# Strict regex matching APA parenthetical citations and Latin parenthesized phrases
# Matches: (Author, 2020), (Author & Author, 2020; Other, 2019), (Author, 2020, p. 15), (Term in English)
RE_APA_PAREN = re.compile(
    r"\(\s*[A-Za-z][A-Za-z0-9\s.,;:\-&/–—'\"]*?[A-Za-z0-9]\s*\)"
)

# Matches years in narrative citations: (2020), (2021a), (1998, p. 12)
RE_YEAR_PAREN = re.compile(r"\(\s*\d{4}[a-z]?(?:,\s*p{1,2}\.\s*\d+)?\s*\)")

LATIN_CHAR_SET = set(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    " .,;:!?()[]{}-_+=<>|/%@#$^*'\""
    "\u2013\u2014\u2018\u2019\u201C\u201D\u2026"
)

def chunk_mixed_text(text: str):
    """
    Splits mixed Arabic-English text into a list of tuples: [('ar'|'lat', string)]
    Ensures APA citations and parenthetical English terms never invert or split.
    """
    if not text:
        return []

    # Step 1: Identify and protect atomic Latin/APA spans
    protected_spans = []
    for match in list(RE_APA_PAREN.finditer(text)) + list(RE_YEAR_PAREN.finditer(text)):
        # Verify it has at least one Latin letter or digit and no Arabic characters
        matched_str = match.group(0)
        if not re.search(r"[\u0600-\u06FF\u0750-\u077F\uFB50-\uFDFF\uFE70-\uFEFF]", matched_str):
            protected_spans.append((match.start(), match.end(), matched_str))

    # Sort spans and remove overlaps
    protected_spans.sort(key=lambda x: x[0])
    merged_spans = []
    last_end = -1
    for s, e, val in protected_spans:
        if s >= last_end:
            merged_spans.append((s, e, val))
            last_end = e

    # Step 2: Split text into protected blocks vs general text
    segments = []
    curr = 0
    for s, e, val in merged_spans:
        if s > curr:
            segments.append(("text", text[curr:s]))
        segments.append(("lat_protected", val))
        curr = e
    if curr < len(text):
        segments.append(("text", text[curr:]))

    # Step 3: Run the character chunker on unprotected text
    final_runs = []
    for kind, val in segments:
        if kind == "lat_protected":
            final_runs.append(("lat", val))
            continue

        groups, cur, lat = [], [], None
        for ch in val:
            is_lat = ch in LATIN_CHAR_SET
            if lat is None:
                cur, lat = [ch], is_lat
            elif is_lat == lat:
                cur.append(ch)
            else:
                groups.append(("".join(cur), lat))
                cur, lat = [ch], is_lat
        if cur:
            groups.append(("".join(cur), lat))

        buf = ""
        for g, is_lat in groups:
            # Only promote to Latin if it contains Latin letters or numbers
            if is_lat and (re.search(r"[A-Za-z]", g) or re.search(r"[0-9]", g)):
                if buf:
                    final_runs.append(("ar", buf))
                    buf = ""
                final_runs.append(("lat", g))
            else:
                buf += g
        if buf:
            final_runs.append(("ar", buf))

    # Step 4: Merge adjacent runs of identical direction
    compact_runs = []
    for direction, content in final_runs:
        if not content:
            continue
        if compact_runs and compact_runs[-1][0] == direction:
            compact_runs[-1] = (direction, compact_runs[-1][1] + content)
        else:
            compact_runs.append((direction, content))

    return compact_runs
```

---

## 4. Run Specifications & WordprocessingML Emission

When emitting runs into OpenXML:

1. **Paragraph Properties (`w:pPr`):**
```xml
<w:pPr>
    <w:bidi/>
    <w:spacing w:after="120" w:line="276" w:lineRule="auto"/>
</w:pPr>
```

2. **Arabic Run (`w:r`):**
```xml
<w:r>
    <w:rPr>
        <w:rFonts w:cs="Traditional Arabic" w:ascii="Traditional Arabic" w:hAnsi="Traditional Arabic"/>
        <w:rtl/>
        <w:sz w:val="26"/>
        <w:szCs w:val="26"/>
    </w:rPr>
    <w:t xml:space="preserve">الحديث الأكاديمي المنظم </w:t>
</w:r>
```

3. **APA Latin Run (`w:r`):**
```xml
<w:r>
    <w:rPr>
        <w:rFonts w:ascii="Calibri" w:hAnsi="Calibri" w:cs="Calibri"/>
        <!-- w:rtl MUST NOT be present -->
        <w:sz w:val="22"/>
        <w:szCs w:val="22"/>
    </w:rPr>
    <w:t xml:space="preserve">(Hattie &amp; Timperley, 2007)</w:t>
</w:r>
```

---

## 5. APA 7th Reference List Processing

In the `References` / `قائمة المراجع` section:

* Latin reference entries must have their paragraph direction set to LTR (`<w:jc w:val="left"/>` and **no** `<w:bidi/>`).
* Apply a hanging indent to all entries:
```xml
<w:pPr>
    <w:ind w:left="720" w:hanging="720"/>
</w:pPr>
```
* Titles of books, journal volumes, and report titles must maintain `<w:i/>` italic styling.
* Exception (template precedence): when cloning an institutional template per Rule 5, mirror the template's own reference-list style (e.g. numbered `ListParagraph`) instead of imposing the layout above.

---

## 6. Pre-Delivery Quality Checklist

* [ ] **No Inverted Citation Parens:** Zero instances of `)Author, Year(` or `Author) & (Year`.
* [ ] **Ampersand Cohesion:** Expressions like `Mercer & Howe` never break across runs.
* [ ] **Clean Narrative Years:** In expressions like `يوضح Alexander (2020)`, `Alexander` and `(2020)` stay visually linked.
* [ ] **XML Special Characters:** Every `&`, `<`, `>` in runs is escaped as `&amp;`, `&lt;`, `&gt;`.
* [ ] **Reference List Hanging Indent:** Reference entries have `w:hanging="720"` (0.5 inch / 1.27 cm).
* [ ] **Font Uniformity:** Arabic uses the reference body font (e.g., Traditional Arabic / Sakkal Majalla); Latin citations use the reference secondary font (e.g., Calibri / Times New Roman).
