"""Turn image-search results into embeddable local files.

``image_search`` returns URLs; PowerPoint needs files on disk in a format
``python-pptx`` can embed. This module bridges that gap:

1. search the provider chain (SerpApi -> Brave -> Playwright, with legacy
   Google CSE available when explicitly enabled),
2. download candidate images with a byte cap and an http(s)-only guard,
3. verify them with Pillow, enforce a minimum resolution, and convert
   formats PowerPoint cannot embed (WebP, AVIF) to PNG,
4. write a JSON provenance record beside each file so a slide can credit the
   source and the deck stays auditable after the URLs rot.

Network, quota, and image-decode errors never raise; every failure is returned
in the envelope so the caller (agent or CLI) can explain what happened.
"""

from __future__ import annotations

import hashlib
import io
import json
import logging
import re
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from PIL import Image

from .image_search import MAX_RESULTS, search_images

logger = logging.getLogger(__name__)

# Formats python-pptx embeds directly. Anything else is re-encoded as PNG.
EMBEDDABLE_FORMATS = frozenset({"PNG", "JPEG", "GIF", "BMP", "TIFF"})

_FORMAT_SUFFIX = {
    "PNG": ".png",
    "JPEG": ".jpg",
    "GIF": ".gif",
    "BMP": ".bmp",
    "TIFF": ".tif",
    "WEBP": ".webp",
    "AVIF": ".avif",
}

DEFAULT_MAX_BYTES = 12_000_000
DEFAULT_TIMEOUT = 20.0
DEFAULT_EXCLUDE_TERMS = ("clipart", "cartoon", "logo", "icon", "emoji")
USER_AGENT = "MedDraft_AI/1.0 (figure fetch; +https://github.com/MedDraft_AI)"


# ---------------------------------------------------------------------------
# Naming and paths
# ---------------------------------------------------------------------------


def slugify(text: str, *, max_length: int = 64) -> str:
    """Return a filesystem-safe ASCII slug (never empty)."""
    normalised = unicodedata.normalize("NFKD", str(text or ""))
    ascii_text = normalised.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", ascii_text).strip("-").lower()
    return (slug[:max_length].rstrip("-") or "figure")


def _unique_stem(directory: Path, stem: str) -> str:
    """Return a stem that does not collide in ``directory`` (ignoring suffix)."""
    candidate = stem
    counter = 2
    while any(directory.glob(f"{candidate}.*")):
        candidate = f"{stem}-{counter}"
        counter += 1
    return candidate


def _split_url(url: str) -> urllib.parse.SplitResult | None:
    try:
        parts = urllib.parse.urlsplit(str(url or "").strip())
    except ValueError:
        return None
    if parts.scheme.lower() not in ("http", "https") or not parts.netloc:
        return None
    return parts


def _open_url(url: str, timeout: float):
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "image/avif,image/webp,image/png,image/jpeg,image/*;q=0.8",
            "Accept-Encoding": "identity",
        },
    )
    return urllib.request.urlopen(request, timeout=timeout)


# ---------------------------------------------------------------------------
# Download
# ---------------------------------------------------------------------------


def download_image(
    url: str,
    destination: str | Path,
    *,
    timeout: float = DEFAULT_TIMEOUT,
    max_bytes: int = DEFAULT_MAX_BYTES,
    min_width: int = 0,
    min_height: int = 0,
    convert_unsupported: bool = True,
) -> dict[str, Any]:
    """Download ``url`` to ``destination`` and return a provenance record.

    ``destination`` may omit its suffix; the real suffix follows the detected
    format. Returns ``{"success": False, "error": ...}`` instead of raising for
    bad URLs, HTTP errors, oversized bodies, decode failures, and formats
    Pillow cannot read.
    """
    parts = _split_url(url)
    if parts is None:
        return {
            "success": False,
            "url": str(url or ""),
            "error": "image URL must be an http(s) URL",
        }

    try:
        with _open_url(parts.geturl(), float(timeout)) as response:
            declared_length = response.headers.get("Content-Length")
            if declared_length:
                try:
                    too_big = int(declared_length) > max_bytes
                except (TypeError, ValueError):
                    too_big = False
                if too_big:
                    return {
                        "success": False,
                        "url": parts.geturl(),
                        "error": f"image is larger than the {max_bytes} byte cap",
                    }
            data = response.read(max_bytes + 1)
            content_type = response.headers.get("Content-Type", "")
    except urllib.error.HTTPError as exc:
        return {
            "success": False,
            "url": parts.geturl(),
            "error": f"HTTP {exc.code} while downloading the image",
        }
    except Exception as exc:  # URLError, timeout, socket, SSL
        return {
            "success": False,
            "url": parts.geturl(),
            "error": f"network error: {exc}",
        }

    if len(data) > max_bytes:
        return {
            "success": False,
            "url": parts.geturl(),
            "error": f"image is larger than the {max_bytes} byte cap",
        }
    if not data:
        return {
            "success": False,
            "url": parts.geturl(),
            "error": "empty response body",
        }

    try:
        with Image.open(io.BytesIO(data)) as probe:
            detected = (probe.format or "").upper()
            width, height = probe.size
            probe.load()
    except Exception as exc:
        return {
            "success": False,
            "url": parts.geturl(),
            "content_type": content_type,
            "error": f"not a decodable image: {exc}",
        }

    if min_width and width < int(min_width):
        return {
            "success": False,
            "url": parts.geturl(),
            "width": width,
            "height": height,
            "error": f"image width {width}px is below the {int(min_width)}px floor",
        }
    if min_height and height < int(min_height):
        return {
            "success": False,
            "url": parts.geturl(),
            "width": width,
            "height": height,
            "error": f"image height {height}px is below the {int(min_height)}px floor",
        }

    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)

    reencode = convert_unsupported and detected not in EMBEDDABLE_FORMATS
    suffix = ".png" if reencode else _FORMAT_SUFFIX.get(detected, ".png")
    provided = destination.suffix.lower()
    same_format = provided == suffix or (provided in (".jpg", ".jpeg") and suffix == ".jpg")
    if same_format:
        target = destination
    else:
        target = destination.with_suffix(suffix)

    try:
        if reencode:
            with Image.open(io.BytesIO(data)) as image:
                if image.mode not in ("RGB", "RGBA"):
                    image = image.convert("RGBA")
                buffer = io.BytesIO()
                image.save(buffer, format="PNG", optimize=True)
                payload = buffer.getvalue()
                detected_out = "PNG"
        else:
            payload = data
            detected_out = detected or "PNG"

        tmp_path = target.with_name(target.name + ".part")
        tmp_path.write_bytes(payload)
        tmp_path.replace(target)
    except Exception as exc:
        return {
            "success": False,
            "url": parts.geturl(),
            "error": f"could not write the image: {exc}",
        }

    return {
        "success": True,
        "url": parts.geturl(),
        "path": str(target),
        "bytes": len(payload),
        "width": width,
        "height": height,
        "format": detected_out,
        "source_format": detected,
        "converted": bool(reencode),
        "content_type": content_type,
        "sha256": hashlib.sha256(payload).hexdigest(),
    }


# ---------------------------------------------------------------------------
# Search + download
# ---------------------------------------------------------------------------


def fetch_figures(
    specs: Sequence[Mapping[str, Any]],
    out_dir: str | Path,
    *,
    limit: int = 6,
    provider_order: str | Sequence[str] | None = None,
    safe_search: str = "active",
    required_terms: str | Sequence[str] | None = None,
    exclude_terms: str | Sequence[str] | None = DEFAULT_EXCLUDE_TERMS,
    preferred_hosts: str | Sequence[str] | None = None,
    min_width: int = 800,
    min_height: int = 600,
    timeout: float | None = None,
    max_bytes: int = DEFAULT_MAX_BYTES,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Search and download one image per spec.

    Each spec needs a ``query`` and may carry ``id``, ``title`` and its own
    ``required_terms`` / ``exclude_terms`` / ``preferred_hosts``. The first
    candidate that downloads cleanly wins; lower-ranked candidates are tried
    in order so one dead host does not lose the figure.

    Returns ``{success, figures, failures, providers, out_dir}``. A partial
    success still returns ``success: True`` when at least one figure landed.
    """
    directory = Path(out_dir)
    specs = list(specs)
    results: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    provider_counts: dict[str, int] = {}

    try:
        requested = max(1, min(int(limit), MAX_RESULTS))
    except (TypeError, ValueError):
        requested = 3

    for index, spec in enumerate(specs, start=1):
        query = str(spec.get("query") or "").strip()
        figure_id = slugify(str(spec.get("id") or spec.get("title") or query or f"figure-{index}"))
        if not query:
            failures.append({"id": figure_id, "query": "", "error": "query is required"})
            continue

        spec_required = spec.get("required_terms", required_terms)
        spec_excluded = spec.get("exclude_terms", exclude_terms)
        spec_hosts = spec.get("preferred_hosts", preferred_hosts)

        try:
            payload = search_images(
                query,
                num_results=requested,
                provider_order=provider_order,
                safe_search=safe_search,
                required_terms=spec_required,
                exclude_terms=spec_excluded,
                preferred_hosts=spec_hosts,
                timeout=timeout,
            )
        except Exception as exc:  # search_images is defensive, but never trust it
            failures.append({"id": figure_id, "query": query, "error": f"search failed: {exc}"})
            continue

        provider = payload.get("provider")
        if provider:
            provider_counts[provider] = provider_counts.get(provider, 0) + 1

        candidates = payload.get("results") or []
        if not candidates:
            failures.append(
                {
                    "id": figure_id,
                    "query": query,
                    "error": "no image results",
                    "attempts": payload.get("attempts", []),
                }
            )
            continue

        if dry_run:
            results.append(
                {
                    "id": figure_id,
                    "query": query,
                    "provider": provider,
                    "downloaded": False,
                    "candidates": candidates,
                }
            )
            continue

        accepted: dict[str, Any] | None = None
        tried: list[dict[str, Any]] = []
        for rank, candidate in enumerate(candidates, start=1):
            image_url = str(candidate.get("image_url") or "").strip()
            if not image_url:
                continue
            stem = _unique_stem(directory, figure_id)
            outcome = download_image(
                image_url,
                directory / stem,
                timeout=float(timeout or DEFAULT_TIMEOUT),
                max_bytes=max_bytes,
                min_width=min_width,
                min_height=min_height,
            )
            tried.append(
                {
                    "rank": rank,
                    "url": image_url,
                    "success": outcome.get("success", False),
                    "error": outcome.get("error"),
                }
            )
            if outcome.get("success"):
                accepted = {
                    "id": figure_id,
                    "query": query,
                    "title": candidate.get("title") or spec.get("title") or figure_id,
                    "provider": candidate.get("provider") or provider,
                    "context_url": candidate.get("context_url"),
                    "thumbnail_url": candidate.get("thumbnail_url"),
                    "image_url": image_url,
                    "path": outcome["path"],
                    "width": outcome.get("width"),
                    "height": outcome.get("height"),
                    "format": outcome.get("format"),
                    "bytes": outcome.get("bytes"),
                    "sha256": outcome.get("sha256"),
                    "license_note": (
                        "Verify the hosting page's licence before publication; "
                        "keep context_url for attribution."
                    ),
                    "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    "tried": tried,
                }
                break

        if accepted is None:
            failures.append(
                {
                    "id": figure_id,
                    "query": query,
                    "error": "every candidate failed to download",
                    "tried": tried,
                }
            )
            continue

        sidecar = Path(accepted["path"]).with_suffix(".json")
        try:
            sidecar.write_text(json.dumps(accepted, indent=2, ensure_ascii=False), encoding="utf-8")
        except OSError as exc:  # provenance is useful, not essential
            logger.warning("Could not write figure provenance %s: %s", sidecar, exc)

        results.append(accepted)

    return {
        "success": bool(results) or not specs,
        "out_dir": str(directory),
        "count": len(results),
        "failed": len(failures),
        "figures": results,
        "failures": failures,
        "providers": provider_counts,
    }
