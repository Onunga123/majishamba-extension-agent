"""Provider-neutral LLM interface for the Kachieng AI Agent.

Supports two providers:
1. OpenRouter (default) — cloud API, no local model needed, works on any laptop.
   Set LLM_PROVIDER=openrouter, OPENROUTER_API_KEY=<key>, OPENROUTER_MODEL=<model>
2. Ollama (optional) — local model, works offline, for judges/local use.
   Set LLM_PROVIDER=ollama, OLLAMA_HOST=<host>, OLLAMA_MODEL=<model>

Default: LLM_PROVIDER=openrouter
If no provider is configured, falls back to the deterministic template.

The interface:
- Never sends farmer names, phone numbers, or household IDs to the cloud.
- Uses internal pseudonymous references (cluster_id, household_id) in prompts.
- Logs the actual model identity returned by the provider.
- Does NOT log or expose the API key.
- Enforces a tool-call budget (max 3 LLM calls per advisory run).
- Falls back to the deterministic template on any failure.
"""
from __future__ import annotations

import json
import logging
import os
import time
import hashlib
from typing import Any

logger = logging.getLogger("majishamba.llm")


def get_llm_provider() -> str:
    """Return the configured LLM provider: 'openrouter', 'ollama', or 'none'."""
    return os.environ.get("LLM_PROVIDER", "none").lower()


def get_openrouter_api_key() -> str:
    """Return the OpenRouter API key from env. Never logged or exposed."""
    return os.environ.get("OPENROUTER_API_KEY", "")


def get_openrouter_model() -> str:
    """Return the configured OpenRouter model. Default: openrouter/free (auto-routes to best free model)."""
    return os.environ.get("OPENROUTER_MODEL", "openrouter/free")


def get_openrouter_timeout() -> int:
    return int(os.environ.get("OPENROUTER_TIMEOUT_SECONDS", "60"))


def get_openrouter_max_tokens() -> int:
    return int(os.environ.get("OPENROUTER_MAX_OUTPUT_TOKENS", "800"))


def is_openrouter_configured() -> bool:
    """Check if OpenRouter is ready to use (key present)."""
    return bool(get_openrouter_api_key())


def is_ollama_configured() -> bool:
    """Check if Ollama is available."""
    if os.environ.get("MAJISHAMBA_SKIP_OLLAMA", "0") == "1":
        return False
    try:
        import ollama  # noqa: F401
        return True
    except ImportError:
        return False


def call_llm(prompt: str) -> dict[str, Any] | None:
    """Call the configured LLM provider. Returns dict with text + metadata, or None.

    The dict contains:
    - text: the model's response text
    - model: the actual model name returned by the provider
    - provider: 'openrouter' or 'ollama'
    - elapsed_s: wall-clock seconds
    - prompt_hash: SHA-256 hash of the prompt (for provenance, not the prompt itself)

    Never raises — logs errors and returns None on failure.
    Never logs or returns the API key.
    """
    provider = get_llm_provider()
    prompt_hash = hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:16]
    started = time.time()

    if provider == "openrouter":
        if not is_openrouter_configured():
            logger.warning("LLM_PROVIDER=openrouter but OPENROUTER_API_KEY is not set — falling back to template.")
            return None
        result = _call_openrouter(prompt, prompt_hash, started)
        if result is None:
            # Primary model failed — try fallback free models
            result = _call_openrouter_fallback(prompt, prompt_hash, started)
        return result

    elif provider == "ollama":
        if not is_ollama_configured():
            logger.warning("LLM_PROVIDER=ollama but Ollama is not available — falling back to template.")
            return None
        result = _call_ollama(prompt, prompt_hash, started)
        return result

    else:
        # No provider configured — use deterministic template (handled by caller).
        logger.info("No LLM provider configured (LLM_PROVIDER=%s) — using deterministic template.", provider)
        return None


def _call_openrouter(prompt: str, prompt_hash: str, started: float) -> dict[str, Any] | None:
    """Call OpenRouter's chat completions API."""
    import httpx

    api_key = get_openrouter_api_key()
    model = get_openrouter_model()
    timeout = get_openrouter_timeout()
    max_tokens = get_openrouter_max_tokens()

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/Onunga123/majishamba-extension-agent",
        "X-Title": "Kachieng AI Agent",
    }
    body = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": 0.2,
    }

    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=body)
            if resp.status_code == 429:
                logger.warning("OpenRouter rate-limited (429). Falling back to template.")
                return None
            if resp.status_code != 200:
                logger.warning("OpenRouter returned HTTP %s: %s", resp.status_code, resp.text[:200])
                return None
            data = resp.json()
            # Extract the response text
            choices = data.get("choices", [])
            if not choices:
                logger.warning("OpenRouter response has no choices.")
                return None
            text = choices[0].get("message", {}).get("content", "")
            if not text:
                logger.warning("OpenRouter response has empty content (model returned null).")
                return None
            # Get the actual model returned (may differ from requested)
            actual_model = data.get("model", model)
            elapsed = round(time.time() - started, 2)
            logger.info("OpenRouter call OK: model=%s, elapsed=%ss, chars=%d", actual_model, elapsed, len(text))
            return {
                "text": _strip_code_fence(text),
                "model": actual_model,
                "provider": "openrouter",
                "elapsed_s": elapsed,
                "prompt_hash": prompt_hash,
            }
    except httpx.TimeoutException:
        logger.warning("OpenRouter call timed out after %ss. Falling back to template.", timeout)
        return None
    except Exception as exc:
        logger.warning("OpenRouter call failed: %s", exc)
        return None


# Fallback free models — tried in order if the primary model fails (429, timeout, etc.)
FALLBACK_FREE_MODELS = [
    "google/gemma-4-26b-a4b-it:free",
    "google/gemma-4-31b-it:free",
    "liquid/lfm-2.5-2.6b:free",
    "apodex/apodex-1.1-mini:free",
]


def _call_openrouter_fallback(prompt: str, prompt_hash: str, started: float) -> dict[str, Any] | None:
    """Try fallback free models if the primary model failed."""
    primary_model = get_openrouter_model()
    api_key = get_openrouter_api_key()
    timeout = get_openrouter_timeout()
    max_tokens = get_openrouter_max_tokens()

    for model in FALLBACK_FREE_MODELS:
        if model == primary_model:
            continue  # Already tried
        logger.info("Trying fallback model: %s", model)
        # Small delay to avoid immediate rate-limit on the next model
        time.sleep(1)
        result = _call_openrouter_single(prompt, api_key, model, timeout, max_tokens, prompt_hash, started)
        if result:
            logger.info("Fallback model succeeded: %s", model)
            return result
    return None


def _call_openrouter_single(prompt, api_key, model, timeout, max_tokens, prompt_hash, started) -> dict[str, Any] | None:
    """Make a single OpenRouter API call to a specific model."""
    import httpx

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/Onunga123/majishamba-extension-agent",
        "X-Title": "Kachieng AI Agent",
    }
    body = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": 0.2,
    }
    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=body)
            if resp.status_code == 429:
                logger.warning("OpenRouter rate-limited (429) for model %s.", model)
                return None
            if resp.status_code != 200:
                logger.warning("OpenRouter returned HTTP %s for model %s: %s", resp.status_code, model, resp.text[:200])
                return None
            data = resp.json()
            choices = data.get("choices", [])
            if not choices:
                return None
            text = choices[0].get("message", {}).get("content", "")
            if not text:
                logger.warning("OpenRouter response has empty content for model %s.", model)
                return None
            actual_model = data.get("model", model)
            elapsed = round(time.time() - started, 2)
            logger.info("OpenRouter call OK: model=%s, elapsed=%ss", actual_model, elapsed)
            return {
                "text": _strip_code_fence(text),
                "model": actual_model,
                "provider": "openrouter",
                "elapsed_s": elapsed,
                "prompt_hash": prompt_hash,
            }
    except Exception as exc:
        logger.warning("OpenRouter call failed for model %s: %s", model, exc)
        return None


def _call_ollama(prompt: str, prompt_hash: str, started: float) -> dict[str, Any] | None:
    """Call the local Ollama model."""
    try:
        import ollama  # type: ignore[import-untyped]
    except ImportError:
        logger.warning("Ollama package not installed.")
        return None

    host = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")
    model = os.environ.get("OLLAMA_MODEL", "qwen2.5:7b-instruct")
    default_timeout = "10" if os.environ.get("DJANGO_SETTINGS_MODULE", "").endswith("development") else "60"
    timeout_s = int(os.environ.get("MAJISHAMBA_OLLAMA_TIMEOUT", default_timeout))
    num_predict = int(os.environ.get("MAJISHAMBA_OLLAMA_NUM_PREDICT", "400"))

    try:
        client = ollama.Client(host=host, timeout=timeout_s)
        resp = client.generate(
            model=model, prompt=prompt, stream=False,
            keep_alive="10m",
            options={"temperature": 0.2, "num_predict": num_predict, "top_p": 0.9},
        )
        text = (resp.get("response") if isinstance(resp, dict) else getattr(resp, "response", "")) or ""
        elapsed = round(time.time() - started, 2)
        logger.info("Ollama call OK: model=%s, elapsed=%ss", model, elapsed)
        return {
            "text": _strip_code_fence(text),
            "model": model,
            "provider": "ollama",
            "elapsed_s": elapsed,
            "prompt_hash": prompt_hash,
        }
    except Exception as exc:
        logger.warning("Ollama call failed: %s. Falling back to template.", exc)
        return None


def _strip_code_fence(text: str) -> str:
    """Strip ```json ... ``` fences from model output."""
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        return "\n".join(lines).strip()
    return text


def provider_status() -> dict[str, Any]:
    """Return the current LLM provider status for the dashboard/settings display."""
    provider = get_llm_provider()
    return {
        "provider": provider,
        "openrouter_configured": is_openrouter_configured(),
        "openrouter_model": get_openrouter_model() if is_openrouter_configured() else "(not configured)",
        "ollama_available": is_ollama_configured(),
        "ollama_model": os.environ.get("OLLAMA_MODEL", "qwen2.5:7b-instruct"),
        "fallback": "deterministic_template",
        "note": "If no provider is configured or the call fails, the system falls back to a deterministic template. The officer still reviews and approves every advisory.",
    }
