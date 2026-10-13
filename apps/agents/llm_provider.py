"""Explicit, provider-neutral LLM interface for the Kachieng AI Agent.

Supported modes are selected with ``LLM_PROVIDER``:

* ``openrouter`` — cloud inference through OpenRouter (recommended for demos).
* ``ollama`` — local inference, preserving the open-weights execution path.
* ``none`` — deterministic fallback only.

Provider failures never switch providers or models silently. The caller may
apply the established deterministic fallback, while returned metadata records
which provider was attempted and why it failed. API keys and prompt contents
are never logged by this module.
"""
from __future__ import annotations

import hashlib
import logging
import os
import time
from typing import Any

logger = logging.getLogger("majishamba.llm")

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
SUPPORTED_PROVIDERS = {"openrouter", "ollama", "none"}


def get_llm_provider() -> str:
    """Return the explicitly configured provider, defaulting safely to ``none``."""
    provider = os.environ.get("LLM_PROVIDER", "none").strip().lower()
    if provider not in SUPPORTED_PROVIDERS:
        logger.warning("Unsupported LLM_PROVIDER=%s; using deterministic fallback.", provider)
        return "none"
    return provider


def get_openrouter_api_key() -> str:
    """Return the OpenRouter key from the environment; never log or expose it."""
    return os.environ.get("OPENROUTER_API_KEY", "")


def get_openrouter_model() -> str:
    """Return the configured OpenRouter instruction-following model ID.

    The former ``:free`` variant now returns HTTP 404 because it is no longer
    available for free routing. Keep the model configurable, but default to the
    currently usable catalog slug.
    """
    default = "qwen/qwen-2.5-7b-instruct"
    return os.environ.get("OPENROUTER_MODEL", default).strip() or default


def get_openrouter_timeout() -> int:
    return _positive_int_env("OPENROUTER_TIMEOUT_SECONDS", 60)


def get_openrouter_max_tokens() -> int:
    return _positive_int_env("OPENROUTER_MAX_OUTPUT_TOKENS", 1200)


def get_openrouter_json_mode() -> bool:
    """Whether to request the provider's JSON object response mode."""
    return _env_bool("OPENROUTER_JSON_MODE", True)


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    return default if value is None else value.lower() in {"1", "true", "yes", "on"}


def is_openrouter_configured() -> bool:
    return bool(get_openrouter_api_key())


def is_ollama_configured() -> bool:
    if os.environ.get("MAJISHAMBA_SKIP_OLLAMA", "0") == "1":
        return False
    try:
        import ollama  # noqa: F401
    except ImportError:
        return False
    return True


def call_llm(prompt: str, *, json_mode: bool | None = None) -> dict[str, Any] | None:
    """Call the selected provider and return text plus execution metadata.

    A successful result has non-empty ``text``. A failed configured-provider
    result has no text but includes a safe ``status`` and ``error`` code so the
    graph can use the deterministic fallback transparently. ``none`` returns
    ``None`` because no model was requested.
    """
    provider = get_llm_provider()
    prompt_hash = hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:16]
    started = time.time()

    if provider == "none":
        logger.info("LLM_PROVIDER=none; using deterministic template.")
        return None
    if provider == "openrouter":
        if not is_openrouter_configured():
            logger.warning("OpenRouter selected but OPENROUTER_API_KEY is not set.")
            return _failure(provider, get_openrouter_model(), prompt_hash, started, "missing_api_key")
        return _call_openrouter(prompt, prompt_hash, started, json_mode=json_mode)
    if provider == "ollama":
        if not is_ollama_configured():
            logger.warning("Ollama selected but the client is unavailable.")
            return _failure(
                provider,
                os.environ.get("OLLAMA_MODEL", "qwen2.5:7b-instruct"),
                prompt_hash,
                started,
                "unavailable",
            )
        return _call_ollama(prompt, prompt_hash, started)
    return None  # Defensive; get_llm_provider normalizes unsupported values.


def _call_openrouter(
    prompt: str,
    prompt_hash: str,
    started: float,
    *,
    json_mode: bool | None = None,
) -> dict[str, Any]:
    """Make exactly one request to OpenRouter using the configured model."""
    import httpx

    model = get_openrouter_model()
    timeout = get_openrouter_timeout()
    body = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": get_openrouter_max_tokens(),
        "temperature": 0.2,
    }
    # OpenRouter passes this through to compatible chat-completion models.  It
    # is deliberately configurable because some legacy/free models reject it.
    if get_openrouter_json_mode() if json_mode is None else json_mode:
        body["response_format"] = {"type": "json_object"}
    headers = {
        "Authorization": f"Bearer {get_openrouter_api_key()}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/Onunga123/majishamba-extension-agent",
        "X-Title": "Kachieng AI Agent",
    }

    try:
        with httpx.Client(timeout=timeout) as client:
            response = client.post(OPENROUTER_URL, headers=headers, json=body)
        if response.status_code != 200:
            error = {
                401: "authentication_error",
                403: "authentication_error",
                408: "request_timeout",
                429: "rate_limited",
            }.get(
                response.status_code,
                "model_unavailable" if response.status_code >= 500 else "http_error",
            )
            logger.warning("OpenRouter request failed: status=%s error=%s", response.status_code, error)
            return _failure("openrouter", model, prompt_hash, started, error, response.status_code)
        try:
            data = response.json()
        except (TypeError, ValueError):
            return _failure("openrouter", model, prompt_hash, started, "malformed_response", 200)
        choices = data.get("choices") if isinstance(data, dict) else None
        choice = choices[0] if isinstance(choices, list) and choices else {}
        if not isinstance(choice, dict):
            choice = {}
        message = choice.get("message")
        if not isinstance(message, dict):
            message = {}
        actual_model = data.get("model") or model
        finish_reason = choice.get("finish_reason")
        incomplete_details = choice.get("incomplete_details") or data.get("incomplete_details")
        refusal = message.get("refusal")
        incomplete = finish_reason in {"length", "max_tokens", "incomplete"} or bool(incomplete_details)
        if refusal:
            return _failure(
                "openrouter",
                actual_model,
                prompt_hash,
                started,
                "refusal",
                200,
                configured_model=model,
                finish_reason=finish_reason,
                incomplete_details=incomplete_details,
            )
        if incomplete:
            if not isinstance(message.get("content", ""), str) or not message.get("content", "").strip():
                return _failure(
                    "openrouter",
                    actual_model,
                    prompt_hash,
                    started,
                    "incomplete_response",
                    200,
                    configured_model=model,
                    finish_reason=finish_reason,
                    incomplete_details=incomplete_details,
                )
            return _incomplete_result(
                message["content"], actual_model, model, prompt_hash, started, finish_reason, incomplete_details
            )
        content = message.get("content", "")
        if not isinstance(content, str) or not content.strip():
            return _failure(
                "openrouter",
                actual_model,
                prompt_hash,
                started,
                "empty_response",
                200,
                configured_model=model,
                finish_reason=finish_reason,
                incomplete_details=incomplete_details,
            )
        elapsed = round(time.time() - started, 2)
        logger.info("OpenRouter request succeeded: model=%s elapsed=%ss", actual_model, elapsed)
        result = {
            "text": _strip_code_fence(content),
            "model": actual_model,
            "configured_model": model,
            "provider": "openrouter",
            "execution_mode": "openrouter",
            "status": "incomplete" if incomplete else "success",
            "finish_reason": finish_reason or "",
            "incomplete_details": incomplete_details or {},
            "elapsed_s": elapsed,
            "prompt_hash": prompt_hash,
        }
        if incomplete:
            result["error"] = "incomplete_response"
        return result
    except httpx.TimeoutException:
        logger.warning("OpenRouter request timed out after %ss.", timeout)
        return _failure("openrouter", model, prompt_hash, started, "timeout")
    except httpx.RequestError:
        logger.warning("OpenRouter network request failed.")
        return _failure("openrouter", model, prompt_hash, started, "network_error")
    except Exception:
        logger.exception("Unexpected OpenRouter response handling failure.")
        return _failure("openrouter", model, prompt_hash, started, "unexpected_error")


def _call_ollama(prompt: str, prompt_hash: str, started: float) -> dict[str, Any]:
    """Call the existing local Ollama integration without changing its settings."""
    try:
        import ollama  # type: ignore[import-untyped]
    except ImportError:
        return _failure(
            "ollama",
            os.environ.get("OLLAMA_MODEL", "qwen2.5:7b-instruct"),
            prompt_hash,
            started,
            "client_missing",
        )

    host = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")
    model = os.environ.get("OLLAMA_MODEL", "qwen2.5:7b-instruct")
    default_timeout = "10" if os.environ.get("DJANGO_SETTINGS_MODULE", "").endswith("development") else "60"
    timeout_s = _positive_int_env("MAJISHAMBA_OLLAMA_TIMEOUT", int(default_timeout))
    num_predict = _positive_int_env("MAJISHAMBA_OLLAMA_NUM_PREDICT", 400)
    try:
        response = ollama.Client(host=host, timeout=timeout_s).generate(
            model=model,
            prompt=prompt,
            stream=False,
            keep_alive=os.environ.get("MAJISHAMBA_OLLAMA_KEEP_ALIVE", "10m"),
            options={"temperature": 0.2, "num_predict": num_predict, "top_p": 0.9},
        )
        text = (
            response.get("response")
            if isinstance(response, dict)
            else getattr(response, "response", "")
        ) or ""
        if not isinstance(text, str) or not text.strip():
            return _failure("ollama", model, prompt_hash, started, "empty_response")
        return {
            "text": _strip_code_fence(text),
            "model": model,
            "configured_model": model,
            "provider": "ollama",
            "execution_mode": "ollama",
            "status": "success",
            "elapsed_s": round(time.time() - started, 2),
            "prompt_hash": prompt_hash,
        }
    except Exception:
        logger.exception("Ollama request failed; deterministic fallback will be used.")
        return _failure("ollama", model, prompt_hash, started, "request_failed")


def _failure(
    provider: str,
    model: str,
    prompt_hash: str,
    started: float,
    error: str,
    http_status: int | None = None,
    *,
    configured_model: str | None = None,
    finish_reason: str | None = None,
    incomplete_details: Any = None,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "provider": provider,
        "execution_mode": provider,
        "configured_model": configured_model or model,
        "model": model,
        "status": "failed",
        "error": error,
        "elapsed_s": round(time.time() - started, 2),
        "prompt_hash": prompt_hash,
    }
    if http_status is not None:
        result["http_status"] = http_status
    if finish_reason:
        result["finish_reason"] = finish_reason
    if incomplete_details:
        result["incomplete_details"] = incomplete_details
    return result


def _incomplete_result(
    content: str,
    actual_model: str,
    configured_model: str,
    prompt_hash: str,
    started: float,
    finish_reason: str | None,
    incomplete_details: Any,
) -> dict[str, Any]:
    """Preserve incomplete provider text without treating it as usable output."""
    return {
        "text": _strip_code_fence(content),
        "model": actual_model,
        "configured_model": configured_model,
        "provider": "openrouter",
        "execution_mode": "openrouter",
        "status": "incomplete",
        "error": "incomplete_response",
        "finish_reason": finish_reason or "",
        "incomplete_details": incomplete_details or {},
        "elapsed_s": round(time.time() - started, 2),
        "prompt_hash": prompt_hash,
    }


def _positive_int_env(name: str, default: int) -> int:
    try:
        return max(1, int(os.environ.get(name, str(default))))
    except ValueError:
        logger.warning("Invalid integer in %s; using default.", name)
        return default


def _strip_code_fence(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        return "\n".join(lines).strip()
    return text


def provider_status() -> dict[str, Any]:
    provider = get_llm_provider()
    return {
        "provider": provider,
        "openrouter_configured": is_openrouter_configured(),
        "openrouter_model": get_openrouter_model(),
        "ollama_available": is_ollama_configured(),
        "ollama_model": os.environ.get("OLLAMA_MODEL", "qwen2.5:7b-instruct"),
        "fallback": "deterministic_template",
        "note": "Provider failures use the deterministic template and preserve failure metadata; providers are never switched silently.",
    }