"""Thin wrapper around the Anthropic SDK used by every step."""
from __future__ import annotations

import json
import os
import re

import anthropic

DEFAULT_MODEL = os.environ.get("LITSCOUT_MODEL", "claude-opus-5-5")
FALLBACK_BETA = "server-side-fallback-2026-07-01"

_client = None


def client():
    global _client
    if _client is None:
        # Reads ANTHROPIC_API_KEY (or an `ant auth login` profile) from the environment.
        _client = anthropic.Anthropic()
    return _client


def ask(prompt: str, system: str = "", effort: str = "medium", max_tokens: int = 32000,
        model: str | None = None) -> str:
    """Send one request and return the text of the reply.

    Streams so that long inputs/outputs do not hit HTTP timeouts. Uses the
    server-side refusal fallback so a rare safety decline is retried on a
    fallback model instead of returning nothing.
    """
    kwargs = dict(
        model=model or DEFAULT_MODEL,
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}],
        output_config={"effort": effort},
        betas=[FALLBACK_BETA],
        fallbacks="default",
    )
    if system:
        kwargs["system"] = system
    with client().beta.messages.stream(**kwargs) as stream:
        msg = stream.get_final_message()
    if msg.stop_reason == "refusal":
        raise RuntimeError("The model declined this request (stop_reason=refusal).")
    text = "".join(b.text for b in msg.content if b.type == "text")
    if msg.stop_reason == "max_tokens":
        text += "\n\n[output cut off at max_tokens]"
    return text


def ask_json(prompt: str, system: str = "", effort: str = "low", max_tokens: int = 32000):
    """Ask for JSON and parse it. The prompt must say what JSON shape to return."""
    text = ask(prompt + "\n\nReturn only JSON, no prose and no code fences.",
               system=system, effort=effort, max_tokens=max_tokens)
    return parse_json(text)


def parse_json(text: str):
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if fence:
        text = fence.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # take the outermost [...] or {...}
        for open_, close in (("[", "]"), ("{", "}")):
            i, j = text.find(open_), text.rfind(close)
            if i != -1 and j > i:
                try:
                    return json.loads(text[i:j + 1])
                except json.JSONDecodeError:
                    continue
        raise ValueError("Model reply was not valid JSON:\n" + text[:500])
