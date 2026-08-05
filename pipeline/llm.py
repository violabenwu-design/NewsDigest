"""Shared LLM helper: one structured-output call, JSON back.

Backend is a spec string, selected by DIGEST_LLM_BACKEND (or set llm.BACKEND
in code, or pass backend= per call):
  claude[:<model>]  - Anthropic API (default model claude-opus-5;
                      needs ANTHROPIC_API_KEY). e.g. claude:claude-fable-5
  ollama[:<model>]  - Ollama /api/chat structured outputs (default model
                      qwen3:8b; OLLAMA_URL for the server). Model names may
                      themselves contain colons, e.g. ollama:kimi-k3:cloud
"""
from __future__ import annotations

import json
import logging
import os

import httpx

log = logging.getLogger(__name__)

BACKEND = os.environ.get("DIGEST_LLM_BACKEND", "claude")

CLAUDE_MODEL = os.environ.get("DIGEST_CLAUDE_MODEL", "claude-opus-5")
OLLAMA_MODEL = os.environ.get("DIGEST_OLLAMA_MODEL", "qwen3:8b")
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")

_claude_client = None


def resolve(spec: str) -> tuple[str, str]:
    """'ollama:kimi-k3:cloud' -> ('ollama', 'kimi-k3:cloud'); bare kind -> default model."""
    kind, _, model = spec.partition(":")
    if kind not in ("claude", "ollama"):
        raise ValueError(f"unknown backend kind {kind!r} in spec {spec!r}")
    return kind, model or (CLAUDE_MODEL if kind == "claude" else OLLAMA_MODEL)


def _claude_call(model, system, user, schema, max_tokens, effort):
    global _claude_client
    if _claude_client is None:
        import anthropic

        # Daily batch job: latency doesn't matter, completing does. Ride out
        # transient 429/5xx/529 (overloaded) with generous SDK-level retries.
        _claude_client = anthropic.Anthropic(max_retries=8, timeout=600.0)
    # No refusal fallbacks here on purpose: in a model comparison, a fallback
    # model's answer would silently pollute the column. A refusal skips the call.
    # (If production ever moves to claude-fable-5, re-add the beta fallbacks
    # path for it — see git history.)
    response = _claude_client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=system,
        output_config={
            "effort": effort,
            "format": {"type": "json_schema", "schema": schema},
        },
        messages=[{"role": "user", "content": user}],
    )
    if response.stop_reason == "refusal":
        log.warning("%s refused request; skipping", model)
        return None
    if response.stop_reason == "max_tokens":
        log.warning("hit max_tokens; output may be truncated")
    return next((b.text for b in response.content if b.type == "text"), "")


def _ollama_call(model, system, user, schema, max_tokens, effort):
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "format": schema,  # Ollama constrains output to this JSON schema
        "stream": False,
        "think": False,
        "options": {"num_ctx": 16384, "temperature": 0, "num_predict": max_tokens},
    }
    resp = httpx.post(f"{OLLAMA_URL}/api/chat", json=body, timeout=900)
    if resp.status_code == 400 and "think" in resp.text.lower():
        # some models (always-on reasoners) reject think=false; retry without it
        body.pop("think")
        resp = httpx.post(f"{OLLAMA_URL}/api/chat", json=body, timeout=900)
    resp.raise_for_status()
    return resp.json()["message"]["content"]


def structured_call(
    system: str,
    user: str,
    schema: dict,
    max_tokens: int = 16000,
    effort: str = "medium",
    backend: str | None = None,
) -> dict | None:
    """Run one structured-output request. Returns parsed JSON, or None if the
    call failed — callers must treat None as "skip this item", never as fatal."""
    kind, model = resolve(backend or BACKEND)
    try:
        if kind == "ollama":
            text = _ollama_call(model, system, user, schema, max_tokens, effort)
        else:
            text = _claude_call(model, system, user, schema, max_tokens, effort)
    except Exception as e:
        # Retries are already exhausted by here (SDK-level). One dead call must
        # not destroy a whole run, so degrade instead of raising.
        log.error("%s call failed after retries: %s: %s", model, type(e).__name__, e)
        return None
    if text is None:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        log.error("failed to parse model JSON (%s): %s", backend, e)
        return None
