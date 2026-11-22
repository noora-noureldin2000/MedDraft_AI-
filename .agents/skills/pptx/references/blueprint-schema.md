# Blueprint schema

A blueprint is one JSON object. `deck_builder.py` reads it and writes a `.pptx`.
All keys except `slides` are optional.

```json
{
  "title": "Gingival Sulcus: Structure and Clinical Relevance",
  "subtitle": "A visual walkthrough for the periodontology seminar",
  "author": "MedDraft_AI",
  "accent": "#0E7C86",
  "sources": ["Carranza's Clinical Periodontology", "PubMed review, 2024"],
  "slides": []
}
```

## Top-level keys

| Key | Type | Notes |
|---|---|---|
| `title` | string | Deck title; also written to document properties |
| `subtitle` | string | Cover subtitle |
| `author` | string | Document properties |
| `accent` | string | `#RRGGBB`; overrides the default teal |
| `sources` | string[] | First three appear on the cover; all go to properties |
| `slides` | object[] | Required unless you accept a one-slide cover |

## Slide kinds

Every slide has `kind` and `title`. Unknown kinds render as `content`.

Shared optional keys: `kicker` (small uppercase label), `subtitle`, `notes`
(speaker notes), `source` (footer line).

### `cover`

```json
{
  "kind": "cover",
  "kicker": "PERIODONTOLOGY",
  "title": "Gingival Sulcus: Structure and Clinical Relevance",
  "subtitle": "Histology, defence mechanisms, and probing depth",
  "sources": ["Carranza's Clinical Periodontology"],
  "notes": "Open with the clinical question that motivates the talk."
}
```

### `agenda`

Uses `bullets` (max 6, first 6 kept). Each becomes a numbered row.

```json
{"kind": "agenda", "title": "Agenda", "bullets": ["Anatomy", "Host defence", "Probing depth"]}
```

### `section`

A dark divider. The number is inferred from `kicker` digits, otherwise the page
number is used.

```json
{"kind": "section", "kicker": "SECTION 02", "title": "Host defence in the sulcus"}
```

### `content`

The workhorse: claim title, 2 to 3 bullets, optional takeaway panel.

```json
{
  "kind": "content",
  "kicker": "KEY CONTENT",
  "title": "The sulcus is a dynamic interface",
  "bullets": [
    "The sulcus is the space between tooth surface and free gingival margin.",
    "Junctional epithelium provides the primary seal.",
    "Sulcular fluid carries immunoglobulins and neutrophils."
  ],
  "takeaway": "Probing depth measures sulcus depth; attachment loss measures destruction.",
  "source": "Carranza's Clinical Periodontology, ch. 1",
  "notes": "Ask the audience to distinguish the two measurements before revealing the takeaway."
}
```

### `figure`

A two-column slide: reading cues on the left, framed image on the right.

```json
{
  "kind": "figure",
  "title": "Histology of the sulcular epithelium",
  "query": "gingival sulcus histology diagram",
  "image_path": "figures/slide-05-histology.png",
  "caption": "Sulcular and junctional epithelium at the dentogingival junction.",
  "credit": "Source: https://example.org/figure (CC BY 4.0)",
  "context_url": "https://example.org/figure",
  "bullets": ["Non-keratinised sulcular epithelium.", "Junctional epithelium is the seal."],
  "notes": "Point to the junctional epithelium before discussing permeability."
}
```

Behavior:

- `image_path` is resolved relative to the blueprint file, so a deck folder is
  portable.
- If the file is missing but `query` exists, the slide renders a labelled slot
  telling the reader to run `fetch_figures.py`.
- `caption` is drawn under the image; `credit` (falling back to `context_url`)
  is drawn beneath the caption.
- `bullets` become up to three reading cues, not a second content column.
- The image is aspect-fit; it is never stretched.

`fetch_figures.py` adds `figure_query`, `figure_provider`, `figure_sha256`, and
`context_url` when it fills a slot, and sets `credit` if absent.

### `summary`

Dark closing slide with up to four numbered takeaways.

```json
{
  "kind": "summary",
  "title": "Key takeaways",
  "bullets": ["The sulcus is an anatomical space.", "Host defence depends on epithelial integrity.", "Probing depth alone cannot separate health from attachment loss."]
}
```

## Validation rules

`deck_builder.py --check` returns warnings for:

- no `title`, no `slides`;
- unknown `kind`;
- `content`, `agenda`, or `summary` without `bullets`;
- `figure` without `image_path` or `query`;
- a `figure` with a query but no image (a reminder to run the fetch step).

Warnings do not stop a build. Treat them as a to-do list.

## Content rules that the engine cannot enforce

- One claim per `content` slide.
- Two to three bullets, each under about 140 characters.
- A takeaway that adds interpretation, not a repeat of the last bullet.
- Parallel wording across `summary` items.
- Speaker notes written as spoken sentences.

## Minimal valid blueprint

```json
{
  "title": "A three-slide deck",
  "slides": [
    {"kind": "cover", "title": "A three-slide deck"},
    {"kind": "content", "title": "One claim", "bullets": ["Evidence one.", "Evidence two."]},
    {"kind": "summary", "title": "Key takeaways", "bullets": ["Takeaway one."]}
  ]
}
```
