---
name: pptx
description: Build and edit 16:9 PowerPoint decks with native, editable shapes, and fill figure slots with sourced images through MedDraft's quota-aware Google Images chain (SerpApi, Brave, optional legacy Google CSE, Playwright fallback). Use for lecture decks, seminar or thesis-defence slides, journal-club talks, figure-led teaching decks, or any request that mentions PowerPoint, PPTX, slides, a deck, or a presentation.
license: MIT
---

> **Mirror note:** this pack ships twice, at `meddraft_ai/prompts/pptx/` (pipeline
> registry) and `.agents/skills/pptx/` (agent skill). Keep the two copies
> byte-identical; `skills-lock.json` pins the agent copy, and
> `tests/test_pptx_deck_builder.py` reads the pipeline copy.

# PPTX deck building with sourced figures

Two jobs live here:

1. **Build a deck** from a JSON blueprint with the local design engine, so every
   slide is editable text and shapes rather than a flattened screenshot.
2. **Fill figure slots** with real images, searched through a provider chain
   that spends free tiers in order and falls back to a keyless Playwright
   scrape. Every downloaded image keeps a provenance record for attribution.

The design language is ported from **Noora_PPT Builder**: 16:9 canvas, blank
layouts, one accent colour, generous margins, thin rules, a highlighted takeaway
panel, and speaker notes on every slide.

## When to use

Use this skill when the user asks for:

- a lecture, seminar, journal-club, or thesis-defence deck;
- slides from a paper, report, outline, or topic brief;
- visual teaching material where anatomy, histology, devices, procedures, or
  pathology need illustrative figures;
- edits to an existing `.pptx` that keep it editable.

Do **not** use it for a research poster (use `pptx-posters` or
`latex-posters`), a manuscript figure (use `figure-planner` / `figure-style`),
or a plain document (use `docx`).

## Ground rules

- **Native shapes, not screenshots.** Text must remain editable in PowerPoint.
- **One accent colour per deck.** Default teal `#0E7C86`; override only with a
  reason (institutional brand, topic convention).
- **Six slide kinds only:** `cover`, `agenda`, `section`, `content`, `figure`,
  `summary`. If a slide does not fit one, split it.
- **Two to three bullets per content slide.** If the material needs more, make
  another slide. Never shrink below 13 pt to win an argument with the layout.
- **No lorem ipsum and no empty placeholders.** A `figure` slide without an
  image must either be filled or removed.
- **Every searched image carries provenance.** A credit line on the slide and the
  source page in the sidecar JSON. User-supplied files should get a credit too.
  If the licence is unclear, say so to the user before publishing.
- **Speaker notes are part of the deliverable.** Write the sentence the speaker
  should say, not a restatement of the bullet.

## Workflow

### 1. Blueprint first

Write a blueprint JSON before touching PowerPoint. The schema and a worked
example are in [`references/blueprint-schema.md`](references/blueprint-schema.md).

```bash
python meddraft_ai/prompts/pptx/scripts/deck_builder.py --example > deck.json
python meddraft_ai/prompts/pptx/scripts/deck_builder.py deck.json --check
```

Plan the narrative explicitly:

| Slide | Job |
|---|---|
| `cover` | Title, subtitle, source list, no bullets |
| `agenda` | 3 to 5 numbered stops, one line each |
| `section` | Section number and title, no body text |
| `content` | One claim as the title, 2 to 3 evidence bullets, one takeaway |
| `figure` | One image, a short caption, 2 to 3 reading cues |
| `summary` | 3 to 4 takeaways, parallel wording |

`content` titles should be claims ("The sulcus is a dynamic interface"), not
labels ("Introduction"). The takeaway panel answers "so what".

### 2. Fill the figure slots

Figure slides declare a `query`. The fetch script searches, downloads, verifies,
converts unsupported formats, and writes the path back into the blueprint:

```bash
python meddraft_ai/prompts/pptx/scripts/fetch_figures.py --blueprint deck.json
```

What happens under the hood:

1. `search_images()` tries providers in order and skips exhausted free tiers
   using the local quota ledger.
2. Candidates are ranked by required terms, excluded terms, preferred hosts,
   MIME type, and resolution.
3. The first candidate that satisfies the resolution floor is downloaded,
   verified with Pillow, and, if it is WebP or AVIF, re-encoded as PNG.
4. A `<figure>.json` sidecar stores the query, provider, image URL, source page,
   dimensions, and SHA-256.

Options that matter:

```bash
# Inspect what is configured and how much free quota remains locally
python -m meddraft_ai.cli refs image-providers

# Search only, no download
python meddraft_ai/prompts/pptx/scripts/fetch_figures.py --blueprint deck.json --dry-run

# Prefer authoritative hosts and reject clip art
python meddraft_ai/prompts/pptx/scripts/fetch_figures.py \
  --blueprint deck.json \
  --require-term histology \
  --prefer-host ncbi.nlm.nih.gov \
  --prefer-host commons.wikimedia.org \
  --exclude-term cartoon

# One-off lookup
python meddraft_ai/prompts/pptx/scripts/fetch_figures.py \
  --query "gingival sulcus histology" --out-dir figures --limit 5
```

If the user has already attached images, place them in `figures/` and set
`image_path` directly; skip the search entirely.

#### Agent tool binding

The search is already exposed as an OpenAI-style tool. Bind the schema and the
dispatcher without translation:

```python
from meddraft_ai.search import (
    get_image_search_tool_schema,
    execute_image_search_tool,
    IMAGE_SEARCH_TOOL_NAME,  # "search_google_images"
)

tools = [get_image_search_tool_schema()]
result = execute_image_search_tool({"query": "cortical bone histology", "num_results": 3})
```

Then download the chosen `image_url` with
`meddraft_ai.search.image_fetch.download_image()`, or let `fetch_figures.py`
do both steps. The tool description already tells the model to use literature
tools for papers and this tool only for images.

#### Provider chain and quotas

| Order | Provider | Free tier (local ledger) | Credentials |
|---|---|---|---|
| 1 | SerpApi Google Images | 100 searches / month | `SERP_API_KEY` or `SERPAPI_API_KEY` |
| 2 | Brave Images API | 2,000 queries / month | `BRAVE_API_KEY` |
| 3 | Playwright Google Images scrape | no key, slower, CAPTCHA risk | Node.js + built browser engine |
| opt-in | Google Custom Search JSON API (legacy) | 100 queries / day, grandfathered projects only | `GOOGLE_CSE_API_KEY` + `GOOGLE_CSE_ID` |

Google closed the Custom Search JSON API to new customers and will stop serving
existing access on 2027-01-01, so `google_cse` is **not** in the default chain.
Enable it explicitly only if the project already had access.

- The ledger lives at `.cache/image_search_quota.json` by default. Override with
  `IMAGE_SEARCH_QUOTA_FILE`; disable with `IMAGE_SEARCH_QUOTA_ENABLED=false`.
- On HTTP 429 the provider gets a cooldown and the chain moves on. Search
  failures never raise; they are reported in `attempts`.
- Force a different order with `IMAGE_SEARCH_PROVIDER_ORDER` or
  `--provider-order`.
- The ledger is local. It cannot see usage from another machine sharing the key,
  so the provider dashboard remains authoritative.

Full details, including the failure matrix and medical query recipes, are in
[`references/figure-sourcing.md`](references/figure-sourcing.md).

### 3. Build

```bash
python meddraft_ai/prompts/pptx/scripts/deck_builder.py deck.json -o talk.pptx
```

The engine:

- sets a 16:9 canvas (13.333 x 7.5 in) and blank layouts;
- fits title and body text to the box instead of overflowing;
- places figures with aspect-fit inside a framed panel and prints the credit;
- adds page numbers, a source footer, and speaker notes;
- degrades a broken slide to a readable title slide instead of failing the deck.

Preview the JSON returned by `--json`: `warnings` flags missing bullets, figure
slots without an image, and unknown slide kinds.

### 4. Quality gate

Run this checklist before showing the deck:

- [ ] Every title is a claim or a clear label, not a vague noun.
- [ ] No slide has more than 3 body bullets or text below 13 pt.
- [ ] Every figure slide has an image, a caption, and a credit line.
- [ ] The credit line and sidecar point to a source page the user can open.
- [ ] Image resolution is at least 800 x 600; no stretched or cropped labels.
- [ ] Anatomy and histology images match the structure named in the slide.
- [ ] Speaker notes say something the slide does not.
- [ ] A dark slide is not followed by another dark slide by accident.
- [ ] `--check` returns no warnings, or each warning is deliberate.

If LibreOffice is installed, render a contact sheet and read it:

```bash
soffice --headless --convert-to pdf talk.pptx
pdftoppm -png -r 70 talk.pdf slide
```

Check for clipped text, overlapping shapes, and images that lost their labels
at slide scale.

## Editing an existing deck

Keep the file editable by working at the OOXML level, not by re-screenshotting:

```bash
python meddraft_ai/prompts/docx/ooxml/scripts/unpack.py deck.pptx unpacked/
# edit ppt/slides/slideN.xml, ppt/notesSlides/notesSlideN.xml, or ppt/media/
python meddraft_ai/prompts/docx/ooxml/scripts/validate.py unpacked/ --original deck.pptx
python meddraft_ai/prompts/docx/ooxml/scripts/pack.py unpacked/ deck-edited.pptx
```

Validate after every edit. The OOXML tooling is shared with the `docx` pack.

For template-driven decks, extract the template text and theme first, then map
content to existing layouts. Do not invent a layout the template does not have.

## Image policy for medical teaching

- **Prefer primary and public-domain sources:** NIH, NCI, CDC, NLM, Wikimedia
  Commons, OpenStax, university teaching repositories.
- **Publisher figures are usually off limits.** Do not embed a figure from a
  paywalled article or a textbook PDF unless the user confirms permission.
- **Devices and products:** photographs are often trademarked. Keep the credit
  and avoid implying endorsement.
- **Patients:** reject any image with identifiable faces or records unless the
  user confirms consent. Prefer illustrations for clinical signs.
- **Accuracy over prettiness.** A correct schematic beats a dramatic stock
  photo. If no trustworthy image exists, draw a labelled schematic or say so.
- **Never let the model "remember" a figure.** Search or use a user-supplied
  file; do not fabricate an image path.

## Files

| Path | Purpose |
|---|---|
| `scripts/deck_builder.py` | Blueprint to `.pptx` design engine |
| `scripts/fetch_figures.py` | Search, download, provenance, blueprint write-back |
| `references/blueprint-schema.md` | Full blueprint schema and example |
| `references/figure-sourcing.md` | Providers, quotas, ranking, failure handling, query recipes |

Related skills: `scientific-slides` for talk structure and timing,
`figure-planner` / `figure-style` for manuscript figures, `docx` for the shared
OOXML pack/unpack/validate scripts.
