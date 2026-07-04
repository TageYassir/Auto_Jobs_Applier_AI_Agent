from __future__ import annotations

import os
import time
from typing import Optional

import httpx

import config as cfg
from src.logging import logger

DEFAULT_OLLAMA_URL = "http://127.0.0.1:11434"
DEFAULT_MODEL = "gemma:latest"
DEFAULT_TIMEOUT_SECONDS = 60
DEFAULT_MAX_RETRIES = 2


def _env_bool(value: str | None, default: bool = True) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _get_setting(name: str, default):
    if hasattr(cfg, name):
        value = getattr(cfg, name)
        if value is not None and value != "":
            return value
    return os.getenv(name, default)


def _resolve_config() -> dict:
    return {
        "enabled": _env_bool(str(_get_setting("LLM_ENABLED", True)).strip(), True),
        "base_url": _get_setting("OLLAMA_BASE_URL", DEFAULT_OLLAMA_URL).rstrip("/"),
        "model": _get_setting("LLM_MODEL", DEFAULT_MODEL),
        "timeout_seconds": int(_get_setting("LLM_TIMEOUT_SECONDS", DEFAULT_TIMEOUT_SECONDS)),
        "max_retries": int(_get_setting("LLM_MAX_RETRIES", DEFAULT_MAX_RETRIES)),
    }


def is_llm_available() -> bool:
    settings = _resolve_config()
    if not settings["enabled"]:
        return False

    try:
        timeout = httpx.Timeout(settings["timeout_seconds"], connect=5.0)
        response = httpx.get(f"{settings['base_url']}/api/tags", timeout=timeout)
        return response.status_code == 200
    except Exception as exc:
        logger.warning(f"LLM unavailable (Ollama). {exc}")
        return False


def generate_text(
    prompt: str,
    system: str | None = None,
    temperature: float = 0.2,
    max_tokens: int | None = None,
) -> Optional[str]:
    settings = _resolve_config()
    if not settings["enabled"]:
        logger.warning("LLM disabled. Falling back to manual/skip mode.")
        return None

    timeout = httpx.Timeout(settings["timeout_seconds"], connect=5.0)
    payload = {
        "model": settings["model"],
        "messages": [],
        "stream": False,
        "options": {
            "temperature": temperature,
        },
    }

    if system:
        payload["messages"].append({"role": "system", "content": system})
    payload["messages"].append({"role": "user", "content": prompt})

    if max_tokens is not None:
        payload["options"]["num_predict"] = max_tokens

    last_error: Exception | None = None
    for attempt in range(settings["max_retries"] + 1):
        try:
            response = httpx.post(
                f"{settings['base_url']}/api/chat",
                json=payload,
                timeout=timeout,
            )
            response.raise_for_status()
            data = response.json()
            content = (data.get("message") or {}).get("content")
            if content and content.strip():
                return content.strip()
            logger.warning("LLM returned an empty response. Falling back to manual/skip mode.")
            return None
        except Exception as exc:
            last_error = exc
            if attempt < settings["max_retries"]:
                time.sleep(0.8 * (attempt + 1))
                continue
            logger.warning(f"LLM unavailable (Ollama). Falling back to manual/skip mode. {exc}")
            return None

    if last_error:
        logger.warning(f"LLM unavailable (Ollama). Falling back to manual/skip mode. {last_error}")
    return None


def summarize_or_none(text: str) -> Optional[str]:
    prompt = (
        "Summarize the following text in 3-5 concise bullet points focused on skills, requirements, "
        "and relevant responsibilities. Return plain text only.\n\n"
        f"TEXT:\n{text}"
    )
    return generate_text(prompt, system="You are a concise recruitment assistant.", temperature=0.2, max_tokens=300)
