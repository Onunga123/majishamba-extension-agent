"""Tests for the provider-neutral LLM interface."""
from __future__ import annotations

import json
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
    """When LLM_PROVIDER=openrouter but no API key, call_llm returns None."""
    with patch.dict("os.environ", {"LLM_PROVIDER": "openrouter", "OPENROUTER_API_KEY": ""}, clear=False):
        from apps.agents.llm_provider import call_llm
        result = call_llm("Test prompt")
        assert result is None


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


@pytest.mark.django_db
def test_openrouter_rate_limit_returns_none():
    """When OpenRouter returns 429, call_llm returns None (fallback to template)."""
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
            assert result is None


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
            assert result is None


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
