"""Tests for provider routing, retry classification, and PRISMA reconciliation."""

from __future__ import annotations

import requests

from meddraft_ai.core.llm_client import _is_retryable_failure
from meddraft_ai.core.provider_router import ProviderRouter
from meddraft_ai.screening.prisma import PrismaFlow


def _http_error(status: int) -> requests.exceptions.HTTPError:
    response = requests.Response()
    response.status_code = status
    return requests.exceptions.HTTPError(response=response)


class TestRetryClassification:
    def test_connection_error_is_retryable(self):
        assert _is_retryable_failure(requests.exceptions.ConnectionError()) is True

    def test_timeout_is_retryable(self):
        assert _is_retryable_failure(requests.exceptions.Timeout()) is True

    def test_rate_limit_is_retryable(self):
        assert _is_retryable_failure(_http_error(429)) is True

    def test_server_error_is_retryable(self):
        assert _is_retryable_failure(_http_error(503)) is True

    def test_bad_request_is_not_retryable(self):
        assert _is_retryable_failure(_http_error(400)) is False

    def test_auth_error_is_not_retryable(self):
        assert _is_retryable_failure(_http_error(401)) is False


class TestVisionRouting:
    def test_text_prompt_mentioning_figure_is_not_vision(self):
        assert ProviderRouter().is_vision_task() is False

    def test_prompt_with_image_is_vision(self):
        assert ProviderRouter().is_vision_task(image_path="fig.png") is True


class TestPrismaReconciliation:
    @staticmethod
    def _record(abstract: str, fulltext: str | None) -> dict:
        record = {"screening": {"verdict": abstract}}
        if fulltext is not None:
            record["fulltext"] = {"verdict": fulltext, "reason": "reason"}
        return record

    def test_flow_accounts_for_unsure_records(self):
        records = [
            self._record("INCLUDE", "INCLUDE"),
            self._record("INCLUDE", "EXCLUDE"),
            self._record("INCLUDE", "UNSURE"),
            self._record("EXCLUDE", None),
        ]
        flow = PrismaFlow.generate_flowchart(4, 0, records)
        stats = flow["stats"]
        assert stats["assessed"] == stats["included"] + stats["excluded"] + stats["unresolved"]
        assert stats["unresolved"] == 1
