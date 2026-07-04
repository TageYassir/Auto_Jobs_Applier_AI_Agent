from __future__ import annotations

import httpx

from src.ai_hawk.llm import provider


def test_generate_text_returns_content(monkeypatch):
    def fake_post(url, json, timeout):
        return httpx.Response(200, json={"message": {"content": "hello world"}})

    monkeypatch.setattr(provider.httpx, "post", fake_post)
    monkeypatch.setattr(provider, "_resolve_config", lambda: {"enabled": True, "base_url": "http://127.0.0.1:11434", "model": "gemma:latest", "timeout_seconds": 1, "max_retries": 0})

    assert provider.generate_text("prompt") == "hello world"


def test_generate_text_returns_none_on_error(monkeypatch):
    def fake_post(url, json, timeout):
        raise httpx.ConnectError("down", request=httpx.Request("POST", url))

    monkeypatch.setattr(provider.httpx, "post", fake_post)
    monkeypatch.setattr(provider, "_resolve_config", lambda: {"enabled": True, "base_url": "http://127.0.0.1:11434", "model": "gemma:latest", "timeout_seconds": 1, "max_retries": 0})

    assert provider.generate_text("prompt") is None
