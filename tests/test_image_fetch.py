"""Offline tests for image download and figure fetch.

HTTP is mocked at ``image_fetch._open_url``; no real network calls are made and
the Playwright fallback is never launched.
"""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest
from PIL import Image
from PIL import features as pil_features

from meddraft_ai.search import image_fetch


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class FakeResponse:
    def __init__(self, data: bytes, *, content_type: str = "image/png", length: int | None = None):
        self._data = data
        self.headers = {
            "Content-Type": content_type,
            "Content-Length": str(len(data) if length is None else length),
        }

    def read(self, amount: int = -1) -> bytes:
        return self._data if amount < 0 else self._data[:amount]

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def _image_bytes(fmt: str = "PNG", size: tuple[int, int] = (1200, 900), mode: str = "RGB") -> bytes:
    buffer = io.BytesIO()
    Image.new(mode, size, (30, 120, 140)).save(buffer, format=fmt)
    return buffer.getvalue()


def _urlopen_returning(data: bytes, **headers):
    return lambda *args, **kwargs: FakeResponse(data, **headers)


# ---------------------------------------------------------------------------
# slugify and URL guards
# ---------------------------------------------------------------------------


class TestSlugify:
    def test_spaces_and_punctuation_become_dashes(self):
        assert image_fetch.slugify("Gingival sulcus: histology!") == "gingival-sulcus-histology"

    def test_empty_falls_back_to_figure(self):
        assert image_fetch.slugify("") == "figure"

    def test_non_ascii_is_transliterated_or_dropped(self):
        assert image_fetch.slugify("café histology") == "cafe-histology"


class TestUrlGuard:
    def test_rejects_file_scheme(self, tmp_path):
        record = image_fetch.download_image("file:///etc/passwd", tmp_path / "x")
        assert record["success"] is False
        assert "http" in record["error"]

    def test_rejects_relative_path(self, tmp_path):
        record = image_fetch.download_image("images/x.png", tmp_path / "x")
        assert record["success"] is False


# ---------------------------------------------------------------------------
# download_image
# ---------------------------------------------------------------------------


class TestDownloadImage:
    def test_writes_png_and_reports_dimensions(self, tmp_path, monkeypatch):
        data = _image_bytes("PNG")
        monkeypatch.setattr(image_fetch, "_open_url", _urlopen_returning(data))

        record = image_fetch.download_image("https://example.org/a", tmp_path / "fig")

        assert record["success"] is True
        target = Path(record["path"])
        assert target.exists() and target.suffix == ".png"
        assert (record["width"], record["height"]) == (1200, 900)
        assert record["format"] == "PNG"
        assert record["converted"] is False
        assert len(record["sha256"]) == 64

    def test_corrects_suffix_to_detected_format(self, tmp_path, monkeypatch):
        data = _image_bytes("JPEG")
        monkeypatch.setattr(image_fetch, "_open_url", _urlopen_returning(data, content_type="image/png"))

        record = image_fetch.download_image("https://example.org/a", tmp_path / "fig.png")

        assert record["success"] is True
        assert Path(record["path"]).suffix == ".jpg"

    def test_rejects_body_over_byte_cap(self, tmp_path, monkeypatch):
        data = _image_bytes("PNG")
        monkeypatch.setattr(image_fetch, "_open_url", _urlopen_returning(data))

        record = image_fetch.download_image("https://example.org/a", tmp_path / "fig", max_bytes=10)

        assert record["success"] is False
        assert "byte cap" in record["error"]

    def test_rejects_images_below_resolution_floor(self, tmp_path, monkeypatch):
        data = _image_bytes("PNG", size=(200, 150))
        monkeypatch.setattr(image_fetch, "_open_url", _urlopen_returning(data))

        record = image_fetch.download_image(
            "https://example.org/a", tmp_path / "fig", min_width=800, min_height=600
        )

        assert record["success"] is False
        assert "width" in record["error"]

    def test_rejects_undecodable_bytes(self, tmp_path, monkeypatch):
        monkeypatch.setattr(image_fetch, "_open_url", _urlopen_returning(b"not an image"))

        record = image_fetch.download_image("https://example.org/a", tmp_path / "fig")

        assert record["success"] is False
        assert "decodable" in record["error"]

    def test_converts_webp_for_powerpoint(self, tmp_path, monkeypatch):
        if not pil_features.check("webp"):
            pytest.skip("Pillow was built without WebP support")
        data = _image_bytes("WEBP")
        monkeypatch.setattr(image_fetch, "_open_url", _urlopen_returning(data, content_type="image/webp"))

        record = image_fetch.download_image("https://example.org/a", tmp_path / "fig.webp")

        assert record["success"] is True
        assert record["converted"] is True
        assert Path(record["path"]).suffix == ".png"
        assert record["source_format"] == "WEBP"


# ---------------------------------------------------------------------------
# fetch_figures
# ---------------------------------------------------------------------------


def _search_payload(urls, provider="serpapi"):
    return {
        "success": True,
        "query": "q",
        "provider": provider,
        "count": len(urls),
        "results": [
            {
                "title": f"Image {index}",
                "image_url": url,
                "thumbnail_url": url + "?thumb",
                "context_url": "https://example.org/page",
                "width": 1200,
                "height": 900,
                "provider": provider,
                "position": index,
            }
            for index, url in enumerate(urls, start=1)
        ],
        "attempts": [],
    }


class TestFetchFigures:
    def test_falls_through_dead_candidate_and_writes_sidecar(self, tmp_path, monkeypatch):
        data = _image_bytes("PNG")
        monkeypatch.setattr(image_fetch, "search_images", lambda *a, **k: _search_payload(
            ["ftp://bad.example/a.png", "https://good.example/b.png"]
        ))
        monkeypatch.setattr(image_fetch, "_open_url", _urlopen_returning(data))

        result = image_fetch.fetch_figures(
            [{"id": "sulcus", "query": "sulcus histology"}],
            tmp_path,
            min_width=400,
            min_height=300,
        )

        assert result["success"] is True
        assert result["count"] == 1
        figure = result["figures"][0]
        assert Path(figure["path"]).exists()
        assert len(figure["tried"]) == 2
        assert figure["tried"][0]["success"] is False
        assert figure["tried"][1]["success"] is True
        assert result["providers"] == {"serpapi": 1}

        sidecar = Path(figure["path"]).with_suffix(".json")
        assert sidecar.exists()
        provenance = json.loads(sidecar.read_text(encoding="utf-8"))
        assert provenance["query"] == "sulcus histology"
        assert provenance["context_url"] == "https://example.org/page"

    def test_reports_no_results_per_spec(self, tmp_path, monkeypatch):
        monkeypatch.setattr(image_fetch, "search_images", lambda *a, **k: {
            "success": False, "query": "q", "provider": None, "count": 0,
            "results": [], "attempts": [{"provider": "serpapi", "status": "skipped"}],
        })

        result = image_fetch.fetch_figures([{"query": "missing"}], tmp_path)

        assert result["success"] is False
        assert result["failures"][0]["error"] == "no image results"

    def test_dry_run_does_not_download(self, tmp_path, monkeypatch):
        monkeypatch.setattr(image_fetch, "search_images", lambda *a, **k: _search_payload(
            ["https://good.example/b.png"]
        ))

        result = image_fetch.fetch_figures([{"query": "q"}], tmp_path, dry_run=True)

        assert result["figures"][0]["downloaded"] is False
        assert not list(tmp_path.glob("*.png"))

    def test_requires_a_query(self, tmp_path, monkeypatch):
        monkeypatch.setattr(image_fetch, "search_images", lambda *a, **k: pytest.fail("must not search"))

        result = image_fetch.fetch_figures([{"title": "No query"}], tmp_path)

        assert result["success"] is False
        assert result["failures"][0]["error"] == "query is required"
