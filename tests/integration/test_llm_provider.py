"""Tests for the provider-neutral LLM interface."""
from __future__ import annotations

import json
import unittest
from unittest.mock import patch, MagicMock

import pytest


@pytest.mark.django_db
def test_no_provider_falls_back_to_template():
    """When LLM_PROVIDER is not set, call_llm returns None (template is used)."""
    with patch.dict("os.environ", {"LLM_PROVIDER": "none"}, clear=False):
        from apps.agents.llm_provider import call_llm
        result = call_llm("Test prompt")
        assert result is None


@pytest.mark.django_db
def test_openrouter_without_key_returns_none():
    """Missing credentials produce transparent failure metadata."""
    with patch.dict("os.environ", {"LLM_PROVIDER": "openrouter", "OPENROUTER_API_KEY": ""}, clear=False):
        from apps.agents.llm_provider import call_llm
        result = call_llm("Test prompt")
        assert result["provider"] == "openrouter"
        assert result["status"] == "failed"
        assert result["error"] == "missing_api_key"


@pytest.mark.django_db
def test_openrouter_with_mocked_api():
    """When OpenRouter is configured and the API returns 200, call_llm returns the text."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "model": "google/gemma-4-31b-it:free",
        "choices": [{"message": {"content": '{"recommendation_type": "delay", "summary": "Test", "body": "Test body that is long enough to pass validation.", "confidence": "medium", "limitations": "", "evidence": [{"source_type": "weather", "source_ref": "test", "claim": "rain"}]}'}}],
    }

    with patch.dict("os.environ", {
        "LLM_PROVIDER": "openrouter",
        "OPENROUTER_API_KEY": "sk-or-v1-test-key",
        "OPENROUTER_MODEL": "google/gemma-4-31b-it:free",
    }, clear=False):
        with patch("httpx.Client") as mock_client_class:
            mock_client = MagicMock()
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=None)
            mock_client.post.return_value = mock_resp
            mock_client_class.return_value = mock_client

            from apps.agents.llm_provider import call_llm
            result = call_llm("Generate an advisory in JSON format.")
            assert result is not None
            assert result["provider"] == "openrouter"
            assert "gemma" in result["model"]
            assert "recommendation_type" in result["text"]
            assert result["status"] == "success"
            assert result["execution_mode"] == "openrouter"
            assert mock_client.post.call_count == 1


@pytest.mark.django_db
def test_openrouter_rate_limit_does_not_switch_models():
    """A rate limit is recorded and never triggers a hidden model retry."""
    mock_resp = MagicMock()
    mock_resp.status_code = 429
    mock_resp.text = "Rate limited"

    with patch.dict("os.environ", {
        "LLM_PROVIDER": "openrouter",
        "OPENROUTER_API_KEY": "sk-or-v1-test-key",
    }, clear=False):
        with patch("httpx.Client") as mock_client_class:
            mock_client = MagicMock()
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=None)
            mock_client.post.return_value = mock_resp
            mock_client_class.return_value = mock_client

            from apps.agents.llm_provider import call_llm
            result = call_llm("Test")
            assert result["status"] == "failed"
            assert result["error"] == "rate_limited"
            assert result["http_status"] == 429
            assert mock_client.post.call_count == 1


@pytest.mark.django_db
def test_openrouter_timeout_returns_none():
    """When OpenRouter times out, call_llm returns None."""
    import httpx

    with patch.dict("os.environ", {
        "LLM_PROVIDER": "openrouter",
        "OPENROUTER_API_KEY": "sk-or-v1-test-key",
    }, clear=False):
        with patch("httpx.Client") as mock_client_class:
            mock_client = MagicMock()
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=None)
            mock_client.post.side_effect = httpx.TimeoutException("timed out")
            mock_client_class.return_value = mock_client

            from apps.agents.llm_provider import call_llm
            result = call_llm("Test")
            assert result["status"] == "failed"
            assert result["error"] == "timeout"


@pytest.mark.django_db
def test_openrouter_auth_failure_is_explicit():
    mock_resp = MagicMock(status_code=401, text="unauthorized")
    with patch.dict("os.environ", {
        "LLM_PROVIDER": "openrouter",
        "OPENROUTER_API_KEY": "sk-or-v1-test-key",
    }, clear=False), patch("httpx.Client") as mock_client_class:
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=None)
        mock_client.post.return_value = mock_resp
        mock_client_class.return_value = mock_client
        from apps.agents.llm_provider import call_llm
        result = call_llm("Test")
        assert result["error"] == "authentication_error"
        assert result["http_status"] == 401


@pytest.mark.django_db
def test_openrouter_empty_response_is_explicit():
    mock_resp = MagicMock(status_code=200)
    mock_resp.json.return_value = {"model": "openrouter/free", "choices": []}
    with patch.dict("os.environ", {
        "LLM_PROVIDER": "openrouter",
        "OPENROUTER_API_KEY": "sk-or-v1-test-key",
    }, clear=False), patch("httpx.Client") as mock_client_class:
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=None)
        mock_client.post.return_value = mock_resp
        mock_client_class.return_value = mock_client
        from apps.agents.llm_provider import call_llm
        result = call_llm("Test")
        assert result["error"] == "empty_response"
        assert result["status"] == "failed"
        assert result["http_status"] == 200
        assert result["model"] == "openrouter/free"


@pytest.mark.django_db
def test_openrouter_refusal_is_distinct_from_empty_content():
    mock_resp = MagicMock(status_code=200)
    mock_resp.json.return_value = {
        "model": "qwen/qwen-2.5-7b-instruct:free",
        "choices": [{"message": {"content": "", "refusal": "safety policy"}, "finish_reason": "stop"}],
    }
    with patch.dict("os.environ", {
        "LLM_PROVIDER": "openrouter",
        "OPENROUTER_API_KEY": "sk-or-v1-test-key",
        "OPENROUTER_MODEL": "qwen/qwen-2.5-7b-instruct:free",
    }, clear=False), patch("httpx.Client") as mock_client_class:
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=None)
        mock_client.post.return_value = mock_resp
        mock_client_class.return_value = mock_client
        from apps.agents.llm_provider import call_llm
        result = call_llm("Test")
        assert result["error"] == "refusal"
        assert result["finish_reason"] == "stop"
        assert result["configured_model"] == "qwen/qwen-2.5-7b-instruct:free"


@pytest.mark.django_db
def test_invalid_provider_uses_none_without_network(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "unexpected-provider")
    from apps.agents.llm_provider import call_llm, get_llm_provider
    assert get_llm_provider() == "none"
    assert call_llm("Test") is None


@pytest.mark.django_db
def test_api_key_not_in_response():
    """The API key must never appear in the LLM response or logs."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "model": "test-model",
        "choices": [{"message": {"content": "test response"}}],
    }

    with patch.dict("os.environ", {
        "LLM_PROVIDER": "openrouter",
        "OPENROUTER_API_KEY": "sk-or-v1-SECRET-KEY-12345",
    }, clear=False):
        with patch("httpx.Client") as mock_client_class:
            mock_client = MagicMock()
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=None)
            mock_client.post.return_value = mock_resp
            mock_client_class.return_value = mock_client

            from apps.agents.llm_provider import call_llm
            result = call_llm("Test")
            assert result is not None
            assert "sk-or-v1-SECRET-KEY-12345" not in result["text"]
            assert "sk-or-v1-SECRET-KEY-12345" not in result["model"]


@pytest.mark.django_db
def test_provider_status_report():
    """provider_status() returns the current provider configuration."""
    with patch.dict("os.environ", {"LLM_PROVIDER": "openrouter", "OPENROUTER_API_KEY": "test"}, clear=False):
        from apps.agents.llm_provider import provider_status
        status = provider_status()
        assert status["provider"] == "openrouter"
        assert status["openrouter_configured"] is True
        assert "free" in status["openrouter_model"] or "gemma" in status["openrouter_model"]


@pytest.mark.django_db
def test_ollama_still_selectable():
    """When LLM_PROVIDER=ollama, the system uses Ollama (not OpenRouter)."""
    with patch.dict("os.environ", {"LLM_PROVIDER": "ollama"}, clear=False):
        from apps.agents.llm_provider import get_llm_provider
        assert get_llm_provider() == "ollama"


@pytest.mark.django_db
def test_paid_model_not_selected_automatically():
    """The default model is the free one, not a paid model."""
    from apps.agents.llm_provider import get_openrouter_model
    model = get_openrouter_model()
    assert ":free" in model or model == "openrouter/free", f"Default model should be free, got: {model}"


@pytest.mark.django_db
def test_agent_graph_uses_call_llm(officer, monkeypatch):
    """The agent graph's draft_advisory node should use call_llm, not _try_ollama directly."""
    monkeypatch.setenv("MAJISHAMBA_SKIP_OLLAMA", "1")
    monkeypatch.setenv("LLM_PROVIDER", "none")
    from django.core.management import call_command
    from io import StringIO
    call_command("loaddata", "data/fixtures/migori_kachieng_clusters.json",
                 "data/fixtures/migori_kachieng_plots.json",
                 "data/fixtures/migori_crop_calendars.json",
                 "data/fixtures/nyatike_weather_signals.json",
                 "data/fixtures/migori_pest_alerts.json",
                 "data/fixtures/migori_market_prices.json",
                 ignorenonexistent=True, stdout=StringIO())
    call_command("seed_kachieng_clusters", stdout=StringIO())
    from apps.agents.runner import run_advisory_pipeline
    result = run_advisory_pipeline(
        cluster_id="KACH-01", ward="Kachieng", sub_county="Nyatike", county="Migori", actor=officer,
    )
    assert "advisory_id" in result, f"agent failed: {result}"
    from apps.advisories.models import Advisory
    adv = Advisory.objects.get(id=result["advisory_id"])
    # With no provider, should be fallback_template
    assert adv.generation_mode == "fallback_template"


class TestProviderAndGraphDeterministic(unittest.TestCase):
    """Django-runner-compatible tests for provider and graph edge cases."""

    @staticmethod
    def _valid_json() -> str:
        return json.dumps({
            "recommendation_type": "delay",
            "summary": "Delay planting until local rainfall onset is verified.",
            "body": "Delay planting and verify local rainfall onset with the cluster representative before sowing. "
            "Use the cited weather and calendar evidence, and review this advisory locally.",
            "confidence": "medium",
            "limitations": "Officer review required.",
            "evidence": [{
                "source_type": "weather",
                "source_ref": "test-weather",
                "claim": "Rainfall onset",
                "source_url": "",
            }],
        })

    def test_successful_json_requests_supported_response_format(self):
        response = MagicMock(status_code=200)
        response.json.return_value = {
            "model": "openrouter/free",
            "choices": [{"message": {"content": self._valid_json()}, "finish_reason": "stop"}],
        }
        with patch.dict("os.environ", {
            "LLM_PROVIDER": "openrouter",
            "OPENROUTER_API_KEY": "test-key",
        }, clear=False), patch("httpx.Client") as client_class:
            client = MagicMock()
            client.__enter__.return_value = client
            client.post.return_value = response
            client_class.return_value = client
            from apps.agents.llm_provider import call_llm

            result = call_llm("Return JSON")

        self.assertEqual(result["status"], "success")
        request_body = client.post.call_args.kwargs["json"]
        self.assertEqual(request_body["response_format"], {"type": "json_object"})
        self.assertEqual(request_body["max_tokens"], 1200)

    def test_truncated_json_is_incomplete_not_success(self):
        response = MagicMock(status_code=200)
        response.json.return_value = {
            "model": "openrouter/free",
            "choices": [{
                "message": {"content": '{"recommendation_type":"delay"'},
                "finish_reason": "length",
            }],
        }
        with patch.dict("os.environ", {
            "LLM_PROVIDER": "openrouter",
            "OPENROUTER_API_KEY": "test-key",
        }, clear=False), patch("httpx.Client") as client_class:
            client = MagicMock()
            client.__enter__.return_value = client
            client.post.return_value = response
            client_class.return_value = client
            from apps.agents.llm_provider import call_llm

            result = call_llm("Return JSON")

        self.assertEqual(result["status"], "incomplete")
        self.assertEqual(result["error"], "incomplete_response")
        self.assertEqual(result["finish_reason"], "length")

    def test_invalid_schema_retries_once_and_accepts_valid_retry(self):
        from apps.agents.graph import draft_advisory

        invalid = {"provider": "openrouter", "model": "test", "status": "success", "text": "{}"}
        valid = {"provider": "openrouter", "model": "test", "status": "success", "text": self._valid_json()}
        with patch("apps.agents.llm_provider.call_llm", side_effect=[invalid, valid]) as provider:
            result = draft_advisory({"cluster_id": "KACH-01"})

        self.assertEqual(provider.call_count, 2)
        self.assertEqual(result["generation_mode"], "llm_openrouter")
        self.assertEqual(result["model_metadata"]["status"], "success")
        self.assertEqual(result["model_metadata"]["retry_count"], 1)

    def test_invalid_schema_retry_exhaustion_uses_fallback_metadata(self):
        from apps.agents.graph import draft_advisory

        invalid = {"provider": "openrouter", "model": "test", "status": "success", "text": "{}"}
        with patch("apps.agents.llm_provider.call_llm", side_effect=[invalid, invalid]) as provider:
            result = draft_advisory({"cluster_id": "KACH-01"})

        self.assertEqual(provider.call_count, 2)
        self.assertEqual(result["generation_mode"], "fallback_template")
        self.assertEqual(result["model_metadata"]["execution_mode"], "fallback_template")
        self.assertEqual(result["model_metadata"]["status"], "fallback")
        self.assertEqual(result["model_metadata"]["provider"], "openrouter")
        self.assertEqual(result["model_metadata"]["provider_error"], "invalid_output")
        self.assertEqual(result["model_metadata"]["retry_count"], 1)

    def test_invalid_schema_retry_preserves_validation_error(self):
        from apps.agents.graph import draft_advisory

        invalid = {"provider": "openrouter", "model": "test", "status": "success", "text": "{}"}
        with patch("apps.agents.llm_provider.call_llm", side_effect=[invalid, invalid]) as provider:
            result = draft_advisory({"cluster_id": "KACH-01"})

        self.assertEqual(provider.call_count, 2)
        self.assertIn("recommendation_type", result["model_metadata"]["retry_error"])
        self.assertNotEqual(result["model_metadata"]["retry_error"], "ValidationError")

    def test_malformed_json_retry_preserves_parse_error(self):
        from apps.agents.graph import draft_advisory

        malformed = {
            "provider": "openrouter",
            "model": "test",
            "status": "success",
            "text": '{"recommendation_type":',
        }
        with patch("apps.agents.llm_provider.call_llm", side_effect=[malformed, malformed]) as provider:
            result = draft_advisory({"cluster_id": "KACH-01"})

        self.assertEqual(provider.call_count, 2)
        self.assertIn("Expecting value", result["model_metadata"]["retry_error"])
        self.assertNotEqual(result["model_metadata"]["retry_error"], "JSONDecodeError")

    def test_provider_failure_uses_accurate_fallback_status(self):
        from apps.agents.graph import draft_advisory

        failure = {
            "provider": "openrouter",
            "model": "test",
            "status": "failed",
            "error": "rate_limited",
        }
        with patch("apps.agents.llm_provider.call_llm", return_value=failure):
            result = draft_advisory({"cluster_id": "KACH-01"})

        self.assertEqual(result["generation_mode"], "fallback_template")
        self.assertEqual(result["model_metadata"]["status"], "fallback")
        self.assertEqual(result["model_metadata"]["provider"], "openrouter")
        self.assertEqual(result["model_metadata"]["provider_error"], "rate_limited")
