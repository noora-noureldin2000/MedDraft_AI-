"""Contract tests for ResearchOrchestrator._call_browser_engine (H-13).

The Python side parses the Node engine's stdout by scanning for the last
line that is a complete JSON object. These tests pin that contract offline:
all subprocess calls are mocked — no browser is launched.

test-guard compliance:
  - Rule 2: mocked at the subprocess boundary only
  - Rule 3: one scenario per test
  - Rule 5: names describe scenario and expected outcome
"""

from __future__ import annotations

import json
import subprocess
from unittest.mock import patch, MagicMock

import pytest

from meddraft_ai.search.research_orchestrator import ResearchOrchestrator


@pytest.fixture()
def orchestrator() -> ResearchOrchestrator:
    return ResearchOrchestrator()


class TestCallBrowserEngineContract:
    def test_parses_json_reply_from_noisy_stdout(self, orchestrator):
        """Engine logs status lines before the JSON reply; parser must skip them."""
        noisy_stdout = (
            "\U0001f504 Checking for reCAPTCHA on page...\n"
            "\u2139\ufe0f No reCAPTCHA anchor found.\n"
            '{"success": true, "count": 2, "results": [{"title": "A"}]}\n'
        )
        with patch(
            "subprocess.run",
            MagicMock(return_value=subprocess.CompletedProcess(args=[], returncode=0, stdout=noisy_stdout)),
        ):
            result = orchestrator._call_browser_engine("scholar-search", "query", "5")
        assert result["success"] is True
        assert result["count"] == 2

    def test_returns_error_envelope_when_output_has_no_json(self, orchestrator):
        plain_stdout = "some crash trace without json\n"
        with patch(
            "subprocess.run",
            MagicMock(return_value=subprocess.CompletedProcess(args=[], returncode=0, stdout=plain_stdout)),
        ):
            result = orchestrator._call_browser_engine("scholar-search", "query", "5")
        assert result["success"] is False
        assert "No JSON output" in result["error"]

    def test_timeout_returns_error_envelope(self, orchestrator):
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="node", timeout=150)):
            result = orchestrator._call_browser_engine("scholar-search", "query", "5")
        assert result["success"] is False
        assert "timed out" in result["error"].lower()

    def test_proxy_env_is_forwarded_to_engine_process(self, orchestrator):
        """Configured proxy values must reach the engine via environment variables."""
        captured_kwargs: dict = {}

        def fake_run(*args, **kwargs):
            captured_kwargs.update(kwargs)
            return subprocess.CompletedProcess(args=[], returncode=0, stdout='{"success": true}')

        with patch.dict(
            "os.environ",
            {"PROXY_SERVER": "http://proxy:8080", "PROXY_USERNAME": "u", "PROXY_PASSWORD": "p"},
        ):
            with patch("subprocess.run", side_effect=fake_run):
                orchestrator._call_browser_engine("scholar-search", "query", "5")

        env = captured_kwargs.get("env", {})
        assert env.get("PROXY_SERVER") == "http://proxy:8080"
        assert env.get("PROXY_USERNAME") == "u"
        assert env.get("PROXY_PASSWORD") == "p"


class TestSearchScholarStealthEnvelope:
    def test_scholar_stealth_returns_empty_list_on_engine_failure(self, orchestrator):
        """Engine-level failure envelope must surface as [] from the orchestrator."""
        failing_stdout = '{"success": false, "error": "Blocked by Google Scholar CAPTCHA"}\n'
        with patch(
            "subprocess.run",
            MagicMock(return_value=subprocess.CompletedProcess(args=[], returncode=0, stdout=failing_stdout)),
        ):
            results = orchestrator.search_scholar_stealth("anything", limit=5)
        assert results == []
