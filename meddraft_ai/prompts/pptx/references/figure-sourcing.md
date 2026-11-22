# Figure sourcing: provider chain, quotas, and medical query practice

This is the operating manual behind `fetch_figures.py` and the
`search_google_images` tool. It explains how the chain spends free tiers, what
each failure means, and how to choose a defensible teaching image.

## Why a chain

An image search is a small, bursty workload. A single deck may need 5 to 12
figures, and one provider's monthly free tier can disappear in two afternoons.
The chain treats providers as interchangeable suppliers and keeps a local
ledger so a request goes to the cheapest available tier first:

```
SerpApi (100/month)
  -> Brave (2,000/month)
    -> Playwright scrape (no key)
```

Google Custom Search JSON API is a legacy tier: it is closed to new customers
and existing access ends 2027-01-01. It remains supported when explicitly
enabled, but it is not part of the default chain.

If a provider is unconfigured, exhausted, cooling down after a 429, or returns
zero usable results, the next one is tried. `attempts` in the response records
every provider and why it was skipped or failed.

## Provider reference

| Provider | Endpoint | Credentials | Free tier | Notes |
|---|---|---|---|---|
| `serpapi` | `https://serpapi.com/search.json` | `SERP_API_KEY` or `SERPAPI_API_KEY` | 100 searches/month | Best metadata: title, source page, original resolution |
| `brave` | `https://api.search.brave.com/res/v1/images/search` | `BRAVE_API_KEY` or `BRAVE_SEARCH_API_KEY` | 2,000 queries/month | 1 request/second; `safesearch` maps from the tool argument |
| `browser` | bundled Node CLI | Node.js + `meddraft_ai/search/browser_engine/dist/cli.js` | none | Emergency fallback; can hit consent walls, CAPTCHA, or slow loads |
| `google_cse` (legacy) | `https://www.googleapis.com/customsearch/v1` | `GOOGLE_CSE_API_KEY` (or `GOOGLE_API_KEY`) + `GOOGLE_CSE_ID` (or `GOOGLE_SEARCH_ENGINE_ID`, `GOOGLE_CX`) | 100 queries/day, grandfathered projects only | Closed to new customers; existing access ends 2027-01-01; 10 results per request |

Aliases accepted by `--provider-order`: `serp`, `serp_api`, `google`, `cse`,
`google-cse`, `playwright`, `scrape`. Unknown names are ignored.

## Configuration

```bash
# Provider keys
SERP_API_KEY=
GOOGLE_CSE_API_KEY=
GOOGLE_CSE_ID=
BRAVE_API_KEY=

# Chain behavior
IMAGE_SEARCH_PROVIDER_ORDER=serpapi,brave,browser
IMAGE_SEARCH_TIMEOUT=20
IMAGE_SEARCH_BROWSER_TIMEOUT=150
IMAGE_SEARCH_QUOTA_ENABLED=true
IMAGE_SEARCH_QUOTA_FILE=.cache/image_search_quota.json
```

Inspect the effective state without exposing keys:

```bash
python -m meddraft_ai.cli refs image-providers
python -m meddraft_ai.cli refs image-providers --json
```

Each row reports whether the provider is configured, its free-tier limit, the
count used in the current period, and the reset date.

## Quota ledger

The ledger is a small JSON file, not a database:

```json
{
  "providers": {
    "serpapi": {"period": "2026-11", "used": 7, "cooldown_until": null},
    "brave": {"period": "2026-11", "used": 41, "cooldown_until": null}
  }
}
```

Rules:

- Counters are per provider per period: monthly for SerpApi and Brave, daily for
  the legacy Google CSE.
- A successful request increments the counter before the next provider is
  considered.
- A 429 or a quota-shaped error writes a cooldown and lets the chain continue.
- The ledger is local and best-effort. It cannot see usage from another machine
  or another tool sharing the key, so the provider dashboard is authoritative.
- Set `IMAGE_SEARCH_QUOTA_ENABLED=false` to ignore it (not recommended for
  shared keys).

## Ranking and filtering

`search_images()` and `fetch_figures.py` accept the same signals:

| Argument | Effect |
|---|---|
| `required_terms` | Terms that should appear in title or URL; missing terms heavily penalise a result |
| `optional_terms` | Terms that raise a result's rank |
| `exclude_terms` | Terms that disqualify a result (`--exclude-term` is repeatable) |
| `preferred_hosts` | Hosts that get a large rank boost, e.g. `ncbi.nlm.nih.gov` |
| resolution | High-resolution results rank above low; very small ones fall below the download floor |

Default excludes in `fetch_figures.py` are `clipart, cartoon, logo, icon,
emoji`. Override with `--exclude-term`; passing any value replaces the default
list.

`fetch_figures.py` also enforces a resolution floor before the file is accepted:
800 x 600 by default. Raise it for full-bleed figures; lower it only for
legitimate schematic diagrams that are vector-like and upscale cleanly.

## Response envelope

`search_images()` returns:

```json
{
  "success": true,
  "query": "gingival sulcus histology",
  "provider": "brave",
  "count": 3,
  "results": [
    {
      "title": "Junctional epithelium",
      "image_url": "https://.../full.jpg",
      "thumbnail_url": "https://.../thumb.jpg",
      "context_url": "https://.../page",
      "width": 1600,
      "height": 1200,
      "provider": "brave",
      "position": 1
    }
  ],
  "attempts": [
    {"provider": "serpapi", "status": "skipped", "reason": "not configured"},
    {"provider": "brave", "status": "success", "count": 3}
  ]
}
```

On total failure `success` is `false`, `results` is empty, and every attempt is
explained. The function does not raise for provider, network, quota, or browser
errors.

## Download and provenance

`download_image()` adds the file layer:

- rejects non-`http(s)` URLs;
- caps the body at 12 MB and checks `Content-Length` first;
- verifies bytes with Pillow and reads the true format, ignoring a lying
  `Content-Type`;
- rejects images below the width/height floor;
- writes to a `.part` file and renames atomically;
- converts WebP and AVIF to PNG because `python-pptx` cannot embed them;
- returns dimensions, byte count, format, and SHA-256.

`fetch_figures()` writes a sidecar beside each image:

```json
{
  "id": "slide-05-histology",
  "query": "gingival sulcus histology diagram",
  "title": "Junctional epithelium",
  "provider": "brave",
  "image_url": "https://.../full.jpg",
  "context_url": "https://.../page",
  "path": "figures/slide-05-histology.jpg",
  "width": 1600,
  "height": 1200,
  "format": "JPEG",
  "sha256": "...",
  "license_note": "Verify the hosting page's licence before publication; keep context_url for attribution.",
  "fetched_at": "2026-11-22T10:00:00+00:00",
  "tried": [{"rank": 1, "url": "...", "success": true, "error": null}]
}
```

Keep the sidecar with the deck. It is the audit trail when a reviewer asks where
a figure came from.

## Failure matrix

| Symptom | Meaning | Action |
|---|---|---|
| `not configured` | Key or CSE ID missing | Add the env var, or let the chain fall through |
| `HTTP 401/403` | Bad key, disabled API, or CSE without image search | Check the provider console; try the next tier |
| `HTTP 429` with cooldown | Free tier exhausted or rate limited | Chain moves on automatically; wait for reset |
| `quota` or `exceeded` in message | Provider counts this as quota | Same as 429 |
| `every candidate failed to download` | Ranking returned URLs, but hosts rejected or served non-images | Raise `--limit`, add `--prefer-host`, or search a different wording |
| `image width ... below the floor` | Thumbnails or small schematics only | Lower `--min-width` for diagrams, or choose another candidate |
| `Playwright browser engine unavailable` | Node missing or `dist/cli.js` not built | Install Node.js and run `npm install && npm run build` in `meddraft_ai/search/browser_engine` |
| `CAPTCHA` or consent wall | Browser fallback blocked | Use an API tier; do not hammer the scrape |

## Medical query recipes

Good queries name the structure, the modality, and the view. Bad queries name
the concept and return stock photos.

| Need | Query pattern | Useful constraints |
|---|---|---|
| Anatomy | `<structure> anatomy diagram labeled` | `--prefer-host commons.wikimedia.org`, `--exclude-term cartoon` |
| Histology | `<tissue> histology <stain> labeled` | `--require-term histology`, `--min-width 1000` |
| Pathology | `<condition> histopathology micrograph` | `--exclude-term cartoon`, `--prefer-host pathologyoutlines.com` |
| Microbiology | `<organism> Gram stain microscopy` | `--require-term stain` |
| Device | `<device name> photograph` or `<device> schematic` | Add the manufacturer only if a product shot is appropriate |
| Procedure | `<procedure> step by step illustration` | Prefer illustrations over operating-room photos |
| Radiology | `<modality> <region> <finding>` e.g. `CBCT mandibular canal` | `--prefer-host radiopaedia.org` |
| Epidemiology | `<measure> global map <year>` | Prefer WHO, CDC, IHME |
| Dental materials | `<material> SEM micrograph` | `--require-term SEM` |

Query hygiene:

- Put the structure first, then the modality: "periodontal ligament histology",
  not "histology of the thing that holds the tooth".
- Ask for "labeled" only when labels are legible at slide size. Otherwise the
  labels become noise and you should annotate the slide yourself.
- Use `--prefer-host` for authority, not for exclusion. A good image on an
  unexpected host should still be allowed to rank.
- Run `--dry-run` first when the wording is uncertain; it lists candidates
  without spending downloads or writing files.

## Licensing and attribution

| Source | Typical status | What to do |
|---|---|---|
| NIH, NCI, CDC, NLM | Mostly public domain | Credit the agency; still check the specific page |
| Wikimedia Commons | CC BY / CC BY-SA / public domain | Reproduce the licence and author in the credit line |
| OpenStax, university repositories | Usually CC BY | Credit author and institution |
| Journal articles | Publisher copyright | Do not embed without permission; link instead |
| Manufacturer sites | Copyrighted; trademarks | Use only for device identification, keep the credit |
| Random image search hits | Unknown | Treat as unlicensed until the source page says otherwise |

Minimum credit line on a slide:

```
Source: <author or agency>, <page title>, <URL> (<licence>)
```

If the licence is unknown, write `Licence: verify` and tell the user before the
deck is shared. The sidecar keeps the full URL so the check is reproducible.

## Privacy and safety

- Reject identifiable patients, faces, records, or operating-field photos unless
  the user confirms consent.
- Prefer illustrations for clinical signs and procedures.
- Keep `safe_search=active` unless the user explicitly needs otherwise.
- Do not send unpublished patient data or institution-confidential material in a
  query string.

## Programmatic use

```python
from meddraft_ai.search.image_fetch import fetch_figures

result = fetch_figures(
    [
        {"id": "sulcus", "title": "Sulcular epithelium", "query": "gingival sulcus histology labeled"},
        {"id": "junction", "query": "dentogingival junction diagram",
         "preferred_hosts": ["commons.wikimedia.org"]},
    ],
    "figures",
    limit=4,
    min_width=1000,
    min_height=700,
)
```

The result has `success`, `figures`, `failures`, and `providers`. A partial
success is still `success: True`; inspect `failures` before building the deck.

For a single image:

```python
from meddraft_ai.search.image_fetch import download_image
record = download_image(url, "figures/sulcus")
if not record["success"]:
    print(record["error"])
```

## Verifying the chain offline

The provider parsers and the dispatcher are covered by mocked tests:

```bash
pytest tests/test_image_search.py tests/test_image_fetch.py -v
```

No network calls are made. To exercise the real chain, start with
`refs image-providers` and a single one-off query, then check the ledger file to
confirm which tier was charged.
