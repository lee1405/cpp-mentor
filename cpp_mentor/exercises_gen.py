"""Personalized exercise generation.

Instead of using a fixed, googlable problem set, the agent asks Gemini to
generate a FRESH exercise for this learner on each topic — with specific
numbers, names and edge cases — plus hidden test cases and a reference
solution. Because the problem is unique to this learner and this day, it
cannot be found online or copied from a friend.
"""
from __future__ import annotations

import json
from typing import Any

from .gemini_client import chat_json

_SYSTEM = (
    "You are an expert C/C++ instructor generating a single programming exercise "
    "for a fresher. You must return ONLY a JSON object with this exact schema:\n"
    "{\n"
    '  "id": "string (kebab-case, unique, based on the topic)",\n'
    '  "title": "string",\n'
    '  "language": "c" or "cpp",\n'
    '  "prompt": "string — the full problem statement given to the learner. '
    "Use SPECIFIC, unusual numbers and names so the problem is not findable online. "
    "State the exact input/output format precisely.",\n'
    '  "tests": [ {"name": "string", "input": "string", "expected": "string"} ],\n'
    '  "reference_solution": "string — a correct, complete program for this language"\n'
    "}\n"
    "Rules:\n"
    "- Provide 3 to 5 test cases including at least one edge case.\n"
    "- 'input' is what is fed to stdin; 'expected' is the exact stdout (trim trailing newline).\n"
    "- The reference_solution MUST produce exactly the expected outputs for all tests.\n"
    "- Keep the difficulty appropriate for the stated level.\n"
    "- No markdown, no code fences, no text outside the JSON."
)


def generate_exercise(cfg: dict[str, Any], topic: dict[str, Any],
                      language: str = "c", level: str = "beginner") -> dict[str, Any]:
    """Ask Gemini for a fresh exercise for the given topic."""
    user = (
        f"Topic: {topic.get('title')}\n"
        f"Objectives: {json.dumps(topic.get('objectives', []))}\n"
        f"Language: {language}\n"
        f"Level: {level}\n"
        "Generate one exercise now."
    )
    data = chat_json(cfg, _SYSTEM, user)
    # Basic validation.
    if not isinstance(data, dict) or "prompt" not in data or "tests" not in data:
        raise ValueError(f"Generated exercise missing required fields: {data}")
    data.setdefault("language", language)
    data.setdefault("id", topic.get("id", "exercise"))
    data.setdefault("reference_solution", "")
    return data


def generate_quiz(cfg: dict[str, Any], topic: dict[str, Any], count: int = 3) -> list[dict[str, Any]]:
    """Ask Gemini for a short multiple-choice quiz on the topic.

    Returns a list of {"question":..., "options":[...], "answer": <index>, "explanation":...}
    """
    system = (
        "You are an expert C/C++ instructor. Return ONLY a JSON object: "
        '{"quiz": [ {"question": "string", "options": ["a","b","c","d"], '
        '"answer": <0-based index of the correct option>, "explanation": "string"} ]}. '
        f"Produce exactly {count} questions. No markdown, no text outside the JSON."
    )
    user = (
        f"Topic: {topic.get('title')}\n"
        f"Objectives: {json.dumps(topic.get('objectives', []))}\n"
        "Create the quiz now."
    )
    data = chat_json(cfg, system, user)
    quiz = data.get("quiz", []) if isinstance(data, dict) else []
    return quiz[:count]
