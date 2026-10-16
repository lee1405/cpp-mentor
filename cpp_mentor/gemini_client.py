"""Thin wrapper around the Google Gemini API (google-genai SDK)."""
from __future__ import annotations

import os
from typing import Any


class GeminiError(RuntimeError):
    pass


def _client(cfg: dict[str, Any]):
    try:
        from google import genai
    except ImportError as e:  # pragma: no cover
        raise GeminiError(
            "The 'google-genai' package is not installed. Run: pip install -r requirements.txt"
        ) from e

    key = os.environ.get(cfg.get("gemini", {}).get("api_key_env", "GEMINI_API_KEY"), "")
    if not key:
        raise GeminiError(
            "No Gemini API key found. Set the environment variable GEMINI_API_KEY "
            "(Windows: setx GEMINI_API_KEY \"AIza...\" then reopen the terminal)."
        )
    return genai.Client(api_key=key)


def chat(cfg: dict[str, Any], system_prompt: str, history: list[dict[str, str]],
         user_message: str, temperature: float | None = None) -> str:
    """Send a conversation to Gemini and return the text reply.

    history: list of {"role": "user"|"model", "content": "..."}
    """
    client = _client(cfg)
    model_name = cfg.get("gemini", {}).get("model", "gemini-2.5-flash")
    temp = cfg.get("gemini", {}).get("temperature", 0.7) if temperature is None else temperature

    contents = [
        {"role": h["role"], "parts": [{"text": h["content"]}]}
        for h in history
    ]
    contents.append({"role": "user", "parts": [{"text": user_message}]})

    try:
        resp = client.models.generate_content(
            model=model_name,
            contents=contents,
            config={
                "system_instruction": system_prompt,
                "temperature": temp,
            },
        )
    except Exception as e:  # network / API errors
        raise GeminiError(f"Gemini API call failed: {e}") from e

    text = (resp.text or "").strip()
    if not text:
        raise GeminiError("Gemini returned an empty response.")
    return text


def chat_json(cfg: dict[str, Any], system_prompt: str, user_message: str) -> Any:
    """Ask Gemini to return strict JSON and parse it."""
    prompt = (
        system_prompt
        + "\n\nIMPORTANT: Respond with ONLY a valid JSON object. No markdown, no code fences, "
        "no commentary before or after the JSON."
    )
    raw = chat(cfg, prompt, [], user_message, temperature=0.3)
    # Strip accidental code fences.
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.strip("`")
        if raw.lower().startswith("json"):
            raw = raw[4:]
    import json
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        raise GeminiError(f"Gemini did not return valid JSON: {e}\n---\n{raw[:500]}") from e
