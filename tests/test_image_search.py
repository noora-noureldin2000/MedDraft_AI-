"""Offline tests for the provider-chained Google Images search.

All HTTP is mocked at the urllib boundary; the Playwright fallback is never
launched. Each test covers one scenario (test-guard Rule 3).
"""

from __future__ import annotations

import io
import json
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

import pytest

from meddraft_ai.search import image_search


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class FakeResponse:
    def __init__(self, payload):
        self._data = json.dumps(payload).encode("utf-8")

    def read(self):
        return self._data

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


def _urlopen_returning(payload):
    return lambda *args, **kwargs: FakeResponse(payload)


def _item(url: str, provider: str = "serpapi", title: str = "Image", **extra):
    base = {
        "title": title,
        "image_url": url,
        "thumbnail_url": url.replace(".jpg", "_thumb.jpg"),
        "context_url": "https://example.org/source",
        "width": 800,
        "height": 600,
        "provider": provider,
        "position": 1,
    }
    base.update(extra)
    return base


def _all_configured(provider: str):
    return True, {"api_key": "dummy", "cse_id": "dummy-cx"}, ""


# ---------------------------------------------------------------------------
# Provider parsers
# ---------------------------------------------------------------------------


class TestSerpApiParsing:
    def test_maps_original_to_image_url_and_link_to_context(self, monkeypatch):
        payload = {
            "images_results": [
                {
                    "position": 1,
                    "title": "Gingival sulcus histology",
                    "original": "https://cdn.example.org/sulcus.jpg",
                    "thumbnail": "https://encrypted-tbn0.gstatic.com/sulcus.jpg",
                    "link": "https://example.org/article",
                    "original_width": 1200,
                    "original_height": 900,
                }
            ]
        }
        monkeypatch.setattr("urllib.request.urlopen", _urlopen_returning(payload))

        results = image_search._search_serpapi("sulcus", 3, api_key="key")

        assert len(results) == 1
        assert results[0]["image_url"] == "https://cdn.example.org/sulcus.jpg"
        assert results[0]["context_url"] == "https://example.org/article"
        assert results[0]["provider"] == "serpapi"
        assert results[0]["width"] == 1200

    def test_raises_provider_error_on_api_error_payload(self, monkeypatch):
        monkeypatch.setattr(
            "urllib.request.urlopen",
            _urlopen_returning({"error": "Invalid API key"}),
        )

        with pytest.raises(image_search.ProviderRequestError) as excinfo:
            image_search._search_serpapi("x", 1, api_key="secret-key-123")

        assert "Invalid API key" in excinfo.value.message
        assert "secret-key-123" not in excinfo.value.message

    def test_long_caption_titles_are_truncated_for_context_economy(self):
        item = image_search._normalise_item(
            title="A" * 300,
            image_url="https://a.example/x.jpg",
            provider="serpapi",
            position=1,
        )

        assert len(item["title"]) == 160
        assert item["title"].endswith("...")


class TestGoogleCseParsing:
    def test_maps_link_and_image_context(self, monkeypatch):
        payload = {
            "items": [
                {
                    "title": "Periodontal ligament diagram",
                    "link": "https://example.org/pdl.png",
                    "image": {
                        "contextLink": "https://example.org/pdl-page",
                        "thumbnailLink": "https://encrypted-tbn0.gstatic.com/pdl.png",
                        "width": 1024,
                        "height": 768,
                    },
                }
            ]
        }
        monkeypatch.setattr("urllib.request.urlopen", _urlopen_returning(payload))

        results = image_search._search_google_cse(
            "periodontal ligament", 3, api_key="key", cse_id="cx"
        )

        assert results[0]["image_url"] == "https://example.org/pdl.png"
        assert results[0]["context_url"] == "https://example.org/pdl-page"
        assert results[0]["provider"] == "google_cse"


class TestBraveParsing:
    def test_maps_properties_url_to_image_and_url_to_context(self, monkeypatch):
        payload = {
            "results": [
                {
                    "title": "Alveolar bone",
                    "url": "https://example.org/alveolar-page",
                    "thumbnail": {"src": "https://imgs.search.brave.com/alveolar.jpg"},
                    "properties": {
                        "url": "https://example.org/alveolar.jpg",
                        "width": 1500,
                        "height": 1000,
                    },
                }
            ]
        }
        monkeypatch.setattr("urllib.request.urlopen", _urlopen_returning(payload))

        results = image_search._search_brave("alveolar bone", 2, api_key="key")

        assert results[0]["image_url"] == "https://example.org/alveolar.jpg"
        assert results[0]["context_url"] == "https://example.org/alveolar-page"
        assert results[0]["provider"] == "brave"


class TestHttpErrors:
    def test_429_is_surfaced_with_retry_after(self, monkeypatch):
        body = io.BytesIO(json.dumps({"error": {"message": "rate limit exceeded"}}).encode())
        error = urllib.error.HTTPError(
            "https://api.search.brave.com/res/v1/images/search",
            429,
            "Too Many Requests",
            {"Retry-After": "7"},
            body,
        )
        monkeypatch.setattr("urllib.request.urlopen", lambda *a, **k: (_ for _ in ()).throw(error))

        with pytest.raises(image_search.ProviderRequestError) as excinfo:
            image_search._search_brave("x", 1, api_key="brave-secret")

        assert excinfo.value.status == 429
        assert excinfo.value.retry_after == 7.0

    def test_nested_validation_detail_surfaces_the_bad_parameter(self, monkeypatch):
        body = io.BytesIO(
            json.dumps(
                {
                    "type": "ErrorResponse",
                    "error": {
                        "status": 422,
                        "detail": "Unable to validate request parameter(s)",
                        "meta": {
                            "errors": [
                                {
                                    "loc": ["query", "safesearch"],
                                    "msg": "Input should be 'off' or 'strict'",
                                }
                            ]
                        },
                    },
                }
            ).encode()
        )
        error = urllib.error.HTTPError(
            "https://api.search.brave.com/res/v1/images/search",
            422,
            "Unprocessable Entity",
            {},
            body,
        )
        monkeypatch.setattr("urllib.request.urlopen", lambda *a, **k: (_ for _ in ()).throw(error))

        with pytest.raises(image_search.ProviderRequestError) as excinfo:
            image_search._search_brave("x", 1, api_key="brave-secret")

        assert "safesearch" in excinfo.value.message
        assert "Input should be" in excinfo.value.message

    def test_brave_safe_search_maps_active_to_strict(self, monkeypatch):
        captured = {}

        def fake_urlopen(request, timeout=None):
            captured["url"] = request.full_url
            return FakeResponse({"results": []})

        monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

        image_search._search_brave("q", 1, api_key="key", safe_search="active")

        assert "safesearch=strict" in captured["url"]


# ---------------------------------------------------------------------------
# Provider order and fallback chain
# ---------------------------------------------------------------------------


class TestProviderOrder:
    def test_aliases_are_normalised_and_unknown_names_dropped(self):
        order = image_search.resolve_provider_order("google,serp,brave,playwright,nope")
        assert order == ["google_cse", "serpapi", "brave", "browser"]

    def test_empty_order_falls_back_to_default_chain_without_legacy_google(self):
        assert image_search.resolve_provider_order("") == [
            "serpapi",
            "brave",
            "browser",
        ]
        assert "google_cse" not in image_search.DEFAULT_PROVIDER_ORDER


class TestSearchChain:
    def test_first_configured_provider_wins(self, monkeypatch):
        monkeypatch.setattr(image_search, "_resolve_credentials", _all_configured)

        def fake_serp(query, num, **kwargs):
            return [_item("https://a.example/one.jpg", "serpapi")]

        monkeypatch.setattr(image_search, "_search_serpapi", fake_serp)
        monkeypatch.setattr(
            image_search,
            "_search_google_cse",
            lambda *a, **k: pytest.fail("fallback must not run when the first provider fills the request"),
        )

        result = image_search.search_images(
            "q",
            1,
            provider_order=["serpapi", "google_cse"],
            ledger=image_search.QuotaLedger(enabled=False),
        )

        assert result["success"] is True
        assert result["provider"] == "serpapi"
        assert len(result["attempts"]) == 1

    def test_empty_provider_falls_through_to_next(self, monkeypatch):
        monkeypatch.setattr(image_search, "_resolve_credentials", _all_configured)
        monkeypatch.setattr(image_search, "_search_serpapi", lambda *a, **k: [])
        monkeypatch.setattr(
            image_search,
            "_search_google_cse",
            lambda *a, **k: [_item("https://a.example/google.jpg", "google_cse")],
        )

        result = image_search.search_images(
            "q",
            1,
            provider_order=["serpapi", "google_cse"],
            ledger=image_search.QuotaLedger(enabled=False),
        )

        assert result["success"] is True
        assert result["provider"] == "google_cse"
        assert [a["status"] for a in result["attempts"]] == ["empty", "ok"]

    def test_provider_error_falls_through_and_is_reported(self, monkeypatch):
        monkeypatch.setattr(image_search, "_resolve_credentials", _all_configured)

        def boom(*args, **kwargs):
            raise image_search.ProviderRequestError("network down")

        monkeypatch.setattr(image_search, "_search_serpapi", boom)
        monkeypatch.setattr(
            image_search,
            "_search_google_cse",
            lambda *a, **k: [_item("https://a.example/google.jpg", "google_cse")],
        )

        result = image_search.search_images(
            "q",
            1,
            provider_order=["serpapi", "google_cse"],
            ledger=image_search.QuotaLedger(enabled=False),
        )

        assert result["success"] is True
        assert result["attempts"][0] == {
            "provider": "serpapi",
            "status": "error",
            "reason": "network down",
            "http_status": None,
        }

    def test_missing_credentials_skips_provider_without_calling_it(self, monkeypatch):
        def credentials(provider):
            if provider == "serpapi":
                return False, {}, "SERP_API_KEY"
            return True, {"api_key": "dummy"}, ""

        monkeypatch.setattr(image_search, "_resolve_credentials", credentials)
        monkeypatch.setattr(
            image_search,
            "_search_serpapi",
            lambda *a, **k: pytest.fail("SerpApi must not be called without a key"),
        )
        monkeypatch.setattr(
            image_search,
            "_search_brave",
            lambda *a, **k: [_item("https://a.example/brave.jpg", "brave")],
        )

        result = image_search.search_images(
            "q",
            1,
            provider_order=["serpapi", "brave"],
            ledger=image_search.QuotaLedger(enabled=False),
        )

        assert result["success"] is True
        assert result["attempts"][0]["reason"] == "missing_credentials"
        assert result["attempts"][0]["missing"] == "SERP_API_KEY"

    def test_exhausted_quota_is_skipped(self, tmp_path, monkeypatch):
        ledger = image_search.QuotaLedger(tmp_path / "quota.json")
        ledger.mark_exhausted("serpapi")
        monkeypatch.setattr(image_search, "_resolve_credentials", _all_configured)
        monkeypatch.setattr(
            image_search,
            "_search_serpapi",
            lambda *a, **k: pytest.fail("SerpApi quota is exhausted"),
        )
        monkeypatch.setattr(
            image_search,
            "_search_google_cse",
            lambda *a, **k: [_item("https://a.example/google.jpg", "google_cse")],
        )

        result = image_search.search_images(
            "q",
            1,
            provider_order=["serpapi", "google_cse"],
            ledger=ledger,
        )

        assert result["success"] is True
        assert result["attempts"][0]["reason"] == "quota_exhausted"
        assert result["attempts"][0]["limit"] == 100

    def test_all_providers_unavailable_returns_failure_envelope(self, monkeypatch):
        monkeypatch.setattr(
            image_search, "_resolve_credentials", lambda provider: (False, {}, "missing")
        )

        result = image_search.search_images(
            "q",
            3,
            provider_order=["serpapi", "google_cse", "brave"],
            ledger=image_search.QuotaLedger(enabled=False),
        )

        assert result["success"] is False
        assert result["results"] == []
        assert "serpapi: missing" in result["error"]
        assert len(result["attempts"]) == 3

    def test_empty_query_returns_failure_without_calling_providers(self, monkeypatch):
        monkeypatch.setattr(
            image_search,
            "_resolve_credentials",
            lambda provider: pytest.fail("providers must not run for an empty query"),
        )

        result = image_search.search_images("   ", 3)

        assert result["success"] is False
        assert result["error"] == "query is required"

    def test_results_are_deduplicated_and_capped(self, monkeypatch):
        monkeypatch.setattr(image_search, "_resolve_credentials", _all_configured)
        duplicate = "https://a.example/shared.jpg"
        monkeypatch.setattr(
            image_search,
            "_search_serpapi",
            lambda *a, **k: [_item(duplicate, "serpapi")],
        )
        monkeypatch.setattr(
            image_search,
            "_search_google_cse",
            lambda *a, **k: [
                _item(duplicate + "#fragment", "google_cse"),
                _item("https://a.example/second.jpg", "google_cse"),
            ],
        )

        result = image_search.search_images(
            "q",
            2,
            provider_order=["serpapi", "google_cse"],
            ledger=image_search.QuotaLedger(enabled=False),
        )

        assert len(result["results"]) == 2
        assert result["count"] == 2
        assert result["results"][0]["image_url"] == duplicate

    def test_no_fallback_uses_only_first_provider(self, monkeypatch):
        monkeypatch.setattr(image_search, "_resolve_credentials", _all_configured)
        monkeypatch.setattr(image_search, "_search_serpapi", lambda *a, **k: [])
        monkeypatch.setattr(
            image_search,
            "_search_google_cse",
            lambda *a, **k: pytest.fail("fallback must be disabled"),
        )

        result = image_search.search_images(
            "q",
            1,
            provider_order=["serpapi", "google_cse"],
            allow_fallback=False,
            ledger=image_search.QuotaLedger(enabled=False),
        )

        assert result["success"] is False
        assert len(result["attempts"]) == 1


# ---------------------------------------------------------------------------
# Relevance scoring
# ---------------------------------------------------------------------------


class TestRanking:
    def test_required_optional_and_preferred_host_rank_the_best_image_first(self):
        results = [
            _item("https://random.example/clipart.jpg", title="Cartoon tooth clipart"),
            _item(
                "https://www.ncbi.nlm.nih.gov/histology.jpg",
                title="Gingival sulcus histology",
                width=1600,
                height=1200,
            ),
        ]

        ranked = image_search.filter_and_rank_results(
            results,
            required_terms=["histology"],
            optional_terms=["sulcus"],
            exclude_terms=["clipart"],
            preferred_hosts=["ncbi.nlm.nih.gov"],
        )

        assert len(ranked) == 1
        assert ranked[0]["title"] == "Gingival sulcus histology"
        assert ranked[0]["relevance_score"] > 0

    def test_excluded_term_is_hard_filtered(self):
        results = [
            _item("https://a.example/logo.jpg", title="Hospital logo"),
            _item("https://a.example/photo.jpg", title="Hospital ward photograph"),
        ]

        ranked = image_search.filter_and_rank_results(results, exclude_terms=["logo"])

        assert len(ranked) == 1
        assert ranked[0]["title"] == "Hospital ward photograph"

    def test_ranks_applied_inside_search_chain(self, monkeypatch):
        monkeypatch.setattr(image_search, "_resolve_credentials", _all_configured)
        monkeypatch.setattr(
            image_search,
            "_search_serpapi",
            lambda *a, **k: [
                _item("https://a.example/bad.jpg", title="Cartoon tooth"),
                _item("https://a.example/good.jpg", title="Tooth histology section"),
            ],
        )

        result = image_search.search_images(
            "tooth histology",
            1,
            provider_order=["serpapi"],
            required_terms=["histology"],
            exclude_terms=["cartoon"],
            ledger=image_search.QuotaLedger(enabled=False),
        )

        assert result["results"][0]["image_url"] == "https://a.example/good.jpg"


# ---------------------------------------------------------------------------
# Markdown, tool schema, status
# ---------------------------------------------------------------------------


class TestAgentSurface:
    def test_markdown_uses_standard_image_syntax(self):
        payload = {
            "results": [
                {
                    "title": "Gingival sulcus [histology]",
                    "image_url": "https://a.example/sulcus.jpg",
                    "context_url": "https://a.example/page",
                }
            ]
        }

        rendered = image_search.render_markdown(payload, include_source=True)

        assert rendered.startswith("![Gingival sulcus \\[histology\\]](https://a.example/sulcus.jpg)")
        assert "Source: https://a.example/page" in rendered

    def test_tool_schema_exposes_expected_contract(self):
        schema = image_search.get_image_search_tool_schema()
        function = schema["function"]

        assert function["name"] == "search_google_images"
        assert function["parameters"]["required"] == ["query"]
        assert function["parameters"]["properties"]["num_results"]["maximum"] == 10
        assert "required_terms" in function["parameters"]["properties"]

    def test_tool_dispatcher_forwards_model_arguments(self, monkeypatch):
        captured = {}

        def fake_search(query, num_results=3, **kwargs):
            captured.update(query=query, num_results=num_results, **kwargs)
            return {"success": True, "results": []}

        monkeypatch.setattr(image_search, "search_images", fake_search)

        image_search.execute_image_search_tool(
            {
                "query": "alveolar bone radiograph",
                "num_results": 2,
                "safe_search": "off",
                "required_terms": ["radiograph"],
                "exclude_terms": ["clipart"],
            }
        )

        assert captured == {
            "query": "alveolar bone radiograph",
            "num_results": 2,
            "safe_search": "off",
            "required_terms": ["radiograph"],
            "exclude_terms": ["clipart"],
        }

    def test_tool_dispatcher_rejects_non_object_arguments(self):
        result = image_search.execute_image_search_tool(None)

        assert result["success"] is False
        assert result["error"] == "tool arguments must be an object"

    def test_provider_status_never_returns_api_keys(self, monkeypatch):
        monkeypatch.setenv("SERP_API_KEY", "secret-serp-value")
        monkeypatch.setenv("BRAVE_API_KEY", "secret-brave-value")
        monkeypatch.setenv("GOOGLE_CSE_API_KEY", "secret-google-value")
        monkeypatch.setenv("GOOGLE_CSE_ID", "cx-value")

        statuses = image_search.get_provider_status(
            ledger=image_search.QuotaLedger(enabled=False)
        )
        serialised = json.dumps(statuses)

        assert "secret-serp-value" not in serialised
        assert "secret-brave-value" not in serialised
        assert "secret-google-value" not in serialised

    def test_browser_payload_parser_maps_camel_case_fields(self):
        payload = {
            "success": True,
            "results": [
                {
                    "index": 0,
                    "title": "Playwright image",
                    "imageUrl": "https://a.example/browser.jpg",
                    "thumbnailUrl": "https://a.example/thumb.jpg",
                    "contextUrl": "https://a.example/page",
                    "width": 1280,
                    "height": 720,
                }
            ],
        }

        results = image_search._parse_browser_payload(payload, 3)

        assert results[0]["image_url"] == "https://a.example/browser.jpg"
        assert results[0]["context_url"] == "https://a.example/page"
        assert results[0]["provider"] == "browser"

    def test_unavailable_browser_is_reported_as_missing_credentials(self, monkeypatch):
        monkeypatch.setattr(image_search, "_browser_available", lambda: False)

        result = image_search.search_images(
            "q",
            1,
            provider_order=["browser"],
            ledger=image_search.QuotaLedger(enabled=False),
        )

        assert result["success"] is False
        assert result["attempts"][0]["reason"] == "missing_credentials"


# ---------------------------------------------------------------------------
# Quota ledger
# ---------------------------------------------------------------------------


class TestQuotaLedger:
    def test_usage_persists_across_ledger_instances(self, tmp_path):
        path = tmp_path / "quota.json"
        first = image_search.QuotaLedger(path)
        first.record_success("brave")

        second = image_search.QuotaLedger(path)

        assert second.status("brave")["used"] == 1
        assert second.status("brave")["remaining"] == 1999

    def test_daily_period_rollover_resets_usage(self, tmp_path):
        moment = [datetime(2026, 11, 22, 23, 0, tzinfo=timezone.utc)]
        ledger = image_search.QuotaLedger(
            tmp_path / "quota.json", now=lambda: moment[0]
        )
        ledger.record_success("google_cse")
        assert ledger.status("google_cse")["used"] == 1

        moment[0] = datetime(2026, 11, 23, 0, 1, tzinfo=timezone.utc)

        assert ledger.status("google_cse")["used"] == 0
        assert ledger.status("google_cse")["remaining"] == 100

    def test_monthly_period_rollover_resets_usage(self, tmp_path):
        moment = [datetime(2026, 11, 30, 23, 0, tzinfo=timezone.utc)]
        ledger = image_search.QuotaLedger(
            tmp_path / "quota.json", now=lambda: moment[0]
        )
        ledger.record_success("serpapi")

        moment[0] = datetime(2026, 12, 1, 0, 1, tzinfo=timezone.utc)

        assert ledger.status("serpapi")["used"] == 0
        assert ledger.status("serpapi")["reset_at"].startswith("2027-01-01")

    def test_cooldown_blocks_provider_until_it_expires(self, tmp_path):
        moment = [datetime(2026, 11, 22, 12, 0, tzinfo=timezone.utc)]
        ledger = image_search.QuotaLedger(
            tmp_path / "quota.json", now=lambda: moment[0]
        )
        ledger.record_cooldown("brave", 60)

        assert ledger.can_use("brave") == (False, "rate_limited")

        moment[0] = datetime(2026, 11, 22, 12, 2, tzinfo=timezone.utc)

        assert ledger.can_use("brave") == (True, None)

    def test_disabled_ledger_does_not_create_a_file(self, tmp_path):
        path = tmp_path / "quota.json"
        ledger = image_search.QuotaLedger(path, enabled=False)
        ledger.record_success("serpapi")

        assert not path.exists()
        assert ledger.status("serpapi")["limit"] == 100
